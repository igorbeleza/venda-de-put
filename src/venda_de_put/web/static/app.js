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

const GRUPO_ABREV = {
  "Utilities (Energia/Saneamento)": "Utilities",
  "Mineração e Siderurgia": "Mineração",
  "Transporte e Logística": "Transporte",
  "Telecom e Tecnologia": "Telecom",
  "Petróleo e Gás": "Petróleo",
  "Agro e Alimentos": "Agro",
  "Construção Civil": "Construção",
  "Papel e Química": "Papel",
  "Shopping Centers": "Shoppings",
  "Serviços e Lazer": "Serviços",
};

function semDado(v) {
  return v === null || v === undefined || v === "" ? "sem dado" : v;
}

function abreviaGrupo(nome) {
  if (nome === null || nome === undefined || nome === "") return "sem dado";
  const full = String(nome);
  if (GRUPO_ABREV[full]) return GRUPO_ABREV[full];
  if (full.length <= 14) return full;
  return full.slice(0, 13) + "…";
}

function grupoHtml(nome) {
  const full = semDado(nome);
  const short = abreviaGrupo(nome);
  return `<dd class="grupo" title="${full}">${short}</dd>`;
}

function num(v, style) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "sem dado";
  if (style === "pct") return fmtNum.format(Number(v) * 100) + "%";
  return fmtNum.format(Number(v));
}

