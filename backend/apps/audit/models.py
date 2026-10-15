from django.conf import settings
from django.db import models


class AuditAction(models.TextChoices):
    LOGIN = "LOGIN", "Login"
    LOGOUT = "LOGOUT", "Logout"
    LOGIN_FAILED = "LOGIN_FAILED", "Failed login"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED", "Account locked"
    ACCOUNT_UNLOCKED = "ACCOUNT_UNLOCKED", "Account unlocked"
    SESSION_EXPIRED = "SESSION_EXPIRED", "Session expired"
    USER_REGISTERED = "USER_REGISTERED", "User registered"
    EMAIL_VERIFIED = "EMAIL_VERIFIED", "Email verified"
    PASSWORD_RESET_REQUESTED = "PASSWORD_RESET_REQUESTED", "Password reset requested"
    PASSWORD_CHANGED = "PASSWORD_CHANGED", "Password changed"
    PROFILE_UPDATED = "PROFILE_UPDATED", "Profile updated"
    ACCOUNT_DELETED = "ACCOUNT_DELETED", "Account deleted"
    EMPLOYEE_CREATED = "EMPLOYEE_CREATED", "Employee created"
    USER_ACTIVATED = "USER_ACTIVATED", "User activated"
    USER_DEACTIVATED = "USER_DEACTIVATED", "User deactivated"
    VEHICLE_CREATED = "VEHICLE_CREATED", "Vehicle created"
    VEHICLE_UPDATED = "VEHICLE_UPDATED", "Vehicle updated"
    POLICY_PLAN_CHANGED = "POLICY_PLAN_CHANGED", "Policy plan changed"
    POLICY_REQUESTED = "POLICY_REQUESTED", "Policy requested"
    POLICY_REQUEST_REJECTED = "POLICY_REQUEST_REJECTED", "Policy request rejected"
    POLICY_REQUEST_WITHDRAWN = "POLICY_REQUEST_WITHDRAWN", "Policy request withdrawn"
    POLICY_CREATED = "POLICY_CREATED", "Policy created"
    POLICY_STATUS_CHANGED = "POLICY_STATUS_CHANGED", "Policy status changed"
    POLICY_CANCELLED = "POLICY_CANCELLED", "Policy cancelled"
    POLICY_EXPIRED = "POLICY_EXPIRED", "Policy expired"
    CLAIM_SUBMITTED = "CLAIM_SUBMITTED", "Claim submitted"
    CLAIM_EDITED = "CLAIM_EDITED", "Claim edited"
    CLAIM_STATUS_CHANGED = "CLAIM_STATUS_CHANGED", "Claim status changed"
    CLAIM_REVIEW_STARTED = "CLAIM_REVIEW_STARTED", "Claim review started"
    CLAIM_APPROVED = "CLAIM_APPROVED", "Claim approved"
    CLAIM_REJECTED = "CLAIM_REJECTED", "Claim rejected"
    CLAIM_WITHDRAWN = "CLAIM_WITHDRAWN", "Claim withdrawn"
    CLAIM_CLOSED = "CLAIM_CLOSED", "Claim closed"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED", "Document uploaded"
    DOCUMENT_VERIFIED = "DOCUMENT_VERIFIED", "Document verified"
    DOCUMENT_REJECTED = "DOCUMENT_REJECTED", "Document rejected"
    DOCUMENT_REPLACED = "DOCUMENT_REPLACED", "Document replaced"
    DOCUMENT_DOWNLOADED = "DOCUMENT_DOWNLOADED", "Document downloaded"
    FRAUD_ASSESSED = "FRAUD_ASSESSED", "Fraud assessment completed"
    FRAUD_ASSESSMENT_FAILED = "FRAUD_ASSESSMENT_FAILED", "Fraud assessment failed"
    CLAIM_FLAGGED = "CLAIM_FLAGGED", "Claim flagged for fraud review"
    INVESTIGATION_ASSIGNED = "INVESTIGATION_ASSIGNED", "Investigation assigned"
    INVESTIGATION_UPDATED = "INVESTIGATION_UPDATED", "Investigation updated"
    INVESTIGATION_COMPLETED = "INVESTIGATION_COMPLETED", "Investigation completed"
    APPEAL_SUBMITTED = "APPEAL_SUBMITTED", "Appeal submitted"
    APPEAL_ACCEPTED = "APPEAL_ACCEPTED", "Appeal accepted"
    APPEAL_DECLINED = "APPEAL_DECLINED", "Appeal declined"
    REPORT_EXPORTED = "REPORT_EXPORTED", "Report exported"


class AuditLog(models.Model):
    """Append-only audit trail. No API endpoint can update or delete rows."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                              on_delete=models.SET_NULL, related_name="audit_events")
    actor_email = models.CharField(max_length=254, blank=True)   # snapshot, survives account anonymisation
    actor_role = models.CharField(max_length=20, blank=True)
    action = models.CharField(max_length=40, choices=AuditAction.choices, db_index=True)
    entity_type = models.CharField(max_length=40, db_index=True)
    entity_id = models.CharField(max_length=64, blank=True, db_index=True)
    description = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["entity_type", "entity_id", "created_at"])]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.entity_type}#{self.entity_id}"
