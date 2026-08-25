# Plan review (claude opus)

Segunda passada, sobre a spec `2026-08-24-brapi-cotahist-fallback-preco-design.md`, o plano
`2026-08-24-brapi-cotahist-fallback-preco.md` e o código atual do repo. Também confronta a
primeira revisão (`-cmdc-review.md`, ox-alpha, veredito Ready).

**Verdict:** Needs fixes before execution

Dois blockers. O primeiro é um teste que **não pode passar** como escrito (verificado rodando
httpx 0.28.1 do `.venv` do projeto). O segundo é um buraco funcional que faz o bootstrap
Cotahist virar letra morta a partir da segunda raspagem — e nenhum teste do plano o pega.

---

## Blockers

### B1 — `tests/test_brapi.py::test_brapi_lote_so_os_pedidos`: asserção impossível

Plano, Task 2, Step 1:

```python
assert "symbols=PETR4,VALE3" in seen["url"]
```

A implementação do próprio plano monta a query com `params={"symbols": ",".join(tickers)}`.
httpx percent-encoda a vírgula. Verificado no `.venv` deste repo (httpx 0.28.1):

```
URL: https://brapi.dev/api/v2/stocks/quote?symbols=PETR4%2CVALE3
```

A asserção falha sempre. Task 2 Step 4 (“Expected: PASS”) trava, e o subagente TDD vai
concluir que a implementação está errada — quando o errado é o teste. O risco concreto é ele
“consertar” a implementação: montar a URL por concatenação de string, ou trocar `params=` por
`f"{BRAPI_QUOTE}?symbols=..."`, perdendo o escape de qualquer outro parâmetro.

Correção: assertar o valor decodificado, não a string crua.

```python
assert request.url.params["symbols"] == "PETR4,VALE3"
```

E, se quiser manter a checagem de que o token não vaza na URL, `assert "token=" not in
str(request.url)` continua válido. Se a intenção for de fato mandar vírgula literal (a brapi
aceita `%2C`, então não é necessário), isso precisa estar escrito na spec e na implementação,
não só no assert.

**Ox-alpha não viu.** Não há menção a encoding de query em nenhum dos 15 pontos “verificados um
a um”.

---

### B2 — Ticker que já caiu em “sem dado” nunca mais é frio; Cotahist nunca dispara para ele

Plano, Task 4:

```python
prev_tech_early = {a.ticker: a.technicals for a in previous.assets if a.technicals}
frios = [t for t in faltou if prev_tech_early.get(t) is None]
```

Isso é fiel à letra da spec (“o snapshot anterior não tem esse ticker em `assets`, ou
`technicals` é `None`”). O problema é que **`technicals` nunca fica `None`** para um ticker do
universo. `run_scrape` sempre constrói um `TechnicalInput` — no caminho “sem dado” ele sai com
os oito campos `None`, e um dataclass frozen sem `__bool__` é sempre truthy. Verificado
rodando `run_scrape` com price/iv/fund vazios:

```
technicals obj: TechnicalInput(preco=None, mm200=None, ifr=None, boll_inf=None,
                               iv=None, hv=None, iv_rank=None, iv_percentile=None)
bool: True
serialized technicals: {'preco': None, 'mm200': None, ..., 'iv_percentile': None}
```

E `snapshot.py::_technicals` só devolve `None` quando a chave está ausente no JSON — o dict de
nulos volta como `TechnicalInput`, truthy de novo.

Consequência, na ordem em que acontece na vida real:

1. Raspagem 1: Yahoo perde PETR4, brapi sem token/vazio, sem anterior → Cotahist tenta,
   falha (ou nem roda, se `history is None`) → asset gravado com `technicals` de oito nulos.
   É exatamente o cenário do teste 5 do plano (`test_sem_anterior_cotahist_falha_sem_spot_sem_dado`).
2. Raspagem 2: Yahoo perde PETR4 de novo. `faltou = ["PETR4"]`. `prev_tech_early["PETR4"]`
   existe e é truthy → **`frios` sai vazio** → `history.fetch_history` nunca é chamado.
