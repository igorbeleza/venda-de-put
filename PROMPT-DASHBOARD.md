# Prompt de planejamento — Dashboard de Venda de PUT

Documento **novo**. Não é reescrita do `PROMPT-PLANEJAMENTO.md`. O Excel é a autoridade do modelo; o arquivo antigo só entra como fonte de armadilhas de coleta já medidas.

**O que fazer com este texto:** ler inteiro, devolver um plano de implementação (arquivos, fases, testes, deploy) e só então escrever código. Não implementar neste passo.

---

## Decisões de produto (v1)

Travadas antes de implementar. Reverter qualquer uma muda o resto do documento — não “ajuste pontual”.

| # | Decisão | Escolha |
|---|---|---|
| 1 | Escopo da v1 | Recomendação de **ativo**, como no Excel. Três listas + prêmio-alvo da Config. **Sem** motor de strike/delta/put |
| 2 | Acesso | **Só o dono, com senha** (HTTP Basic ou equivalente). Sem contas, sem OAuth |
| 3 | Frescor | Raspagem em **horários fixos** (11h, 13h, 16h BRT, dia útil). Fundamentus dias **1 e 15, 07h**. Botão Atualizar **nunca raspa** — só relê o snapshot |
| 4 | Visual | Sidebar única + **abas horizontais com os 8 nomes do Excel**. Telas de produto (cards no Dashboard, tabelas densas no resto). Não clonar célula a célula |

Registro de operações, carteira, P&L, ordens, backtest, multi-usuário: **fora**.

---

## 1. O problema

A planilha `carteira_venda_put (4).xlsx` recomenda ativos da B3 para venda de PUT cruzando fundamento (Fundamentus) com timing técnico (Profit via RTD). Três fricções matam o fluxo:

1. Só roda no Excel desktop / Windows, com o Profit aberto. `=RTD("rtdtrading.rtdserver",,"PETR4_B_0","ULT")` não existe na web.
2. Os códigos RTD de IV (387) e HV (45) voltam `Atributo Inválido`. IV, HV, IV/HV e “Prêmio?” estão vazios.
3. Fundamentus é colado à mão na aba Dados.

O produto substitui a planilha por uma página HTML no VPS do usuário, acessível do celular, com o **mesmo modelo de scoring** e as **mesmas 8 abas**. A fonte da verdade passa a ser o código. O `.xlsx` fica no repositório como referência histórica e como gabarito de paridade.

Isto **não** é recomendação de investimento. A ressalva da aba Instruções vai no rodapé de todas as telas.

---

## 2. Persona de quem implementa

Especialista em mercado de opções da B3 que também escreve código. Prêmio, moneyness, IV Rank, capital travado e risco de exercício são vocabulário operacional. Se o modelo transcrito tiver erro de **mérito financeiro** — não só de código — aponte antes de implementar.

O Excel manda. Onde o prompt antigo (`PROMPT-PLANEJAMENTO.md`) divergir da fórmula da planilha, **ganha a planilha**. Divergência já conhecida: o prompt antigo diz para pular `nMrgL` no Financeiro; a célula `AA2` **não pula**. Ver §6.

---

## 3. Arquitetura da v1

```
[cron 11h/13h/16h BRT]          [cron 1 e 15, 07h]
        │                                │
        ▼                                ▼
 Yahoo chart (86×)                  Fundamentus HTML
 preço, OHLC 2y                     ~994 papéis × 22 cols
        │                                │
        ▼                                │
 OpLab /mercado-de-opcoes                │
 IV, IV Rank, IV Percentil               │
 (1 página, os 86 estão lá)              │
        │                                │
        └────────────┬───────────────────┘
                     ▼
              snapshot JSON em disco
              + 1 arquivo/dia às 16h (histórico, sem tela)
                     │
                     ▼
         motor de scoring (pandas / puro)
         3 listas + PctF / ScoreT / ScoreC
                     │
                     ▼
         FastAPI em 127.0.0.1:PORTA
         HTML/CSS/JS puro, sem build, sem Tailwind
                     │
                     ▼
         nginx (arquivo NOVO + reload)
         HTTPS + senha
```

**Fronteira entre fontes — um número, uma origem:**

