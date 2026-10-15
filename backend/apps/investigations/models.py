from django.conf import settings
from django.db import models


class InvestigationStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    COMPLETED = "COMPLETED", "Completed"


class InvestigationTrigger(models.TextChoices):
    HIGH_RISK = "HIGH_RISK", "Automatic — high fraud risk"
    ESCALATION = "ESCALATION", "Escalated by claim adjuster"


class Recommendation(models.TextChoices):
    LEGITIMATE = "LEGITIMATE", "No fraud indicators confirmed"
    SUSPICIOUS = "SUSPICIOUS", "Suspicious — proceed with caution"
    FRAUDULENT = "FRAUDULENT", "Fraud confirmed — recommend rejection"
    INCONCLUSIVE = "INCONCLUSIVE", "Inconclusive"


class Investigation(models.Model):
    """SIU case file (REQ-FRD-011). Records are permanent — completed investigations are immutable."""

    claim = models.ForeignKey("claims.Claim", on_delete=models.PROTECT, related_name="investigations")
    assessment = models.ForeignKey("fraud.FraudAssessment", null=True, blank=True, on_delete=models.PROTECT,
                                   related_name="investigations")
    trigger = models.CharField(max_length=12, choices=InvestigationTrigger.choices)
    trigger_reason = models.TextField(blank=True)
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                  related_name="+")
    investigator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                     related_name="investigations")
    status = models.CharField(max_length=12, choices=InvestigationStatus.choices, default=InvestigationStatus.OPEN,
                              db_index=True)
    findings = models.TextField(blank=True)
    evidence_notes = models.TextField(blank=True)
    recommendation = models.CharField(max_length=12, choices=Recommendation.choices, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(status="COMPLETED") | (~models.Q(findings="") & ~models.Q(recommendation="")),
                name="completed_investigation_has_findings"),
        ]


class InvestigationNote(models.Model):
    investigation = models.ForeignKey(Investigation, on_delete=models.PROTECT, related_name="notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