3. No loop do técnico: `candle is None`, `prev is not None` → reusa mm200/ifr/boll/hv que são
   todos `None`. “Sem dado” para sempre.

O bootstrap de histórico existe justamente para tirar um ticker desse estado, e ele fica
trancado do lado de fora. Nenhum teste do plano faz a terceira rodada que exporia isso — o
teste 5 grava o snapshot venenoso e para ali.

Correção: definir frio por técnico **útil**, não por `technicals is None`. Ex.:

```python
def _frio(prev: TechnicalInput | None) -> bool:
    return prev is None or (prev.mm200 is None and prev.preco is None)
```

(escolher os campos com a spec; o par `mm200`/`preco` é o mínimo que o passo 4.2 da spec reusa).
Isso muda a spec — a linha da seção **CotahistBootstrap** e o passo 3 do **Fluxo** precisam
dizer “sem técnico anterior aproveitável”. E precisa de um teste de terceira rodada:
snapshot “sem dado” + Yahoo falho + Cotahist ok → série montada, `frios == ["PETR4"]`.

Cuidado ao corrigir: o `elif prev is not None` do loop do técnico usa o mesmo `prev_tech`.
Se um ticker virar frio e o Cotahist trouxer série, o ramo `if candle is not None` já tem
precedência, então não há conflito. Mas se o Cotahist falhar, o `elif` continua entrando com
o técnico de nulos — comportamento correto (“sem dado”), só não pode mais bloquear o `frios`.

**Ox-alpha não viu.** A revisão afirma que “Overlay de preço no técnico anterior … ramo do
candle tem precedência” — verdade, mas isso é o passo 4; o bug está no passo 3, na definição
de `frios`.

---

## Non-blocking

- **`cli_scrape` já tem uma local chamada `history`.** `scrape.py:317` faz
  `history = snapshot_history(root)` e `scrape.py:364` faz
  `write_snapshot(snap, current, history, archive_if_1600=True)`. Task 5 manda acrescentar
  `history=CotahistBootstrap(root / "cotahist", now=now)` na chamada de `run_scrape` — como
  kwarg funciona, mas o plano não avisa da colisão. Se o implementador criar um local
  (`history = CotahistBootstrap(...)`, leitura natural do texto “instancia as duas fontes”),
  `write_snapshot` passa a receber um `CotahistBootstrap` como diretório de histórico e o
  arquivamento quebra em silêncio. O plano deveria mandar renomear a local para `history_dir`
  (ou nomear a fonte `cotahist=`), e o teste de Task 5 não pega isso porque só olha string
  de fonte. Ox-alpha não viu.

- **Cotahist: ZIP corrupto derruba tudo, e um 200 ruim envenena o cache.** `_read_zip` não tem
  try/except: `zipfile.BadZipFile` num ZIP truncado, ou `IndexError` em `zf.namelist()[0]`
  num ZIP vazio, sobe de `fetch_history`. O `try/except` de `run_scrape` segura o processo,
  mas joga fora as séries de **todos** os frios e dos **dois** anos, não só do arquivo ruim.
  Pior: `_zip_bytes` faz `path.write_bytes(resp.content)` antes de validar, então um 200 com
  HTML de erro da B3 sobrescreve o ZIP bom em cache — a partir daí o ano corrente fica
  permanentemente quebrado até alguém apagar `data/cotahist/` à mão. A linha “ZIP corrupto /
  TXT ausente → frios sem série” da tabela de Erros da spec só é satisfeita por acidente, e
  não tem teste. Sugestão: validar com `zipfile.is_zipfile(io.BytesIO(content))` antes de
  gravar, e envolver `_read_zip` num try/except por ano.

