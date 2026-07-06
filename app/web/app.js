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
};

// ---- View controller: exactly one of #view-login / #view-app is visible ----

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
  views.login.hidden = true;
  views.app.hidden = false;
  document.getElementById("who-name").textContent = user.name;
  document.getElementById("who-role").textContent = user.role.replace(/_/g, " ");
  renderContent(user);
}

// Placeholder for Block 10. Block 11 replaces this with the real screens
// (firm dashboard, client summary, network rollup).
function renderContent() {
  document.getElementById("content").innerHTML = `
    <div class="empty">
      <p>You're signed in. The dashboard and client views arrive next.</p>
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
