from fastapi.testclient import TestClient

from venda_de_put.web.app import create_app


def _register(client, username):
    response = client.post(
        "/api/carteira/auth/register",
        json={"username": username, "password": "senha-pessoal-123"},
    )
    assert response.status_code == 201
    return response.json()["csrf_token"]


def test_wallet_survives_app_restart_and_remains_owner_scoped(tmp_path):
    client_a = TestClient(create_app(data_dir=tmp_path))
    csrf_a = _register(client_a, "owner_a")
    body = {
        "sale_date": "2026-08-01", "underlying_ticker": "PETR4",
        "option_ticker": "PETRU400", "option_kind": "put", "quantity": 100,
        "strike_cents": 4000, "expiry_date": "2026-09-18",
        "premium_per_share_cents": 80, "status": "open",
        "close_cost_per_share_cents": None, "repurchase_date": None,
    }
    assert client_a.post(
        "/api/carteira/operations", json=body,
        headers={"X-CSRF-Token": csrf_a},
    ).status_code == 201

    restarted = TestClient(create_app(data_dir=tmp_path))
    login = restarted.post(
        "/api/carteira/auth/login",
        json={"username": "OWNER_A", "password": "senha-pessoal-123"},
    )
    assert login.status_code == 200
    assert len(restarted.get("/api/carteira/operations").json()) == 1
    assert restarted.get("/api/me").json() == {"admin": False}

    client_b = TestClient(create_app(data_dir=tmp_path))
    _register(client_b, "owner_b")
    assert client_b.get("/api/carteira/operations").json() == []
    assert client_b.get("/api/carteira/summary?year=2026").json()["premium_received_cents"] == 0
