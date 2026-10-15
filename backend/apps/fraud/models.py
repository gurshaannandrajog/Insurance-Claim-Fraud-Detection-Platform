from django.conf import settings
from django.db import models

from apps.claims.models import RiskLevel


class AssessmentStatus(models.TextChoices):
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed (service unavailable)"


class AssessmentTrigger(models.TextChoices):
    SUBMISSION = "SUBMISSION", "Claim submitted"
    EDIT = "EDIT", "Claim edited by customer"
    APPEAL = "APPEAL", "Claim reopened on appeal"
    MANUAL = "MANUAL", "Re-run by staff"


class FraudAssessment(models.Model):
    """Every assessment run is retained (REQ-FRD-012) — including failures — with the exact input sent."""

    claim = models.ForeignKey("claims.Claim", on_delete=models.PROTECT, related_name="fraud_assessments")
    status = models.CharField(max_length=10, choices=AssessmentStatus.choices)
    trigger = models.CharField(max_length=10, choices=AssessmentTrigger.choices)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                     related_name="+")
    risk_score = models.PositiveSmallIntegerField(null=True, blank=True)
    risk_level = models.CharField(max_length=6, choices=RiskLevel.choices, blank=True)
    flagged = models.BooleanField(default=False)
    engine = models.CharField(max_length=40, blank=True)          # e.g. "rules-v1" — swap for "ml-v1" later
    request_payload = models.JSONField(default=dict)
    error_message = models.CharField(max_length=255, blank=True)
    response_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(risk_score__isnull=True) | models.Q(risk_score__lte=100),
                                   name="assessment_score_range"),
        ]


class FraudIndicator(models.Model):
    """One contributing factor (REQ-FRD-004)."""

    assessment = models.ForeignKey(FraudAssessment, on_delete=models.CASCADE, related_name="indicators")
    code = models.CharField(max_length=40)
    category = models.CharField(max_length=30)
    description = models.CharField(max_length=255)
    weight = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["-weight", "id"]
