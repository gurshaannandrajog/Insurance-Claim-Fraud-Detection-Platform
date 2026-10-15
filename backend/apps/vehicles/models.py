from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class VehicleType(models.TextChoices):
    CAR = "CAR", "Car"
    MOTORCYCLE = "MOTORCYCLE", "Motorcycle"
    SCOOTER = "SCOOTER", "Scooter"
    SUV = "SUV", "SUV"
    COMMERCIAL = "COMMERCIAL", "Commercial vehicle"
    OTHER = "OTHER", "Other"


class Vehicle(TimeStampedModel):
    """REQ-VEH-002/003. Records are never deleted (REQ-VEH-010): there is no delete endpoint and FKs use PROTECT."""

    customer = models.ForeignKey("accounts.CustomerProfile", on_delete=models.PROTECT, related_name="vehicles")
    registration_number = models.CharField(
        max_length=15, unique=True,  # REQ-VEH-004 (stored normalised: upper-case, no spaces)
        validators=[RegexValidator(r"^[A-Z0-9-]{4,15}$", "Use letters and digits only, e.g. MH02AB1234.")])
    make = models.CharField(max_length=60)
    model = models.CharField(max_length=60)
    vehicle_type = models.CharField(max_length=12, choices=VehicleType.choices)
    manufacturing_year = models.PositiveSmallIntegerField(validators=[MinValueValidator(1950), MaxValueValidator(2100)])
    registration_date = models.DateField()
    purchase_date = models.DateField()
    engine_number = models.CharField(max_length=30, unique=True)
    chassis_number = models.CharField(max_length=30, unique=True)
    color = models.CharField(max_length=30)
    # Registered owner — stored separately from the policyholder (REQ-VEH-003)
    owner_name = models.CharField(max_length=150)
    owner_phone = models.CharField(max_length=16, blank=True)
    owner_address = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(manufacturing_year__gte=1950), name="vehicle_year_sane"),
        ]

    def __str__(self):
        return f"{self.registration_number} ({self.make} {self.model})"

    @property
    def is_locked(self):
        """REQ-VEH-009: immutable once associated with a policy (or a pending request)."""
        return self.policies.exists() or self.policy_requests.filter(status="PENDING").exists()

    @property
    def current_policy(self):
        return self.policies.filter(status__in=["ACTIVE", "PARTIALLY_CLAIMED", "CLAIMED"]).first()
