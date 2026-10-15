"""
Claim state machine (see docs/ANALYSIS.md §4).

`TRANSITIONS` is the single source of truth for which status changes are legal. Every change goes through
`transition()`, which validates it, records actor/time/reason in ClaimStatusHistory and writes an audit row.
No other code assigns `claim.status` directly.
"""
from apps.audit.models import AuditAction
from apps.audit.services import log_event
from apps.core.exceptions import InvalidTransitionError

from .models import Claim, ClaimStatus, ClaimStatusHistory

S = ClaimStatus

TRANSITIONS = {
    S.SUBMITTED: {S.UNDER_REVIEW, S.FRAUD_REVIEW, S.CLOSED},
    S.UNDER_REVIEW: {S.DOCUMENTS_PENDING, S.FRAUD_REVIEW, S.APPROVED, S.REJECTED, S.PERMANENTLY_REJECTED},
    S.DOCUMENTS_PENDING: {S.UNDER_REVIEW, S.FRAUD_REVIEW, S.REJECTED, S.PERMANENTLY_REJECTED},
    S.FRAUD_REVIEW: {S.UNDER_REVIEW},
    S.REJECTED: {S.UNDER_REVIEW, S.CLOSED, S.PERMANENTLY_REJECTED},
    S.APPROVED: set(),
    S.CLOSED: set(),
    S.PERMANENTLY_REJECTED: set(),
}

# What a customer is shown for each internal status (REQ-FRD-010: fraud review is not disclosed)
CUSTOMER_STATUS = {S.FRAUD_REVIEW: S.UNDER_REVIEW}


def can_transition(from_status, to_status):
    return to_status in TRANSITIONS.get(from_status, set())


def transition(claim: Claim, to_status, *, actor=None, reason="", internal=False, request=None, metadata=None):
    """Caller must hold a row lock on `claim` (select_for_update) inside a transaction."""
    from_status = claim.status
    if not can_transition(from_status, to_status):
        raise InvalidTransitionError(
            f"A claim cannot move from {S(from_status).label} to {S(to_status).label}.",
            extra={"from": from_status, "to": to_status})
    claim.status = to_status
    claim.save()
    ClaimStatusHistory.objects.create(claim=claim, from_status=from_status, to_status=to_status, actor=actor,
                                      reason=reason, is_internal=internal)
    log_event(AuditAction.CLAIM_STATUS_CHANGED, claim, actor=actor, request=request,
              description=f"{from_status} → {to_status}",
              metadata={"from": from_status, "to": to_status, "reason": reason, **(metadata or {})})
    return claim


def customer_visible_status(status):
    return CUSTOMER_STATUS.get(status, status)
