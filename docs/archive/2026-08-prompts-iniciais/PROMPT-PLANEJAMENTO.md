# Dashboard de Venda de PUT — Prompt de Planejamento

> **Arquivo.** História de agosto/2026. Não é autoridade. Leia `AGENTS.md`, `docs/mvp.md` e `docs/sdd.md`.

**Persona:** você é um **especialista sênior em finanças**, com domínio de mercado de opções da B3, análise fundamentalista e análise técnica — e escreve código. Trate o assunto com o vocabulário e o rigor de quem opera: prêmio, delta, moneyness, IV Rank, capital travado, probabilidade de exercício e risco de exercício são conceitos que você já domina, não termos a pesquisar. Quando o modelo transcrito aqui tiver um problema de mérito financeiro — e não apenas de implementação — aponte antes de codificar.

Você vai planejar e depois construir um dashboard web que recomenda ativos da B3 para venda de PUT, substituindo uma planilha Excel que hoje depende do Profit/Nelogica via RTD.

Leia este documento inteiro antes de propor qualquer coisa. Ele é auto-contido: **não é necessário abrir o arquivo `carteira_venda_put (4).xlsx`** — todo o modelo de cálculo está transcrito abaixo. O `.xlsx` continua no repositório apenas como referência histórica.

---

## 1. O que existe hoje

Uma planilha com 8 abas que funciona assim:

```
Fundamentus (colado à mão)  ──▶  aba Dados (994 linhas, 22 colunas)
                                      │ VLOOKUP
Profit via RTD ──────────────────▶  aba "Ativos Líquidos e Informações"
(preço, MM200, IFR,                   │ 86 tickers, colunas A→BD
 Bollinger, IV, HV)                   │ ranking por percentil dentro do setor
                                      ▼
                                 aba Dashboard — 3 listas Top 10
```

**Três problemas que motivam a reconstrução:**

1. `=RTD("rtdtrading.rtdserver",,"PETR4_B_0","ULT")` só funciona no Excel desktop, no Windows, com o Profit aberto. Preço, MM200, IFR, Bollinger, IV e HV — todos os dados de mercado — dependem disso.
2. Os códigos RTD de volatilidade (387 e 45) retornam `Atributo Inválido`. As colunas IV, HV, IV/HV e "Prêmio?" estão vazias na planilha atual.
3. A planilha recomenda o **ativo**, mas não o **strike** — o usuário ainda precisa abrir o Profit para montar a operação.

---

## 2. Arquitetura decidida

Estas decisões já foram tomadas com o usuário. **Não as reabra**; se achar que alguma está errada, diga por quê antes de implementar.

| Decisão | Escolha |
|---|---|
| Onde roda | Servidor próprio, acessível de qualquer lugar (incluindo celular) |
| Hospedagem | **VPS Oracle Cloud já existente** — Ubuntu, `ubuntu@[VPS]`. ⚠️ **Já hospeda outros sites em nginx que não podem ser tocados.** Ver seção 2.1, que é inegociável |
| Acesso | **URL pública, sem senha** |
| Raspagem | **Horários fixos**: 11h00, 13h00 e 16h00 (BRT), dias úteis. Fundamentus **2× por mês** (dias 1 e 15, às 7h00). Tudo configurável por variável de ambiente |
| Botão Atualizar | **Nunca dispara raspagem.** Apenas relê o snapshot em cache e mostra o carimbo de quando foi coletado |
| Fonte da verdade | O **código** recalcula todo o scoring. O Excel vira legado |
| Stack | **Python + FastAPI** (raspagem, pandas, agendador) + **HTML/CSS/JS puro** no front. Sem framework de front, sem build step, sem Tailwind |
| Layout | **Dashboard-first**: sidebar esquerda única (fixa, por enquanto com um item só) + abas horizontais no topo do conteúdo, replicando as 8 abas do Excel — mas cada aba desenhada como tela de produto, não como grade de células |
| Universo | Os **86 tickers curados** (lista na seção 6), editáveis pela interface |
| Cadeia de opções | Buscada **apenas para os ativos que entraram nas listas** (~10-25 páginas por ciclo, não 86) |
| Vencimento | **Escolhido pelo usuário num seletor no topo do Dashboard.** Padrão = próximo mensal; opção de mostrar também os semanais. Trocar o vencimento recalcula os strikes na hora, **sem nova raspagem**. Ver seções 7 e 11.6 |
| Escopo | **Somente recomendação.** Registro de operações fica para outro momento — não construa |

**Por que o botão Atualizar não raspa:** a URL é pública e sem senha. Se o botão disparasse raspagem, qualquer pessoa poderia clicar repetidamente e disparar centenas de requisições ao Yahoo, OpLab e Fundamentus. O resultado não seria lentidão — seria o IP do servidor na lista negra das três fontes, derrubando o dashboard por tempo indeterminado.

### 2.1 Restrições da VPS — leia antes de tocar no servidor

O servidor **já está em produção com outros sites servidos por nginx**. Esses sites não têm relação com este projeto e **não podem ser afetados de nenhuma forma**. Uma queda deles é falha grave, não efeito colateral aceitável.

**Proibido, sem exceção:**

- Editar, mover ou apagar qualquer arquivo existente em `/etc/nginx/nginx.conf`, `/etc/nginx/sites-available/`, `/etc/nginx/sites-enabled/` ou `/etc/nginx/conf.d/`
- `systemctl restart nginx` — reiniciar derruba os sites existentes durante a troca
- Mexer em certificados, no `certbot`, ou em qualquer `server_name` que já exista
- `apt upgrade`, troca de versão do Python do sistema, ou `pip install` fora de virtualenv
- Alterar regras de firewall, `iptables`, ou Security List / NSG do Oracle Cloud
- Ocupar as portas 80 e 443, ou qualquer porta já em uso

**O caminho correto:**

1. **Antes de qualquer coisa**, faça o levantamento e mostre ao usuário: `nginx -T` (dump da configuração efetiva), `ss -tlnp` (portas em uso), `systemctl list-units --type=service --state=running`, e `df -h`. Não escreva nada antes de o usuário confirmar o que encontrou.
2. Aplicação isolada em `/opt/venda-de-put/`, com usuário de serviço próprio e **virtualenv próprio**. Nada instalado no Python do sistema.
3. Serviço `systemd` próprio (`venda-de-put.service`), ligado a **`127.0.0.1:PORTA`** — nunca a `0.0.0.0`. Escolha uma porta alta e livre, confirmada pelo `ss -tlnp` do passo 1.
4. **Um único arquivo novo** em `/etc/nginx/sites-available/venda-de-put`, com `server_name` próprio (subdomínio), fazendo `proxy_pass` para a porta local. Nenhum arquivo existente é editado — apenas um novo é criado e um symlink adicionado em `sites-enabled/`.
5. Antes de ativar: **`sudo nginx -t`**. Se der qualquer erro, remova o symlink e pare. Nunca prossiga com configuração que não valida.
6. Para aplicar: **`sudo systemctl reload nginx`** — reload, jamais restart. Reload troca a configuração sem derrubar conexão.
7. Depois de aplicar, **verifique que os sites antigos continuam respondendo** antes de declarar sucesso.
8. Backup de `/etc/nginx` antes de mexer: `sudo tar czf ~/nginx-backup-$(date +%F).tar.gz /etc/nginx`.