| Dado | Fonte |
|---|---|
| Preço à vista, MM200, IFR, Bollinger, HV, máx/mín 52s | Yahoo (calculado do OHLC, exceto 52s preferir `meta`) |
| IV, IV Rank, IV Percentil | OpLab lista de mercado |
| Balanço (P/L, ROE, DY, …) | Fundamentus |
| Calendário de vencimento e dias úteis | Aba Feriados + regra da aba Vencimentos |
| Prêmio-alvo | `meta_30d × √(dias_corridos / 30)` — Config, **sem** cadeia de opções |

Isolar cada fonte atrás de uma interface (`PriceSource`, `IvSource`, `FundamentalsSource`). O último snapshot bom fica em disco. Fonte fora do ar → dashboard serve o último dado válido **marcado como desatualizado**. Nunca tela em branco, nunca `0` no lugar de “sem dado”.

**Fora da v1 de propósito:** buscar `/mercado/acoes/opcoes/{TICKER}` para sugerir strike. Isso é fase 2 (§13). Na v1 o OpLab entra só pela página de mercado (um GET por ciclo).

---

## 4. Restrições da VPS — inegociável

Servidor: Ubuntu, `ubuntu@[VPS]`. **Já hospeda outros sites em nginx.** Derrubar um deles é falha grave.

**Proibido:**

- Editar, mover ou apagar qualquer arquivo que já exista em `/etc/nginx/`
- `systemctl restart nginx` (use **reload**)
- Mexer em certificado, certbot, ou `server_name` alheio
- `apt upgrade`, trocar Python do sistema, `pip install` fora de venv
- Firewall, iptables, Security List / NSG da Oracle
- Ocupar 80/443 direto, ou qualquer porta já em uso

**Caminho:**

1. **Antes de escrever qualquer coisa no servidor**, levantar e mostrar ao usuário: `nginx -T`, `ss -tlnp`, `systemctl list-units --type=service --state=running`, `df -h`. Esperar confirmação.
2. App em `/opt/venda-de-put/`, usuário de serviço próprio, virtualenv próprio.
3. `systemd` `venda-de-put.service` em `127.0.0.1:PORTA` — nunca `0.0.0.0`. Porta alta e livre, confirmada no passo 1.
4. **Um único arquivo novo** `/etc/nginx/sites-available/venda-de-put` + symlink em `sites-enabled/`. `server_name` informado pelo usuário — **não inventar domínio**.
5. `sudo nginx -t` antes de ativar. Erro → remover o symlink e parar.
6. `sudo systemctl reload nginx`. Depois, verificar que os sites antigos ainda respondem.
7. Backup antes: `sudo tar czf ~/nginx-backup-$(date +%F).tar.gz /etc/nginx`.
8. Auth no próprio nginx (`auth_basic`) ou na app — mas a URL **não fica aberta**.

**Ainda falta o usuário informar:** o hostname (subdomínio apontando para `[VPS]`). Sem isso, não se escreve o server block.

Plano B se o IP de datacenter for bloqueado: o scrape roda na máquina do usuário e publica o JSON na VPS. Desenhar as interfaces para isso ser possível; não implementar o plano B na v1.

---

## 5. Fontes — contrato e armadilhas (já medidas em 13/08/2026)

Não é obrigatório reabrir as quatro verificações. Se reabrir, o resultado tem que bater com isto ou o desvio precisa ser explicado.

### 5.1 Yahoo — preço e técnico

```
GET https://query1.finance.yahoo.com/v8/finance/chart/{TICKER}.SA?range=2y&interval=1d
```

JSON, sem cookie, sem crumb. 86/86 tickers do universo resolvem (incluindo units `BPAC11`, `ENGI11`, `IGTI11`, `KLBN11`, `SANB11`, `SAPR11`, `TAEE11`).

