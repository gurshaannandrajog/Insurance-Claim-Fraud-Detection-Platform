"""
Transparent, explainable rule-based scoring engine ("rules-v1").

Each rule inspects the feature payload and may return a Factor with a weight (points). The risk score is the
sum of weights, capped at 100. Every point added is explained by a factor, which is what adjusters and SIU see
(REQ-FRD-004). Weights are deliberately simple and documented so they can be defended in a review; an ML model
can later replace this class behind the same interface.

Feature payload (built by Django, see backend/apps/fraud/features.py):
  claim:    claim_type, requested_amount, incident_date, incident_time, submitted_at, description_length
  policy:   start_date, end_date, idv, cumulative_approved_amount
  vehicle:  manufacturing_year, purchase_date
  history:  customer_claims_last_12_months, vehicle_claims_last_12_months, customer_rejected_claims, similar_claims[]
  documents: types[], count, rejected_count, reused_in_other_claims
"""
from datetime import date, datetime

from .base import Factor, RiskScorer, ScoreResult

INCIDENT_EVIDENCE = {
    "ACCIDENT": {"ACCIDENT_PHOTO", "DAMAGE_PHOTO"},
    "FIRE": {"FIRE_EVIDENCE"},
    "THIRD_PARTY": {"THIRD_PARTY_DOCUMENT"},
}


def _date(s):
    return date.fromisoformat(s[:10])


def _dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# --------------------------------------------------------------------------------------------- rules
def rule_amount_vs_idv(f):
    amount, idv = f["claim"]["requested_amount"], f["policy"]["idv"]
    ratio = amount / idv if idv else 0
    if ratio >= 0.8:
        return Factor("AMOUNT_NEAR_IDV", "Claim amount", f"Requested amount is {ratio:.0%} of the insured value", 25)
    if ratio >= 0.5:
        return Factor("AMOUNT_HIGH_VS_IDV", "Claim amount", f"Requested amount is {ratio:.0%} of the insured value", 15)
    if ratio >= 0.3:
        return Factor("AMOUNT_ELEVATED", "Claim amount", f"Requested amount is {ratio:.0%} of the insured value", 6)
    return None


def rule_new_policy(f):
    days = (_date(f["claim"]["incident_date"]) - _date(f["policy"]["start_date"])).days
    if days <= 15:
        return Factor("VERY_NEW_POLICY", "Policy", f"Incident occurred {days} day(s) after the policy started", 22)
    if days <= 60:
        return Factor("NEW_POLICY", "Policy", f"Incident occurred {days} days after the policy started", 10)
    return None


def rule_near_expiry(f):
    days = (_date(f["policy"]["end_date"]) - _date(f["claim"]["incident_date"])).days
    if 0 <= days <= 15:
        return Factor("NEAR_POLICY_EXPIRY", "Policy", f"Incident occurred {days} day(s) before the policy expires", 8)
    return None


def rule_prior_partial_claims(f):
    used = f["policy"].get("cumulative_approved_amount", 0)
    if used and f["policy"]["idv"] and used / f["policy"]["idv"] >= 0.5:
        return Factor("POLICY_HEAVILY_CLAIMED", "Claim history",
                      "More than half of the policy's insured value has already been paid out", 8)
    return None


def rule_claim_frequency(f):
    n = max(f["history"]["customer_claims_last_12_months"], f["history"]["vehicle_claims_last_12_months"])
    if n >= 3:
        return Factor("FREQUENT_CLAIMS", "Claim history", f"{n} other claims in the last 12 months", 20)
    if n == 2:
        return Factor("REPEAT_CLAIMS", "Claim history", "2 other claims in the last 12 months", 12)
    if n == 1:
        return Factor("PRIOR_CLAIM", "Claim history", "1 other claim in the last 12 months", 5)
    return None


def rule_similar_claims(f):
    similar = f["history"].get("similar_claims") or []
    if similar:
        closest = min(s["days_apart"] for s in similar)
        return Factor("SIMILAR_CLAIM_NEARBY", "Duplicate / similar claims",
                      f"{len(similar)} other claim(s) on this vehicle within 30 days (closest {closest} day(s) apart)",
                      18)
    return None


