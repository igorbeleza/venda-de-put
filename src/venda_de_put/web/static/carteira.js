let csrfToken = "";

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
  if (me.authenticated) showLoggedIn();
  else showLoggedOut();
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
  loadSession();
});
