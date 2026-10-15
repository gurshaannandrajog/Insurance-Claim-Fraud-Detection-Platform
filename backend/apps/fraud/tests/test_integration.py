"""
Integration test: Django → (HTTP) → real Flask fraud service → scoring engine, without a network socket.
`requests.post` is routed into the Flask app's test client, so the actual API, validation and rules run.
"""
import sys
from datetime import time, timedelta
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.claims.models import ClaimStatus
from apps.core.tests.factories import make_customer, make_policy, make_vehicle, submit_claim

FRAUD_DIR = Path(settings.BASE_DIR).parent / "fraud-service"


class FakeResponse:
    def __init__(self, flask_response):
        self.status_code = flask_response.status_code
        self._json = flask_response.get_json()

    def json(self):
        return self._json


@override_settings(FRAUD_SERVICE_API_KEY="integration-key")
class DjangoFlaskIntegrationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        sys.path.insert(0, str(FRAUD_DIR))
        from fraud_service import create_app
        cls.flask = create_app({"API_KEY": "integration-key", "TESTING": True}).test_client()

    def route(self, url, json=None, headers=None, timeout=None):
        path = url.split("5001", 1)[-1] if "5001" in url else "/api/v1/assess"
        return FakeResponse(self.flask.post(path, json=json, headers=headers))

    def test_real_engine_scores_a_clean_claim_low(self):
        customer = make_customer()
        policy = make_policy(make_vehicle(customer), idv=600000)
        with mock.patch("apps.fraud.client.requests.post", side_effect=self.route):
            claim = submit_claim(policy, requested_amount=Decimal("30000"))
        a = claim.fraud_assessments.get()
        self.assertEqual(a.status, "COMPLETED")
        self.assertEqual(a.engine, "rules-v1")
        self.assertEqual(claim.current_risk_level, "LOW")
        self.assertEqual(claim.status, ClaimStatus.SUBMITTED)

    def test_real_engine_flags_a_suspicious_claim(self):
        customer = make_customer()
        vehicle = make_vehicle(customer, year=2012)
        policy = make_policy(vehicle, idv=300000, start=timezone.localdate() - timedelta(days=6))
        with mock.patch("apps.fraud.client.requests.post", side_effect=self.route):
            claim = submit_claim(policy, claim_type="FIRE", requested_amount=Decimal("290000"),
                                 incident_date=timezone.localdate() - timedelta(days=1), incident_time=time(2, 30))
        a = claim.fraud_assessments.get()
        codes = set(a.indicators.values_list("code", flat=True))
        self.assertGreaterEqual(a.risk_score, 60)
        self.assertTrue({"AMOUNT_NEAR_IDV", "VERY_NEW_POLICY", "NIGHT_INCIDENT", "FIRE_OLD_VEHICLE"} <= codes, codes)
        self.assertEqual(claim.status, ClaimStatus.FRAUD_REVIEW)

    def test_wrong_api_key_is_recorded_as_failure(self):
        customer = make_customer()
        policy = make_policy(make_vehicle(customer))
        with override_settings(FRAUD_SERVICE_API_KEY="wrong"), \
                mock.patch("apps.fraud.client.requests.post", side_effect=self.route):
            claim = submit_claim(policy)
        self.assertEqual(claim.fraud_assessments.get().status, "FAILED")
