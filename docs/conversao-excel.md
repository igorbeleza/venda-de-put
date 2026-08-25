# Da planilha Excel para esta página

A versão **1.0.0** é o dashboard web que substitui `carteira_venda_put (4).xlsx`.
Este arquivo conta **como** as contas da planilha chegaram ao código. Glossário em
`CONTEXT.md`. Fórmulas vivas em `docs/scoring.md` e no pacote `src/venda_de_put/`.
O `.xlsx` fica só na máquina (gitignored).

Os briefs de agosto/2026 que transcreveram o modelo estão em
`docs/archive/2026-08-prompts-iniciais/`. O plano executável está em
`docs/superpowers/plans/2026-08-13-dashboard-venda-put.md`.

## Por que sair do Excel

A planilha fazia três coisas ao mesmo tempo: colar o Fundamentus, puxar preço e
indicadores de um terminal de corretora via RTD, e ranquear 86 papéis em três
listas. Três problemas:

1. `=RTD(...)` só funciona no Excel desktop, no Windows, com o terminal aberto.
2. Os códigos RTD de volatilidade vinham inválidos; IV, HV e “Prêmio?” ficavam
   vazios.
3. A planilha recomendava o **ativo**, não o **strike**. Montar a put ainda pedia
   o terminal.

A página web recalcula o mesmo modelo, busca os dados sozinha e escolhe strike
no vencimento que o usuário aponta.

## O que cada aba virou

| Aba do Excel | Nesta página |
|---|---|
| Dashboard (três listas + textos em primeira pessoa) | Dashboard: cards ①②③, seletor de vencimento, strike e prêmio-alvo |
| Ativos Líquidos e Informações | Ativos (fundamento + técnico; ranks atrás de “mostrar cálculo”) |
| Dados (Fundamentus colado) | Dados (tabela raspada, cotação do Fundamentus) |
| Setores | Setores |
| Config (células amarelas) | Config (admin): parâmetros, carimbo da raspagem, botão de raspar |
| Vencimentos | Vencimentos |
| Feriados | Feriados (admin) |
| Instruções | Instruções (IFR 10–50, sem terminal) |

Colunas auxiliares do Excel (RTD cru, parse de string do Bollinger, `AS`→`BD`)
não existem: eram contorno de limitação da planilha.

## De onde vêm os números

```
Excel                          Esta página
─────────────────────────      ──────────────────────────────────
Fundamentus colado à mão  →    sources/fundamentus.py  (aba Dados)
RTD preço / MM / IFR /    →    Yahoo (série 2y/1d). Se o ticker
Bollinger / HV                 falha 3 vezes: à vista brapi.dev;
                               sem técnico anterior: Cotahist B3
(IV quebrado no RTD)      →    OpLab `iv_current` + cadeia de puts
VLOOKUP ticker → grupo    →    data/universe.json
SMALL/MATCH das listas    →    scoring.py (puro, sem HTTP)
(não havia strike)        →    strike.py no vencimento escolhido
arquivo .xlsx             →    snapshot JSON em disco; a UI só lê
```

O motor (`score_fundamentals` → `apply_technical` → `build_lists`) não conhece
HTTP. Quem fala com a rede é só o scrape. `POST /api/refresh` relê o arquivo;
não raspa.

## Fórmulas: Excel → código

A transcrição fiel está na seção 4 de
`docs/archive/2026-08-prompts-iniciais/PROMPT-PLANEJAMENTO.md`. O código que
manda hoje é `src/venda_de_put/scoring.py`. Resumo do mapeamento:

| Peça | Planilha | Código |
|---|---|---|
| Ranks no setor (`nROE`…`nCrsc`) | `COUNTIF` / `RANK` no grupo | `_rank_higher_better` / `_rank_lower_better` / `_rank_valuation` |
| Múltiplo ≤ 0 | vai para o fim, não é “barato” | `group_size + 1` |
| Financeiro | pulava ROIC, dívida, liq. corrente, EV/EBITDA | idem; **nMrgL entra** (a planilha também; um rascunho antigo do prompt dizia o contrário) |
| Qualid / Saúde / Valuat / Consist | `AVERAGE` ignora vazio | `_mean` ignora `None` |
| ScoreF | `IFERROR` da soma ponderada: um bloco vazio anula a nota | bloco vazio → `None` (decisão D1 variante B, 19/08/2026) |
| PctF | percentil do ScoreF **no grupo** | `(melhores + 1) / quem tem ScoreF` |
| Tendência / timing / SINAL | Preço vs MM200; IFR 10–50 e preço na Boll Inf × (1+folga) | `apply_technical` |
| ScoreT | `(preço − Boll Inf)/Boll Inf` se SINAL aceso; senão `100 + IFR/1000` | igual; SINAL vazio tira da ② |
| ScoreC | PctF se SINAL aceso | igual |
| Listas ①②③ | `SMALL`/`MATCH` no Dashboard | 10 menores PctF / ScoreT / ScoreC |
| Empate | `ROW()/1e8` nas colunas *u* (PctFu, ScoreTu, ScoreCu) | ticker A–Z. Não muda a nota; só a ordem se a nota empatar |

Indicadores, que o Profit entregava prontos:

| Indicador | No código | Detalhe que a planilha escondia |
|---|---|---|
| MM200 | SMA 200 | RTD usava código `3`; assume-se simples |
| IFR | Wilder 14 (`rsi_wilder`) | Clássico, não média simples. ADR 0003 |
| Boll Inf | SMA 20 − 2σ **populacional** (`/n`) | o Profit mandava as 3 bandas numa célula |
| HV | σ **amostral** de 21 log-retornos × √252 | janela curta de propósito (put 45–21 dias) |
| IV | OpLab, não calculada aqui | RTD 387/45 vinha “Atributo Inválido” |
| Prêmio-alvo | `meta_30d × √(dias/30)` | `premium.py`; meta gravada 1,15% (ajuste da recompra a 70% exaurido) |
| Taxa da put | último / strike, com volume no dia | ADR 0002; nunca `put.bs.bid` (é a call) |

Dado impossível vira o texto **sem dado**. Nunca zero inventado.

## O que a planilha não tinha

O motor de strike é novo. No vencimento escolhido: puts OTM, delta ≥ −0,45,
último e volume no dia, menor strike cuja taxa ainda paga a meta. Sem série /
sem liquidez / abaixo da meta são estados visíveis, não linha sumida. Trocar o
vencimento **não** reordena as três listas.

## Como a paridade foi provada

1. `scripts/extract_excel_fixtures.py` lê o `.xlsx` local e grava
   `tests/fixtures/excel_ativos.json` e `excel_dados.json`.
2. `tests/test_scoring_ranks.py` e `tests/test_scoring_lists.py` conferem ranks
   e as três listas contra esse retrato.
3. Três laudos de divergência (`docs/divergencias-planilha.md`,
   `docs/revisao-divergencias-planilha.md`,
   `docs/segunda-revisao-divergencias.md`) confrontaram código × fórmula Excel
   célula a célula. O que foi aceito em 19/08/2026: D1 (bloco vazio anula
   ScoreF), D3 (ScoreT exige SINAL preenchido), D2 (desempate por ticker, não
   por `ROW()`).

Para regenerar as fixtures: copie a planilha para a raiz e rode o script
(dependência `openpyxl`, extra `[dev]`).
