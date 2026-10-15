"""Authentication & account business logic (SRS §4.1, §4.2)."""
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.audit.models import AuditAction
from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError, ConflictError, ForbiddenActionError
from apps.notifications.services import send_email

from .models import CustomerProfile, EmployeeProfile, Role, User

VERIFY_SALT = "accounts.email-verification"


# ----------------------------------------------------------------------------- registration & verification
def make_verification_token(user):
    return signing.dumps({"uid": user.pk, "email": user.email}, salt=VERIFY_SALT)


def send_verification_email(user):
    link = f"{settings.FRONTEND_URL}/verify-email?token={make_verification_token(user)}"
    return send_email(
        user.email, "Verify your email address",
        f"Hello {user.full_name},\n\nPlease verify your email address to activate your account:\n{link}\n\n"
        f"This link is valid for {settings.EMAIL_VERIFICATION_MAX_AGE_HOURS} hours.",
    )


@transaction.atomic
def register_customer(*, email, password, full_name, phone, date_of_birth, address_line, city, state,
                      postal_code, request=None):
    email = email.strip().lower()
    if User.objects.filter(email=email).exists():
        raise ConflictError("An account with this email already exists.", code="email_taken",
                            fields={"email": ["An account with this email already exists."]})
    candidate = User(email=email, full_name=full_name)
    password_validation.validate_password(password, candidate)
    user = User.objects.create_user(email=email, password=password, full_name=full_name.strip(), role=Role.CUSTOMER)
    CustomerProfile.objects.create(user=user, phone=phone, date_of_birth=date_of_birth, address_line=address_line,
                                   city=city, state=state, postal_code=postal_code)
    log_event(AuditAction.USER_REGISTERED, user, actor=user, request=request)
    transaction.on_commit(lambda: send_verification_email(user))
    return user


def verify_email(token, request=None):
    try:
        data = signing.loads(token, salt=VERIFY_SALT, max_age=settings.EMAIL_VERIFICATION_MAX_AGE_HOURS * 3600)
    except signing.SignatureExpired:
        raise BusinessRuleError("This verification link has expired. Request a new one.", code="token_expired")
    except signing.BadSignature:
        raise BusinessRuleError("This verification link is invalid.", code="token_invalid")
    user = User.objects.filter(pk=data.get("uid"), email=data.get("email")).first()
    if not user:
        raise BusinessRuleError("This verification link is invalid.", code="token_invalid")
    if not user.is_email_verified:
        user.is_email_verified = True
        user.email_verified_at = timezone.now()
        user.save(update_fields=["is_email_verified", "email_verified_at"])
        log_event(AuditAction.EMAIL_VERIFIED, user, actor=user, request=request)
    return user


def resend_verification(email):
    user = User.objects.filter(email=email.strip().lower(), is_active=True, is_email_verified=False).first()
    if user:
        send_verification_email(user)
    # Always succeed silently: never reveal whether an email is registered.


