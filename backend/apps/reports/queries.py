"""
Reporting queries (SRS §4.8, REQ-REP-001..009). Every number is computed from the database at request time.
Each report builder returns {"title", "columns", "rows", "summary"} so that the JSON view and every export
format (CSV / Excel / PDF) render exactly the same filtered data.
"""
from collections import Counter, OrderedDict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.claims.models import Claim, ClaimStatus, ClaimType, RiskLevel
from apps.core.filters import day_range_q
from apps.investigations.models import Investigation, InvestigationStatus
from apps.policies.models import Policy, PolicyRequest, PolicyRequestStatus, PolicyStatus
from apps.vehicles.models import Vehicle

ROW_LIMIT_JSON = 500


def _d(v):
    return float(v or 0)


def _choices_counts(qs, field, choices):
    counts = dict(qs.values_list(field).annotate(n=Count("id")).values_list(field, "n"))
    return [{"key": k, "label": label, "value": counts.get(k, 0)} for k, label in choices]


def _monthly(dates, months=12, values=None):
    """Bucket datetimes/dates into the last N months in Python (portable; no DB time-zone tables needed)."""
    today = timezone.localdate()
    keys = []
    y, m = today.year, today.month
    for _ in range(months):
        keys.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    keys.reverse()
    buckets = OrderedDict((k, 0.0) for k in keys)
    for i, d in enumerate(dates):
        if hasattr(d, "tzinfo") and getattr(d, "tzinfo", None) is not None:
            d = timezone.localtime(d)
        key = f"{d.year:04d}-{d.month:02d}"
        if key in buckets:
            buckets[key] += float(values[i]) if values is not None else 1
    return [{"month": k, "value": round(v, 2)} for k, v in buckets.items()]


# ----------------------------------------------------------------------------- filtering
def filtered_claims(f):
    qs = Claim.objects.select_related("policy__vehicle", "policy__customer__user")
    qs = qs.filter(day_range_q("submitted_at", f.get("date_from"), f.get("date_to")))
    if f.get("claim_type"):
        qs = qs.filter(claim_type=f["claim_type"])
    if f.get("claim_status"):
        qs = qs.filter(status=f["claim_status"])
    if f.get("policy_status"):
        qs = qs.filter(policy__status=f["policy_status"])
    if f.get("risk_level"):
        qs = qs.filter(current_risk_level=f["risk_level"])
    return qs


def filtered_policies(f):
    qs = Policy.objects.select_related("vehicle", "customer__user")
    qs = qs.filter(day_range_q("created_at", f.get("date_from"), f.get("date_to")))
    if f.get("policy_status"):
        qs = qs.filter(status=f["policy_status"])
    if f.get("claim_type") or f.get("claim_status") or f.get("risk_level"):
        qs = qs.filter(pk__in=filtered_claims({k: v for k, v in f.items() if k not in ("date_from", "date_to")})
                       .values("policy_id"))
    return qs


# ----------------------------------------------------------------------------- reports
def claims_report(f):
    qs = filtered_claims(f)
    agg = qs.aggregate(total_requested=Sum("requested_amount"), total_approved=Sum("approved_amount"),
                       avg_approved=Avg("approved_amount"), count=Count("id"))
    summary = {
        "total_claims": agg["count"],
        "total_requested_amount": _d(agg["total_requested"]),                       # REQ-REP-003
        "total_approved_amount": _d(agg["total_approved"]),
        "average_approved_amount": round(_d(agg["avg_approved"]), 2),
        "by_status": _choices_counts(qs, "status", ClaimStatus.choices),             # REQ-REP-002
        "by_type": _choices_counts(qs, "claim_type", ClaimType.choices),            # REQ-REP-004
    }
    columns = ["Claim No.", "Submitted", "Customer", "Vehicle", "Policy", "Type", "Status", "Requested (₹)",
               "Approved (₹)", "Risk score", "Risk level"]
    rows = [[c.claim_number, timezone.localtime(c.submitted_at).strftime("%Y-%m-%d"),
             c.policy.customer.user.full_name, c.policy.vehicle.registration_number, c.policy.policy_number,
             c.get_claim_type_display(), c.get_status_display(), _d(c.requested_amount),
             _d(c.approved_amount) if c.approved_amount is not None else "", c.current_risk_score if
             c.current_risk_score is not None else "", c.get_current_risk_level_display() or ""] for c in qs]
    return {"title": "Claims report", "columns": columns, "rows": rows, "summary": summary}


