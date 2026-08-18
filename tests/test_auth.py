import time
from pathlib import Path

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from venda_de_put.auth import (
    SESSION_MAX_AGE_SECONDS,
    check_password,
    create_session_token,
    verify_session_token,
)
from venda_de_put.web.app import create_app, require_admin


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path


# --- Testes unitários do módulo auth ---

def test_check_password_sem_env_retorna_false(monkeypatch):
    monkeypatch.delenv("VENDA_DE_PUT_ADMIN_PASSWORD", raising=False)
    assert check_password("qualquer_coisa") is False
    assert check_password("") is False


def test_check_password_com_env(monkeypatch):
    monkeypatch.setenv("VENDA_DE_PUT_ADMIN_PASSWORD", "senha_correta_123")
    assert check_password("senha_correta_123") is True
    assert check_password("senha_errada") is False
    assert check_password("") is False


def test_session_token_ciclo_valido():
    token = create_session_token()
    assert isinstance(token, str)
    assert verify_session_token(token) is True


def test_session_token_invalido():
    assert verify_session_token("") is False
    assert verify_session_token("invalido") is False
    assert verify_session_token("123.abc") is False
    assert verify_session_token("123.abc.def.ghi") is False


def test_session_token_adulterado():
    token = create_session_token()
    parts = token.split(".")
    # Altera payload
    tampered = f"{int(parts[0]) + 1}.{parts[1]}.{parts[2]}"
    assert verify_session_token(tampered) is False
    # Altera assinatura
    tampered_sig = f"{parts[0]}.{parts[1]}.{parts[2][:-1]}a"
    assert verify_session_token(tampered_sig) is False


def test_session_token_expirado():
    token = create_session_token()
    # verify com max_age=-1 deve falhar
    assert verify_session_token(token, max_age=-1) is False


def test_session_token_com_secret_key(monkeypatch):
    monkeypatch.setenv("VENDA_DE_PUT_SECRET_KEY", "chave_secreta_teste")
    token = create_session_token()
    assert verify_session_token(token) is True

    # Se a chave mudar, o token anterior torna-se inválido
    monkeypatch.setenv("VENDA_DE_PUT_SECRET_KEY", "outra_chave")
    assert verify_session_token(token) is False


# --- Testes de rotas HTTP /api/login, /api/logout, /api/me e require_admin ---

def test_api_me_deslogado(data_dir: Path):
    app = create_app(data_dir)
    client = TestClient(app)
    res = client.get("/api/me")
    assert res.status_code == 200
    assert res.json() == {"admin": False}


def test_api_login_senha_errada(data_dir: Path, monkeypatch):
    monkeypatch.setenv("VENDA_DE_PUT_ADMIN_PASSWORD", "correta")
    app = create_app(data_dir)
    client = TestClient(app)

    res = client.post("/api/login", json={"password": "errada"})
    assert res.status_code == 401


def test_api_login_sem_env_senha(data_dir: Path, monkeypatch):
    monkeypatch.delenv("VENDA_DE_PUT_ADMIN_PASSWORD", raising=False)
    app = create_app(data_dir)
    client = TestClient(app)

    res = client.post("/api/login", json={"password": "qualquer"})
    assert res.status_code == 401


def _set_cookie_header(res) -> str:
    return res.headers.get("set-cookie") or ""


def test_login_cookie_path_raiz_sem_prefixo(data_dir: Path, monkeypatch):
    monkeypatch.setenv("VENDA_DE_PUT_ADMIN_PASSWORD", "segredo")
    client = TestClient(create_app(data_dir))
    res = client.post("/api/login", json={"password": "segredo"})
    cookie = _set_cookie_header(res)
    assert "session=" in cookie
    assert "Path=/venda-de-put" not in cookie
    assert "Path=/" in cookie


def test_login_cookie_path_segue_x_forwarded_prefix(data_dir: Path, monkeypatch):
    monkeypatch.setenv("VENDA_DE_PUT_ADMIN_PASSWORD", "segredo")
    client = TestClient(create_app(data_dir))
    res = client.post(
        "/api/login",
        json={"password": "segredo"},
        headers={"X-Forwarded-Prefix": "/venda-de-put"},
    )
    cookie = _set_cookie_header(res)
    assert "Path=/venda-de-put" in cookie
    assert "Secure" not in cookie


def test_login_cookie_secure_atras_de_https(data_dir: Path, monkeypatch):
    monkeypatch.setenv("VENDA_DE_PUT_ADMIN_PASSWORD", "segredo")
    client = TestClient(create_app(data_dir))
    res = client.post(
        "/api/login",
        json={"password": "segredo"},
        headers={
            "X-Forwarded-Prefix": "/venda-de-put",
            "X-Forwarded-Proto": "https",
        },
    )
    cookie = _set_cookie_header(res)
    assert "Path=/venda-de-put" in cookie
    assert "Secure" in cookie


