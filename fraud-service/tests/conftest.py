import copy

import pytest

from fraud_service import create_app

BASE = {
    "claim": {"claim_number": "CLM-T", "claim_type": "ACCIDENT", "requested_amount": 40000.0,
              "incident_date": "2026-06-10", "incident_time": "14:30", "submitted_at": "2026-06-11T10:00:00+05:30",
              "incident_location": "Andheri, Mumbai", "description_length": 180},
    "policy": {"start_date": "2026-01-01", "end_date": "2026-12-31", "idv": 600000.0,
               "cumulative_approved_amount": 0.0},
    "vehicle": {"manufacturing_year": 2021, "purchase_date": "2021-03-01", "vehicle_type": "CAR"},
    "history": {"customer_claims_last_12_months": 0, "vehicle_claims_last_12_months": 0,
                "customer_rejected_claims": 0, "similar_claims": []},
    "documents": {"types": ["KYC", "ADDRESS_PROOF", "VEHICLE_REGISTRATION", "ACCIDENT_PHOTO"], "count": 4,
                  "rejected_count": 0, "reused_in_other_claims": 0},
}


@pytest.fixture
def payload():
    return copy.deepcopy(BASE)


@pytest.fixture
def client():
    app = create_app({"API_KEY": "test-key", "TESTING": True})
    return app.test_client()


@pytest.fixture
def auth():
    return {"X-API-Key": "test-key"}
