from pathlib import Path

from fastapi.testclient import TestClient

from venda_de_put.web.app import create_app


def _register(client: TestClient, username: str = "igor") -> str:
    response = client.post(
        "/api/carteira/auth/register",
        json={"username": username, "password": "senha-pessoal-123"},
    )
    assert response.status_code == 201
    assert "carteira_session" in response.cookies
    assert "carteira_csrf" in response.cookies
    return response.json()["csrf_token"]


def test_register_sets_separate_cookies_and_me(tmp_path: Path):
    client = TestClient(create_app(data_dir=tmp_path))
    csrf = _register(client)
    assert csrf
    assert client.get("/api/carteira/me").json() == {
        "authenticated": True,
        "username": "igor",
    }
    assert client.get("/api/me").json() == {"admin": False}


def test_mutation_requires_matching_csrf(tmp_path: Path):
    client = TestClient(create_app(data_dir=tmp_path))
    csrf = _register(client)
    payload = {"cash_cents": 500_000}
    assert client.put("/api/carteira/account", json=payload).status_code == 403
    assert client.put(
        "/api/carteira/account",
        json=payload,
        headers={"X-CSRF-Token": csrf + "x"},
    ).status_code == 403
    ok = client.put(
        "/api/carteira/account", json=payload,
        headers={"X-CSRF-Token": csrf},
    )
    assert ok.status_code == 200
    assert ok.json() == payload


def test_me_without_personal_session_is_anonymous(tmp_path: Path):
    client = TestClient(create_app(data_dir=tmp_path))
    assert client.get("/api/carteira/me").json() == {
        "authenticated": False,
        "username": None,
    }


def test_admin_cookie_does_not_authorize_personal_api(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("VENDA_DE_PUT_ADMIN_PASSWORD", "segredo")
    client = TestClient(create_app(data_dir=tmp_path))
    login = client.post("/api/login", json={"password": "segredo"})
    assert login.status_code == 200
    assert client.get("/api/me").json() == {"admin": True}
    assert client.get("/api/carteira/me").json() == {
        "authenticated": False,
        "username": None,
    }
    assert client.get("/api/carteira/account").status_code == 401
    assert client.put(
        "/api/carteira/account",
        json={"cash_cents": 1},
        headers={"X-CSRF-Token": "nao-e-csrf-pessoal"},
    ).status_code == 401


def test_duplicate_register_is_conflict(tmp_path: Path):
    client = TestClient(create_app(data_dir=tmp_path))
    _register(client, "igor")
    again = client.post(
        "/api/carteira/auth/register",
        json={"username": "IGOR", "password": "outra-senha-123"},
    )
    assert again.status_code == 409


def test_summary_without_snapshot_keeps_quotes_none(tmp_path: Path):
    client = TestClient(create_app(data_dir=tmp_path))
    csrf = _register(client)
    created = client.post(
        "/api/carteira/operations",
        headers={"X-CSRF-Token": csrf},
        json={
            "sale_date": "2026-08-01",
            "underlying_ticker": "PETR4",
            "option_ticker": "PETRU400",
            "option_kind": "put",
            "quantity": 100,
            "strike_cents": 4000,
            "expiry_date": "2026-09-18",
            "premium_per_share_cents": 80,
            "status": "open",
            "close_cost_per_share_cents": None,
            "repurchase_date": None,
        },
    )
    assert created.status_code == 201
    summary = client.get("/api/carteira/summary", params={"year": 2026})
    assert summary.status_code == 200
    body = summary.json()
    assert body["cash_cents"] is None
    assert body["open_option_market_value_cents"] is None
    assert body["put_capital_at_risk_cents"] == 400_000
    assert set(body["missing_quotes"]) == {"PETR4", "PETRU400"}
    assert body["open_operations"][0]["underlying_price_cents"] is None
    assert body["open_operations"][0]["option_price_cents"] is None
    assert "user_id" not in body
    assert "password_hash" not in str(body)


def test_logout_requires_csrf_and_revokes_session(tmp_path: Path):
    client = TestClient(create_app(data_dir=tmp_path))
    csrf = _register(client)
    assert client.post("/api/carteira/auth/logout").status_code == 403
    out = client.post(
        "/api/carteira/auth/logout",
        headers={"X-CSRF-Token": csrf},
    )
    assert out.status_code == 200
    assert client.get("/api/carteira/me").json() == {
        "authenticated": False,
        "username": None,
    }
    assert client.get("/api/carteira/account").status_code == 401
