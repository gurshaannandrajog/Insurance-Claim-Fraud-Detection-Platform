"""
In-app + email notifications (REQ-BR-022, REQ-CLM-018, REQ-DOC-010).

The in-app row is written inside the caller's transaction (so it is rolled back together with the
business change). The email is sent only *after* the transaction commits (`on_commit`), so a rolled-back
approval can never e-mail the customer. Email failures never break the business operation; they are
recorded in `email_status` and logged.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction

from apps.accounts.models import Role, User

from .models import EmailStatus, Notification, NotificationType

logger = logging.getLogger(__name__)


def send_email(to, subject, body):
    """Send one plain-text email. Returns True on success; never raises."""
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to], fail_silently=False)
        return True
    except Exception:  # SMTP down, bad credentials, DNS... — must not break the request
        logger.exception("Email to %s failed (%s)", to, subject)
        return False


def _email_body(user, message, link):
    url = f"{settings.FRONTEND_URL}{link}" if link else settings.FRONTEND_URL
    return (f"Hello {user.full_name},\n\n{message}\n\nView in the portal: {url}\n\n"
            "— Insurance Claim Processing & Fraud Detection Platform\n"
            "This is an automated message; please do not reply.")


def notify(recipient, ntype, title, message, *, claim=None, link="", email=True):
    if recipient is None or not recipient.is_active:
        return None
    note = Notification.objects.create(
        recipient=recipient, type=ntype, title=title, message=message, claim=claim, link=link,
        email_status=EmailStatus.PENDING if email else EmailStatus.NOT_REQUIRED,
    )
    if email:
        def _send():
            ok = send_email(recipient.email, title, _email_body(recipient, message, link))
            Notification.objects.filter(pk=note.pk).update(
                email_status=EmailStatus.SENT if ok else EmailStatus.FAILED)
        transaction.on_commit(_send)
    return note


def notify_role(role, ntype, title, message, *, claim=None, link="", email=False):
    for user in User.objects.filter(role=role, is_active=True):
        notify(user, ntype, title, message, claim=claim, link=link, email=email)


def notify_staff_claim(user_or_none, role, *args, **kwargs):
    """Notify a specific staff member, or everyone with `role` if nobody is assigned yet."""
    if user_or_none is not None:
        return notify(user_or_none, *args, **kwargs)
    return notify_role(role, *args, **kwargs)


__all__ = ["notify", "notify_role", "notify_staff_claim", "send_email", "NotificationType", "Role"]