- **`docs/sdd.md` linha 95 e `AGENTS.md` linha 20 viram mentira e nenhuma task as corrige.**
  O SDD diz hoje: *“Nada disso existe no código hoje: não há `sources/brapi.py` nem
  `sources/cotahist.py`, o Yahoo tenta 2 vezes por ticker, não há `VENDA_DE_PUT_BRAPI_TOKEN`
  no `.env.example` e a UI não tem faixa de preço.”* Task 7 só manda mexer na tabela de
  módulos e acrescentar um bullet em Coleta. `AGENTS.md:20` (*“desenhado, ainda sem código”*)
  nem aparece no File map, e `AGENTS.md` é a leitura obrigatória número um do repo.

- **Task 4, Step 1: os testes 1–6 estão só em prosa** (ox-alpha já apontou; concordo e reforço).
  Dois deles dependem de detalhes que a prosa não fixa: o teste 4 fala em “timestamps de
  ontem” sem dizer o valor, e o teste 2 afirma “history não chamado” sem dizer que um
  `FakeHistory` precisa ser passado para essa afirmação significar alguma coisa. Escrever os
  seis por extenso antes de executar.

- **Frio + Cotahist ok + sem spot brapi continua sem teste** (ox-alpha apontou como
  non-blocking; concordo com o item, discordo do peso — ver seção Ox-alpha). É o único caminho
  em que a série Cotahist chega inteira ao cálculo **e** o aviso acende, e é a combinação
  central da feature.

- **`test_brapi_sem_token_nao_faz_get` passa `token=""` explícito** (ox-alpha). Concordo:
  `BrapiSpotHttp(client=client)` com `monkeypatch.delenv` cobriria o caminho de produção.

- **`parse_yahoo_chart` não preenche o novo `CandleSeries.timestamps`.** O campo nasce
  meio-populado: só séries Cotahist o têm. Não é bug hoje (a série Yahoo nunca reentra em
  `apply_spot_as_last_period`), mas é armadilha para o próximo que escrever
  `apply_spot_as_last_period(cs.closes, px, cs.timestamps or None, now)` sobre uma série Yahoo
  e receber `None` silenciosamente, caindo no ramo “anexa” em vez de “troca a barra de hoje”.

- **O overlay quebra o invariante `len(timestamps) == len(closes)`.** Task 3 crava esse
  invariante num assert (`test_cotahist_cache_hit_nao_baixa`), e Task 4 o viola:
  `replace(cs, closes=closes, preco=px)` deixa `timestamps` com o tamanho antigo quando o
  spot é anexado. Inócuo hoje (ninguém lê depois), mas ou o `replace` atualiza `timestamps`
  ou o invariante não devia ser afirmado como invariante.

- **`max_52`/`min_52` do Cotahist mentem o nome.** A spec manda `max`/`min` **dos fechamentos
  da série**, e a série é de ~2 anos — não de 52 semanas. O Yahoo entrega o campo real
  (`fiftyTwoWeekHigh`). Depois de um bootstrap Cotahist, os dois números da tela mudam de
  significado sem aviso. Ox-alpha notou a parte do spot não entrar no `max_52`, não a parte
  da janela. É a spec que está frouxa aqui, não o plano.

- **`timeout=60.0` no Cotahist vs. “timeout 30s como as outras fontes” na spec** (ox-alpha).
  Concordo; alinhar a frase da spec, já que o ZIP anual justifica o desvio.

- **`if self._owns and self._client is None` redundante** e **client recriado a cada
  `fetch_spots`** (ox-alpha). Concordo, cosmético. Note que no Cotahist isso cria um client
  novo por ano (dois por raspagem fria).

- **Guarda `no tickers` roda depois do fetch/fallback** (ox-alpha). Concordo, cosmético; hoje
  o CLI nunca passa universo vazio.

- **`prev_tech_early` duplica `prev_tech`** (ox-alpha). Concordo. Vale notar que
  `prev_tech_early` é montado **dentro** do bloco `yahoo`, então num retry `--from-step oplab`
  ele nem existe — mas `spots` fica `{}` e o overlay cai em `prev.preco`. Correto por sorte;
  merece um comentário no código.

