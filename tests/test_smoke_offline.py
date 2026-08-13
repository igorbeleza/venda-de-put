from pathlib import Path

import httpx

from venda_de_put.smoke import run_smoke

FIXTURES = Path("tests/fixtures")


def test_smoke_uses_2y_not_max(monkeypatch):
    seen: list[str] = []
    yahoo_payload = (
        FIXTURES / "yahoo_petr4.json"
    ).read_text(encoding="utf-8")
    oplab_html = (FIXTURES / "oplab_next_data.html").read_text(encoding="utf-8")
    fund_bytes = (FIXTURES / "fundamentus.html").read_bytes()

    class C:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def close(self):
            pass

        def get(self, url, **kw):
            seen.append(url)

            class R:
                def __init__(self, url: str):
                    self.url = url
                    if "yahoo" in url or "finance" in url:
                        self.text = yahoo_payload
                        self.content = yahoo_payload.encode("utf-8")
                    elif "oplab" in url:
                        self.text = oplab_html
                        self.content = oplab_html.encode("utf-8")
                    else:
                        self.text = fund_bytes.decode("latin-1")
                        self.content = fund_bytes

                def raise_for_status(self):
                    pass

                def json(self):
                    import json

                    return json.loads(yahoo_payload)

            return R(url)

    monkeypatch.setattr(httpx, "Client", C)
    result = run_smoke()
    assert result.ok
    assert seen, "smoke deve fazer GET"
    assert all("range=max" not in url for url in seen)
    yahoo_urls = [u for u in seen if "yahoo" in u or "finance" in u]
    assert len(yahoo_urls) == 1
    assert "PETR4.SA" in yahoo_urls[0]
    assert "range=2y" in yahoo_urls[0]
    assert sum(1 for u in seen if "oplab" in u) == 1
    assert sum(1 for u in seen if "fundamentus" in u) == 1
    assert len(seen) == 3
