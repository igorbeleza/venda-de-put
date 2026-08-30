let csrfToken = "";
const store = {
  portfolio: new Map(),
  operations: new Map(),
  custody: new Map(),
  flows: new Map(),
};

const CLASS_LABEL = {stock: "Ação", margin: "Margem"};
const SIDE_LABEL = {buy: "Compra", sell: "Venda"};
const KIND_LABEL = {put: "Venda de PUT", call: "Venda de CALL"};
const STATUS_LABEL = {
  open: "Aberta",
  expired: "Virou pó (expirou)",
  exercised: "Exercida",
  closed_early: "Encerrada antes",
};
const FLOW_LABEL = {contribution: "Aporte", withdrawal: "Retirada"};

function cookieValue(name) {
  const hit = document.cookie.split("; ").find((row) => row.startsWith(`${name}=`));
  return hit ? decodeURIComponent(hit.split("=").slice(1).join("=")) : "";
}

function errorMessage(payload) {
  const detail = payload && payload.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
  }
  return "Não foi possível concluir";
}

async function api(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = {"Content-Type": "application/json", ...(options.headers || {})};
  if (!["GET", "HEAD"].includes(method)) {
    headers["X-CSRF-Token"] = csrfToken || cookieValue("carteira_csrf");
  }
  const response = await fetch(`api/carteira/${path}`, {...options, headers});
  if (response.status === 401) {
    showLoggedOut();
    throw new Error("não autorizado");
  }
  if (response.status === 404) {
    throw new Error("Este lançamento não existe ou não pertence à sua carteira.");
  }
  if (!response.ok) {
    let payload = {};
    try {
      payload = await response.json();
    } catch (_err) {
      payload = {};
    }
    throw new Error(errorMessage(payload));
  }
  return response.status === 204 ? null : response.json();
}

function setAuthMessage(text) {
  const node = document.getElementById("auth-message");
  if (node) node.textContent = text || "";
}

function setCrudMessage(text) {
  const node = document.getElementById("crud-message");
  if (node) node.textContent = text || "";
}

function setFieldError(id, message) {
  const input = document.getElementById(id);
  const error = document.getElementById(`${id}-error`);
  if (input) input.setCustomValidity(message || "");
  if (error) error.textContent = message || "";
}

function clearFieldError(id) {
  setFieldError(id, "");
}

function moneyToCents(raw, allowNegative = false) {
  const normalized = String(raw).trim().replace(/\./g, "").replace(",", ".");
  const valid = allowNegative
    ? /^-?\d+(\.\d{1,2})?$/.test(normalized)
    : /^\d+(\.\d{1,2})?$/.test(normalized);
  if (!valid) throw new Error("Informe um valor com até 2 casas decimais");
  return Math.round(Number(normalized) * 100);
}

function formatMoney(cents) {
  return cents == null
    ? "sem dado"
    : (cents / 100).toLocaleString("pt-BR", {style: "currency", currency: "BRL"});
}

function textCell(value) {
  const td = document.createElement("td");
  td.textContent = value == null || value === "" ? "sem dado" : String(value);
  return td;
}

function centsToInput(cents) {
  if (cents == null) return "";
  const negative = cents < 0;
  const abs = Math.abs(cents);
  const whole = String(Math.trunc(abs / 100));
  const frac = String(abs % 100).padStart(2, "0");
  return `${negative ? "-" : ""}${whole},${frac}`;
}

function moneyCell(cents, calculated = false) {
  const td = document.createElement("td");
  td.textContent = formatMoney(cents);
  if (calculated) td.className = "calculated";
  return td;
}

function readMoney(id, allowNegative = false) {
  clearFieldError(id);
  try {
    return moneyToCents(document.getElementById(id).value, allowNegative);
  } catch (err) {
    setFieldError(id, err.message);
    const input = document.getElementById(id);
    if (input && input.reportValidity) input.reportValidity();
    throw err;
  }
}