- **`.gitignore data/cotahist/` cobre “.TXT extraídos” que nunca existem.** `_read_zip` lê o
  ZIP em memória; nada é extraído para disco. A frase da spec está a mais.

- **Task 6: o teste seta `app.state.snapshot = None` mas não `snapshot_mtime`.** Funciona
  porque `get_snap` testa `snapshot is None` primeiro, mas os testes existentes de
  `test_api.py` (linhas 169–170, 181–182) setam os dois. Seguir o padrão da casa.

- **Testes de Task 5 são asserções sobre texto-fonte**, não sobre comportamento
  (`assert "spot=BrapiSpotHttp()" in src`). Passam com a fonte instanciada errado (parâmetros
  trocados, cache_dir errado). Mesmo padrão de `test_refresh_import_guard`, então é aceito na
  casa — mas não confunda com cobertura.

**Coisas que confirmei e estão certas** (para o implementador não perder tempo): offsets
Cotahist batem com o layout real da B3 e com o helper `_line`; os quatro caminhos de cache têm
teste; a exceção de `price.fetch` não aborta o fallback; `yahoo_ok` é fixado antes de
`series.update(hist)`; `CandleSeries` nunca é serializado, então `timestamps` com
`default_factory` não mexe no schema do snapshot e os construtores posicionais de 6 args dos
testes atuais continuam válidos; a assinatura de `apply_spot_as_last_period` bate; nenhum teste
existente afirma `ok=True` com cobertura parcial, então a saída da regra da metade não quebra
`test_yahoo_half_tickers_...`; `test_smoke_offline` faz 1 GET no Yahoo (sucesso na primeira
tentativa), logo `range(3)` não mexe no `assert len(seen) == 3`; a fixture `data_dir` de
`test_api.py` cobre os três tickers, então o carimbo yahoo continua `ok`; `__main__.main` chama
`load_dotenv()` antes de `cli_scrape`; `passos_from_stamps` propaga `stamp.error` sem código
novo; `app.py` já importa `scrape_progress` e a guarda AST (`endswith("scrape")`) não o pega;
`premio-tape` e `class="lists"` aparecem uma vez cada no `index.html`, e `.hidden` e
`--warn/--warn-ink/--warn-tint` existem no CSS nos dois temas; `FakePrice` devolve dict novo,
então `series.update(hist)` não contamina fixture compartilhada; `create_app` migra o
`current.json` legado para `snapshots/current.json`, então `read_snapshot(app.state.snapshot_path)`
do teste de Task 6 funciona (padrão já usado em `test_api.py:145`).

---

## Spec coverage gaps

- **Erros, “ZIP corrupto / TXT ausente”** — sem task e sem teste; só é satisfeito de raspão
  pelo `try/except` externo, com dano colateral (ver Non-blocking). Ox-alpha não listou.
- **Erros, “Ticker não aparece no Cotahist → sem série naquele papel”** — sem teste dedicado.
  `parse_cotahist_text` deleta a chave vazia, mas nada crava isso.
- **Erros, “Brapi 401 / 403 / 429 / 5xx → lote inteiro sem spot”** — só 429 tem teste. Os
  outros caem no mesmo `raise_for_status`, então é equivalência óbvia; anotado por completude.
