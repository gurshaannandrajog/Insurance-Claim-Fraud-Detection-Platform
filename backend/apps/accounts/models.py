from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class Role(models.TextChoices):
    CUSTOMER = "CUSTOMER", "Customer"
    ADJUSTER = "ADJUSTER", "Claim Adjuster"
    SIU = "SIU", "SIU Investigator"
    ADMIN = "ADMIN", "Administrator"


STAFF_ROLES = {Role.ADJUSTER, Role.SIU, Role.ADMIN}

phone_validator = RegexValidator(r"^\+?[0-9]{10,15}$", "Enter a valid phone number (10–15 digits, optional +).")


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.update(role=Role.ADMIN, is_email_verified=True, email_verified_at=timezone.now())
        extra.setdefault("full_name", "System Administrator")
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser):
    """Single user table for all four roles. Authorisation is driven by `role` (REQ-AUTH-008)."""

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CUSTOMER, db_index=True)
    is_active = models.BooleanField(default=True)
    is_email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)

    # Account lockout (REQ-AUTH-005)
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    deleted_at = models.DateTimeField(null=True, blank=True)
    date_joined = models.DateTimeField(default=timezone.now, db_index=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return f"{self.full_name} <{self.email}>"

    @property
    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())

    @property
    def is_customer(self):
        return self.role == Role.CUSTOMER

    @property
    def is_staff_member(self):
        return self.role in STAFF_ROLES

    # Django's auth backends call these; we do not use django.contrib.admin.
    @property
    def is_staff(self):
        return False

    @property
    def is_superuser(self):
        return False

    def has_perm(self, perm, obj=None):
        return False

    def has_module_perms(self, app_label):
        return False


class CustomerProfile(TimeStampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="customer_profile")
    phone = models.CharField(max_length=16, validators=[phone_validator])
    date_of_birth = models.DateField()                       # immutable via profile API (REQ-CUST-003)
    address_line = models.CharField(max_length=255)
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80)
    postal_code = models.CharField(max_length=10, validators=[RegexValidator(r"^[0-9A-Za-z -]{4,10}$")])

    def __str__(self):
        return f"Customer {self.user.full_name}"


class EmployeeProfile(TimeStampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="employee_profile")
    employee_id = models.CharField(max_length=20, unique=True)
    department = models.CharField(max_length=80, blank=True)
    phone = models.CharField(max_length=16, blank=True, validators=[phone_validator])
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    def __str__(self):
        return f"{self.employee_id} {self.user.full_name}"