function actionCell(editFn, deleteFn, id) {
  const td = document.createElement("td");
  const editBtn = document.createElement("button");
  editBtn.type = "button";
  editBtn.textContent = "Editar";
  editBtn.addEventListener("click", () => editFn(id));
  const delBtn = document.createElement("button");
  delBtn.type = "button";
  delBtn.textContent = "Apagar";
  delBtn.addEventListener("click", () => deleteFn(id));
  td.append(editBtn, delBtn);
  return td;
}

function fillTable(tbodyId, rows, renderRow) {
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return;
  tbody.replaceChildren();
  rows.forEach((row) => tbody.append(renderRow(row)));
}

function showLoggedOut() {
  const auth = document.getElementById("carteira-auth");
  const app = document.getElementById("carteira-app");
  const logoutBtn = document.getElementById("carteira-logout");
  if (auth) auth.hidden = false;
  if (app) app.hidden = true;
  if (logoutBtn) logoutBtn.hidden = true;
  csrfToken = cookieValue("carteira_csrf");
}

function showLoggedIn() {
  const auth = document.getElementById("carteira-auth");
  const app = document.getElementById("carteira-app");
  const logoutBtn = document.getElementById("carteira-logout");
  if (auth) auth.hidden = true;
  if (app) app.hidden = false;
  if (logoutBtn) logoutBtn.hidden = false;
  setAuthMessage("");
}

async function loadSession() {
  csrfToken = cookieValue("carteira_csrf") || csrfToken;
  const response = await fetch("api/carteira/me");
  if (!response.ok) {
    showLoggedOut();
    return {authenticated: false, username: null};
  }
  const me = await response.json();
  if (me.authenticated) {
    showLoggedIn();
    await loadAll();
  } else {
    showLoggedOut();
  }
  return me;
}

async function submitRegister(event) {
  event.preventDefault();
  setAuthMessage("");
  const username = document.getElementById("register-username").value;
  const password = document.getElementById("register-password").value;
  try {
    const result = await api("auth/register", {
      method: "POST",
      body: JSON.stringify({username, password}),
    });
    csrfToken = result.csrf_token || cookieValue("carteira_csrf");
    await loadSession();
  } catch (err) {
    setAuthMessage(err.message);
  }
}

async function submitLogin(event) {
  event.preventDefault();
  setAuthMessage("");
  const username = document.getElementById("login-username").value;
  const password = document.getElementById("login-user-password").value;
  try {
    const result = await api("auth/login", {
      method: "POST",
      body: JSON.stringify({username, password}),
    });
    csrfToken = result.csrf_token || cookieValue("carteira_csrf");
    await loadSession();
  } catch (err) {
    setAuthMessage(err.message);
  }
}

async function logout() {
  try {
    await api("auth/logout", {method: "POST"});
  } catch (_err) {
    /* volta ao login mesmo se a sessão já tiver expirado */
  }
  csrfToken = "";
  showLoggedOut();
}

function showPane(name) {
  document.querySelectorAll("[id^='carteira-pane-']").forEach((el) => {
    el.hidden = el.id !== `carteira-pane-${name}`;
  });
  document.querySelectorAll(".carteira-nav [data-pane]").forEach((btn) => {
    btn.setAttribute("aria-selected", btn.dataset.pane === name ? "true" : "false");
  });
}

function toggleCloseFields() {
  const status = document.getElementById("operation-status");
  const wrap = document.getElementById("operation-close-fields");
  const cost = document.getElementById("operation-close-cost");
  const repurchase = document.getElementById("operation-repurchase-date");
  if (!status || !wrap || !cost || !repurchase) return;
  const isEarly = status.value === "closed_early";
  wrap.hidden = !isEarly;
  cost.required = isEarly;
  repurchase.required = isEarly;
  if (!isEarly) {
    cost.value = "";
    repurchase.value = "";
    clearFieldError("operation-close-cost");
  }
}

