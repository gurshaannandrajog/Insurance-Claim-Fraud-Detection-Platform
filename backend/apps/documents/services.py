"""Document management (SRS §4.6)."""
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role
from apps.audit.models import AuditAction
from apps.audit.services import log_event
from apps.claims.models import Claim, ClaimStatus
from apps.core.exceptions import BusinessRuleError, ConflictError, ForbiddenActionError
from apps.notifications.models import NotificationType
from apps.notifications.services import notify, notify_staff_claim

from .models import (CLAIM_SPECIFIC_EVIDENCE, MANDATORY_DOCUMENT_TYPES, ClaimDocument, DocumentReview,
                     DocumentStatus, DocumentType)
from .validators import validate_upload

CUSTOMER_UPLOAD_STATUSES = {ClaimStatus.SUBMITTED, ClaimStatus.UNDER_REVIEW, ClaimStatus.DOCUMENTS_PENDING,
                            ClaimStatus.FRAUD_REVIEW}
ADJUSTER_PROCESSING_STATUSES = {ClaimStatus.UNDER_REVIEW, ClaimStatus.DOCUMENTS_PENDING}
CUSTOMER_TYPES = set(DocumentType.values) - {DocumentType.REPAIR_ESTIMATE}


def required_document_groups(claim_type):
    groups = [{"label": DocumentType(t).label, "types": [t]} for t in MANDATORY_DOCUMENT_TYPES]
    evidence = CLAIM_SPECIFIC_EVIDENCE.get(claim_type)
    if evidence:
        groups.append({"label": evidence["label"], "types": list(evidence["types"])})
    return groups


def document_checklist(claim):
    """For each required group: is there a current document, and is it verified?"""
    current = list(claim.documents.filter(is_current=True))
    result = []
    for group in required_document_groups(claim.claim_type):
        docs = [d for d in current if d.document_type in group["types"]]
        result.append({
            "label": group["label"], "types": group["types"],
            "provided": bool(docs),
            "verified": any(d.status == DocumentStatus.VERIFIED for d in docs),
            "rejected": bool(docs) and all(d.status == DocumentStatus.REJECTED for d in docs),
        })
    return result


def missing_verified_documents(claim):
    return [g["label"] for g in document_checklist(claim) if not g["verified"]]


def store_document(claim, uploaded, document_type, user, *, appeal=None, replaces=None, request=None, meta=None):
    """Caller provides the transaction. `meta` = output of validate_upload (validated before the transaction)."""
    meta = meta or validate_upload(uploaded)
    doc = ClaimDocument(claim=claim, appeal=appeal, document_type=document_type,
                        original_filename=meta["original_filename"], content_type=meta["content_type"],
                        size_bytes=meta["size"], sha256=meta["sha256"], uploaded_by=user, replaces=replaces)
    doc.file.save(f"upload.{meta['extension']}", uploaded, save=False)
    doc.save()
    if replaces is not None:
        ClaimDocument.objects.filter(pk=replaces.pk).update(is_current=False)
        DocumentReview.objects.create(document=replaces, action=DocumentReview.Action.REPLACED, actor=user,
                                      reason=f"Replaced by document #{doc.pk}")
        log_event(AuditAction.DOCUMENT_REPLACED, doc, actor=user, request=request,
                  metadata={"claim": claim.claim_number, "replaced_document": replaces.pk})
    log_event(AuditAction.DOCUMENT_UPLOADED, doc, actor=user, request=request,
              metadata={"claim": claim.claim_number, "type": document_type, "size": meta["size"]})
    return doc


def _ensure_adjuster_can_act(claim, user):
    if claim.assigned_adjuster_id and claim.assigned_adjuster_id != user.pk and claim.assigned_adjuster.is_active:
        raise ForbiddenActionError(f"This claim is assigned to {claim.assigned_adjuster.full_name}.",
                                   code="not_assigned_adjuster")


