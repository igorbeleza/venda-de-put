# Segunda opinião — auditoria do estudo `docs/revisao-divergencias-planilha.md`

**Status:** parcialmente aplicado em 2026-08-19 (D1 variante B, D3, D2 doc). O laudo abaixo é de 18/08, antes da correção.
**Data:** 2026-08-18 · **Autor:** Claude Opus 5 (terceiro revisor)
**Escopo original:** *analysis only*. Nenhuma linha de `src/`, `tests/`, `data/` ou de outros docs foi tocada na revisão.
**Objeto:** o estudo **NOVO** (`docs/revisao-divergencias-planilha.md`, Grok 4.6) contra o estudo
**ANTIGO** (`docs/divergencias-planilha.md`), ambos conferidos contra a fonte, não entre si.

Fontes lidas (nenhuma alterada): `carteira_venda_put (4).xlsx` (abas `Ativos Líquidos e Informações`,
`Dashboard`), `src/venda_de_put/scoring.py`, `src/venda_de_put/indicators.py`,
`tests/fixtures/excel_ativos.json`, `.scratch/vps/{ativos,dashboard}.json` (snapshot 18/08 16:00).
Scripts efêmeros desta revisão: `.scratch/rev2_fixture.py`, `.scratch/rev2_method.py`,
`.scratch/rev2_vps_m2.py` (+ reexecução de `.scratch/revisao_contas.py`, `.scratch/revisao_vps.py`,
`.scratch/d1_stress2.py`). Nada em `src/` foi tocado.

---

## Veredito em uma tela

| # | Afirmação do estudo NOVO | Veredito |
|---|---|---|
| 1 | Paridade 86/86 Excel cache × recálculo × `scoring.py` | **CONCORDO** |
| 2 | As três listas: conjunto idêntico, ordem difere só em empate | **CONCORDO** |
| 3 | D1 regra + viés monotônico + latência | **CONCORDO** |
| 4 | D1 Consist VPS: 18 invasores, mesmos nomes e posições | **CONCORDO** (e é robusto a método) |
| 5 | D1 Saúde: o estudo antigo publicou fixture como produção | **CONCORDO** na acusação |
| 6 | D1 Saúde: "produção = 16 invasores" | **PARCIAL** — 16 é de outro método; pelo método do estudo antigo são **13** |
| 7 | D1 Saúde: "na fixture são 12, o antigo omitiu VAMO3 e MOTV3" | **DISCORDO** — não houve omissão, é diferença de método |
| 8 | D2 empates estruturais; top-10 com conjunto inalterado | **CONCORDO** |
| 9 | D2: "59 vs 58 porque ITUB4=BRSR6 no ScoreF cru" | **DISCORDO** na causa (o par existe; a explicação não) |
| 10 | D3: AUAU3 vivo na VPS, SINAL vazio, ScoreT=100+IFR/1000 | **CONCORDO** — número a número |
| 11 | D4, D5, D6, D7, D8 | **CONCORDO** |

Resumo honesto: **o estudo NOVO está certo no que importa** — a paridade, o viés do D1, a procedência
contaminada do bloco Saúde e o caso vivo do D3. Erra em dois pontos secundários (itens 7 e 9), ambos
de atribuição causal, nenhum deles muda uma decisão de produto.

---

## 1. Paridade 86/86 — CONCORDO

Recalculei os 86 ativos do zero em Python a partir das colunas cruas da aba `Ativos Líquidos e
Informações`, reproduzindo a semântica Excel (`COUNTIFS` para os ranks, `AVERAGE` que ignora vazio,
`IFERROR` do ScoreF), e comparei três lados: **cache do `.xlsx`** (valores gravados) × **meu
recálculo** × **`scoring.py` no mesmo input**.

| Campo | cache × recálculo | Excel × `scoring.py` |
|---|---|---|
| nROE, nROIC, nMrgL, nDív, nLiqC, nP/L, nP/VP, nEV/EB, nCrsc | 86/86 | 0 divergências |
| Qualid, Saúde, Valuat, Consist | 86/86 | 0 divergências |
| ScoreF, PctF | 86/86 (ScoreF não-nulo: 86 dos dois lados) | 0 divergências |
| ScoreT | 86/86 (não-nulo: 86 dos dois lados) | 0 divergências |
| ScoreC | 86/86 | 0 divergências |
| SINAL | — | 0 divergências |

`tests/fixtures/excel_ativos.json` × cache do `.xlsx`: **0 divergências** — a fixture é retrato fiel
da planilha.

