"""
Claim lifecycle business logic (SRS §4.5, REQ-CLM-001..018, REQ-BR-009..018).

Views stay thin: they validate input shape and call these functions. Every write runs inside
`transaction.atomic()` with row locks, so multi-table operations (claim + policy + history + audit +
notification) either all happen or none do (REQ-QUA-002).
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role
from apps.audit.models import AuditAction
from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError, ConflictError, ForbiddenActionError
from apps.core.numbering import assign_number, temporary_number
from apps.documents.models import MANDATORY_DOCUMENT_TYPES, DocumentType
from apps.documents.services import missing_verified_documents, store_document
from apps.documents.validators import validate_upload
from apps.fraud.models import AssessmentStatus, AssessmentTrigger
from apps.fraud.services import run_assessment
from apps.investigations.models import InvestigationStatus, InvestigationTrigger
from apps.investigations.services import open_investigation
from apps.notifications.models import NotificationType
from apps.notifications.services import notify, notify_staff_claim
from apps.policies.models import Policy
from apps.policies.services import apply_approved_claim_amount, expire_due_policies, is_claimable
from apps.vehicles.models import Vehicle

from .models import Appeal, AppealStatus, Claim, ClaimStatus, ClosureReason
from .workflow import transition

EDITABLE_FIELDS = ["claim_type", "incident_date", "incident_time", "incident_location", "description",
                   "requested_amount"]


def _customer_link(claim):
    return f"/claims/{claim.pk}"


def _staff_link(claim):
    return f"/staff/claims/{claim.pk}"


# ----------------------------------------------------------------------------- validation helpers
def _validate_incident(data):
    now = timezone.localtime()
    if data["incident_date"] > now.date():
        raise BusinessRuleError("The incident date cannot be in the future.", code="incident_in_future",
                                fields={"incident_date": ["Cannot be in the future."]})
    if data["incident_date"] == now.date() and data["incident_time"] > now.time():
        raise BusinessRuleError("The incident time cannot be in the future.", code="incident_in_future",
                                fields={"incident_time": ["Cannot be in the future."]})
    if Decimal(data["requested_amount"]) <= 0:
        raise BusinessRuleError("Claim amount must be greater than zero.", code="invalid_amount",
                                fields={"requested_amount": ["Must be greater than zero."]})


def _check_policy(policy, data):
    ok, msg = is_claimable(policy, data["incident_date"])           # REQ-CLM-004 / REQ-POL-013
    if not ok:
        raise ConflictError(msg, code="policy_not_claimable")
    if Decimal(data["requested_amount"]) > policy.remaining_idv:
        raise BusinessRuleError(f"The claim amount exceeds the policy's remaining insured value "
                                f"(₹{policy.remaining_idv:,.2f}).", code="exceeds_remaining_idv",
                                fields={"requested_amount": ["Exceeds remaining IDV."]})


def find_duplicate(policy, incident_date, claim_type, exclude_pk=None):
    """REQ-CLM-016/017: same policy + vehicle + incident date + claim type = same incident."""
    qs = (Claim.objects.filter(policy__vehicle=policy.vehicle, incident_date=incident_date, claim_type=claim_type)
          .exclude(closure_reason=ClosureReason.WITHDRAWN))
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.first()


def _raise_duplicate(dup):
    raise ConflictError(f"A claim for this incident already exists ({dup.claim_number}). "
                        "Duplicate claims for the same incident are not allowed.", code="duplicate_claim",
                        extra={"existing_claim": dup.claim_number})


def _ensure_adjuster(claim, user):
    """Only the assigned adjuster may act; the first adjuster to act on an unassigned claim takes it."""
    if user.role != Role.ADJUSTER:
        raise ForbiddenActionError("Only Claim Adjusters can perform this action.", code="adjuster_only")
    if claim.assigned_adjuster_id and claim.assigned_adjuster_id != user.pk and claim.assigned_adjuster.is_active:
        raise ForbiddenActionError(f"This claim is assigned to {claim.assigned_adjuster.full_name}.",
                                   code="not_assigned_adjuster")
    if claim.assigned_adjuster_id != user.pk:
        claim.assigned_adjuster = user


def _lock(claim):
    return (Claim.objects.select_for_update()
            .select_related("policy__customer__user", "policy__vehicle", "assigned_adjuster").get(pk=claim.pk))


# ----------------------------------------------------------------------------- submission
def submit_claim(user, *, vehicle_id, policy_id, data, documents, request=None):
    """
    Claim submission (SRS §4.5.2):
    1 customer → 2 vehicle → 3 policy → 4 eligibility → 5 duplicates → 6 claim number → 7 status Submitted
    → 8 notifications → 9 fraud assessment.  `documents` = list of (document_type, UploadedFile).
    """
    customer = user.customer_profile                                                  # 1
    _validate_incident(data)
    provided = {t for t, _ in documents}
    missing = [DocumentType(t).label for t in MANDATORY_DOCUMENT_TYPES if t not in provided]
    if missing:                                                                       # REQ-DOC-006
        raise BusinessRuleError("Required documents missing: " + ", ".join(missing) + ".",
                                code="missing_documents", fields={"documents": missing})
    metas = [(t, f, validate_upload(f)) for t, f in documents]                         # validate files before locking

    expire_due_policies()
    with transaction.atomic():
        vehicle = Vehicle.objects.filter(pk=vehicle_id, customer=customer).first()   # 2
        if vehicle is None:
            raise BusinessRuleError("Vehicle not found.", code="vehicle_not_found", status_code=404)
        policy = Policy.objects.select_for_update().filter(pk=policy_id, customer=customer).first()   # 3
        if policy is None or policy.vehicle_id != vehicle.pk:
            raise BusinessRuleError("The selected policy does not belong to this vehicle.", code="policy_mismatch",
                                    fields={"policy_id": ["Policy does not cover this vehicle."]})
        _check_policy(policy, data)                                                   # 4
        dup = find_duplicate(policy, data["incident_date"], data["claim_type"])       # 5
        if dup:
            _raise_duplicate(dup)
        claim = Claim.objects.create(claim_number=temporary_number(), policy=policy,  # 6, 7
                                     status=ClaimStatus.SUBMITTED, **data)
        assign_number(claim, "CLM", "claim_number")
        claim.history.create(from_status="", to_status=ClaimStatus.SUBMITTED, actor=user, reason="Claim submitted")
        for doc_type, f, meta in metas:
            store_document(claim, f, doc_type, user, request=request, meta=meta)
        log_event(AuditAction.CLAIM_SUBMITTED, claim, actor=user, request=request,
                  metadata={"claim_number": claim.claim_number, "policy": policy.policy_number,
                            "amount": str(claim.requested_amount), "type": claim.claim_type})
        notify(user, NotificationType.CLAIM_SUBMITTED, f"Claim {claim.claim_number} submitted",   # 8
               f"We received your {claim.get_claim_type_display().lower()} claim for "
               f"₹{claim.requested_amount:,.2f} on {vehicle.registration_number}. You can edit it for the next "
               f"{settings.CLAIM_EDIT_WINDOW_MINUTES} minutes, until an adjuster starts the review.",
               claim=claim, link=_customer_link(claim), email=True)
        notify_staff_claim(None, Role.ADJUSTER, NotificationType.ASSIGNMENT, f"New claim {claim.claim_number}",
                           f"{claim.get_claim_type_display()} claim for ₹{claim.requested_amount:,.2f} awaits review.",
                           claim=claim, link=_staff_link(claim))
    run_assessment(claim, trigger=AssessmentTrigger.SUBMISSION, request=request)           # 9 (outside the txn)
    claim.refresh_from_db()
    return claim


def edit_claim(user, claim, data, request=None):
    """REQ-CLM-006 / REQ-BR-010 — enforced here, not in the browser."""
    with transaction.atomic():
        claim = _lock(claim)
        if claim.status != ClaimStatus.SUBMITTED or claim.review_started_at is not None:
            raise ConflictError("This claim can no longer be edited because review has started.",
                                code="claim_locked_review_started")
        if timezone.now() > claim.edit_deadline:
            raise ConflictError(f"The {settings.CLAIM_EDIT_WINDOW_MINUTES}-minute editing window for this claim has "
                                "closed.", code="edit_window_closed")
        merged = {f: data.get(f, getattr(claim, f)) for f in EDITABLE_FIELDS}
        _validate_incident(merged)
        policy = Policy.objects.select_for_update().get(pk=claim.policy_id)
        _check_policy(policy, merged)
        dup = find_duplicate(policy, merged["incident_date"], merged["claim_type"], exclude_pk=claim.pk)
        if dup:
            _raise_duplicate(dup)
        changed = {f: [str(getattr(claim, f)), str(v)] for f, v in merged.items() if getattr(claim, f) != v}
        if not changed:
            return claim
        for f, v in merged.items():
            setattr(claim, f, v)
        claim.save()
        log_event(AuditAction.CLAIM_EDITED, claim, actor=user, request=request, metadata={"changes": changed})
    run_assessment(claim, trigger=AssessmentTrigger.EDIT, request=request)
    claim.refresh_from_db()
    return claim


@transaction.atomic
def withdraw_claim(user, claim, request=None):
    claim = _lock(claim)
    if claim.status != ClaimStatus.SUBMITTED or claim.review_started_at is not None:
        raise ConflictError("Claims can only be withdrawn before review starts.", code="cannot_withdraw")
    claim.closure_reason, claim.closed_at = ClosureReason.WITHDRAWN, timezone.now()
    transition(claim, ClaimStatus.CLOSED, actor=user, reason="Withdrawn by customer", request=request)
    log_event(AuditAction.CLAIM_WITHDRAWN, claim, actor=user, request=request)
    return claim


# ----------------------------------------------------------------------------- adjuster review
@transaction.atomic
def start_review(user, claim, request=None):
    claim = _lock(claim)
    _ensure_adjuster(claim, user)
    if claim.status == ClaimStatus.DOCUMENTS_PENDING:
        transition(claim, ClaimStatus.UNDER_REVIEW, actor=user, reason="Review resumed", request=request)
        return claim
    if claim.status != ClaimStatus.SUBMITTED:
        raise ConflictError("Only newly submitted claims can be picked up for review.", code="invalid_status_transition")
    claim.review_started_at = timezone.now()                 # ends the customer's edit window immediately
    transition(claim, ClaimStatus.UNDER_REVIEW, actor=user, reason="Review started", request=request)
    log_event(AuditAction.CLAIM_REVIEW_STARTED, claim, actor=user, request=request)
    notify(claim.policy.customer.user, NotificationType.CLAIM_UPDATE, f"Claim {claim.claim_number} is under review",
           "A claim adjuster has started reviewing your claim. Editing is now closed.", claim=claim,
           link=_customer_link(claim), email=False)
    return claim


@transaction.atomic
def request_documents(user, claim, note, request=None):
    """REQ-CLM-007 — Documents Pending when required information is missing."""
    claim = _lock(claim)
    _ensure_adjuster(claim, user)
    if not note or not note.strip():
        raise BusinessRuleError("Describe which documents or information are needed.", code="reason_required",
                                fields={"note": ["Required."]})
    transition(claim, ClaimStatus.DOCUMENTS_PENDING, actor=user, reason=note.strip(), request=request)
    notify(claim.policy.customer.user, NotificationType.DOCUMENTS_REQUESTED,
           f"More documents needed for claim {claim.claim_number}", note.strip(), claim=claim,
           link=_customer_link(claim), email=True)
    return claim


@transaction.atomic
def escalate_to_siu(user, claim, reason, request=None):
    """§2.2 — adjuster escalates (typically medium-risk) claims to the SIU."""
    claim = _lock(claim)
    _ensure_adjuster(claim, user)
    if not reason or not reason.strip():
        raise BusinessRuleError("An escalation reason is required.", code="reason_required",
                                fields={"reason": ["Required."]})
    claim.siu_cleared_at = None
    claim.is_flagged = True
    transition(claim, ClaimStatus.FRAUD_REVIEW, actor=user, internal=True, reason=reason.strip(), request=request)
    open_investigation(claim, trigger=InvestigationTrigger.ESCALATION, reason=reason.strip(), actor=user,
                       assessment=claim.fraud_assessments.filter(status=AssessmentStatus.COMPLETED).first())
    return claim


def rerun_fraud_assessment(user, claim, request=None):
    if claim.status not in (ClaimStatus.SUBMITTED, ClaimStatus.UNDER_REVIEW, ClaimStatus.DOCUMENTS_PENDING,
                            ClaimStatus.FRAUD_REVIEW):
        raise ConflictError("Fraud assessment can only be re-run while the claim is being processed.",
                            code="claim_not_under_processing")
    return run_assessment(claim, trigger=AssessmentTrigger.MANUAL, actor=user, request=request)


@transaction.atomic
def approve_claim(user, claim, approved_amount, notes="", request=None):
    """
    SRS §4.5.2 'Claim Approval': store approved amount (requested kept separate), update policy cumulative
    amount + status, update claim status, audit, notify — one transaction (REQ-CLM-008/009/010).
    """
    claim = _lock(claim)
    _ensure_adjuster(claim, user)
    if claim.status != ClaimStatus.UNDER_REVIEW:
        raise ConflictError("Only claims under review can be approved.", code="invalid_status_transition")
    approved_amount = Decimal(approved_amount)
    if approved_amount <= 0:
        raise BusinessRuleError("Approved amount must be greater than zero.", code="invalid_amount",
                                fields={"approved_amount": ["Must be greater than zero."]})
    if approved_amount > claim.requested_amount:
        raise BusinessRuleError("Approved amount cannot exceed the amount the customer requested.",
                                code="exceeds_requested", fields={"approved_amount": ["Exceeds requested amount."]})
    if not claim.fraud_assessments.filter(status=AssessmentStatus.COMPLETED).exists():
        raise ConflictError("A completed fraud assessment is required before a decision. Re-run the assessment.",
                            code="fraud_assessment_missing")
    if claim.investigations.exclude(status=InvestigationStatus.COMPLETED).exists():
        raise ConflictError("An SIU investigation on this claim is still open.", code="investigation_open")
    missing = missing_verified_documents(claim)
    if missing:
        raise ConflictError("These required documents are not verified yet: " + ", ".join(missing) + ".",
                            code="documents_not_verified", extra={"missing": missing})
    policy = apply_approved_claim_amount(claim.policy, approved_amount, actor=user, request=request)
    claim.approved_amount = approved_amount
    claim.assessment_notes = notes or ""
    claim.decided_by, claim.decided_at = user, timezone.now()
    transition(claim, ClaimStatus.APPROVED, actor=user, reason=notes or "Claim approved", request=request,
               metadata={"approved_amount": str(approved_amount)})
    log_event(AuditAction.CLAIM_APPROVED, claim, actor=user, request=request,
              metadata={"approved_amount": str(approved_amount), "requested_amount": str(claim.requested_amount),
                        "policy_cumulative": str(policy.cumulative_approved_amount), "policy_status": policy.status})
    notify(claim.policy.customer.user, NotificationType.CLAIM_APPROVED, f"Claim {claim.claim_number} approved",
           f"Your claim has been approved for ₹{approved_amount:,.2f} (requested ₹{claim.requested_amount:,.2f})."
           + (f" Assessment: {notes}" if notes else ""), claim=claim, link=_customer_link(claim), email=True)
    return claim


@transaction.atomic
def reject_claim(user, claim, reason, allow_further_appeal=None, request=None):
    """REQ-CLM-012/014/015. After an appeal, the adjuster decides whether another appeal is permitted."""
    claim = _lock(claim)
    _ensure_adjuster(claim, user)
    if claim.status not in (ClaimStatus.UNDER_REVIEW, ClaimStatus.DOCUMENTS_PENDING):
        raise ConflictError("Only claims under review can be rejected.", code="invalid_status_transition")
    if not reason or not reason.strip():
        raise BusinessRuleError("A rejection reason is required.", code="reason_required",
                                fields={"reason": ["Required."]})
    if claim.investigations.exclude(status=InvestigationStatus.COMPLETED).exists():
        raise ConflictError("An SIU investigation on this claim is still open.", code="investigation_open")
    if claim.appeal_count >= 1:
        if allow_further_appeal is None:
            raise BusinessRuleError("This claim has already been appealed. Decide whether a further appeal is allowed.",
                                    code="appeal_decision_required",
                                    fields={"allow_further_appeal": ["Required for a previously appealed claim."]})
        claim.further_appeal_allowed = bool(allow_further_appeal)
    else:
        claim.further_appeal_allowed = True     # the first rejection is always appealable (REQ-BR-015)
    claim.rejection_reason = reason.strip()
    claim.decided_by, claim.decided_at = user, timezone.now()
    final = not claim.further_appeal_allowed
    transition(claim, ClaimStatus.PERMANENTLY_REJECTED if final else ClaimStatus.REJECTED, actor=user,
               reason=reason.strip(), request=request)
    log_event(AuditAction.CLAIM_REJECTED, claim, actor=user, request=request,
              metadata={"reason": reason.strip(), "permanent": final})
    tail = (" No further appeal is permitted; this decision is final." if final else
            f" You may appeal this decision within {settings.APPEAL_WINDOW_DAYS} days with additional information.")
    notify(claim.policy.customer.user, NotificationType.CLAIM_REJECTED, f"Claim {claim.claim_number} rejected",
           f"Reason: {reason.strip()}.{tail}", claim=claim, link=_customer_link(claim), email=True)
    return claim


# ----------------------------------------------------------------------------- after rejection (customer)
def appeal_deadline(claim):
    return (claim.decided_at or claim.updated_at) + timedelta(days=settings.APPEAL_WINDOW_DAYS)


def can_appeal(claim):
    return (claim.status == ClaimStatus.REJECTED and claim.further_appeal_allowed
            and not claim.appeals.filter(status=AppealStatus.PENDING).exists()
            and timezone.now() <= appeal_deadline(claim))


def submit_appeal(user, claim, reason, documents, request=None):
    """REQ-CLM-013 — additional information and evidence."""
    if not reason or len(reason.strip()) < 20:
        raise BusinessRuleError("Explain the grounds for your appeal (at least 20 characters).", code="reason_required",
                                fields={"reason": ["At least 20 characters."]})
    metas = [(t, f, validate_upload(f)) for t, f in documents]
    with transaction.atomic():
        claim = _lock(claim)
        if claim.status != ClaimStatus.REJECTED:
            raise ConflictError("Only rejected claims can be appealed.", code="not_appealable")
        if not claim.further_appeal_allowed:
            raise ConflictError("No further appeal is permitted for this claim.", code="appeal_not_allowed")
        if claim.appeals.filter(status=AppealStatus.PENDING).exists():
            raise ConflictError("An appeal for this claim is already pending.", code="appeal_pending")
        if timezone.now() > appeal_deadline(claim):
            raise ConflictError("The appeal window for this claim has closed.", code="appeal_window_closed")
        claim.appeal_count += 1
        claim.save(update_fields=["appeal_count", "updated_at"])
        appeal = Appeal.objects.create(claim=claim, sequence=claim.appeal_count, reason=reason.strip(),
                                       submitted_by=user)
        for doc_type, f, meta in metas:
            store_document(claim, f, doc_type, user, appeal=appeal, request=request, meta=meta)
        claim.history.create(from_status=claim.status, to_status=claim.status, actor=user,
                             reason=f"Appeal #{appeal.sequence} submitted")
        log_event(AuditAction.APPEAL_SUBMITTED, appeal, actor=user, request=request,
                  metadata={"claim": claim.claim_number, "documents": len(metas)})
        notify(user, NotificationType.APPEAL, f"Appeal submitted for {claim.claim_number}",
               "Your appeal has been received and will be reviewed by a claim adjuster.", claim=claim,
               link=_customer_link(claim), email=True)
        notify_staff_claim(claim.assigned_adjuster, Role.ADJUSTER, NotificationType.APPEAL,
                           f"Appeal on {claim.claim_number}", reason.strip()[:300], claim=claim,
                           link=_staff_link(claim), email=True)
    return appeal


@transaction.atomic
def accept_rejection(user, claim, request=None):
    """Activity diagram: 'Customer appeals? No → Close Claim'."""
    claim = _lock(claim)
    if claim.status != ClaimStatus.REJECTED or claim.appeals.filter(status=AppealStatus.PENDING).exists():
        raise ConflictError("Only rejected claims without a pending appeal can be closed.", code="cannot_close")
    claim.closure_reason, claim.closed_at = ClosureReason.DECISION_ACCEPTED, timezone.now()
    transition(claim, ClaimStatus.CLOSED, actor=user, reason="Customer accepted the decision", request=request)
    log_event(AuditAction.CLAIM_CLOSED, claim, actor=user, request=request)
    return claim


# ----------------------------------------------------------------------------- appeal decision (adjuster)
def decide_appeal(user, appeal, *, accept, note, allow_further_appeal=None, request=None):
    """
    Accept → claim reopened (UNDER_REVIEW) and fraud re-assessed; it is then approved or rejected again.
    Decline → claim stays Rejected; the adjuster states whether a further appeal is permitted (REQ-BR-016);
    if not, the claim becomes Permanently Rejected (REQ-CLM-015).
    """
    if not note or not note.strip():
        raise BusinessRuleError("A decision note is required.", code="reason_required", fields={"note": ["Required."]})
    with transaction.atomic():
        appeal = Appeal.objects.select_for_update().get(pk=appeal.pk)
        claim = _lock(appeal.claim)
        _ensure_adjuster(claim, user)
        if appeal.status != AppealStatus.PENDING:
            raise ConflictError("This appeal has already been decided.", code="appeal_already_decided")
        if claim.status != ClaimStatus.REJECTED:
            raise ConflictError("The claim is not in a rejected state.", code="invalid_status_transition")
        appeal.decided_by, appeal.decided_at, appeal.decision_note = user, timezone.now(), note.strip()
        customer = claim.policy.customer.user
        if accept:
            appeal.status = AppealStatus.ACCEPTED
            appeal.save()
            claim.siu_cleared_at = None             # new review episode — high risk will be flagged again
            claim.decided_by = claim.decided_at = None
            transition(claim, ClaimStatus.UNDER_REVIEW, actor=user,
                       reason=f"Appeal #{appeal.sequence} accepted — claim reopened: {note.strip()}", request=request)
            log_event(AuditAction.APPEAL_ACCEPTED, appeal, actor=user, request=request,
                      metadata={"claim": claim.claim_number})
            notify(customer, NotificationType.APPEAL, f"Appeal accepted — claim {claim.claim_number} reopened",
                   f"Your claim has been reopened for reassessment. {note.strip()}", claim=claim,
                   link=_customer_link(claim), email=True)
        else:
            if allow_further_appeal is None:
                raise BusinessRuleError("Decide whether a further appeal is allowed.", code="appeal_decision_required",
                                        fields={"allow_further_appeal": ["Required."]})
            appeal.status = AppealStatus.DECLINED
            appeal.further_appeal_allowed = bool(allow_further_appeal)
            appeal.save()
            claim.further_appeal_allowed = bool(allow_further_appeal)
            if not allow_further_appeal:
                transition(claim, ClaimStatus.PERMANENTLY_REJECTED, actor=user,
                           reason=f"Appeal #{appeal.sequence} declined; no further appeal permitted: {note.strip()}",
                           request=request)
            else:
                claim.save()
                claim.history.create(from_status=claim.status, to_status=claim.status, actor=user,
                                     reason=f"Appeal #{appeal.sequence} declined: {note.strip()}")
            log_event(AuditAction.APPEAL_DECLINED, appeal, actor=user, request=request,
                      metadata={"claim": claim.claim_number, "further_appeal_allowed": bool(allow_further_appeal)})
            notify(customer, NotificationType.APPEAL, f"Appeal declined for claim {claim.claim_number}",
                   f"{note.strip()} " + ("You may submit one further appeal." if allow_further_appeal
                                         else "No further appeal is permitted; the claim is permanently rejected."),
                   claim=claim, link=_customer_link(claim), email=True)
    if accept:
        run_assessment(claim, trigger=AssessmentTrigger.APPEAL, actor=user, request=request)
    return appeal


# ----------------------------------------------------------------------------- maintenance
def close_unappealed_rejections():
    cutoff = timezone.now() - timedelta(days=settings.APPEAL_WINDOW_DAYS)
    count = 0
    for claim in Claim.objects.filter(status=ClaimStatus.REJECTED, decided_at__lt=cutoff):
        with transaction.atomic():
            c = _lock(claim)
            if c.status != ClaimStatus.REJECTED or c.appeals.filter(status=AppealStatus.PENDING).exists():
                continue
            c.closure_reason, c.closed_at = ClosureReason.APPEAL_WINDOW_ELAPSED, timezone.now()
            transition(c, ClaimStatus.CLOSED, reason="Appeal window elapsed")
            count += 1
    return count