async function loadAll() {
  setCrudMessage("");
  const results = await Promise.allSettled([
    loadAccount(),
    loadPortfolio(),
    loadOperations(),
    loadCustody(),
    loadCashFlows(),
    loadSummary(),
  ]);
  const failed = results.find((item) => item.status === "rejected");
  if (failed) {
    setCrudMessage(failed.reason && failed.reason.message
      ? failed.reason.message
      : "Não foi possível concluir");
  }
}

async function loadAccount() {
  const account = await api("account");
  const input = document.getElementById("cash-cents");
  if (input) input.value = centsToInput(account.cash_cents);
}

async function loadSummary() {
  try {
    const year = new Date().getFullYear();
    await api(`summary?year=${year}`);
  } catch (_err) {
    /* não inventa números quando o resumo falha */
  }
}

async function loadPortfolio() {
  const rows = await api("portfolio");
  store.portfolio = new Map(rows.map((row) => [row.id, row]));
  fillTable("portfolio-body", rows, (row) => {
    const tr = document.createElement("tr");
    tr.append(
      textCell(row.trade_date),
      textCell(row.ticker),
      textCell(CLASS_LABEL[row.asset_class] || row.asset_class),
      textCell(SIDE_LABEL[row.side] || row.side),
      textCell(row.quantity),
      moneyCell(row.price_cents),
      textCell(row.note),
      actionCell(editPortfolioEntry, deletePortfolioEntry, row.id),
    );
    return tr;
  });
}

async function loadOperations() {
  const rows = await api("operations");
  store.operations = new Map(rows.map((row) => [row.id, row]));
  fillTable("operations-body", rows, (row) => {
    const tr = document.createElement("tr");
    tr.append(
      textCell(row.sale_date),
      textCell(row.underlying_ticker),
      textCell(row.option_ticker),
      textCell(KIND_LABEL[row.option_kind] || row.option_kind),
      textCell(row.quantity),
      moneyCell(row.strike_cents),
      textCell(row.expiry_date),
      moneyCell(row.premium_per_share_cents),
      textCell(STATUS_LABEL[row.status] || row.status),
      moneyCell(row.close_cost_per_share_cents),
      textCell(row.repurchase_date),
      moneyCell(row.premium_total_cents, true),
      textCell(row.closing_date),
      moneyCell(row.net_result_cents, true),
      textCell(row.narrative),
      actionCell(editOperation, deleteOperation, row.id),
    );
    const narrativeCell = tr.children[14];
    if (narrativeCell) narrativeCell.classList.add("calculated");
    const closingCell = tr.children[12];
    if (closingCell) closingCell.classList.add("calculated");
    return tr;
  });
}

async function loadCustody() {
  const rows = await api("custody");
  store.custody = new Map(rows.map((row) => [row.id, row]));
  fillTable("custody-body", rows, (row) => {
    const tr = document.createElement("tr");
    tr.append(
      textCell(row.as_of_date),
      moneyCell(row.total_cents),
      actionCell(editCustody, deleteCustody, row.id),
    );
    return tr;
  });
}

async function loadCashFlows() {
  const rows = await api("cash-flows");
  store.flows = new Map(rows.map((row) => [row.id, row]));
  fillTable("flows-body", rows, (row) => {
    const tr = document.createElement("tr");
    tr.append(
      textCell(row.flow_date),
      textCell(FLOW_LABEL[row.kind] || row.kind),
      moneyCell(row.amount_cents),
      textCell(row.note),
      actionCell(editCashFlow, deleteCashFlow, row.id),
    );
    return tr;
  });
}

async function saveAccount(event) {
  event.preventDefault();
  setCrudMessage("");
  clearFieldError("cash-cents");
  try {
    const raw = document.getElementById("cash-cents").value.trim();
    const cash_cents = raw === "" ? null : readMoney("cash-cents", true);
    await api("account", {
      method: "PUT",
      body: JSON.stringify({cash_cents}),
    });
    setCrudMessage("Caixa salva.");
    await Promise.all([loadAccount(), loadSummary()]);
  } catch (err) {
    setCrudMessage(err.message);
  }
}

