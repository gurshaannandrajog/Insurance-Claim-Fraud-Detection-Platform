import re
import time
from datetime import timedelta

from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.middleware import SESSION_KEY
from apps.accounts.models import Role, User
from apps.accounts.services import make_verification_token
from apps.audit.models import AuditAction, AuditLog
from apps.core.tests.factories import PASSWORD, BaseAPITest, make_customer, make_policy, make_staff, make_vehicle, \
    submit_claim

REGISTER = {"email": "new.user@example.com", "password": "Valid#Pass1", "confirm_password": "Valid#Pass1",
            "full_name": "New User", "phone": "+919876543210", "date_of_birth": "1995-05-05",
            "address_line": "5 Hill Road", "city": "Mumbai", "state": "Maharashtra", "postal_code": "400050"}


class RegistrationTests(BaseAPITest):
    def test_register_sends_verification_and_blocks_login_until_verified(self):
        c = APIClient()
        with self.captureOnCommitCallbacks(execute=True):
            r = c.post("/api/auth/register/", REGISTER, format="json")
        self.assertEqual(r.status_code, 201)
        user = User.objects.get(email="new.user@example.com")
        self.assertEqual(user.role, Role.CUSTOMER)
        self.assertFalse(user.is_email_verified)
        self.assertNotEqual(user.password, "Valid#Pass1")            # REQ-AUTH-010: hashed, not plain text
        self.assertTrue(user.check_password("Valid#Pass1"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/verify-email?token=", mail.outbox[0].body)

        r = c.post("/api/auth/login/", {"email": user.email, "password": "Valid#Pass1"}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data["error"]["code"], "email_not_verified")

        token = re.search(r"token=(\S+)", mail.outbox[0].body).group(1)
        self.assertEqual(c.post("/api/auth/verify-email/", {"token": token}, format="json").status_code, 200)
        r = c.post("/api/auth/login/", {"email": user.email, "password": "Valid#Pass1"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["role"], "CUSTOMER")
        self.assertEqual(c.get("/api/auth/me/").data["email"], user.email)

    def test_invalid_verification_token(self):
        r = APIClient().post("/api/auth/verify-email/", {"token": "garbage"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["error"]["code"], "token_invalid")

    def test_password_policy_enforced(self):
        for weak in ["short1!A", "alllowercase1!", "ALLUPPERCASE1!", "NoNumbers!!", "NoSpecial123", "Ab1!"]:
            data = {**REGISTER, "password": weak, "confirm_password": weak}
            r = APIClient().post("/api/auth/register/", data, format="json")
            if weak == "short1!A":  # 8 chars, all classes → valid
                self.assertEqual(r.status_code, 201, r.data)
                User.objects.filter(email=REGISTER["email"]).delete()
                continue
            self.assertEqual(r.status_code, 400, weak)

    def test_duplicate_email_and_minimum_age(self):
        make_customer(email="taken@example.com")
        r = APIClient().post("/api/auth/register/", {**REGISTER, "email": "TAKEN@example.com"}, format="json")
        self.assertEqual(r.status_code, 409)
        r = APIClient().post("/api/auth/register/", {**REGISTER, "date_of_birth": str(timezone.localdate())},
                             format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("date_of_birth", r.data["error"]["fields"])

    def test_verification_token_is_tied_to_user(self):
        user = make_customer()
        user.is_email_verified = False
        user.save()
        token = make_verification_token(user)
        APIClient().post("/api/auth/verify-email/", {"token": token}, format="json")
        user.refresh_from_db()
        self.assertTrue(user.is_email_verified)


class LoginLockoutTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.user = make_customer(email="lock@example.com")
        self.c = APIClient()

    def login(self, password):
        return self.c.post("/api/auth/login/", {"email": "lock@example.com", "password": password}, format="json")

    def test_four_failures_lock_account_for_20_minutes(self):
        for i in range(3):
            r = self.login("wrong")
            self.assertEqual(r.status_code, 401)
        r = self.login("wrong")                                   # 4th consecutive failure
        self.assertEqual(r.status_code, 423)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_locked)
        lock_minutes = (self.user.locked_until - timezone.now()).total_seconds() / 60
        self.assertTrue(19 < lock_minutes <= 20)
        self.assertEqual(self.login(PASSWORD).status_code, 423)  # correct password still refused while locked
        self.assertTrue(AuditLog.objects.filter(action=AuditAction.ACCOUNT_LOCKED, entity_id=str(self.user.pk)).exists())
        self.assertEqual(AuditLog.objects.filter(action=AuditAction.LOGIN_FAILED).count(), 4)

        self.user.locked_until = timezone.now() - timedelta(seconds=1)   # lock elapses
        self.user.save()
        self.assertEqual(self.login(PASSWORD).status_code, 200)

    def test_success_resets_counter(self):
        self.login("wrong")
        self.login("wrong")
        self.assertEqual(self.login(PASSWORD).status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 0)

    def test_unknown_email_gives_generic_error(self):
        r = self.c.post("/api/auth/login/", {"email": "nobody@example.com", "password": "x"}, format="json")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.data["error"]["message"], "Invalid email or password.")

    def test_deactivated_user_cannot_login(self):
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.login(PASSWORD).status_code, 403)

    def test_admin_can_unlock(self):
        for _ in range(4):
            self.login("wrong")
        admin = make_staff(Role.ADMIN)
        r = self.client_for(admin).post(f"/api/admin/users/{self.user.pk}/unlock/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.login(PASSWORD).status_code, 200)


class CsrfTests(BaseAPITest):
    def test_login_requires_csrf_token(self):
        make_customer(email="csrf@example.com")
        c = APIClient(enforce_csrf_checks=True)
        r = c.post("/api/auth/login/", {"email": "csrf@example.com", "password": PASSWORD}, format="json")
        self.assertEqual(r.status_code, 403)
        c.get("/api/auth/csrf/")
        token = c.cookies["csrftoken"].value
        r = c.post("/api/auth/login/", {"email": "csrf@example.com", "password": PASSWORD}, format="json",
                   HTTP_X_CSRFTOKEN=token)
        self.assertEqual(r.status_code, 200)


class PasswordResetTests(BaseAPITest):
    def test_reset_flow_and_single_use_token(self):
        user = make_customer(email="reset@example.com")
        c = APIClient()
        c.post("/api/auth/password-reset/", {"email": "reset@example.com"}, format="json")
        self.assertEqual(len(mail.outbox), 1)
        uid, token = re.search(r"uid=([\w-]+)&token=([\w-]+)", mail.outbox[0].body).groups()
        r = c.post("/api/auth/password-reset/confirm/", {"uid": uid, "token": token, "new_password": "Brand#New9"},
                   format="json")
        self.assertEqual(r.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password("Brand#New9"))
        r = c.post("/api/auth/password-reset/confirm/", {"uid": uid, "token": token, "new_password": "Other#New9"},
                   format="json")
        self.assertEqual(r.status_code, 400)                      # token cannot be reused

    def test_unknown_email_does_not_reveal_anything(self):
        r = APIClient().post("/api/auth/password-reset/", {"email": "ghost@example.com"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_enforces_password_policy(self):
        make_customer(email="weak@example.com")
        c = APIClient()
        c.post("/api/auth/password-reset/", {"email": "weak@example.com"}, format="json")
        uid, token = re.search(r"uid=([\w-]+)&token=([\w-]+)", mail.outbox[0].body).groups()
        r = c.post("/api/auth/password-reset/confirm/", {"uid": uid, "token": token, "new_password": "password"},
                   format="json")
        self.assertEqual(r.status_code, 400)


class SessionTimeoutTests(BaseAPITest):
    def test_inactive_session_is_terminated_after_30_minutes(self):
        user = make_customer()
        c = APIClient()
        c.post("/api/auth/login/", {"email": user.email, "password": PASSWORD}, format="json")
        self.assertEqual(c.get("/api/auth/me/").status_code, 200)
        session = c.session
        session[SESSION_KEY] = time.time() - 31 * 60
        session.save()
        r = c.get("/api/auth/me/")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["error"]["code"], "session_expired")
        r = c.get("/api/auth/me/")                                   # the session is gone for good
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["error"]["code"], "not_authenticated")

    def test_background_polling_does_not_count_as_activity(self):
        user = make_customer()
        c = APIClient()
        c.post("/api/auth/login/", {"email": user.email, "password": PASSWORD}, format="json")
        session = c.session
        old = time.time() - 20 * 60
        session[SESSION_KEY] = old
        session.save()
        c.get("/api/notifications/unread-count/", HTTP_X_BACKGROUND_POLL="1")
        self.assertAlmostEqual(c.session[SESSION_KEY], old, delta=1)
        c.get("/api/auth/me/")
        self.assertGreater(c.session[SESSION_KEY], old + 60)


class ProfileTests(BaseAPITest):
    def test_customer_updates_allowed_fields_only(self):
        user = make_customer()
        c = self.client_for(user)
        r = c.patch("/api/profile/", {"phone": "+919811112222", "city": "Pune"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["customer_profile"]["phone"], "+919811112222")
        for field, value in (("email", "x@example.com"), ("date_of_birth", "2000-01-01")):
            r = c.patch("/api/profile/", {field: value}, format="json")
            self.assertEqual(r.status_code, 400)                  # REQ-CUST-003
        user.refresh_from_db()
        self.assertNotEqual(user.email, "x@example.com")

    def test_account_deletion_blocked_by_active_claim(self):
        user = make_customer()
        policy = make_policy(make_vehicle(user))
        submit_claim(policy)
        c = self.client_for(user)
        r = c.post("/api/profile/delete/", {"password": PASSWORD}, format="json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["error"]["code"], "active_claims_exist")

    def test_account_deletion_without_active_claims(self):
        user = make_customer()
        r = self.client_for(user).post("/api/profile/delete/", {"password": PASSWORD}, format="json")
        self.assertEqual(r.status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertIsNotNone(user.deleted_at)


class EmployeeAdministrationTests(BaseAPITest):
    def test_admin_creates_employee_who_sets_password_by_email(self):
        admin = make_staff(Role.ADMIN)
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client_for(admin).post("/api/admin/users/", {
                "email": "new.adjuster@claims.local", "full_name": "New Adjuster", "role": "ADJUSTER",
                "employee_id": "EMP-9001"}, format="json")
        self.assertEqual(r.status_code, 201)
        emp = User.objects.get(email="new.adjuster@claims.local")
        self.assertFalse(emp.has_usable_password())
        uid, token = re.search(r"uid=([\w-]+)&token=([\w-]+)", mail.outbox[-1].body).groups()
        r = APIClient().post("/api/auth/password-reset/confirm/",
                             {"uid": uid, "token": token, "new_password": "Kx9#mountain"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        r = APIClient().post("/api/auth/login/", {"email": emp.email, "password": "Kx9#mountain"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["role"], "ADJUSTER")

    def test_non_admins_cannot_manage_users(self):
        for role in (Role.CUSTOMER, Role.ADJUSTER, Role.SIU):
            user = make_customer() if role == Role.CUSTOMER else make_staff(role)
            c = self.client_for(user)
            self.assertEqual(c.get("/api/admin/users/").status_code, 403)
            self.assertEqual(c.post("/api/admin/users/", {"email": "a@b.c", "full_name": "X Y", "role": "ADMIN",
                                                          "employee_id": "EMP-1"}, format="json").status_code, 403)

    def test_unauthenticated_requests_are_rejected(self):
        for url in ("/api/claims/", "/api/vehicles/", "/api/policies/", "/api/dashboard/", "/api/notifications/"):
            self.assertEqual(APIClient().get(url).status_code, 401, url)
