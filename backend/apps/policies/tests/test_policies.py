from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.accounts.models import Role
from apps.claims import services as claim_services
from apps.core.tests.factories import (BaseAPITest, make_customer, make_plan, make_policy, make_staff, make_vehicle,
                                       submit_claim)
from apps.policies.models import Policy, PolicyStatus
from apps.policies.services import expire_due_policies


class PolicyRequestTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.customer = make_customer()
        self.admin = make_staff(Role.ADMIN)
        self.plan = make_plan(premium_rate_percent=Decimal("2.50"))
        self.vehicle = make_vehicle(self.customer)
        self.cc = self.client_for(self.customer)
        self.ac = self.client_for(self.admin)

    def request_policy(self, vehicle=None, client=None):
        return (client or self.cc).post("/api/policy-requests/", {
            "vehicle_id": (vehicle or self.vehicle).pk, "plan_id": self.plan.pk, "requested_idv": "400000"},
            format="json")

    def test_request_and_admin_approval_creates_active_policy(self):
        r = self.request_policy()
        self.assertEqual(r.status_code, 201, r.data)
        r = self.ac.post(f"/api/policy-requests/{r.data['id']}/approve/", {}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertRegex(r.data["policy_number"], r"^POL-\d{4}-\d{6}$")          # REQ-POL-003
        self.assertEqual(r.data["status"], "ACTIVE")                              # REQ-POL-005
        self.assertEqual(Decimal(r.data["premium_amount"]), Decimal("10000.00"))  # 400000 × 2.5%
        self.assertEqual(r.data["vehicle"]["id"], self.vehicle.pk)

    def test_customer_cannot_approve_or_request_for_others_vehicle(self):
        r = self.request_policy()
        self.assertEqual(self.cc.post(f"/api/policy-requests/{r.data['id']}/approve/").status_code, 403)
        other_vehicle = make_vehicle(make_customer())
        self.assertEqual(self.request_policy(vehicle=other_vehicle).status_code, 404)

    def test_vehicle_cannot_have_two_live_policies(self):
        policy = make_policy(self.vehicle)
        for status in (PolicyStatus.ACTIVE, PolicyStatus.PARTIALLY_CLAIMED, PolicyStatus.CLAIMED):
            Policy.objects.filter(pk=policy.pk).update(status=status)
            r = self.request_policy()
            self.assertEqual(r.status_code, 409, status)                         # REQ-VEH-008
            self.assertEqual(r.data["error"]["code"], "vehicle_has_live_policy")
        for status in (PolicyStatus.EXPIRED, PolicyStatus.CANCELLED):
            Policy.objects.filter(pk=policy.pk).update(status=status)
            self.assertEqual(self.request_policy().status_code, 201, status)    # REQ-VEH-007 / REQ-POL-014
            self.cc.post(f"/api/policy-requests/{self.vehicle.policy_requests.first().pk}/withdraw/")

    def test_approval_rechecks_live_policy(self):
        r = self.request_policy()
        make_policy(self.vehicle)              # a policy appeared after the request was made
        r = self.ac.post(f"/api/policy-requests/{r.data['id']}/approve/", {}, format="json")
        self.assertEqual(r.status_code, 409)

    def test_reject_request_requires_reason(self):
        r = self.request_policy()
        self.assertEqual(self.ac.post(f"/api/policy-requests/{r.data['id']}/reject/", {}, format="json").status_code,
                         400)
        r = self.ac.post(f"/api/policy-requests/{r.data['id']}/reject/", {"reason": "Incomplete"}, format="json")
        self.assertEqual(r.data["status"], "REJECTED")

    def test_plan_change_does_not_affect_existing_policies(self):
        r = self.request_policy()
        policy = self.ac.post(f"/api/policy-requests/{r.data['id']}/approve/", {}, format="json").data
        self.ac.patch(f"/api/policy-plans/{self.plan.pk}/", {"premium_rate_percent": "9.99"}, format="json")
        p = Policy.objects.get(pk=policy["id"])
        self.assertEqual(p.premium_rate_percent, Decimal("2.50"))             # REQ-POL-015 / REQ-BR-021
        self.assertEqual(p.premium_amount, Decimal("10000.00"))

    def test_customer_sees_only_own_policies(self):
        mine = make_policy(self.vehicle)
        theirs = make_policy(make_vehicle(make_customer()))
        ids = [p["id"] for p in self.cc.get("/api/policies/").data["results"]]
        self.assertEqual(ids, [mine.pk])
        self.assertEqual(self.cc.get(f"/api/policies/{theirs.pk}/").status_code, 404)   # REQ-POL-016


class PolicyStatusTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.customer = make_customer()
        self.policy = make_policy(make_vehicle(self.customer), idv=100000)
        self.adjuster = make_staff(Role.ADJUSTER)

    def approve(self, amount, **kw):
        claim = submit_claim(self.policy, requested_amount=Decimal(amount), **kw)
        claim_services.start_review(self.adjuster, claim)
        for d in claim.documents.all():
            from apps.documents.services import verify_document
            verify_document(self.adjuster, d)
        return claim_services.approve_claim(self.adjuster, claim, Decimal(amount))

    def test_partially_claimed_then_claimed(self):
        self.approve(30000)
        self.policy.refresh_from_db()
        self.assertEqual(self.policy.cumulative_approved_amount, Decimal("30000"))
        self.assertEqual(self.policy.status, PolicyStatus.PARTIALLY_CLAIMED)          # REQ-POL-009
        self.approve(70000, incident_date=timezone.localdate() - timedelta(days=5))
        self.policy.refresh_from_db()
        self.assertEqual(self.policy.status, PolicyStatus.CLAIMED)                    # REQ-POL-010

    def test_claimed_policy_accepts_no_new_claims(self):
        Policy.objects.filter(pk=self.policy.pk).update(status=PolicyStatus.CLAIMED)
        with self.assertRaises(Exception) as ctx:
            submit_claim(self.policy)
        self.assertEqual(getattr(ctx.exception, "code", ""), "policy_not_claimable")   # REQ-POL-013

    def test_expiry(self):
        Policy.objects.filter(pk=self.policy.pk).update(end_date=timezone.localdate() - timedelta(days=1))
        self.assertEqual(expire_due_policies(), 1)                                      # REQ-POL-011
        self.policy.refresh_from_db()
        self.assertEqual(self.policy.status, PolicyStatus.EXPIRED)
        self.assertEqual(expire_due_policies(), 0)                                      # idempotent

    def test_cancellation_by_admin_only_and_blocked_by_open_claims(self):
        admin = self.client_for(make_staff(Role.ADMIN))
        self.assertEqual(self.client_for(self.customer).post(f"/api/policies/{self.policy.pk}/cancel/",
                                                             {"reason": "x"}, format="json").status_code, 403)
        claim = submit_claim(self.policy)
        r = admin.post(f"/api/policies/{self.policy.pk}/cancel/", {"reason": "Customer request"}, format="json")
        self.assertEqual(r.status_code, 409)
        claim_services.withdraw_claim(self.customer, claim)
        r = admin.post(f"/api/policies/{self.policy.pk}/cancel/", {"reason": "Customer request"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "CANCELLED")                                  # REQ-POL-012