function resetPortfolioForm() {
  const form = document.getElementById("portfolio-form");
  if (form) form.reset();
  const hidden = document.getElementById("portfolio-id");
  if (hidden) hidden.value = "";
  clearFieldError("portfolio-price");
}

async function savePortfolioEntry(event) {
  event.preventDefault();
  setCrudMessage("");
  try {
    const id = document.getElementById("portfolio-id").value;
    const body = {
      trade_date: document.getElementById("portfolio-date").value,
      ticker: document.getElementById("portfolio-ticker").value.trim().toUpperCase(),
      asset_class: document.getElementById("portfolio-class").value,
      side: document.getElementById("portfolio-side").value,
      quantity: Number.parseInt(document.getElementById("portfolio-quantity").value, 10),
      price_cents: readMoney("portfolio-price"),
      note: document.getElementById("portfolio-note").value.trim(),
    };
    await api(id ? `portfolio/${id}` : "portfolio", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(body),
    });
    resetPortfolioForm();
    setCrudMessage("Movimento salvo.");
    await Promise.all([loadPortfolio(), loadSummary()]);
  } catch (err) {
    setCrudMessage(err.message);
  }
}

function editPortfolioEntry(id) {
  const row = store.portfolio.get(Number(id));
  if (!row) return;
  document.getElementById("portfolio-id").value = String(row.id);
  document.getElementById("portfolio-date").value = row.trade_date;
  document.getElementById("portfolio-ticker").value = row.ticker;
  document.getElementById("portfolio-class").value = row.asset_class;
  document.getElementById("portfolio-side").value = row.side;
  document.getElementById("portfolio-quantity").value = String(row.quantity);
  document.getElementById("portfolio-price").value = centsToInput(row.price_cents);
  document.getElementById("portfolio-note").value = row.note || "";
  clearFieldError("portfolio-price");
  showPane("movimentos");
}

async function deletePortfolioEntry(id) {
  if (!window.confirm("Apagar este lançamento?")) return;
  try {
    await api(`portfolio/${id}`, {method: "DELETE"});
    if (document.getElementById("portfolio-id").value === String(id)) {
      resetPortfolioForm();
    }
    setCrudMessage("Movimento apagado.");
    await Promise.all([loadPortfolio(), loadSummary()]);
  } catch (err) {
    setCrudMessage(err.message);
  }
}

function resetOperationForm() {
  const form = document.getElementById("operation-form");
  if (form) form.reset();
  const hidden = document.getElementById("operation-id");
  if (hidden) hidden.value = "";
  ["operation-strike", "operation-premium", "operation-close-cost"].forEach(clearFieldError);
  toggleCloseFields();
}

async function saveOperation(event) {
  event.preventDefault();
  setCrudMessage("");
  try {
    const id = document.getElementById("operation-id").value;
    const status = document.getElementById("operation-status").value;
    const body = {
      sale_date: document.getElementById("operation-sale-date").value,
      underlying_ticker: document.getElementById("operation-underlying").value.trim().toUpperCase(),
      option_ticker: document.getElementById("operation-option-ticker").value.trim().toUpperCase(),
      option_kind: document.getElementById("operation-kind").value,
      quantity: Number.parseInt(document.getElementById("operation-quantity").value, 10),
      strike_cents: moneyToCents(document.getElementById("operation-strike").value),
      expiry_date: document.getElementById("operation-expiry").value,
      premium_per_share_cents: moneyToCents(document.getElementById("operation-premium").value),
      status,
      close_cost_per_share_cents: status === "closed_early"
        ? moneyToCents(document.getElementById("operation-close-cost").value) : null,
      repurchase_date: status === "closed_early"
        ? document.getElementById("operation-repurchase-date").value : null,
    };
    await api(id ? `operations/${id}` : "operations", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(body),
    });
    resetOperationForm();
    setCrudMessage("Operação salva.");
    await Promise.all([loadOperations(), loadSummary()]);
  } catch (err) {
    if (err.message === "Informe um valor com até 2 casas decimais") {
      try {
        readMoney("operation-strike");
        readMoney("operation-premium");
        if (document.getElementById("operation-status").value === "closed_early") {
          readMoney("operation-close-cost");
        }
      } catch (_inner) {
        /* field-level already set */
      }
    }
    setCrudMessage(err.message);
  }
}

