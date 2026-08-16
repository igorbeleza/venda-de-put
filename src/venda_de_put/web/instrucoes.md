# Instruções

Ferramenta de seleção para venda de put coberta por critério próprio.

## Timing de entrada

- IFR (RSI clássico / Wilder, 14 períodos — não a média simples da janela) entre **10** e **50**
- Preço na ou abaixo da banda inferior de Bollinger, com folga configurável
- Tendência: preço acima da média móvel de 200 períodos

## Prazo

As vendas de put são abertas com **45 a 21 dias corridos** até o vencimento.

## Prêmio

O prêmio-alvo escala a meta de 30 dias pela raiz do prazo até o vencimento.

No vencimento escolhido, o prêmio da put é **último preço negociado / strike**. A entrada usa o **menor strike OTM** (mais distante do à vista) em que essa taxa seja **pelo menos** a meta do vencimento — maior segurança que ainda bate a meta. Só entra strike com último e volume no dia; último sem negócio é cotação velha.

## Dados

Os dados vêm do snapshot em disco (Yahoo, OpLab, Fundamentus), relido no botão Atualizar — sem terminal de corretora.

Configuração de janelas (IFR, Bollinger, MM, horários de coleta) fica na aba Config. Não há campos de terminal nem planilha auxiliar.
