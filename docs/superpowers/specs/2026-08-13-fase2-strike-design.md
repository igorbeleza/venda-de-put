# Fase 2 — motor de strike + UI A

Data: 2026-08-13

## Decisão de produto

Variante **A (Faixa Excel)**, com o ajuste pedido: em cada card, destacar **preço atual** (não “preço”), **strike** e **prêmio (bid)**.

Trocar o vencimento **não reordena** as três listas. Muda: dias corridos, prêmio-alvo, strike e bid.

## Prêmio-alvo

`prêmio_alvo = meta_30d × √(dias_corridos / 30)`

Dashboard (topo, fita):

1. Meta de prêmio p/ 30 dias
2. Dias até o vencimento (corridos)
3. **Prêmio-alvo para esse vencimento** (destaque)

Config restaura o bloco da planilha (Config!A17:B20). O terceiro campo é fórmula, não se edita. `meta_30d` persiste. Dias no Config espelha o vencimento do Dashboard (o seletor é a fonte da verdade).

## Motor de strike

Só dos tickers das três listas. Cadeia OpLab `/mercado/acoes/opcoes/{TICKER}`. Snapshot guarda PUT enxuta (`due_date`, `strike`, `bid`, `ask`, `delta`, `poe`, `volume`), séries ≤ 120 dias corridos. Sem JSON cru.

Seleção no vencimento escolhido:

1. PUT, `strike < preço atual`
2. Descarte `delta < −0,45`
3. Prêmio = `put.bid` de primeiro nível (**nunca** `put.bs.bid`)
4. `prêmio_% = bid / strike`
5. Menor strike cujo `% ≥ alvo`
6. Senão: maior `%`, status `abaixo_da_meta`
7. Sem série: `sem_serie`
8. Série sem `bid > 0`: `sem_liquidez`

A linha nunca some.

## Card (todas as listas)

Campos atuais + `preço atual` (destaque) + faixa Meta 30d | Meta vencimento + `strike` e `prêmio (bid)` em destaque + delta, POE, distância, status.

## Fora

Não reordenar listas. Refresh da UI não raspa. Sem `bs.bid`.