def test_logout_apaga_cookie_no_mesmo_prefixo(data_dir: Path, monkeypatch):
    monkeypatch.setenv("VENDA_DE_PUT_ADMIN_PASSWORD", "segredo")
    client = TestClient(create_app(data_dir))
    client.post(
        "/api/login",
        json={"password": "segredo"},
        headers={"X-Forwarded-Prefix": "/venda-de-put"},
    )
    res = client.post(
        "/api/logout",
        headers={"X-Forwarded-Prefix": "/venda-de-put"},
    )
    assert "Path=/venda-de-put" in _set_cookie_header(res)


def test_api_login_sucesso_me_e_logout(data_dir: Path, monkeypatch):
    monkeypatch.setenv("VENDA_DE_PUT_ADMIN_PASSWORD", "segredo")
    app = create_app(data_dir)
    client = TestClient(app)

    # 1. Login com sucesso
    res = client.post("/api/login", json={"password": "segredo"})
    assert res.status_code == 200
    assert res.json() == {"admin": True}
    assert "session" in res.cookies

    # 2. /api/me reconhece admin
    res_me = client.get("/api/me")
    assert res_me.status_code == 200
    assert res_me.json() == {"admin": True}

    # 3. Logout apaga cookie
    res_logout = client.post("/api/logout")
    assert res_logout.status_code == 200
    assert res_logout.json() == {"admin": False}

    # 4. /api/me volta a ser False
    res_me_after = client.get("/api/me")
    assert res_me_after.status_code == 200
    assert res_me_after.json() == {"admin": False}


def test_session_token_timestamp_nao_inteiro():
    assert verify_session_token("abc.def.ghi") is False


def test_check_password_tipo_invalido():
    assert check_password(None) is False  # type: ignore
    assert check_password(123) is False  # type: ignore


def test_api_login_payload_invalido(data_dir: Path):
    app = create_app(data_dir)
    client = TestClient(app)

    res = client.post("/api/login", json={"outrocampo": "123"})
    assert res.status_code == 400

    res_list = client.post("/api/login", json=["senha"])
    assert res_list.status_code in (400, 422)


def test_api_me_cookie_adulterado(data_dir: Path, monkeypatch):
    monkeypatch.setenv("VENDA_DE_PUT_ADMIN_PASSWORD", "segredo")
    app = create_app(data_dir)
    client = TestClient(app)

    client.cookies.set("session", "token.falso.invalido")
    res = client.get("/api/me")
    assert res.status_code == 200
    assert res.json() == {"admin": False}


def test_require_admin_fastapi_depends(data_dir: Path, monkeypatch):
    from fastapi import Depends

    monkeypatch.setenv("VENDA_DE_PUT_ADMIN_PASSWORD", "segredo")
    app = create_app(data_dir)

    @app.get("/api/test-depends")
    def route_with_depends(_=Depends(require_admin)):
        return {"authorized": True}

    client = TestClient(app)
    assert client.get("/api/test-depends").status_code == 401

    client.post("/api/login", json={"password": "segredo"})
    res = client.get("/api/test-depends")
    assert res.status_code == 200
    assert res.json() == {"authorized": True}


def test_require_admin_helper(data_dir: Path, monkeypatch):
    monkeypatch.setenv("VENDA_DE_PUT_ADMIN_PASSWORD", "segredo")
    app = create_app(data_dir)
    client = TestClient(app)

    # Cria rota de teste usando require_admin
    @app.get("/api/test-protected")
    def protected(request: Request):
        require_admin(request)
        return {"ok": True}

    # Sem autenticação -> 401
    res = client.get("/api/test-protected")
    assert res.status_code == 401

    # Com login -> 200
    client.post("/api/login", json={"password": "segredo"})
    res2 = client.get("/api/test-protected")
    assert res2.status_code == 200
    assert res2.json() == {"ok": True}


def test_put_config_sem_auth_retorna_401(data_dir: Path):
    app = create_app(data_dir)
    client = TestClient(app)
    res = client.put("/api/config", json={})
    assert res.status_code == 401


def test_put_feriados_sem_auth_retorna_401(data_dir: Path):
    app = create_app(data_dir)
    client = TestClient(app)
    res = client.put("/api/feriados", json=[])
    assert res.status_code == 401


def test_post_scrape_sem_auth_retorna_401(data_dir: Path):
    app = create_app(data_dir)
    client = TestClient(app)
    res = client.post("/api/scrape", json={})
    assert res.status_code == 401


def test_get_scrape_status_sem_auth_retorna_401(data_dir: Path):
    app = create_app(data_dir)
    client = TestClient(app)
    res = client.get("/api/scrape/status")
    assert res.status_code == 401


