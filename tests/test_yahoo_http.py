from venda_de_put.sources.yahoo import YahooHttp, YAHOO_CHART


class _Resp:
    def __init__(self, status: int, payload: dict | None = None) -> None:
        self.status_code = status
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self) -> dict:
        return self._payload


class _Scripted:
    def __init__(self, outcomes: list) -> None:
        self.outcomes = list(outcomes)
        self.n = 0

    def get(self, url, headers=None):
        self.n += 1
        item = self.outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _chart(preco: float = 41.75) -> dict:
    return {
        "chart": {
            "result": [{
                "meta": {
                    "regularMarketPrice": preco,
                    "fiftyTwoWeekHigh": 42.0,
                    "fiftyTwoWeekLow": 30.0,
                },
                "timestamp": [1, 2, 3],
                "indicators": {"quote": [{"close": [40.0, 40.5, 41.0]}]},
            }]
        }
    }


def test_yahoo_http_terceira_tentativa_grava_serie():
    client = _Scripted([
        RuntimeError("net"),
        _Resp(500),
        _Resp(200, _chart()),
    ])
    out = YahooHttp(client).fetch(["PETR4"])
    assert "PETR4" in out
    assert out["PETR4"].preco == 41.75
    assert client.n == 3
    assert YAHOO_CHART.format(ticker="PETR4")


def test_yahoo_http_tres_falhas_omitam_ticker():
    client = _Scripted([
        RuntimeError("a"),
        RuntimeError("b"),
        RuntimeError("c"),
    ])
    out = YahooHttp(client).fetch(["PETR4"])
    assert out == {}
    assert client.n == 3
