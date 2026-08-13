const fmtNum = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const fmtDateTime = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

function semDado(v) {
  return v === null || v === undefined || v === "" ? "sem dado" : v;
}

function num(v, style) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "sem dado";
  if (style === "pct") return fmtNum.format(Number(v) * 100) + "%";
  return fmtNum.format(Number(v));
}

function vencLabel(iso) {
  if (!iso) return "sem dado";
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

function stampText(iso) {
  const d = new Date(iso);
  return `Atualizado em ${fmtDateTime.format(d)}`;
}

function cardHtml(kind, a, vencIso) {
  const venc = vencLabel(vencIso);
  if (kind === "fundamentalista") {
    return `<article class="card"><h3>${a.ticker}</h3>
      <dl>
        <dt>grupo</dt><dd>${semDado(a.grupo)}</dd>
        <dt>ScoreF</dt><dd>${num(a.score_f)}</dd>
        <dt>ROE</dt><dd>${num(a.roe, "pct")}</dd>
        <dt>P/L</dt><dd>${num(a.pl)}</dd>
        <dt>P/VP</dt><dd>${num(a.pvp)}</dd>
        <dt>DY</dt><dd>${num(a.dy, "pct")}</dd>
        <dt>vencimento</dt><dd>${venc}</dd>
      </dl></article>`;
  }
  if (kind === "tecnico") {
    return `<article class="card"><h3>${a.ticker}</h3>
      <dl>
        <dt>SINAL</dt><dd>${semDado(a.sinal)}</dd>
        <dt>IFR</dt><dd>${num(a.ifr)}</dd>
        <dt>preço</dt><dd>${num(a.preco)}</dd>
        <dt>Boll Inf</dt><dd>${num(a.boll_inf)}</dd>
        <dt>IV/HV</dt><dd>${num(a.iv_hv)}</dd>
        <dt>vencimento</dt><dd>${venc}</dd>
      </dl></article>`;
  }
  return `<article class="card"><h3>${a.ticker}</h3>
    <dl>
      <dt>grupo</dt><dd>${semDado(a.grupo)}</dd>
      <dt>ScoreF</dt><dd>${num(a.score_f)}</dd>
      <dt>SINAL</dt><dd>${semDado(a.sinal)}</dd>
      <dt>IFR</dt><dd>${num(a.ifr)}</dd>
      <dt>preço</dt><dd>${num(a.preco)}</dd>
      <dt>IV/HV</dt><dd>${num(a.iv_hv)}</dd>
      <dt>vencimento</dt><dd>${venc}</dd>
    </dl></article>`;
}

function renderList(id, kind, rows, vencIso) {
  const el = document.getElementById(id);
  if (!rows || rows.length === 0) {
    const empty = kind === "combinado"
      ? "Nenhum ativo com as duas pontas alinhadas agora."
      : "Nenhum ativo nesta lista.";
    el.innerHTML = `<p class="empty">${empty}</p>`;
    return;
  }
  el.innerHTML = rows.map((a) => cardHtml(kind, a, vencIso)).join("");
}

async function loadVencimentos() {
  const so = document.getElementById("so-mensais").checked ? 1 : 0;
  const res = await fetch(`/api/vencimentos?so_mensais=${so}`);
  const data = await res.json();
  const sel = document.getElementById("vencimento");
  const prev = sel.value;
  sel.innerHTML = (data.vencimentos || []).map((v) => {
    const val = v.efetivo;
    return `<option value="${val}">${v.label}</option>`;
  }).join("");
  if (prev && [...sel.options].some((o) => o.value === prev)) sel.value = prev;
}

async function loadDashboard() {
  const sel = document.getElementById("vencimento");
  const qs = new URLSearchParams();
  if (sel.value) qs.set("vencimento", sel.value);
  qs.set("so_mensais", document.getElementById("so-mensais").checked ? "1" : "0");
  const res = await fetch("/api/dashboard?" + qs.toString());
  if (!res.ok) return;
  const data = await res.json();
  document.getElementById("carimbo").textContent = stampText(data.generated_at);
  document.getElementById("badge-stale").classList.toggle("hidden", !data.stale);
  const p = data.premio_alvo;
  document.getElementById("premio-alvo").textContent =
    p == null ? "" : "Prêmio-alvo " + num(p, "pct");
  const vencIso = data.vencimento && data.vencimento.efetivo;
  if (vencIso && !sel.value) {
    if (![...sel.options].some((o) => o.value === vencIso)) {
      const opt = document.createElement("option");
      opt.value = vencIso;
      opt.textContent = data.vencimento.label;
      sel.appendChild(opt);
    }
    sel.value = vencIso;
  }
  const L = data.listas || {};
  renderList("cards-fundamentalista", "fundamentalista", L.fundamentalista, vencIso);
  renderList("cards-tecnico", "tecnico", L.tecnico, vencIso);
  renderList("cards-combinado", "combinado", L.combinado, vencIso);
}

function activateTab(name) {
  document.querySelectorAll(".tab").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === name);
  });
  document.querySelectorAll(".pane").forEach((p) => {
    const on = p.id === "pane-" + name;
    p.classList.toggle("active", on);
    p.hidden = !on;
  });
  if (name === "ativos") loadAtivos();
  if (name === "dados") loadDados();
  if (name === "setores") loadSetores();
  if (name === "config") loadConfig();
  if (name === "vencimentos") loadVencimentosTable();
  if (name === "feriados") loadFeriados();
  if (name === "instrucoes") loadInstrucoes();
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => activateTab(btn.dataset.tab));
});