**Ressalva que o estudo NOVO fez e eu confirmo, mas reforço:** a paridade de **ScoreC** é vazia.
No snapshot da planilha o ScoreC é "sem dado" nos 86 ativos (nenhum SINAL aceso), então os dois lados
concordam por ausência, não por acerto. O mesmo vale para a lista ③, vazia dos dois lados. Quem ler a
tabela como "ScoreC está validado" está lendo errado: o que está validado é o ScoreF/PctF/ScoreT.

## 2. As três listas — CONCORDO

Planilha (`SMALL` sobre `PctFu`/`ScoreTu`/`ScoreCu`) × `build_lists` (`scoring.py:176-190`):

| Lista | Conjunto | Ordem | Observação |
|---|---|---|---|
| ① fundamentalista | **igual** | **difere** | Excel: `… RECV3, PSSA3, CMIN3, VIVA3 …` · app: `… RECV3, CMIN3, PSSA3, VIVA3 …` |
| ② técnico | **igual** | **igual** | `VIVT3, PSSA3, TIMS3, CXSE3, USIM5, SAPR11, EQTL3, LREN3, SBSP3, POMO4` |
| ③ combinado | igual (vazia) | igual | vazia dos dois lados — sem SINAL na planilha |

A troca em ① é exatamente o par empatado **PSSA3/CMIN3** no 4º/5º, ambos com PctF = 1/7 = 0,142857.
Excel desempata por `ROW()` (`pctfu = PctF + ROW()/100000000`), o app por ticker
(`key=(pct_f, ticker)`). É o D2, e é a única diferença de ordem no snapshot da planilha.

Na VPS reproduzi as três listas publicadas **ticker a ticker** (`①`, `②` e `③` iguais ao
`dashboard.json`): ③ tem 6 nomes — `JHSF3, CSMG3, BBSE3, GGBR4, ENEV3, TUPY3` — exatamente os 6
ativos com SINAL aceso. Regra do ScoreC honrada em produção.

## 3. D1 — ScoreF com bloco ausente

**Regra — CONCORDO.** `scoring.py:70-89` monta `parts` só com os blocos presentes e faz
`score_f = sum(parts) if parts else None`: **bloco faltante é descartado e os pesos restantes não são
renormalizados**. O Excel é tudo-ou-nada:

```
scoref: =IF($B2="Financeiro",IFERROR(0.5*AH2+0.3*AJ2+0.2*AK2,""),
                              IFERROR(0.4*AH2+0.25*AI2+0.2*AJ2+0.15*AK2,""))
```

Um bloco vazio contamina a aritmética inteira → `#VALUE!` → `IFERROR` → `""` → sem ScoreF, sem PctF,
fora das listas. Divergência real, das duas descrições (antiga e nova) que a descrevem igual.

**Viés — CONCORDO, e é monotônico.** PctF = `(better+1)/denom` com `better` = pares com ScoreF
*menor* (`scoring.py:106-113`), e a lista ① ordena `pct_f` **ascendente**. Menos blocos ⇒ soma menor
⇒ menos gente "melhor" ⇒ **PctF menor** ⇒ **posição melhor**. Confirmado nos dois exemplos:

- **A** — não-financeiro rank 4 em tudo: completo = 3,5000000000000004; sem Consist =
  3,0000000000000004 → o incompleto passa na frente do completo.
- **B** — grupo de 6, ativo pior do grupo (rank 6) só com Consist: 0,15×6 = 0,8999999999999999 <
  1,00 do melhor ativo completo → **assume o 1º lugar**.

Nuance que nenhum dos dois estudos registrou e que vale para calibrar o susto: o viés só morde quando
o bloco sobrevivente tem rank bom o bastante. Um financeiro só com Consist em **último** lugar do
grupo (rank 14) dá 0,20×14 = 2,8000000000000003, muito acima do 1,00 do melhor completo — não invade
nada. O bug é real, mas não é "qualquer ativo mutilado vira 1º".

**Latência — CONCORDO.** Nos 86 ativos da planilha: **nenhum** bloco usado está vazio; zero campos
`None`. O Fundamentus manda `0,00` em vez de vazio, e o zero entra na média
(`roic: 11, mrg_liq: 12, div_pat: 11, liq_corr: 10, ev_ebitda: 11, cresc: 4, roe: 1, pl: 1` zeros).
O gatilho existe (9 das 994 linhas da raspagem VPS trazem `Dív.Líq/Pat` de fato ausente), mas nenhuma
delas entra no universo de 86. **Bug latente, não ativo.**

