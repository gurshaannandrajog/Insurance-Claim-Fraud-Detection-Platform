from unittest import mock

from django.core import mail

from apps.core.tests.factories import BaseAPITest, make_customer, make_policy, make_vehicle, submit_claim
from apps.notifications.models import Notification
from apps.notifications.services import notify


class NotificationTests(BaseAPITest):
    def test_users_see_only_their_notifications_and_can_mark_read(self):
        me, other = make_customer(), make_customer()
        n = notify(me, "ACCOUNT", "Hello", "Mine", email=False)
        theirs = notify(other, "ACCOUNT", "Hi", "Theirs", email=False)
        c = self.client_for(me)
        r = c.get("/api/notifications/")
        self.assertEqual([x["id"] for x in r.data["results"]], [n.pk])
        self.assertEqual(c.get("/api/notifications/unread-count/").data["unread"], 1)
        self.assertEqual(c.post(f"/api/notifications/{theirs.pk}/read/").status_code, 404)
        self.assertTrue(c.post(f"/api/notifications/{n.pk}/read/").data["is_read"])
        self.assertEqual(c.get("/api/notifications/unread-count/").data["unread"], 0)

    def test_email_sent_after_commit_and_failures_are_recorded(self):
        user = make_customer()
        with self.captureOnCommitCallbacks(execute=True):
            n = notify(user, "CLAIM_UPDATE", "Subject", "Body", email=True)
        n.refresh_from_db()
        self.assertEqual(n.email_status, "SENT")
        self.assertEqual(mail.outbox[-1].to, [user.email])
        with mock.patch("apps.notifications.services.send_mail", side_effect=OSError("SMTP down")):
            with self.captureOnCommitCallbacks(execute=True):
                n2 = notify(user, "CLAIM_UPDATE", "Subject", "Body", email=True)
        n2.refresh_from_db()
        self.assertEqual(n2.email_status, "FAILED")      # email failure never breaks the business operation

    def test_claim_submission_notifies_customer(self):
        customer = make_customer()
        claim = submit_claim(make_policy(make_vehicle(customer)))
        self.assertTrue(Notification.objects.filter(recipient=customer, claim=claim, type="CLAIM_SUBMITTED").exists())