- **Nunca** `range=max` com `interval=1d`: o Yahoo ignora o intervalo e devolve barras mensais (PETR4 cai de ~500 candles para ~320).
- Nulls no meio da série são **cache transitório**. Não conclua “ticker sem dado” com uma coleta. Null ≠ zero.
- `AUAU3`: IPO em 05/01/2026, sem MM200 até ~out/2026. Caminho explícito “sem dado”.
- `NATU3`: série efetiva começa 26/06/2025 (migração NTCO3). MM200 calcula em cima de pouco histórico — mostre isso.
- Prefira `meta.fiftyTwoWeekHigh/Low` e `regularMarketPrice`; calcule do OHLC só como fallback.
- API não oficial: isole atrás de `PriceSource`.

### 5.2 OpLab — só a lista de mercado, na v1

```
GET https://opcoes.oplab.com.br/mercado-de-opcoes
```

Portal Next.js. **Não parsear tabela HTML.** O payload está em `<script id="__NEXT_DATA__">`. `requests` + `json.loads`.

Contrato observado: `props.pageProps.stocks[]` (~239–242 papéis) com `symbol, name, close, variation, volume, iv_current, iv_1y_rank, iv_1y_percentile`. Os 86 estão lá. `RAIZ4` vem sem IV — “sem dado”.

Timestamps do portal já vêm em formato brasileiro. `time` do JSON está em ISO UTC — converter para `America/Sao_Paulo` na exibição.

**Não chamar** `/mercado/acoes/opcoes/{TICKER}` na v1. Essa página pesa até ~5 MB por ativo (VALE3 4,9 MB) e só serve ao motor de strike.

Se alguém no futuro for nessa rota: `put.bs.bid` / `put.bs.ask` são as cotações da **CALL** do mesmo strike. Prêmio da put é `put.bid` de primeiro nível. Sempre. Essa armadilha fica registrada aqui para a fase 2 não a repetir.

### 5.3 Fundamentus

```
GET https://fundamentus.com.br/resultado.php
```

HTML, sem JS, sem cookie. **Encoding ISO-8859-1** (UTF-8 explode em `0xe7`). Números pt-BR (`1.234,56`, percentuais com `%`). 22 colunas na ordem da aba Dados:

```
Papel, Cotação, P/L, P/VP, PSR, Div.Yield, P/Ativo, P/Cap.Giro, P/EBIT,
P/Ativ Circ.Liq, EV/EBIT, EV/EBITDA, Mrg Bruta, Mrg Ebit, Mrg. Líq.,
Liq. Corr., ROIC, ROE, Liq.2meses, Patrim. Líq, Dív.Líq/Patrim, Cresc. Rec.5a
```

O site escreve `Dív.Líq/ Patrim.` (espaço e ponto). O Excel escreve `Dív.Líq/Patrim`. **Case por posição**, não por string.

Roda 2× por mês: fundamento muda com balanço, não com o pregão.

### 5.4 Cadência e o botão Atualizar

Variáveis de ambiente, não hardcoded:

- `SCRAPE_TIMES=11:00,13:00,16:00` (America/Sao_Paulo, dias úteis B3)
- `FUNDAMENTUS_DAYS=1,15`
- `FUNDAMENTUS_TIME=07:00`

O botão Atualizar **relê o snapshot**. Motivo: mesmo com senha, um clique que dispara 86 Yahoo + 1 OpLab + (às vezes) Fundamentus, apertado no nervosismo, ainda queima cota e pode banir o IP. A senha não é desculpa para scrape on-demand na v1.

Toda tela mostra o carimbo da coleta (`dd/MM/yyyy HH:mm:ss`, Brasília), visível, não em tooltip. Fora do horário / fim de semana / feriado: marcar **dado velho**.

---

## 6. Modelo de scoring — transcrição da planilha

Autoridade: fórmulas da aba `Ativos Líquidos e Informações`, linha 2, conferidas no arquivo. **Menor rank / menor score = melhor.** Uma ordenação decrescente coloca as piores empresas no topo com cara de certo. Escreva teste para isso.

### 6.1 Universo (86)

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

Mapa ticker → grupo persistido em arquivo (JSON/YAML), **editável na aba Ativos ou Config**, não hardcoded. BDRs (`ROXO34`, `XPBR31`, `JBSS32`) fora.

