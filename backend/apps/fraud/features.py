"""
Feature extraction (REQ-FRD-001). Django owns the data, so it gathers claim, policy, vehicle, history and
document facts into a plain JSON payload; the Flask service is stateless and only scores it. This keeps the
scoring engine swappable (rules today, an ML model later) without giving it database access.
"""
from datetime import timedelta

from apps.claims.models import Claim, ClaimStatus, ClosureReason
from apps.documents.models import ClaimDocument, DocumentStatus

SIMILAR_WINDOW_DAYS = 30


def _money(v):
    return float(v) if v is not None else None


def build_payload(claim: Claim) -> dict:
    policy, vehicle = claim.policy, claim.policy.vehicle
    customer = policy.customer
    year_ago = claim.incident_date - timedelta(days=365)
    others = (Claim.objects.filter(policy__customer=customer).exclude(pk=claim.pk)
              .exclude(closure_reason=ClosureReason.WITHDRAWN))
    vehicle_claims = Claim.objects.filter(policy__vehicle=vehicle).exclude(pk=claim.pk).exclude(
        closure_reason=ClosureReason.WITHDRAWN)

    similar = []
    window = timedelta(days=SIMILAR_WINDOW_DAYS)
    for c in vehicle_claims.filter(incident_date__range=(claim.incident_date - window, claim.incident_date + window)):
        similar.append({"claim_number": c.claim_number, "claim_type": c.claim_type,
                        "incident_date": c.incident_date.isoformat(),
                        "days_apart": abs((c.incident_date - claim.incident_date).days), "status": c.status})

    docs = list(ClaimDocument.objects.filter(claim=claim, is_current=True))
    hashes = [d.sha256 for d in docs]
    reused = (ClaimDocument.objects.filter(sha256__in=hashes).exclude(claim=claim)
              .exclude(document_type__in=["KYC", "ADDRESS_PROOF", "VEHICLE_REGISTRATION"])  # identity docs repeat legitimately
              .values("claim_id").distinct().count()) if hashes else 0

    return {
        "claim": {
            "claim_number": claim.claim_number, "claim_type": claim.claim_type,
            "requested_amount": _money(claim.requested_amount),
            "incident_date": claim.incident_date.isoformat(), "incident_time": claim.incident_time.strftime("%H:%M"),
            "submitted_at": claim.submitted_at.isoformat(), "incident_location": claim.incident_location,
            "description_length": len(claim.description.strip()),
        },
        "policy": {
            "policy_number": policy.policy_number, "start_date": policy.start_date.isoformat(),
            "end_date": policy.end_date.isoformat(), "idv": _money(policy.idv),
            "cumulative_approved_amount": _money(policy.cumulative_approved_amount),
            "premium_amount": _money(policy.premium_amount), "status": policy.status,
        },
        "vehicle": {
            "vehicle_type": vehicle.vehicle_type, "manufacturing_year": vehicle.manufacturing_year,
            "purchase_date": vehicle.purchase_date.isoformat(),
            "registration_date": vehicle.registration_date.isoformat(),
        },
        "history": {
            "customer_total_claims": others.count(),
            "customer_claims_last_12_months": others.filter(incident_date__gte=year_ago).count(),
            "vehicle_claims_last_12_months": vehicle_claims.filter(incident_date__gte=year_ago).count(),
            "customer_rejected_claims": others.filter(
                status__in=[ClaimStatus.REJECTED, ClaimStatus.PERMANENTLY_REJECTED]).count(),
            "similar_claims": similar,
        },
        "documents": {
            "types": sorted({d.document_type for d in docs}),
            "count": len(docs),
            "rejected_count": sum(1 for d in docs if d.status == DocumentStatus.REJECTED),
            "reused_in_other_claims": reused,
        },
    }