# ----------------------------------------------------------------------------- login with lockout
def authenticate_user(email, password, request=None):
    """
    REQ-AUTH-003/005: email + password, email must be verified, 4 consecutive failures lock for 20 min.
    The counter is incremented with a row lock so concurrent bad attempts cannot slip past the limit.
    """
    generic = BusinessRuleError("Invalid email or password.", code="invalid_credentials", status_code=401)
    email = (email or "").strip().lower()
    with transaction.atomic():
        user = User.objects.select_for_update().filter(email=email).first()
        if user is None or user.deleted_at:
            # run a hash anyway to keep timing similar for unknown emails
            User().set_password(password)
            raise generic
        now = timezone.now()
        if user.is_locked:
            minutes = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
            raise BusinessRuleError(
                f"Account locked after repeated failed sign-in attempts. Try again in {minutes} minute(s).",
                code="account_locked", status_code=423, extra={"locked_until": user.locked_until.isoformat()})
        if user.locked_until and user.locked_until <= now:     # lock expired → fresh start
            user.locked_until = None
            user.failed_login_attempts = 0

        if not user.check_password(password):
            user.failed_login_attempts += 1
            log_event(AuditAction.LOGIN_FAILED, user, request=request,
                      metadata={"attempt": user.failed_login_attempts})
            if user.failed_login_attempts >= settings.LOGIN_MAX_FAILED_ATTEMPTS:
                user.locked_until = now + timedelta(minutes=settings.ACCOUNT_LOCK_MINUTES)
                user.failed_login_attempts = 0
                user.save(update_fields=["failed_login_attempts", "locked_until"])
                log_event(AuditAction.ACCOUNT_LOCKED, user, request=request,
                          metadata={"locked_until": user.locked_until.isoformat()})
                user_to_raise = BusinessRuleError(
                    f"Too many failed attempts. Your account is locked for {settings.ACCOUNT_LOCK_MINUTES} minutes.",
                    code="account_locked", status_code=423,
                    extra={"locked_until": user.locked_until.isoformat()})
            else:
                user.save(update_fields=["failed_login_attempts", "locked_until"])
                remaining = settings.LOGIN_MAX_FAILED_ATTEMPTS - user.failed_login_attempts
                user_to_raise = BusinessRuleError(
                    f"Invalid email or password. {remaining} attempt(s) left before the account is locked.",
                    code="invalid_credentials", status_code=401)
        else:
            user_to_raise = None
            if not user.is_active:
                user_to_raise = ForbiddenActionError("This account has been deactivated.", code="account_inactive")
            elif not user.is_email_verified:
                user_to_raise = ForbiddenActionError("Please verify your email address before signing in.",
                                                     code="email_not_verified")
            else:
                user.failed_login_attempts = 0
                user.locked_until = None
                user.last_login = now
                user.save(update_fields=["failed_login_attempts", "locked_until", "last_login"])
                log_event(AuditAction.LOGIN, user, actor=user, request=request)
    # raise outside the atomic block so the failed-attempt counter is committed
    if user_to_raise:
        raise user_to_raise
    return user


# ----------------------------------------------------------------------------- password reset / change
def request_password_reset(email, request=None):
    user = User.objects.filter(email=(email or "").strip().lower(), is_active=True, deleted_at__isnull=True).first()
    if not user:
        return  # do not reveal whether the email exists
    send_password_link(user, subject="Reset your password",
                       intro="We received a request to reset your password.")
    log_event(AuditAction.PASSWORD_RESET_REQUESTED, user, request=request)


def send_password_link(user, *, subject, intro):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
    return send_email(user.email, subject,
                      f"Hello {user.full_name},\n\n{intro}\nSet your password here:\n{link}\n\n"
                      "If you did not request this, you can ignore this email.")


