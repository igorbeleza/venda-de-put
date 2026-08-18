# Runbook de deploy — venda de PUT

Documentação apenas. **Não executar estes passos sem o output do levantamento colado na conversa e o `SERVER_NAME` informado pelo usuário.** Nenhuma escrita na VPS antes disso.

Serviço da app: `127.0.0.1:8765` (nunca `0.0.0.0`). Nginx novo + `reload` (nunca `restart`).

## Proibido

- `apt upgrade`
- `pip install` no Python do sistema (só no venv em `/opt/venda-de-put/.venv`)
- `ufw` / `iptables` / Security List
- `certbot` em certificado alheio (HTTPS só se o levantamento mostrar o mesmo padrão já usado nos outros sites)
- Bind em `0.0.0.0`
- Editar, mover ou apagar qualquer arquivo nginx que já exista
- `systemctl restart nginx`

## Ordem (literal)

### 1. Não escrever nada — levantamento

Rodar e **colar na conversa**:

```bash
nginx -T
ss -tlnp
systemctl list-units --type=service --state=running
df -h
```

Confirmar: porta 8765 livre (ou escolher outra alta livre), hosts já servidos pelo nginx, espaço em disco.

### 2. Esperar o usuário

Aguardar confirmação e que o usuário informe:

- `SERVER_NAME` (subdomínio apontando para a VPS)
- senha do administrador único (`VENDA_DE_PUT_ADMIN_PASSWORD`, ADR 0004 — a
  senha **não** vai para o git)

### 3. Backup do nginx

```bash
sudo tar czf ~/nginx-backup-$(date +%F).tar.gz /etc/nginx
```

### 4. Usuário, diretório, venv, app

```bash
sudo useradd --system --home /opt/venda-de-put --shell /usr/sbin/nologin venda-de-put
sudo mkdir -p /opt/venda-de-put/data /opt/venda-de-put/etc
# copiar o código do projeto para /opt/venda-de-put
sudo python3 -m venv /opt/venda-de-put/.venv
sudo /opt/venda-de-put/.venv/bin/pip install /opt/venda-de-put
sudo chown -R venda-de-put:venda-de-put /opt/venda-de-put
```

Porta **8765** somente se o `ss` do passo 1 mostrou livre; senão outra porta alta livre e ajustar unit + template nginx.

Units (a partir deste repositório):

```bash
sudo cp deploy/venda-de-put.service /etc/systemd/system/
sudo cp deploy/venda-de-put-scrape.service /etc/systemd/system/
sudo cp deploy/venda-de-put-scrape.timer /etc/systemd/system/
sudo systemctl daemon-reload
```

### 5. Segredos do login de admin (ADR 0004)

O site é público; só a aba Config, feriados e a raspagem manual pedem login
de administrador. Credenciais ficam num `EnvironmentFile` fora do git, nunca
no unit do systemd:

```bash
sudo mkdir -p /opt/venda-de-put/etc
sudo tee /opt/venda-de-put/etc/venda-de-put.env > /dev/null <<'EOF'
VENDA_DE_PUT_ADMIN_PASSWORD=SENHA_DO_ADMIN
VENDA_DE_PUT_SECRET_KEY=CHAVE_ALEATORIA_LONGA
EOF
sudo chown root:venda-de-put /opt/venda-de-put/etc/venda-de-put.env
sudo chmod 640 /opt/venda-de-put/etc/venda-de-put.env
```

Gerar `VENDA_DE_PUT_SECRET_KEY` com `openssl rand -hex 32` (ou equivalente) —
sem essa variável fixa, o processo gera uma chave em memória a cada start e
a sessão do admin cai a cada restart/deploy.

Htpasswd/`auth_basic` do nginx não é mais necessário só para visitar o site
(o template não traz mais essa diretiva). Se o usuário quiser mantê-lo por
outro motivo, é uma decisão à parte, fora deste runbook.

### 6. Arquivo nginx **novo** apenas

Substituir `SERVER_NAME` no template `deploy/nginx-venda-de-put.conf.template` (e a porta do `proxy_pass` se não for 8765).

```bash
sudo cp /caminho/para/nginx-venda-de-put.conf /etc/nginx/sites-available/venda-de-put
sudo ln -s /etc/nginx/sites-available/venda-de-put /etc/nginx/sites-enabled/venda-de-put
```

**Zero** edits em arquivos que já existiam em `/etc/nginx/`.

HTTPS: só se o levantamento (`nginx -T`) mostrar certbot / `include snippets/ssl.conf` + 443 nos outros sites — **replicar o mesmo esquema** no arquivo novo. Não inventar certbot.

### 7. Validar nginx

```bash
sudo nginx -t
```

Qualquer erro: remover o symlink e parar.

```bash
sudo rm /etc/nginx/sites-enabled/venda-de-put
```

### 8. Aplicar com reload

```bash
sudo systemctl reload nginx
```

Nunca `restart`.

### 9. Sites antigos intactos

Para cada host que o `nginx -T` listou:

```bash
curl -I https://SITE_ANTIGO
```

Deve continuar 200/301 como antes.

### 10. Site público e login de admin

Dashboard sem qualquer credencial → `200` e HTML do Dashboard (site público,
ADR 0004):

```bash
curl -I http://SERVER_NAME
```

Config sem sessão → `401` na escrita; login de admin → cookie de sessão e
`200`:

```bash
curl -i -X PUT http://SERVER_NAME/api/config -H 'Content-Type: application/json' -d '{}'
# 401 esperado

curl -i -c /tmp/venda-de-put-cookie -X POST http://SERVER_NAME/api/login \
  -H 'Content-Type: application/json' -d '{"password":"SENHA_DO_ADMIN"}'
# 200 esperado, Set-Cookie: session=...

curl -i -b /tmp/venda-de-put-cookie http://SERVER_NAME/api/me
# {"admin": true}
```

### 11. Serviços

```bash
sudo systemctl enable --now venda-de-put.service venda-de-put-scrape.timer
```

Timer: Mon–Fri 11:00, 13:00, 16:00 America/Sao_Paulo, e 07:00 nos dias 1 e 15.

## Pós-deploy (opcional)

```bash
sudo systemctl status venda-de-put.service
sudo systemctl list-timers venda-de-put-scrape.timer
sudo -u venda-de-put /opt/venda-de-put/.venv/bin/python -m venda_de_put scrape
```
