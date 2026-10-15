"""Shared test helpers. The fraud service is mocked by default (FraudMockMixin) so unit tests are deterministic;
`apps/fraud/tests/test_integration.py` runs the real Flask scoring engine."""
from datetime import date, time, timedelta
from decimal import Decimal
from unittest import mock

from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import CustomerProfile, EmployeeProfile, Role, User
from apps.claims import services as claim_services
from apps.core.numbering import assign_number, temporary_number
from apps.core.sample_files import upload_jpeg, upload_pdf
from apps.policies.models import Policy, PolicyPlan, PolicyStatus
from apps.policies.services import calculate_premium
from apps.vehicles.models import Vehicle

PASSWORD = "Str0ng!Pass"
_counter = {"n": 0}


def _n():
    _counter["n"] += 1
    return _counter["n"]


def make_customer(email=None, name="Test Customer"):
    n = _n()
    user = User.objects.create_user(email=email or f"cust{n}@example.com", password=PASSWORD, full_name=name,
                                    role=Role.CUSTOMER, is_email_verified=True, email_verified_at=timezone.now())
    CustomerProfile.objects.create(user=user, phone="+919800000001", date_of_birth=date(1990, 1, 1),
                                   address_line="1 Test Street", city="Mumbai", state="MH", postal_code="400058")
    return user


def make_staff(role, email=None, name=None):
    n = _n()
    user = User.objects.create_user(email=email or f"{role.lower()}{n}@claims.local", password=PASSWORD,
                                    full_name=name or f"{role.title()} {n}", role=role, is_email_verified=True,
                                    email_verified_at=timezone.now())
    EmployeeProfile.objects.create(user=user, employee_id=f"EMP-{n:04d}")
    return user


def make_plan(**kw):
    defaults = dict(code=f"PLAN{_n()}", name="Standard", premium_rate_percent=Decimal("3.00"), term_months=12,
                    min_idv=Decimal("10000"), max_idv=Decimal("5000000"))
    defaults.update(kw)
    return PolicyPlan.objects.create(**defaults)


def make_vehicle(customer_user, reg=None, year=2021):
    n = _n()
    return Vehicle.objects.create(
        customer=customer_user.customer_profile, registration_number=reg or f"MH01TS{n:04d}", make="Maruti",
        model="Swift", vehicle_type="CAR", manufacturing_year=year, registration_date=date(year, 6, 1),
        purchase_date=date(year, 6, 1), engine_number=f"ENG{n:06d}", chassis_number=f"CH{n:08d}", color="White",
        owner_name=customer_user.full_name)


def make_policy(vehicle, admin=None, idv=500000, start=None, days=364, status=PolicyStatus.ACTIVE, plan=None):
    plan = plan or make_plan()
    admin = admin or make_staff(Role.ADMIN)
    start = start or (timezone.localdate() - timedelta(days=100))
    p = Policy.objects.create(policy_number=temporary_number(), customer=vehicle.customer, vehicle=vehicle, plan=plan,
                              plan_name=plan.name, premium_rate_percent=plan.premium_rate_percent, start_date=start,
                              end_date=start + timedelta(days=days), idv=Decimal(idv),
                              premium_amount=calculate_premium(idv, plan.premium_rate_percent, 12), status=status,
                              created_by=admin)
    assign_number(p, "POL", "policy_number")
    return p


def mandatory_docs(extra_type=None):
    docs = [("KYC", upload_pdf("kyc.pdf")), ("ADDRESS_PROOF", upload_pdf("address.pdf")),
            ("VEHICLE_REGISTRATION", upload_pdf("rc.pdf"))]
    if extra_type == "ACCIDENT":
        docs.append(("ACCIDENT_PHOTO", upload_jpeg("photo.jpg")))
    elif extra_type == "FIRE":
        docs.append(("FIRE_EVIDENCE", upload_jpeg("fire.jpg")))
    elif extra_type == "THIRD_PARTY":
        docs.append(("THIRD_PARTY_DOCUMENT", upload_pdf("tp.pdf")))
    return docs


def claim_data(**kw):
    d = dict(claim_type="ACCIDENT", incident_date=timezone.localdate() - timedelta(days=3), incident_time=time(14, 0),
             incident_location="Andheri, Mumbai", requested_amount=Decimal("50000"),
             description="Rear-ended at a traffic signal; bumper and tail lamp damaged.")
    d.update(kw)
    return d


def submit_claim(policy, **kw):
    user = policy.customer.user
    data = claim_data(**kw)
    return claim_services.submit_claim(user, vehicle_id=policy.vehicle_id, policy_id=policy.pk, data=data,
                                       documents=mandatory_docs(data["claim_type"]))


def fraud_result(score=10, level="LOW"):
    return ({"risk_score": score, "risk_level": level, "flagged": level == "HIGH",
             "factors": [{"code": "TEST", "category": "Test", "description": "Test factor", "weight": score}],
             "engine": "test"}, 5)


class FraudMockMixin:
    """Patches the HTTP call to the Flask service. Set self.fraud.return_value / side_effect per test."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch("apps.fraud.client.assess", return_value=fraud_result())
        self.fraud = patcher.start()
        self.addCleanup(patcher.stop)


class BaseAPITest(FraudMockMixin, APITestCase):
    def client_for(self, user):
        c = APIClient()
        c.force_login(user)
        return c
