# MVP — Venda de PUT

O que o produto é hoje. Autoridade de escopo. Mudança de fronteira começa aqui.

## Promessa

Uma página web, no celular e no desktop, que responde: **quais papéis do universo eu aceito vender put agora**, com strike e taxa no vencimento que eu escolhi.

Substitui a planilha Excel + terminal de corretora. O modelo de scoring (ranks setoriais, tendência, timing) está no código.

## Cabe no MVP

- Oito abas: Dashboard, Ativos, Dados, Setores, Config, Vencimentos, Feriados, Instruções.
- Três listas Top 10 no Dashboard (fundamentalista, técnico, combinado) com os textos narrativos fixos.
- Seletor de vencimento. Padrão: próximo mensal. Toggle “só mensais”.
- Prêmio-alvo = meta 30d × √(dias corridos / 30). Meta 30d editável no Config.
- Strike de entrada no vencimento escolhido (ver `docs/sdd.md`).
- Coleta Yahoo + OpLab + Fundamentus → snapshot em disco. Botão Atualizar relê o arquivo; não raspa.
- CLI: `python -m venda_de_put scrape` e `serve`.
- Sem login na app (deploy pode pôr htpasswd no nginx).

## Janela e entrada

- Operação abre com **45 a 21 dias corridos** até o vencimento. O seletor lista outras séries para consulta.
- Taxa da put = **último / strike**, só com volume no dia.
- Entra o **menor strike OTM** (delta ≥ −0,45) cuja taxa ≥ prêmio-alvo.

## Não cabe

- Registrar operação, P&L, ajuste ou exercício.
- Banco, usuário, multi-tenant.
- Raspar a cada request ou no botão Atualizar.
- Escolher strike por bid, mid ou prêmio teórico.
- Reordenar as listas ao trocar o vencimento.
- Inventar 0 no lugar de “sem dado”.
- Dependência de terminal de corretora em runtime.

## Pronto quando

- `python -m pytest` passa.
- Dashboard mostra as três listas, strike e meta do vencimento escolhido.
- Ativos, Dados, Config e Instruções abrem sem terminal.
- Scrape grava snapshot; a UI só lê.

## Depois do MVP

Fora deste arquivo até o produto pedir: diário de trades, alerta, live quote, filtro duro da janela 45–21 no seletor, último período dos indicadores = instante da raspagem (`docs/superpowers/specs/2026-08-17-indicadores-ultimo-periodo.md`).
