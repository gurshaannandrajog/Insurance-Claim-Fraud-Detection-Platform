"""Strict input validation — the service rejects malformed payloads with 400 instead of guessing."""
from datetime import date, datetime

SCHEMA = {
    "claim": {"claim_type": str, "requested_amount": (int, float), "incident_date": "date", "incident_time": "time",
              "submitted_at": "datetime"},
    "policy": {"start_date": "date", "end_date": "date", "idv": (int, float)},
    "vehicle": {"manufacturing_year": int, "purchase_date": "date"},
    "history": {"customer_claims_last_12_months": int, "vehicle_claims_last_12_months": int,
                "customer_rejected_claims": int, "similar_claims": list},
    "documents": {"types": list, "count": int},
}
CLAIM_TYPES = {"ACCIDENT", "FIRE", "THIRD_PARTY"}


class PayloadError(ValueError):
    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


def _check(kind, value):
    if kind == "date":
        date.fromisoformat(str(value)[:10])
        return True
    if kind == "time":
        h, m = str(value).split(":")[:2]
        return 0 <= int(h) < 24 and 0 <= int(m) < 60
    if kind == "datetime":
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return True
    if kind is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, kind) and not isinstance(value, bool)


def validate(payload):
    errors = []
    if not isinstance(payload, dict):
        raise PayloadError(["Body must be a JSON object"])
    for section, fields in SCHEMA.items():
        block = payload.get(section)
        if not isinstance(block, dict):
            errors.append(f"'{section}' object is required")
            continue
        for name, kind in fields.items():
            if name not in block:
                errors.append(f"{section}.{name} is required")
                continue
            try:
                ok = _check(kind, block[name])
            except (ValueError, TypeError):
                ok = False
            if not ok:
                errors.append(f"{section}.{name} has an invalid value")
    if not errors:
        if payload["claim"]["claim_type"] not in CLAIM_TYPES:
            errors.append("claim.claim_type must be ACCIDENT, FIRE or THIRD_PARTY")
        if payload["claim"]["requested_amount"] <= 0:
            errors.append("claim.requested_amount must be positive")
        if payload["policy"]["idv"] <= 0:
            errors.append("policy.idv must be positive")
    if errors:
        raise PayloadError(errors)
    payload["policy"].setdefault("cumulative_approved_amount", 0)
    payload["claim"].setdefault("description_length", 100)
    payload["documents"].setdefault("rejected_count", 0)
    payload["documents"].setdefault("reused_in_other_claims", 0)
    return payload