const ATIVOS_BASE = [
  ["ticker", "ticker"], ["grupo", "grupo"], ["score_f", "ScoreF"],
  ["roe", "ROE"], ["pl", "P/L"], ["pvp", "P/VP"], ["dy", "DY"],
  ["sinal", "SINAL"], ["ifr", "IFR"], ["score_c", "ScoreC"],
];
const ATIVOS_CALC = [
  ["n_roe", "nROE"], ["n_pl", "nP/L"], ["n_pvp", "nP/VP"],
  ["n_roe", "nROE"], ["score_c", "ScoreC"],
];

let ativosRows = [];
let ativosSort = { key: "ticker", dir: 1 };

function cellVal(row, key) {
  if (row[key] !== undefined && row[key] !== null) return row[key];
  if (row.fund && row.fund[key] !== undefined) return row.fund[key];
  return null;
}

function fillTable(table, headers, rows, { onRow, fmt } = {}) {
  const thead = "<thead><tr>" + headers.map((h) => `<th data-key="${h[0]}">${h[1]}</th>`).join("") + "</tr></thead>";
  const body = rows.map((row) => {
    const tds = headers.map(([key, label]) => {
      const raw = cellVal(row, key);
      const shown = fmt ? fmt(key, raw) : semDado(typeof raw === "number" ? num(raw) : raw);
      return `<td data-label="${label}">${shown}</td>`;
    }).join("");
    return `<tr class="${onRow ? "clickable" : ""}" data-efetivo="${row.efetivo || ""}">${tds}</tr>`;
  }).join("");
  table.innerHTML = thead + "<tbody>" + body + "</tbody>";
  table.querySelectorAll("th").forEach((th) => {
    th.addEventListener("click", () => {
      if (table.id === "tbl-ativos") {
        const k = th.dataset.key;
        if (ativosSort.key === k) ativosSort.dir *= -1;
        else { ativosSort.key = k; ativosSort.dir = 1; }
        renderAtivos();
      }
    });
  });
  if (onRow) {
    table.querySelectorAll("tbody tr").forEach((tr, i) => onRow(tr, rows[i]));
  }
}

async function loadAtivos() {
  const calc = document.getElementById("mostrar-calculo").checked ? 1 : 0;
  const res = await fetch("/api/ativos?calculo=" + calc);
  const data = await res.json();
  ativosRows = data.ativos || [];
  renderAtivos();
}

function renderAtivos() {
  const q = (document.getElementById("filtro-ativos").value || "").toLowerCase();
  const calc = document.getElementById("mostrar-calculo").checked;
  const headers = calc
    ? ATIVOS_BASE.concat([["n_roe", "nROE"], ["n_pl", "nP/L"], ["n_pvp", "nP/VP"]])
    : ATIVOS_BASE;
  let rows = ativosRows.filter((a) => {
    if (!q) return true;
    return String(a.ticker || "").toLowerCase().includes(q)
      || String(a.grupo || "").toLowerCase().includes(q);
  });
  const k = ativosSort.key;
  rows = rows.slice().sort((a, b) => {
    const va = cellVal(a, k);
    const vb = cellVal(b, k);
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    if (typeof va === "number" && typeof vb === "number") return (va - vb) * ativosSort.dir;
    return String(va).localeCompare(String(vb), "pt-BR") * ativosSort.dir;
  });
  fillTable(document.getElementById("tbl-ativos"), headers, rows, {
    fmt(key, raw) {
      if (raw == null || raw === "") return "sem dado";
      if (key === "roe" || key === "dy") return num(raw, "pct");
      if (typeof raw === "number") return num(raw);
      return semDado(raw);
    },
  });
}

document.getElementById("filtro-ativos").addEventListener("input", renderAtivos);
document.getElementById("mostrar-calculo").addEventListener("change", loadAtivos);

const DADOS_COLS = [
  ["ticker", "ticker"], ["cotacao", "cotação"], ["pl", "P/L"], ["pvp", "P/VP"],
  ["dy", "DY"], ["ev_ebitda", "EV/EBITDA"], ["mrg_liq", "mrg líq"],
  ["liq_corr", "liq corr"], ["roic", "ROIC"], ["roe", "ROE"],
  ["div_liq_patrim", "div/pat"], ["cresc_rec_5a", "cresc 5a"],
];

async function loadDados() {
  const res = await fetch("/api/dados");
  const data = await res.json();
  const c = data.carimbo;
  document.getElementById("carimbo-dados").textContent = c
    ? stampText(c.collected_at) + (c.ok ? "" : " · erro")
    : stampText(data.generated_at);
  fillTable(document.getElementById("tbl-dados"), DADOS_COLS, data.rows || [], {
    fmt(_k, raw) {
      if (raw == null || raw === "") return "sem dado";
      return typeof raw === "number" ? num(raw) : raw;
    },
  });
}

