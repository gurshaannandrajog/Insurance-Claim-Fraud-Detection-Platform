from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.core.models import TimeStampedModel


class ClaimType(models.TextChoices):
    ACCIDENT = "ACCIDENT", "Accident"
    FIRE = "FIRE", "Fire"
    THIRD_PARTY = "THIRD_PARTY", "Third-party damage"


class ClaimStatus(models.TextChoices):
    SUBMITTED = "SUBMITTED", "Submitted"
    UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
    DOCUMENTS_PENDING = "DOCUMENTS_PENDING", "Documents Pending"
    FRAUD_REVIEW = "FRAUD_REVIEW", "Fraud Review"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    CLOSED = "CLOSED", "Closed"
    PERMANENTLY_REJECTED = "PERMANENTLY_REJECTED", "Permanently Rejected"

    @classmethod
    def terminal(cls):
        return [cls.APPROVED, cls.CLOSED, cls.PERMANENTLY_REJECTED]

    @classmethod
    def in_processing(cls):
        return [cls.SUBMITTED, cls.UNDER_REVIEW, cls.DOCUMENTS_PENDING, cls.FRAUD_REVIEW]


class ClosureReason(models.TextChoices):
    WITHDRAWN = "WITHDRAWN", "Withdrawn by customer"
    DECISION_ACCEPTED = "DECISION_ACCEPTED", "Customer accepted the decision"
    APPEAL_WINDOW_ELAPSED = "APPEAL_WINDOW_ELAPSED", "Appeal window elapsed"


class RiskLevel(models.TextChoices):
    LOW = "LOW", "Low Risk"
    MEDIUM = "MEDIUM", "Medium Risk"
    HIGH = "HIGH", "High Risk"


class Claim(TimeStampedModel):
    """
    A claim references only its Policy; the customer and vehicle are reached through the policy
    (policy.customer, policy.vehicle), which is immutable — so the three can never disagree (REQ-CLM-002).
    """
    claim_number = models.CharField(max_length=24, unique=True)
    policy = models.ForeignKey("policies.Policy", on_delete=models.PROTECT, related_name="claims")
    claim_type = models.CharField(max_length=12, choices=ClaimType.choices, db_index=True)
    incident_date = models.DateField()
    incident_time = models.TimeField()
    incident_location = models.CharField(max_length=255)
    description = models.TextField()
    requested_amount = models.DecimalField(max_digits=12, decimal_places=2)         # customer's figure — never overwritten
    approved_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)  # REQ-CLM-008
    status = models.CharField(max_length=24, choices=ClaimStatus.choices, default=ClaimStatus.SUBMITTED, db_index=True)
    submitted_at = models.DateTimeField(default=timezone.now, db_index=True)
    review_started_at = models.DateTimeField(null=True, blank=True)
    assigned_adjuster = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                          related_name="assigned_claims")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                   related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    assessment_notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    appeal_count = models.PositiveSmallIntegerField(default=0)
    further_appeal_allowed = models.BooleanField(default=True)
    closure_reason = models.CharField(max_length=24, choices=ClosureReason.choices, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    # Latest fraud result, copied from FraudAssessment for indexed filtering in queues/reports (justified denormalisation)
    current_risk_score = models.PositiveSmallIntegerField(null=True, blank=True)
    current_risk_level = models.CharField(max_length=6, choices=RiskLevel.choices, blank=True, db_index=True)
    is_flagged = models.BooleanField(default=False, db_index=True)
    siu_cleared_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at", "-id"]
        indexes = [models.Index(fields=["policy", "incident_date", "claim_type"]),
                   models.Index(fields=["status", "submitted_at"])]
        constraints = [
            models.CheckConstraint(condition=Q(requested_amount__gt=0), name="claim_requested_positive"),
            models.CheckConstraint(condition=Q(approved_amount__isnull=True) |
                                   (Q(approved_amount__gt=0) & Q(approved_amount__lte=F("requested_amount"))),
                                   name="claim_approved_le_requested"),
            models.CheckConstraint(condition=~Q(status__in=["REJECTED", "PERMANENTLY_REJECTED"]) |
                                   ~Q(rejection_reason=""), name="claim_rejection_has_reason"),   # REQ-CLM-012
            models.CheckConstraint(condition=~Q(status="APPROVED") | Q(approved_amount__isnull=False),
                                   name="claim_approved_has_amount"),
            models.CheckConstraint(condition=Q(current_risk_score__isnull=True) | Q(current_risk_score__lte=100),
                                   name="claim_risk_score_range"),
        ]

    def __str__(self):
        return self.claim_number

    @property
    def customer(self):
        return self.policy.customer

    @property
    def vehicle(self):
        return self.policy.vehicle

    @property
    def edit_deadline(self):
        return self.submitted_at + timedelta(minutes=settings.CLAIM_EDIT_WINDOW_MINUTES)

    @property
    def is_editable(self):
        """REQ-CLM-006 / REQ-BR-010 — evaluated on the server for every edit request."""
        return (self.status == ClaimStatus.SUBMITTED and self.review_started_at is None
                and timezone.now() <= self.edit_deadline)


class ClaimStatusHistory(models.Model):
    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name="history")
    from_status = models.CharField(max_length=24, choices=ClaimStatus.choices, blank=True)
    to_status = models.CharField(max_length=24, choices=ClaimStatus.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                              related_name="+")  # null = system (e.g. fraud engine)
    reason = models.TextField(blank=True)
    is_internal = models.BooleanField(default=False)  # fraud/SIU details hidden from customers (REQ-FRD-010)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class AppealStatus(models.TextChoices):
    PENDING = "PENDING", "Pending review"
    ACCEPTED = "ACCEPTED", "Accepted — claim reopened"
    DECLINED = "DECLINED", "Declined"


class Appeal(models.Model):
    claim = models.ForeignKey(Claim, on_delete=models.PROTECT, related_name="appeals")
    sequence = models.PositiveSmallIntegerField()
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=AppealStatus.choices, default=AppealStatus.PENDING, db_index=True)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                   related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True)
    further_appeal_allowed = models.BooleanField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["claim", "sequence"], name="appeal_sequence_unique")]
