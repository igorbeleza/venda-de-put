# Divergências código × planilha original

Auditoria de conformidade das **análises ① Fundamentalista, ② Técnica e ③ Combinada**
contra `carteira_venda_put (4).xlsx` (aba `Ativos Líquidos e Informações` + `Dashboard`).

Status: **parcialmente aplicado** em 2026-08-19. Decisões aceitas: D1 variante B
(bloco vazio anula ScoreF), D3 (ScoreT exige SINAL preenchido), D2 (desempate por
ticker + correção da doc). Não aplicados: D2 por `ROW()`, D4–D8 (registrar / lacuna).
O corpo abaixo é o laudo de 18/08; o código de então já não é o de hoje.

---

## D1 — ScoreF com bloco ausente: soma parcial em vez de anular · ALTA · ①③

### A regra da planilha

`AL2` (ScoreF):
```
=IF($B2="Financeiro",IFERROR(0.5*AH2+0.3*AJ2+0.2*AK2,""),
                     IFERROR(0.4*AH2+0.25*AI2+0.2*AJ2+0.15*AK2,""))
```
Os quatro blocos são `AH`=Qualid, `AI`=Saúde, `AJ`=Valuat, `AK`=Consist, e cada um devolve
**texto vazio** (`""`) quando não há dado. Em Excel, aritmética com texto não é zero: é erro.
`0.25*""` → `#VALUE!`, que contamina a soma inteira, cai no `IFERROR` e devolve `""`.

Consequência: **basta um bloco vazio para o ScoreF inteiro sumir**. Sem ScoreF não há PctF
(`AM2` começa com `IF(AL2="","",…)`), sem PctF não há PctFu (`AN`) nem ScoreC (`AQ`) — o
ativo simplesmente **não existe** para as listas ① e ③. É um "tudo ou nada" deliberado: a
planilha se recusa a ranquear quem não tem o dossiê completo.

Os pesos de cada ramo somam exatamente 1,00 (0,40+0,25+0,20+0,15 e 0,50+0,30+0,20). Isso
importa para o que vem a seguir.

### O que o código faz

`src/venda_de_put/scoring.py:70-89`:
```python
parts = []
if qualid is not None:  parts.append(0.40 * qualid)
if saude  is not None:  parts.append(0.25 * saude)
if valuat is not None:  parts.append(0.20 * valuat)
if consist is not None: parts.append(0.15 * consist)
score_f = sum(parts) if parts else None
```
Cada bloco ausente é **descartado** e a soma segue com os pesos restantes — sem
renormalizar. Só devolve `None` se **todos** os quatro faltarem. É o oposto da planilha.

### Por que isso inverte o ranking (e não só desloca a escala)

Três fatos se combinam:

1. Os blocos são **ranks dentro do setor**, portanto sempre `≥ 1` (1 = melhor).
2. ScoreF é uma média ponderada desses ranks, então um ativo completo tem `ScoreF ≥ 1,00`
   (o mínimo, 1,00, é o ativo que é 1º em tudo).
3. **Menor ScoreF = melhor**, e `scoring.py:178` ordena `pct_f` de forma ascendente.

Como todo peso descartado subtrai `peso × rank ≥ peso`, **remover qualquer bloco só pode
baixar o ScoreF** — ou seja, só pode **melhorar** a posição do ativo. O viés é monotônico e
sempre na mesma direção: **quanto menos dado o ativo tem, melhor ele ranqueia.**

Exemplo A — grupo não-financeiro de 6 nomes, ativo medíocre (rank 4 em tudo) sem o bloco Saúde:
```
planilha:  ScoreF = ""                                     → fora da lista
app:       0,40×4 + 0,20×4 + 0,15×4 = 3,00                 (pesos somam 0,75)
concorrente completo, rank 3,5 em tudo:              3,50
→ 3,00 < 3,50: o ativo incompleto passa na frente do melhor.
```

