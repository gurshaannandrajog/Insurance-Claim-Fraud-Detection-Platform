from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q

from apps.core.models import TimeStampedModel


class PolicyStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    PARTIALLY_CLAIMED = "PARTIALLY_CLAIMED", "Partially Claimed"
    CLAIMED = "CLAIMED", "Claimed"
    EXPIRED = "EXPIRED", "Expired"
    CANCELLED = "CANCELLED", "Cancelled"

    @classmethod
    def live(cls):
        """Statuses that block a new policy for the same vehicle (REQ-VEH-008)."""
        return [cls.ACTIVE, cls.PARTIALLY_CLAIMED, cls.CLAIMED]

    @classmethod
    def claimable(cls):
        """Statuses that accept new claims (REQ-POL-013 / REQ-CLM-004)."""
        return [cls.ACTIVE, cls.PARTIALLY_CLAIMED]


class PolicyPlan(TimeStampedModel):
    """
    Admin-managed product configuration (REQ-POL-015, REQ-BR-021). Policies copy these values at creation,
    so editing a plan only affects *future* policyholders.
    """
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    premium_rate_percent = models.DecimalField(max_digits=5, decimal_places=2,
                                               validators=[MinValueValidator(Decimal("0.01"))])
    term_months = models.PositiveSmallIntegerField(default=12)
    min_idv = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("10000"))
    max_idv = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("10000000"))
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(condition=Q(premium_rate_percent__gt=0), name="plan_rate_positive"),
            models.CheckConstraint(condition=Q(term_months__gte=1) & Q(term_months__lte=60), name="plan_term_range"),
            models.CheckConstraint(condition=Q(max_idv__gte=F("min_idv")), name="plan_idv_range"),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class PolicyRequestStatus(models.TextChoices):
    PENDING = "PENDING", "Pending review"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"


class PolicyRequest(TimeStampedModel):
    customer = models.ForeignKey("accounts.CustomerProfile", on_delete=models.PROTECT, related_name="policy_requests")
    vehicle = models.ForeignKey("vehicles.Vehicle", on_delete=models.PROTECT, related_name="policy_requests")
    plan = models.ForeignKey(PolicyPlan, on_delete=models.PROTECT, related_name="requests")
    requested_idv = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=10, choices=PolicyRequestStatus.choices, default=PolicyRequestStatus.PENDING,
                              db_index=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                    related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=Q(requested_idv__gt=0), name="request_idv_positive")]


class Policy(TimeStampedModel):
    policy_number = models.CharField(max_length=24, unique=True)
    customer = models.ForeignKey("accounts.CustomerProfile", on_delete=models.PROTECT, related_name="policies")
    vehicle = models.ForeignKey("vehicles.Vehicle", on_delete=models.PROTECT, related_name="policies")
    request = models.OneToOneField(PolicyRequest, null=True, blank=True, on_delete=models.PROTECT,
                                   related_name="policy")
    # Snapshot of plan terms at creation (REQ-POL-015)
    plan = models.ForeignKey(PolicyPlan, on_delete=models.PROTECT, related_name="policies")
    plan_name = models.CharField(max_length=80)
    premium_rate_percent = models.DecimalField(max_digits=5, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField()
    idv = models.DecimalField(max_digits=12, decimal_places=2)
    premium_amount = models.DecimalField(max_digits=12, decimal_places=2)
    cumulative_approved_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    status = models.CharField(max_length=20, choices=PolicyStatus.choices, default=PolicyStatus.ACTIVE, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                     related_name="+")
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["vehicle", "status"]), models.Index(fields=["end_date", "status"])]
        constraints = [
            models.CheckConstraint(condition=Q(idv__gt=0), name="policy_idv_positive"),
            models.CheckConstraint(condition=Q(premium_amount__gte=0), name="policy_premium_nonneg"),
            models.CheckConstraint(condition=Q(end_date__gt=F("start_date")), name="policy_dates_order"),
            models.CheckConstraint(condition=Q(cumulative_approved_amount__gte=0) &
                                   Q(cumulative_approved_amount__lte=F("idv")), name="policy_cumulative_le_idv"),
        ]

    def __str__(self):
        return self.policy_number

    @property
    def remaining_idv(self):
        return self.idv - self.cumulative_approved_amount