def test_get_scrape_status_autenticado(data_dir: Path):
    app = create_app(data_dir)
    client = TestClient(app)
    client.cookies.set("session", create_session_token())
    res = client.get("/api/scrape/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("idle", "running")
    assert "erro" in data
    assert "generated_at" in data
    assert "passos" in data
    ids = [p["id"] for p in data["passos"]]
    assert ids == ["yahoo", "oplab", "fundamentus", "oplab_cadeia"]
    for p in data["passos"]:
        assert "label" in p and "status" in p
        assert "erro" in p


def test_post_scrape_sucesso_e_comandos(data_dir: Path, monkeypatch):
    import subprocess
    import sys

    app = create_app(data_dir)
    client = TestClient(app)
    client.cookies.set("session", create_session_token())

    captured_cmds = []
    captured_kwargs = []
    created_procs = []

    class FakeProc:
        def __init__(self, cmd, *args, **kwargs):
            captured_cmds.append(cmd)
            captured_kwargs.append(kwargs)
            self.returncode = None
            self.communicated = False
            self._stderr = ""
            created_procs.append(self)

        def poll(self):
            return self.returncode

        def communicate(self):
            self.communicated = True
            if self.returncode is None:
                self.returncode = 0
            return ("", self._stderr)

    monkeypatch.setattr(subprocess, "Popen", FakeProc)

    # 1. Sem body
    res = client.post("/api/scrape")
    assert res.status_code == 200
    assert res.json() == {"status": "running"}
    assert captured_cmds[-1][0] == sys.executable
    assert captured_cmds[-1][captured_cmds[-1].index("--data-dir") + 1] == str(data_dir)
    assert captured_kwargs[-1]["stdout"] == subprocess.DEVNULL
    assert captured_kwargs[-1]["stderr"] == subprocess.PIPE
    assert "--force-fundamentus" not in captured_cmds[-1]
    assert created_procs[-1].communicated is True

    # 2. Com incluir_fundamentus: True
    res_true = client.post("/api/scrape", json={"incluir_fundamentus": True})
    assert res_true.status_code == 200
    assert captured_cmds[-1][0] == sys.executable
    assert captured_cmds[-1][captured_cmds[-1].index("--data-dir") + 1] == str(data_dir)
    assert captured_kwargs[-1]["stdout"] == subprocess.DEVNULL
    assert "--force-fundamentus" in captured_cmds[-1]
    idx = captured_cmds[-1].index("--force-fundamentus")
    assert captured_cmds[-1][idx + 1] == "true"

    # 3. Com incluir_fundamentus: False
    res_false = client.post("/api/scrape", json={"incluir_fundamentus": False})
    assert res_false.status_code == 200
    assert captured_cmds[-1][0] == sys.executable
    assert captured_cmds[-1][captured_cmds[-1].index("--data-dir") + 1] == str(data_dir)
    assert captured_kwargs[-1]["stdout"] == subprocess.DEVNULL
    assert "--force-fundamentus" in captured_cmds[-1]
    idx = captured_cmds[-1].index("--force-fundamentus")
    assert captured_cmds[-1][idx + 1] == "false"

    res_passo = client.post("/api/scrape", json={"passo": "oplab"})
    assert res_passo.status_code == 200
    cmd = captured_cmds[-1]
    assert cmd[cmd.index("--from-step") + 1] == "oplab"

    res_ruim = client.post("/api/scrape", json={"passo": "nexiste"})
    assert res_ruim.status_code == 400


def test_post_scrape_status_running_enquanto_ativo(data_dir: Path):
    app = create_app(data_dir)
    client = TestClient(app)
    client.cookies.set("session", create_session_token())

    class ActiveProc:
        def __init__(self):
            self.returncode = None

        def poll(self):
            return self.returncode

    proc = ActiveProc()
    app.state.scrape_process = proc

    # Enquanto o processo está ativo (poll() is None), status deve ser running
    status = client.get("/api/scrape/status").json()
    assert status["status"] == "running"

    # E novo POST deve dar 409
    res = client.post("/api/scrape")
    assert res.status_code == 409
    assert "em andamento" in res.json()["detail"]

    # Quando finaliza, status volta para idle
    proc.returncode = 0
    status_idle = client.get("/api/scrape/status").json()
    assert status_idle["status"] == "idle"


def test_post_scrape_falha_grava_erro_no_status(data_dir: Path, monkeypatch):
    import subprocess

    app = create_app(data_dir)
    client = TestClient(app)
    client.cookies.set("session", create_session_token())

    class FailingProc:
        def __init__(self, cmd, *args, **kwargs):
            self.returncode = 1

        def poll(self):
            return self.returncode

        def communicate(self):
            return ("", "Falha ao conectar na B3")

    monkeypatch.setattr(subprocess, "Popen", FailingProc)

    res = client.post("/api/scrape")
    assert res.status_code == 200

    status = client.get("/api/scrape/status").json()
    assert status["status"] == "idle"
    assert "Falha ao conectar na B3" in status["erro"]


def test_main_cli_force_fundamentus_parsing(monkeypatch):
    from venda_de_put.__main__ import main
    import venda_de_put.scrape

    calls = []

    def fake_cli_scrape(data_dir=None, force_fundamentus=None, from_step=None):
        calls.append((data_dir, force_fundamentus, from_step))
        return 0

    monkeypatch.setattr(venda_de_put.scrape, "cli_scrape", fake_cli_scrape)

    main(["scrape"])
    assert calls[-1] == (None, None, None)

    main(["scrape", "--force-fundamentus", "true"])
    assert calls[-1] == (None, True, None)

    main(["scrape", "--force-fundamentus", "false"])
    assert calls[-1] == (None, False, None)

    main(["scrape", "--from-step", "oplab"])
    assert calls[-1] == (None, None, "oplab")



