"""HTTP contract tests for the billing API.

Pure API-level tests: they drive the ASGI app in-process via the `client`
fixture (see conftest.py), need no browser and no frontend build, and run
serially under a plain `pytest` invocation locally or in CI.
"""

import pytest

# Seed data (see app/seed.py): account 1 = 张家 with a 120 kWh reading,
# account 2 = 李家(种子偏高) with a 400 kWh peak reading.
SEED_BILL_CASES = [
    {"account_id": 1, "kwh": 120, "peak": False},
    {"account_id": 2, "kwh": 400, "peak": True},
]

UNKNOWN_ACCOUNT_ID = 999999


def test_health_structure(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert isinstance(body["project"], str) and body["project"]


def test_tiers_non_empty_and_monotonic(client):
    r = client.get("/api/tiers")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) > 0
    for tier in items:
        assert set(tier) >= {"up_to", "price", "sort_order"}
        assert tier["price"] > 0
    # Only the last tier may be open-ended (up_to is None).
    for tier in items[:-1]:
        assert tier["up_to"] is not None
    ups = [t["up_to"] for t in items if t["up_to"] is not None]
    assert all(b > a for a, b in zip(ups, ups[1:])), "tier bounds must strictly increase"
    prices = [t["price"] for t in items]
    assert all(b > a for a, b in zip(prices, prices[1:])), "tier prices must strictly increase"


@pytest.mark.parametrize("payload", SEED_BILL_CASES)
def test_bill_response_contract(client, payload):
    r = client.post("/api/bill", json={**payload, "persist": False})
    assert r.status_code == 200
    body = r.json()
    for key in ("kwh", "peak_factor", "total", "segments"):
        assert key in body, f"missing key {key!r} in bill response"
    assert body["kwh"] == pytest.approx(payload["kwh"])
    assert body["peak_factor"] > 0
    segments = body["segments"]
    assert isinstance(segments, list) and segments
    for seg in segments:
        assert isinstance(seg["amount"], (int, float))
    seg_sum = sum(seg["amount"] for seg in segments)
    # Segment amounts must add up to the total within one cent.
    assert seg_sum == pytest.approx(body["total"], abs=0.01)


def test_bill_negative_kwh_rejected(client):
    r = client.post("/api/bill", json={"account_id": 1, "kwh": -1})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, list) and detail
    assert any("kwh" in item["loc"] for item in detail)


def test_bill_unknown_account_rejected(client):
    r = client.post("/api/bill", json={"account_id": UNKNOWN_ACCOUNT_ID, "kwh": 100})
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert isinstance(detail, str) and detail


def test_bill_missing_required_field_rejected(client):
    r = client.post("/api/bill", json={"account_id": 1})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, list) and detail
    assert any(item["type"] == "missing" and "kwh" in item["loc"] for item in detail)


def test_bill_same_request_twice_is_stable(client):
    payload = {"account_id": 1, "kwh": 120, "peak": False, "persist": False}
    r1 = client.post("/api/bill", json=payload)
    r2 = client.post("/api/bill", json=payload)
    assert r1.status_code == r2.status_code == 200
    body1, body2 = r1.json(), r2.json()
    assert set(body1) == set(body2)
    assert body1["total"] == body2["total"]