Exemplo B — o caso patológico. Grupo de 6 nomes, ativo que só tem `Cresc. Rec.5a`, e é o
**pior** do grupo nesse quesito (rank 6):
```
app:  ScoreF = 0,15 × 6 = 0,90
melhor ativo completo possível (1º em tudo): 0,40+0,25+0,20+0,15 = 1,00
→ 0,90 < 1,00: o pior colocado, sem dossiê, toma o 1º lugar da lista ①.
```
E como `better = 0`, seu `PctF = 1/denom` — o menor possível do grupo. Se o SINAL estiver
aceso, ele encabeça a ③ também.

### Quando dispara

A divergência é **no nível do bloco**, não do campo. Faltar *um* campo dentro de um bloco é
tratado igual nos dois lados (`AVERAGE` do Excel ignora vazios; `_mean` em `scoring.py:13-17`
também) — isso **confere**. O problema só aparece quando o bloco inteiro esvazia:

| Bloco | Campos | Some quando faltam |
|---|---|---|
| Qualid | ROE, ROIC, Mrg.Líq | os 3 |
| Saúde | Dív.Líq/Pat, Liq.Corr | os 2 |
| Valuat | P/L, P/VP, EV/EBITDA | os 3 |
| **Consist** | **Cresc. Rec.5a** | **1 campo — gatilho mais provável** |

`Consist` é um bloco de campo único: **um** `Cresc. Rec.5a` ausente no Fundamentus já
dispara o desvio de −0,15×rank. `Saúde` (2 campos) vem logo atrás — Fundamentus deixa
`Dív.Líq/Patrim` e `Liq.Corr` em branco com frequência para holdings e certas estruturas.

Nota: para ativos do grupo `Financeiro`, `saude` é `None` por construção
(`scoring.py:58-59`) mas o ramo financeiro não usa esse bloco — correto, sem divergência aí.

### Estado atual

**Latente, não ativo.** Nos dados de hoje todos os VLOOKUP resolveram e nenhum bloco está
vazio. E **nenhum teste cobre o caso**: `tests/fixtures/excel_ativos.json` tem 86 linhas,
todas completas. O desvio aparece silenciosamente na primeira vez que o Fundamentus omitir
um campo — sem erro, sem log, só uma lista errada.

### Decisão pendente

1. **Replicar o Excel** — qualquer bloco vazio ⇒ `score_f = None`, ativo fora. Fidelidade
   máxima; listas encolhem quando a fonte falha.
2. **Renormalizar** — dividir pela soma dos pesos presentes (`0,75` no exemplo A → 4,00).
   Mantém o ativo, elimina o viés, mas é regra nova que a planilha não tem.
3. **Manter** e assumir como melhoria deliberada — **não recomendado**: hoje o efeito não é
   neutro, é um prêmio sistemático à falta de dado.

### D1 simulada — impacto medido nas análises ①②③

> **Procedência dos dados.** A primeira rodada usou `tests/fixtures/excel_ativos.json` — que é
> o retrato da planilha, não do mercado. Refeita em 2026-08-18 contra a **produção na VPS**,
> lida por `GET /venda-de-put/api/{ativos?calculo=1,dashboard,dados}` (somente leitura; nenhum
> `POST /api/scrape` ou `/api/refresh` foi disparado). Snapshot `generated_at`
> `2026-08-18T16:00:12-03:00`, `stale: false`, carimbos ok nas quatro fontes; Fundamentus de
> 14:05. 86 ativos, 994 linhas cruas. **Os números abaixo são os de produção**; os da fixture
> ficaram anotados onde divergem.
>
> Controle de fidelidade: reconstruí `AssetInput` a partir das linhas cruas e reexecutei o
> pipeline — a variante A reproduz as três listas da VPS **ticker a ticker**. O simulador é fiel.

Três variantes do combinador, com o **resto do pipeline intacto** (`score_fundamentals` real,
`apply_technical` real, `build_lists` real):

| | Variante | Regra do ScoreF |
|---|---|---|
| **A** | atual (código de hoje) | `sum(pesos presentes)` — sem renormalizar |
| **B** | "nova" = planilha | qualquer bloco ausente ⇒ `None`, ativo fora |
| **C** | renormalizada | `sum(pesos presentes) / soma dos pesos presentes` |

