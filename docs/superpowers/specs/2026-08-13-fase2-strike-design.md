# Fase 2 — motor de strike + UI A

Data: 2026-08-13

Autoridade viva do produto: `docs/mvp.md` e `docs/sdd.md`. Este arquivo detalha o motor de strike.

## Decisão de produto

Variante **A (Faixa Excel)**, com o ajuste pedido: em cada card, destacar **preço atual** (não “preço”), **strike** e **prêmio (último negócio)**.

Trocar o vencimento **não reordena** as três listas. Muda: dias corridos, prêmio-alvo, strike e prêmio.

**Janela de abertura da operação:** as vendas de put são abertas com **45 a 21 dias corridos** até o vencimento (inclusive). Fora dessa faixa o seletor ainda consulta; não é quando a operação é aberta.

## Prêmio-alvo

`prêmio_alvo = meta_30d × √(dias_corridos / 30)`

Dashboard (topo, fita):

1. Meta de prêmio p/ 30 dias
2. Dias até o vencimento (corridos)
3. **Prêmio-alvo para esse vencimento** (destaque)

Config restaura o bloco da planilha (Config!A17:B20). O terceiro campo é fórmula, não se edita. `meta_30d` persiste. Dias no Config espelha o vencimento do Dashboard (o seletor é a fonte da verdade).

## Motor de strike

Só dos tickers das três listas. Cadeia OpLab `/mercado/acoes/opcoes/{TICKER}`. Snapshot guarda PUT enxuta (`due_date`, `strike`, `bid`, `ask`, `last` = `put.close`, `symbol`, `delta`, `poe`, `volume`), séries ≤ 120 dias corridos. Sem JSON cru.

Seleção no vencimento escolhido:

1. PUT, `strike < preço atual`
2. Descarte `delta < −0,45`
3. Prêmio em reais = `put.close` (último negócio). **Nunca** `put.bs.bid` (é a call). Bid/ask ficam só como livro.
4. `prêmio_% = último / strike`
5. Menor strike cujo `% ≥ alvo` (primeiro, subindo do mais OTM — máxima segurança que ainda bate a meta)
6. Senão: maior `%`, status `abaixo_da_meta`
7. Sem série: `sem_serie`
8. Série sem `último > 0` **e** volume no dia: `sem_liquidez` (último velho sem negócio não entra)

Exemplo (BRAV3, 18/09/2026, meta 1,21%): BRAVU162 16,13 último 0,19 → 1,17% (não basta); BRAVU165 16,38 último 0,22 → 1,34% (primeiro ≥ 1,21%).

A linha nunca some.

## Card (todas as listas)

Campos atuais + `preço atual` (destaque) + faixa Meta 30d | Meta vencimento + `strike` (código da opção) e `prêmio (últ.)` em destaque + delta, POE, distância, status.

## Fora

Não reordenar listas. Refresh da UI não raspa. Sem `bs.bid`.
