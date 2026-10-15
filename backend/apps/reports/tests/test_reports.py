import csv
import io
from decimal import Decimal

from openpyxl import load_workbook

from apps.accounts.models import Role
from apps.audit.models import AuditAction, AuditLog
from apps.claims import services as claim_services
from apps.claims.models import Claim
from apps.core.tests.factories import (BaseAPITest, fraud_result, make_customer, make_policy, make_staff, make_vehicle,
                                       submit_claim)
from apps.documents.services import verify_document


class ReportingTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.admin = make_staff(Role.ADMIN)
        self.ac = self.client_for(self.admin)
        self.adjuster = make_staff(Role.ADJUSTER)
        cust = make_customer()
        self.p1 = make_policy(make_vehicle(cust), idv=300000)
        self.p2 = make_policy(make_vehicle(make_customer()), idv=300000)
        c1 = submit_claim(self.p1, requested_amount=Decimal("40000"))
        claim_services.start_review(self.adjuster, c1)
        for d in c1.documents.all():
            verify_document(self.adjuster, d)
        claim_services.approve_claim(self.adjuster, c1, Decimal("35000"))
        self.fraud.return_value = fraud_result(80, "HIGH")
        submit_claim(self.p2, claim_type="FIRE", requested_amount=Decimal("100000"))

    def test_admin_dashboard_matches_database(self):
        r = self.ac.get("/api/dashboard/")
        k = r.data["kpis"]
        self.assertEqual(k["total_claims"], Claim.objects.count())
        self.assertEqual(k["approved_claims"], 1)
        self.assertEqual(k["fraud_review_claims"], 1)
        self.assertEqual(k["high_risk_claims"], 1)
        self.assertEqual(k["total_requested_amount"], 140000.0)
        self.assertEqual(k["total_approved_amount"], 35000.0)
        by_status = {x["key"]: x["value"] for x in r.data["charts"]["claims_by_status"]}
        self.assertEqual(by_status["APPROVED"], 1)
        self.assertEqual(len(r.data["charts"]["claim_amount_trend"]), 12)

    def test_claims_report_filters(self):
        r = self.ac.get("/api/reports/?report=claims&claim_type=FIRE")
        self.assertEqual(r.data["total_rows"], 1)
        self.assertEqual(r.data["rows"][0][5], "Fire")
        r = self.ac.get("/api/reports/?report=claims&claim_status=APPROVED")
        self.assertEqual(r.data["summary"]["total_approved_amount"], 35000.0)
        self.assertEqual(r.data["summary"]["average_approved_amount"], 35000.0)
        r = self.ac.get("/api/reports/?report=fraud&risk_level=HIGH")
        self.assertEqual(r.data["summary"]["flagged_claims"], 1)
        self.assertEqual(r.data["summary"]["in_fraud_review"], 1)

    def test_all_report_types(self):
        for name in ("claims", "fraud", "policies", "vehicles", "customers"):
            r = self.ac.get(f"/api/reports/?report={name}")
            self.assertEqual(r.status_code, 200, name)
            self.assertTrue(r.data["columns"])
        r = self.ac.get("/api/reports/?report=policies")
        statuses = {x["key"]: x["value"] for x in r.data["summary"]["by_status"]}
        self.assertEqual(statuses["PARTIALLY_CLAIMED"], 1)

    def test_exports_respect_filters(self):
        r = self.ac.get("/api/reports/export/?report=claims&format=csv&claim_type=FIRE")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r["Content-Disposition"])
        rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
        data_rows = [row for row in rows if row and row[0].startswith("CLM-")]
        self.assertEqual(len(data_rows), 1)
        self.assertEqual(data_rows[0][5], "Fire")

        r = self.ac.get("/api/reports/export/?report=claims&format=xlsx")
        wb = load_workbook(io.BytesIO(r.content))
        claim_cells = [c.value for c in wb["Report"]["A"] if isinstance(c.value, str) and c.value.startswith("CLM-")]
        self.assertEqual(len(claim_cells), 2)

        r = self.ac.get("/api/reports/export/?report=fraud&format=pdf")
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r.content.startswith(b"%PDF"))
        self.assertTrue(AuditLog.objects.filter(action=AuditAction.REPORT_EXPORTED).exists())

    def test_reports_are_admin_only(self):
        for user in (make_customer(), self.adjuster, make_staff(Role.SIU)):
            c = self.client_for(user)
            self.assertEqual(c.get("/api/reports/").status_code, 403)                      # REQ-REP-011
            self.assertEqual(c.get("/api/reports/export/?format=csv").status_code, 403)
            self.assertEqual(c.get("/api/audit-logs/").status_code, 403)

    def test_audit_log_records_key_events(self):
        actions = set(AuditLog.objects.values_list("action", flat=True))
        for a in (AuditAction.CLAIM_SUBMITTED, AuditAction.CLAIM_REVIEW_STARTED, AuditAction.DOCUMENT_VERIFIED,
                  AuditAction.FRAUD_ASSESSED, AuditAction.CLAIM_APPROVED, AuditAction.CLAIM_FLAGGED):
            self.assertIn(a, actions)
        r = self.ac.get("/api/audit-logs/?action=CLAIM_APPROVED")
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["results"][0]["actor_email"], self.adjuster.email)

    def test_role_dashboards(self):
        for user in (make_customer(), self.adjuster, make_staff(Role.SIU)):
            self.assertEqual(self.client_for(user).get("/api/dashboard/").status_code, 200)
        siu = self.client_for(make_staff(Role.SIU)).get("/api/dashboard/").data
        self.assertEqual(siu["counts"]["open"], 1)
        adj = self.client_for(self.adjuster).get("/api/dashboard/").data
        self.assertEqual(adj["counts"]["fraud_review"], 1)
