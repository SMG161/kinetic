// Kinetic demo page: a thin layer over the real API. No framework, no build step.
// Tokens live in memory (and sessionStorage, so a reload keeps you signed in).

const DISCIPLINES = ["TRAINER", "PHYSIO", "PHYSICIAN", "MASSAGE", "NUTRITION"];
const state = { tokens: null, me: null, seed: null, orgs: {}, clients: {} };
const $ = (selector) => document.querySelector(selector);

// ---- API helper: every request goes through here and is logged ----

async function api(method, path, body, { auth = true, token } = {}) {
  const headers = { "Content-Type": "application/json" };
  const bearer = token ?? (auth && state.tokens ? state.tokens.access_token : null);
  if (bearer) headers.Authorization = `Bearer ${bearer}`;
  const response = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const raw = await response.text();
  let data = raw;
  try { data = raw ? JSON.parse(raw) : null; } catch { /* not JSON: keep the text */ }
  log(method, path, body, response.status, data);
  return { ok: response.ok, status: response.status, data };
}

function log(method, path, body, status, data) {
  const item = document.createElement("li");
  item.className = status < 300 ? "ok" : status < 500 ? "warn" : "bad";
  const shown = body ? { ...body } : null;
  if (shown?.password) shown.password = "••••••";
  if (shown?.refresh_token) shown.refresh_token = shown.refresh_token.slice(0, 8) + "…";
  item.innerHTML = `<span class="status">${status}</span> ${method} ${path}`;
  if (shown) item.append(pre("request", shown));
  item.append(pre("response", data));
  $("#log").prepend(item);
}

function pre(label, value) {
  const el = document.createElement("pre");
  el.textContent = `${label}: ${typeof value === "string" ? value : JSON.stringify(value, null, 2)}`;
  return el;
}

// ---- Session ----

function setTokens(tokens) {
  state.tokens = tokens;
  if (tokens) sessionStorage.setItem("kinetic-tokens", JSON.stringify(tokens));
  else sessionStorage.removeItem("kinetic-tokens");
  loadMe();
}

async function loadMe() {
  if (!state.tokens) {
    state.me = null;
    $("#who").textContent = "Signed out";
    $("#me").textContent = "Sign in to see your personas.";
    renderOrgs();
    return;
  }
  const { ok, data } = await api("GET", "/me");
  if (!ok) { $("#who").textContent = "Token rejected: refresh or sign in again"; return; }
  state.me = data;
  const expires = new Date(state.tokens.expires_at).toLocaleTimeString();
  $("#who").textContent = `${data.full_name} · access token until ${expires}`;
  if (data.client) state.clients[data.full_name] = data.client.id;
  for (const s of data.staff) state.orgs[s.organization_name] = s.organization_id;
  renderMe(data);
  renderOrgs();
}

function renderMe(me) {
  const staff = me.staff.length
    ? me.staff.map((s) => `<li>${s.role} at ${s.organization_name}${s.disciplines.length ? ` (${s.disciplines.join(", ")})` : ""}</li>`).join("")
    : "<li>none</li>";
  $("#me").innerHTML = `
    <p><strong>${me.full_name}</strong> &lt;${me.email}&gt; · person ${me.id}</p>
    <p>Client: ${me.client ? `yes (client id ${me.client.id})` : "no"}</p>
    <p>Provider: ${me.provider ? me.provider.qualifications.join(", ") : "no"}</p>
    <p>Staff memberships:</p><ul>${staff}</ul>`;
}

function renderOrgs() {
  const select = $("#org");
  const current = select.value;
  select.innerHTML = Object.entries(state.orgs).map(([name, id]) => `<option value="${id}">${name}</option>`).join("");
  if (current) select.value = current;
  $("#client-ids").innerHTML = Object.entries(state.clients).map(([name, id]) => `<option value="${id}">${name}</option>`).join("");
}

// ---- Seed data: one-click sign-in and pending invitations ----

async function loadSeed() {
  const response = await fetch("seed.json");
  if (!response.ok) {
    $("#seed-hint").textContent = "No seed data yet. Run: uv run python scripts/seed.py --reset";
    return;
  }
  state.seed = await response.json();
  Object.assign(state.orgs, state.seed.organizations);
  Object.assign(state.clients, state.seed.clients);
  $("#seed-hint").textContent = "Synthetic people from scripts/seed.py. One click signs in.";
  $("#accounts").innerHTML = "";
  for (const account of state.seed.accounts) {
    const item = document.createElement("li");
    item.innerHTML = `<div>${account.name} <small>${account.email} · ${account.summary}</small></div>`;
    const button = document.createElement("button");
    button.textContent = "Sign in";
    button.onclick = () => signIn(account.email, state.seed.password);
    item.append(button);
    $("#accounts").append(item);
  }
  $("#pending").innerHTML = "";
  for (const invitation of state.seed.pending_invitations) {
    const item = document.createElement("li");
    item.innerHTML = `<div>${invitation.description} <small>${invitation.email}</small></div>`;
    const button = document.createElement("button");
    button.textContent = "Use token";
    button.onclick = () => { $("#accept-form").token.value = invitation.token; };
    item.append(button);
    $("#pending").append(item);
  }
  renderOrgs();
}

