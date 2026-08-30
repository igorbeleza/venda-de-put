import pytest
from fastapi.testclient import TestClient

from venda_de_put.web.app import create_app


def _user(data_dir, username):
    client = TestClient(create_app(data_dir=data_dir))
    response = client.post(
        "/api/carteira/auth/register",
        json={"username": username, "password": "senha-pessoal-123"},
    )
    return client, response.json()["csrf_token"]


def test_user_b_cannot_read_update_or_delete_user_a_operation(tmp_path):
    a, csrf_a = _user(tmp_path, "user_a")
    body = {
        "sale_date": "2026-08-01", "underlying_ticker": "PETR4",
        "option_ticker": "PETRU400", "option_kind": "put",
        "quantity": 100, "strike_cents": 4000,
        "expiry_date": "2026-09-18", "premium_per_share_cents": 80,
        "status": "open", "close_cost_per_share_cents": None,
        "repurchase_date": None,
    }
    created = a.post(
        "/api/carteira/operations",
        headers={"X-CSRF-Token": csrf_a},
        json=body,
    )
    assert created.status_code == 201
    operation_id = created.json()["id"]
    payload = created.json()
    assert payload["underlying_price_cents"] is None
    assert payload["option_price_cents"] is None
    assert payload["open_profit_cents"] is None
    assert "user_id" not in payload

    b, csrf_b = _user(tmp_path, "user_b")
    assert b.get("/api/carteira/operations").json() == []
    assert b.get(f"/api/carteira/operations/{operation_id}").status_code == 404
    assert b.put(
        f"/api/carteira/operations/{operation_id}",
        headers={"X-CSRF-Token": csrf_b}, json=body,
    ).status_code == 404
    assert b.delete(
        f"/api/carteira/operations/{operation_id}",
        headers={"X-CSRF-Token": csrf_b},
    ).status_code == 404
    assert len(a.get("/api/carteira/operations").json()) == 1


@pytest.mark.parametrize(
    ("collection", "payload"),
    [
        ("portfolio", {
            "trade_date": "2026-08-01", "ticker": "PETR4",
            "asset_class": "stock", "side": "buy", "quantity": 100,
            "price_cents": 4000, "note": "inicial",
        }),
        ("custody", {"as_of_date": "2026-08-30", "total_cents": 500_000}),
        ("cash-flows", {
            "flow_date": "2026-08-01", "kind": "contribution",
            "amount_cents": 500_000, "note": "inicial",
        }),
    ],
)
def test_other_collections_are_owner_scoped(tmp_path, collection, payload):
    a, csrf_a = _user(tmp_path, f"a_{collection.replace('-', '_')}")
    created = a.post(
        f"/api/carteira/{collection}", json=payload,
        headers={"X-CSRF-Token": csrf_a},
    )
    assert created.status_code == 201
    item_id = created.json()["id"]

    b, csrf_b = _user(tmp_path, f"b_{collection.replace('-', '_')}")
    assert b.get(f"/api/carteira/{collection}").json() == []
    assert b.get(f"/api/carteira/{collection}/{item_id}").status_code == 404
    assert b.put(
        f"/api/carteira/{collection}/{item_id}", json=payload,
        headers={"X-CSRF-Token": csrf_b},
    ).status_code == 404
    assert b.delete(
        f"/api/carteira/{collection}/{item_id}",
        headers={"X-CSRF-Token": csrf_b},
    ).status_code == 404
