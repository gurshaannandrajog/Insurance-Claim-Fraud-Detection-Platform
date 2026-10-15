"""
Load a realistic demo dataset by driving the REAL service layer (the same code the API uses), so every claim has
genuine status history, documents on disk, fraud assessments from the running Flask service, SIU records,
notifications and audit-log entries.

    python manage.py seed_demo --reset      # wipe the database + uploaded files, then seed

Requires the fraud service to be running (python fraud-service/app.py). Demo credentials are printed at the end
and documented in the README — they are never hard-coded in the frontend.
"""
import shutil
from datetime import time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db.models import F
from django.test.utils import override_settings
from django.utils import timezone

from apps.accounts.models import CustomerProfile, EmployeeProfile, Role, User
from apps.audit.models import AuditLog
from apps.claims import services as claims
from apps.claims.models import Claim, ClaimStatusHistory
from apps.core.numbering import assign_number, temporary_number
from apps.core.sample_files import upload_jpeg, upload_pdf
from apps.documents.models import ClaimDocument
from apps.documents.services import reject_document, upload_document, verify_document
from apps.fraud import client as fraud_client
from apps.fraud.models import FraudAssessment
from apps.investigations import services as siu
from apps.notifications.models import Notification
from apps.policies.models import Policy, PolicyPlan, PolicyRequest, PolicyStatus
from apps.policies.services import calculate_premium, expire_due_policies
from apps.vehicles.models import Vehicle

DEMO_PASSWORD = "Demo@1234"


