import json
from decimal import Decimal

from apps.accounts.models import Role
from apps.claims import services as claim_services
from apps.claims.models import ClaimStatus
from apps.core.tests.factories import (BaseAPITest, fraud_result, make_customer, make_policy, make_staff, make_vehicle,
                                       submit_claim)
from apps.fraud.client import FraudServiceError
from apps.fraud.features import build_payload
from apps.fraud.services import classify
from apps.investigations.models import Investigation, InvestigationStatus
from apps.notifications.models import Notification

FRAUD_WORDS = ("risk", "fraud", "flag", "indicator", "investigat", "siu")


def _keys(obj, out=None):
    out = out if out is not None else set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k.lower())
            _keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _keys(v, out)
    return out


class FraudAssessmentTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.customer = make_customer()
        self.policy = make_policy(make_vehicle(self.customer), idv=300000)
        self.siu = make_staff(Role.SIU)
        self.adjuster = make_staff(Role.ADJUSTER)

    def test_classification_bands(self):
        self.assertEqual([classify(s) for s in (0, 29, 30, 59, 60, 100)],
                         ["LOW", "LOW", "MEDIUM", "MEDIUM", "HIGH", "HIGH"])               # REQ-FRD-003

    def test_low_and_medium_risk_are_not_flagged(self):
        self.fraud.return_value = fraud_result(45, "MEDIUM")
        claim = submit_claim(self.policy)
        self.assertEqual(claim.status, ClaimStatus.SUBMITTED)
        self.assertEqual(claim.current_risk_level, "MEDIUM")
        self.assertFalse(claim.is_flagged)

    def test_high_risk_goes_to_fraud_review_not_rejection(self):
        self.fraud.return_value = fraud_result(78, "HIGH")
        claim = submit_claim(self.policy)
        self.assertEqual(claim.status, ClaimStatus.FRAUD_REVIEW)                          # REQ-FRD-006
        self.assertTrue(claim.is_flagged)                                                 # REQ-FRD-005
        self.assertNotIn(claim.status, (ClaimStatus.REJECTED, ClaimStatus.PERMANENTLY_REJECTED))  # REQ-FRD-007
        a = claim.fraud_assessments.get()
        self.assertEqual((a.risk_score, a.risk_level, a.indicators.count()), (78, "HIGH", 1))  # REQ-FRD-004
        self.assertEqual(Investigation.objects.get(claim=claim).status, InvestigationStatus.OPEN)
        self.assertTrue(Notification.objects.filter(recipient=self.siu, type="FRAUD_ALERT").exists())
        # flagged claim cannot be decided until SIU finishes
        r = self.client_for(self.adjuster).post(f"/api/claims/{claim.pk}/approve/", {"approved_amount": "10"},
                                                format="json")
        self.assertEqual(r.status_code, 409)

    def test_level_is_derived_from_score_not_trusted_from_service(self):
        self.fraud.return_value = fraud_result(65, "LOW")   # inconsistent response
        claim = submit_claim(self.policy)
        self.assertEqual(claim.current_risk_level, "HIGH")

    def test_service_unavailable_degrades_gracefully(self):
        self.fraud.side_effect = FraudServiceError("Fraud service unreachable: ConnectionError")
        claim = submit_claim(self.policy)                                                 # submission still succeeds
        self.assertEqual(claim.status, ClaimStatus.SUBMITTED)
        self.assertEqual(claim.fraud_assessments.get().status, "FAILED")
        ac = self.client_for(self.adjuster)
        ac.post(f"/api/claims/{claim.pk}/start-review/")
        for d in claim.documents.all():
            ac.post(f"/api/documents/{d.pk}/verify/")
        r = ac.post(f"/api/claims/{claim.pk}/approve/", {"approved_amount": "1000"}, format="json")
        self.assertEqual(r.data["error"]["code"], "fraud_assessment_missing")             # no decision without it
        self.fraud.side_effect = None
        self.fraud.return_value = fraud_result(12, "LOW")
        r = ac.post(f"/api/claims/{claim.pk}/rerun-fraud/")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["status"], "COMPLETED")
        r = ac.post(f"/api/claims/{claim.pk}/approve/", {"approved_amount": "1000"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)

    def test_customer_never_sees_fraud_information(self):
        self.fraud.return_value = fraud_result(88, "HIGH")
        claim = submit_claim(self.policy)
        c = self.client_for(self.customer)
        detail = c.get(f"/api/claims/{claim.pk}/").data
        listing = c.get("/api/claims/").data
        dash = c.get("/api/dashboard/").data
        for payload in (detail, listing, dash):
            keys = _keys(json.loads(json.dumps(payload, default=str)))
            leaked = {k for k in keys if any(w in k for w in FRAUD_WORDS)}
            self.assertEqual(leaked, set(), leaked)                                       # REQ-FRD-010
        self.assertEqual(detail["status"], "UNDER_REVIEW")                                # Fraud Review masked
        self.assertNotIn("Fraud", json.dumps(detail["timeline"], default=str))
        self.assertNotIn("88", json.dumps(detail["timeline"], default=str))
        self.assertEqual(c.get("/api/fraud/assessments/").status_code, 403)
        self.assertEqual(c.get("/api/claims/?risk_level=HIGH").data["count"], 1)          # filter ignored for customers

    def test_staff_can_view_fraud_details(self):
        self.fraud.return_value = fraud_result(70, "HIGH")
        claim = submit_claim(self.policy)
        for role in (Role.ADJUSTER, Role.SIU, Role.ADMIN):                                # REQ-FRD-008/009
            r = self.client_for(make_staff(role)).get(f"/api/claims/{claim.pk}/")
            self.assertEqual(r.data["fraud_assessments"][0]["risk_score"], 70, role)

    def test_feature_payload(self):
        claim = submit_claim(self.policy, requested_amount=Decimal("90000"))
        p = build_payload(claim)
        self.assertEqual(p["claim"]["requested_amount"], 90000.0)
        self.assertEqual(p["policy"]["idv"], 300000.0)
        self.assertEqual(set(p), {"claim", "policy", "vehicle", "history", "documents"})
        self.assertIn("KYC", p["documents"]["types"])

    def test_assessments_are_retained(self):
        claim = submit_claim(self.policy)
        claim_services.edit_claim(self.customer, claim, {"requested_amount": Decimal("40000")})
        self.assertEqual(claim.fraud_assessments.count(), 2)                              # REQ-FRD-012
