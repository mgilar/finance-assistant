import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # context manager runs the lifespan (data load)
        yield c


def test_summary_ok_with_request_id(client):
    r = client.get("/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["request_id"] and body["request_id"] == r.headers["X-Request-ID"]
    assert body["invoice_count"] == 140
    assert body["lineage"]["credit_notes_included"] == 2


@pytest.mark.parametrize("breakdown", ["by_currency", "by_vendor_status"])
def test_breakdown_rows_add_up_to_total(client, breakdown):
    body = client.get("/summary").json()
    rows = body[breakdown]
    assert sum(r["invoice_count"] for r in rows) == body["invoice_count"]
    # Each row is rounded to cents independently: allow 1 cent per row.
    assert sum(r["eur_approx"] for r in rows) == pytest.approx(
        body["total_eur_approx"], abs=0.01 * len(rows)
    )


def test_currency_rows_keep_exact_native_totals(client):
    rows = {r["currency"]: r for r in client.get("/summary").json()["by_currency"]}
    assert rows["EUR"]["total_native"] == 4493726.12
    assert rows["EUR"]["eur_approx"] == rows["EUR"]["total_native"]


def test_unknown_route_has_typed_error_body(client):
    r = client.get("/nope")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert body["request_id"] == r.headers["X-Request-ID"]