def reset_password(uid, token, new_password, request=None):
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)))
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        user = None
    if user is None or not default_token_generator.check_token(user, token):
        raise BusinessRuleError("This password-reset link is invalid or has already been used.", code="token_invalid")
    password_validation.validate_password(new_password, user)
    user.set_password(new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    fields = ["password", "failed_login_attempts", "locked_until"]
    if user.is_staff_member and not user.is_email_verified:   # employees verify by setting their password
        user.is_email_verified, user.email_verified_at = True, timezone.now()
        fields += ["is_email_verified", "email_verified_at"]
    user.save(update_fields=fields)
    log_event(AuditAction.PASSWORD_CHANGED, user, actor=user, request=request, metadata={"via": "reset_link"})
    return user


def change_password(user, current_password, new_password, request=None):
    if not user.check_password(current_password):
        raise BusinessRuleError("Current password is incorrect.", code="invalid_password",
                                fields={"current_password": ["Current password is incorrect."]})
    password_validation.validate_password(new_password, user)
    user.set_password(new_password)
    user.save(update_fields=["password"])
    log_event(AuditAction.PASSWORD_CHANGED, user, actor=user, request=request)


# ----------------------------------------------------------------------------- profile & deletion
def update_customer_profile(user, data, request=None):
    """REQ-CUST-002/003: only name, phone and address fields are writable."""
    profile = user.customer_profile
    changed = []
    if "full_name" in data and data["full_name"] != user.full_name:
        user.full_name = data["full_name"]
        user.save(update_fields=["full_name"])
        changed.append("full_name")
    for field in ("phone", "address_line", "city", "state", "postal_code"):
        if field in data and getattr(profile, field) != data[field]:
            setattr(profile, field, data[field])
            changed.append(field)
    profile.full_clean()
    profile.save()
    if changed:
        log_event(AuditAction.PROFILE_UPDATED, user, actor=user, request=request, metadata={"fields": changed})
    return user


@transaction.atomic
def delete_customer_account(user, password, request=None):
    """REQ-CUST-007: allowed only without active claims. Records are retained; the login is disabled."""
    from apps.claims.models import Claim, ClaimStatus

    if not user.check_password(password):
        raise BusinessRuleError("Password is incorrect.", code="invalid_password",
                                fields={"password": ["Password is incorrect."]})
    active = Claim.objects.filter(policy__customer=user.customer_profile).exclude(
        status__in=ClaimStatus.terminal()).count()
    if active:
        raise ConflictError(f"You have {active} active claim(s). Accounts can only be deleted when no claims are active.",
                            code="active_claims_exist")
    original = user.email
    user.is_active = False
    user.deleted_at = timezone.now()
    user.email = f"deleted-{user.pk}-{secrets.token_hex(4)}@deleted.invalid"
    user.set_unusable_password()
    user.save()
    log_event(AuditAction.ACCOUNT_DELETED, user, actor=user, request=request, metadata={"original_email": original})


# ----------------------------------------------------------------------------- administration of users
@transaction.atomic
def create_employee(*, admin, email, full_name, role, employee_id, department="", phone="", request=None):
    if role not in (Role.ADJUSTER, Role.SIU, Role.ADMIN):
        raise BusinessRuleError("Employees must be Claim Adjusters, SIU Investigators or Administrators.",
                                code="invalid_role", fields={"role": ["Invalid employee role."]})
    email = email.strip().lower()
    if User.objects.filter(email=email).exists():
        raise ConflictError("An account with this email already exists.", code="email_taken",
                            fields={"email": ["An account with this email already exists."]})
    if EmployeeProfile.objects.filter(employee_id=employee_id).exists():
        raise ConflictError("Employee ID already in use.", code="employee_id_taken",
                            fields={"employee_id": ["Employee ID already in use."]})
    user = User.objects.create_user(email=email, password=None, full_name=full_name, role=role)
    EmployeeProfile.objects.create(user=user, employee_id=employee_id, department=department, phone=phone,
                                   created_by=admin)
    log_event(AuditAction.EMPLOYEE_CREATED, user, actor=admin, request=request, metadata={"role": role})
    transaction.on_commit(lambda: send_password_link(
        user, subject="Your Insurance Claims staff account",
        intro=f"An administrator created a {user.get_role_display()} account for you."))
    return user


def set_user_active(admin, user, active, request=None):
    if user.pk == admin.pk and not active:
        raise BusinessRuleError("You cannot deactivate your own account.", code="self_deactivation")
    user.is_active = active
    user.save(update_fields=["is_active"])
    log_event(AuditAction.USER_ACTIVATED if active else AuditAction.USER_DEACTIVATED, user, actor=admin,
              request=request)
    return user


def unlock_user(admin, user, request=None):
    user.locked_until = None
    user.failed_login_attempts = 0
    user.save(update_fields=["locked_until", "failed_login_attempts"])
    log_event(AuditAction.ACCOUNT_UNLOCKED, user, actor=admin, request=request)
    return user
