"""
Scheduled housekeeping — run daily (Windows Task Scheduler / cron), e.g.:
    python manage.py run_maintenance
* expires policies whose validity period has ended (REQ-POL-011, REQ-BR-007)
* closes rejected claims whose appeal window elapsed without an appeal (activity diagram 'Close Claim')
Both operations are idempotent and also triggered lazily by the API, so the system is correct even if this
job has not run yet.
"""
from django.core.management.base import BaseCommand

from apps.claims.services import close_unappealed_rejections
from apps.policies.services import expire_due_policies


class Command(BaseCommand):
    help = "Expire due policies and close rejected claims past the appeal window."

    def handle(self, *args, **options):
        expired = expire_due_policies()
        closed = close_unappealed_rejections()
        self.stdout.write(self.style.SUCCESS(f"Expired {expired} policy(ies); closed {closed} claim(s)."))
