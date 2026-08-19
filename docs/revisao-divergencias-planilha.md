# Revisão independente — contas da planilha × análises ①②③

Segunda auditoria, independente do estudo em `docs/divergencias-planilha.md`
(Claude Opus 5 xhigh). **Nenhuma correção de código foi aplicada.**

Status: **parcialmente aplicado** em 2026-08-19 (D1 variante B, D3, D2 doc).
O laudo abaixo é de 18–19/08, antes da correção. Data da revisão: 2026-08-18 (revisão 19/08).

Autor desta revisão: Grok 4.6. Scripts efêmeros: `.scratch/revisao_contas.py`,
`.scratch/revisao_vps.py`. Fontes lidas, não alteradas:
`carteira_venda_put (4).xlsx`, `src/venda_de_put/scoring.py`,
`tests/fixtures/excel_ativos.json`, `.scratch/vps/{ativos,dashboard,dados}.json`.

---

## Como conferi (não reaproveitei as contas do estudo anterior)

1. Li as **fórmulas** da aba `Ativos Líquidos e Informações` (linha 2) e do
   `Dashboard` (`INDEX/MATCH/SMALL` em `AN`, `AP`, `AR`).
2. Recalculei do zero, em Python, a semântica Excel: `COUNTIFS` dos ranks,
   `AVERAGE` dos blocos, `IFERROR` do ScoreF (tudo-ou-nada), `PctF`,
   `ScoreT` (`OR(M,Q,X)`), `ScoreC`, e `ROW()/1e8` para PctFu/ScoreTu/ScoreCu.
3. Comparei esse recálculo com o **cache** gravado no `.xlsx` (data_only) e
   com `scoring.py` no mesmo input.
4. Remontei as três listas pela regra `SMALL` da planilha e pela regra
   `(nota, ticker)` do app.
5. Só então reli D1–D8. O snapshot da VPS (18/08 16:00) foi usado só para
   checar os números de *impacto* que o estudo anterior atribuiu à produção.

Dois mundos, não misturar:

| Mundo | O que é | ① | ② | ③ |
|---|---|---|---|---|
| Planilha / fixture | cache do `.xlsx` + `excel_ativos.json` | BRSR6, SBSP3, RECV3, PSSA3, CMIN3, VIVA3, ISAE4, CURY3, ECOR3, BEEF3 | VIVT3, PSSA3, TIMS3, CXSE3, USIM5, SAPR11, EQTL3, LREN3, SBSP3, POMO4 | *vazia* (nenhum SINAL) |
| Produção VPS 16:00 | `.scratch/vps/` | PSSA3, ISAE4, PETR4, BBDC3, CMIN3, VIVA3, SBSP3, CURY3, RENT3, BEEF3 | CSMG3, JHSF3, GGBR4, BBSE3, TUPY3, ENEV3, POMO4, LREN3, USIM5, BBDC4 | JHSF3, CSMG3, BBSE3, GGBR4, ENEV3, TUPY3 (6) |

A ② da planilha é só `100+IFR/1000` (ninguém com `► VENDER PUT`). A ② da VPS
abre com 6 SINAIS e completa com IFR baixo. São snapshots diferentes.

---

## Resultado central — as contas da planilha fecham

Nos **86** ativos da aba, o recálculo independente bateu **86/86** com o cache
do Excel e **86/86** com `scoring.py`, em:

nROE, nROIC, nMrgL, nDív, nLiqC, nP/L, nP/VP, nEV/EB, nCrsc,
Qualid, Saúde, Valuat, Consist, ScoreF, PctF, ScoreT, ScoreC, SINAL.

Contagem por grupo = aba `Setores` (14+13+9+7+7+6+6+5+4+4+3+3+3+2). Config
`B2/B3/B4` = 10 / 50 / 0,05. Fixture JSON = cache do Excel.

Aritmética pontual (não-financeiro e financeiro):

```
CMIN3 (VPS): 0,40·1 + 0,25·4,5 + 0,20·4,333… + 0,15·1 = 2,541666…  (= publicado)
PSSA3 (VPS): 0,50·4 + 0,30·9 + 0,20·2 = 5,10                      (= publicado)
ITUB4 (VPS): 0,50·5 + 0,30·10 + 0,20·1 = 5,70                      (= publicado)
```