def rule_rejected_history(f):
    n = f["history"]["customer_rejected_claims"]
    if n >= 1:
        return Factor("PRIOR_REJECTIONS", "Claim history", f"Customer has {n} previously rejected claim(s)",
                      min(15, 8 + 4 * (n - 1)))
    return None


def rule_reporting_delay(f):
    delay = (_dt(f["claim"]["submitted_at"]).date() - _date(f["claim"]["incident_date"])).days
    if delay > 30:
        return Factor("LATE_REPORTING", "Claim characteristics", f"Reported {delay} days after the incident", 12)
    if delay > 7:
        return Factor("DELAYED_REPORTING", "Claim characteristics", f"Reported {delay} days after the incident", 5)
    return None


def rule_night_incident(f):
    hour = int(f["claim"]["incident_time"][:2])
    if 0 <= hour < 5:
        return Factor("NIGHT_INCIDENT", "Claim characteristics", "Incident reported between midnight and 5 am", 5)
    return None


def rule_old_vehicle_fire(f):
    age = _date(f["claim"]["incident_date"]).year - f["vehicle"]["manufacturing_year"]
    if f["claim"]["claim_type"] == "FIRE" and age >= 10:
        return Factor("FIRE_OLD_VEHICLE", "Vehicle", f"Fire claim on a {age}-year-old vehicle", 12)
    if age >= 15:
        return Factor("VERY_OLD_VEHICLE", "Vehicle", f"Vehicle is {age} years old", 5)
    return None


def rule_recent_purchase(f):
    days = (_date(f["policy"]["start_date"]) - _date(f["vehicle"]["purchase_date"])).days
    if f["vehicle"]["manufacturing_year"] <= _date(f["policy"]["start_date"]).year - 8 and 0 <= days <= 30:
        return Factor("OLD_VEHICLE_RECENTLY_BOUGHT", "Vehicle",
                      "Older vehicle bought shortly before the policy started", 6)
    return None


def rule_missing_evidence(f):
    needed = INCIDENT_EVIDENCE.get(f["claim"]["claim_type"], set())
    if needed and not needed & set(f["documents"].get("types", [])):
        return Factor("NO_INCIDENT_EVIDENCE", "Documents", "No incident evidence (photos / third-party documents) "
                      "provided yet", 8)
    return None


def rule_reused_documents(f):
    n = f["documents"].get("reused_in_other_claims", 0)
    if n:
        return Factor("REUSED_EVIDENCE", "Documents",
                      f"Identical evidence file(s) were already submitted with {n} other claim(s)", 25)
    return None


def rule_rejected_documents(f):
    if f["documents"].get("rejected_count", 0) >= 2:
        return Factor("MULTIPLE_REJECTED_DOCUMENTS", "Documents", "Several documents were rejected during review", 6)
    return None


def rule_thin_description(f):
    if f["claim"].get("description_length", 0) < 40:
        return Factor("THIN_DESCRIPTION", "Claim characteristics", "Very brief incident description", 4)
    return None


def rule_round_amount(f):
    amt = f["claim"]["requested_amount"]
    if amt >= 100000 and amt % 50000 == 0:
        return Factor("ROUND_AMOUNT", "Claim amount", "Large round-number claim amount", 3)
    return None


RULES = [rule_amount_vs_idv, rule_new_policy, rule_near_expiry, rule_prior_partial_claims, rule_claim_frequency,
         rule_similar_claims, rule_rejected_history, rule_reporting_delay, rule_night_incident, rule_old_vehicle_fire,
         rule_recent_purchase, rule_missing_evidence, rule_reused_documents, rule_rejected_documents,
         rule_thin_description, rule_round_amount]


class RuleBasedScorer(RiskScorer):
    name = "rules-v1"

    def score(self, features: dict) -> ScoreResult:
        factors = [factor for rule in RULES if (factor := rule(features)) is not None]
        total = min(100, sum(fct.weight for fct in factors))
        return ScoreResult(risk_score=total, factors=factors, engine=self.name)