| Grupo | Qtd | Tickers |
|---|---|---|
| Financeiro | 14 | ITUB4 BBAS3 BBDC4 B3SA3 BPAC11 ITSA4 BBSE3 IRBR3 BBDC3 ABCB4 CXSE3 SANB11 PSSA3 BRSR6 |
| Utilities (Energia/Saneamento) | 13 | EGIE3 AXIA3 SBSP3 ENEV3 CMIG4 EQTL3 TAEE11 CSMG3 ISAE4 CPLE3 SAPR11 ENGI11 CPFE3 |
| Petróleo e Gás | 9 | PETR4 PRIO3 BRAV3 CSAN3 PETR3 VBBR3 UGPA3 RECV3 RAIZ4 |
| Mineração e Siderurgia | 7 | VALE3 CSNA3 USIM5 BRAP4 GGBR4 CMIN3 GOAU4 |
| Varejo | 7 | AZZA3 LREN3 CEAB3 VIVA3 GMAT3 AUAU3 ALPA4 |
| Construção Civil | 6 | CYRE3 MRVE3 JHSF3 DIRR3 CURY3 EZTC3 |
| Transporte e Logística | 6 | RENT3 RAIL3 VAMO3 MOTV3 MOVI3 ECOR3 |
| Agro e Alimentos | 5 | NATU3 MBRF3 ABEV3 BEEF3 SLCE3 |
| Industrial | 4 | EMBJ3 WEGE3 POMO4 TUPY3 |
| Saúde | 4 | RADL3 RDOR3 HYPE3 FLRY3 |
| Papel e Química | 3 | SUZB3 BRKM5 KLBN11 |
| Telecom e Tecnologia | 3 | TOTS3 VIVT3 TIMS3 |
| Shopping Centers | 3 | ALOS3 MULT3 IGTI11 |
| Serviços e Lazer | 2 | YDUQ3 SMFT3 |

### 6.2 Ranks dentro do grupo (1 = melhor)

```
nROE   = contagem(ROE  > meu) + 1
nROIC  = contagem(ROIC > meu) + 1     se Grupo ≠ Financeiro; senão vazio
nMrgL  = contagem(MrgL > minha) + 1   ← TAMBÉM no Financeiro (AA2 não tem IF de setor)
nLiqC  = contagem(LiqC > minha) + 1   se Grupo ≠ Financeiro; senão vazio
nCrsc  = contagem(Cresc > meu) + 1
nDív   = contagem(Dív  < minha) + 1   ASCENDENTE; pular Financeiro
```

Múltiplos negativos (P/L, P/VP, EV/EBITDA) **não** são “baratos”:

```
se valor <= 0:  n = tamanho_do_grupo + 1
senão:          n = contagem(0 < par < meu) + 1
nEV/EB pulado se Financeiro
```

### 6.3 Blocos e ScoreF

```
Qualid   = MÉDIA(nROE, nROIC, nMrgL)     # ignora vazio → Financeiro = média(nROE, nMrgL)
Saúde    = MÉDIA(nDív, nLiqC)            # vazio no Financeiro
Valuat   = MÉDIA(nP/L, nP/VP, nEV/EB)
Consist  = nCrsc

ScoreF (Financeiro) = 0,50·Qualid + 0,30·Valuat + 0,20·Consist
ScoreF (demais)     = 0,40·Qualid + 0,25·Saúde  + 0,20·Valuat + 0,15·Consist

PctF = (contagem_no_grupo(ScoreF < meu) + 1) / contagem_no_grupo(ScoreF > 0)
```

`PctF` menor = melhor.

### 6.4 Camada técnica

Padrões do Config (células amarelas), ajustáveis na tela:

| Parâmetro | Célula | Padrão |
|---|---|---|
| IFR mínimo | B2 | 10 |
| IFR máximo | B3 | 50 |
| Folga banda inferior | B4 | 0,05 |
| Meta de prêmio / 30 dias | B18 | 1,15% |
| Dias até o vencimento (corridos) | B19 | 50 (na web: derivado do vencimento selecionado) |

A aba Instruções ainda diz “IFR 35–45”. O Config sempre rodou 10–50 e é isso que o usuário usa. **Padrão 10–50**; corrigir o texto das Instruções.