Exemplos A e B do estudo anterior estão certos:

```
A: 0,40·4 + 0,20·4 + 0,15·4 = 3,00   <   completo 3,5 = 3,50
B: 0,15·6 = 0,90                     <   melhor completo = 1,00
```

### Listas ①②③ — planilha × código (mesmo input da planilha)

| Lista | Excel `SMALL` (ROW) | código `(nota, ticker)` | conjunto | ordem |
|---|---|---|---|---|
| ① | BRSR6, SBSP3, RECV3, **PSSA3, CMIN3**, VIVA3, ISAE4, CURY3, ECOR3, BEEF3 | BRSR6, SBSP3, RECV3, **CMIN3, PSSA3**, VIVA3, ISAE4, CURY3, ECOR3, BEEF3 | igual | só 4º/5º |
| ② | VIVT3 … POMO4 (igual nos dois) | idem | igual | igual |
| ③ | vazia | vazia | igual | — |

O Dashboard cacheado (`B5:B14`, `B18:B27`, `B31:B40`) reproduz exatamente o
`SMALL` que eu remontei. A ③ vazia é o `IFERROR` de `SMALL` sobre `AR` todo
vazio — a planilha admite lista curta, inclusive zero nomes.

Variantes A (código de hoje) / B (Excel tudo-ou-nada) / C (renormalizar):
**idênticas** neste snapshot e no da VPS, porque nenhum dos 86 perde um bloco
que o ramo use. `saude is None` nos 14 financeiros da VPS é o ramo, não falta
de dado.

---

## Veredito por achado do estudo anterior

### D1 — ScoreF com bloco ausente: soma parcial · **CONFIRMO a regra e o viés; CORRIJO o parágrafo da Saúde em produção**

**Regra.** `AL2` é `IFERROR(0,4*AH+0,25*AI+0,2*AJ+0,15*AK)` (ou 0,5/0,3/0,2
no Financeiro). Texto vazio num fator → `#VALUE!` → ScoreF `""` → sem PctF →
fora de ① e ③. O código soma só os pesos presentes, sem renormalizar.
Menor ScoreF é melhor, ranks ≥ 1, então **descartar bloco só pode melhorar**
o ativo. Consist é o gatilho realista (1 campo). Isso tudo confere com a
fórmula e com o código.

**Hoje está latente.** Nos 86 da planilha e nos 86 da VPS: zero `None` nos
nove campos do universo. O Fundamentus manda `0,00`, não vazio. Na raspagem
VPS (994 linhas) o único `None` é `Dív.Líq/Pat` em **9 papéis fora do
universo**, os mesmos que o estudo listou: PITI4, GPAR3, BSGR3, BBTG11,
SASG3, CCTY3, ICPI3, SLCP3, DUFB11. Zeros no universo VPS: EV/EBITDA 10,
Liq.Corr 10, ROIC 10, Dív 11, Mrg.Líq 11, Cresc.Rec.5a 4 — bate.

**Stress Consist na VPS — bate com a tabela do estudo.** 18 invasores do
top-10 da ① (estavam fora, o código os coloca dentro; o Excel os tiraria).
Sete assumem o 1º: BBDC4, B3SA3, ITSA4, BBSE3, ABCB4, SANB11, BRSR6.
CXSE3 68º→6º; B3SA3 62º→1º; BBAS3 72º→11º (fica *fora* do top-10, como o
estudo disse). Lista ② imune. A ③ só se move via PctF entre quem já tem
SINAL.

**Stress Saúde — o estudo misturou fixture com produção.**

| | Estudo (no bloco “produção”) | Recálculo independente |
|---|---|---|
| Invasores Consist VPS | 18 | **18, mesmos nomes e posições** |
| Invasores Saúde VPS | “10 dos 72” (lista com SAPR11, PETR4, RENT3…) | **16** fora-do-top que entram; PETR4 e RENT3 *já estavam* no top-10 |
| “Maior salto MULT3 82º→21º” | apresentado como produção | **é da fixture** (pct_f=1,00, 82º→21º). Na VPS MULT3 é 23º e **permanece 23º** se perder Saúde |

Na fixture, Saúde gera 12 invasores (não 10): o estudo omitiu VAMO3 e MOTV3
nessa lista. O salto MULT3 82→21 na *fixture* está correto.

