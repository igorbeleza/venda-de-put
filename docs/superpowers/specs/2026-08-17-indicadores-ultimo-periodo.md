# Último período dos indicadores = instante da raspagem

Implementado. `apply_spot_as_last_period` em `indicators.py`; o parse do Yahoo aplica antes de gravar `closes`.

## Pedido

Se a raspagem roda às 11h, o à vista daquele instante entra como **último período** da MM200, do IFR, da Boll Inf e do HV. Tendência e timing passam a comparar preço e indicadores na mesma base de tempo. Esse à vista (e as cotações da cadeia) está cerca de **15 minutos atrasado** em relação ao horário da raspagem.

## Contrato

`preco` (`regularMarketPrice`) entra na janela:

- barra de hoje existe (timestamp no dia da raspagem, `America/Sao_Paulo`) → troca o último close pelo à vista;
- senão, anexa um período novo;
- se o último close válido já é o à vista, não duplica (pregão fechado / fim de semana).

MM200, IFR, Boll Inf e HV usam essa série. `null` no meio continua buraco.

Testes: `test_spot_*` em `tests/test_indicators.py`; `test_yahoo_replaces_todays_bar_with_spot` e último período = `preco` em `tests/test_sources.py`.

## Planilha

A planilha **não** tinha essa fórmula. Lia MM200, IFR e Bollinger ao vivo do gráfico (feed RTD). Num gráfico diário a última barra é a sessão em curso, então às 11h aqueles números se mexiam com o último. O efeito observado é o deste pedido; o mecanismo era o gráfico, não uma janela de fechamentos no Excel.

IV/HV nessa planilha não chegavam (códigos inválidos). História: `docs/archive/2026-08-prompts-iniciais/`, ADR `0003-ifr-wilder.md`.

## Efeito

Deixa de ser MM200/Bollinger clássicos de fechamento: queda forte no dia puxa a banda e o IFR no mesmo instante do `preco`. Scoring (tendência, timing, SINAL) já vê essa janela.
