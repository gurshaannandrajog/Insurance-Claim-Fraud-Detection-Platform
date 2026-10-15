"""Read-side helpers: object-level access (IDOR protection) and which actions a user may take on a claim."""
from django.db.models import Q

from apps.accounts.models import Role
from apps.fraud.models import AssessmentStatus
from apps.investigations.models import InvestigationStatus

from .models import AppealStatus, Claim, ClaimStatus


def claims_visible_to(user):
    """
    Customers: only claims on their own policies (REQ-CUST-008, REQ-SEC-008).
    SIU: only claims that have been sent to fraud review (REQ-SEC-010).
    Adjusters and Administrators: all claims (administrators read-only, REQ-SEC-011).
    Anything outside this queryset returns 404 — the existence of other customers' claims is not revealed.
    """
    qs = Claim.objects.select_related("policy__vehicle", "policy__customer__user", "assigned_adjuster", "decided_by")
    if user.role == Role.CUSTOMER:
        return qs.filter(policy__customer__user=user)
    if user.role == Role.SIU:
        return qs.filter(Q(investigations__isnull=False)).distinct()
    if user.role in (Role.ADJUSTER, Role.ADMIN):
        return qs
    return qs.none()


def available_actions(claim: Claim, user):
    from .services import can_appeal

    acts = []
    s = claim.status
    if user.role == Role.CUSTOMER:
        if claim.is_editable:
            acts += ["edit", "withdraw"]
        if s in (ClaimStatus.SUBMITTED, ClaimStatus.UNDER_REVIEW, ClaimStatus.DOCUMENTS_PENDING,
                 ClaimStatus.FRAUD_REVIEW):
            acts.append("upload_document")
        if can_appeal(claim):
            acts.append("appeal")
        if s == ClaimStatus.REJECTED and not claim.appeals.filter(status=AppealStatus.PENDING).exists():
            acts.append("accept_decision")
        return acts

    if user.role == Role.ADJUSTER:
        mine = claim.assigned_adjuster_id in (None, user.pk) or not claim.assigned_adjuster.is_active
        if not mine:
            return []
        if s == ClaimStatus.SUBMITTED:
            acts.append("start_review")
        if s == ClaimStatus.DOCUMENTS_PENDING:
            acts += ["resume_review", "reject", "upload_document", "review_documents"]
        if s == ClaimStatus.UNDER_REVIEW:
            acts += ["request_documents", "escalate", "reject", "upload_document", "review_documents"]
            if claim.fraud_assessments.filter(status=AssessmentStatus.COMPLETED).exists() and \
                    not claim.investigations.exclude(status=InvestigationStatus.COMPLETED).exists():
                acts.append("approve")
        if s in ClaimStatus.in_processing():
            acts.append("rerun_fraud")
        if s == ClaimStatus.REJECTED and claim.appeals.filter(status=AppealStatus.PENDING).exists():
            acts.append("decide_appeal")
        return acts

    if user.role == Role.SIU:
        inv = claim.investigations.exclude(status=InvestigationStatus.COMPLETED).first()
        if inv and (inv.investigator_id in (None, user.pk) or not inv.investigator.is_active):
            acts.append("investigate")
        return acts
    return []