**Decisão.** Continuo recomendando replicar o Excel (variante B) enquanto o
bug está latente. A janela “zero impacto observável nas três listas” é real
hoje. Não renormalizar sem decisão explícita — é regra nova.

---

### D2 — desempate ticker vs `ROW()` · **CONFIRMO a estrutura; REFINO o impacto**

`AN2 = PctF + ROW()/1e8`. Dashboard usa `SMALL` disso. O app usa
`(pct_f, ticker)`. `FundScore` não tem `pct_fu`. Certo.

Empate é **estrutural**: com os tamanhos da aba `Setores`, 58 dos 86 PctF
colidem entre grupos quando o ScoreF é único dentro do setor. Na VPS sobe
para 59/86 porque ITUB4 e BRSR6 empatam no ScoreF cru (ambos 5,70).
`docs/scoring.md` chamar isso de “caso raro” está errado.

**No corte `[:10]`, o conjunto não muda em nenhum dos dois snapshots.**

- Planilha: empate 1/7 em PSSA3/CMIN3/VIVA3 é 4º–6º. Só troca a **ordem**
  (Excel: PSSA3 então CMIN3 pela linha; app: CMIN3 então PSSA3). 10º BEEF3
  (0,20) ≠ 11º ABCB4 (0,214).
- VPS: mesmo bloco 1/7 em BBDC3/CMIN3/VIVA3 (4º–6º). CURY3/RENT3 (ambos 1/6)
  trocam 8º/9º se o desempate for a linha do universo. 10º BEEF3 ≠ 11º BBDC4.

O estudo está certo ao dizer que *pode* trocar o **nome** se um bloco de
empate cruzar o 10º. Isso **não aconteceu** nem na planilha nem na VPS.
A ③ da planilha está vazia; a da VPS tem 6 ScoreC distintos — D2 não a toca
hoje.

**Decisão.** Manter ticker e corrigir a doc, **ou** carregar a ordem do
universo para paridade com `ROW()`. Não é urgente para o resultado das
listas atuais.

---

### D3 — ScoreT sem SINAL · **CONFIRMO; na VPS já está vivo (1 papel)**

Fórmula `AO2`:

```
=IF(OR($M2="",$Q2="",X2=""),"",IF(X2="► VENDER PUT",($M2-$Q2)/$Q2,100+$O2/1000))
```

Exige Preço, Boll Inf **e** SINAL nos dois ramos. O código, no `elif ifr`,
atribui `100+IFR/1000` mesmo com `sinal is None`.

- Planilha: 0 casos (os 86 têm M, Q e X).
- VPS: **AUAU3** — `mm200` ausente → tendência vazia → SINAL vazio, IFR 41,81,
  `score_t = 100,0418`. O Excel o tiraria da ②. Não entra no top-10 da ②
  (os 6 SINAIS e 4 IFRs menores ocupam as vagas). Confirma o “só a cauda”
  do estudo; deixa de ser só teórico.

① e ③ imunes.

---

### D4 — RTD/Profit ≠ Yahoo · **CONFIRMO como lacuna; sem conta para fechar**

Não comparei um único número Profit × Yahoo: a planilha não guarda o valor
numérico cru do RTD de forma auditável sem o servidor, e o app recalcula
do Yahoo. Convenções (`boll` 20/2 pop, HV 21 amostral, MM200 SMA, IFR Wilder
14) são do app/`docs/sdd.md`, não da aba Config (só códigos RTD 3/1/12/387/45).
`Q = MIN` das três linhas de Bollinger do Profit — diferente de uma banda
única SMA20−2σ. Risco de paridade do SINAL, não erro de fórmula do ScoreT.

---

### D5 — `"Financeiro"` case-sensitive · **CONFIRMO, latente**

Excel `IF($B2="Financeiro")` é case-insensitive. `a.grupo == "Financeiro"`
não é. Os 14 grupos do universo (planilha, `universe.json`, VPS) usam a
grafia exata. Sem desvio hoje.

---

### D6 — `rsi_wilder` sem variação → `None` · **CONFIRMO a leitura do código**

`indicators.py:71-72`. Sem série plana nos dois snapshots. Efeito: some da ②.
Não reexecutei o Wilder contra o Profit.

---