class Command(BaseCommand):
    help = "Seed realistic demo data (use --reset to wipe first)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Flush the database and uploaded files first")
        parser.add_argument("--allow-without-fraud", action="store_true",
                            help="Seed even if the fraud service is down (assessments will be recorded as FAILED)")

    def handle(self, *args, **opts):
        if not fraud_client.health() and not opts["allow_without_fraud"]:
            raise CommandError(f"Fraud service is not reachable at {settings.FRAUD_SERVICE_URL}. Start it with "
                               "`python fraud-service/app.py` (or pass --allow-without-fraud).")
        if opts["reset"]:
            self.stdout.write("Flushing database and uploaded documents…")
            call_command("flush", interactive=False, verbosity=0)
            shutil.rmtree(settings.MEDIA_ROOT / "claim_documents", ignore_errors=True)
        elif User.objects.exists():
            raise CommandError("Database is not empty. Re-run with --reset to wipe and reseed.")
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            self.seed()
        self.stdout.write(self.style.SUCCESS("\nDemo data loaded. All accounts use the password: " + DEMO_PASSWORD))
        for email, role in [("admin@claims.local", "Administrator"), ("adjuster@claims.local", "Claim Adjuster"),
                            ("adjuster2@claims.local", "Claim Adjuster"), ("siu@claims.local", "SIU Investigator"),
                            ("customer@claims.local", "Customer (Rohan Mehta)"),
                            ("meera.joshi@example.com", "Customer with a pending appeal")]:
            self.stdout.write(f"  {role:<32} {email}")

    # ------------------------------------------------------------------------------------------- helpers
    def today(self):
        return timezone.localdate()

    def staff(self, email, name, role, emp_id, dept):
        u = User.objects.create_user(email=email, password=DEMO_PASSWORD, full_name=name, role=role,
                                     is_email_verified=True, email_verified_at=timezone.now())
        EmployeeProfile.objects.create(user=u, employee_id=emp_id, department=dept, phone="+919800000000")
        return u

    def customer(self, email, name, phone, dob, city, joined_days_ago):
        u = User.objects.create_user(email=email, password=DEMO_PASSWORD, full_name=name, role=Role.CUSTOMER,
                                     is_email_verified=True, email_verified_at=timezone.now(),
                                     date_joined=timezone.now() - timedelta(days=joined_days_ago))
        CustomerProfile.objects.create(user=u, phone=phone, date_of_birth=dob, address_line="12, Sunrise Apartments",
                                       city=city, state="Maharashtra", postal_code="400058")
        return u.customer_profile

    def vehicle(self, cust, reg, make, model, vtype, year, color, days_ago=300):
        bought = self.today() - timedelta(days=min(days_ago + 200, (self.today().year - year) * 365 + 30))
        return Vehicle.objects.create(
            customer=cust, registration_number=reg, make=make, model=model, vehicle_type=vtype,
            manufacturing_year=year, registration_date=bought, purchase_date=bought,
            engine_number=f"ENG{reg[-6:]}{year}", chassis_number=f"MA3{reg}{year}"[:17], color=color,
            owner_name=cust.user.full_name, owner_phone=cust.phone)

    def policy(self, vehicle, plan, idv, start_days_ago, admin):
        start = self.today() - timedelta(days=start_days_ago)
        pr = PolicyRequest.objects.create(customer=vehicle.customer, vehicle=vehicle, plan=plan, requested_idv=idv,
                                          status="APPROVED", reviewed_by=admin, reviewed_at=timezone.now())
        p = Policy.objects.create(
            policy_number=temporary_number(), customer=vehicle.customer, vehicle=vehicle, request=pr, plan=plan,
            plan_name=plan.name, premium_rate_percent=plan.premium_rate_percent, start_date=start,
            end_date=start + timedelta(days=364), idv=Decimal(idv),
            premium_amount=calculate_premium(idv, plan.premium_rate_percent, plan.term_months),
            status=PolicyStatus.ACTIVE, created_by=admin)
        assign_number(p, "POL", "policy_number")
        return p

    def docs(self, ctype, extra=True):
        files = [("KYC", upload_pdf("aadhaar_kyc.pdf", "KYC — Aadhaar / PAN")),
                 ("ADDRESS_PROOF", upload_pdf("address_proof.pdf", "Address proof — electricity bill")),
                 ("VEHICLE_REGISTRATION", upload_pdf("rc_book.pdf", "Vehicle Registration Certificate"))]
        if extra:
            files.append({"ACCIDENT": ("ACCIDENT_PHOTO", upload_jpeg("front_bumper.jpg", "Accident damage")),
                          "FIRE": ("FIRE_EVIDENCE", upload_jpeg("fire_damage.jpg", "Fire damage", (120, 50, 30))),
                          "THIRD_PARTY": ("THIRD_PARTY_DOCUMENT", upload_pdf("fir_copy.pdf", "Third-party FIR copy"))
                          }[ctype])
        return files

    def submit(self, cust, policy, ctype, amount, days_ago=2, hour=15, desc=None, extra_docs=True, location=None):
        data = {"claim_type": ctype, "incident_date": self.today() - timedelta(days=days_ago),
                "incident_time": time(hour, 20), "requested_amount": Decimal(amount),
                "incident_location": location or "Western Express Highway, Andheri East, Mumbai",
                "description": desc or ("Vehicle was hit from the side at a signal by a delivery van. Front left door "
                                        "and fender dented, mirror broken. Photographs taken at the spot.")}
        return claims.submit_claim(cust.user, vehicle_id=policy.vehicle_id, policy_id=policy.pk, data=data,
                                   documents=self.docs(ctype, extra_docs))

    def verify_all(self, adjuster, claim):
        for d in ClaimDocument.objects.filter(claim=claim, is_current=True, status="PENDING"):
            verify_document(adjuster, d)

    def backdate(self, claim, days):
        """Spread historical claims over past months so dashboards show real trends."""
        delta = timedelta(days=days)
        Claim.objects.filter(pk=claim.pk).update(
            incident_date=F("incident_date") - delta, submitted_at=F("submitted_at") - delta,
            review_started_at=F("review_started_at") - delta, decided_at=F("decided_at") - delta,
            closed_at=F("closed_at") - delta)
        ClaimStatusHistory.objects.filter(claim=claim).update(created_at=F("created_at") - delta)
        ClaimDocument.objects.filter(claim=claim).update(uploaded_at=F("uploaded_at") - delta)
        FraudAssessment.objects.filter(claim=claim).update(created_at=F("created_at") - delta)
        Notification.objects.filter(claim=claim).update(created_at=F("created_at") - delta)
        claim.appeals.update(created_at=F("created_at") - delta)
        AuditLog.objects.filter(entity_type="claim", entity_id=str(claim.pk)).update(created_at=F("created_at") - delta)

    # ------------------------------------------------------------------------------------------- data
    def seed(self):
        out = self.stdout.write
        out("Creating staff and plans…")
        admin = self.staff("admin@claims.local", "Anita Desai", Role.ADMIN, "EMP-1001", "Operations")
        adj = self.staff("adjuster@claims.local", "Priya Sharma", Role.ADJUSTER, "EMP-2001", "Motor Claims")
        adj2 = self.staff("adjuster2@claims.local", "Karan Malhotra", Role.ADJUSTER, "EMP-2002", "Motor Claims")
        inv = self.staff("siu@claims.local", "Vikram Rao", Role.SIU, "EMP-3001", "Special Investigation Unit")

        std = PolicyPlan.objects.create(code="COMP-STD", name="Comprehensive Standard", premium_rate_percent="2.80",
                                        term_months=12, min_idv=50000, max_idv=5000000,
                                        description="Own damage + third-party liability. Standard deductible.")
        prem = PolicyPlan.objects.create(code="COMP-ZD", name="Comprehensive Zero Depreciation",
                                         premium_rate_percent="3.60", term_months=12, min_idv=100000, max_idv=8000000,
                                         description="Comprehensive cover without depreciation deduction on parts.")
        PolicyPlan.objects.create(code="TP-ONLY", name="Third-Party Liability", premium_rate_percent="1.20",
                                  term_months=12, min_idv=20000, max_idv=2000000,
                                  description="Mandatory third-party cover.")

        out("Creating customers, vehicles and policies…")
        rohan = self.customer("customer@claims.local", "Rohan Mehta", "+919820011223", "1992-04-18", "Mumbai", 290)
        neha = self.customer("neha.kapoor@example.com", "Neha Kapoor", "+919820044556", "1988-11-02", "Pune", 25)
        arjun = self.customer("arjun.nair@example.com", "Arjun Nair", "+919820077889", "1985-07-23", "Thane", 240)
        fatima = self.customer("fatima.shaikh@example.com", "Fatima Shaikh", "+919821122334", "1995-01-30",
                               "Navi Mumbai", 180)
        sanjay = self.customer("sanjay.iyer@example.com", "Sanjay Iyer", "+919821155667", "1979-09-12", "Mumbai", 320)
        meera = self.customer("meera.joshi@example.com", "Meera Joshi", "+919821188990", "1990-03-08", "Nashik", 150)
        rahul = self.customer("rahul.verma@example.com", "Rahul Verma", "+919822233445", "1983-12-19", "Mumbai", 95)

        v_swift = self.vehicle(rohan, "MH02AB1234", "Maruti Suzuki", "Swift VXi", "CAR", 2021, "Pearl White")
        v_activa = self.vehicle(rohan, "MH02CD5678", "Honda", "Activa 6G", "SCOOTER", 2022, "Matte Grey")
        v_creta = self.vehicle(rohan, "MH01EF9012", "Hyundai", "Creta SX", "SUV", 2024, "Abyss Black")
        v_city = self.vehicle(rohan, "MH04GH3456", "Honda", "City ZX", "CAR", 2017, "Silver")
        v_nexon = self.vehicle(neha, "MH12JK7890", "Tata", "Nexon XZ", "SUV", 2014, "Flame Red")
        v_xuv = self.vehicle(arjun, "MH04LM2468", "Mahindra", "XUV700", "SUV", 2023, "Midnight Black")
        v_baleno = self.vehicle(fatima, "MH43NP1357", "Maruti Suzuki", "Baleno Alpha", "CAR", 2022, "Nexa Blue")
        v_pulsar = self.vehicle(sanjay, "MH02QR8642", "Bajaj", "Pulsar NS200", "MOTORCYCLE", 2020, "Racing Red")
        v_i20 = self.vehicle(meera, "MH15ST9753", "Hyundai", "i20 Asta", "CAR", 2021, "Titan Grey")
        v_seltos = self.vehicle(rahul, "MH02UV1122", "Kia", "Seltos HTX", "SUV", 2023, "Gravity Grey")
        v_ertiga = self.vehicle(rahul, "MH03WX3344", "Maruti Suzuki", "Ertiga ZXi", "CAR", 2019, "Magma Grey")
        self.vehicle(arjun, "MH04YZ5566", "Royal Enfield", "Classic 350", "MOTORCYCLE", 2022, "Stealth Black")

        p_swift = self.policy(v_swift, std, 550000, 330, admin)
        p_activa = self.policy(v_activa, std, 75000, 300, admin)
        self.policy(v_city, std, 380000, 420, admin)             # will expire
        p_nexon = self.policy(v_nexon, std, 420000, 10, admin)            # brand-new policy
        p_xuv = self.policy(v_xuv, prem, 2100000, 320, admin)
        p_baleno = self.policy(v_baleno, std, 690000, 200, admin)
        p_pulsar = self.policy(v_pulsar, std, 80000, 330, admin)
        p_i20 = self.policy(v_i20, prem, 640000, 310, admin)
        p_seltos = self.policy(v_seltos, prem, 1450000, 90, admin)
        p_ertiga = self.policy(v_ertiga, std, 720000, 330, admin)
        expire_due_policies()                                             # p_city → Expired

        from apps.policies.services import cancel_policy, create_policy_request
        cancel_policy(admin, p_seltos, "Customer sold the vehicle and requested cancellation.")
        create_policy_request(rohan, vehicle=v_creta, plan=prem, requested_idv=Decimal("1650000"),
                              notes="New car, please include zero depreciation.")

        out("Submitting and processing claims (this calls the fraud service)…")
        # 1. Approved accident claim → Rohan's Swift becomes Partially Claimed
        c1 = self.submit(rohan, p_swift, "ACCIDENT", 52000)
        claims.start_review(adj, c1)
        upload_document(adj, c1, upload_pdf("garage_estimate.pdf", "Repair estimate — Sai Motors",
                                            ["Door panel: 18,500", "Fender: 9,200", "Mirror: 4,800",
                                             "Paint & labour: 15,500"]), "REPAIR_ESTIMATE")
        self.verify_all(adj, c1)
        claims.approve_claim(adj, c1, Decimal("48000"), "Approved per garage estimate; mirror replaced with OEM part.")
        self.backdate(c1, 210)

        # 2. Sanjay — total-loss style approval → policy Claimed
        c2 = self.submit(sanjay, p_pulsar, "ACCIDENT", 80000, desc="Motorcycle skidded on wet road near Sion "
                         "flyover and was hit by a bus. Frame bent, engine casing cracked; surveyor declared total loss.")
        claims.start_review(adj2, c2)
        self.verify_all(adj2, c2)
        claims.approve_claim(adj2, c2, Decimal("80000"), "Total loss confirmed by surveyor.")
        self.backdate(c2, 150)

        # 3. Rohan's Activa — rejected, customer can still appeal
        c3 = self.submit(rohan, p_activa, "THIRD_PARTY", 38000, desc="My scooter brushed a parked car while "
                         "reversing in a society compound. The car owner demanded payment for scratches.")
        claims.start_review(adj, c3)
        self.verify_all(adj, c3)
        claims.reject_claim(adj, c3, "Third-party damage not covered: the incident occurred on private premises and "
                                     "no police report or third-party claim was filed.")
        self.backdate(c3, 6)

        # 4. Meera — rejected, then appealed (pending appeal for the adjuster demo)
        c4 = self.submit(meera, p_i20, "ACCIDENT", 125000, desc="Car hit a divider at night to avoid a stray animal "
                         "on the Mumbai–Nashik highway. Front bumper, radiator and headlamp damaged.")
        claims.start_review(adj, c4)
        self.verify_all(adj, c4)
        claims.reject_claim(adj, c4, "Photographs do not show radiator damage; repair estimate unsupported.")
        claims.submit_appeal(meera.user, c4, "The radiator damage is internal and visible only after dismantling. "
                             "Attaching the workshop's inspection report and additional photographs.",
                             [("DAMAGE_PHOTO", upload_jpeg("radiator.jpg", "Radiator after dismantling")),
                              ("OTHER", upload_pdf("inspection_report.pdf", "Workshop inspection report"))])
        self.backdate(c4, 4)

        # 5. Arjun — under review, documents pending (one rejected document)
        c5 = self.submit(arjun, p_xuv, "ACCIDENT", 210000, desc="Rear-ended by a truck in slow traffic on the "
                         "Eastern Express Highway. Tailgate, rear bumper and parking sensors damaged.")
        claims.start_review(adj, c5)
        addr = ClaimDocument.objects.get(claim=c5, document_type="ADDRESS_PROOF")
        reject_document(adj, addr, "Address proof is older than 3 months; upload a recent utility bill.")
        claims.request_documents(adj, c5, "Please upload a recent address proof (not older than 3 months) and the "
                                          "repair estimate from an authorised workshop.")
        self.backdate(c5, 3)

        # 6. Fatima — under review with all documents verified, ready for an approve/reject decision
        c6 = self.submit(fatima, p_baleno, "FIRE", 160000, hour=21, desc="Short circuit under the dashboard while "
                         "parked outside home; the fire was put out by neighbours. Dashboard wiring and interior burnt.")
        claims.start_review(adj, c6)
        self.verify_all(adj, c6)
        self.backdate(c6, 1)

        # 7. Rahul — escalated to SIU, found fraudulent, rejected, appeal declined → permanently rejected
        c7 = self.submit(rahul, p_ertiga, "ACCIDENT", 410000, hour=1, desc="Car fell into a ditch at night.")
        claims.start_review(adj2, c7)
        claims.escalate_to_siu(adj2, c7, "Damage photographs look inconsistent with the described ditch accident; "
                                         "request field verification.")
        investigation = c7.investigations.first()
        siu.start_investigation(inv, investigation)
        siu.save_progress(inv, investigation, note="Visited the reported location — no ditch on that stretch; road "
                                                   "under construction barricades since March.")
        siu.complete_investigation(inv, investigation, recommendation="FRAUDULENT",
                                   findings="Location does not match the account. Workshop records show the same "
                                            "damage was repaired under a cash job two months earlier.",
                                   evidence_notes="Site photos and workshop invoice #WK-2231 obtained.")
        self.verify_all(adj2, c7)
        claims.reject_claim(adj2, c7, "SIU investigation established that the damage pre-dates the policy incident.")
        claims.submit_appeal(rahul.user, c7, "I disagree with the investigation; the earlier repair was for a "
                             "different panel. Please review again.", [])
        claims.decide_appeal(adj2, c7.appeals.first(), accept=False, allow_further_appeal=False,
                             note="Appeal reviewed with SIU evidence; no new information provided.")
        self.backdate(c7, 60)

        # 8. Neha — brand-new policy, near-total fire claim at 2 am on an old vehicle → HIGH risk → Fraud Review
        self.submit(neha, p_nexon, "FIRE", 395000, days_ago=1, hour=2, extra_docs=False,
                    desc="Vehicle caught fire at night in the parking lot.", location="Hinjewadi Phase 2, Pune")

        # 9. Rohan — a fresh claim waiting in the review queue
        self.submit(rohan, p_swift, "ACCIDENT", 18500, days_ago=1, desc="Minor collision with an auto-rickshaw at "
                    "Andheri station road; rear bumper cracked and tail-lamp broken.")

        Claim.objects.filter(pk__in=[c.pk for c in (c1, c2)]).update(updated_at=F("submitted_at"))
        out(f"  {Claim.objects.count()} claims, {FraudAssessment.objects.count()} fraud assessments, "
            f"{Notification.objects.count()} notifications, {AuditLog.objects.count()} audit entries")
