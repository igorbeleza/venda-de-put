# Ideia futura — último período dos indicadores = instante da raspagem

Não implementar. Estacionado até o produto pedir.

## Pedido

Se a raspagem roda às 11h, o à vista daquele instante entra como **último período** da MM200, do IFR, da Boll Inf e do HV. Tendência e timing passam a comparar preço e indicadores na mesma base de tempo.

## Hoje

`sources/yahoo.py` guarda duas coisas separadas: `closes` (barras diárias do chart `2y/1d`) e `preco` (`regularMarketPrice`).

`scrape.py` calcula MM200 / IFR / Boll Inf / HV **só** em `closes`. Não substitui o último close pelo `preco` e não anexa o `preco` se a barra de hoje não veio. Timestamps das barras são ignorados.

O scoring usa o `preco` do instante contra esses indicadores. Se o Yahoo incluir a barra de hoje no `close[]`, pode coincidir por acaso da fonte — não é contrato.

Teste que trava a separação: `tests/test_sources.py` (`closes` terminam em 41,0; `preco` 41,75).

## Planilha

A planilha **não** tinha essa fórmula. Lia MM200, IFR e Bollinger ao vivo do gráfico (feed RTD). Num gráfico diário a última barra é a sessão em curso, então às 11h aqueles números se mexiam com o último. O efeito observado é o deste pedido; o mecanismo era o gráfico, não uma janela de fechamentos no Excel.

IV/HV nessa planilha não chegavam (códigos inválidos). História: `docs/archive/2026-08-prompts-iniciais/`, ADR `0003-ifr-wilder.md`.

## Se um dia for feito

No parse (ou logo antes dos indicadores): se houver `preco`, trocar o close de hoje por ele quando a barra de hoje existir; senão anexar como período novo. Só então SMA / Wilder / Bollinger / HV.

Deixa de ser MM200/Bollinger clássicos de fechamento. Recalcula tendência, timing e SINAL no mesmo scrape. Teste que falha primeiro: último período da série = `preco` do instante, mesmo quando o `close[]` do Yahoo diverge.
