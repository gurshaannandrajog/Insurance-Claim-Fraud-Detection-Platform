"""
Fraud Detection & Risk Assessment service (SRS §4.7) — a separate Flask API.

Endpoints
  GET  /health                 liveness probe (no auth)
  GET  /api/v1/engine          active engine + risk bands (auth)
  POST /api/v1/assess          score one claim → {risk_score, risk_level, flagged, factors[], engine} (auth)

Authentication: shared secret in the `X-API-Key` header (FRAUD_SERVICE_API_KEY). Only the Django backend calls
this service; it is never exposed to browsers.
"""
import hmac
import logging
import os
import time
from pathlib import Path

from flask import Flask, jsonify, request

from .scoring.registry import get_scorer
from .validation import PayloadError, validate

log = logging.getLogger("fraud_service")


def _load_env():
    try:
        from dotenv import load_dotenv
    except ImportError:  # optional dependency
        return
    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env")
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def create_app(config=None):
    _load_env()
    app = Flask(__name__)
    app.config.update(API_KEY=os.environ.get("FRAUD_SERVICE_API_KEY", ""), MAX_CONTENT_LENGTH=256 * 1024)
    if config:
        app.config.update(config)
    scorer = get_scorer()
    if not app.config["API_KEY"]:
        log.warning("FRAUD_SERVICE_API_KEY is empty — requests will be rejected until it is set")

    def authorised():
        key = app.config["API_KEY"]
        supplied = request.headers.get("X-API-Key", "")
        return bool(key) and hmac.compare_digest(supplied.encode(), key.encode())

    @app.get("/health")
    def health():
        return jsonify(status="ok", engine=scorer.name)

    @app.get("/api/v1/engine")
    def engine():
        if not authorised():
            return jsonify(error="unauthorised"), 401
        return jsonify(engine=scorer.name, bands={"LOW": [0, 29], "MEDIUM": [30, 59], "HIGH": [60, 100]})

    @app.post("/api/v1/assess")
    def assess():
        if not authorised():
            return jsonify(error="unauthorised"), 401
        payload = request.get_json(silent=True)
        try:
            features = validate(payload)
        except PayloadError as exc:
            return jsonify(error="invalid_payload", details=exc.errors), 400
        started = time.perf_counter()
        result = scorer.score(features).to_dict()
        log.info("assessed %s score=%s level=%s in %.1fms", features["claim"].get("claim_number", "?"),
                 result["risk_score"], result["risk_level"], (time.perf_counter() - started) * 1000)
        return jsonify(result)

    @app.errorhandler(404)
    def not_found(_):
        return jsonify(error="not_found"), 404

    @app.errorhandler(405)
    def method_not_allowed(_):
        return jsonify(error="method_not_allowed"), 405

    @app.errorhandler(413)
    def too_large(_):
        return jsonify(error="payload_too_large"), 413

    @app.errorhandler(Exception)
    def unhandled(exc):
        log.exception("Unhandled error")
        return jsonify(error="internal_error"), 500

    return app