```
Tendência = "alta"    se Preço > MM200
          = "fora"    senão

Timing    = "ENTRADA" se IFR ∈ [ifrMin, ifrMax]
                       e Preço ≤ BollInf × (1 + folga)
          = "aguardar" senão

SINAL     = "► VENDER PUT" se Tendência = alta e Timing = ENTRADA
          = "—"            senão
```

### 6.5 Scores de ordenação e as três listas

```
ScoreT = (Preço − BollInf) / BollInf    se SINAL aceso
       = 100 + IFR/1000                 se não     # empurra sem-sinal para o fim, ordenados por IFR

ScoreC = PctF                           se SINAL aceso
       = vazio                          se não     # fora da lista ③
```

| Lista | Ordenação | Observação |
|---|---|---|
| ① Fundamentalista | 10 menores PctF | melhores empresas para carregar |
| ② Técnico | 10 menores ScoreT | timing agora; completa com sem-sinal via truque do 100+IFR/1000 |
| ③ Combinado | menores ScoreC | **pode ter < 10**. É a lista que o usuário usa de verdade |

Desempate: ticker alfabético (o Excel usa `ROW()/1e8`).

### 6.6 Indicadores a calcular do OHLC

O Profit entregava pronto. Agora o código calcula. Cada período/desvio é configurável.

| Indicador | Cálculo | Nota |
|---|---|---|
| MM200 | SMA 200 do fechamento | RTD usava código `3`; tipo SMA assumido, configurável |
| IFR (14) | RSI de Wilder, 14, suavização de Wilder | não média simples |
| Bollinger | SMA(20) ± 2σ; usar a **banda inferior** | 20/2 é o padrão Profit, não está no arquivo |
| HV | σ dos log-retornos de **21 dias úteis**, × √252 | janela curta de propósito (put 30–50d) |
| IV / IV Rank / IV Percentil | OpLab `iv_current`, `iv_1y_rank`, `iv_1y_percentile` | |
| IV/HV | IV ÷ HV | > 1 = prêmio gordo; **destaque IV Rank/Percentil** — comparam o ativo consigo mesmo |
| Máx/mín 52s | do `meta` Yahoo | coluna nova: posição no range `(p − mín)/(máx − mín)` em % |

Indicador impossível (histórico curto, IV ausente): texto **“sem dado”**, visível. Nunca 0, nunca célula muda.

### 6.7 Prêmio-alvo (existe no Excel; não escolhe strike)

```
prêmio_alvo_% = meta_30d × √(dias_corridos_até_vencimento / 30)
```

Na planilha, `dias_corridos` é digitado em Config!B19. Na web: um seletor no topo do Dashboard alimentado pela aba Vencimentos (datas reais, já ajustadas por feriado). Trocar o vencimento **recalcula só o prêmio-alvo** e o rótulo de dias. **Não reordena as três listas** — scoring não usa dado de opção.

Detecção de mensal: **dia do mês ∈ [15, 21]**, uma série por mês. Não use “3ª sexta” — falha em feriado (nov/2026 é quinta 19/11; abr/2028 é quinta 20/04). A aba Feriados é a autoridade; se a sexta nominal é feriado, o vencimento efetivo recua para o dia útil anterior (fórmula da coluna D de Vencimentos).

O seletor mostra, no mínimo:

```
18/09/2026 · sex · 36 dias corridos · 25 úteis · MENSAL
```

Padrão ao abrir: próximo mensal. Toggle “só mensais” ligado por padrão.

---

## 7. As 8 telas

Chrome: sidebar esquerda **fixa, um item só** (“Venda de PUT”). Abas horizontais no topo do conteúdo, nesta ordem:

1. **Dashboard** (inicial) — três listas como cards. Manter os **três textos narrativos literais** (não gerar com IA):

> ① *“Essa lista não é sobre achar a ação que vai 'bombar'. É sobre achar a empresa que eu aceitaria carregar mesmo se ela caísse amanhã. A gente compara cada ação com as outras do mesmo setor — banco com banco, varejo com varejo, elétrica com elétrica — olhando rentabilidade, dívida e se o preço não está esticado. O resultado é: essas são as empresas com o fundamento mais sólido pra virem à put. Se eu for exercido em alguma delas, eu compro empresa boa, não sobra.”*

