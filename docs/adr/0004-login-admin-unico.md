# 0004 — Login de administrador único, site público

## Contexto

O MVP original (`docs/mvp.md`) dizia "sem login na app"; o controle de acesso
era só o htpasswd do nginx (template local, fora do git),
protegendo o site inteiro para um único usuário (`igor`).

Passa a existir um pedido explícito: o dashboard deve ficar totalmente
público (Dashboard, Ativos, Dados, Setores, Vencimentos, Feriados, Instruções
sem login), e só a aba **Config** — que já edita `AppConfig` via
`PUT /api/config` — mais a edição de feriados e uma raspagem manual sob
demanda ficam atrás de um login de administrador. Só existe um administrador.

## Decisão

- **Login único, sem banco.** Credencial em `VENDA_DE_PUT_ADMIN_PASSWORD`
  (variável de ambiente, nunca no git — segue o padrão de
  `VENDA_DE_PUT_DATA` em `paths.py`). `docs/mvp.md` já exclui "Banco,
  usuário, multi-tenant" do escopo; um segundo administrador não é um caso
  a resolver agora.
- **`.env` local, o mesmo arquivo em produção.** `venda_de_put.paths.load_dotenv`
  lê `VAR=valor` de um `.env` no diretório de trabalho pra `os.environ`, sem
  sobrescrever o que já estiver exportado — chamado no início de
  `__main__.main()`. Nenhuma dependência nova (sem `python-dotenv`). Local:
  copiar `.env.example` pra `.env` e preencher. Produção: o mesmo `.env`
  vai pro `WorkingDirectory` do serviço (caminho no runbook local, fora
  do git) — sem `Environment=`/`EnvironmentFile=` no unit.
- **Sessão por cookie assinado**, não por biblioteca de terceiros. HMAC-SHA256
  com `hmac`/`hashlib`/`secrets` da stdlib (`src/venda_de_put/auth.py`).
  Chave em `VENDA_DE_PUT_SECRET_KEY`; se ausente, uma chave é gerada em
  memória no start do processo — sessões não sobrevivem a um restart nesse
  caso, aceitável para uma ferramenta de administrador único.
  Atrás de um prefixo no proxy, `Path` do cookie é o
  `X-Forwarded-Prefix` e `Secure` liga se `X-Forwarded-Proto` é https
  (senão o cookie vazaria na raiz do host compartilhado).
- **Escopo do gate (API)**: `require_admin` protege `PUT /api/config`,
  `PUT /api/feriados`, `POST /api/scrape` e `GET /api/scrape/status`. Todo
  `GET` de leitura (dashboard, ativos, dados, setores, vencimentos,
  feriados, instruções) continua público, sem exceção — inclusive
  `GET /api/feriados`.
- **Escopo do gate (UI)**: mais restrito que a API. A aba **Feriados**
  também some do menu pra quem não está logado (igual Config), não só o
  formulário de edição — não faz sentido mostrar uma tabela de feriados sem
  nenhuma ação possível. `GET /api/feriados` continua respondendo pra quem
  bater direto na API sem sessão; só a navegação pela aba é que fica
  admin-only.
- **Raspagem sob demanda não importa `scrape.py` em `app.py`.** Essa
  fronteira já era uma decisão de arquitetura (`docs/sdd.md`: "API. Não
  importa `run_scrape`", garantida por
  `tests/test_refresh_import_guard.py`). `POST /api/scrape` sobe
  `sys.executable -m venda_de_put scrape [--force-fundamentus true|false]
  [--from-step yahoo|oplab|fundamentus|oplab_cadeia]` como subprocesso via
  `BackgroundTasks`, o mesmo mecanismo que o timer systemd local já usa —
  a rota HTTP só troca o agendador (systemd) por um clique de admin,
  sem furar o processo único documentado. `app.py` pode ler
  `scrape_progress.py` (passos e regra das 1 hora); continua proibido
  importar `scrape.py` / `run_scrape`.
- **`force_fundamentus`** (`scrape.py`, `should_fetch_fundamentus`,
  `run_scrape`, `__main__.py --force-fundamentus`) é um override explícito:
  `None` mantém o agendamento de sempre (`cfg.fundamentus_days`/
  `fundamentus_time`), `True` força a raspagem do Fundamentus agora,
  `False` pula mesmo que o dia bata. `cli_scrape`/o timer do systemd não
  passam esse parâmetro — comportamento agendado é idêntico ao de antes.
- **Retry de passo** (`POST /api/scrape` com `passo`, CLI `--from-step`):
  refaz o passo e os dependentes (Yahoo → os quatro; OpLab → OpLab+Cadeia;
  Fundamentus → Fundamentus+Cadeia; Cadeia → só Cadeia). Se
  `generated_at` da última coleta tem mais de 1 hora, o recorte é ignorado
  e roda o ciclo inteiro (`retry_completo` no status).
- **nginx deixa de ser obrigatório para visitar o site.** O proxy reverso
  não precisa de `auth_basic`. TLS/certbot é decisão à parte, no runbook
  local.

## Alternativas descartadas

- **Banco de usuários / múltiplos administradores** — fora do MVP
  explicitamente; adicionaria uma tabela e uma UI de gestão de usuário para
  um caso que não existe (um administrador).
- **Biblioteca de sessão (itsdangerous, `SessionMiddleware`)** — dependência
  nova só para assinar um cookie; `hmac` da stdlib resolve com o mesmo
  nível de segurança para esse volume de tráfego.
- **Manter o htpasswd do nginx como único gate** — deixaria de existir uma
  página pública, que é o pedido. Também não dava para diferenciar
  visitante de administrador dentro da mesma UI.
- **Raspagem sob demanda in-process (`BackgroundTasks` chamando
  `run_scrape` direto)** — foi a primeira tentativa de implementação;
  descartada em cima da hora por violar o guard de arquitetura de
  `web/app.py` nunca importar `scrape.py` (achado pelo executor da tarefa,
  que perguntou antes de prosseguir — ver `orca orchestration ask` no
  histórico da tarefa). Subprocesso preserva a fronteira e reaproveita o
  mesmo caminho que o systemd timer já exercita em produção.

## Consequências

- Dois segredos novos em produção: `VENDA_DE_PUT_ADMIN_PASSWORD` e
  `VENDA_DE_PUT_SECRET_KEY`, via `.env` copiado pro servidor (não versionado
  — ver runbook local em `deploy/`).
- `GET /api/scrape/status` deixou de ser público durante a implementação
  (revisão apontou que o campo `erro` vaza stderr do subprocesso) — também
  gateado por `require_admin`.
- Reiniciar o processo sem `VENDA_DE_PUT_SECRET_KEY` fixo derruba a sessão
  do administrador (ele loga de novo); não afeta visitantes, que nunca
  tinham sessão.
