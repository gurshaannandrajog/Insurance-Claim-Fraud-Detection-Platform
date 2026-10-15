from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import Role
from apps.claims import services as claim_services
from apps.core.sample_files import upload_jpeg, upload_pdf
from apps.core.tests.factories import BaseAPITest, make_customer, make_policy, make_staff, make_vehicle, submit_claim
from apps.documents.models import ClaimDocument
from apps.notifications.models import Notification


class DocumentTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.customer = make_customer()
        self.claim = submit_claim(make_policy(make_vehicle(self.customer)))
        self.cc = self.client_for(self.customer)
        self.adjuster = make_staff(Role.ADJUSTER)
        self.ac = self.client_for(self.adjuster)

    def upload(self, client, f, doc_type="DAMAGE_PHOTO", **extra):
        return client.post(f"/api/claims/{self.claim.pk}/documents/", {"document_type": doc_type, "file": f, **extra},
                           format="multipart")

    def test_valid_pdf_and_jpeg(self):
        self.assertEqual(self.upload(self.cc, upload_jpeg("dent.jpeg")).status_code, 201)
        r = self.upload(self.cc, upload_pdf("estimate.pdf"), "OTHER")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["status"], "PENDING")
        doc = ClaimDocument.objects.get(pk=r.data["id"])
        self.assertNotIn("estimate", doc.file.name)                               # random storage name

    def test_invalid_extension(self):
        r = self.upload(self.cc, SimpleUploadedFile("virus.exe", b"MZ\x90\x00"))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["error"]["code"], "unsupported_file_type")
        r = self.upload(self.cc, SimpleUploadedFile("photo.png", b"\x89PNG\r\n"))
        self.assertEqual(r.data["error"]["code"], "unsupported_file_type")

    def test_content_must_match_extension(self):
        r = self.upload(self.cc, SimpleUploadedFile("fake.pdf", b"MZ this is an executable"))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["error"]["code"], "file_content_mismatch")
        r = self.upload(self.cc, SimpleUploadedFile("fake.jpg", b"%PDF-1.4 not a jpeg"))
        self.assertEqual(r.data["error"]["code"], "file_content_mismatch")

    def test_file_larger_than_10mb_rejected(self):
        big = SimpleUploadedFile("big.pdf", b"%PDF-1.4\n" + b"0" * (10 * 1024 * 1024))
        r = self.upload(self.cc, big)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["error"]["code"], "file_too_large")
        exactly = SimpleUploadedFile("max.pdf", b"%PDF-1.4\n" + b"0" * (10 * 1024 * 1024 - 9))
        self.assertEqual(self.upload(self.cc, exactly).status_code, 201)

    def test_verify_and_reject_with_reason(self):
        claim_services.start_review(self.adjuster, self.claim)
        doc, doc2 = self.claim.documents.all()[:2]
        self.assertEqual(self.ac.post(f"/api/documents/{doc.pk}/verify/").data["status"], "VERIFIED")
        r = self.ac.post(f"/api/documents/{doc2.pk}/reject/", {"reason": ""}, format="json")
        self.assertEqual(r.status_code, 400)                                       # REQ-DOC-009
        with self.captureOnCommitCallbacks(execute=True):
            r = self.ac.post(f"/api/documents/{doc2.pk}/reject/", {"reason": "Blurred scan"}, format="json")
        self.assertEqual(r.data["status"], "REJECTED")
        self.assertEqual(r.data["rejection_reason"], "Blurred scan")
        n = Notification.objects.get(recipient=self.customer, type="DOCUMENT_REJECTED")    # REQ-DOC-010 in-app
        self.assertIn("Blurred scan", n.message)
        self.assertTrue(any("Document rejected" in m.subject for m in mail.outbox))        # … and email

    def test_customer_cannot_verify(self):
        claim_services.start_review(self.adjuster, self.claim)
        doc = self.claim.documents.first()
        self.assertEqual(self.cc.post(f"/api/documents/{doc.pk}/verify/").status_code, 403)

    def test_replacement_keeps_history(self):
        claim_services.start_review(self.adjuster, self.claim)
        doc = self.claim.documents.get(document_type="KYC")
        self.ac.post(f"/api/documents/{doc.pk}/reject/", {"reason": "Expired ID"}, format="json")
        # customer may replace only a rejected document, with the same type
        r = self.upload(self.cc, upload_pdf("kyc2.pdf"), "KYC", replaces=doc.pk)
        self.assertEqual(r.status_code, 201, r.data)
        doc.refresh_from_db()
        self.assertFalse(doc.is_current)
        self.assertEqual(doc.replaced_by.pk, r.data["id"])
        # adjuster replaces an incorrect document (REQ-DOC-011)
        addr = self.claim.documents.get(document_type="ADDRESS_PROOF")
        r = self.upload(self.ac, upload_pdf("addr-correct.pdf"), "ADDRESS_PROOF", replaces=addr.pk)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(ClaimDocument.objects.filter(claim=self.claim).count(), 6)        # nothing deleted

    def test_customer_cannot_replace_unrejected_doc(self):
        doc = self.claim.documents.get(document_type="KYC")
        r = self.upload(self.cc, upload_pdf("kyc2.pdf"), "KYC", replaces=doc.pk)
        self.assertEqual(r.status_code, 409)

    def test_download_access_control(self):
        doc = self.claim.documents.first()
        url = f"/api/documents/{doc.pk}/download/"
        r = self.cc.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(b"".join(r.streaming_content).startswith(b"%PDF"))
        self.assertEqual(self.client_for(make_customer()).get(url).status_code, 404)   # REQ-DOC-012 (IDOR)
        self.assertEqual(self.client_for(make_staff(Role.ADMIN)).get(url).status_code, 404)
        self.assertEqual(self.client_for(make_staff(Role.SIU)).get(url).status_code, 404)  # not a flagged claim
        self.assertEqual(self.ac.get(url).status_code, 200)
        self.assertEqual(self.client.get(url).status_code, 401)                     # anonymous