> ② *“Aqui a pergunta muda: não é 'essa empresa é boa', é 'agora é a hora'. A gente só entra vendendo put quando duas coisas acontecem ao mesmo tempo: a ação está numa tendência de alta de verdade (não é ilusão de curto prazo), e ela deu uma respirada — um recuo saudável que deixa o prêmio mais gordo. Se só tiver o recuo sem a tendência de alta, cara, isso não é oportunidade, é faca caindo. Por isso a coluna de sinal só acende quando os dois REALMENTE se encontram.”*

> ③ *“Essa é a lista que eu realmente usa. É a interseção das outras duas: empresa que eu aceitaria carregar de olhos fechados e que está no momento certo de entrada agora. Fundamento decide o quê; técnico decide quando. Reparem que às vezes essa lista vem com menos de 10 nomes — e tá certo assim. Proteção que gera lucro não é sobre ter sempre uma operação pra fazer, é sobre só entrar quando as duas pontas se alinham.”*

   Colunas por lista, iguais ao Excel:
   - ① ticker, grupo, ScoreF, ROE, P/L, P/VP, DY
   - ② ticker, SINAL, IFR, preço, Boll Inf, IV/HV
   - ③ ticker, grupo, ScoreF, SINAL, IFR, preço, IV/HV

   No topo: seletor de vencimento + prêmio-alvo resultante + carimbo da coleta. No card, o vencimento em `dd/MM/yyyy` (o card vai para print/WhatsApp).

2. **Ativos** — os 86, ordenável e filtrável. Ranks (`nROE`…`ScoreC`) atrás de toggle “mostrar cálculo”. Colunas AS–BD do Excel (RTD cru e parse de string do Bollinger) **não existem**.

3. **Dados** — snapshot Fundamentus + carimbo.

4. **Setores** — 14 grupos, contagem, ScoreF médio.

5. **Config** — amarelo = editável, igual à convenção da planilha. IFR min/max, folga, meta 30d, períodos MM/Bollinger/IFR/HV, horários de raspagem. Códigos RTD do Profit **saem** (não há Profit). Alterar **recalcula na hora** sobre o snapshot, sem scrape. Persistir em arquivo no servidor.

6. **Vencimentos** — calendário (nominal, tipo, feriado?, efetivo, dia, corridos, úteis, status). Clicar uma linha leva ao Dashboard com aquele vencimento.

7. **Feriados** — lista editável. Recalcula Vencimentos.

8. **Instruções** — texto do Excel, com IFR corrigido para 10–50 e Profit/RTD trocados por esta arquitetura.

**Responsivo:** Dashboard usável no celular (caso de uso principal). Tabela larga vira card no breakpoint móvel.