function editOperation(id) {
  const row = store.operations.get(Number(id));
  if (!row) return;
  document.getElementById("operation-id").value = String(row.id);
  document.getElementById("operation-sale-date").value = row.sale_date;
  document.getElementById("operation-underlying").value = row.underlying_ticker;
  document.getElementById("operation-option-ticker").value = row.option_ticker;
  document.getElementById("operation-kind").value = row.option_kind;
  document.getElementById("operation-quantity").value = String(row.quantity);
  document.getElementById("operation-strike").value = centsToInput(row.strike_cents);
  document.getElementById("operation-expiry").value = row.expiry_date;
  document.getElementById("operation-premium").value = centsToInput(row.premium_per_share_cents);
  document.getElementById("operation-status").value = row.status;
  toggleCloseFields();
  if (row.status === "closed_early") {
    document.getElementById("operation-close-cost").value = centsToInput(row.close_cost_per_share_cents);
    document.getElementById("operation-repurchase-date").value = row.repurchase_date || "";
  }
  showPane("operacoes");
}

async function deleteOperation(id) {
  if (!window.confirm("Apagar este lançamento?")) return;
  try {
    await api(`operations/${id}`, {method: "DELETE"});
    if (document.getElementById("operation-id").value === String(id)) {
      resetOperationForm();
    }
    setCrudMessage("Operação apagada.");
    await Promise.all([loadOperations(), loadSummary()]);
  } catch (err) {
    setCrudMessage(err.message);
  }
}

function resetCustodyForm() {
  const form = document.getElementById("custody-form");
  if (form) form.reset();
  const hidden = document.getElementById("custody-id");
  if (hidden) hidden.value = "";
  clearFieldError("custody-total");
}

async function saveCustody(event) {
  event.preventDefault();
  setCrudMessage("");
  try {
    const id = document.getElementById("custody-id").value;
    const body = {
      as_of_date: document.getElementById("custody-date").value,
      total_cents: readMoney("custody-total", true),
    };
    await api(id ? `custody/${id}` : "custody", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(body),
    });
    resetCustodyForm();
    setCrudMessage("Custódia salva.");
    await Promise.all([loadCustody(), loadSummary()]);
  } catch (err) {
    setCrudMessage(err.message);
  }
}

function editCustody(id) {
  const row = store.custody.get(Number(id));
  if (!row) return;
  document.getElementById("custody-id").value = String(row.id);
  document.getElementById("custody-date").value = row.as_of_date;
  document.getElementById("custody-total").value = centsToInput(row.total_cents);
  clearFieldError("custody-total");
  showPane("evolucao");
}

async function deleteCustody(id) {
  if (!window.confirm("Apagar este lançamento?")) return;
  try {
    await api(`custody/${id}`, {method: "DELETE"});
    if (document.getElementById("custody-id").value === String(id)) {
      resetCustodyForm();
    }
    setCrudMessage("Custódia apagada.");
    await Promise.all([loadCustody(), loadSummary()]);
  } catch (err) {
    setCrudMessage(err.message);
  }
}

function resetCashFlowForm() {
  const form = document.getElementById("flow-form");
  if (form) form.reset();
  const hidden = document.getElementById("flow-id");
  if (hidden) hidden.value = "";
  clearFieldError("flow-amount");
}