### D7 — denominador PctF = 0 · **CONFIRMO a fórmula; impacto ainda mais vazio**

`AM2` divide por `COUNTIFS(...,">0")` sem `IFERROR`. Se o denominador for 0
e `AL` for numérico, o Excel explode a ①/③ inteiras; o app só omite o ativo.

Na prática o gatilho quase não existe: ScoreF de ranks é sempre ≥ 1,00 quando
calculado. `AL=""` já cai no `IF(AL2="","",…)` — não chega no `#DIV/0!`.
Se um grupo inteiro não tem ScoreF, Excel e app esvaziam só esses nomes e
seguem com os outros. Divergência real só se existisse ScoreF numérico ≤ 0.
Manter o app e registrar, como o estudo sugeriu.

---

### D8 — colunas extras IV Rank / IV Percentil · **fora desta conferência**

Não é conta das análises ①②③. Aceito o “previsto / nenhuma coluna da
planilha ausente” sem reabrir o JS.

---

## O que o estudo anterior acertou e eu também fechei

- Direção dos ranks e “múltiplo ≤ 0 → tamanho+1”.
- Financeiro sem nROIC/nDív/nLiqC/nEV-EB; pesos 0,5/0,3/0,2.
- `AVERAGE` ↔ `_mean` (ignora vazio).
- PctF = `(better+1)/denom` no grupo.
- Tendência / Timing / SINAL, inclusive vazios; `ifr_min/max` e `folga`.
- ScoreT com SINAL = `(M−Q)/Q` **sem** ×100 e **sem** +IFR/1000.
- ScoreC = PctF só com SINAL; senão vazio.
- `[:10]` sem preencher; ③ pode ter < 10.
- Universo 86 = aba `Setores`.
- `_FIELD_ORDER` do Fundamentus 1:1 com a aba `Dados` (não reparsei o HTML
  do site hoje; conferi o código e o payload VPS de 994 linhas).

---

## Achados meus que o estudo não isolou

1. **D3 já disparou na VPS** (AUAU3). Latente na planilha, vivo na produção,
   ainda sem ocupar vaga no top-10 da ②.
2. **D1 Saúde “produção” no estudo anterior está contaminado pela fixture**
   (MULT3 82→21 e a lista de 10 nomes). Consist-produção está limpo.
3. **D2 não troca o conjunto** nos dois snapshots disponíveis — só a ordem
   de empatados *dentro* do top-10. O risco de trocar o 10º nome é real e
   não observado.
4. **Empate intra-setor na VPS:** ITUB4 = BRSR6 = ScoreF 5,70 → +1 ativo
   no bolo de empates (59 vs 58 teóricos).
5. Faixa Excel `$B$2:$B$87` / `$AL$2:$AL$87` está **hardcoded em 86 linhas**.
   Se o universo crescer, a planilha original deixaria de contar o resto.
   O app não tem esse teto. Não é bug do código; é limite da planilha.

---

## O que eu *não* conferi (igual ao estudo, de propósito)

- Paridade numérica RTD/Profit × Yahoo (D4).
- IV OpLab × Vol Impl RTD.
- Cadeia `AS..BD` linha a linha (só o `MIN` das três bandas, já em D4).
- `premium.py`, `strike.py`, calendário, scrape.

---

## Decisões (aplicadas em 2026-08-19)

| # | Proposta | Estado |
|---|---|---|
| 1 | D1 → variante B (bloco vazio anula ScoreF) | **aplicado** |
| 2 | D3 → exigir Preço, Boll Inf **e** SINAL no ScoreT | **aplicado** |
| 3 | D2 → manter ticker **e** corrigir `docs/scoring.md` (“empate raro”) | **aplicado** |
| 4 | D2 alt. → desempate pela ordem do universo (`ROW`) | **não** |
| 5 | D5/D6/D7 → registrar, não mudar comportamento | **registrado** (sem mudança de código) |
| 6 | D4 → aceitar como lacuna de spec; não “corrigir” sem Profit | **registrado** |
| 7 | D1 Saúde do estudo anterior → não usar aqueles 10 nomes / MULT3 82→21 como evidência de produção | **aplicado** no laudo original |

Scripts desta revisão: `.scratch/revisao_contas.py`, `.scratch/revisao_vps.py`.
