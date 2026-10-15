"""Role × protected-function matrix (REQ-AUTH-008/009, REQ-SEC-007..012). 403 = forbidden by role."""
from apps.accounts.models import Role
from apps.core.tests.factories import (BaseAPITest, fraud_result, make_customer, make_plan, make_policy, make_staff,
                                       make_vehicle, submit_claim)

ALLOW, DENY = "allow", "deny"


class AuthorizationMatrixTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.customer = make_customer()
        self.users = {Role.CUSTOMER: self.customer, Role.ADJUSTER: make_staff(Role.ADJUSTER),
                      Role.SIU: make_staff(Role.SIU), Role.ADMIN: make_staff(Role.ADMIN)}
        self.policy = make_policy(make_vehicle(self.customer))
        self.fraud.return_value = fraud_result(70, "HIGH")
        self.claim = submit_claim(self.policy)
        self.plan = make_plan()

    def check(self, method, url, expected, data=None):
        for role, user in self.users.items():
            r = getattr(self.client_for(user), method)(url, data or {}, format="json")
            denied = r.status_code == 403
            want = expected[role]
            self.assertEqual(denied, want == DENY, f"{method.upper()} {url} as {role}: {r.status_code}")

    def test_matrix(self):
        C, A, S, M = Role.CUSTOMER, Role.ADJUSTER, Role.SIU, Role.ADMIN
        cid = self.claim.pk
        rows = [
            ("post", "/api/vehicles/", {C: ALLOW, A: DENY, S: DENY, M: DENY}),
            ("post", "/api/policy-requests/", {C: ALLOW, A: DENY, S: DENY, M: DENY}),
            ("post", "/api/policy-plans/", {C: DENY, A: DENY, S: DENY, M: ALLOW}),
            ("post", f"/api/policies/{self.policy.pk}/cancel/", {C: DENY, A: DENY, S: DENY, M: ALLOW}),
            ("post", "/api/claims/", {C: ALLOW, A: DENY, S: DENY, M: DENY}),
            ("post", f"/api/claims/{cid}/approve/", {C: DENY, A: ALLOW, S: DENY, M: DENY}),
            ("post", f"/api/claims/{cid}/reject/", {C: DENY, A: ALLOW, S: DENY, M: DENY}),
            ("post", f"/api/claims/{cid}/start-review/", {C: DENY, A: ALLOW, S: DENY, M: DENY}),
            ("post", f"/api/claims/{cid}/appeal/", {C: ALLOW, A: DENY, S: DENY, M: DENY}),
            ("get", "/api/fraud/assessments/", {C: DENY, A: ALLOW, S: ALLOW, M: ALLOW}),
            ("get", "/api/investigations/", {C: DENY, A: ALLOW, S: ALLOW, M: ALLOW}),
            ("post", f"/api/investigations/{self.claim.investigations.get().pk}/start/",
             {C: DENY, A: DENY, S: ALLOW, M: DENY}),
            ("get", "/api/reports/", {C: DENY, A: DENY, S: DENY, M: ALLOW}),
            ("get", "/api/admin/users/", {C: DENY, A: DENY, S: DENY, M: ALLOW}),
            ("get", "/api/audit-logs/", {C: DENY, A: DENY, S: DENY, M: ALLOW}),
            ("get", "/api/profile/", {C: ALLOW, A: DENY, S: DENY, M: DENY}),
        ]
        for method, url, expected in rows:
            self.check(method, url, expected)