#### Resultado com os dados de produção: **as três são idênticas**

| Lista | A (antigo) = **o que está no ar** | B (novo/Excel) | C | Δ |
|---|---|---|---|---|
| ① Fundamentalista | PSSA3, ISAE4, PETR4, BBDC3, CMIN3, VIVA3, SBSP3, CURY3, RENT3, BEEF3 | *idem* | *idem* | **nenhuma** |
| ② Técnica | CSMG3, JHSF3, GGBR4, BBSE3, TUPY3, ENEV3, POMO4, LREN3, USIM5, BBDC4 | *idem* | *idem* | **nenhuma** |
| ③ Combinada | JHSF3, CSMG3, BBSE3, GGBR4, ENEV3, TUPY3 *(6 nomes)* | *idem* | *idem* | **nenhuma** |

Motivo: **nenhum dos 86 ativos perde um bloco que o seu ramo use**. `score_f` e `pct_f` são
não-nulos nos 86. Sem bloco vazio, A, B e C são aritmeticamente a mesma coisa — corrigir D1
hoje é uma mudança de **zero impacto observável**.

> A ③ **não** está vazia em produção (6 nomes) — a fixture da planilha é que dava ③ vazia, por
> não ter nenhum SINAL aceso. Isso não muda a conclusão de D1, mas corrige a leitura anterior:
> a lista ③ existe e é curta (< 10), como o Excel também admite.

**Por que está latente — e não é sorte.** Os 14 ativos com bloco vazio são exatamente os 14
`Financeiro`, e o bloco vazio é `Saúde` — que o ramo financeiro **não usa** (pesos 0,50/0,30/0,20
sobre Qualid/Valuat/Consist, soma 1,00). É vazio por construção, não por falta de dado.

A causa estrutural é o formato da fonte: o Fundamentus publica **`0,00`, não vazio**, quando não
tem o indicador. Nos 86 do universo, `None` aparece **zero vezes** nos nove campos; o que existe
é zero — 10 ativos com `EV/EBITDA` 0, 11 com `Mrg.Líq` 0, 10 com `Liq.Corr` 0, 10 com `ROIC` 0,
11 com `Dív.Líq/Pat` 0, 4 com `Cresc.Rec.5a` 0. Zero **não** é ausência para `_mean` nem para os
`_rank_*`, então o bloco nunca colapsa. E a planilha come o mesmo `0,00` do mesmo lugar — a
paridade se mantém por acidente de formato, dos dois lados.

Some-se a isso que `_mean` ignora `None` individual (paridade com `AVERAGE`): um campo faltando
não zera o bloco. Para D1 disparar é preciso o **bloco inteiro** sumir — `Qualid` exige perder
ROE+ROIC+Mrg.Líq, `Valuat` exige P/L+P/VP+EV/EBITDA, `Saúde` exige Dív.Líq/Pat+Liq.Corr. Só
**`Consist` é bloco de campo único** (`Cresc.Rec.5a`): é o gatilho realista.

Mas `None` é possível, e a prova está nos dados de hoje: **9 das 994 linhas** trazem
`Dív.Líq/Pat = None` — `PITI4`, `GPAR3`, `BSGR3`, `BBTG11`, `SASG3`, `CCTY3`, `ICPI3`, `SLCP3`,
`DUFB11`. Todas fora do universo, todas com `liq_2meses ≈ 0` e `patrim_liq = 0`: micro-caps sem
put líquida, que o filtro de liquidez nunca deixaria entrar. **O gatilho existe e está contido
na cauda ilíquida** — não é impossível, é improvável enquanto o universo for o de hoje.

Dois pontos que a simulação também fecha:

- **A lista ② é imune a D1 por construção** — `ScoreT` depende só de preço/MM200/IFR/Boll Inf,
  nunca de `ScoreF`. Nenhuma correção em D1 pode movê-la. Confirmado: idêntica nas três variantes.