def upload_document(user, claim, uploaded, document_type, *, replaces_id=None, request=None):
    """REQ-DOC-001/004/011. Customers upload during processing; adjusters add documents and replace them."""
    if document_type not in DocumentType.values:
        raise BusinessRuleError("Unknown document type.", code="invalid_document_type",
                                fields={"document_type": ["Invalid choice."]})
    meta = validate_upload(uploaded)  # fail fast, before taking locks
    with transaction.atomic():
        claim = Claim.objects.select_for_update().select_related("assigned_adjuster", "policy__customer__user").get(
            pk=claim.pk)
        replaces = None
        if replaces_id:
            replaces = ClaimDocument.objects.select_for_update().filter(pk=replaces_id, claim=claim).first()
            if replaces is None or not replaces.is_current:
                raise BusinessRuleError("The document to replace was not found or was already replaced.",
                                        code="invalid_replacement")
        if user.role == Role.CUSTOMER:
            if claim.status not in CUSTOMER_UPLOAD_STATUSES:
                raise ConflictError("Documents can no longer be added to this claim. "
                                    "If it was rejected, submit additional evidence with an appeal.",
                                    code="claim_not_accepting_documents")
            if document_type not in CUSTOMER_TYPES:
                raise ForbiddenActionError("Repair estimates are uploaded by the claim adjuster.",
                                           code="document_type_not_allowed")
            if replaces is not None and replaces.status != DocumentStatus.REJECTED:
                raise ConflictError("Only rejected documents can be replaced.", code="replace_only_rejected")
        elif user.role == Role.ADJUSTER:
            if claim.status not in ADJUSTER_PROCESSING_STATUSES:
                raise ConflictError("Start the review before adding or replacing documents.",
                                    code="claim_not_under_processing")
            _ensure_adjuster_can_act(claim, user)
        else:
            raise ForbiddenActionError("Your role cannot upload claim documents.")
        if replaces is not None and replaces.document_type != document_type:
            raise BusinessRuleError("A replacement must be the same document type.", code="replacement_type_mismatch")
        doc = store_document(claim, uploaded, document_type, user, replaces=replaces, request=request, meta=meta)
        if user.role == Role.CUSTOMER and claim.status in (ClaimStatus.DOCUMENTS_PENDING, ClaimStatus.UNDER_REVIEW):
            notify_staff_claim(claim.assigned_adjuster, Role.ADJUSTER, NotificationType.CLAIM_UPDATE,
                               f"New document on {claim.claim_number}",
                               f"The customer uploaded {doc.get_document_type_display()}.", claim=claim,
                               link=f"/staff/claims/{claim.pk}")
    return doc


@transaction.atomic
def verify_document(user, doc, request=None):
    return _review(user, doc, DocumentStatus.VERIFIED, "", request)


@transaction.atomic
def reject_document(user, doc, reason, request=None):
    if not reason or not reason.strip():   # REQ-DOC-009
        raise BusinessRuleError("A reason is required when rejecting a document.", code="reason_required",
                                fields={"reason": ["Required."]})
    return _review(user, doc, DocumentStatus.REJECTED, reason.strip(), request)


def _review(user, doc, new_status, reason, request):
    doc = ClaimDocument.objects.select_for_update().get(pk=doc.pk)
    claim = Claim.objects.select_for_update().select_related("assigned_adjuster", "policy__customer__user").get(
        pk=doc.claim_id)
    if claim.status not in ADJUSTER_PROCESSING_STATUSES:
        raise ConflictError("Documents can only be verified while the claim is under review.",
                            code="claim_not_under_processing")
    _ensure_adjuster_can_act(claim, user)
    if not doc.is_current:
        raise ConflictError("This document has been replaced.", code="document_replaced")
    if doc.status != DocumentStatus.PENDING:
        raise ConflictError(f"This document is already {doc.get_status_display().lower()}.",
                            code="document_already_reviewed")
    doc.status, doc.verified_by, doc.verified_at = new_status, user, timezone.now()
    doc.rejection_reason = reason
    doc.save()
    DocumentReview.objects.create(document=doc, action=new_status, actor=user, reason=reason)
    if claim.assigned_adjuster_id is None:
        claim.assigned_adjuster = user
        claim.save(update_fields=["assigned_adjuster", "updated_at"])
    if new_status == DocumentStatus.VERIFIED:
        log_event(AuditAction.DOCUMENT_VERIFIED, doc, actor=user, request=request,
                  metadata={"claim": claim.claim_number})
    else:
        log_event(AuditAction.DOCUMENT_REJECTED, doc, actor=user, request=request,
                  metadata={"claim": claim.claim_number, "reason": reason})
        # REQ-DOC-010 — in-app + email
        notify(claim.policy.customer.user, NotificationType.DOCUMENT_REJECTED,
               f"Document rejected on claim {claim.claim_number}",
               f"Your {doc.get_document_type_display()} ({doc.original_filename}) was rejected. Reason: {reason}. "
               "Please upload a corrected document.", claim=claim, link=f"/claims/{claim.pk}", email=True)
    return doc


def can_access_document(user, doc):
    """REQ-DOC-012 / REQ-SEC-013 — checked on every download."""
    claim = doc.claim
    if user.role == Role.CUSTOMER:
        return claim.policy.customer.user_id == user.pk
    if user.role == Role.ADJUSTER:
        return True
    if user.role == Role.SIU:
        return claim.investigations.exists()
    return False  # administrators manage the platform but do not handle claim evidence