async function signIn(email, password) {
  const { ok, data } = await api("POST", "/auth/login", { email, password }, { auth: false });
  if (ok) setTokens(data);
}

// ---- Forms ----

function fields(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function checked(form, name) {
  return [...form.querySelectorAll(`input[name="${name}"]:checked`)].map((box) => box.value);
}

function onSubmit(id, handler) {
  $(id).addEventListener("submit", (event) => { event.preventDefault(); handler(event.target); });
}

const orgId = () => $("#org").value;
const clientId = () => $("#client-id").value.trim();

onSubmit("#login-form", (form) => signIn(form.email.value, form.password.value));

onSubmit("#signup-form", async (form) => {
  const { ok, data } = await api("POST", "/auth/signup", fields(form), { auth: false });
  if (ok) setTokens(data);
});

onSubmit("#org-form", async (form) => {
  const { ok, data } = await api("POST", "/orgs", fields(form));
  if (ok) { state.orgs[data.name] = data.id; renderOrgs(); $("#org").value = data.id; loadMe(); }
});

onSubmit("#staff-form", async (form) => {
  const { email, role } = fields(form);
  const { ok } = await api("POST", `/orgs/${orgId()}/staff`, { email, role, disciplines: checked(form, "disciplines") });
  if (ok) loadMe();
});

onSubmit("#provider-form", async (form) => {
  const { ok } = await api("POST", "/providers", { qualifications: checked(form, "qualifications") });
  if (ok) loadMe();
});

onSubmit("#relationship-form", async (form) => {
  const { ok, data } = await api("POST", `/orgs/${orgId()}/clients`, fields(form));
  if (ok) { $("#client-id").value = data.client_id; renderRelationship(data); }
});

onSubmit("#handoff-form", async (form) => {
  const { ok, data } = await api("POST", `/orgs/${orgId()}/clients/${clientId()}/practice-lead`, fields(form));
  if (ok) renderRelationship(data);
});

$("#view-relationship").onclick = async () => {
  const { ok, data } = await api("GET", `/orgs/${orgId()}/clients/${clientId()}`);
  if (ok) renderRelationship(data);
};

function renderRelationship(relationship) {
  const rows = relationship.lead_history.map((lead) => `
    <tr><td>${lead.person_id}</td><td>${lead.reason}</td>
    <td>${new Date(lead.valid_from).toLocaleString()}</td>
    <td>${lead.valid_to ? new Date(lead.valid_to).toLocaleString() : "current"}</td></tr>`).join("");
  $("#relationship").innerHTML = `
    <table><thead><tr><th>Practice lead (person id)</th><th>Reason</th><th>From</th><th>To</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

onSubmit("#invite-form", async (form) => {
  const { kind, email, role, practice_lead_email, reason } = fields(form);
  const body = { kind, email };
  if (kind === "STAFF") body.role = role;
  if (kind === "PRACTITIONER") body.disciplines = checked(form, "disciplines");
  if (kind === "CLIENT") Object.assign(body, { practice_lead_email, reason });
  const { ok, data } = await api("POST", `/orgs/${orgId()}/invitations`, body);
  if (ok) $("#accept-form").token.value = data.token;
});

onSubmit("#accept-form", async (form) => {
  const { token, mode, full_name, password } = fields(form);
  const asNew = mode === "new";
  const body = asNew ? { token, full_name, password } : { token };
  const { ok, data } = await api("POST", "/invitations/accept", body, { auth: !asNew });
  if (ok && data.tokens) setTokens(data.tokens);
  else if (ok) loadMe();
});

function showKindFields() {
  const kind = $("#invite-kind").value;
  document.querySelectorAll("#invite-form [data-kind]").forEach((el) => { el.hidden = el.dataset.kind !== kind; });
}
$("#invite-kind").onchange = showKindFields;

// ---- Session buttons and quick auth checks ----

$("#refresh").onclick = async () => {
  if (!state.tokens) return;
  const { ok, data } = await api("POST", "/auth/refresh", { refresh_token: state.tokens.refresh_token }, { auth: false });
  if (ok) setTokens(data);
};

$("#logout").onclick = async () => {
  if (state.tokens) await api("POST", "/auth/logout");
  setTokens(null);
};

const checks = {
  me: () => api("GET", "/me"),
  "no-token": () => api("GET", "/me", null, { auth: false }),
  forged: () => api("GET", "/me", null, { token: "not.a.real.jwt" }),
  health: () => api("GET", "/health", null, { auth: false }),
};
document.querySelectorAll("[data-check]").forEach((button) => { button.onclick = checks[button.dataset.check]; });

$("#clear-log").onclick = () => { $("#log").innerHTML = ""; };

// ---- Start up ----

document.querySelectorAll(".disciplines").forEach((box) => {
  for (const discipline of DISCIPLINES) {
    const label = document.createElement("label");
    label.innerHTML = `<input type="checkbox" name="${box.dataset.name}" value="${discipline}"> ${discipline}`;
    box.append(label);
  }
});
showKindFields();
const saved = sessionStorage.getItem("kinetic-tokens");
loadSeed().then(() => setTokens(saved ? JSON.parse(saved) : null));
