// Kinetic demo page: a thin layer over the real API. No framework, no build step.
// Tokens live in memory (and sessionStorage, so a reload keeps you signed in).

const DISCIPLINES = ["TRAINER", "PHYSIO", "PHYSICIAN", "MASSAGE", "NUTRITION"];
const CATEGORIES = ["MEDICAL_HISTORY", "ASSESSMENT", "ASSESSMENT_SUMMARY", "CLINICAL_NOTE", "SESSION_NOTE",
  "TRAINING_PLAN", "MASSAGE_PLAN", "NUTRITION_PLAN"];
const ACTIONS = ["VIEW_TEAM", "ADD_MEMBER", "CHANGE_ENGAGEMENT", "END_MEMBERSHIP", "SCHEDULE_COVERAGE", "END_COVERAGE",
  "DISCHARGE_ORGANIZATION", "ACCEPT_CARE_INVITATION", "VIEW_RECORD", "WRITE_NOTE", "RUN_SESSION", "MESSAGE_CLIENT", "BILL"];
const state = { tokens: null, me: null, seed: null, orgs: {}, clients: {}, names: {}, selected: null };
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
  Object.assign(state.names, state.seed.names);
  $("#client-id").value = state.seed.clients["Maya Patel"];
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
  $("#pending-care").innerHTML = "";
  for (const invitation of state.seed.pending_care_invitations) {
    const item = document.createElement("li");
    item.innerHTML = `<div>${invitation.description} <small>${invitation.email}</small></div>`;
    const button = document.createElement("button");
    button.textContent = "Use token";
    button.onclick = () => { $("#care-accept-form").token.value = invitation.token; };
    item.append(button);
    $("#pending-care").append(item);
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
  const { full_name, email, password } = fields(form);
  const body = { full_name, email, password, qualifications: checked(form, "qualifications") };
  const { ok, data } = await api("POST", "/auth/signup", body, { auth: false });
  if (ok) setTokens(data);
});

onSubmit("#org-form", async (form) => {
  const { ok, data } = await api("POST", "/orgs", fields(form));
  if (ok) { state.orgs[data.name] = data.id; renderOrgs(); $("#org").value = data.id; loadMe(); }
});

