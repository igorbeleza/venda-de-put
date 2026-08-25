# MVP — Venda de PUT

O que o produto é hoje. Autoridade de escopo. Mudança de fronteira começa aqui.

## Promessa

Uma página web, no celular e no desktop, que responde: **quais papéis do universo eu aceito vender put agora**, com strike e taxa no vencimento que eu escolhi.

Substitui a planilha Excel + terminal de corretora. O modelo de scoring (ranks setoriais, tendência, timing) está no código.

## Cabe no MVP

- Oito abas: Dashboard, Ativos, Dados, Setores, Config, Vencimentos, Feriados, Instruções.
- Três listas Top 10 no Dashboard (fundamentalista, técnico, combinado) com os textos narrativos fixos.
- Seletor de vencimento. Padrão: próximo mensal. Toggle “só mensais”.
- Prêmio-alvo = meta 30d × √(dias corridos / 30). Meta 30d editável no Config, na calculadora, em porcentagem (1,15%), gravada como fração. O 1% que se busca no strike em 30 dias vira 1,15% porque a put é recomprada com 70% do prêmio exaurido (venda 1,00 → recompra 0,30), sem depender do prazo. O dashboard não registra nem fecha a operação; só escolhe strike com essa meta.
- Aba Config / Raspagem: carimbo da última coleta, passos por fonte e retry do passo que falhou (com dependentes; ciclo inteiro se a coleta tem mais de 1 hora).
- Strike de entrada no vencimento escolhido (ver `docs/sdd.md`).
- Coleta Yahoo + OpLab + Fundamentus → snapshot em disco. Se o Yahoo perde um ticker (3 tentativas), o scrape busca à vista na brapi.dev; sem técnico anterior aproveitável, monta histórico pelos ZIPs Cotahist da B3. Botão Atualizar relê o arquivo; não raspa. Cotações ~15 minutos atrasadas em relação ao horário da raspagem.
- Cotações separadas nas abas: Ativos mostra o à vista da última raspagem (`preco`: Yahoo, ou brapi/Cotahist no fallback), com carimbo da coleta; Dados mostra os indicadores do Fundamentus com a cotação dele — não o preço da raspagem.
- CLI: `python -m venda_de_put scrape` e `serve`.
- Dashboard, Ativos, Dados, Setores, Vencimentos e Instruções são públicos, sem login. A UI resolve `static/` e `api/` relativo à página, então o site pode ficar num path (não só na raiz do host).
- Login de administrador único (senha em `VENDA_DE_PUT_ADMIN_PASSWORD`, sessão por cookie assinado) gateia as abas Config e Feriados (ambas somem do menu pra quem não está logado) e o botão de raspar sob demanda — ver `docs/adr/0004-login-admin-unico.md`. Deploy não precisa mais de htpasswd no nginx para o site ser visto; pode manter por outros motivos.
- Horizonte do calendário de Vencimentos (`calendario_ate`, hoje 31/12/2027) é editável no Config, mesma tela do admin.

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

Fora deste arquivo até o produto pedir: diário de trades, alerta, live quote, filtro duro da janela 45–21 no seletor.
