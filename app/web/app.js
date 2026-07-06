"use strict";

// Email Context — thin client for the JSON API.
// The whole UI is a consumer of /api/v1: it holds a JWT, attaches it as a
// Bearer token, and renders what the API returns. No framework, no build step.

const TOKEN_KEY = "ec_token";

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

// Single choke-point for every API call: attaches auth, parses JSON, surfaces
// the server's {detail} as an error, and turns an expired token into re-login.
const api = {
  get token() {
    return localStorage.getItem(TOKEN_KEY);
  },
  set token(value) {
    if (value) localStorage.setItem(TOKEN_KEY, value);
    else localStorage.removeItem(TOKEN_KEY);
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
  },

  async request(method, path, body) {
    const headers = { "Content-Type": "application/json" };
    const hadToken = !!this.token;
    if (hadToken) headers["Authorization"] = `Bearer ${this.token}`;

    let res;
    try {
      res = await fetch(`/api/v1${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new ApiError("Network error — is the server reachable?", 0);
    }

    const text = await res.text();
    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        /* non-JSON response body; leave data null */
      }
    }

    if (!res.ok) {
      const detail = (data && data.detail) || `Request failed (${res.status})`;
      // An invalid/expired token on an authenticated call (we sent one and got
      // 401) means the session is dead — clear it and bounce to login. A 401 on
      // login itself (no token sent) is just bad credentials, handled inline.
      if (res.status === 401 && hadToken) {
        this.clear();
        showLogin();
      }
      throw new ApiError(detail, res.status);
    }
    return data;
  },

  login(email, password) {
    return this.request("POST", "/auth/login", { email, password });
  },
  me() {
    return this.request("GET", "/auth/me");
  },
  networkReport() {
    return this.request("GET", "/reports/network");
  },
  firmReport(firmId) {
    const q = firmId ? `?firm_id=${encodeURIComponent(firmId)}` : "";
    return this.request("GET", `/reports/firm${q}`);
  },
  clientSummary(clientId) {
    return this.request("GET", `/clients/${clientId}/summary`);
  },
  refreshSummary(clientId) {
    return this.request("POST", `/clients/${clientId}/summary/refresh`);
  },
};

// ---- Small helpers ----

// Escape anything server/LLM-originated before it reaches innerHTML.
function esc(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
}

function fmtDate(iso) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function statRow(pairs) {
  return `<div class="stat-row">${pairs
    .map(
      ([lbl, num]) =>
        `<div class="stat"><div class="num">${num}</div><div class="lbl">${esc(lbl)}</div></div>`,
    )
    .join("")}</div>`;
}

function staleCell(n) {
  return n > 0 ? `<span class="badge stale">${n}</span>` : `<span class="muted">0</span>`;
}

let toastTimer = null;
function toast(message, isError) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.classList.toggle("err", !!isError);
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.hidden = true;
  }, 3200);
}

// ---- View controller: exactly one of #view-login / #view-app is visible ----

let currentUser = null;

const views = {
  login: document.getElementById("view-login"),
  app: document.getElementById("view-app"),
};

function showLogin() {
  views.app.hidden = true;
  views.login.hidden = false;
  const pw = document.getElementById("login-password");
  if (pw) pw.value = "";
}

function showApp(user) {
  currentUser = user;
  views.login.hidden = true;
  views.app.hidden = false;
  document.getElementById("who-name").textContent = user.name;
  document.getElementById("who-role").textContent = user.role.replace(/_/g, " ");
  buildNav(user);
  route();
}

function defaultRoute(user) {
  if (user.role === "superuser") return "network";
  if (user.role === "firm_admin") return "firm";
  return "home";
}

function buildNav(user) {
  const items = [];
  if (user.role === "superuser") items.push(["network", "Network"]);
  if (user.role === "firm_admin") items.push(["firm", "My firm"]);
  document.getElementById("nav").innerHTML = items
    .map(([key, label]) => `<a data-nav="${key}" href="#/${key}">${esc(label)}</a>`)
    .join("");
}

function setActiveNav(view) {
  document
    .querySelectorAll("#nav a")
    .forEach((a) => a.classList.toggle("active", a.dataset.nav === view));
}

// ---- Hash router ----
// #/network · #/firm · #/firm/<id> · #/client/<id> · #/home

async function route() {
  if (!currentUser) return;
  let hash = location.hash.slice(1);
  if (!hash || hash === "/") {
    hash = "/" + defaultRoute(currentUser);
    history.replaceState(null, "", "#" + hash);
  }
  const [view, arg] = hash.split("/").filter(Boolean);
  setActiveNav(view);

  const content = document.getElementById("content");
  content.innerHTML = `<div class="empty"><span class="spinner"></span> Loading…</div>`;
  try {
    if (view === "network") await renderNetwork(content);
    else if (view === "firm") await renderFirm(content, arg);
    else if (view === "client") await renderClient(content, arg);
    else renderHome(content);
  } catch (err) {
    if (err.status === 401) return; // already bounced to login
    content.innerHTML = `<div class="empty"><p class="error">${esc(err.message)}</p></div>`;
  }
}

window.addEventListener("hashchange", route);

// ---- Screens ----

async function renderNetwork(content) {
  const d = await api.networkReport();
  content.innerHTML = `
    <div class="page-head"><h1>Network overview</h1><span class="muted">Ascend · all firms</span></div>
    ${statRow([
      ["Firms", d.total_firms],
      ["Clients", d.total_clients],
      ["With summary", d.clients_with_summary],
      ["Stale", d.clients_stale],
      ["Emails", d.total_emails],
    ])}
    <div class="table-wrap"><table>
      <thead><tr>
        <th>Firm</th><th class="num">Clients</th><th class="num">With summary</th>
        <th class="num">Stale</th><th class="num">Emails</th>
      </tr></thead>
      <tbody>${d.firms
        .map(
          (f) => `
        <tr class="clickable" data-firm="${esc(f.firm_id)}">
          <td><strong>${esc(f.firm_name)}</strong></td>
          <td class="num">${f.total_clients}</td>
          <td class="num">${f.clients_with_summary}</td>
          <td class="num">${staleCell(f.clients_stale)}</td>
          <td class="num">${f.total_emails}</td>
        </tr>`,
        )
        .join("")}</tbody>
    </table></div>`;
  content
    .querySelectorAll("tr[data-firm]")
    .forEach((tr) =>
      tr.addEventListener("click", () => {
        location.hash = `/firm/${tr.dataset.firm}`;
      }),
    );
}

async function renderFirm(content, firmId) {
  const d = await api.firmReport(firmId); // firmId undefined for a firm_admin
  const back =
    currentUser.role === "superuser"
      ? `<span class="back" data-back>← Back to network</span>`
      : "";
  content.innerHTML = `
    ${back}
    <div class="page-head"><h1>${esc(d.firm_name)}</h1><span class="muted">Firm dashboard</span></div>
    ${statRow([
      ["Clients", d.total_clients],
      ["With summary", d.clients_with_summary],
      ["Stale", d.clients_stale],
      ["Emails", d.total_emails],
    ])}
    <div class="table-wrap"><table>
      <thead><tr>
        <th>Client</th><th class="num">Emails</th><th class="num">New</th><th>Status</th>
      </tr></thead>
      <tbody>${d.clients
        .map(
          (c) => `
        <tr class="clickable" data-client="${esc(c.client_id)}">
          <td><strong>${esc(c.client_name)}</strong><br><span class="muted">${esc(c.client_email)}</span></td>
          <td class="num">${c.total_emails}</td>
          <td class="num">${c.new_emails_count || ""}</td>
          <td>${rowStatus(c)}</td>
        </tr>`,
        )
        .join("")}</tbody>
    </table></div>`;
  const backEl = content.querySelector("[data-back]");
  if (backEl) backEl.addEventListener("click", () => history.back());
  content
    .querySelectorAll("tr[data-client]")
    .forEach((tr) =>
      tr.addEventListener("click", () => {
        location.hash = `/client/${tr.dataset.client}`;
      }),
    );
}

function rowStatus(c) {
  if (!c.has_summary) return `<span class="badge none">No summary</span>`;
  if (c.is_stale) return `<span class="badge stale">Stale · ${c.new_emails_count} new</span>`;
  return `<span class="badge fresh">Up to date</span>`;
}

async function renderClient(content, clientId) {
  const s = await api.clientSummary(clientId);
  content.innerHTML = summaryHtml(s);
  wireSummary(content, clientId);
}

function summaryHtml(s) {
  const badge = !s.generated
    ? `<span class="badge none">No summary yet</span>`
    : s.is_stale
      ? `<span class="badge stale">Stale · ${s.new_emails_count} new email${
          s.new_emails_count === 1 ? "" : "s"
        }</span>`
      : `<span class="badge fresh">Up to date</span>`;

  const canGenerate = s.total_emails_count > 0;
  const label = s.generated ? "Regenerate" : "Generate summary";
  const meta = s.last_refreshed_at
    ? `<span class="muted">Last refreshed ${esc(fmtDate(s.last_refreshed_at))}${
        s.model_used ? " · " + esc(s.model_used) : ""
      }</span>`
    : "";

  const body = s.payload
    ? payloadHtml(s.payload)
    : `<div class="empty">
         <p>No summary has been generated for this client yet.</p>
         <p class="muted">${s.total_emails_count} email${
           s.total_emails_count === 1 ? "" : "s"
         } on file${canGenerate ? " — generate one above." : "; nothing to summarize yet."}</p>
       </div>`;

  return `
    <span class="back" data-back>← Back</span>
    <div class="page-head"><h1>${esc(s.client_name)}</h1><span class="muted">${esc(s.client_email)}</span></div>
    <div class="summary-actions">
      ${badge}
      <button class="btn primary small" data-refresh ${canGenerate ? "" : "disabled"}>${label}</button>
      ${meta}
    </div>
    ${statRow([
      ["Total emails", s.total_emails_count],
      ["Analyzed", s.emails_analyzed_count],
      ["New since summary", s.new_emails_count],
    ])}
    ${body}`;
}

function payloadHtml(p) {
  const actors =
    (p.actors || [])
      .map(
        (a) =>
          `<div class="actor"><span>${esc(a.name)}</span><span class="role">${esc(a.role)}</span></div>`,
      )
      .join("") || `<p class="muted">None identified.</p>`;

  const concluded =
    (p.concluded_discussions || []).map((d) => `<li>${esc(d)}</li>`).join("") ||
    `<li class="muted">None yet.</li>`;

  const items =
    (p.open_action_items || [])
      .map(
        (i) =>
          `<li>${esc(i.description)}${i.owner ? ` <span class="owner">— ${esc(i.owner)}</span>` : ""}</li>`,
      )
      .join("") || `<li class="muted">None open.</li>`;

  return `
    <div class="summary-grid">
      <div class="panel full"><h3>Overview</h3><p class="overview">${esc(p.overview)}</p></div>
      <div class="panel"><h3>Actors</h3>${actors}</div>
      <div class="panel"><h3>Concluded discussions</h3><ul>${concluded}</ul></div>
      <div class="panel full"><h3>Open action items</h3><ul>${items}</ul></div>
    </div>`;
}

function wireSummary(content, clientId) {
  const backEl = content.querySelector("[data-back]");
  if (backEl) backEl.addEventListener("click", () => history.back());

  const btn = content.querySelector("[data-refresh]");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    const original = btn.textContent;
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span> Working…`;
    try {
      const s = await api.refreshSummary(clientId);
      content.innerHTML = summaryHtml(s); // re-render with fresh data + new button
      wireSummary(content, clientId);
      toast("Summary regenerated");
    } catch (err) {
      if (err.status !== 401) toast(err.message, true);
      btn.disabled = false;
      btn.textContent = original;
    }
  });
}

function renderHome(content) {
  content.innerHTML = `
    <div class="empty">
      <p>Signed in as <strong>${esc(currentUser.name)}</strong>.</p>
      <p class="muted">Client summaries in your firm open by link (e.g. <code>#/client/&lt;id&gt;</code>).
      The firm-wide client roster is available to firm admins.</p>
    </div>`;
}

// ---- Login form ----

const loginForm = document.getElementById("login-form");
const loginError = document.getElementById("login-error");
const loginSubmit = document.getElementById("login-submit");

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.hidden = true;
  loginSubmit.disabled = true;
  loginSubmit.textContent = "Signing in…";
  try {
    const email = document.getElementById("login-email").value.trim();
    const password = document.getElementById("login-password").value;
    const { access_token } = await api.login(email, password);
    api.token = access_token;
    const user = await api.me(); // validate + fetch principal for the shell
    if (!location.hash) history.replaceState(null, "", "#/" + defaultRoute(user));
    showApp(user);
  } catch (err) {
    loginError.textContent = err.message;
    loginError.hidden = false;
  } finally {
    loginSubmit.disabled = false;
    loginSubmit.textContent = "Sign in";
  }
});

document.getElementById("logout").addEventListener("click", () => {
  api.clear();
  currentUser = null;
  history.replaceState(null, "", location.pathname); // drop any #/route
  showLogin();
});

// ---- Bootstrap: rehydrate a stored session on load ----

async function boot() {
  if (!api.token) {
    showLogin();
    return;
  }
  try {
    const user = await api.me(); // confirms the token is still valid
    showApp(user);
  } catch {
    // request() already cleared the token + showed login on a 401; any other
    // failure also lands the user on the login screen.
    showLogin();
  }
}

boot();