async function saveCashFlow(event) {
  event.preventDefault();
  setCrudMessage("");
  try {
    const id = document.getElementById("flow-id").value;
    const body = {
      flow_date: document.getElementById("flow-date").value,
      kind: document.getElementById("flow-kind").value,
      amount_cents: readMoney("flow-amount"),
      note: document.getElementById("flow-note").value.trim(),
    };
    await api(id ? `cash-flows/${id}` : "cash-flows", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(body),
    });
    resetCashFlowForm();
    setCrudMessage("Fluxo salvo.");
    await Promise.all([loadCashFlows(), loadSummary()]);
  } catch (err) {
    setCrudMessage(err.message);
  }
}

function editCashFlow(id) {
  const row = store.flows.get(Number(id));
  if (!row) return;
  document.getElementById("flow-id").value = String(row.id);
  document.getElementById("flow-date").value = row.flow_date;
  document.getElementById("flow-kind").value = row.kind;
  document.getElementById("flow-amount").value = centsToInput(row.amount_cents);
  document.getElementById("flow-note").value = row.note || "";
  clearFieldError("flow-amount");
  showPane("evolucao");
}

async function deleteCashFlow(id) {
  if (!window.confirm("Apagar este lançamento?")) return;
  try {
    await api(`cash-flows/${id}`, {method: "DELETE"});
    if (document.getElementById("flow-id").value === String(id)) {
      resetCashFlowForm();
    }
    setCrudMessage("Fluxo apagado.");
    await Promise.all([loadCashFlows(), loadSummary()]);
  } catch (err) {
    setCrudMessage(err.message);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const registerForm = document.getElementById("register-form");
  const loginForm = document.getElementById("login-form");
  const logoutBtn = document.getElementById("carteira-logout");
  if (registerForm) registerForm.addEventListener("submit", submitRegister);
  if (loginForm) loginForm.addEventListener("submit", submitLogin);
  if (logoutBtn) logoutBtn.addEventListener("click", logout);
  document.querySelectorAll(".carteira-nav [data-pane]").forEach((btn) => {
    btn.addEventListener("click", () => showPane(btn.dataset.pane));
  });
  const accountForm = document.getElementById("account-form");
  const portfolioForm = document.getElementById("portfolio-form");
  const operationForm = document.getElementById("operation-form");
  const custodyForm = document.getElementById("custody-form");
  const flowForm = document.getElementById("flow-form");
  if (accountForm) accountForm.addEventListener("submit", saveAccount);
  if (portfolioForm) portfolioForm.addEventListener("submit", savePortfolioEntry);
  if (operationForm) operationForm.addEventListener("submit", saveOperation);
  if (custodyForm) custodyForm.addEventListener("submit", saveCustody);
  if (flowForm) flowForm.addEventListener("submit", saveCashFlow);
  const portfolioCancel = document.getElementById("portfolio-cancel");
  const operationCancel = document.getElementById("operation-cancel");
  const custodyCancel = document.getElementById("custody-cancel");
  const flowCancel = document.getElementById("flow-cancel");
  if (portfolioCancel) portfolioCancel.addEventListener("click", resetPortfolioForm);
  if (operationCancel) operationCancel.addEventListener("click", resetOperationForm);
  if (custodyCancel) custodyCancel.addEventListener("click", resetCustodyForm);
  if (flowCancel) flowCancel.addEventListener("click", resetCashFlowForm);
  const status = document.getElementById("operation-status");
  if (status) status.addEventListener("change", toggleCloseFields);
  [
    "cash-cents", "portfolio-price", "operation-strike", "operation-premium",
    "operation-close-cost", "custody-total", "flow-amount",
  ].forEach((id) => {
    const input = document.getElementById(id);
    if (input) input.addEventListener("input", () => clearFieldError(id));
  });
  toggleCloseFields();
  loadSession();
});
