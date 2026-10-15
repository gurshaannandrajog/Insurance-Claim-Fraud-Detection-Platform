from fraud_service.scoring.base import classify
from fraud_service.scoring.rules import RuleBasedScorer

scorer = RuleBasedScorer()


def codes(result):
    return {f.code for f in result.factors}


def test_risk_bands_match_srs():
    assert classify(0) == "LOW" and classify(29) == "LOW"
    assert classify(30) == "MEDIUM" and classify(59) == "MEDIUM"
    assert classify(60) == "HIGH" and classify(100) == "HIGH"


def test_clean_claim_is_low_risk(payload):
    r = scorer.score(payload)
    assert r.risk_score < 30 and r.risk_level == "LOW"


def test_score_is_sum_of_explained_factor_weights(payload):
    payload["claim"]["requested_amount"] = 500000
    payload["history"]["customer_claims_last_12_months"] = 2
    r = scorer.score(payload)
    assert r.risk_score == sum(f.weight for f in r.factors)
    assert {"AMOUNT_NEAR_IDV", "REPEAT_CLAIMS"} <= codes(r)


def test_suspicious_claim_is_high_risk_and_flagged(payload):
    payload["claim"].update(requested_amount=550000, incident_date="2026-01-05", incident_time="02:15",
                            claim_type="FIRE")
    payload["vehicle"]["manufacturing_year"] = 2012
    payload["documents"]["types"] = ["KYC", "ADDRESS_PROOF", "VEHICLE_REGISTRATION"]
    payload["history"]["similar_claims"] = [{"claim_number": "X", "claim_type": "ACCIDENT",
                                             "incident_date": "2026-01-02", "days_apart": 3, "status": "REJECTED"}]
    d = scorer.score(payload).to_dict()
    assert d["risk_level"] == "HIGH" and d["flagged"] is True and d["risk_score"] >= 60
    assert d["factors"] == sorted(d["factors"], key=lambda f: -f["weight"])


def test_score_is_capped_at_100(payload):
    payload["claim"].update(requested_amount=600000, incident_date="2026-01-02", incident_time="01:00",
                            claim_type="FIRE", description_length=5, submitted_at="2026-03-10T00:00:00")
    payload["vehicle"]["manufacturing_year"] = 2005
    payload["history"].update(customer_claims_last_12_months=5, customer_rejected_claims=3,
                              similar_claims=[{"days_apart": 1}])
    payload["documents"].update(types=[], reused_in_other_claims=2, rejected_count=3)
    assert scorer.score(payload).risk_score == 100


def test_reused_evidence_is_detected(payload):
    payload["documents"]["reused_in_other_claims"] = 1
    assert "REUSED_EVIDENCE" in codes(scorer.score(payload))


def test_late_reporting(payload):
    payload["claim"]["submitted_at"] = "2026-08-01T09:00:00"
    assert "LATE_REPORTING" in codes(scorer.score(payload))