### 3.1 Tabela Consist da VPS (18 invasores) — CONCORDO integralmente

Reproduzi os 18, com os **mesmos nomes e as mesmas posições** da tabela do estudo antigo — incluindo
`CXSE3 68º→6º` (maior salto, +62), `BBAS3 72º→11º` (que, note-se, **não** invade o top-10) e
`B3SA3 62º→1º`. Rodei os **dois** métodos possíveis (ver 3.2) e o resultado é 18 nos dois. Esta parte
do estudo antigo está limpa e é da produção, como ele diz.

### 3.2 Bloco Saúde — a acusação procede, o número do estudo NOVO não fecha

Existem dois experimentos diferentes escondidos atrás da frase "um ticker perde um bloco":

- **método 1 (post-hoc):** zera o bloco na soma do ScoreF, mantendo os ranks dos pares intactos;
- **método 2 (insumo):** apaga `Dív.Líq/Pat` e `Liq.Corr` do ticker e **re-ranqueia o grupo** — é o
  que de fato acontece quando o Fundamentus omite o campo, e é o que o script do estudo antigo
  (`.scratch/d1_stress2.py`) faz.

Medições minhas, mesmas listas, mesmo corte:

| Fonte | Bloco | Método 1 | Método 2 | MULT3 |
|---|---|---|---|---|
| fixture (= planilha) | Saúde | 12 invasores | **10 invasores** | 82º → 21º (nos dois) |
| fixture (= planilha) | Consist | 14 | 14 | — |
| **produção (VPS)** | Saúde | **16 invasores** | **13 invasores** | 23º → **23º** (nos dois) |
| **produção (VPS)** | Consist | 18 | 18 | — |

Conclusões, sem diplomacia:

1. **O estudo NOVO está certo na acusação de procedência.** `MULT3 82º→21º` e a lista de "10 dos 72"
   são da **fixture**, e estão publicados dentro de um documento cuja seção "Procedência dos dados"
   declara produção — a tabela Consist logo acima é produção de verdade. O leitor é induzido a erro.
   Na VPS o MULT3 é **23º e permanece 23º** perdendo Saúde: o salto espetacular não existe em
   produção. Confirmado nos dois métodos.
2. **O "16" do estudo NOVO é método 1.** Pelo método do próprio estudo antigo, produção dá **13**, não
   16. O estudo NOVO comparou 16 (produção, método 1) com 10 (fixture, método 2): trocou a fonte *e* o
   método na mesma linha da tabela. O número correto para a frase "quanto pior é a produção" é
   **10 → 13**.
3. **"O estudo antigo omitiu VAMO3 e MOTV3" está errado.** Não houve omissão. Pelo método 2 —
   o do script dele — VAMO3 fica em 25º (não se move) e MOTV3 vai a 22º: **não entram no top-10**.
   Eles só entram no método 1 (VAMO3 25º→9º, MOTV3 51º→9º). Provado em `.scratch/rev2_method.py`.
   A lista de 10 nomes do estudo antigo é internamente coerente com o método que ele usou.
4. Confirmo o detalhe fino do estudo NOVO: na produção **PETR4 (3º) e RENT3 (9º) já estão no top-10**,
   logo não podem "invadir" — a lista do estudo antigo os inclui porque na fixture eles estavam fora.
   E `SAPR11` não invade em produção.

Ressalva de método minha, declarada: na VPS o payload publica apenas os ranks (`n_div`, `n_liqc`), não
as métricas cruas. O método 2 na VPS foi **emulado** decrementando o rank dos pares que contavam o
ticker removido como melhor — equivalente exato à semântica `rank = #{p < mine} + 1`, inclusive em
empates. Não é uma releitura do disco da VPS.

## 4. D2 — empates de PctF e o corte `[:10]` — CONCORDO (com uma causa trocada)

Estrutural, confirmado: PctF só assume `(k+1)/n` com `n` nos tamanhos da aba `Setores`
(14, 13, 9, 7, 7, 6, 6, 5, 4, 4, 3, 3, 3, 2) — são 42 valores possíveis para 86 ativos, a colisão
entre grupos é inevitável. Contagem: **58/86 ativos empatados na planilha** (42 valores distintos) e
**59/86 na VPS** (41 distintos).

Conjunto do top-10 **inalterado** nos dois snapshots; só a ordem muda, e só dentro do empate:

| Snapshot | Par que troca | PctF | Posições | Corte 10º × 11º |
|---|---|---|---|---|
| Planilha | PSSA3 ↔ CMIN3 | 1/7 = 0,142857 | 4º/5º | BEEF3 0,20 × ABCB4 0,214285 — **sem empate** |
| VPS | CURY3 ↔ RENT3 | 1/6 = 0,166666 | 8º/9º | BEEF3 0,20 × BBDC4 0,214285 — **sem empate** |

Ou seja: o risco que o estudo antigo levanta (bloco de empate cruzando o corte ⇒ **nome diferente** na
lista) é estruturalmente válido e **não disparou em nenhum dos dois snapshots**. O estudo NOVO está
certo em rebaixar a urgência sem negar a estrutura.

**Erro do estudo NOVO aqui:** "na VPS sobe para 59/86 **porque** ITUB4 e BRSR6 empatam no ScoreF cru
(ambos 5,70)". O par existe e eu confirmo (ITUB4 = BRSR6 = ScoreF 5,70, Financeiro, PctF 2/7 =
0,285714) — mas **a planilha tem exatamente o mesmo fenômeno**: B3SA3 = BBSE3 = ScoreF 6,40 →
PctF 3/7. Cada snapshot tem um, e só um, empate de ScoreF dentro do setor. O delta 58 → 59 vem da
redistribuição do conjunto inteiro de valores (42 → 41 distintos) entre dois universos diferentes, não
desse par. A observação é boa; a explicação é falsa.

## 5. D3 — ScoreT sem SINAL — CONCORDO, número a número

```
scoret: =IF(OR($M2="",$Q2="",X2=""),"",IF(X2="► VENDER PUT",($M2-$Q2)/$Q2,100+$O2/1000))
```

Exige Preço **e** Boll Inf **e** SINAL nos dois ramos. O código (`scoring.py:146-151`) cai no
`elif tech.ifr is not None: score_t = 100 + tech.ifr/1000` sempre que houver IFR, com SINAL vazio ou não.

Caso vivo na VPS, conferido: **AUAU3** — preço 3,16 · MM200 **sem dado** · Boll Inf 3,0200607961890085 ·
IFR 41,81403767275076 · SINAL vazio · **ScoreT = 100,04181403767275** = 100 + IFR/1000, exato. O Excel
devolveria `""` (X2 vazio). Cadeia causal confirmada no código: sem MM200 → `tendencia = None` →
`sinal = None`, e o ScoreT sobrevive assim mesmo.

Impacto, também confirmado: AUAU3 **não** entra na ②, porque as 10 vagas já estão tomadas pelos 6
ativos com SINAL (ScoreT ≈ 0,00004 a 0,045) mais os 4 menores `100+IFR/1000`
(POMO4, LREN3, USIM5, BBDC4). O estudo antigo dizia "só afeta a cauda, nunca o topo" — está certo, e o
estudo NOVO acrescenta o que faltava: **deixou de ser teórico**, já existe 1 papel nessa condição.

## 6. D4–D8 — CONCORDO com o estudo NOVO

- **D4 (RTD/Profit × Yahoo):** lacuna real e **não fechável hoje**. Confirmo as convenções do lado do
  código: Bollinger inferior com desvio **populacional** (divisão por *n*), MM200 = SMA de 200,
  HV amostral (`ddof=1`) sobre 21 log-retornos × √252, IFR de Wilder 14
  (`indicators.py`), parametrizados em `data/config.json`. O lado RTD (códigos 3/1/12/387/45) não é
  auditável a partir do repo — nenhum snapshot do Profit foi guardado. Continua **sem dado**, e
  chamar isso de "divergência" seria inventar número.
- **D5 (`"Financeiro"` case-sensitive):** `scoring.py:53` compara com igualdade exata; o Excel
  (`IF($B2="Financeiro";…)`) é case-insensitive. Os 14 grupos do universo usam a grafia exata — nenhum
  `casefold` divergente. Latente. Se um dia vier `FINANCEIRO`, 14 ativos trocam de fórmula de ScoreF
  em silêncio (0,50/0,30/0,20 → 0,40/0,25/0,20/0,15 com bloco Saúde) — não é cosmético.
- **D6 (`_rsi_wilder` → `None` em série sem variação):** confirmo a leitura do código e o efeito
  correto — o ativo **some da ②** (sem IFR ⇒ sem ScoreT ⇒ filtrado em `build_lists`). Sem série plana
  nos dois snapshots. O estudo NOVO acerta inclusive a lista afetada.
