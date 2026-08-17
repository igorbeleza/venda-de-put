# Scoring — ScoreF, PctF, ScoreT, ScoreC e as três listas

Autoridade: `src/venda_de_put/scoring.py`. Paridade dos ranks com a planilha: `tests/test_scoring_ranks.py` e `tests/fixtures/excel_ativos.json`.

Menor é melhor em ScoreF, PctF, ScoreT e ScoreC. Desempate: ticker A–Z.

## PctFu, ScoreTu, ScoreCu (planilha)

Na planilha (`carteira_venda_put (4).xlsx`) as colunas AN / AP / AR **existem**. O “u” não é universo. É **único**: a mesma nota mais `ROW()/1e8`, para o `SMALL`/`MATCH` do Dashboard não empatar.

```
PctFu   = PctF   + linha/1e8     # AN; lista ①
ScoreTu = ScoreT + linha/1e8     # AP; lista ②
ScoreCu = ScoreC + linha/1e8     # AR; lista ③
```

Não entram em ScoreF, PctF, ScoreT, ScoreC, tendência, timing nem SINAL. Sem eles, as quatro notas da tabela abaixo saem iguais.

Neste app o desempate é o ticker (A–Z), não o número da linha. Só muda a ordem se dois papéis tiverem a **mesma** nota — caso raro. Não recalcula nada.

## Peças

### Ranks no grupo (`nROE` … `nCrsc`)

`1` = melhor do setor. Tamanho do grupo = quantos tickers têm aquele `grupo` no universo.

| Rank | Direção | Financeiro |
|---|---|---|
| nROE, nMrgL, nCrsc | maior valor cru → rank menor | entram |
| nROIC, nLiqC | maior valor cru → rank menor | pulados (`None`) |
| nDív | menor dívida → rank menor | pulado |
| nP/L, nP/VP, nEV/EB | menor múltiplo **positivo** → rank menor | nEV/EB pulado |

Múltiplo ≤ 0 não é “barato”: rank = tamanho do grupo + 1.

Quem não tem o indicador não entra na contagem do par; o ausente fica `None`.

### Blocos

```
Qualid  = média(nROE, nROIC, nMrgL)     # Financeiro: média(nROE, nMrgL)
Saúde   = média(nDív, nLiqC)            # vazio no Financeiro
Valuat  = média(nP/L, nP/VP, nEV/EB)
Consist = nCrsc
```

Médias ignoram `None`.

### ScoreF

Nota bruta no setor (ainda não é a lista ①).

```
Financeiro:  0,50·Qualid + 0,30·Valuat + 0,20·Consist
Demais:      0,40·Qualid + 0,25·Saúde  + 0,20·Valuat + 0,15·Consist
```

Só entram os blocos que existirem. Sem nenhum bloco → `sem dado`.

### PctF

Percentil do ScoreF **no mesmo grupo**:

```
PctF = (quantos do grupo têm ScoreF < o meu + 1) / (quantos do grupo têm ScoreF > 0)
```

Menor PctF = melhor empresa do setor para carregar. É o que ordena a lista ①. ScoreF de grupos diferentes não se compara — por isso a lista não ordena por ScoreF cru.

### SINAL (liga ScoreT “de verdade” e o ScoreC)

```
Tendência = alta   se preço > MM200
          = fora   senão
          = vazio  se faltar preço ou MM200

Timing    = ENTRADA  se IFR ∈ [ifr_min, ifr_max] e preço ≤ Boll Inf × (1 + folga)
          = aguardar senão
          = vazio    se faltar IFR, preço ou Boll Inf

SINAL     = ► VENDER PUT  se tendência alta e timing ENTRADA
          = —             se os dois lados existem mas não fecham
          = vazio         se falta tendência ou timing
```

Padrão: IFR 10–50, folga 5% (`data/config.json`).

### ScoreT

Só ordena a lista ②. Duas fórmulas de propósito:

```
com SINAL aceso:  ScoreT = (preço − Boll Inf) / Boll Inf     # ~0,00 a ~0,05
sem SINAL:        ScoreT = 100 + IFR / 1000                  # ~100,01 a ~100,10
sem IFR:          vazio  → fora da ②
```

O `100 + …` é o truque da planilha: quem não tem SINAL vai para o fim, e entre esses ganha o IFR menor. Sem isso a ② ficaria vazia em dia sem entrada.

Não é “o IFR é o score”. Com SINAL aceso o IFR não entra no ScoreT — entra a distância da banda.

### ScoreC

```
ScoreC = PctF    se SINAL aceso
       = vazio   senão
```

Não é produto ScoreF × ScoreT. Não é percentil no universo. É o **mesmo PctF**, só que só quem está no ponto de vender put.

## As três análises

```
① Fundamentalista  →  10 menores PctF     (precisa ter PctF)
② Técnico          →  10 menores ScoreT    (precisa ter ScoreT)
③ Combinado        →  menores ScoreC       (só SINAL aceso; pode ter < 10)
```

Trocar o vencimento **não** reordena as listas. Strike e prêmio-alvo mudam no card; ScoreF / PctF / ScoreT / ScoreC não.

### ① Fundamentalista

Empresas que se aceita carregar se exercido. Ignora IFR, banda e SINAL. Um papel pode ser o 1º da ① e ter `sinal = —`.

### ② Técnico

Timing agora. Ordem típica:

1. os que têm `► VENDER PUT`, do mais colado na banda ao mais longe (ainda dentro da folga);
2. se sobrar vaga até 10, os sem SINAL com menor IFR (`ScoreT ≈ 100,0x`).

Exemplo do snapshot 17/08 12:49: seis com SINAL, depois POMO4 / TIMS3 / USIM5 / BBDC4 (IFR baixo, tendência `fora` ou timing que não fecha). BRAV3 com IFR ~40 e SINAL apagado não entra — ScoreT ~100,04 perde para IFR 17–23.

### ③ Combinado

Interseção: tem que **passar no SINAL** (alta + ENTRADA) e então ordena pelo PctF. É a lista de operação. Sem SINAL → sem ScoreC → fora, por melhor que seja o ScoreF.

Por isso BRAV3 some da ③ quando o preço passa da folga da banda: o fundamento continua, o SINAL apaga, o ScoreC some.

## Diagrama

```
Fundamentus ──► ranks no grupo ──► ScoreF ──► PctF ──► ①
                                      │
                                      └──────────────► ScoreC = PctF ─┐
Yahoo close+à vista ──► MM200, IFR, Boll Inf                          │
                              │                                       ▼
                              ├─ tendência + timing ─► SINAL ──► ③ (só se aceso)
                              │         │
                              │         ├─ aceso:  ScoreT = dist. da banda ─┐
                              │         └─ apagado: ScoreT = 100+IFR/1000 ─┴► ②
```

## O que não é

| Nome | Neste app |
|---|---|
| PctFu / ScoreTu / ScoreCu | na planilha: nota + `ROW()/1e8` para o `SMALL`. Aqui: desempate por ticker. Não alimentam ScoreF/PctF/ScoreT/ScoreC |
| Percentil nos 86 | não existe; rank é no grupo |
| ScoreT “de fundamento” | ScoreT é só timing |
| Média ①×② | a ③ não mistura as duas notas |

Código: `score_fundamentals`, `apply_technical`, `build_lists`. Listas: CONTEXT.md. Indicadores: `docs/sdd.md` e `docs/superpowers/specs/2026-08-17-indicadores-ultimo-periodo.md`.