**Porque o proxy passa pelo nginx que já está nas portas 80/443, nenhuma mudança de firewall é necessária** — nem no `iptables` local (o Ubuntu do Oracle Cloud vem com regras próprias que bloqueiam portas mesmo quando a Security List permite), nem no console da Oracle. Se o acesso fosse por porta direta, seriam necessárias as duas coisas. Evite isso.

**Falta definir:** o `server_name`. Requer um subdomínio apontando por DNS para `[VPS]`. Pergunte ao usuário qual domínio usar antes de escrever o arquivo do nginx — não invente um.

**Sobre bloqueio de IP:** o IP é de datacenter, o que aumenta o risco de Fundamentus e OpLab bloquearem. Os horários fixos e o volume baixo (~86 requisições ao Yahoo e ~10-25 ao OpLab, três vezes ao dia) são a mitigação. Se o bloqueio acontecer, a alternativa é o script de raspagem rodar na máquina do usuário e publicar o JSON na VPS.

---

## 3. Fontes de dados

Nenhuma exige assinatura. Todas são acessadas por raspagem/HTTP direto.

### 3.1 Yahoo Finance — preço e tudo que é técnico

```
GET https://query1.finance.yahoo.com/v8/finance/chart/{TICKER}.SA?range=2y&interval=1d
```

Verificado: JSON limpo, **sem autenticação, sem cookie, sem crumb**. Retorna `timestamp[]` e `indicators.quote[0].{open,high,low,close,volume}` mais `adjclose`. Para `PETR4.SA`: 494 candles, moeda `BRL`, bolsa `SAO`, timezone `America/Sao_Paulo`. Alguns elementos vêm `null` — trate como buraco, não como zero.

Daqui saem: **preço atual, MM200, IFR(14), Bandas de Bollinger, HV, máxima/mínima de 52 semanas**.

⚠️ É uma API não oficial. Isole-a atrás de uma interface `PriceSource` para poder trocar sem reescrever nada.

### 3.2 OpLab (portal livre) — tudo que é de opção

Sem login. Cotações com 15 minutos de atraso. Timestamps já em formato brasileiro (`13/08/26, 12:05:29`).

✅ **Não raspe o HTML.** Verificado: o portal é Next.js e serve o payload inteiro em `<script id="__NEXT_DATA__">`. Um `GET` com `requests` + `json.loads` entrega tudo. **Leia a seção 11.2 antes de escrever o parser** — ela traz o contrato dos campos e uma armadilha que inverte o preço das puts.

**Lista de ativos** — `https://opcoes.oplab.com.br/mercado-de-opcoes` (`/mercado` redireciona para cá)
239 tickers em `pageProps.stocks[]` com `close`, `variation`, `volume`, `iv_current`, `iv_1y_rank`, `iv_1y_percentile`. **Cobre os 86 do universo.**

**Cadeia por ativo** — `https://opcoes.oplab.com.br/mercado/acoes/opcoes/{TICKER}`
`pageProps.series[]` com `due_date` (ISO), `days_to_maturity` (dias úteis) e `strikes[]`, cada strike com `call{}` e `put{}` completos — inclusive `bs{}` com **delta, gamma, vega, theta, poe (prob. de exercício), volatility e moneyness já calculados**.
`pageProps.asset` traz `close/open/high/low/bid/ask`, `iv_current`, `ewma_current`, `stdv_1y`, `beta_ibov`.

Não tem: open interest nem volume em contratos.

⚠️ A coluna `Venc.` **da tela** vem em dias úteis, mas isso é só apresentação — **o JSON traz `due_date` em ISO**. Não há conversão a fazer.

### 3.3 Fundamentus — fundamentos

```
GET https://fundamentus.com.br/resultado.php
```

HTML servido pelo servidor, sem JavaScript, sem cookie. **Encoding ISO-8859-1** — decodifique explicitamente ou os acentos viram lixo. Números em formato brasileiro (`1.234,56`), percentuais com `%`. ~500+ linhas, 22 colunas, exatamente na ordem da aba `Dados`:

```
Papel, Cotação, P/L, P/VP, PSR, Div.Yield, P/Ativo, P/Cap.Giro, P/EBIT,
P/Ativ Circ.Liq, EV/EBIT, EV/EBITDA, Mrg Bruta, Mrg Ebit, Mrg. Líq.,
Liq. Corr., ROIC, ROE, Liq.2meses, Patrim. Líq, Dív.Líq/Patrim, Cresc. Rec.5a
```

Substitui a colagem manual. Roda **2× por mês** (dias 1 e 15, às 7h00) — fundamento muda por trimestre, e o Fundamentus só se move quando sai balanço. Raspar mais que isso é gastar requisição em dado que não mudou.

### 3.4 Fronteira entre as fontes

Mantenha limpa, para não ter dois números divergentes na mesma tela:

- **Yahoo** → preço à vista e todos os indicadores do ativo
- **OpLab** → só o que é de opção: IV, IV Rank, IV Percentil, cadeia, strikes
- **Fundamentus** → só balanço

---

## 4. O modelo de scoring — transcrição fiel do Excel

⚠️ **A armadilha central: nas colunas de rank e score, MENOR É MELHOR.** Os valores são posições dentro do setor, não notas. Rank 1 = o melhor do grupo. O Excel usa `SMALL()` para montar as listas. Uma reimplementação que ordene decrescente produzirá exatamente as piores empresas no topo, com aparência perfeitamente plausível. Escreva teste para isso.

### 4.1 Agrupamento

Cada ativo pertence a um `Grupo` (setor). Todos os ranks são calculados **dentro do próprio grupo**, nunca contra o universo inteiro — comparar P/L de banco com P/L de mineradora não significa nada.

14 grupos, somando 86 ativos:

| Grupo | Qtd | Grupo | Qtd |
|---|---|---|---|
| Financeiro | 14 | Agro e Alimentos | 5 |
| Utilities (Energia/Saneamento) | 13 | Industrial | 4 |
| Petróleo e Gás | 9 | Saúde | 4 |
| Mineração e Siderurgia | 7 | Papel e Química | 3 |
| Varejo | 7 | Telecom e Tecnologia | 3 |
| Construção Civil | 6 | Shopping Centers | 3 |
| Transporte e Logística | 6 | Serviços e Lazer | 2 |

**Financeiro tem tratamento separado**: bancos e seguradoras não têm ROIC, Dívida Líquida/Patrimônio, Liquidez Corrente nem EV/EBITDA que signifiquem a mesma coisa. Esses quatro indicadores são **pulados** para o grupo Financeiro, e os pesos do score final mudam.

### 4.2 Ranks dentro do setor (1 = melhor)

Para cada ativo, contando apenas contra membros do mesmo grupo:

```
nROE   = contagem(ROE  > meu ROE)  + 1
nROIC  = contagem(ROIC > meu ROIC) + 1        [pular se Financeiro]
nMrgL  = contagem(MrgLíq > minha)  + 1        [pular se Financeiro]
nLiqC  = contagem(LiqCorr > minha) + 1        [pular se Financeiro]
nCrsc  = contagem(CrescRec > meu)  + 1

nDív   = contagem(DívLíq/Pat < minha) + 1     [ASCENDENTE — menos dívida é melhor]
                                              [pular se Financeiro]
```

Múltiplos com regra especial para valores negativos — P/L, P/VP e EV/EBITDA negativos são **mandados para o fim**, não tratados como "baratos":

```
se valor <= 0:
    n = total_do_grupo + 1
senão:
    n = contagem(0 < valor_do_par < meu_valor) + 1

aplicar a: nP/L, nP/VP, nEV/EB (este último pulado se Financeiro)
```

### 4.3 Blocos e score fundamentalista

```
Qualidade      = média(nROE, nROIC, nMrgL)      # ignora os ausentes
Saúde          = média(nDív, nLiqC)
Valuation      = média(nP/L, nP/VP, nEV/EB)
Consistência   = nCrsc

ScoreF (Financeiro)  = 0,50·Qualidade + 0,30·Valuation + 0,20·Consistência
ScoreF (demais)      = 0,40·Qualidade + 0,25·Saúde + 0,20·Valuation + 0,15·Consistência

PctF = (contagem_no_grupo(ScoreF < meu ScoreF) + 1) / contagem_no_grupo(ScoreF > 0)
```

`PctF` é o percentil dentro do setor. **Menor = melhor.**

### 4.4 Camada técnica

```
Tendência = "alta"     se Preço > MM200
          = "fora"     caso contrário

Timing    = "ENTRADA"  se  IFR >= ifrMin  E  IFR <= ifrMax
                       E   Preço <= BandaInferior × (1 + folga)
          = "aguardar" caso contrário

SINAL     = "► VENDER PUT"  se Tendência = "alta" E Timing = "ENTRADA"
          = "—"             caso contrário
```

`ifrMin = 10`, `ifrMax = 50`, `folga = 0,05` (o preço pode estar até 5% **acima** da banda inferior e ainda conta como "perto"). Todos ajustáveis na tela.

> **Nota sobre a faixa de IFR:** a aba `Instruções` do Excel documenta "IFR 35–45", mas o `Config` sempre rodou com 10–50 — e foi 10–50 que produziu os resultados que o usuário vem usando. Mantenha **10–50** como padrão e corrija o texto das Instruções. Com `Preço > MM200` e o preço colado na banda inferior, o Bollinger já faz o filtro pesado; o IFR aqui serve para excluir sobrecomprado.

### 4.5 Scores de ordenação

```
ScoreT = (Preço − BandaInferior) / BandaInferior    se SINAL aceso
       = 100 + IFR/1000                             se não

ScoreC = PctF                                       se SINAL aceso
       = (vazio, fica fora da lista)                se não
```

`ScoreT`: quanto menor, mais colado na banda inferior. O `100 + IFR/1000` é um truque do Excel para empurrar os sem-sinal para o fim da lista, ordenados por IFR crescente — **preserve esse comportamento**, é o que faz a lista ② se completar em dias sem sinal.

### 4.6 As três listas

| # | Lista | Ordenação | Observação |
|---|---|---|---|
| ① | **Fundamentalista** | 10 menores `PctF` | melhores empresas para carregar |
| ② | **Técnico** | 10 menores `ScoreT` | quem está no ponto de entrada agora |
| ③ | **Combinado** | menores `ScoreC` | **pode ter menos de 10 itens** — só entra quem tem SINAL aceso. É por aqui que se começa |

O Excel resolvia empate somando `ROW()/100000000`. Em código, use ordenação estável com desempate alfabético por ticker.

BDRs ficam fora do universo (`ROXO34`, `XPBR31`, `JBSS32`).

---

## 5. Indicadores a calcular do OHLC

O Profit entregava tudo pronto; agora é você que calcula. Torne cada parâmetro configurável.

| Indicador | Cálculo | Assumido |
|---|---|---|
| **MM200** | Média móvel **simples** do fechamento, 200 períodos | O código RTD era `3`; o período é certo, o tipo (simples/exponencial) não. Assumir simples, deixar configurável |
| **IFR (14)** | RSI de Wilder, 14 períodos, com suavização de Wilder (não média simples) | Equivale ao IFR **Clássico** do Profit, não ao **Simples**. Detalhe e checagem ITUB4 em `PROMPT-DASHBOARD.md` §6.6 |
| **Bollinger** | SMA(20) ± 2 desvios-padrão. Usar a **banda inferior** | O Profit mandava as 3 linhas numa célula só e o Excel isolava a menor por `MIN()`. Período/desvio não são recuperáveis do arquivo — 20/2 é o padrão do Profit. Deixar configurável |
| **HV** | Desvio-padrão dos log-retornos de **21 dias úteis**, anualizado (× √252) | Janela curta de propósito: a put abre com 45–21 dias corridos, então importa a movimentação recente, não a de 1 ano. O OpLab publica "Desvio Padrão (1a)" mas prefira calcular, para ter controle da janela |
| **IV** | Ler do OpLab: `IV (1a)`, `IV Rank`, `IV Percentil` | |
| **IV/HV** | `IV ÷ HV`. Acima de 1 = prêmio gordo, favorável a vender | Manter por continuidade com o Excel, **mas destacar IV Rank e IV Percentil** — dizem se o prêmio está caro em relação ao histórico do próprio ativo, que é a pergunta certa |
| **Máx/mín 52 semanas** | Do OHLC. Exibir como **posição no range**: `(preço − mín) / (máx − mín)` em % | Coluna nova, não existia no Excel. Um número comparável entre ativos: vender put com o ativo a 15% do range é situação bem diferente de vender a 85% |

Quando um indicador não puder ser calculado (histórico curto, ticker sem dado), mostre **"sem dado"** de forma visível. Nunca zero, nunca célula vazia sem explicação — a planilha atual falha exatamente assim com IV/HV e o usuário levou tempo para perceber.

---

## 6. Universo (86 tickers)

```
ABCB4  ABEV3  ALOS3  ALPA4  AUAU3  AXIA3  AZZA3  B3SA3  BBAS3  BBDC3
BBDC4  BBSE3  BEEF3  BPAC11 BRAP4  BRAV3  BRKM5  BRSR6  CEAB3  CMIG4
CMIN3  CPFE3  CPLE3  CSAN3  CSMG3  CSNA3  CURY3  CXSE3  CYRE3  DIRR3
ECOR3  EGIE3  EMBJ3  ENEV3  ENGI11 EQTL3  EZTC3  FLRY3  GGBR4  GMAT3
GOAU4  HYPE3  IGTI11 IRBR3  ISAE4  ITSA4  ITUB4  JHSF3  KLBN11 LREN3
MBRF3  MOTV3  MOVI3  MRVE3  MULT3  NATU3  PETR3  PETR4  POMO4  PRIO3
PSSA3  RADL3  RAIL3  RAIZ4  RDOR3  RECV3  RENT3  SANB11 SAPR11 SBSP3
SLCE3  SMFT3  SUZB3  TAEE11 TIMS3  TOTS3  TUPY3  UGPA3  USIM5  VALE3
VAMO3  VBBR3  VIVA3  VIVT3  WEGE3  YDUQ3
```

