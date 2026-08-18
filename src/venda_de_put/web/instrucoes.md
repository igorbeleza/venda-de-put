# Instruções

Ferramenta de seleção para venda de put coberta por critério próprio.

## Timing de entrada

- IFR (RSI clássico / Wilder, 14 períodos — não a média simples da janela) entre **10** e **50**
- Preço na ou abaixo da banda inferior de Bollinger, com folga configurável
- Tendência: preço acima da média móvel de 200 períodos

## Prazo

As vendas de put são abertas com **45 a 21 dias corridos** até o vencimento.

## Prêmio

A meta econômica é **1% do strike em 30 dias**. A put é recomprada quando o prêmio está **70% exaurido** — vendida a 1,00, recompra a 0,30 — independentemente do prazo que ainda falta. Por isso a meta gravada no Config é **1,15% do strike em 30 dias**: já traz o ajuste dessa saída antecipada.

O prêmio-alvo do vencimento escolhido escala essa meta de 30 dias pela raiz do prazo (√(dias corridos / 30)).

No vencimento escolhido, o prêmio da put é **último preço negociado / strike**. A entrada usa o **menor strike OTM** (mais distante do à vista) em que essa taxa seja **pelo menos** a meta do vencimento — maior segurança que ainda bate a meta. Só entra strike com último e volume no dia; último sem negócio é cotação velha.

## Dados

Os dados vêm do snapshot em disco (Yahoo, OpLab, Fundamentus), relido no botão Atualizar — sem terminal de corretora.

Configuração de janelas (IFR, Bollinger, MM, horários de coleta) e a meta de prêmio para 30 dias (em porcentagem) ficam na aba Config. A mesma aba mostra o carimbo da última coleta e o resultado de cada fonte. Não há campos de terminal nem planilha auxiliar.