- **A ③ só é alcançável por D1 via `PctF`** (`ScoreC = PctF`), e só entre os que já têm SINAL
  aceso — em produção, 6 ativos.

#### Sensibilidade: o que acontece quando um bloco *falta*

Como o cenário real não exercita o bug, medi a **falha realista**: um ticker por vez perde um
bloco (86 simulações independentes), tudo o mais constante.

**Bloco `Consist`** — basta o Fundamentus omitir `Cresc. Rec.5a` de **um** papel:

| Ticker | Grupo | Posição real | Com A (antigo) | Com B (novo) |
|---|---|---|---|---|
| B3SA3 | Financeiro | 62º | **1º** | fora da lista |
| ITSA4 | Financeiro | 57º | **1º** | fora da lista |
| BBSE3 | Financeiro | 47º | **1º** | fora da lista |
| ABCB4 | Financeiro | 42º | **1º** | fora da lista |
| SANB11 | Financeiro | 37º | **1º** | fora da lista |
| BRSR6 | Financeiro | 17º | **1º** | fora da lista |
| BBDC4 | Financeiro | 11º | **1º** | fora da lista |
| TAEE11 | Utilities | 13º | **2º** | fora da lista |
| PETR3 | Petróleo e Gás | 24º | **3º** | fora da lista |
| RECV3 | Petróleo e Gás | 12º | **3º** | fora da lista |
| CXSE3 | Financeiro | 68º | **6º** | fora da lista |
| LREN3 | Varejo | 19º | **6º** | fora da lista |
| JHSF3 | Construção Civil | 36º | **8º** | fora da lista |
| DIRR3 | Construção Civil | 21º | **8º** | fora da lista |
| VAMO3 | Transporte e Log. | 52º | **9º** | fora da lista |
| MOTV3 | Transporte e Log. | 22º | **9º** | fora da lista |
| SLCE3 | Agro e Alimentos | 45º | **10º** | fora da lista |
| ABEV3 | Agro e Alimentos | 28º | **10º** | fora da lista |

**18 dos 86 ativos invadem o top-10 da ① perdendo um único campo** (na fixture eram 14 — a
produção é mais frágil, não menos). Maior salto absoluto: `CXSE3`, 68º → 6º (**+62 posições**);
depois `BBAS3` 72º → 11º e `B3SA3` 62º → 1º (**+61**). Sete dos dezoito assumem o **1º lugar**.

Financeiros dominam porque lá `Consist` pesa 0,20 (vs 0,15) — quanto maior o peso descartado,
maior o prêmio indevido. Perder `Cresc.Rec.5a` num financeiro é abrir mão de 20% do critério e
ser recompensado com a liderança da lista.

**Bloco `Saúde`** — os números deste parágrafo são da **fixture da planilha**, não da
produção: **10 dos 72** invadem o top-10 (método: apagar o insumo e re-ranquear) —
`MOVI3`, `RENT3`, `JHSF3`, `CPFE3`, `PETR3`, `ABEV3`, `DIRR3`, `SAPR11`, `TAEE11`,
`PETR4`. Maior salto na fixture: `MULT3`, 82º → 21º. Na VPS 16:00 o MULT3 é 23º e
permanece 23º; invasores de produção são 13 (mesmo método) ou 16 (zerar o bloco sem
re-ranquear). A tabela Consist logo acima **é** de produção.

Em todos os casos a variante B faz a coisa certa e óbvia: **o ativo sai da lista**, como na
planilha. Não há caso em que A acerte e B erre.

#### Conclusão

Corrigir D1 é **seguro agora e caro depois**: não altera nenhuma das três listas em produção, e
evita que a primeira omissão do Fundamentus promova um ativo de 68º para 6º — ou de 62º para 1º
— sem nenhum sinal de erro. A janela para aplicar a correção sem discussão sobre resultado é
exatamente esta.

Duas ressalvas honestas sobre o alcance da medição:

1. É **um** snapshot (18/08 16:00), não uma série. Diz que o bug está latente hoje, não que
   nunca disparou. O histórico em `data/snapshots/history/` na VPS responderia isso e não foi
   consultado — exigiria acesso ao disco da máquina, não à API.
