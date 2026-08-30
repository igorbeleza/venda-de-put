# 0005: Carteira multiusuário em SQLite

## Contexto

O snapshot JSON representa um estado global de mercado produzido pela raspagem. A carteira pessoal tem outro ciclo de vida: várias pessoas alteram lançamentos independentes, e cada alteração precisa preservar relações e regras de integridade.

A identidade da carteira também não é a identidade do administrador. O administrador mantém o acesso a Config, Feriados e à raspagem sob demanda. Cada pessoa usa outro login para acessar somente a própria carteira.

## Decisão

O snapshot público continua em `data/snapshots/current.json`. A carteira pessoal usa `data/carteira.sqlite3` e migrações versionadas.

`users` é a raiz de propriedade. Sessões e registros pessoais pertencem a um `user_id`, com chaves estrangeiras e exclusão em cascata. Consultas e alterações sempre filtram o proprietário autenticado. A API não aceita um `user_id` informado pelo cliente.

O login de administrador e os logins pessoais são independentes. Uma sessão administrativa não abre uma carteira, e uma sessão pessoal não concede acesso administrativo.

O banco persiste somente dados informados pela pessoa. Posições, saldos calculados, P&L, rentabilidade e outros valores derivados são recalculados a partir dos registros pessoais e do snapshot público.

## Por que SQLite

SQLite fornece transações, chaves estrangeiras, restrições e migrações sem adicionar outro serviço ao processo único atual. O volume da carteira cabe em um arquivo local, e o modo WAL permite leituras durante gravações curtas.

JSON continua adequado ao snapshot global, que a raspagem substitui como uma unidade. JSON não é adequado a alterações concorrentes de registros relacionados nem impõe as regras de propriedade e integridade da carteira.

PostgreSQL resolveria essas regras, mas exigiria um serviço, credenciais, backup e operação adicionais. Esse custo não se justifica para o volume e o modelo de implantação atuais.

## Consequências

As requisições pessoais usam apenas o SQLite e o snapshot já gravado. Elas nunca chamam as fontes de mercado.

Cada nova mudança de schema exige uma migração transacional e repetível. A aplicação registra a versão somente depois que todos os comandos da migração terminam.

O arquivo SQLite e seus arquivos `-shm` e `-wal` são estado de runtime e não entram no Git.
