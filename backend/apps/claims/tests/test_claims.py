from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.utils import timezone

from apps.accounts.models import Role
from apps.audit.models import AuditAction, AuditLog
from apps.claims import services
from apps.claims.models import Claim, ClaimStatus
from apps.core.sample_files import upload_jpeg, upload_pdf
from apps.core.tests.factories import (BaseAPITest, claim_data, make_customer, make_policy, make_staff, make_vehicle,
                                       submit_claim)
from apps.documents.services import verify_document
from apps.notifications.models import Notification
from apps.policies.models import Policy, PolicyStatus


def multipart(policy, **overrides):
    d = claim_data(**overrides)
    return {"vehicle_id": policy.vehicle_id, "policy_id": policy.pk, "claim_type": d["claim_type"],
            "incident_date": str(d["incident_date"]), "incident_time": "14:00", "incident_location": "Andheri",
            "description": d["description"], "requested_amount": str(d["requested_amount"]),
            "document_types": ["KYC", "ADDRESS_PROOF", "VEHICLE_REGISTRATION", "ACCIDENT_PHOTO"],
            "files": [upload_pdf("kyc.pdf"), upload_pdf("addr.pdf"), upload_pdf("rc.pdf"), upload_jpeg("p.jpg")]}


class ClaimSubmissionTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.customer = make_customer()
        self.policy = make_policy(make_vehicle(self.customer), idv=500000)
        self.c = self.client_for(self.customer)

    def test_valid_submission_end_to_end(self):
        with self.captureOnCommitCallbacks(execute=True):
            r = self.c.post("/api/claims/", multipart(self.policy), format="multipart")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertRegex(r.data["claim_number"], r"^CLM-\d{4}-\d{6}$")
        self.assertEqual(r.data["status"], "SUBMITTED")
        self.assertTrue(r.data["is_editable"])
        self.assertEqual(len(r.data["documents"]), 4)
        claim = Claim.objects.get(pk=r.data["id"])
        self.assertEqual(claim.fraud_assessments.count(), 1)                    # fraud triggered
        self.assertTrue(Notification.objects.filter(recipient=self.customer, claim=claim).exists())
        self.assertTrue(any("submitted" in m.subject for m in mail.outbox))       # email notification
        self.assertTrue(AuditLog.objects.filter(action=AuditAction.CLAIM_SUBMITTED, entity_id=str(claim.pk)).exists())

    def test_missing_mandatory_documents(self):
        data = multipart(self.policy)
        data["document_types"], data["files"] = ["KYC"], [upload_pdf("kyc.pdf")]
        r = self.c.post("/api/claims/", data, format="multipart")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["error"]["code"], "missing_documents")
        self.assertEqual(Claim.objects.count(), 0)

    def test_policy_must_belong_to_customer_and_vehicle(self):
        other = make_policy(make_vehicle(make_customer()))
        r = self.c.post("/api/claims/", {**multipart(self.policy), "policy_id": other.pk}, format="multipart")
        self.assertEqual(r.status_code, 400)
        second_vehicle_policy = make_policy(make_vehicle(self.customer))
        r = self.c.post("/api/claims/", {**multipart(self.policy), "policy_id": second_vehicle_policy.pk},
                        format="multipart")
        self.assertEqual(r.data["error"]["code"], "policy_mismatch")

    def test_expired_cancelled_and_claimed_policies_rejected(self):
        for status in (PolicyStatus.EXPIRED, PolicyStatus.CANCELLED, PolicyStatus.CLAIMED):
            Policy.objects.filter(pk=self.policy.pk).update(status=status)
            r = self.c.post("/api/claims/", multipart(self.policy), format="multipart")
            self.assertEqual(r.status_code, 409, status)                         # REQ-CLM-004
            self.assertEqual(r.data["error"]["code"], "policy_not_claimable")

    def test_incident_must_be_in_policy_period_and_not_future(self):
        before = self.policy.start_date - timedelta(days=1)
        r = self.c.post("/api/claims/", multipart(self.policy, incident_date=before), format="multipart")
        self.assertEqual(r.status_code, 409)
        future = timezone.localdate() + timedelta(days=1)
        r = self.c.post("/api/claims/", multipart(self.policy, incident_date=future), format="multipart")
        self.assertEqual(r.status_code, 400)

    def test_amount_cannot_exceed_remaining_idv(self):
        r = self.c.post("/api/claims/", multipart(self.policy, requested_amount=Decimal("600000")), format="multipart")
        self.assertEqual(r.data["error"]["code"], "exceeds_remaining_idv")

    def test_duplicate_claim_for_same_incident(self):
        self.assertEqual(self.c.post("/api/claims/", multipart(self.policy), format="multipart").status_code, 201)
        r = self.c.post("/api/claims/", multipart(self.policy), format="multipart")
        self.assertEqual(r.status_code, 409)                                      # REQ-CLM-016/017
        self.assertEqual(r.data["error"]["code"], "duplicate_claim")
        # a different claim type on the same day is a different incident
        r = self.c.post("/api/claims/", multipart(self.policy, claim_type="THIRD_PARTY") | {
            "document_types": ["KYC", "ADDRESS_PROOF", "VEHICLE_REGISTRATION"],
            "files": [upload_pdf("a.pdf"), upload_pdf("b.pdf"), upload_pdf("c.pdf")]}, format="multipart")
        self.assertEqual(r.status_code, 201)

    def test_withdrawn_claim_does_not_block_resubmission(self):
        claim = submit_claim(self.policy)
        self.assertEqual(self.c.post(f"/api/claims/{claim.pk}/withdraw/").status_code, 200)
        self.assertEqual(self.c.post("/api/claims/", multipart(self.policy), format="multipart").status_code, 201)


class ClaimEditWindowTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.customer = make_customer()
        self.claim = submit_claim(make_policy(make_vehicle(self.customer)))
        self.c = self.client_for(self.customer)

    def test_edit_within_30_minutes(self):
        r = self.c.patch(f"/api/claims/{self.claim.pk}/", {"requested_amount": "45000"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(Decimal(r.data["requested_amount"]), Decimal("45000"))
        self.assertEqual(self.claim.fraud_assessments.count(), 2)               # re-assessed after edit

    def test_edit_after_30_minutes_rejected_by_server(self):
        Claim.objects.filter(pk=self.claim.pk).update(submitted_at=timezone.now() - timedelta(minutes=31))
        r = self.c.patch(f"/api/claims/{self.claim.pk}/", {"requested_amount": "45000"}, format="json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["error"]["code"], "edit_window_closed")

    def test_edit_disabled_once_review_starts(self):
        services.start_review(make_staff(Role.ADJUSTER), self.claim)
        r = self.c.patch(f"/api/claims/{self.claim.pk}/", {"requested_amount": "45000"}, format="json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["error"]["code"], "claim_locked_review_started")
        self.assertNotIn("edit", self.c.get(f"/api/claims/{self.claim.pk}/").data["actions"])

    def test_other_customer_cannot_edit(self):
        r = self.client_for(make_customer()).patch(f"/api/claims/{self.claim.pk}/", {"requested_amount": "1"},
                                                   format="json")
        self.assertEqual(r.status_code, 404)


class ClaimDecisionTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.customer = make_customer()
        self.policy = make_policy(make_vehicle(self.customer), idv=200000)
        self.claim = submit_claim(self.policy, requested_amount=Decimal("60000"))
        self.adjuster = make_staff(Role.ADJUSTER)
        self.ac = self.client_for(self.adjuster)

    def review_and_verify(self):
        self.assertEqual(self.ac.post(f"/api/claims/{self.claim.pk}/start-review/").status_code, 200)
        for d in self.claim.documents.all():
            self.assertEqual(self.ac.post(f"/api/documents/{d.pk}/verify/").status_code, 200)

    def test_review_transition_and_invalid_transitions(self):
        r = self.ac.post(f"/api/claims/{self.claim.pk}/approve/", {"approved_amount": "1000"}, format="json")
        self.assertEqual(r.status_code, 409)                                      # cannot approve a Submitted claim
        r = self.ac.post(f"/api/claims/{self.claim.pk}/start-review/")
        self.assertEqual(r.data["status"], "UNDER_REVIEW")
        self.assertEqual(r.data["assigned_adjuster_name"], self.adjuster.full_name)
        self.assertEqual(self.ac.post(f"/api/claims/{self.claim.pk}/start-review/").status_code, 409)

    def test_documents_pending_and_resume(self):
        self.ac.post(f"/api/claims/{self.claim.pk}/start-review/")
        r = self.ac.post(f"/api/claims/{self.claim.pk}/request-documents/", {"note": "Upload the FIR copy"},
                         format="json")
        self.assertEqual(r.data["status"], "DOCUMENTS_PENDING")                   # REQ-CLM-007
        r = self.ac.post(f"/api/claims/{self.claim.pk}/start-review/")
        self.assertEqual(r.data["status"], "UNDER_REVIEW")

    def test_approval_requires_verified_documents(self):
        self.ac.post(f"/api/claims/{self.claim.pk}/start-review/")
        r = self.ac.post(f"/api/claims/{self.claim.pk}/approve/", {"approved_amount": "50000"}, format="json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["error"]["code"], "documents_not_verified")

    def test_approval_updates_policy_atomically(self):
        self.review_and_verify()
        with self.captureOnCommitCallbacks(execute=True):
            r = self.ac.post(f"/api/claims/{self.claim.pk}/approve/",
                             {"approved_amount": "55000", "notes": "As per estimate"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["status"], "APPROVED")
        self.assertEqual(Decimal(r.data["approved_amount"]), Decimal("55000"))
        self.assertEqual(Decimal(r.data["requested_amount"]), Decimal("60000"))   # REQ-CLM-008 never overwritten
        self.policy.refresh_from_db()
        self.assertEqual(self.policy.cumulative_approved_amount, Decimal("55000"))  # REQ-CLM-010
        self.assertEqual(self.policy.status, PolicyStatus.PARTIALLY_CLAIMED)
        self.assertTrue(any("approved" in m.subject for m in mail.outbox))

    def test_approval_rolls_back_completely_on_failure(self):
        self.review_and_verify()
        with mock.patch("apps.claims.services.notify", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                services.approve_claim(self.adjuster, self.claim, Decimal("50000"))
        self.claim.refresh_from_db()
        self.policy.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.UNDER_REVIEW)
        self.assertIsNone(self.claim.approved_amount)
        self.assertEqual(self.policy.cumulative_approved_amount, Decimal("0"))
        self.assertEqual(self.policy.status, PolicyStatus.ACTIVE)

    def test_approved_amount_limits(self):
        self.review_and_verify()
        r = self.ac.post(f"/api/claims/{self.claim.pk}/approve/", {"approved_amount": "60001"}, format="json")
        self.assertEqual(r.data["error"]["code"], "exceeds_requested")

    def test_rejection_requires_reason(self):
        self.ac.post(f"/api/claims/{self.claim.pk}/start-review/")
        self.assertEqual(self.ac.post(f"/api/claims/{self.claim.pk}/reject/", {"reason": ""},
                                      format="json").status_code, 400)
        with self.captureOnCommitCallbacks(execute=True):
            r = self.ac.post(f"/api/claims/{self.claim.pk}/reject/", {"reason": "Not covered"}, format="json")
        self.assertEqual(r.data["status"], "REJECTED")
        self.assertEqual(r.data["rejection_reason"], "Not covered")
        cust = self.client_for(self.customer).get(f"/api/claims/{self.claim.pk}/").data
        self.assertIn("appeal", cust["actions"])
        self.assertTrue(any("rejected" in m.subject for m in mail.outbox))

    def test_admin_and_siu_cannot_decide_claims(self):
        self.review_and_verify()
        for role in (Role.ADMIN, Role.SIU):
            c = self.client_for(make_staff(role))
            r = c.post(f"/api/claims/{self.claim.pk}/approve/", {"approved_amount": "100"}, format="json")
            self.assertEqual(r.status_code, 403, role)                            # REQ-SEC-011 / REQ-BR-020
            r = c.post(f"/api/claims/{self.claim.pk}/reject/", {"reason": "x"}, format="json")
            self.assertEqual(r.status_code, 403, role)

    def test_only_assigned_adjuster_can_act(self):
        self.ac.post(f"/api/claims/{self.claim.pk}/start-review/")
        other = self.client_for(make_staff(Role.ADJUSTER))
        r = other.post(f"/api/claims/{self.claim.pk}/reject/", {"reason": "x"}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data["error"]["code"], "not_assigned_adjuster")


class AppealTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.customer = make_customer()
        self.claim = submit_claim(make_policy(make_vehicle(self.customer)))
        self.adjuster = make_staff(Role.ADJUSTER)
        self.ac = self.client_for(self.adjuster)
        self.cc = self.client_for(self.customer)
        services.start_review(self.adjuster, self.claim)
        services.reject_claim(self.adjuster, self.claim, "Insufficient evidence")

    def appeal(self):
        return self.cc.post(f"/api/claims/{self.claim.pk}/appeal/", {
            "reason": "Attaching the police report and workshop estimate that prove the damage.",
            "document_types": ["OTHER"], "files": [upload_pdf("police.pdf")]}, format="multipart")

    def test_full_appeal_cycle_to_permanent_rejection(self):
        r = self.appeal()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(len(r.data["appeals"]), 1)
        self.assertEqual(self.appeal().status_code, 409)                         # one pending appeal at a time
        appeal_id = r.data["appeals"][0]["id"]
        r = self.ac.post(f"/api/appeals/{appeal_id}/decide/", {"accept": True, "note": "New evidence"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.UNDER_REVIEW)              # reopened
        self.assertEqual(self.claim.fraud_assessments.count(), 2)                 # re-assessed

        # second rejection: adjuster MUST decide on further appeals (REQ-BR-016)
        r = self.ac.post(f"/api/claims/{self.claim.pk}/reject/", {"reason": "Still unsupported"}, format="json")
        self.assertEqual(r.data["error"]["code"], "appeal_decision_required")
        r = self.ac.post(f"/api/claims/{self.claim.pk}/reject/",
                         {"reason": "Still unsupported", "allow_further_appeal": False}, format="json")
        self.assertEqual(r.data["status"], "PERMANENTLY_REJECTED")               # REQ-CLM-015
        r = self.appeal()
        self.assertEqual(r.status_code, 409)

    def test_declined_appeal_with_further_appeal_allowed(self):
        appeal_id = self.appeal().data["appeals"][0]["id"]
        r = self.ac.post(f"/api/appeals/{appeal_id}/decide/", {"accept": False, "note": "No"}, format="json")
        self.assertEqual(r.status_code, 400)                                       # decision on further appeal needed
        r = self.ac.post(f"/api/appeals/{appeal_id}/decide/",
                         {"accept": False, "note": "Not enough", "allow_further_appeal": True}, format="json")
        self.assertEqual(r.data["status"], "DECLINED")
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.REJECTED)
        self.assertEqual(self.appeal().status_code, 201)                           # one more appeal allowed

    def test_customer_can_accept_decision_and_close(self):
        r = self.cc.post(f"/api/claims/{self.claim.pk}/accept-decision/")
        self.assertEqual(r.data["status"], "CLOSED")

    def test_appeal_window(self):
        Claim.objects.filter(pk=self.claim.pk).update(decided_at=timezone.now() - timedelta(days=31))
        self.assertEqual(self.appeal().status_code, 409)
        self.assertEqual(services.close_unappealed_rejections(), 1)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.CLOSED)


class VerifyHelperTests(BaseAPITest):
    def test_verify_document_helper_marks_verified(self):
        customer = make_customer()
        claim = submit_claim(make_policy(make_vehicle(customer)))
        adj = make_staff(Role.ADJUSTER)
        services.start_review(adj, claim)
        doc = claim.documents.first()
        verify_document(adj, doc)
        doc.refresh_from_db()
        self.assertEqual(doc.status, "VERIFIED")