onSubmit("#provider-form", async (form) => {
  const { ok } = await api("POST", "/providers", { qualifications: checked(form, "qualifications") });
  if (ok) loadMe();
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

// ---- Care team ----

const team = () => `/clients/${clientId()}/care-team`;
const nameOf = (id) => state.names[id] ?? (id ? id.slice(0, 8) : "");
const orgName = (id) => Object.keys(state.orgs).find((name) => state.orgs[name] === id) ?? (id ? id.slice(0, 8) : "solo");
const when = (value) => (value ? new Date(value).toLocaleString() : "current");
const requireSelected = () => state.selected ?? alert("Pick a member in the table first");

function memberRows(members) {
  return members.map((m) => `
    <tr><td>${nameOf(m.provider_id)}</td><td>${m.discipline}</td><td>${orgName(m.org_context_id)}</td>
    <td>${m.engagement}</td><td>${m.reason}</td><td>${when(m.valid_from)}</td><td>${when(m.valid_to)}</td>
    <td><button type="button" data-select="${m.id}" data-label="${nameOf(m.provider_id)}">Select</button></td></tr>`).join("");
}

function coverageRows(coverages) {
  return coverages.map((c) => `
    <tr><td>${nameOf(c.covering_provider_id)}</td><td>${c.reason}</td><td>${when(c.starts_at)}</td><td>${when(c.ends_at)}</td>
    <td>${c.cancelled_at ? "cancelled" : ""}</td>
    <td><button type="button" data-end-coverage="${c.id}" data-member="${c.covered_membership_id}">End</button></td></tr>`).join("");
}

function renderMembers(title, members, coverages) {
  $("#team").innerHTML = `<h3>${title}</h3>
    <table><thead><tr><th>Provider</th><th>Discipline</th><th>Org</th><th>Engagement</th><th>Reason</th><th>From</th><th>To</th><th></th></tr></thead>
    <tbody>${memberRows(members)}</tbody></table>
    <h3>Coverage</h3>
    <table><thead><tr><th>Cover</th><th>Reason</th><th>Starts</th><th>Ends</th><th></th><th></th></tr></thead>
    <tbody>${coverageRows(coverages)}</tbody></table>`;
  document.querySelectorAll("[data-select]").forEach((button) => {
    button.onclick = () => {
      state.selected = button.dataset.select;
      $("#selected").textContent = `(${button.dataset.label})`;
    };
  });
  document.querySelectorAll("[data-end-coverage]").forEach((button) => {
    button.onclick = async () => {
      const path = `${team()}/members/${button.dataset.member}/coverages/${button.dataset.endCoverage}/end`;
      const { ok } = await api("POST", path, { reason: "Handed back from the demo page" });
      if (ok) viewTeam();
    };
  });
}

async function viewTeam() {
  const asOf = $("#as-of").value;
  const query = asOf ? `?as_of=${encodeURIComponent(new Date(asOf).toISOString())}` : "";
  const { ok, data } = await api("GET", team() + query);
  if (!ok) return;
  const leads = data.practice_leads.map((l) => `${orgName(l.organization_id)}: ${nameOf(l.person_id)}`).join(", ");
  renderMembers(`Team at ${when(data.at)}. Practice leads: ${leads || "none you may see"}`, data.members, data.coverages);
}

$("#view-team").onclick = viewTeam;

$("#view-history").onclick = async () => {
  const { ok, data } = await api("GET", `${team()}/history`);
  if (!ok) return;
  renderMembers("Every period ever recorded", data.memberships, data.coverages);
  const events = data.events.map((e) => `<tr><td>${when(e.at)}</td><td>${e.type}</td><td>${nameOf(e.actor_id)}</td><td>${e.reason}</td></tr>`).join("");
  $("#team").insertAdjacentHTML("beforeend", `<h3>Events</h3>
    <table><thead><tr><th>When</th><th>What</th><th>Who</th><th>Why</th></tr></thead><tbody>${events}</tbody></table>`);
};

onSubmit("#member-form", async (form) => {
  const { ok } = await api("POST", `${team()}/members`, { ...fields(form), org_id: orgId() });
  if (ok) viewTeam();
});

onSubmit("#engagement-form", async (form) => {
  if (!requireSelected()) return;
  const { ok, data } = await api("POST", `${team()}/members/${state.selected}/engagement`, fields(form));
  if (ok) { state.selected = data.id; viewTeam(); }
});

onSubmit("#end-form", async (form) => {
  if (!requireSelected()) return;
  const { ok } = await api("POST", `${team()}/members/${state.selected}/end`, fields(form));
  if (ok) { state.selected = null; viewTeam(); }
});

onSubmit("#coverage-form", async (form) => {
  if (!requireSelected()) return;
  const { covering_provider_email, start_in, days, reason } = fields(form);
  const start = Date.now() + Number(start_in) * 86400000;
  const body = {
    covering_provider_email, reason,
    starts_at: new Date(start).toISOString(),
    ends_at: new Date(start + Number(days) * 86400000).toISOString(),
  };
  const { ok } = await api("POST", `${team()}/members/${state.selected}/coverages`, body);
  if (ok) viewTeam();
});

onSubmit("#discharge-form", async (form) => {
  const { ok } = await api("POST", `${team()}/orgs/${orgId()}/discharge`, fields(form));
  if (ok) viewTeam();
});

// ---- Care invitations ----

onSubmit("#care-invite-form", async (form) => {
  const { ok, data } = await api("POST", "/care-invitations", fields(form));
  if (ok) $("#care-accept-form").token.value = data.token;
});

onSubmit("#care-accept-form", async (form) => {
  const { ok } = await api("POST", "/care-invitations/accept", fields(form));
  if (ok) viewTeam();
});

// ---- Records ----

const records = () => `/clients/${clientId()}/records`;

async function viewRecords() {
  const { ok, data } = await api("GET", records());
  if (!ok) { $("#records").textContent = "Refused: see the reason in the log."; return; }
  const rows = data.map((r) => `<tr><td>${r.category}</td><td>${nameOf(r.author_id)}</td><td>${r.body}</td><td>${when(r.written_at)}</td></tr>`).join("");
  $("#records").innerHTML = `<table><thead><tr><th>Category</th><th>Author</th><th>Note</th><th>Written</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

$("#view-records").onclick = viewRecords;

onSubmit("#record-form", async (form) => {
  const { ok } = await api("POST", records(), fields(form));
  if (ok) viewRecords();
});

// ---- Explain ----

onSubmit("#explain-form", async (form) => {
  const { action, category } = fields(form);
  const params = new URLSearchParams({ action, client_id: clientId() });
  if (category) params.set("category", category);
  if (state.selected) params.set("membership_id", state.selected);
  if (["ADD_MEMBER", "DISCHARGE_ORGANIZATION"].includes(action)) params.set("org_id", orgId());
  const { ok, data } = await api("GET", `/access/explain?${params}`);
  $("#explanation").textContent = ok ? data.reason : "Sign in first.";
  $("#explanation").className = ok && data.allowed ? "allowed" : "denied";
});

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
document.querySelectorAll(".discipline-select").forEach((select) => {
  select.insertAdjacentHTML("beforeend", DISCIPLINES.map((d) => `<option>${d}</option>`).join(""));
});
document.querySelectorAll(".category-select").forEach((select) => {
  select.insertAdjacentHTML("beforeend", CATEGORIES.map((c) => `<option>${c}</option>`).join(""));
});
$("#explain-action").innerHTML = ACTIONS.map((a) => `<option>${a}</option>`).join("");
showKindFields();
const saved = sessionStorage.getItem("kinetic-tokens");
loadSeed().then(() => setTokens(saved ? JSON.parse(saved) : null));