async function loadSetores() {
  const res = await fetch("/api/setores");
  const data = await res.json();
  fillTable(
    document.getElementById("tbl-setores"),
    [["grupo", "grupo"], ["contagem", "contagem"], ["score_f_medio", "ScoreF médio"]],
    data.setores || [],
    { fmt(_k, raw) { return raw == null ? "sem dado" : (typeof raw === "number" ? num(raw) : raw); } },
  );
}

const CFG_NUM = [
  "ifr_min", "ifr_max", "folga", "meta_premio_30d", "mm_periodos",
  "ifr_periodos", "boll_periodos", "boll_desvios", "hv_periodos",
];

async function loadConfig() {
  const cfg = await (await fetch("/api/config")).json();
  const form = document.getElementById("form-config");
  for (const [k, v] of Object.entries(cfg)) {
    const el = form.elements[k];
    if (!el) continue;
    el.value = Array.isArray(v) ? v.join(", ") : v;
  }
}

async function saveConfig() {
  const form = document.getElementById("form-config");
  const body = {};
  const src = await (await fetch("/api/config")).json();
  Object.assign(body, src);
  for (const el of form.elements) {
    if (!el.name) continue;
    if (el.name === "scrape_times" || el.name === "fundamentus_days") {
      body[el.name] = el.value.split(/[,\s]+/).filter(Boolean).map((x) =>
        el.name === "fundamentus_days" ? Number(x) : x
      );
    } else if (CFG_NUM.includes(el.name)) {
      body[el.name] = Number(el.value);
    } else {
      body[el.name] = el.value;
    }
  }
  await fetch("/api/config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  await loadDashboard();
}

document.getElementById("form-config").addEventListener("submit", (e) => {
  e.preventDefault();
  saveConfig();
});
document.getElementById("form-config").addEventListener("focusout", (e) => {
  if (e.target && e.target.classList.contains("edit")) saveConfig();
});

async function loadVencimentosTable() {
  const res = await fetch("/api/vencimentos");
  const data = await res.json();
  fillTable(
    document.getElementById("tbl-vencimentos"),
    [
      ["efetivo", "efetivo"], ["nominal", "nominal"], ["tipo", "tipo"],
      ["dias_corridos", "dias corridos"], ["dias_uteis", "úteis"], ["label", "rótulo"],
    ],
    data.vencimentos || [],
    {
      onRow(tr, row) {
        tr.addEventListener("click", () => {
          const sel = document.getElementById("vencimento");
          if (![...sel.options].some((o) => o.value === row.efetivo)) {
            const opt = document.createElement("option");
            opt.value = row.efetivo;
            opt.textContent = row.label;
            sel.appendChild(opt);
          }
          sel.value = row.efetivo;
          activateTab("dashboard");
          loadDashboard();
        });
      },
    },
  );
}

let feriadosCache = [];

async function loadFeriados() {
  const data = await (await fetch("/api/feriados")).json();
  feriadosCache = Array.isArray(data) ? data : (data.feriados || []);
  const tbl = document.getElementById("tbl-feriados");
  const headers = [["date", "data"], ["descricao", "descrição"], ["_rm", ""]];
  const thead = "<thead><tr>" + headers.map((h) => `<th>${h[1]}</th>`).join("") + "</tr></thead>";
  const body = feriadosCache.map((row, i) => `<tr>
    <td data-label="data">${row.date || row.data || ""}</td>
    <td data-label="descrição">${row.descricao || ""}</td>
    <td data-label=""><button type="button" data-i="${i}" class="rm-feriado">remover</button></td>
  </tr>`).join("");
  tbl.innerHTML = thead + "<tbody>" + body + "</tbody>";
  tbl.querySelectorAll(".rm-feriado").forEach((btn) => {
    btn.addEventListener("click", async () => {
      feriadosCache.splice(Number(btn.dataset.i), 1);
      await putFeriados();
    });
  });
}

async function putFeriados() {
  await fetch("/api/feriados", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(feriadosCache),
  });
  await loadFeriados();
  await loadVencimentos();
}

document.getElementById("btn-add-feriado").addEventListener("click", async () => {
  const date = document.getElementById("feriado-data").value;
  const descricao = document.getElementById("feriado-desc").value;
  if (!date) return;
  feriadosCache.push({ date, descricao });
  await putFeriados();
});

async function loadInstrucoes() {
  const data = await (await fetch("/api/instrucoes")).json();
  document.getElementById("texto-instrucoes").textContent = data.texto || "";
}

document.getElementById("vencimento").addEventListener("change", () => {
  loadDashboard();
});

document.getElementById("so-mensais").addEventListener("change", async () => {
  await loadVencimentos();
  await loadDashboard();
});

document.getElementById("btn-atualizar").addEventListener("click", async () => {
  await fetch("/api/refresh", { method: "POST" });
  await loadDashboard();
});

loadVencimentos().then(loadDashboard);
