"""HTTP contract tests for the billing API.

These tests drive the real ASGI app via FastAPI's TestClient: no browser,
no frontend build, no network port. Run serially with plain ``pytest``.
"""

ONE_CENT = 0.01

SEEDED_ACCOUNT_ID = 1  # '张家', seeded reading 120 kWh, non-peak
PEAK_ACCOUNT_ID = 2  # '李家(种子偏高)', seeded reading 400 kWh, peak
UNKNOWN_ACCOUNT_ID = 999999

BILL_KEYS = {"run_id", "kwh", "peak_factor", "total", "segments"}
SEGMENT_KEYS = {"from_kwh", "to_kwh", "qty", "price", "amount"}


def _segment_amounts_sum(body) -> float:
    return float(sum(seg["amount"] for seg in body["segments"]))


# ---------------------------------------------------------------- health ----


def test_health_structure(api):
    resp = api.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"ok", "project"}
    assert body["ok"] is True
    assert isinstance(body["project"], str) and body["project"]


# ----------------------------------------------------------------- tiers ----


def test_tiers_nonempty_and_monotonic(api):
    resp = api.get("/api/tiers")
    assert resp.status_code == 200
    items = resp.json()["items"]

    assert isinstance(items, list)
    assert len(items) >= 2
    for tier in items:
        assert set(tier.keys()) >= {"up_to", "price"}
        assert tier["price"] > 0

    # Progressive pricing: unit price must not decrease as usage grows.
    prices = [tier["price"] for tier in items]
    assert prices == sorted(prices)

    # Band thresholds must be strictly ascending; the open-ended tier last.
    thresholds = [tier["up_to"] for tier in items]
    finite = [v for v in thresholds if v is not None]
    assert finite == sorted(set(finite))
    assert thresholds[-1] is None


# -------------------------------------------------------------- bill: ok ----


def test_bill_seeded_account_contract(api):
    payload = {"account_id": SEEDED_ACCOUNT_ID, "kwh": 120, "peak": False, "persist": False}
    resp = api.post("/api/bill", json=payload)
    assert resp.status_code == 200
    body = resp.json()

    assert set(body.keys()) == BILL_KEYS
    assert body["run_id"] is None  # persist=False
    assert body["kwh"] == 120
    assert body["peak_factor"] == 1.0
    assert isinstance(body["total"], (int, float))
    assert body["total"] == 62.40  # 120 kWh all inside the first 0.52 band

    assert isinstance(body["segments"], list)
    assert len(body["segments"]) >= 1
    for seg in body["segments"]:
        assert set(seg.keys()) == SEGMENT_KEYS
        assert seg["amount"] >= 0

    # Sum of per-segment amounts must reconcile with total to the cent.
    assert abs(_segment_amounts_sum(body) - body["total"]) <= ONE_CENT


def test_bill_peak_seeded_account_contract(api):
    payload = {"account_id": SEEDED_ACCOUNT_ID, "kwh": 400, "peak": True, "persist": False}
    resp = api.post("/api/bill", json=payload)
    assert resp.status_code == 200
    body = resp.json()

    assert set(body.keys()) == BILL_KEYS
    assert body["kwh"] == 400
    assert body["peak_factor"] == 1.2  # seeded settings value
    assert body["total"] == 309.60
    assert len(body["segments"]) == 3  # crosses all three bands
    assert abs(_segment_amounts_sum(body) - body["total"]) <= ONE_CENT


def test_bill_repeated_calls_have_stable_keys_and_total(api):
    payload = {"account_id": PEAK_ACCOUNT_ID, "kwh": 400, "peak": False, "persist": False}

    first = api.post("/api/bill", json=payload)
    second = api.post("/api/bill", json=payload)
    assert first.status_code == second.status_code == 200

    first_body, second_body = first.json(), second.json()
    assert set(first_body.keys()) == set(second_body.keys()) == BILL_KEYS
    assert first_body["total"] == second_body["total"]
    assert first_body["peak_factor"] == second_body["peak_factor"] == 1.0
    assert abs(_segment_amounts_sum(first_body) - first_body["total"]) <= ONE_CENT
    assert abs(_segment_amounts_sum(second_body) - second_body["total"]) <= ONE_CENT


# ------------------------------------------------------------ bill: errors --


def _validation_error_for(detail, field: str) -> dict | None:
    assert isinstance(detail, list) and detail, "FastAPI validation errors must be a non-empty list"
    for err in detail:
        assert set(err.keys()) >= {"loc", "msg", "type"}
        if field in [str(part) for part in err["loc"]]:
            return err
    return None


def test_bill_negative_kwh_rejected(api):
    resp = api.post(
        "/api/bill",
        json={"account_id": SEEDED_ACCOUNT_ID, "kwh": -1, "peak": False, "persist": False},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert set(body.keys()) == {"detail"}
    err = _validation_error_for(body["detail"], "kwh")
    assert err is not None
    assert err["type"] == "greater_than_equal"


def test_bill_unknown_account_returns_404(api):
    resp = api.post(
        "/api/bill",
        json={"account_id": UNKNOWN_ACCOUNT_ID, "kwh": 120, "peak": False, "persist": False},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert set(body.keys()) == {"detail"}
    assert isinstance(body["detail"], str)
    assert body["detail"] == "account not found"


def test_bill_missing_required_field_rejected(api):
    resp = api.post(
        "/api/bill",
        json={"account_id": SEEDED_ACCOUNT_ID, "peak": False, "persist": False},  # no kwh
    )
    assert resp.status_code == 422
    body = resp.json()
    assert set(body.keys()) == {"detail"}
    err = _validation_error_for(body["detail"], "kwh")
    assert err is not None
    assert err["type"] == "missing"
