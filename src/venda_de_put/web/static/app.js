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

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".pane").forEach((p) => {
      p.classList.remove("active");
      p.hidden = true;
    });
    const pane = document.getElementById("pane-" + btn.dataset.tab);
    if (pane) {
      pane.hidden = false;
      pane.classList.add("active");
    }
  });
});

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