function parseBrDate(s) {
  const t = String(s || "").trim();
  let m = t.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (m) {
    const d = Number(m[1]);
    const mo = Number(m[2]);
    const y = Number(m[3]);
    const dt = new Date(y, mo - 1, d);
    if (dt.getFullYear() !== y || dt.getMonth() !== mo - 1 || dt.getDate() !== d) return null;
    return `${String(y).padStart(4, "0")}-${String(mo).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(t)) return t;
  return null;
}

function maskBrDate(s) {
  const d = String(s || "").replace(/\D/g, "").slice(0, 8);
  if (d.length <= 2) return d;
  if (d.length <= 4) return `${d.slice(0, 2)}/${d.slice(2)}`;
  return `${d.slice(0, 2)}/${d.slice(2, 4)}/${d.slice(4)}`;
}

function vencLabel(iso) {
  if (!iso) return "sem dado";
  const part = String(iso).slice(0, 10);
  const [y, m, d] = part.split("-");
  if (!y || !m || !d || y.length !== 4) return semDado(iso);
  return `${d}/${m}/${y}`;
}

function strikeStatus(st, vencIso) {
  if (st === "ok") return `<span class="chip-ok">bate a meta</span>`;
  if (st === "abaixo_da_meta") return `<span class="chip-warn">abaixo da meta</span>`;
  if (st === "sem_liquidez") return `<span class="chip-warn">série sem liquidez</span>`;
  if (st === "sem_serie") return `<span class="chip-warn">sem série em ${vencLabel(vencIso)}</span>`;
  return "";
}

function opsBlock(a, vencIso, meta30, alvo) {
  const venc = vencLabel(vencIso);
  const premio = a.premio_bid == null
    ? "sem dado"
    : (a.premio_bid_pct == null
      ? num(a.premio_bid)
      : `${num(a.premio_bid)}<small>${num(a.premio_bid_pct, "pct")}</small>`);
  const hasStrike = a.strike != null;
  const strikeLbl = hasStrike
    ? (a.option_symbol
      ? `${num(a.strike)}<small>${a.option_symbol}</small>`
      : num(a.strike))
    : "sem dado";
  return `
    <div class="card-ops">
      <div class="op hl-ops"><span>Preço atual</span><b>${num(a.preco)}</b></div>
      <div class="op hl-ops"><span>Strike</span><b>${strikeLbl}</b></div>
      <div class="op hl-ops"><span>Prêmio (últ.)</span><b>${premio}</b></div>
    </div>
    <div class="card-strip">
      <div class="m30"><span>Meta 30 dias</span><b>${num(meta30, "pct")}</b></div>
      <div class="mv"><span>Meta venc.</span><b>${num(alvo, "pct")}</b></div>
    </div>
    <dl class="card-sub">
      <dt>Vencimento</dt><dd>${venc}</dd>
      <dt>Distância</dt><dd>${num(a.distancia_pct, "pct")}</dd>
      <dt>Delta</dt><dd>${num(a.delta)}</dd>
      <dt>Prob. exercício</dt><dd>${num(a.poe, "pct")}</dd>
    </dl>`;
}

function stampText(iso) {
  const d = new Date(iso);
  return `Atualizado em ${fmtDateTime.format(d)}`;
}

function cardHtml(kind, a, vencIso, meta30, alvo) {
  const ops = opsBlock(a, vencIso, meta30, alvo);
  const status = strikeStatus(a.strike_status, vencIso);
  let metrics;
  if (kind === "fundamentalista") {
    metrics = `<dt>Grupo</dt>${grupoHtml(a.grupo)}
        <dt>ScoreF</dt><dd>${num(a.score_f)}</dd>
        <dt>ROE</dt><dd>${num(a.roe, "pct")}</dd>
        <dt>P/L</dt><dd>${num(a.pl)}</dd>
        <dt>P/VP</dt><dd>${num(a.pvp)}</dd>
        <dt>DY</dt><dd>${num(a.dy, "pct")}</dd>`;
  } else if (kind === "tecnico") {
    metrics = `<dt>SINAL</dt><dd>${semDado(a.sinal)}</dd>
        <dt>IFR</dt><dd>${num(a.ifr)}</dd>
        <dt>Boll Inf</dt><dd>${num(a.boll_inf)}</dd>
        <dt>IV/HV</dt><dd>${num(a.iv_hv)}</dd>
        <dt>IV Rank</dt><dd>${num(a.iv_rank)}</dd>
        <dt>IV Percentil</dt><dd>${num(a.iv_percentile)}</dd>`;
  } else {
    metrics = `<dt>Grupo</dt>${grupoHtml(a.grupo)}
      <dt>ScoreF</dt><dd>${num(a.score_f)}</dd>
      <dt>SINAL</dt><dd>${semDado(a.sinal)}</dd>
      <dt>IFR</dt><dd>${num(a.ifr)}</dd>
      <dt>IV/HV</dt><dd>${num(a.iv_hv)}</dd>
      <dt>IV Rank</dt><dd>${num(a.iv_rank)}</dd>
      <dt>IV Percentil</dt><dd>${num(a.iv_percentile)}</dd>`;
  }
  return `<article class="card">
    <header class="card-head"><h3 class="ticker">${a.ticker}</h3>${status}</header>
    ${ops}
    <dl class="card-metrics">${metrics}</dl>
  </article>`;
}

function renderList(id, kind, rows, vencIso, meta30, alvo) {
  const el = document.getElementById(id);
  if (!rows || rows.length === 0) {
    const empty = kind === "combinado"
      ? "Nenhum ativo com as duas pontas alinhadas agora."
      : "Nenhum ativo nesta lista.";
    el.innerHTML = `<p class="empty">${empty}</p>`;
    return;
  }
  el.innerHTML = rows.map((a) => cardHtml(kind, a, vencIso, meta30, alvo)).join("");
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
  const meta30 = data.meta_premio_30d;
  const dias = data.vencimento && data.vencimento.dias_corridos;
  document.getElementById("premio-alvo").textContent = p == null ? "—" : num(p, "pct");
  document.getElementById("meta-30d").textContent = meta30 == null ? "—" : num(meta30, "pct");
  document.getElementById("dias-corridos").textContent = dias == null ? "—" : String(dias);
  const calcDias = document.getElementById("calc-dias");
  if (calcDias && document.activeElement !== calcDias) calcDias.value = dias == null ? "" : dias;
  paintCalcAlvo();
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
  renderList("cards-fundamentalista", "fundamentalista", L.fundamentalista, vencIso, meta30, p);
  renderList("cards-tecnico", "tecnico", L.tecnico, vencIso, meta30, p);
  renderList("cards-combinado", "combinado", L.combinado, vencIso, meta30, p);
  fitCards();
}

function paintCalcAlvo() {
  const metaEl = document.getElementById("calc-meta-30d");
  const diasEl = document.getElementById("calc-dias");
  const out = document.getElementById("calc-alvo");
  if (!metaEl || !diasEl || !out) return;
  const meta = Number(metaEl.value);
  const dias = Number(diasEl.value);
  if (!Number.isFinite(meta) || !Number.isFinite(dias) || dias <= 0) {
    out.textContent = "—";
    return;
  }
  out.textContent = num(meta * Math.sqrt(dias / 30), "pct");
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
  ["sinal", "SINAL"], ["mm200", "MM200"], ["ifr", "IFR"], ["boll_inf", "Boll Inf"],
  ["score_c", "ScoreC"],
  ["iv", "IV"], ["hv", "HV"], ["iv_hv", "IV/HV"],
];

const DADOS_COLS = [
  ["ticker", "ticker"], ["cotacao", "cotação"], ["pl", "P/L"], ["pvp", "P/VP"],
  ["dy", "DY"], ["ev_ebitda", "EV/EBITDA"], ["mrg_liq", "mrg líq"],
  ["liq_corr", "liq corr"], ["roic", "ROIC"], ["roe", "ROE"],
  ["div_liq_patrim", "div/pat"], ["cresc_rec_5a", "cresc 5a"],
];

const SETORES_COLS = [
  ["grupo", "grupo"], ["contagem", "contagem"], ["score_f_medio", "ScoreF médio"],
];

let ativosRows = [];
let dadosRows = [];
let setoresRows = [];
const tableSort = {
  "tbl-ativos": { key: null, dir: 0 },
  "tbl-dados": { key: null, dir: 0 },
  "tbl-setores": { key: null, dir: 0 },
  "tbl-vencimentos": { key: null, dir: 0 },
  "tbl-feriados": { key: null, dir: 0 },
};

function colTitle(label) {
  if (!label) return label;
  const letters = Array.from(label).filter((ch) => /\p{L}/u.test(ch)).join("");
  if (!letters) return label;
  if (letters === letters.toLocaleUpperCase("pt-BR")) return label;
  const first = label[0];
  if (first === first.toLocaleLowerCase("pt-BR") && label !== label.toLocaleLowerCase("pt-BR")) {
    return label;
  }
  return first.toLocaleUpperCase("pt-BR") + label.slice(1);
}

function isSortableKey(key) {
  return Boolean(key) && key !== "_rm";
}

function nextSort(state, key) {
  if (state.key !== key || state.dir === 0) return { key, dir: 1 };
  if (state.dir === 1) return { key, dir: -1 };
  return { key: null, dir: 0 };
}

function cellVal(row, key) {
  if (row[key] !== undefined && row[key] !== null) return row[key];
  if (row.fund && row.fund[key] !== undefined) return row.fund[key];
  if (row.technicals && row.technicals[key] !== undefined) return row.technicals[key];
  return null;
}

function volPct(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "sem dado";
  const n = Number(v);
  // OpLab manda IV em pontos (22,83); HV e fixtures de teste vêm em fração (0,23).
  if (Math.abs(n) > 1.5) return fmtNum.format(n) + "%";
  return num(n, "pct");
}

function sortRows(rows, sort) {
  if (!sort || !sort.key || !sort.dir) return rows;
  const k = sort.key;
  const dir = sort.dir;
  return rows.slice().sort((a, b) => {
    const va = cellVal(a, k);
    const vb = cellVal(b, k);
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
    return String(va).localeCompare(String(vb), "pt-BR") * dir;
  });
}

function fillTable(table, headers, rows, { onRow, fmt, sort, onHeader } = {}) {
  const thead = "<thead><tr>" + headers.map(([key, label]) => {
    const title = colTitle(label);
    const canSort = Boolean(onHeader) && isSortableKey(key);
    let aria = "none";
    let extra = "";
    let mark = "";
    if (canSort) {
      if (sort && sort.key === key && sort.dir === 1) {
        aria = "ascending"; extra = " sort-asc"; mark = "▲";
      } else if (sort && sort.key === key && sort.dir === -1) {
        aria = "descending"; extra = " sort-desc"; mark = "▼";
      } else {
        mark = "⇅";
      }
    }
    const tip = canSort ? ' title="Clique para ordenar: crescente, decrescente ou ordem original"' : "";
    const cls = canSort ? ` class="sortable${extra}"` : "";
    const ind = mark ? `<span class="sort-ind" aria-hidden="true">${mark}</span>` : "";
    return `<th data-key="${key}"${cls} aria-sort="${aria}"${tip}>${title}${ind}</th>`;
  }).join("") + "</tr></thead>";
  const body = rows.map((row) => {
    const tds = headers.map(([key, label]) => {
      const raw = cellVal(row, key);
      const shown = fmt ? fmt(key, raw) : semDado(typeof raw === "number" ? num(raw) : raw);
      return `<td data-label="${colTitle(label)}">${shown}</td>`;
    }).join("");
    const rowCls = [
      onRow ? "clickable" : "",
      row.tipo === "MENSAL" ? "row-mensal" : "",
    ].filter(Boolean).join(" ");
    return `<tr class="${rowCls}" data-efetivo="${row.efetivo || ""}">${tds}</tr>`;
  }).join("");
  table.innerHTML = thead + "<tbody>" + body + "</tbody>";
  table.querySelectorAll("th").forEach((th) => {
    th.addEventListener("click", () => {
      if (onHeader && isSortableKey(th.dataset.key)) onHeader(th.dataset.key);
    });
  });
  if (onRow) {
    table.querySelectorAll("tbody tr").forEach((tr, i) => onRow(tr, rows[i]));
  }
}

function bindSort(tableId, render) {
  return (key) => {
    tableSort[tableId] = nextSort(tableSort[tableId], key);
    render();
  };
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
  const sort = tableSort["tbl-ativos"];
  fillTable(document.getElementById("tbl-ativos"), headers, sortRows(rows, sort), {
    sort,
    onHeader: bindSort("tbl-ativos", renderAtivos),
    fmt(key, raw) {
      if (raw == null || raw === "") return "sem dado";
      if (key === "roe" || key === "dy") return num(raw, "pct");
      if (key === "iv" || key === "hv") return volPct(raw);
      if (typeof raw === "number") return num(raw);
      return semDado(raw);
    },
  });
}

document.getElementById("filtro-ativos").addEventListener("input", renderAtivos);
document.getElementById("mostrar-calculo").addEventListener("change", loadAtivos);

function fmtDados(key, raw) {
  if (raw == null || raw === "") return "sem dado";
  if (key === "dy" || key === "mrg_liq" || key === "roic" || key === "roe" || key === "cresc_rec_5a") {
    return num(raw, "pct");
  }
  return typeof raw === "number" ? num(raw) : raw;
}

async function loadDados() {
  const res = await fetch("/api/dados");
  const data = await res.json();
  const c = data.carimbo;
  document.getElementById("carimbo-dados").textContent = c
    ? stampText(c.collected_at) + (c.ok ? "" : " · erro")
    : stampText(data.generated_at);
  dadosRows = data.rows || [];
  renderDados();
}

function renderDados() {
  const sort = tableSort["tbl-dados"];
  fillTable(document.getElementById("tbl-dados"), DADOS_COLS, sortRows(dadosRows, sort), {
    sort,
    onHeader: bindSort("tbl-dados", renderDados),
    fmt: fmtDados,
  });
}

async function loadSetores() {
  const res = await fetch("/api/setores");
  const data = await res.json();
  setoresRows = data.setores || [];
  renderSetores();
}

function renderSetores() {
  const sort = tableSort["tbl-setores"];
  fillTable(document.getElementById("tbl-setores"), SETORES_COLS, sortRows(setoresRows, sort), {
    sort,
    onHeader: bindSort("tbl-setores", renderSetores),
    fmt(_k, raw) { return raw == null ? "sem dado" : (typeof raw === "number" ? num(raw) : raw); },
  });
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
  paintCalcAlvo();
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
  if (e.target && e.target.classList.contains("edit") && e.target.id !== "calc-dias") saveConfig();
});
document.getElementById("calc-meta-30d").addEventListener("input", paintCalcAlvo);
document.getElementById("calc-dias").addEventListener("input", paintCalcAlvo);

let vencimentosRows = [];

async function loadVencimentosTable() {
  const res = await fetch("/api/vencimentos");
  const data = await res.json();
  vencimentosRows = data.vencimentos || [];
  renderVencimentos();
}

function renderVencimentos() {
  const sort = tableSort["tbl-vencimentos"];
  fillTable(
    document.getElementById("tbl-vencimentos"),
    [
      ["efetivo", "efetivo"], ["nominal", "nominal"], ["tipo", "tipo"],
      ["dias_corridos", "dias corridos"], ["dias_uteis", "úteis"], ["label", "rótulo"],
    ],
    sortRows(vencimentosRows, sort),
    {
      sort,
      onHeader: bindSort("tbl-vencimentos", renderVencimentos),
      fmt(key, raw) {
        if (key === "efetivo" || key === "nominal") return vencLabel(raw);
        if (key === "tipo" && raw === "MENSAL") {
          return `<span class="chip-mensal">MENSAL</span>`;
        }
        return semDado(typeof raw === "number" ? num(raw) : raw);
      },
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
  renderFeriados();
}

function renderFeriados() {
  const sort = tableSort["tbl-feriados"];
  const rows = feriadosCache.map((row, i) => ({
    date: row.date || row.data || "",
    descricao: row.descricao || "",
    _rm: i,
  }));
  fillTable(
    document.getElementById("tbl-feriados"),
    [["date", "data"], ["descricao", "descrição"], ["_rm", ""]],
    sortRows(rows, sort),
    {
      sort,
      onHeader: bindSort("tbl-feriados", renderFeriados),
      fmt(key, raw) {
        if (key === "_rm") {
          return `<button type="button" data-i="${raw}" class="rm-feriado">remover</button>`;
        }
        if (key === "date") return vencLabel(raw);
        return semDado(raw);
      },
    },
  );
  document.querySelectorAll("#tbl-feriados .rm-feriado").forEach((btn) => {
    btn.addEventListener("click", async (ev) => {
      ev.stopPropagation();
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

const feriadoDataEl = document.getElementById("feriado-data");
const feriadoPickerEl = document.getElementById("feriado-data-picker");
feriadoDataEl.addEventListener("input", () => {
  feriadoDataEl.value = maskBrDate(feriadoDataEl.value);
  feriadoDataEl.removeAttribute("aria-invalid");
  const iso = parseBrDate(feriadoDataEl.value);
  if (iso) feriadoPickerEl.value = iso;
});
feriadoPickerEl.addEventListener("change", () => {
  if (!feriadoPickerEl.value) return;
  feriadoDataEl.value = vencLabel(feriadoPickerEl.value);
  feriadoDataEl.removeAttribute("aria-invalid");
});
document.getElementById("feriado-data-cal").addEventListener("click", () => {
  const iso = parseBrDate(feriadoDataEl.value);
  if (iso) feriadoPickerEl.value = iso;
  try {
    feriadoPickerEl.showPicker();
  } catch (e) {
    feriadoPickerEl.focus();
    feriadoPickerEl.click();
  }
});

document.getElementById("btn-add-feriado").addEventListener("click", async () => {
  const iso = parseBrDate(feriadoDataEl.value);
  const descricao = document.getElementById("feriado-desc").value;
  if (!iso) {
    feriadoDataEl.setAttribute("aria-invalid", "true");
    feriadoDataEl.focus();
    return;
  }
  feriadosCache.push({ date: iso, descricao });
  feriadoDataEl.value = "";
  document.getElementById("feriado-desc").value = "";
  feriadoDataEl.removeAttribute("aria-invalid");
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

const THEME_KEY = "vdp-theme";

function currentTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function applyTheme(theme) {
  const t = theme === "dark" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", t);
  document.documentElement.style.colorScheme = t;
  try { localStorage.setItem(THEME_KEY, t); } catch (e) { /* ignore */ }
  document.querySelectorAll("[data-theme-set]").forEach((btn) => {
    btn.setAttribute("aria-pressed", String(btn.dataset.themeSet === t));
  });
}

document.querySelectorAll("[data-theme-set]").forEach((btn) => {
  btn.addEventListener("click", () => applyTheme(btn.dataset.themeSet));
});
applyTheme(currentTheme());

const ZOOM_KEY = "vdp-zoom";
const ZOOM_STEPS = [0.85, 1, 1.15, 1.3, 1.5];

function currentZoom() {
  const raw = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--ui-zoom"));
  return Number.isFinite(raw) && raw > 0 ? raw : 1;
}

function nearestZoomStep(z) {
  return ZOOM_STEPS.reduce((best, step) => (
    Math.abs(step - z) < Math.abs(best - z) ? step : best
  ), ZOOM_STEPS[1]);
}

function fitCards() {
  const host = document.querySelector(".cards");
  if (!host) return;
  const width = host.clientWidth;
  if (width < 40) {
    document.documentElement.style.setProperty("--card-min", "100%");
    return;
  }
  const rootPx = parseFloat(getComputedStyle(document.documentElement).fontSize) || 15.5;
  const ideal = Math.round(22 * rootPx);
  const cols = Math.max(1, Math.min(5, Math.floor((width + 14) / (ideal + 14))));
  const min = Math.floor((width - 14 * (cols - 1)) / cols);
  document.documentElement.style.setProperty("--card-min", `${min}px`);
}

function applyUiZoom(next) {
  let z = Number(next);
  if (!Number.isFinite(z)) z = 1;
  z = Math.min(1.5, Math.max(0.85, Math.round(z * 100) / 100));
  document.documentElement.style.setProperty("--ui-zoom", String(z));
  document.documentElement.style.zoom = "";
  try { localStorage.setItem(ZOOM_KEY, String(z)); } catch (e) { /* ignore */ }
  const label = document.getElementById("zoom-reset");
  if (label) label.textContent = `${Math.round(z * 100)}%`;
  requestAnimationFrame(fitCards);
}

document.getElementById("zoom-out").addEventListener("click", () => {
  const i = ZOOM_STEPS.indexOf(nearestZoomStep(currentZoom()));
  applyUiZoom(ZOOM_STEPS[Math.max(0, i - 1)]);
});
document.getElementById("zoom-in").addEventListener("click", () => {
  const i = ZOOM_STEPS.indexOf(nearestZoomStep(currentZoom()));
  applyUiZoom(ZOOM_STEPS[Math.min(ZOOM_STEPS.length - 1, i + 1)]);
});
document.getElementById("zoom-reset").addEventListener("click", () => applyUiZoom(1));

window.addEventListener("resize", fitCards);
applyUiZoom(currentZoom());

loadVencimentos().then(loadDashboard);