2. O que protege hoje é o Fundamentus mandar `0,00` em vez de vazio. Isso é **formato de
   terceiro**, não invariante do sistema: muda sem aviso e sem release nosso.

*Scripts: `.scratch/d1_sim.py`, `.scratch/d1_stress.py`, `.scratch/d1_stress2.py` (fixture) e
`.scratch/vps/d1_vps.py`, `.scratch/vps/d1_stress_vps.py` (produção) — efêmeros, fora do git.
Payloads em `.scratch/vps/*.json`. Nenhum arquivo de produção foi alterado; a VPS só recebeu
três GETs.*

---

## D2 — Desempate por ticker pode trocar o NOME da lista, não só a ordem · MÉDIA · ①③

**Planilha**: `AN2 =IF(AM2="","",AM2+ROW()/100000000)` e
`AR2 =IF(AQ2="","",AQ2+ROW()/100000000)`, consumidos por
`INDEX(...,MATCH(SMALL($AN$2:$AN$87,k),...,0))`. Desempate determinístico pela **linha**.

**Código**: `scoring.py:178` e `:184` — `key=lambda a: (pct_f, a.ticker)` / `(score_c, a.ticker)`.
`FundScore` (`models.py:34-50`) não tem campo `pct_fu`.

**Impacto**: ScoreC = PctF = `(better+1)/denom` **por setor**. Com os tamanhos de grupo da
aba `Setores` (14,13,9,7,7,6,6,5,4,4,3,3,3,2), 58 dos 86 valores possíveis de PctF são
empates exatos — inclusive entre os "primeiros de cada setor", que são justamente os que
entram no top-10. Quando um bloco de empate cruza o corte `[:10]`, o Excel admite o de menor
`ROW()` e o app o de menor ticker → **nome diferente na lista**.

**Agravante documental**: `docs/scoring.md:19` afirma que o empate "só muda a ordem" e é
"caso raro". O empate é **estrutural**, não raro, e pode trocar o ocupante no corte.
Ver também `docs/scoring.md:5,158`, `docs/sdd.md:69`, `CONTEXT.md:85`.

**Decisão pendente**: manter ticker (e corrigir a doc) ou carregar a ordem do universo como
desempate para paridade com a planilha?

---

## D3 — ScoreT admite ativos que a planilha exclui · MÉDIA · ②

*(achado convergente de dois revisores independentes)*

**Planilha** (`AO2`):
```
=IF(OR($M2="",$Q2="",X2=""),"",IF(X2="► VENDER PUT",($M2-$Q2)/$Q2,100+$O2/1000))
```
Exige Preço (M), Boll Inf (Q) **e** SINAL (X) preenchidos em **ambos** os ramos.

**Código**: `scoring.py:146-151` — o `elif tech.ifr is not None` atribui `100 + ifr/1000`
mesmo com `sinal is None` (equivalente a `X2=""`, ex.: sem MM200 ou sem Boll Inf) e sem
exigir Preço/Boll Inf.

**Impacto**: ativo com tendência/timing **indeterminados** entra na ② ordenado por IFR e
ocupa vaga na cauda da lista (`[:10]`, `scoring.py:181`). Nunca afeta o topo (ativos com
sinal valem ~0,00–0,05 e vêm antes dos ~100,0x). Não afeta ① nem ③.

---

## D4 — Origem dos indicadores: RTD/Profit ≠ recálculo local · MÉDIA (lacuna de spec) · ②

**Planilha**: M/N/O/Q/R/S derivam de `AS:AW` =
`RTD("rtdtrading.rtdserver",,$A2&"_B_0",Config!$B$7..$B$12)`. **Q (Boll Inf) é o `MIN` das
três linhas do Bollinger do Profit** (`Config!$B$10 = 12`).

**Código**: `src/venda_de_put/indicators.py` recalcula tudo a partir do Yahoo.