def fraud_report(f):
    qs = filtered_claims(f).filter(current_risk_score__isnull=False).prefetch_related(
        "fraud_assessments__indicators", "investigations")
    summary = {
        "assessed_claims": qs.count(),
        "flagged_claims": qs.filter(is_flagged=True).count(),
        "in_fraud_review": qs.filter(status=ClaimStatus.FRAUD_REVIEW).count(),
        "risk_distribution": _choices_counts(qs, "current_risk_level", RiskLevel.choices),       # REQ-REP-005
        "average_score": round(_d(qs.aggregate(a=Avg("current_risk_score"))["a"]), 1),
        "open_investigations": Investigation.objects.filter(claim__in=qs).exclude(
            status=InvestigationStatus.COMPLETED).count(),
    }
    columns = ["Claim No.", "Submitted", "Customer", "Type", "Status", "Requested (₹)", "Risk score", "Risk level",
               "Flagged", "Contributing factors", "Investigation"]
    rows = []
    for c in qs:
        latest = next((a for a in c.fraud_assessments.all() if a.status == "COMPLETED"), None)
        factors = "; ".join(i.description for i in latest.indicators.all()) if latest else ""
        inv = next(iter(c.investigations.all()), None)
        rows.append([c.claim_number, timezone.localtime(c.submitted_at).strftime("%Y-%m-%d"),
                     c.policy.customer.user.full_name, c.get_claim_type_display(), c.get_status_display(),
                     _d(c.requested_amount), c.current_risk_score, c.get_current_risk_level_display(),
                     "Yes" if c.is_flagged else "No", factors,
                     (f"{inv.get_status_display()}" + (f" – {inv.get_recommendation_display()}"
                                                       if inv.recommendation else "")) if inv else "—"])
    return {"title": "Fraud & risk report", "columns": columns, "rows": rows, "summary": summary}


def policies_report(f):
    qs = filtered_policies(f)
    agg = qs.aggregate(idv=Sum("idv"), premium=Sum("premium_amount"), approved=Sum("cumulative_approved_amount"))
    summary = {
        "total_policies": qs.count(),
        "by_status": _choices_counts(qs, "status", PolicyStatus.choices),           # REQ-REP-006
        "total_idv": _d(agg["idv"]), "total_premium": _d(agg["premium"]),
        "total_approved_claims": _d(agg["approved"]),
    }
    columns = ["Policy No.", "Customer", "Vehicle", "Plan", "Start", "End", "IDV (₹)", "Premium (₹)",
               "Approved claims (₹)", "Status"]
    rows = [[p.policy_number, p.customer.user.full_name, p.vehicle.registration_number, p.plan_name,
             str(p.start_date), str(p.end_date), _d(p.idv), _d(p.premium_amount), _d(p.cumulative_approved_amount),
             p.get_status_display()] for p in qs]
    return {"title": "Policies report", "columns": columns, "rows": rows, "summary": summary}


def vehicles_report(f):
    qs = Vehicle.objects.select_related("customer__user").filter(
        day_range_q("created_at", f.get("date_from"), f.get("date_to")))
    insured_ids = set(Policy.objects.filter(status__in=PolicyStatus.live()).values_list("vehicle_id", flat=True))
    if f.get("policy_status"):
        qs = qs.filter(policies__status=f["policy_status"]).distinct()
    by_make = Counter(f"{v.make} {v.model}" for v in qs)
    summary = {
        "total_vehicles": qs.count(),                                                 # REQ-REP-007
        "currently_insured": sum(1 for v in qs if v.pk in insured_ids),
        "by_make_model": [{"label": k, "value": n} for k, n in by_make.most_common(10)],
        "by_type": [{"label": k, "value": n} for k, n in Counter(v.get_vehicle_type_display() for v in qs).most_common()],
    }
    columns = ["Registration", "Make", "Model", "Type", "Year", "Owner", "Customer", "Insured", "Registered on"]
    rows = [[v.registration_number, v.make, v.model, v.get_vehicle_type_display(), v.manufacturing_year, v.owner_name,
             v.customer.user.full_name, "Yes" if v.pk in insured_ids else "No",
             timezone.localtime(v.created_at).strftime("%Y-%m-%d")] for v in qs]
    return {"title": "Vehicles report", "columns": columns, "rows": rows, "summary": summary}


