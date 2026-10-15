"""
Django ↔ Flask integration (REQ-FRD-001..007, REQ-CLM-011).

* The HTTP call happens OUTSIDE any DB transaction (never hold row locks while waiting on the network).
* If the service is down, a FAILED assessment is stored, staff are informed, and the claim continues —
  submission is never blocked by the fraud service (graceful degradation). Staff can re-run it later;
  a claim cannot be approved without a completed assessment.
* A HIGH result moves the claim to FRAUD_REVIEW and opens an SIU investigation — it never rejects (REQ-FRD-007).
"""
import logging

from django.db import transaction

from apps.audit.models import AuditAction
from apps.audit.services import log_event
from apps.claims.models import Claim, ClaimStatus, RiskLevel
from apps.claims.workflow import transition
from apps.investigations.models import InvestigationTrigger
from apps.investigations.services import open_investigation

from . import client
from .features import build_payload
from .models import AssessmentStatus, FraudAssessment, FraudIndicator

logger = logging.getLogger(__name__)

FLAGGABLE = {ClaimStatus.SUBMITTED, ClaimStatus.UNDER_REVIEW, ClaimStatus.DOCUMENTS_PENDING}


def classify(score: int) -> str:
    """REQ-FRD-003 — kept here too so Django never trusts a level inconsistent with the score."""
    if score >= 60:
        return RiskLevel.HIGH
    if score >= 30:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def run_assessment(claim: Claim, *, trigger, actor=None, request=None) -> FraudAssessment:
    claim = Claim.objects.select_related("policy__vehicle", "policy__customer__user").get(pk=claim.pk)
    payload = build_payload(claim)
    try:
        result, elapsed = client.assess(payload)
    except client.FraudServiceError as exc:
        logger.warning("Fraud assessment failed for %s: %s", claim.claim_number, exc)
        assessment = FraudAssessment.objects.create(claim=claim, status=AssessmentStatus.FAILED, trigger=trigger,
                                                    requested_by=actor, request_payload=payload,
                                                    error_message=str(exc)[:255])
        log_event(AuditAction.FRAUD_ASSESSMENT_FAILED, claim, actor=actor, request=request,
                  metadata={"error": str(exc), "trigger": trigger})
        return assessment

    score = result["risk_score"]
    level = classify(score)
    with transaction.atomic():
        locked = Claim.objects.select_for_update().get(pk=claim.pk)
        assessment = FraudAssessment.objects.create(
            claim=locked, status=AssessmentStatus.COMPLETED, trigger=trigger, requested_by=actor, risk_score=score,
            risk_level=level, flagged=level == RiskLevel.HIGH, engine=result["engine"], request_payload=payload,
            response_ms=elapsed)
        FraudIndicator.objects.bulk_create([
            FraudIndicator(assessment=assessment, code=str(f.get("code", ""))[:40],
                           category=str(f.get("category", ""))[:30], description=str(f.get("description", ""))[:255],
                           weight=max(0, min(100, int(f.get("weight", 0)))))
            for f in result["factors"] if isinstance(f, dict)])
        locked.current_risk_score, locked.current_risk_level = score, level
        locked.is_flagged = locked.is_flagged or level == RiskLevel.HIGH
        locked.save(update_fields=["current_risk_score", "current_risk_level", "is_flagged", "updated_at"])
        log_event(AuditAction.FRAUD_ASSESSED, locked, actor=actor, request=request,
                  metadata={"score": score, "level": level, "trigger": trigger, "engine": result["engine"]})

        # REQ-FRD-005/006 — flag High risk into Fraud Review (unless SIU has already cleared this review episode)
        if level == RiskLevel.HIGH and locked.status in FLAGGABLE and locked.siu_cleared_at is None:
            top = ", ".join(i.description for i in assessment.indicators.all()[:3])
            reason = f"High fraud risk score {score}/100. Top factors: {top}"
            transition(locked, ClaimStatus.FRAUD_REVIEW, actor=None, internal=True, reason=reason, request=request)
            open_investigation(locked, trigger=InvestigationTrigger.HIGH_RISK, reason=reason, assessment=assessment)
            log_event(AuditAction.CLAIM_FLAGGED, locked, metadata={"score": score})
    return assessment


def latest_completed(claim):
    return claim.fraud_assessments.filter(status=AssessmentStatus.COMPLETED).first()
