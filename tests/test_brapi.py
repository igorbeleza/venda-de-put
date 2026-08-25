import httpx

from venda_de_put.sources.brapi import BRAPI_QUOTE, BrapiSpotHttp, parse_brapi_quote


def test_parse_brapi_quote_pega_preco():
    payload = {
        "results": [
            {"symbol": "PETR4", "regularMarketPrice": 41.75},
            {"symbol": "VALE3", "regularMarketPrice": None},
            {"symbol": "ITUB4", "regularMarketPrice": "35.1"},
            {"symbol": "BAD", "regularMarketPrice": "x"},
        ]
    }
    out = parse_brapi_quote(payload)
    assert out["PETR4"] == 41.75
    assert out["ITUB4"] == 35.1
    assert "VALE3" not in out
    assert "BAD" not in out


def test_brapi_sem_token_nao_faz_get(monkeypatch):
    monkeypatch.delenv("VENDA_DE_PUT_BRAPI_TOKEN", raising=False)
    n = {"get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        n["get"] += 1
        return httpx.Response(200, json={"results": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = BrapiSpotHttp(token="", client=client).fetch_spots(["PETR4"])
    assert out == {}
    assert n["get"] == 0


def test_brapi_lote_so_os_pedidos():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        seen["auth"] = request.headers.get("authorization")
        assert "token=" not in str(request.url)
        return httpx.Response(200, json={
            "results": [{"symbol": "PETR4", "regularMarketPrice": 10.0}]
        })

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = BrapiSpotHttp(token="abc", client=client).fetch_spots(["PETR4", "VALE3"])
    assert out == {"PETR4": 10.0}
    # httpx percent-encoda a vírgula (PETR4%2CVALE3). Assertar o valor decodificado.
    assert seen["request"].url.params["symbols"] == "PETR4,VALE3"
    assert seen["auth"] == "Bearer abc"
    assert str(seen["request"].url).startswith(BRAPI_QUOTE)


def test_brapi_http_erro_devolve_vazio():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "rate"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = BrapiSpotHttp(token="abc", client=client).fetch_spots(["PETR4"])
    assert out == {}