**Impacto**: a planilha **não define** período nem convenção de desvio — `boll_periodos=20`,
`boll_desvios=2.0`, `hv_periodos=21`, `mm_periodos=200`, `ifr_periodos=14`
(`data/config.json`) são premissas do app, não parametrizadas na aba `Config` (que só traz
os códigos RTD 3/1/12/387/45). Diferenças de convenção deslocam o Boll Inf e, por tabela, o
gatilho `preço ≤ Boll Inf × (1+folga)` — ou seja, **o próprio SINAL**. Risco de paridade
numérica, não erro de fórmula.

---

## D5 — Teste de "Financeiro" sensível a maiúsculas · BAIXA · ①③

`IF($B2="Financeiro",…)` em `Z/AB/AC/AF/AL` — comparação de texto do Excel é
*case-insensitive*. `scoring.py:53` usa `a.grupo == "Financeiro"` (igualdade exata, sem
normalização). Grupo gravado como "financeiro"/"FINANCEIRO" faria o app calcular
nROIC/nDív/nLiqC/nEV-EB e aplicar pesos 0.40/0.25/0.20/0.15 onde o Excel usa 0.50/0.30/0.20.

---

## D6 — `rsi_wilder` devolve `None` em série sem variação · BAIXA · ②

`indicators.py:71-72`. A coluna `O` da planilha ainda teria valor. Efeito: o ativo some da ②.

---

## D7 — Grupo sem nenhum ScoreF > 0 · BAIXA (app é mais são) · ①③

`AM2` divide por `COUNTIFS(...,">0")`. Com denominador 0 o Excel gera `#DIV/0!`, que propaga
em AN/AR e **zera as listas ① e ③ inteiras** via `IFERROR`. O app (`scoring.py:108-110`)
apenas omite o ativo. Divergência real, mas o comportamento do app é o desejável — sugere-se
manter e registrar.

---

## D8 — Colunas extras nos cards ② e ③ · BAIXA (previsto) · ②③

`IV Rank` e `IV Percentil` (`web/static/app.js:166-167,174-175`) não existem no Dashboard
(`C30..H30`). Adição já prevista em
`docs/archive/2026-08-prompts-iniciais/PROMPT-DASHBOARD.md:59`. **Nenhuma coluna da planilha
está ausente** no app.

---

## Conferido e correto (sem ação)

- Direção de todos os ranks (`Y/AA/AC/AG` maior-melhor, `AB` menor-melhor) e exclusão de
  "pulados" da contagem.
- Regra "múltiplo ≤ 0 não é barato" → rank = tamanho do grupo + 1 (`AD/AE/AF` ↔
  `_rank_valuation`).
- Caso Financeiro: colunas esvaziadas e pesos 0.5/0.3/0.2.
- Médias `Qualid/Saúde/Valuat/Consist` ignoram vazios (`AVERAGE` ↔ `_mean`).
- `PctF` = `(COUNTIFS "<"&AL2 + 1) / COUNTIFS ">0"` ↔ `better`/`denom`.
- `V` (Tendência), `W` (Timing), `X` (SINAL) — equivalentes literais, inclusive os vazios;
  `ifr_min=10` / `ifr_max=50` / `folga=0.05` = `Config!$B$2:$B$4`.
- **`AO` ramo com sinal = `($M2-$Q2)/$Q2`** — sem `×100` e sem `+IFR/1000`.
  `scoring.py:147` está **correto**; `docs/scoring.md:93` também.
- `T` (IV/HV) ↔ `scoring.py:157-160`.
- IFR de Wilder 14 ✓; MM200 = SMA de 200 ✓; HV = σ amostral (ddof=1) de 21 log-retornos ×
  √252 ✓; Bollinger populacional conforme `docs/sdd.md:25` e `CONTEXT.md:100`.
- `AQ` (ScoreC) ↔ `scoring.py:153-156`, inclusive `pct_f is None` com sinal aceso → excluído.
- `[:10]` sem preenchimento artificial; ③ pode ter <10 nomes, como no Excel.
- Nenhum filtro extra de liquidez/setor/vencimento altera a composição das listas;
  `data/universe.json` tem 86 tickers com a mesma contagem por grupo da aba `Setores`.
