# Carteira pessoal

Área autenticada em `/carteira`, separada das oito abas públicas e do login de administrador único. Cada pessoa cadastra os campos amarelos da planilha, administra as próprias operações de opções e acompanha os campos calculados. Ninguém lê nem altera o dado de outra pessoa.

A origem local `spec-carteira.xlsx` é gitignored e **nunca entra no runtime**. Os testes versionam casos mínimos e anonimizados derivados das fórmulas. A autoridade das contas é o código e este documento, não o Excel.

Fronteira de produto: `docs/mvp.md`. Persistência dual e isolamento: `docs/sdd.md` e `docs/adr/0005-carteira-multiusuario-sqlite.md`. Vocabulário: `CONTEXT.md`.

## Fronteira

Três identidades, três papéis:

| Superfície | Quem | O que vê | Persistência |
|---|---|---|---|
| Dashboard público (oito abas) | qualquer um | seleção de venda de put | snapshot JSON global |
| Admin único | senha `VENDA_DE_PUT_ADMIN_PASSWORD` | Config, Feriados, raspar | cookie HMAC de admin |
| Carteira pessoal `/carteira` | login próprio | só os próprios lançamentos | `data/carteira.sqlite3` |

O dashboard público não registra nem fecha a operação. O login pessoal não concede acesso de administrador. O login de administrador não identifica uma pessoa na carteira. Cookies `carteira_session` e `carteira_csrf` nunca autorizam rotas administrativas; o cookie `session` do admin nunca autoriza `/api/carteira`.

Requisições da carteira nunca chamam Yahoo, brapi, Cotahist, OpLab ou Fundamentus. Preço e indicador vêm do snapshot já gravado. Dado ausente é o texto **sem dado**, nunca zero inventado.

## Contrato de dados da planilha

### Campos amarelos

Entradas persistidas no SQLite, sempre filtradas por `user_id` da sessão. A API não aceita `user_id` no corpo.

### Campos calculados

Valores verdes/painel. Recalculados a cada leitura a partir das entradas e do snapshot. Nunca persistidos.

| Área | Persistido (amarelo) | Calculado (verde/painel) |
|---|---|---|
| Conta | caixa na corretora | caixa e composição do patrimônio |
| Minha Carteira | data, ativo, classe, compra/venda, quantidade, preço, observação | valor total; posição; preço médio; valor atual; resultado realizado/não realizado |
| Registro de Operações | data da venda, ativo, ticker da opção, CALL/PUT, quantidade, strike, vencimento, prêmio/ação, status, custo/ação para encerrar, data da recompra | prêmio total; encerramento; resultado líquido; narrativa; risco; moneyness; L/P aberto; dias |
| Evolução | data/custódia; data/tipo/valor/observação de aporte ou retirada | aporte líquido, fluxo, resultado, lucro do período, retorno do período e TWR acumulada |
| Painel | ordenação, filtro de ativo e ano apenas no browser | resumo, opções abertas, visão por ativo, alocações e prêmio mensal |

Dinheiro no banco e na API é inteiro em centavos. Datas são `date`. Observação tem no máximo 500 caracteres. Tickers são gravados em maiúsculas.

## Enums internos

Valores armazenados e no contrato HTTP são as strings em inglês. Rótulos em português são só da UI.

| Enum | Valor | Rótulo |
|---|---|---|
| `AssetClass` | `stock` | Ação |
| `AssetClass` | `margin` | Margem |
| `TradeSide` | `buy` | Compra |
| `TradeSide` | `sell` | Venda |
| `OptionKind` | `put` | Venda de PUT |
| `OptionKind` | `call` | Venda de CALL |
| `OptionStatus` | `open` | Aberta |
| `OptionStatus` | `expired` | Virou pó (expirou) |
| `OptionStatus` | `exercised` | Exercida |
| `OptionStatus` | `closed_early` | Encerrada antes |
| `CashFlowKind` | `contribution` | Aporte |
| `CashFlowKind` | `withdrawal` | Retirada |

`closed_early` exige `close_cost_per_share_cents` e `repurchase_date` (entre venda e vencimento). Os outros status proíbem esses campos. Venda não pode ser posterior ao vencimento.

## Fórmulas (Task 4)

Motor: `compute_operation`, `compute_personal_summary`, `compute_evolution`. Projeção de mercado: `build_market_view(snapshot)` — converte floats do snapshot para centavos com `Decimal` e `ROUND_HALF_UP`, sem I/O e sem filtrar volume da opção.

### Operação

```
premium_total = quantity * premium_per_share_cents
close_total = 0 se close_cost_per_share_cents é None, senão quantity * close_cost_per_share_cents
net_result = premium_total - close_total
```

Data de encerramento: `repurchase_date` se `closed_early`; `expiry_date` se `expired` ou `exercised`; `None` se aberta.

Distância: `underlying - strike` (`None` sem cotação do papel). Fração = distância / strike.