Cada um precisa do seu `Grupo` (setor). A lista deve ser editável pela interface, com o mapa ticker→grupo persistido em arquivo, não hardcoded.

✅ **Já validado (13/08/2026)**: os 86 respondem no Yahoo com sufixo `.SA` e os 86 estão na lista do OpLab. Os 7 units (`BPAC11`, `ENGI11`, `IGTI11`, `KLBN11`, `SANB11`, `SAPR11`, `TAEE11`) passam nas duas fontes. Não é preciso fonte alternativa. Ressalvas de histórico curto (`AUAU3`, `NATU3`) e de IV ausente (`RAIZ4`) estão na seção 11.

---

## 7. Motor de escolha de strike

Novidade em relação ao Excel — é o que transforma a ferramenta de "lista de ativos" em ferramenta de operação.

### 7.1 Vencimento — seletor, não regra automática

O vencimento **não é fixo nem inferido**: é escolhido pelo usuário num seletor no topo do Dashboard. Trocar a seleção muda `dias_corridos`, o que muda o prêmio-alvo, o que muda o strike de cada recomendação. A tabela se atualiza na hora.

**Janela de abertura da operação:** as vendas de put são abertas com **45 a 21 dias corridos** até o vencimento (inclusive). Fora dessa faixa o seletor ainda serve para consulta; não é a janela em que a operação é aberta. Ver `PROMPT-DASHBOARD.md` §6.7.

**Padrão ao abrir:** o próximo mensal. Um parâmetro em `Config` define o comportamento do padrão:

```
vencimento_padrao = "proximo_mensal"                    (padrão)
                  | "proximo_mensal_com_min_dias"       (usa min_dias_uteis abaixo)
                  | "proximo_qualquer"
min_dias_uteis = 5      (só vale para a 2ª opção)
```

A segunda opção existe porque o mensal mais próximo pode estar a poucos dias, onde o prêmio absoluto encolhe mas o capital travado não — ver 11.5. Mas isso é preferência, não regra do modelo: **o padrão de fábrica é simplesmente o próximo mensal**, e quem quiser pular escolhe no seletor ou muda o parâmetro.

**Modo do seletor:** um toggle `Só mensais` (padrão) / `Todos os vencimentos`. Semanais existem, mas quase sempre sem liquidez de put — leia 11.6 antes de desenhar isso, tem armadilha.

**Cada opção do seletor mostra**, e isso não é enfeite (é o que evita o usuário escolher uma série morta):

```
18/09/2026 · sex · 36 dias corridos · 25 úteis · MENSAL · 98 puts com bid
```

**Detecção de mensal — não use "3ª sexta-feira".** Use: **a série cujo dia do mês está entre 15 e 21**, uma por mês. A regra da 3ª sexta falha em feriado e isso não é hipotético — está no dado real: o mensal de novembro/2026 é **quinta, 19/11** (a 3ª sexta, 20/11, é Consciência Negra) e o de abril/2028 é **quinta, 20/04** (21/04 é Tiradentes). A janela 15–21 acerta os dois; "3ª sexta" erra os dois e ainda casa com o semanal errado. A aba `Feriados` do Excel continua útil para exibição e conferência, mas **não é mais necessária para achar o mensal** — o `due_date` do OpLab já vem resolvido.

### 7.2 Prêmio-alvo

Escalado pela raiz do tempo, com `dias_corridos` vindo do **vencimento selecionado**:

```
prêmio_alvo_% = meta_30d × √(dias_corridos_até_vencimento / 30)
meta_30d = 1,15%   (ajustável)
```

Aproximação Black-Scholes/ATM: assume IV parecida entre vencimentos e mesmo nível de moneyness. Boa o bastante para triagem, e é o que a planilha já fazia.

### 7.3 Seleção do strike

Na cadeia do OpLab:

1. Filtrar: `Tipo = PUT`, vencimento = **o selecionado**, `Strike < preço à vista` (somente OTM)
2. Descartar `Delta` pior que **−0,45** (piso rígido)
3. `prêmio = último preço negociado` (`put.close` no OpLab). Bid/ask ficam no livro; **nunca** `put.bs.bid` (é a call do mesmo strike)
4. `prêmio_% = último / strike`
5. Escolher o **strike mais distante do preço** (menor strike) cujo `prêmio_% >= prêmio_alvo_%` — a meta do vencimento com a maior segurança possível. Exemplo BRAV3 18/09/2026, meta 1,21%: BRAVU162 16,13 último 0,19 = 1,17% (não entra); BRAVU165 16,38 último 0,22 = 1,34% (primeiro que satisfaz)
6. Se nenhum atingir a meta: mostrar o de maior `prêmio_%` **marcado como "abaixo da meta"**. Nunca esconder o ativo — sumir com ele faz o usuário achar que não há dado
7. Se o ativo **não tem série** naquele vencimento (acontece com semanais — `RAIZ4` não tem nenhuma), mostrar `sem série em dd/MM/yyyy` na linha. Mesmo princípio do passo 6: a linha continua na tela, explicando o vazio
8. Se tem série mas **nenhuma put com `último > 0` e volume no dia**, mostrar `série sem liquidez`. Último sem negócio (volume 0) é cotação velha e não entra. É estado diferente do passo 7 e o usuário precisa distinguir

Cada recomendação exibe: **ativo, vencimento (dd/MM/yyyy), strike, código da opção, prêmio (último), prêmio %, distância do preço %, delta, probabilidade de exercício, IV Rank**.

Sem os pisos dos passos 2 e 5, o critério "maior prêmio que bate a meta" empurra naturalmente para puts quase no dinheiro em ativo volátil — exatamente o oposto do que se quer.

⚠️ **O seletor de vencimento não reordena as três listas.** O scoring das seções 4.1–4.6 usa fundamento e técnico do ativo — nenhum dado de opção entra nele. Trocar o vencimento muda **apenas as colunas de strike/prêmio** de cada linha. Não recalcule o ranking a cada troca: além de desperdício, dá a impressão falsa de que a escolha do vencimento influencia quais empresas são boas.

---

## 8. As 8 telas

Sidebar esquerda única e fixa (um item por enquanto). Abas horizontais no topo da área de conteúdo, na ordem do Excel.

