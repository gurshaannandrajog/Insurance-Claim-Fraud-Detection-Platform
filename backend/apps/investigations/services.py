"""SIU investigation workflow (SRS §4.7.2 'Fraud Investigation', activity diagram SIU swim-lane)."""
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import log_event
from apps.claims.models import Claim, ClaimStatus
from apps.claims.workflow import transition
from apps.core.exceptions import BusinessRuleError, ConflictError, ForbiddenActionError
from apps.notifications.models import NotificationType
from apps.notifications.services import notify_role, notify_staff_claim

from .models import Investigation, InvestigationNote, InvestigationStatus, Recommendation


def open_investigation(claim, *, trigger, reason, assessment=None, actor=None):
    """Called inside the transaction that moves the claim to FRAUD_REVIEW."""
    inv = Investigation.objects.create(claim=claim, assessment=assessment, trigger=trigger, trigger_reason=reason,
                                       opened_by=actor)
    notify_role("SIU", NotificationType.FRAUD_ALERT, f"Claim {claim.claim_number} flagged for investigation",
                reason, claim=claim, link=f"/staff/claims/{claim.pk}", email=True)
    return inv


def _lock(inv):
    return Investigation.objects.select_for_update().select_related("claim").get(pk=inv.pk)


def _ensure_owner(inv, user):
    if inv.status == InvestigationStatus.COMPLETED:
        raise ConflictError("Completed investigations are permanent and cannot be changed.",
                            code="investigation_completed")
    if inv.investigator_id and inv.investigator_id != user.pk and inv.investigator.is_active:
        raise ForbiddenActionError(f"This investigation is assigned to {inv.investigator.full_name}.",
                                   code="not_assigned_investigator")


@transaction.atomic
def start_investigation(user, inv, request=None):
    inv = _lock(inv)
    _ensure_owner(inv, user)
    if inv.status == InvestigationStatus.OPEN or inv.investigator_id != user.pk:
        inv.investigator = user
        inv.status = InvestigationStatus.IN_PROGRESS
        inv.started_at = inv.started_at or timezone.now()
        inv.save()
        log_event(AuditAction.INVESTIGATION_ASSIGNED, inv, actor=user, request=request,
                  metadata={"claim": inv.claim.claim_number})
    return inv


@transaction.atomic
def save_progress(user, inv, *, findings=None, evidence_notes=None, note="", request=None):
    inv = _lock(inv)
    _ensure_owner(inv, user)
    if inv.status == InvestigationStatus.OPEN:
        inv.status, inv.investigator, inv.started_at = InvestigationStatus.IN_PROGRESS, user, timezone.now()
    if findings is not None:
        inv.findings = findings
    if evidence_notes is not None:
        inv.evidence_notes = evidence_notes
    inv.save()
    if note.strip():
        InvestigationNote.objects.create(investigation=inv, author=user, note=note.strip())
    log_event(AuditAction.INVESTIGATION_UPDATED, inv, actor=user, request=request,
              metadata={"claim": inv.claim.claim_number, "note_added": bool(note.strip())})
    return inv


@transaction.atomic
def complete_investigation(user, inv, *, findings, recommendation, evidence_notes="", request=None):
    """Records findings permanently and hands the claim back to the adjuster for the final decision."""
    inv = _lock(inv)
    _ensure_owner(inv, user)
    if not findings or not findings.strip():
        raise BusinessRuleError("Findings are required to complete an investigation.", code="findings_required",
                                fields={"findings": ["Required."]})
    if recommendation not in Recommendation.values:
        raise BusinessRuleError("Choose a recommendation.", code="recommendation_required",
                                fields={"recommendation": ["Required."]})
    claim = Claim.objects.select_for_update().get(pk=inv.claim_id)
    if claim.status != ClaimStatus.FRAUD_REVIEW:
        raise ConflictError("The claim is no longer in Fraud Review.", code="claim_not_in_fraud_review")
    now = timezone.now()
    inv.findings, inv.evidence_notes, inv.recommendation = findings.strip(), evidence_notes or "", recommendation
    inv.status, inv.investigator, inv.completed_at = InvestigationStatus.COMPLETED, user, now
    inv.started_at = inv.started_at or now
    inv.save()
    claim.siu_cleared_at = now
    transition(claim, ClaimStatus.UNDER_REVIEW, actor=user, internal=True, request=request,
               reason=f"SIU investigation completed — recommendation: {inv.get_recommendation_display()}")
    log_event(AuditAction.INVESTIGATION_COMPLETED, inv, actor=user, request=request,
              metadata={"claim": claim.claim_number, "recommendation": recommendation})
    notify_staff_claim(claim.assigned_adjuster, "ADJUSTER", NotificationType.INVESTIGATION,
                       f"SIU findings recorded for {claim.claim_number}",
                       f"Investigation completed ({inv.get_recommendation_display()}). The claim is back in your "
                       "queue for a final decision.", claim=claim, link=f"/staff/claims/{claim.pk}", email=True)
    return inv
