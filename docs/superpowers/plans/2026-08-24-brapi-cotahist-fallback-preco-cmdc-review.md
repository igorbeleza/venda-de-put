# Plan review (cmdc ox-alpha)

**Verdict:** Ready

## Blockers

Nenhum. Os pontos de caça listados no dispatch foram verificados um a um contra o código atual:

- Offsets Cotahist 1-indexados (`TIPREG` 1–2, `DATA` 3–10, `CODBDI` 11–12, `CODNEG` 13–24, `TPMERC` 25–27, `PREULT` 109–121 ÷ 100) são consistentes entre spec, plano e helper `_line` do teste (`chars[0:2]`, `[2:10]`, `[10:12]`, `[12:24]`, `[24:27]`, `[108:121]`).
- Cache Cotahist: ano anterior sempre reusado; ano corrente revalidado por `st_mtime` ≤ 1 dia; GET falho cai no ZIP velho; 404 sem cache omite o ticker — os quatro caminhos têm teste.
- Exceção de `price.fetch` não aborta brapi/Cotahist (`try/except` com `series = {}` antes de `yahoo_ok = set(series)`), como a spec exige.
- `yahoo_ok` nunca mistura série Cotahist (`series.update(hist)` acontece depois de `yahoo_ok = set(series)`); conjunto vivo = `yahoo_ok ∪ spots`, então Cotahist-sozinho não é vivo e acende o aviso — fiel à spec.
- Overlay de preço no técnico anterior (`spots.get(fund.ticker, prev.preco)`) não recomputa indicadores; ramo do candle tem precedência sobre o overlay, então quem ganhou série Cotahist+spot calcula tudo na série.
- `CandleSeries.timestamps` com `default_factory=list` após `collected_at`: os construtores posicionais de 6 args dos testes atuais continuam válidos; `Snapshot` nunca serializa `CandleSeries` (só `TechnicalInput`, cadeias e fundamentus), então `snapshot.py` nem precisa entrar no File map.
- `apply_spot_as_last_period(cs.closes, px, cs.timestamps or None, now)` casa com a assinatura real (`closes, preco, timestamps, now`); séries Cotahist sempre têm timestamps com `len == len(closes)`.
- Regra da metade sai sem quebrar teste existente: `test_yahoo_half_tickers_stamps_failed_and_merges_previous` continua válido porque 1/3 coberto sem brapi também acende o aviso na regra nova; nenhum teste atual afirma `ok=True` com cobertura parcial.
- Frase única Config/Dashboard via constante `PRICE_NOTICE` em `scrape_progress.py`, módulo que `app.py` já importa; `passos_from_stamps` propaga `stamp.error` para o passo `falhou` sem código novo.
- Guarda de import: `cli_scrape` instancia `BrapiSpotHttp`/`CotahistBootstrap` dentro da função (padrão já usado para Yahoo/OpLab/Fundamentus), então `app.py` continua limpo e `test_refresh_import_guard` se aplica só ao fonte do app.
- Token chega ao subprocesso: `__main__.py` chama `paths.load_dotenv()` antes de `cli_scrape`, e `BrapiSpotHttp(token=None)` lê `VENDA_DE_PUT_BRAPI_TOKEN` na construção. Nunca vai em query string.
- Faixa `#price-notice` entra entre `.premio-tape` e `.lists` (ambos presentes uma vez em `index.html`); variáveis `--warn-tint/--warn-ink/--warn` existem nos temas claro e escuro (`app.css` linhas 22–24 e 87–89); badge `dado velho` (`is_stale`) é elemento separado — conceitos não colidem.
- Reescrita de `sources/__init__.py` no Task 2 preserva as exportações atuais (`ChainSource` nunca foi exportado no nível do pacote; `scrape.py` importa de `sources.types` direto).
- Universo vazio mantém a guarda `no tickers` com carimbo falho — o plano trata o caso antes do teste de cobertura vivo, evitando `ok=True` com `any([])`.

## Non-blocking

- Task 4, Step 1: os testes 1–6 estão descritos só em prosa, sem código, ao contrário dos testes 7–8 e do padrão do resto do plano. Um subagente TDD pode derivar nas asserções. Escrever os seis por completo antes de executar reduz risco.
- Combinação sem teste: ticker frio + Cotahist ok + brapi vazio (ou sem spot). Deveria produzir série com `preco` = último fechamento Cotahist **e** aviso aceso (ticker não-vivo). A tabela de erros da spec cobre a falha do GET, mas o sucesso sem spot ficou sem teste dedicado.
- `tests/test_brapi.py::test_brapi_sem_token_nao_faz_get` passa `token=""` explícito — exercita o caminho de token vazio, não o do env. Construir `BrapiSpotHttp(client=client)` sem argumento com `monkeypatch.delenv` cobriria o caminho real de produção.
- `sources/cotahist.py` usa `timeout=60.0`; a spec pede “timeout 30s como as outras fontes”. Desvio defensável (ZIP anual é grande), mas convém alinhar a frase da spec ou registrar a exceção.
- `BrapiSpotHttp.fetch_spots` cria e fecha um `httpx.Client` novo a cada chamada quando nenhum é injetado. Funcional; guardar o cliente como atributo evaria reconnects por ciclo (um GET por raspagem hoje, custo baixo).
- Condição redundante no `finally`: `if self._owns and self._client is None` — `self._owns` já implica `self._client is None`. Simplificar para `if self._owns` nos dois sources novos.
- `run_scrape` passa a montar `prev_tech_early` dentro do bloco yahoo além do `prev_tech` já computado adiante. Duplicação inofensiva; um dict só bastaria (o segundo é calculado depois das fontes, daí talvez a intenção).
- A guarda de universo vazio agora roda depois do `fetch`/fallback sobre lista vazia — chamaria fontes à toa se o universo fosse vazio. Hoje o CLI nunca passa universo vazio; mover a guarda para antes do fetch seria mais limpo.
- `max_52/min_52` das séries Cotahist não incorporam o spot aplicado como último período (e o Yahoo usa o meta do próprio chart). Comportamento consistente entre fontes; só notar que o spot acima da máxima do histórico não sobe o `max_52`.

## Spec coverage gaps

- Spec, Testes: “Snapshot antigo: aviso sai só do carimbo `yahoo`; load sem campo extra.” Nenhuma task/teste dedica-se a isso — satisfeito por construção (schema do snapshot não muda). Opcional documentar no plano que não há campo novo a migrar.
- Spec, Aviso: “passo `yahoo` `falhou` com a frase no `erro`” é verificado no carimbo (Task 4), mas nenhum teste puxa `GET /api/scrape/status` com carimbo falho para cravar a frase na saída da API. `passos_from_stamps` é código existente e confiável; um assert barato em `test_api.py` fecharia o ciclo.
- Restante da checklist da spec tem tarefa correspondente (self-review do plano confere com a leitura; nenhuma seção da spec ficou órfã).