- **D7 (denominador do PctF = 0):** `pctf` divide por `COUNTIFS(…;">0")` sem `IFERROR`, e o código faz
  o mesmo `denom` (`scoring.py:107`) devolvendo `None`. Confirmo o refinamento do estudo NOVO: o
  `IF(AL2="";"";…)` protege o caso comum, e ScoreF de ranks é sempre ≥ 1,00 quando existe — o
  `#DIV/0!` exigiria ScoreF numérico ≤ 0, que a construção por ranks não produz. **Divergência
  inalcançável**, não apenas rara.
- **D8 (IV Rank / IV Percentil):** sem ação, como os dois estudos dizem. Nenhuma coluna da planilha
  está ausente no app; a adição já estava prevista em doc. Não reabri o JS — fora do escopo das
  análises ①②③.

---

## 7. Erros do estudo NOVO (lista curta e completa)

1. **"Na fixture, Saúde gera 12 invasores (não 10); o estudo omitiu VAMO3 e MOTV3."** Errado. É
   diferença de método (post-hoc × apagar insumo e re-ranquear), não omissão. Pelo método do estudo
   antigo, VAMO3 e MOTV3 legitimamente não entram.
2. **"Na VPS sobe para 59/86 porque ITUB4 e BRSR6 empatam no ScoreF cru."** Causa errada: a planilha
   tem o mesmo tipo de empate (B3SA3/BBSE3, ScoreF 6,40). O par existe; ele não explica o +1.
3. **"Invasores Saúde VPS = 16"** contra os "10 dos 72" do estudo antigo: comparação maçã × laranja
   (troca fonte e método simultaneamente). Pelo método do estudo antigo, produção dá **13**.

Nada além disso. As demais 8 afirmações que confrontei bateram com a fonte.

## 8. O que o estudo NOVO acertou e o antigo errou

- **Procedência do bloco Saúde:** o estudo antigo apresenta números de fixture (`MULT3 82º→21º`,
  "10 dos 72") sob um cabeçalho de produção, na mesma seção em que a tabela Consist é produção real.
  Isso é um defeito de relatório, e o estudo NOVO fez bem em cravá-lo. Em produção o MULT3 **não se
  move**.
- **PETR4/RENT3 não podem invadir em produção** (já estão no top-10) — o estudo antigo herdou a lista
  da fixture sem reconferir.
- **D3 deixou de ser hipótese:** AUAU3 está vivo hoje na VPS. O estudo antigo tratava como teórico.

## 9. Achados meus, que nenhum dos dois isolou

1. **A paridade de ScoreC e da lista ③ na planilha é vazia** (0 valores dos dois lados). Não é
   evidência de acerto; é ausência de dado. Quem for usar a tabela 86/86 como aval do ScoreC vai se
   enganar. Em produção o ScoreC está correto (6 ativos, exatamente os com SINAL) — isso sim é
   evidência.
2. **O viés do D1 tem limiar.** Perder um bloco não empurra qualquer ativo para o topo: um financeiro
   só com Consist em último lugar (0,20×14 = 2,80) fica atrás de qualquer completo (1,00). O prêmio
   indevido depende do rank do bloco sobrevivente. Isso muda a prioridade da correção — o risco real
   é de ativos medianos/bons com bloco faltante, não de qualquer ativo.
3. **Para Consist os dois métodos coincidem (18 em produção, 14 na fixture); para Saúde não.** Quem
   for corrigir o D1 e quiser reusar essas medições precisa dizer qual método está citando, senão as
   duas revisões continuarão discordando por motivo errado.
4. **Faixas `$B$2:$B$87` / `$AL$2:$AL$87` estão fixas em 86 linhas** em todas as fórmulas conferidas
   (ScoreF, PctF, ranks). Se o universo crescer, a planilha para de contar o excedente em silêncio; o
   app não tem esse teto. Não é bug do código — é limite da planilha, e vale registrar antes que
   alguém use a planilha como árbitro de um universo maior.

## 10. O que fica em aberto

| # | Ponto | Estado |
|---|---|---|
| 1 | D1: descartar bloco × anular ScoreF (variante B) | **aplicado** 2026-08-19 |
| 2 | D2: desempate por ticker × por ordem do universo | ticker mantido; doc corrigida |
| 3 | D3: exigir Preço/Boll Inf/SINAL no ScoreT | **aplicado** 2026-08-19 |
| 4 | D1 Saúde no `docs/divergencias-planilha.md` | **corrigido** (fixture ≠ produção; 13 / 16, MULT3 23º→23º) |
| 5 | D4 | continua **sem dado** — exigiria snapshot do Profit |
| 6 | D5/D6/D7 | registrados; não mudam comportamento |
| 7 | D8 | nada a fazer |