- **Aba `Dados` → scraper Fundamentus** (`sources/fundamentus.py`): `_FIELD_ORDER` (22
  posições) bate 1:1 com as 22 colunas da aba (`Papel, Cotação, P/L, P/VP, PSR, Div.Yield,
  P/Ativo, P/Cap.Giro, P/EBIT, P/Ativ Circ.Liq, EV/EBIT, EV/EBITDA, Mrg Bruta, Mrg Ebit,
  Mrg.Líq, Liq.Corr, ROIC, ROE, Liq.2meses, Patrim.Líq, Dív.Líq/Patrim, Cresc.Rec.5a`), e
  todos os `VLOOKUP` da aba `Ativos` (colunas 3,4,6,12,15,16,17,18,21,22) caem nos campos
  certos. `PCT_FIELDS`/100 é consistente com a aba, que guarda fração (`Mrg.Líq -3,6266`,
  `ROE 1,457`) — e como tudo vira **rank ordinal**, a escala não afeta resultado algum.

---

## Cobertura da auditoria — o que NÃO foi conferido

Nem todo cálculo do Excel que virou outra coisa no app foi verificado. Situação por
substituição:

| Origem no Excel | Substituto no app | Status |
|---|---|---|
| Aba `Dados` (colagem Fundamentus) | `sources/fundamentus.py` | ✅ conferido (acima) |
| Dashboard `INDEX/MATCH/SMALL` | `build_lists` (`scoring.py:176-190`) | ✅ conferido (ver D2) |
| `M,N,O,R,S` — RTD/Profit | `indicators.py` sobre Yahoo | ⚠️ só **fórmula**, não número |
| `P,Q` — Bollinger do Profit | `indicators.py` SMA20−2σ | ⚠️ ver D4 |
| `R` (Vol Impl) — RTD | OpLab `iv_current` | ❌ não conferido |
| `AS..BD` — parsing das strings RTD | (sem equivalente) | ❌ nunca examinado |

Detalhando as lacunas:

1. **Paridade numérica RTD × Yahoo nunca foi medida.** Conferi que as *definições* batem com
   `docs/sdd.md` (IFR de Wilder 14, MM200 = SMA 200, HV = σ amostral × √252), mas não comparei
   um único valor calculado contra o que o Profit devolvia. Sem um snapshot do Profit isso é
   inverificável hoje — e é o que sustenta D4.
2. **IV do OpLab × Vol Impl do RTD**: fornecedores diferentes, convenções de superfície
   possivelmente distintas. Entra em `T (IV/HV)` e no card. Nenhuma paridade possível sem
   dado histórico das duas fontes.
3. **Cadeia `AS..BD`** (`Boll_norm`, `Boll_pos1/2`, `Boll_a/b/c/d`, `Preço(raw)`,
   `MM200(raw)`, `IFR(raw)`, `VolImpl(raw)`, `VolHist(raw)`): é o maquinário que fatia a
   string do RTD em números — `SUBSTITUTE(CHAR(160))`, `FIND("/")`, `MID`. Foi lido no dump
   mas **não auditado linha a linha**; o que importa dele é que `Q = MIN` das três linhas de
   Bollinger, e isso já está em D4.
4. **Fora do escopo pedido (análises ①②③)**: `premium.py`, `strike.py`, `calendar_b3.py`,
   `snapshot.py`, `scrape.py`, `paths.py`, `tz.py` e o resto de `web/app.py`. A lógica de
   prêmio-alvo/strike vive em `docs/sdd.md`, não na planilha — a planilha só tem `U (Prêmio?)`
   = `IV>HV`/`IV<HV`, que **foi** conferido.

**Risco de robustez (não é divergência):** `sources/fundamentus.py` faz parsing **posicional**
com `if len(cells) < 22: continue` e nenhuma validação de cabeçalho. Se o Fundamentus inserir
uma coluna, todos os campos deslocam em silêncio e o scoring inteiro fica errado sem erro
algum. Vale um assert de cabeçalho.
