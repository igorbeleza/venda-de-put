# Instruções

Ferramenta de seleção para venda de put coberta por critério próprio.

## Timing de entrada

- IFR (RSI clássico / Wilder, 14 períodos — não a média simples da janela) entre **10** e **50**
- Preço na ou abaixo da banda inferior de Bollinger, com folga configurável
- Tendência: preço acima da média móvel de 200 períodos

## Prêmio

O prêmio-alvo escala a meta de 30 dias pela raiz do prazo até o vencimento.

## Dados

Os dados vêm do snapshot em disco (Yahoo, OpLab, Fundamentus), relido no botão Atualizar — sem terminal de corretora.

Configuração de janelas (IFR, Bollinger, MM, horários de coleta) fica na aba Config. Não há campos de terminal nem planilha auxiliar.
