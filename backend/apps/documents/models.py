import uuid

from django.conf import settings
from django.db import models


class DocumentType(models.TextChoices):
    KYC = "KYC", "KYC details"
    ADDRESS_PROOF = "ADDRESS_PROOF", "Address proof"
    VEHICLE_REGISTRATION = "VEHICLE_REGISTRATION", "Vehicle registration (RC)"
    POLICY_HISTORY = "POLICY_HISTORY", "Policy history"
    ACCIDENT_PHOTO = "ACCIDENT_PHOTO", "Accident photograph"
    FIRE_EVIDENCE = "FIRE_EVIDENCE", "Fire photograph / evidence"
    DAMAGE_PHOTO = "DAMAGE_PHOTO", "Vehicle damage photograph"
    REPAIR_ESTIMATE = "REPAIR_ESTIMATE", "Repair estimate"
    THIRD_PARTY_DOCUMENT = "THIRD_PARTY_DOCUMENT", "Third-party document"
    OTHER = "OTHER", "Other supporting document"


# REQ-DOC-006 / REQ-BR-011
MANDATORY_DOCUMENT_TYPES = [DocumentType.KYC, DocumentType.ADDRESS_PROOF, DocumentType.VEHICLE_REGISTRATION]
CLAIM_SPECIFIC_EVIDENCE = {
    "ACCIDENT": {"label": "Accident or vehicle damage photographs",
                 "types": [DocumentType.ACCIDENT_PHOTO, DocumentType.DAMAGE_PHOTO]},
    "FIRE": {"label": "Fire photographs / evidence", "types": [DocumentType.FIRE_EVIDENCE]},
    "THIRD_PARTY": {"label": "Third-party documents", "types": [DocumentType.THIRD_PARTY_DOCUMENT]},
}


class DocumentStatus(models.TextChoices):
    PENDING = "PENDING", "Pending Verification"
    VERIFIED = "VERIFIED", "Verified"
    REJECTED = "REJECTED", "Rejected"


def document_upload_path(instance, filename):
    # Random, unguessable storage name; the original name is kept only in the database.
    ext = filename.rsplit(".", 1)[-1].lower()
    return f"claim_documents/{instance.claim_id}/{uuid.uuid4().hex}.{ext}"


class ClaimDocument(models.Model):
    claim = models.ForeignKey("claims.Claim", on_delete=models.PROTECT, related_name="documents")
    appeal = models.ForeignKey("claims.Appeal", null=True, blank=True, on_delete=models.PROTECT,
                               related_name="documents")
    document_type = models.CharField(max_length=24, choices=DocumentType.choices)
    file = models.FileField(upload_to=document_upload_path, max_length=255)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=40)
    size_bytes = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=10, choices=DocumentStatus.choices, default=DocumentStatus.PENDING,
                              db_index=True)
    is_current = models.BooleanField(default=True)  # False once replaced; history is retained
    replaces = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT,
                                    related_name="replaced_by")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                    related_name="+")
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=500, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at", "id"]
        indexes = [models.Index(fields=["claim", "is_current", "document_type"])]
        constraints = [
            models.CheckConstraint(condition=models.Q(size_bytes__gt=0) & models.Q(size_bytes__lte=10 * 1024 * 1024),
                                   name="document_size_limit"),
            models.CheckConstraint(
                condition=~models.Q(status="REJECTED") | ~models.Q(rejection_reason=""),
                name="document_rejection_has_reason"),   # REQ-DOC-009 at DB level
        ]

    def __str__(self):
        return f"{self.get_document_type_display()} for claim {self.claim_id}"


class DocumentReview(models.Model):
    """Verification history — every verify / reject / replace decision (who, when, why)."""

    class Action(models.TextChoices):
        VERIFIED = "VERIFIED", "Verified"
        REJECTED = "REJECTED", "Rejected"
        REPLACED = "REPLACED", "Replaced"

    document = models.ForeignKey(ClaimDocument, on_delete=models.PROTECT, related_name="reviews")
    action = models.CharField(max_length=10, choices=Action.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