Moneyness: `None` sem papel; `ATM` se igual ao strike; PUT `ITM` se papel < strike, senão `OTM`; CALL `ITM` se papel > strike, senão `OTM`.

L/P aberto só existe com status `open` e cotação da opção:

```
open_profit_cents = (premium_per_share_cents - option_price) * quantity
```

Sem cotação ou se a operação não está aberta: `None`, nunca zero. `expiry_state` é `overdue`, `today` ou `future`. `days_to_expiry` pode ser negativo. A narrativa usa os quatro desfechos da planilha e nunca trata ausência como zero.

### Carteira e resumo

```
shares = bought_quantity - sold_quantity
average_buy_price = bought_total_cents / bought_quantity   (None se bought_quantity == 0)
market_value_cents = shares * spot                         (None se shares <= 0 ou spot ausente)
unrealized_cents = (spot - average_buy_price) * shares     (None se shares <= 0, spot ou preço médio ausente)
realized_stock_cents = sold_total_cents - average_buy_price * sold_quantity
put_risk_cents = soma(quantity * strike) das PUT abertas   (nunca precisa de cotação)
```

Médias e totais passam por `_round_cents` (`quantize("1", ROUND_HALF_UP)`).

`premium_received_cents` soma o prêmio bruto de **toda** operação registrada. `option_net_result_cents` soma `net_result` (inclui o prêmio bruto das abertas, como a planilha). `realized_total_cents = option_net_result_cents + realized_stock_cents`. `unrealized_result_cents` é só o não realizado das ações (`Painel!G50:G99`); L/P de opção aberta fica em `open_operations`. `monthly_premiums_cents` agrupa prêmio bruto por `sale_date.month` no ano escolhido. Cobertura de CALL: `no_calls`, `covered` ou `uncovered` (ações vs quantidade de CALL aberta).

Agregados de mercado (valor das ações, valor da margem, passivo de opção, patrimônio líquido) incluem só quantidade líquida positiva. Se alguma posição positiva obrigatória não tem preço, o agregado é `None` e o ticker entra em `missing_quotes`. `put_capital_at_risk_cents` não precisa de cotação. `headroom_cents = cash + margin - risk` só quando caixa e margem são conhecidos. `net_worth_cents = cash + stocks + margin - open_options` só quando os quatro componentes são conhecidos.

### Completude

Cotação ausente é `None` / **sem dado**, nunca zero. `missing_quotes` lista cada ticker de papel ou opção que faltou. `MarketView.empty()` não inventa preço.

### Evolução (TWR)

Para cada data de custódia:

- aporte líquido acumulado = aportes − retiradas até a data
- fluxo do período = acumulado atual − acumulado anterior
- resultado total = custódia − acumulado
- lucro do período = (custódia atual − custódia anterior) − fluxo do período
- retorno do período = custódia atual / (custódia anterior + fluxo do período) − 1
- TWR acumulada = (1 + TWR anterior) × (1 + retorno do período) − 1

Denominador zero → `None`, não zero.

## Endpoints (Task 5)

Prefixo `/api/carteira`. Sessão em `carteira_session` (HttpOnly). CSRF em `carteira_csrf` (não HttpOnly) + header `X-CSRF-Token` em toda mutação. `GET me` nunca devolve hash nem `user_id`.

| Método/caminho | Sucesso | Contrato |
|---|---:|---|
| `POST /api/carteira/auth/register` | 201 | `{username,password}` → usuário, cookies e `csrf_token` |
| `POST /api/carteira/auth/login` | 200 | mesmo contrato sem criar usuário |
| `POST /api/carteira/auth/logout` | 200 | revoga sessão e apaga os dois cookies; exige CSRF |
| `GET /api/carteira/me` | 200 | `{authenticated, username}` |
| `GET/PUT /api/carteira/account` | 200 | `cash_cents: int \| null` |
| `GET/POST /api/carteira/{collection}` | 200/201 | lista própria / criação; `collection` é `portfolio`, `operations`, `custody` ou `cash-flows`; operações incluem campos calculados de `OperationPerformance` |
| `GET /api/carteira/{collection}/{id}` | 200 | registro próprio; 404 se alheio ou inexistente |
| `PUT/DELETE /api/carteira/{collection}/{id}` | 200/204 | somente o próprio; 404 se alheio ou inexistente |
| `GET /api/carteira/summary?year=YYYY` | 200 | `PersonalSummary`; `year` entre 2000 e 2100 |

Coleções: `portfolio`, `operations`, `custody`, `cash-flows`. Isolamento HTTP: id de outro dono responde 404, nunca 403 com o registro.

## Backup local

`data/carteira.sqlite3` (e `-wal` / `-shm`) é estado de runtime, fora do git.

Backup válido:

1. processo FastAPI parado, depois copiar `carteira.sqlite3` e, se existirem, `-wal` e `-shm`; ou
2. API de backup online do SQLite (`VACUUM INTO` / `backup`).

Copiar só o arquivo principal com WAL ativo **não** é backup. Este documento não descreve deploy nem escrita em VPS.
