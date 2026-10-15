def test_health_is_public(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.get_json()["status"] == "ok"


def test_assess_requires_api_key(client, payload):
    assert client.post("/api/v1/assess", json=payload).status_code == 401
    assert client.post("/api/v1/assess", json=payload, headers={"X-API-Key": "wrong"}).status_code == 401


def test_assess_returns_contract(client, payload, auth):
    r = client.post("/api/v1/assess", json=payload, headers=auth)
    assert r.status_code == 200
    body = r.get_json()
    assert set(body) == {"risk_score", "risk_level", "flagged", "factors", "engine"}
    assert 0 <= body["risk_score"] <= 100
    assert body["risk_level"] in {"LOW", "MEDIUM", "HIGH"}
    assert body["engine"] == "rules-v1"


def test_invalid_payload_is_rejected(client, payload, auth):
    del payload["policy"]["idv"]
    payload["claim"]["claim_type"] = "THEFT"
    r = client.post("/api/v1/assess", json=payload, headers=auth)
    assert r.status_code == 400
    assert "policy.idv is required" in r.get_json()["details"]


def test_non_json_body(client, auth):
    r = client.post("/api/v1/assess", data="nope", headers=auth)
    assert r.status_code == 400


def test_unknown_route(client):
    assert client.get("/nope").status_code == 404