1. **Dashboard** *(inicial)* — as três listas Top 10 como cards de recomendação, com strike sugerido. Mantenha os **três textos narrativos** em primeira pessoa que existem no Excel (células mescladas `J4:P14`, `J16:P27`, `J29:P37`): são a explicação do porquê de cada lista e é o que separa isso de uma tabela qualquer. **Fixos, não gerados por IA.**
   **No topo, o seletor de vencimento** (seção 7.1): um `<select>` com as séries disponíveis, cada uma rotulada com data, dia da semana, dias corridos, dias úteis, marca de MENSAL e nº de puts com bid; ao lado, o toggle `Só mensais` / `Todos os vencimentos`. Trocar a seleção recalcula strike e prêmio de todas as linhas **instantaneamente, sem ir na rede** — o snapshot já traz todas as séries (11.6). O vencimento escolhido tem que aparecer também **dentro de cada card**, em `dd/MM/yyyy`: o card vai ser lido, printado e mandado por WhatsApp fora do contexto do seletor, e strike sem data não significa nada.
2. **Ativos** — tabela dos 86 com fundamentos e técnico, ordenável e filtrável. As colunas de rank (`nROE`…`ScoreC`) ficam atrás de um toggle "mostrar cálculo". As colunas auxiliares do Excel (`AS`→`BD`, RTD cru e parsing de string do Bollinger) **não existem** — eram contorno de limitação do Excel.
3. **Dados** — snapshot da tabela do Fundamentus, com carimbo de coleta.
4. **Setores** — os 14 grupos, contagem e score médio por setor.
5. **Config** — os parâmetros ajustáveis, com a mesma convenção visual do Excel: **amarelo = você pode mudar**. São eles: IFR mínimo/máximo, folga da banda inferior, meta de prêmio 30d, delta mínimo, períodos de MM/Bollinger/IFR/HV, horários de raspagem, **`vencimento_padrao` e `min_dias_uteis`** (seção 7.1). Alterar deve **recalcular na hora**, sem nova raspagem.
6. **Vencimentos** — calendário de séries, com dias corridos e úteis, marcando o MENSAL. É aqui que o usuário entende o que o seletor do Dashboard está oferecendo: mostre, por vencimento, **quantos dos 86 ativos têm série** e **quantos têm ao menos uma put com bid** — é o mapa de liquidez que revela na hora por que um semanal não rende recomendação. Selecionar uma linha aqui deve levar ao Dashboard já com aquele vencimento escolhido.
7. **Feriados** — calendário B3, editável.
8. **Instruções** — o texto do Excel, **com a faixa de IFR corrigida** para 10–50 e a menção ao Profit/RTD substituída pela arquitetura nova.

**Responsividade:** tabela de 20 colunas não cabe em tela de celular. No breakpoint móvel, cada linha vira card. O Dashboard precisa ser plenamente usável no celular — é o caso de uso principal.

