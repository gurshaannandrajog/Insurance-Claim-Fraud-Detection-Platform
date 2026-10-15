from django.conf import settings
from django.db import models


class NotificationType(models.TextChoices):
    ACCOUNT = "ACCOUNT", "Account"
    POLICY_REQUEST = "POLICY_REQUEST", "Policy request"
    POLICY = "POLICY", "Policy"
    CLAIM_SUBMITTED = "CLAIM_SUBMITTED", "Claim submitted"
    CLAIM_UPDATE = "CLAIM_UPDATE", "Claim update"
    CLAIM_APPROVED = "CLAIM_APPROVED", "Claim approved"
    CLAIM_REJECTED = "CLAIM_REJECTED", "Claim rejected"
    DOCUMENT_REJECTED = "DOCUMENT_REJECTED", "Document rejected"
    DOCUMENTS_REQUESTED = "DOCUMENTS_REQUESTED", "Documents requested"
    APPEAL = "APPEAL", "Appeal"
    FRAUD_ALERT = "FRAUD_ALERT", "Fraud alert"          # staff only
    INVESTIGATION = "INVESTIGATION", "Investigation"    # staff only
    ASSIGNMENT = "ASSIGNMENT", "Work queue"


class EmailStatus(models.TextChoices):
    NOT_REQUIRED = "NOT_REQUIRED", "Not required"
    PENDING = "PENDING", "Pending"
    SENT = "SENT", "Sent"
    FAILED = "FAILED", "Failed"


class Notification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(max_length=24, choices=NotificationType.choices)
    title = models.CharField(max_length=140)
    message = models.TextField()
    claim = models.ForeignKey("claims.Claim", null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="notifications")
    link = models.CharField(max_length=200, blank=True)    # frontend route for the related object
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    email_status = models.CharField(max_length=12, choices=EmailStatus.choices, default=EmailStatus.NOT_REQUIRED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["recipient", "is_read", "created_at"])]

    def __str__(self):
        return f"{self.recipient_id}: {self.title}"
