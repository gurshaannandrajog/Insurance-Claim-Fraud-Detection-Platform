from decimal import Decimal

from apps.accounts.models import Role
from apps.claims.models import ClaimStatus
from apps.core.tests.factories import (BaseAPITest, fraud_result, make_customer, make_policy, make_staff, make_vehicle,
                                       submit_claim)


class SIUWorkflowTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.customer = make_customer()
        self.policy = make_policy(make_vehicle(self.customer), idv=400000)
        self.fraud.return_value = fraud_result(75, "HIGH")
        self.claim = submit_claim(self.policy, requested_amount=Decimal("100000"))
        self.inv = self.claim.investigations.get()
        self.siu_user = make_staff(Role.SIU)
        self.sc = self.client_for(self.siu_user)
        self.adjuster = make_staff(Role.ADJUSTER)
        self.ac = self.client_for(self.adjuster)

    def test_siu_sees_flagged_claims_only(self):
        self.fraud.return_value = fraud_result(5, "LOW")
        clean = submit_claim(make_policy(make_vehicle(make_customer())))
        self.assertEqual(self.sc.get(f"/api/claims/{self.claim.pk}/").status_code, 200)
        self.assertEqual(self.sc.get(f"/api/claims/{clean.pk}/").status_code, 404)        # REQ-SEC-010
        detail = self.sc.get(f"/api/claims/{self.claim.pk}/").data
        self.assertEqual(detail["fraud_assessments"][0]["risk_score"], 75)
        self.assertIn("investigate", detail["actions"])
        doc = self.claim.documents.first()
        self.assertEqual(self.sc.get(f"/api/documents/{doc.pk}/download/").status_code, 200)

    def test_complete_investigation_returns_claim_to_adjuster(self):
        self.assertEqual(self.sc.post(f"/api/investigations/{self.inv.pk}/start/").data["status"], "IN_PROGRESS")
        r = self.sc.post(f"/api/investigations/{self.inv.pk}/progress/",
                         {"findings": "Draft", "note": "Called the workshop"}, format="json")
        self.assertEqual(len(r.data["notes"]), 1)
        r = self.sc.post(f"/api/investigations/{self.inv.pk}/complete/", {"findings": ""}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.sc.post(f"/api/investigations/{self.inv.pk}/complete/",
                         {"findings": "Damage consistent with account; garage invoice verified.",
                          "recommendation": "LEGITIMATE"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.UNDER_REVIEW)

        # completed investigations are permanent
        r = self.sc.post(f"/api/investigations/{self.inv.pk}/progress/", {"findings": "edit"}, format="json")
        self.assertEqual(r.status_code, 409)

        # SIU cannot decide; the adjuster can now approve (High score alone never rejects)
        self.assertEqual(self.sc.post(f"/api/claims/{self.claim.pk}/approve/", {"approved_amount": "1"},
                                      format="json").status_code, 403)
        for d in self.claim.documents.all():
            self.ac.post(f"/api/documents/{d.pk}/verify/")
        r = self.ac.post(f"/api/claims/{self.claim.pk}/approve/", {"approved_amount": "90000"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["investigations"][0]["recommendation"], "LEGITIMATE")

    def test_re_assessment_after_siu_does_not_loop(self):
        self.sc.post(f"/api/investigations/{self.inv.pk}/complete/",
                     {"findings": "Checked", "recommendation": "SUSPICIOUS"}, format="json")
        r = self.ac.post(f"/api/claims/{self.claim.pk}/rerun-fraud/")
        self.assertEqual(r.status_code, 201)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.UNDER_REVIEW)

    def test_adjuster_escalation_creates_investigation(self):
        self.fraud.return_value = fraud_result(40, "MEDIUM")
        claim = submit_claim(make_policy(make_vehicle(make_customer())))
        self.ac.post(f"/api/claims/{claim.pk}/start-review/")
        self.assertEqual(self.ac.post(f"/api/claims/{claim.pk}/escalate/", {"reason": ""},
                                      format="json").status_code, 400)
        r = self.ac.post(f"/api/claims/{claim.pk}/escalate/", {"reason": "Photos look reused"}, format="json")
        self.assertEqual(r.data["status"], "FRAUD_REVIEW")
        self.assertEqual(claim.investigations.get().trigger, "ESCALATION")

    def test_only_siu_records_findings(self):
        for user in (self.adjuster, make_staff(Role.ADMIN), self.customer):
            r = self.client_for(user).post(f"/api/investigations/{self.inv.pk}/complete/",
                                           {"findings": "x", "recommendation": "LEGITIMATE"}, format="json")
            self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client_for(self.customer).get("/api/investigations/").status_code, 403)

    def test_second_investigator_cannot_take_over(self):
        self.sc.post(f"/api/investigations/{self.inv.pk}/start/")
        other = self.client_for(make_staff(Role.SIU))
        self.assertEqual(other.post(f"/api/investigations/{self.inv.pk}/progress/", {"findings": "x"},
                                    format="json").status_code, 403)