- **Testes, “Scrape: sem anterior, Cotahist série + spot brapi”** tem teste (Task 4 #4), mas o
  gêmeo **sem** spot (série Cotahist sozinha, aviso aceso) não — e é o que define a regra
  “Cotahist sozinho não é vivo”. Ox-alpha listou como non-blocking.
- **Testes, “passo Config `falhou` com a frase no `erro`”** — verificado no carimbo (Task 4),
  nunca em `GET /api/scrape/status`. Ox-alpha listou; concordo, é um assert barato.
- **Testes, “Snapshot antigo: aviso sai só do carimbo `yahoo`; load sem campo extra”** — sem
  task. Satisfeito por construção (o schema não muda). Ox-alpha listou; concordo.
- **Autoridade de vocabulário / “atualizar `docs/sdd.md`”** — Task 7 cobre a tabela de módulos
  e a seção Coleta, mas deixa de pé a prosa que afirma o contrário (`sdd.md:95`), e não toca
  `AGENTS.md:20`. `AGENTS.md` não está no File map do plano.
- **Fluxo, passo 3, “ticker frio”** — a definição da spec (`technicals` é `None`) é
  inalcançável na prática. Ver B2: a spec precisa mudar junto com o plano.

---

## Ox-alpha

**Discordo do veredito Ready.**

Misses (nada na revisão dela toca nestes pontos):

- **B1**, encoding de vírgula em query string httpx — um teste do plano que não pode passar.
  A revisão lista 15 verificações e nenhuma cobre o formato real da URL montada por `params=`.
- **B2**, `frios` nunca reaparece depois de um ciclo “sem dado”. A revisão examina o passo 4
  (overlay, precedência do candle) e conclui “fiel à spec”, mas não segue o passo 3 até a
  segunda raspagem. A afirmação “Cotahist-sozinho não é vivo e acende o aviso — fiel à spec”
  está certa e é irrelevante para o bug.
- Colisão do nome `history` em `cli_scrape` (local já existente, usada em `write_snapshot`).
- `_read_zip` sem try/except e cache envenenado por 200 inválido; a linha “ZIP corrupto” da
  tabela de Erros não tem dono.
- `sdd.md:95` e `AGENTS.md:20` afirmando que a feature não existe — a revisão diz que “nenhuma
  seção da spec ficou órfã”, mas a spec manda explicitamente atualizar o SDD e a prosa
  contraditória fica.

Over-dismissal:

- **“Combinação sem teste: ticker frio + Cotahist ok + brapi vazio”** está listado como
  non-blocking com o tom de completude. É o caminho principal da feature (é para isso que o
  Cotahist existe) e é o único que combina série nova + aviso aceso. Com B2 corrigido, ele
  vira o teste que prova que o bootstrap funciona. Merece ser um teste obrigatório da Task 4,
  não uma sugestão.

Concordo integralmente com estes pontos dela, que reverifiquei no código: offsets Cotahist,
os quatro caminhos de cache, exceção de `price.fetch`, `yahoo_ok` vs. `series.update(hist)`,
overlay sem recomputar indicadores, `CandleSeries.timestamps` com `default_factory` não
quebrando construtores posicionais nem o snapshot, assinatura de `apply_spot_as_last_period`,
saída da regra da metade sem quebrar teste existente, `PRICE_NOTICE` em `scrape_progress.py`
(módulo que `app.py` importa sem violar a guarda AST), imports de `cli_scrape` dentro da
função, token chegando via `__main__.load_dotenv()` e nunca em query string, âncoras do
`index.html` e variáveis `--warn*` nos dois temas, reescrita de `sources/__init__.py`
preservando as exportações, e a guarda de universo vazio.

Também concordo com todos os nove itens non-blocking dela; oito deles reapareceram acima com
observações adicionais (timeout 60s, `token=""` no teste, client por chamada, `self._owns`
redundante, `prev_tech_early` duplicado, guarda `no tickers`, `max_52` sem o spot, testes 1–6
em prosa).

---

## O que fazer antes de executar

1. Corrigir a asserção de `test_brapi_lote_so_os_pedidos` (B1).
2. Redefinir “ticker frio” na spec **e** no plano por técnico anterior aproveitável, e
   acrescentar o teste de terceira rodada (B2).
3. Acrescentar à Task 3: validar o ZIP antes de gravar no cache e try/except por ano no
   `_read_zip`, com teste de ZIP corrupto.
4. Acrescentar à Task 5 a instrução de renomear a local `history` de `cli_scrape`.
5. Acrescentar à Task 7 as linhas contraditórias de `docs/sdd.md:95` e `AGENTS.md:20`, e pôr
   `AGENTS.md` no File map.
6. Escrever por extenso os testes 1–6 da Task 4, mais o teste “frio + Cotahist ok + sem spot”.