**Visual:** referência [beautifului.dev](https://www.beautifului.dev/) reconstruída em CSS próprio. Componentes que servem: Records Table, Filter Table, Insight Cards, Recommendation Card, Sidebar. O resto do kit é chat/AI — ignore. Tema claro. Verde `#14492E` (cabeçalhos da planilha), amarelo `#FFF7D6` para campo editável. CSS com variáveis. Sem Tailwind, sem dependência do kit (a home não expõe instalação verificável).

---

## 8. Formatação — requisito rígido

Tudo, em toda tela, inclusive no celular em outro fuso:

- Data `dd/MM/yyyy` — `13/08/2026`
- Hora `HH:mm:ss` 24h — `12:05:29`
- Timezone **sempre** `America/Sao_Paulo`. Nunca hora local do aparelho
- Número `1.234,56` (`Intl.NumberFormat('pt-BR')` / formatação explícita no back)
- Percentual `12,3%`
- Dia da semana e mês em português

---

## 9. Stack

- Back: **Python + FastAPI**, pandas para o motor, agendador (APScheduler ou cron do sistema).
- Front: **HTML + CSS + JS puro**, servido pelo FastAPI. Sem React/Vue, sem bundler, sem Tailwind.
- Persistência: arquivos no disco (snapshot JSON, config, universo, feriados, histórico diário). Sem banco na v1.
- Testes: pytest no motor de scoring com fixture extraída do Excel (mesmos fundamentos → mesmos ScoreF/PctF/lista ①).

---

## 10. Riscos (desenhar em volta, não usar como desculpa)

1. Nenhuma das três fontes tem API pública gratuita. Uso pessoal, volume baixo, `User-Agent` identificável, sem redistribuição. Decisão consciente do dono.
2. Yahoo é API não oficial e o cache fura. Nunca sentenciar “sem dado” numa coleta só.
3. OpLab pode mudar o `buildId` / schema do `__NEXT_DATA__`. Validar campos obrigatórios e falhar alto.
4. IP de datacenter Oracle é o primeiro que site brasileiro bloqueia. Cadência baixa é a mitigação; plano B em §4.
5. VPS compartilhada: o maior risco operacional é o nginx. §4.
6. Senha única (Basic) não é Fort Knox — é o suficiente para Config e universo não ficarem abertos na internet.

---

## 11. Fases de construção

**Fase 1 — Núcleo, sem UI.** Ingestão das três fontes, indicadores, scoring, três listas, prêmio-alvo. Entrega: JSON conferível contra o Excel.

**Fase 2 — Interface.** 8 telas, pt-BR, responsivo. Dashboard primeiro.

**Fase 3 — Operação.** Agendador, cache, snapshot diário, degradação por fonte, senha. Deploy na VPS **na ordem do §4** — levantamento, confirmação, só então escrever.

Não misturar fase 3 com fase 1. Não “já que estamos no servidor, um server block rápido”.

---

## 12. Aceite da v1

1. Mesmos fundamentos → `ScoreF`, `PctF` e lista ① iguais aos do Excel. Divergência = erro de transcrição (o modo mais provável é inverter “menor é melhor”).
2. Teste explícito: ROE alto + dívida baixa + P/L baixo no setor → **topo** da ①.
3. Nenhum RTD / Profit.
4. IV, IV Rank e IV Percentil preenchidos onde o OpLab tem dado; “sem dado” onde não tem (`RAIZ4`).
5. Toda data/hora em pt-BR, fuso de Brasília, inclusive no celular noutro fuso.
6. Botão Atualizar não dispara scrape (teste com rede do scraper desligada / mock).
7. Trocar vencimento não vai à rede e não reordena as listas — só muda dias e prêmio-alvo.
8. Mensal de novembro/2026 = **19/11 (quinta)**, não uma sexta. Regressão do detector.
9. Fonte morta → último snapshot + carimbo de velho. Dashboard não cai.
10. Dashboard usável no celular.
11. Sites que já estavam na VPS respondem igual depois do deploy. Nenhum arquivo nginx pré-existente modificado.
12. Sem senha, a página não entrega o dashboard.

---

## 13. Fase 2 (não construir agora — só não esquecer)

Motor de strike: cadeia OpLab só dos recomendados, `put.bid` (nunca `bs.bid`), piso de delta −0,45, strike OTM mais longe que ainda bate o prêmio-alvo, linha explicada se não houver série ou liquidez. Seletor instantâneo exige guardar **todas** as séries úteis no snapshot (não o JSON cru de 5 MB). Detalhe e armadilhas estão no `PROMPT-PLANEJAMENTO.md` antigo, seções 7 e 11.2/11.5/11.6 — consultar na hora, não agora.

---

## 14. Fora de escopo

- Registro de operações
- Carteira, posição, P&L, risco
- Integração com corretora
- Backtest
- Login multi-usuário / papéis
- Scrape on-demand pelo botão público
- Clonar a grade do Excel célula a célula

---

## 15. Material de referência no disco

| Arquivo | Uso |
|---|---|
| `carteira_venda_put (4).xlsx` | Autoridade do modelo e gabarito de paridade |
| `PROMPT-PLANEJAMENTO.md` | Só armadilhas de coleta (Yahoo/OpLab/Fundamentus) e o motor de strike futuro. **Não** copiar decisões de produto de lá (URL pública, strike na v1, nMrgL pulado) |

---

## Aberto até o deploy (não bloqueia o plano)

- Hostname / subdomínio para o `server_name`
- Senha que o usuário vai usar no `auth_basic`
- Confirmação do levantamento (`nginx -T`, portas) antes de qualquer escrita na VPS
