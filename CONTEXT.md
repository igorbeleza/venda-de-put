# Venda de PUT

Seleção de ações da B3 para vender put, com fundamento setorial e timing técnico. Este arquivo é o glossário. Implementação vive no código e em `docs/sdd.md`.

## Operação

**Venda de put**:
Obrigação de comprar o papel no strike se exercido. Aqui a put é coberta por critério (empresa que se aceita carregar), não por hedge automático.
_Avoid_: covered call, lançamento descoberto

**Janela de abertura**:
Faixa de 45 a 21 dias corridos até o vencimento em que a operação é aberta.
_Avoid_: DTE livre, qualquer série

**Meta 30d**:
Taxa-alvo de prêmio para 30 dias corridos (`meta_premio_30d`, padrão 1,15%).
_Avoid_: yield anual, ROI

**Prêmio-alvo**:
Meta 30d escalada por √(dias corridos / 30) até o vencimento escolhido.
_Avoid_: prêmio linear nos dias

**Prêmio (últ.)**:
Último negócio da put dividido pelo strike. É a taxa que decide a entrada.
_Avoid_: bid/strike, mid, Black-Scholes teórico

**Último**:
`put.close` na cadeia OpLab — último preço negociado daquela put.
_Avoid_: bid, ask, `bs.premium` como fonte

**Volume no dia**:
Negócios da sessão naquela put. Sem volume, o último é cotação velha e não entra.
_Avoid_: open interest, volume do papel à vista

**Strike de entrada**:
Menor strike OTM cujo prêmio (últ.) ainda é ≥ prêmio-alvo. Máxima distância do à vista que ainda paga a meta.
_Avoid_: maior prêmio, ATM, delta-alvo

**OTM**:
Put com strike abaixo do preço à vista.
_Avoid_: ITM, no dinheiro

**Mensal**:
Série cujo dia do mês está entre 15 e 21. Não é “terceira sexta”.
_Avoid_: weekly como padrão

## Listas

**Universo**:
Papéis com put líquida o bastante para o modelo, cada um com um grupo setorial.
_Avoid_: Ibovespa inteiro, carteira livre

**Fundamentalista**:
Top 10 por PctF (ScoreF ranqueado no grupo) — empresas que se aceita carregar se exercido.
_Avoid_: ranking absoluto sem setor; ordenar a ① por ScoreF cru

**Técnico**:
Top 10 por timing (sinal de vender put, depois ScoreT).
_Avoid_: oversold isolado

**Combinado**:
Interseção fundamento × timing, ordenada por ScoreC.
_Avoid_: média simples das duas listas

**SINAL**:
`► VENDER PUT` só quando tendência é alta e timing é entrada. Caso contrário não acende.
_Avoid_: score sozinho como ordem de venda

## Notas

**ScoreF**:
Nota fundamental setorial (ranks de ROE, dívida, múltiplos, etc. dentro do grupo).
_Avoid_: score absoluto entre setores

**ScoreT**:
Ordenação do timing. Com sinal aceso, quanto mais perto da banda inferior, melhor.
_Avoid_: IFR como score

**ScoreC**:
PctF do ativo quando o SINAL está aceso; senão vazio. Ordena a lista combinada.
_Avoid_: produto ScoreF × ScoreT; PctFu da planilha (é desempate `ROW()/1e8`, não percentil no universo)

**PctF**:
Percentil do ScoreF **dentro do grupo**. Menor = melhor do setor.
_Avoid_: percentil nos 86; confundir com ScoreF cru

**IFR**:
RSI de Wilder 14 (clássico). Faixa de entrada 10–50.
_Avoid_: RSI de média simples / Cutler

**MM200**:
Média móvel simples de 200 fechamentos. Tendência alta = preço > MM200.
_Avoid_: exponencial como padrão

**Boll Inf**:
Banda inferior de Bollinger (SMA 20 − 2σ populacional). Timing cola o preço nela, com folga.
_Avoid_: desvio amostral n−1

**HV**:
Volatilidade histórica: desvio amostral de 21 retornos log × √252.
_Avoid_: HV do gráfico de terceiros como definição

**IV**:
Volatilidade implícita do OpLab (`iv_current`).
_Avoid_: IV calculada aqui

## Estados

**Snapshot**:
JSON em disco com ativos, listas, fundamentos, cadeias e carimbos das fontes. O dashboard só lê isso.
_Avoid_: banco, cache em memória como fonte

**Cadeia**:
Puts enxutas por ticker (vencimento, strike, bid, ask, último, símbolo, delta, poe, volume).
_Avoid_: JSON cru do OpLab

**bate a meta**:
Strike de entrada com prêmio (últ.) ≥ prêmio-alvo.
_Avoid_: “ok” na boca do usuário

**abaixo da meta**:
Nenhum OTM líquido bate a meta; mostra-se o de maior taxa mesmo assim.
_Avoid_: esconder o card

**sem série**:
O ticker não tem put naquele vencimento.
_Avoid_: erro, lista vazia

**sem liquidez**:
Há série, mas nenhuma put com último e volume no dia (e OTM/delta válidos).
_Avoid_: misturar com sem série

**sem dado**:
Indicador impossível (histórico curto, IV ausente). Texto visível.
_Avoid_: 0, célula em branco