def customers_report(f):
    qs = (User.objects.filter(role=Role.CUSTOMER, deleted_at__isnull=True).select_related("customer_profile")
          .filter(day_range_q("date_joined", f.get("date_from"), f.get("date_to")))
          .annotate(vehicles=Count("customer_profile__vehicles", distinct=True),
                    live_policies=Count("customer_profile__policies", distinct=True,
                                        filter=Q(customer_profile__policies__status__in=PolicyStatus.live())),
                    claims=Count("customer_profile__policies__claims", distinct=True)))
    summary = {
        "total_customers": qs.count(),                                                # REQ-REP-008
        "active_customers": qs.filter(is_active=True, live_policies__gt=0).count(),
        "verified_customers": qs.filter(is_email_verified=True).count(),
        "registration_trend": _monthly(list(qs.values_list("date_joined", flat=True))),
    }
    columns = ["Name", "Email", "Phone", "City", "Joined", "Verified", "Vehicles", "Live policies", "Claims", "Status"]
    rows = [[u.full_name, u.email, getattr(u.customer_profile, "phone", ""), getattr(u.customer_profile, "city", ""),
             timezone.localtime(u.date_joined).strftime("%Y-%m-%d"), "Yes" if u.is_email_verified else "No",
             u.vehicles, u.live_policies, u.claims, "Active" if u.is_active else "Inactive"] for u in qs]
    return {"title": "Customers report", "columns": columns, "rows": rows, "summary": summary}


REPORTS = {"claims": claims_report, "fraud": fraud_report, "policies": policies_report,
           "vehicles": vehicles_report, "customers": customers_report}


# ----------------------------------------------------------------------------- dashboards
def admin_dashboard():
    claims = Claim.objects.all()
    agg = claims.aggregate(req=Sum("requested_amount"), appr=Sum("approved_amount"), avg=Avg("approved_amount"))
    since = timezone.now() - timedelta(days=365)
    recent = list(claims.filter(submitted_at__gte=since).values_list("submitted_at", "requested_amount",
                                                                      "approved_amount"))
    vehicles = Vehicle.objects.all()
    return {
        "kpis": {
            "total_customers": User.objects.filter(role=Role.CUSTOMER, deleted_at__isnull=True).count(),
            "total_vehicles": vehicles.count(),
            "active_policies": Policy.objects.filter(status__in=[PolicyStatus.ACTIVE,
                                                                 PolicyStatus.PARTIALLY_CLAIMED]).count(),
            "total_claims": claims.count(),
            "pending_claims": claims.filter(status__in=ClaimStatus.in_processing()).count(),
            "approved_claims": claims.filter(status=ClaimStatus.APPROVED).count(),
            "rejected_claims": claims.filter(status__in=[ClaimStatus.REJECTED,
                                                         ClaimStatus.PERMANENTLY_REJECTED]).count(),
            "fraud_review_claims": claims.filter(status=ClaimStatus.FRAUD_REVIEW).count(),
            "high_risk_claims": claims.filter(current_risk_level=RiskLevel.HIGH).count(),
            "total_requested_amount": _d(agg["req"]),
            "total_approved_amount": _d(agg["appr"]),
            "average_approved_amount": round(_d(agg["avg"]), 2),
            "pending_policy_requests": PolicyRequest.objects.filter(status=PolicyRequestStatus.PENDING).count(),
        },
        "charts": {
            "claims_by_status": _choices_counts(claims, "status", ClaimStatus.choices),
            "claims_by_type": _choices_counts(claims, "claim_type", ClaimType.choices),
            "policy_status": _choices_counts(Policy.objects.all(), "status", PolicyStatus.choices),
            "risk_distribution": _choices_counts(claims.exclude(current_risk_level=""), "current_risk_level",
                                                 RiskLevel.choices),
            "claim_amount_trend": [
                {"month": r["month"], "requested": r["value"], "approved": a["value"]}
                for r, a in zip(_monthly([x[0] for x in recent], values=[x[1] for x in recent]),
                                _monthly([x[0] for x in recent], values=[x[2] or Decimal(0) for x in recent]))],
            "claims_trend": _monthly([x[0] for x in recent]),
            "customer_registrations": _monthly(list(User.objects.filter(role=Role.CUSTOMER).values_list(
                "date_joined", flat=True))),
            "vehicles_by_type": [{"label": k, "value": n} for k, n in Counter(
                v.get_vehicle_type_display() for v in vehicles).most_common()],
            "vehicles_by_make": [{"label": k, "value": n} for k, n in Counter(
                vehicles.values_list("make", flat=True)).most_common(8)],
        },
    }