**Visual:** linguagem do [beautifului.dev](https://www.beautifului.dev/) reconstruída em CSS próprio — densidade, tipografia, o tratamento de tabelas e cards. Os componentes aproveitáveis de lá são Records Table, Filter Table, Insight Cards, Recommendation Card e Sidebar Nav; o resto do kit é para interface de chat e não serve aqui. Tema **claro**. Verde institucional `#14492E` (o mesmo dos cabeçalhos da planilha), amarelo `#FFF7D6` marcando campo editável. CSS com variáveis, sem Tailwind.

> Nota: a home do beautifului.dev não expõe stack, repositório nem comando de instalação — a promessa de "copy-paste ready" não é verificável de lá. Trate como **referência visual**, não como dependência.

---

## 9. Formatação brasileira — requisito rígido

**Toda** data e hora, em toda a interface, sem exceção:

- Data: `dd/MM/yyyy` — `13/08/2026`
- Hora: `HH:mm:ss` (24h) — `12:05:29`
- Timezone: `America/Sao_Paulo`, sempre explícito. Nunca use hora local do dispositivo — o usuário pode abrir de outro fuso e a hora do pregão precisa ser a de Brasília
- Números: vírgula decimal, ponto de milhar — `1.234,56`. Use `Intl.NumberFormat('pt-BR')` no front e `Babel`/formatação explícita no back
- Percentuais: `12,3%`
- Dias da semana e meses em português

Todo dado exibido carrega carimbo de quando foi coletado, visível — não escondido em tooltip. Marque explicitamente quando o dado estiver velho (fora do horário de raspagem, fim de semana, feriado).

---

## 10. Riscos conhecidos

Estão registrados de propósito. Não são motivo para não fazer, mas o desenho precisa contá-los.

1. **Nenhuma das três fontes tem API pública gratuita.** O acesso é por raspagem de página. O OpLab restringe sua API paga a "uso exclusivamente pessoal" e o portal livre não documenta permissão de scraping. Decisão do usuário, tomada de forma consciente: uso pessoal, uma requisição por ativo por ciclo, `User-Agent` identificável, sem redistribuição.
2. **Yahoo Finance é API não oficial** — pode mudar ou passar a exigir crumb/cookie sem aviso. Some-se a isso a instabilidade de cache medida na seção 11.1: a mesma chamada pode voltar com buracos que somem na tentativa seguinte. **Nunca decida "o ticker não tem dado" com uma única coleta.**
3. ~~OpLab pode mudar o HTML e quebrar o parser~~ — **risco muito reduzido**: os dados vêm de `__NEXT_DATA__` em JSON estruturado (seção 11.2), não de tabela HTML. Resta o risco de mudança de schema entre deploys do Next (`buildId`). Valide os campos obrigatórios na entrada e falhe alto se sumirem, em vez de propagar `None`.
4. **URL pública sem senha** — a curadoria dos 86 ativos e os parâmetros ficam visíveis para quem tiver o link.
5. **IP do servidor pode ser bloqueado.** É IP de datacenter (Oracle Cloud), o perfil que os sites brasileiros bloqueiam primeiro. Os horários fixos e o volume baixo são a mitigação; o plano B está na seção 2.1.
6. **A VPS é compartilhada com sites em produção.** O maior risco operacional do projeto não é técnico e não está nas fontes de dados — é derrubar site alheio ao configurar o nginx. Seção 2.1.

**Mitigação estrutural:** cada fonte atrás de uma interface própria (`PriceSource`, `OptionsSource`, `FundamentalsSource`), com o último snapshot bom sempre em disco. Se uma fonte cair, o dashboard continua servindo o último dado válido, **marcado como desatualizado** — nunca em branco, nunca em erro.

**Snapshot histórico:** gravar um JSON por dia em disco (o resultado da raspagem das 16h). Sem tela na v1 — mas é impossível recuperar depois se não começar agora, e responde "há quantos dias esse sinal está aceso".

---

## 11. Verificações de viabilidade — JÁ EXECUTADAS

As quatro verificações previstas foram feitas em **13/08/2026** contra as fontes ao vivo. **As quatro passaram.** Não é preciso repeti-las; o que segue é o contrato observado de cada fonte, mais as armadilhas que a inspeção revelou. Cada armadilha aqui é um bug silencioso evitado — todas produzem número plausível e errado, não exceção.

### 11.1 Yahoo cobre os 86 tickers — SIM, 86/86

Todos resolvem com sufixo `.SA`, moeda `BRL`, bolsa `São Paulo`, timezone `America/Sao_Paulo`. **Os 7 units passam** (`BPAC11`, `ENGI11`, `IGTI11`, `KLBN11`, `SANB11`, `SAPR11`, `TAEE11`) — não é preciso fonte alternativa. `range=2y&interval=1d` devolve 500 candles para os estabelecidos.

**Armadilhas confirmadas:**

- ⚠️ **`range=max` ignora silenciosamente `interval=1d` e devolve barras MENSAIS.** `PETR4` cai de 500 candles (`2y`) para 320 (`max`, desde 2000). Não é erro, não é aviso — vem menos dado com aparência de mais histórico. **Use sempre `range=2y`** (ou `5y`); nunca `max` esperando diário.
- ⚠️ **`AUAU3` não tem MM200 e não vai ter tão cedo.** `firstTradeDate = 05/01/2026`, 153 candles mesmo em `max`. MM200 só será possível por volta de out/2026. Não é falha de coleta — é fato de mercado. Precisa de caminho explícito **"sem dado"**, e o ativo não pode sumir da tela por isso.
- ⚠️ **`NATU3` tem série curta**: começa em 26/06/2025 (migração `NTCO3`→`NATU3`), embora `firstTradeDate` diga 26/05/2004. 283 fechamentos — MM200 calcula, mas em cima de pouco histórico.
- ⚠️ **Nulls são transitórios.** Uma primeira coleta trouxe linhas com **todos** os campos OHLCV `null` no meio da série (`B3SA3`, `BBAS3`, `TAEE11`, `BBDC4`, `PETR3`); minutos depois, 4 chamadas seguidas do mesmo ticker vieram sem nenhum null, e `query1` e `query2` concordaram. É instabilidade de cache do Yahoo. **Trate null como buraco a interpolar/pular, nunca como zero, e nunca conclua que um ticker "não tem dado" a partir de uma única coleta.**

**Presente de graça:** o bloco `meta` já traz `fiftyTwoWeekHigh`, `fiftyTwoWeekLow`, `regularMarketPrice`, `regularMarketDayHigh`, `regularMarketDayLow`, `regularMarketVolume`, `chartPreviousClose` e `regularMarketTime`. A máxima/mínima de 52 semanas da seção 5 **não precisa ser calculada** — prefira o `meta`, e calcule só como fallback.

### 11.2 OpLab tem JSON por trás — SIM, e melhor do que XHR

**Não é parsing de HTML e não é XHR.** O portal é **Next.js**, e a página traz o payload inteiro embutido:

```html
<script id="__NEXT_DATA__" type="application/json">{ ... }</script>
```

Um `GET` simples com `requests` (sem navegador, sem JS, sem login, sem cookie) já entrega o JSON completo. Extraia com regex/BeautifulSoup e faça `json.loads`. **A camada de opções fica trivial e robusta** — cai o risco nº 3 da seção 10 quase inteiro. Ainda assim, valide o schema na entrada: `buildId` muda a cada deploy do OpLab e a estrutura pode mudar junto.

**Contrato observado — `/mercado-de-opcoes`** (a URL `/mercado` redireciona para cá):

```
props.pageProps.time            ISO UTC do snapshot
props.pageProps.stocks[]        239-242 ativos, cada um com:
    symbol, name, close, variation, volume,
    iv_current, iv_1y_rank, iv_1y_percentile
props.pageProps.marketIndex     IBOV + iv_1y_max/min/rank/percentile, ewma_*
```

**Cobertura: os 86 tickers estão todos presentes (86/86).** Só `RAIZ4` vem sem `iv_current`/`iv_1y_rank` — precisa do caminho "sem dado".

**Contrato observado — `/mercado/acoes/opcoes/{TICKER}`:**

```
props.pageProps.asset       close, open, high, low, bid, ask, variation, volume,
                            iv_current, ewma_current, stdv_1y, beta_ibov, time
props.pageProps.series[]    35 vencimentos, cada um:
    due_date            "2026-08-21"   <-- DATA REAL, ISO
    days_to_maturity    "6"            <-- dias ÚTEIS
    call / put          letra da série ("H" / "T")
    strikes[]           { strike, call{...}, put{...} }
        put.symbol, bid, ask, close, open, high, low, volume,
        financial_volume, variation, maturity_type, contract_size, strike
        put.bs{}  -> delta, gamma, vega, theta, rho, poe, volatility,
                     moneyness, premium, price, liquidity-text,
                     protection-rate, profit-rate, cost-if-exercised
```

**Delta, prob. de exercício (`poe`), volatilidade por opção e moneyness já vêm calculados.** Não é preciso implementar Black-Scholes para o motor de strike da seção 7.

⚠️ **ARMADILHA GRAVE — `bs.bid` e `bs.ask` dentro de uma PUT são as cotações da CALL do mesmo strike.** Verificado em 23 strikes: **100% de coincidência com `call.bid`/`call.ask`**, e 0% com o bid da própria put. Exemplo real (`PETR4`, spot 41,75, venc 14/08):

| Strike | `put.bid` | `put.bs.bid` | `call.bid` |
|---:|---:|---:|---:|
| 40,86 | **0,04** | 0,92 | 0,92 |
| 41,11 | **0,08** | 0,72 | 0,72 |
| 42,86 | **1,10** | 0,03 | 0,03 |

Usar `bs.bid` como prêmio faria **toda** put OTM parecer bater a meta com folga — 0,92 em vez de 0,04 — e o motor escolheria sempre o strike mais distante. Número plausível, resultado catastroficamente errado. **Nunca use `bs.bid`/`bs.ask`.** Bid/ask de primeiro nível (`put.bid`) são o livro. A taxa de entrada da seção 7 é `put.close` / strike, e só com volume no dia — último sem negócio é cotação velha (ex.: BRAVU122 a 0,27).

⚠️ **`bs.premium` e `bs.price` coincidem com `put.close`** (confirmado em 141/141 casos). Podem servir de conferência do último; a fonte canônica do motor é `put.close`. Sem volume no dia, ignore o último mesmo que `bs.premium` esteja preenchido.

Nota: `bs.delta`, `bs.poe` e `bs.moneyness` **são da put** (delta negativo, `poe` crescendo com o strike). A contaminação é só em `bid`/`ask`.

**Cadeias testadas individualmente** (17 tickers, incluindo os 7 units): todas responderam `HTTP 200` com `__NEXT_DATA__` válido. `RAIZ4` é o extremo magro — 11 séries, 33 strikes, só 13 puts com `bid > 0`; provavelmente não sustenta recomendação de strike e precisa cair fora com aviso, não com erro.

⚠️ **Custo de banda maior do que parece.** A página da cadeia é pesada porque o JSON traz **toda** a matriz de strikes e vencimentos, não só o que a tela mostra: `RAIZ4` 213 KB, `TAEE11` 1,2 MB, `BBAS3` 3,5 MB, `VALE3` **4,9 MB**. Uma rodada de 25 recomendados pode passar de **50 MB** por ciclo, 3× ao dia. Não é proibitivo, mas: busque a cadeia **só dos recomendados** (já é a decisão da seção 2), serialize as requisições com pausa entre elas, e **descarte o JSON cru depois de extrair** — não guarde 50 MB/ciclo em disco na VPS.

### 11.3 Fundamentus decodifica limpo — SIM

`HTTP 200`, `Content-Type: text/html; charset=iso-8859-1`, gzip transparente, 761 702 bytes, sem JS e sem cookie. **994 linhas de dados** e **22 `<th>` na ordem exata** da aba `Dados`. Números confirmados em formato brasileiro: `1.083.050.000,00`, `-208,15%`, `0,000`.

- Decodificar como **UTF-8 falha com exceção** (`0xe7` na posição 3056) — é falha barulhenta, não corrupção silenciosa. `iso-8859-1` e `cp1252` decodificam certo.
- ⚠️ **O cabeçalho 21 não bate por texto**: o site escreve `Dív.Líq/ Patrim.` (com espaço no meio e ponto final), o Excel escreve `Dív.Líq/Patrim`. É a mesma coluna. **Case os cabeçalhos por posição, ou normalize espaços e pontuação — nunca por igualdade de string.**

### 11.4 Mapear `Venc.` para data real — problema dissolvido

A coluna `Venc.` em dias úteis é só apresentação. **O JSON traz `due_date` em ISO (`2026-08-21`) diretamente na série.** Não há conversão a fazer: leia `due_date` e formate para `dd/MM/yyyy`. O `days_to_maturity` da mesma série é o número de **dias úteis já descontados os feriados B3** — útil como conferência, não como fonte.

**A regra da seção 7 se confirma nos dados reais**: o vencimento de novembro/2026 é **19/11 (quinta)**, não a 3ª sexta (20/11), porque 20/11 é feriado. O ajuste "3ª sexta → dia útil anterior se feriado" está certo e é necessário.

Dois sinais adicionais para identificar o mensal, ambos observados:

1. **O mensal tem muito mais strikes** — 21/08: **255**; 18/09: 187; 16/10: 186; contra 32-78 nos semanais. É o desempate mais confiável se a regra de data der ambiguidade.
2. As séries semanais existem em quase toda sexta-feira, então **filtrar só por "é sexta" não basta** — sem a regra do 3º, o motor pegaria o semanal. E "3ª sexta" também não basta: use a janela **dia 15–21**, pelo motivo medido em 11.6.

⚠️ **O calendário de feriados do OpLab parece ter um furo.** Os feriados implícitos no `days_to_maturity` batem para 07/09, 12/10, 02/11, 24/12, 25/12, 31/12 e 01/01 — mas **20/11 (Consciência Negra) não aparece na contagem**, apesar de o próprio OpLab ter deslocado o vencimento de 20/11 para 19/11 por causa dele. **A aba `Feriados` do Excel continua sendo a autoridade**; use o `days_to_maturity` do OpLab só como conferência, e não se surpreenda com divergência de 1 dia perto de novembro.

### 11.5 Sanidade do motor de strike com dado real

Rodando a lógica da seção 7 sobre `PETR4` no mensal de 21/08 (spot 41,75, 8 dias corridos → prêmio-alvo = 1,15% × √(8/30) = **0,59%**), o strike escolhido seria **40,86** — 2,13% abaixo do preço, último/`bid` 0,28 (0,69%), delta −0,266, prob. de exercício 27,9%, "Boa liquidez". Resultado coerente: OTM, delta bem acima do piso de −0,45, prêmio batendo a meta. A medição abaixo foi feita quando o motor ainda lia `bid`; a regra vigente é último/strike com volume (seção 7.3). Exemplo canônico atual: BRAV3 18/09/2026, meta 1,21% → BRAVU165 16,38 último 0,22 = 1,34%.

⚠️ **O que o dado levantou, e como ficou resolvido.** O prêmio de 0,28 é **por ação** — R$ 28,00 por contrato de 100. Batendo os três mensais mais próximos, o de 21/08 é pior nos dois eixos ao mesmo tempo:

| Vencimento | Dias corridos | Strike | Prêmio/ação | Por contrato | % do strike | Distância do preço | Caixa travado/contrato |
|---|---|---|---|---|---|---|---|
| 21/08/2026 | 8 | 40,86 | R$ 0,28 | R$ 28,00 | 0,69% | 2,13% | R$ 4.086,00 |
| 18/09/2026 | 36 | 39,86 | R$ 0,54 | R$ 54,00 | 1,35% | 4,53% | R$ 3.986,00 |
| 16/10/2026 | 64 | 37,80 | R$ 0,66 | R$ 66,00 | 1,75% | 9,46% | R$ 3.780,00 |

Para embolsar ~R$ 1.000 no 21/08 seriam 36 contratos e **R$ 147 mil** de caixa travado; no 18/09, 19 contratos e **R$ 76 mil**, com o strike mais longe do preço e delta parecido (−0,240 contra −0,266). A causa é estrutural: `√(dias/30)` derruba a meta para 0,59% quando falta pouco tempo, mas o capital exigido para vender a put não cai junto.

**A decisão não virou regra automática** — virou o **seletor de vencimento da seção 7.1**, com `vencimento_padrao` em `Config` para quem quiser o pulo automático. Melhor assim: qualquer N fixo seria arbitrário, e o usuário vê a diferença entre 0,69% e 1,35% na tela em vez de o sistema decidir escondido.

### 11.6 O seletor de vencimento é viável — mas semanal é quase todo seco

Medido em 10 tickers (PETR4, VALE3, BBAS3, ITUB4, B3SA3, WEGE3, SUZB3, CYRE3, TAEE11, RAIZ4), cobrindo do mais líquido ao mais magro. Três achados que definem o desenho:

**① Mensal é universal e a data é idêntica para todos — 10/10.** `21/08/2026`, `18/09/2026`, `16/10/2026`, `18/12/2026`, `15/01/2027`… até `RAIZ4`, que só tem 11 séries no total, tem exatamente as mesmas datas mensais. Isso é o que torna um seletor **global** possível: uma data escolhida no topo vale para a tabela inteira. Se as datas divergissem por ativo, o seletor teria de ser por linha e a tela viraria outra coisa.

**② "3ª sexta-feira" está errado como regra.** No dado real, `19/11/2026` é uma **quinta** e é o mensal de novembro (20/11 é Consciência Negra), e `20/04/2028` é **quinta** pelo mesmo motivo (21/04 é Tiradentes). Note que **não existe mensal de novembro/2026 numa sexta** — a lista pula de 16/10 direto para 19/11 e depois 18/12. Use a janela **dia do mês entre 15 e 21**: acerta os dois casos, e há exatamente uma série por mês nessa janela. Detectar por contagem de strikes (255 no mensal contra 32–78 no semanal) funciona como conferência, não como regra primária.

**③ Semanal existe, mas quase sempre sem put líquida.** Contando puts com `bid > 0` em PETR4 — o ativo mais líquido da bolsa:

| Série | 14/08 | 21/08 **M** | 28/08 | 04/09 | 11/09 | 18/09 **M** | 25/09 | 02/10 | 09/10 | 16/10 **M** | 23/10 | 30/10 | 06/11 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| puts com bid | 23 | **72** | 43 | 3 | 2 | **98** | 2 | 1 | 5 | **93** | 1 | 0 | 0 |

Fora do mensal e da semana corrente, o livro é vazio. Em ativos menores é pior: `RAIZ4` **não tem nenhuma série semanal** (só mensais), `TAEE11` tem poucas. E semanais só existem até uns 3 meses à frente — de `19/11/2026` em diante só há mensal.

**Consequências para a implementação:**
- Ofereça o semanal (o usuário pediu), mas com o toggle **`Só mensais` como padrão**.
- **Nunca esconda a linha** quando a série não existe ou está seca — passos 7 e 8 da seção 7.3. Com um semanal selecionado, a maioria das linhas vai cair nesses dois estados, e uma tabela quase vazia sem explicação parece defeito.
- Ponha a contagem de puts com bid **no rótulo da opção do seletor**, antes de o usuário escolher.

**④ O seletor não custa uma requisição.** O JSON da cadeia já traz **todas** as séries de uma vez — não há endpoint por vencimento. Ou seja, trocar de 21/08 para 18/09 é recálculo puro sobre o snapshot em cache, sem rede. Isso encaixa perfeitamente com a regra "botão Atualizar nunca raspa" (seção 2).

⚠️ **Mas o snapshot precisa guardar todas as séries** — se você salvar só o vencimento escolhido, trocar o seletor obriga a raspar de novo e a regra acima se perde. Como o JSON cru é enorme (a amostra de 9 ativos baixou **23 MB**; `VALE3` sozinho, 4,9 MB), **não guarde o cru**: no momento da extração, fique só com as PUTs e só com os campos usados — `due_date`, `strike`, `bid`, `ask`, `last` (`put.close`), `symbol`, `bs.delta`, `bs.poe`, `volume` — e corte séries acima de ~120 dias corridos, que não interessam a esta operação. Isso derruba o snapshot de megabytes para dezenas de kilobytes por ativo, e é o que torna o seletor instantâneo.

---

## 12. Ordem sugerida

**Fase 1 — Núcleo de cálculo (sem interface).** Ingestão das três fontes, cálculo dos indicadores, modelo de scoring, geração das três listas. Ponto de parada: um JSON com as listas, conferível contra o Excel.

**Fase 2 — Interface.** As 8 telas, responsivas, com formatação brasileira. Dashboard primeiro.

**Fase 3 — Motor de strike.** Cadeia do OpLab para os recomendados, extração enxuta de **todas** as séries até ~120 dias (11.6), seletor de vencimento no Dashboard, seleção por prêmio-alvo, cards com strike.

**Fase 4 — Operação.** Agendador nos horários fixos, cache, snapshot em disco, degradação por fonte, e deploy na VPS **seguindo a seção 2.1 à risca** — levantamento primeiro, confirmação do usuário, só então escrever.

---

## 13. Critério de aceite

O que define "funcionou":

1. **Paridade com o Excel.** Alimentado com os mesmos fundamentos, `ScoreF`, `PctF` e a lista ① Fundamentalista devem reproduzir a planilha. Divergência aqui significa erro de transcrição do modelo — e o modo de falha mais provável é a inversão de sinal descrita na seção 4.
2. **Teste explícito de que menor é melhor.** Um ativo com ROE alto, dívida baixa e P/L baixo dentro do seu setor precisa aparecer no **topo** da lista ①.
3. **Nenhum dado de mercado vindo do RTD.** O Profit deixa de ser dependência.
4. **IV, IV Rank e IV Percentil preenchidos** para os ativos das listas — a coluna que hoje está quebrada.
5. **Toda data e hora em formato brasileiro**, com timezone de São Paulo, incluindo no celular em outro fuso.
6. **Botão Atualizar nunca dispara raspagem.**
7. **Trocar o vencimento no seletor não vai à rede** e não reordena as três listas — só recalcula strike e prêmio. Teste com a rede desligada.
8. **O mensal de novembro/2026 é reconhecido como `19/11` (quinta)**, não como uma sexta qualquer. É o caso que quebra a regra ingênua da "3ª sexta" e serve de teste de regressão do detector de vencimento.
9. **Vencimento sem série ou sem liquidez aparece como linha explicada**, nunca como linha sumida ou campo em branco.
10. **Uma fonte fora do ar não derruba o dashboard** — mostra o último dado bom, marcado como desatualizado.
11. **O Dashboard é usável no celular.**
12. **Os sites que já rodavam na VPS continuam respondendo exatamente como antes**, verificado depois do deploy. Nenhum arquivo de configuração pré-existente do nginx foi modificado.

---

## 14. Fora de escopo

- Registro de operações (será feito em outro momento)
- Carteira, posição, P&L, controle de risco
- Ordens ou integração com corretora
- Backtest
- Múltiplos usuários ou login

**Este dashboard é ferramenta de seleção, não recomendação de compra ou venda de ativo** — a mesma ressalva que está na aba `Instruções` do Excel deve aparecer no rodapé de todas as telas.

---

## Anexo — pedido original do usuário

Registrado literalmente, como referência de intenção. Tudo que está acima é o refinamento deste pedido depois de três rodadas de perguntas e da investigação das fontes de dados.

> me ajude a escrever o PROMPT de planejamento desse projeto. o arquivo base é o @"carteira_venda_put (4).xlsx". as orientações estao na aba instrucoes. a "tabela fundamentus" citada está disponivel no site https://fundamentus.com.br/resultado.php, e é transportada para a aba "dados" da planilha. a aba "Ativos Líquidos e Informações" contem um recorte das ações que tem opcoes mais liquidas, e que serão de fato utilizadas ou sugeridas em venda de put. a aba "config" sao parametros que podem ser modificados, como meta de premio para 30 dias, e outros campos em "amarelo" que sempre podem ser modificados. o desafio maior talvez seja os dados das acoes em tempo real, e principalmente os dados de IFR (indice de forca relativa - sigla RSI em ingles), maximo e minimo, bandas de bollinger, volatilidade implicita e historica (IV/HV), media movel de 200 periodos (MM200) e outros parametros que podem nao ter sido citados aqui, mas estão na tabela. a tela principal seria a aba "dashboard" dessa planilha, recomendando os ativos ideais para venda de put naquele momento, dados toda a análise feita anteriormente nas abas. entao, gostaria que fosse gerada uma pagina html com todas essas informacoes, com abas dessa planilha, bem bonita com uso de css, e as abas do excel aparecendo dentro de uma pagina com aba lateral unica , por enquanto, com todas as abas do excel aparecendo de forma horizontal, com uma visao similar a do proprio excel. o registro em si das operacoes será feito em outro momento, esse dashboard de agora será somente a recomendação, como está no excel. alguns detalhes de layout podem retirados da pagina https://www.beautifului.dev/, que inclusive tem a codificação para os elementos. a data e hora sempre tem que estar em formato brasileiro
