"""HTTP client for the separate Flask fraud-detection service (SRS §3.3, §3.4)."""
import time

import requests
from django.conf import settings


class FraudServiceError(Exception):
    pass


def assess(payload: dict) -> tuple[dict, int]:
    """POST the claim features; returns (result, elapsed_ms). Raises FraudServiceError on any failure."""
    url = f"{settings.FRAUD_SERVICE_URL}/api/v1/assess"
    headers = {"X-API-Key": settings.FRAUD_SERVICE_API_KEY, "Content-Type": "application/json"}
    started = time.monotonic()
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=settings.FRAUD_SERVICE_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise FraudServiceError(f"Fraud service unreachable: {exc.__class__.__name__}") from exc
    elapsed = int((time.monotonic() - started) * 1000)
    if resp.status_code != 200:
        raise FraudServiceError(f"Fraud service returned HTTP {resp.status_code}")
    try:
        data = resp.json()
        score = int(data["risk_score"])
        level = str(data["risk_level"]).upper()
        factors = list(data.get("factors", []))
    except (ValueError, KeyError, TypeError) as exc:
        raise FraudServiceError("Fraud service returned an invalid response") from exc
    if not 0 <= score <= 100 or level not in {"LOW", "MEDIUM", "HIGH"}:
        raise FraudServiceError("Fraud service returned an out-of-range score")
    return {"risk_score": score, "risk_level": level, "flagged": bool(data.get("flagged")), "factors": factors,
            "engine": str(data.get("engine", ""))[:40]}, elapsed


def health() -> bool:
    try:
        return requests.get(f"{settings.FRAUD_SERVICE_URL}/health", timeout=3).status_code == 200
    except requests.RequestException:
        return False
