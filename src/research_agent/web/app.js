const storageKeys = {
  token: "erp.session.token",
  workspaceId: "erp.workspace.id",
};

const state = {
  token: localStorage.getItem(storageKeys.token) || "",
  user: null,
  workspaces: [],
  selectedWorkspaceId: localStorage.getItem(storageKeys.workspaceId) || "",
  openAlexResults: [],
  publicBriefings: [],
  publicSummary: null,
  selectedPublicBriefing: null,
  selectedSummaryDays: 7,
  bootstrap: null,
};

const dom = {
  toast: document.getElementById("toast"),
  healthStatus: document.getElementById("health-status"),
  publicStatus: document.getElementById("public-status"),
  publicLatestMeta: document.getElementById("public-latest-meta"),
  publicLatestView: document.getElementById("public-latest-view"),
  publicThemeStrip: document.getElementById("public-theme-strip"),
  publicSummaryView: document.getElementById("public-summary-view"),
  publicBriefingList: document.getElementById("public-briefing-list"),
  refreshPublicButton: document.getElementById("refresh-public"),
  copyPublicLinkButton: document.getElementById("copy-public-link"),
  sessionIndicator: document.getElementById("session-indicator"),
  userSummary: document.getElementById("user-summary"),
  workspaceSelect: document.getElementById("workspace-select"),
  integrationList: document.getElementById("integration-list"),
  briefingList: document.getElementById("briefing-list"),
  openalexResults: document.getElementById("openalex-results"),
  literatureList: document.getElementById("literature-list"),
  assetList: document.getElementById("asset-list"),
  knowledgeList: document.getElementById("knowledge-list"),
  scheduleList: document.getElementById("schedule-list"),
  analysisOutput: document.getElementById("analysis-output"),
};

function escapeHtml(value) {
  return (value ?? "")
    .toString()
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function showToast(message, isError = false) {
  dom.toast.textContent = message;
  dom.toast.classList.remove("hidden");
  dom.toast.style.background = isError ? "rgba(111, 29, 29, 0.95)" : "rgba(31, 30, 26, 0.92)";
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => dom.toast.classList.add("hidden"), 3200);
}

async function api(path, options = {}, auth = true) {
  const headers = new Headers(options.headers || {});
  if (auth && state.token) {
    headers.set("Authorization", `Bearer ${state.token}`);
  }
  const response = await fetch(path, { ...options, headers });
  const text = await response.text();
  let payload = {};
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { detail: text };
    }
  }
  if (!response.ok) {
    if (response.status === 401 && auth) {
      clearSession();
    }
    throw new Error(payload.detail || `Request failed: ${response.status}`);
  }
  return payload;
}

function extractBriefingSlugFromLocation() {
  const match = window.location.pathname.match(/^\/briefings\/([^/]+)$/);
  if (match) {
    return decodeURIComponent(match[1]);
  }
  const search = new URLSearchParams(window.location.search);
  return search.get("briefing") || "";
}

function prettyDate(value) {
  if (!value) {
    return "n/a";
  }
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function absolutePublicUrl(value) {
  if (!value) {
    return "";
  }
  try {
    return new URL(value, window.location.origin).toString();
  } catch {
    return value;
  }
}

function emptyCard(message) {
  return `<div class="card"><p>${escapeHtml(message)}</p></div>`;
}

function clearPrivateLists() {
  dom.integrationList.innerHTML = emptyCard("Log in to view saved provider connections.");
  dom.briefingList.innerHTML = emptyCard("Log in to generate private briefings.");
  dom.openalexResults.innerHTML = emptyCard("Search results will appear here.");
  dom.literatureList.innerHTML = emptyCard("Your imported literature will appear here.");
  dom.assetList.innerHTML = emptyCard("Your uploaded data assets will appear here.");
  dom.knowledgeList.innerHTML = emptyCard("Your private notes will appear here.");
  dom.scheduleList.innerHTML = emptyCard("Your scheduled jobs will appear here.");
  dom.analysisOutput.textContent = "Waiting for analysis output.";
}

function ensureSignedIn() {
  if (!state.token || !state.user) {
    throw new Error("Please sign in first.");
  }
}

function ensureWorkspace() {
  ensureSignedIn();
  if (!state.selectedWorkspaceId) {
    throw new Error("Select a workspace first.");
  }
}

function clearSession() {
  state.token = "";
  state.user = null;
  state.workspaces = [];
  state.selectedWorkspaceId = "";
  localStorage.removeItem(storageKeys.token);
  localStorage.removeItem(storageKeys.workspaceId);
  renderSession();
  renderWorkspaceOptions();
  clearPrivateLists();
}

function setSession(payload) {
  state.token = payload.session_token;
  state.user = payload.user;
  state.workspaces = payload.workspaces || [];
  state.selectedWorkspaceId = state.selectedWorkspaceId || state.workspaces[0]?.id || "";
  localStorage.setItem(storageKeys.token, state.token);
  if (state.selectedWorkspaceId) {
    localStorage.setItem(storageKeys.workspaceId, state.selectedWorkspaceId);
  }
  renderSession();
  renderWorkspaceOptions();
}

function renderSession() {
  if (!state.user) {
    dom.sessionIndicator.textContent = "Signed out";
    dom.userSummary.textContent = "Register or log in to access your private workspace.";
    return;
  }
  dom.sessionIndicator.textContent = "Signed in";
  dom.userSummary.textContent = `${state.user.full_name} | ${state.user.email}`;
}

function renderWorkspaceOptions() {
  dom.workspaceSelect.innerHTML = "";
  if (!state.workspaces.length) {
    dom.workspaceSelect.innerHTML = `<option value="">No workspace yet</option>`;
    return;
  }
  for (const workspace of state.workspaces) {
    const option = document.createElement("option");
    option.value = workspace.id;
    option.textContent = workspace.name;
    option.selected = workspace.id === state.selectedWorkspaceId;
    dom.workspaceSelect.appendChild(option);
  }
}

function renderIntegrations(items) {
  if (!items.length) {
    dom.integrationList.innerHTML = emptyCard("No saved connections yet.");
    return;
  }
  dom.integrationList.innerHTML = items
    .map(
      (item) => `
        <div class="card">
          <h4>${escapeHtml(item.label)}</h4>
          <p>${escapeHtml(item.category)} | ${escapeHtml(item.kind)} | ${escapeHtml(item.model || "default model")}</p>
          <p>${item.is_default ? "Default connection" : "Saved connection"}</p>
          <div class="actions">
            <button type="button" class="secondary" data-test-integration="${item.id}">Test</button>
            <button type="button" class="secondary" data-delete-integration="${item.id}">Delete</button>
          </div>
        </div>
      `,
    )
    .join("");
}

function renderBriefings(items) {
  if (!items.length) {
    dom.briefingList.innerHTML = emptyCard("No private briefings yet.");
    return;
  }
  dom.briefingList.innerHTML = items
    .map(
      (item) => `
        <div class="card">
          <h4>${escapeHtml(item.title)}</h4>
          <p>${escapeHtml(prettyDate(item.created_at))}</p>
          <pre>${escapeHtml(item.summary_markdown)}</pre>
        </div>
      `,
    )
    .join("");
}

function renderOpenAlexResults(items) {
  if (!items.length) {
    dom.openalexResults.innerHTML = emptyCard("No literature results yet.");
    return;
  }
  dom.openalexResults.innerHTML = items
    .map(
      (item) => `
        <div class="card">
          <h4>${escapeHtml(item.title)}</h4>
          <p>${escapeHtml((item.authors || []).slice(0, 4).join(", ")) || "Unknown authors"}</p>
          <p>${escapeHtml(`${item.publication_year || "n/a"} | cited ${item.cited_by_count || 0}`)}</p>
        </div>
      `,
    )
    .join("");
}

function renderLiterature(items) {
  if (!items.length) {
    dom.literatureList.innerHTML = emptyCard("Your literature library is empty.");
    return;
  }
  dom.literatureList.innerHTML = items
    .map(
      (item) => `
        <div class="card">
          <h4>${escapeHtml(item.title)}</h4>
          <p>${escapeHtml((item.authors || []).slice(0, 4).join(", ")) || "Unknown authors"}</p>
          <p>${escapeHtml(item.venue || "Unknown venue")} | ${escapeHtml(item.publication_year || "n/a")}</p>
        </div>
      `,
    )
    .join("");
}

function renderAssets(items) {
  if (!items.length) {
    dom.assetList.innerHTML = emptyCard("No uploaded assets yet.");
    return;
  }
  dom.assetList.innerHTML = items
    .map(
      (item) => `
        <div class="card">
          <h4>${escapeHtml(item.title)}</h4>
          <p>ID: ${escapeHtml(item.id)}</p>
          <p>${escapeHtml(item.kind)} | ${escapeHtml(item.content_type || "unknown content type")}</p>
          <div class="actions">
            <button type="button" class="secondary" data-download-asset="${item.id}">Download</button>
            ${item.kind.startsWith("dataset") ? `<button type="button" class="secondary" data-clean-asset="${item.id}">Clean</button>` : ""}
          </div>
        </div>
      `,
    )
    .join("");
}

function renderKnowledge(items) {
  if (!items.length) {
    dom.knowledgeList.innerHTML = emptyCard("No private notes yet.");
    return;
  }
  dom.knowledgeList.innerHTML = items
    .map(
      (item) => `
        <div class="card">
          <h4>${escapeHtml(item.title)}</h4>
          <p>${escapeHtml((item.tags || []).join(", ")) || "No tags"}</p>
          <p>${escapeHtml(item.content)}</p>
        </div>
      `,
    )
    .join("");
}

function renderSchedules(items) {
  if (!items.length) {
    dom.scheduleList.innerHTML = emptyCard("No private recurring jobs yet.");
    return;
  }
  dom.scheduleList.innerHTML = items
    .map(
      (item) => `
        <div class="card">
          <h4>${escapeHtml(item.name)}</h4>
          <p>${escapeHtml(item.job_type)} | ${escapeHtml(item.timezone_name)} | ${escapeHtml(item.local_time)}</p>
          <p>Next run: ${escapeHtml(item.next_run_at || "not scheduled")}</p>
        </div>
      `,
    )
    .join("");
}

function renderPublicThemes(topThemes) {
  if (!topThemes || !topThemes.length) {
    dom.publicThemeStrip.innerHTML = `<span class="muted">No stable theme signal yet.</span>`;
    return;
  }
  dom.publicThemeStrip.innerHTML = topThemes
    .map(
      (item) =>
        `<span class="topic-chip">${escapeHtml(item.theme)} <strong>${escapeHtml(item.count)}</strong></span>`,
    )
    .join("");
}

function renderPublicLatest(briefing) {
  if (!briefing) {
    state.selectedPublicBriefing = null;
    dom.publicLatestMeta.textContent = "No public briefing has been published yet.";
    dom.publicLatestView.textContent = "The public daily monitor will appear here after the first scheduled collection.";
    renderPublicThemes([]);
    return;
  }
  state.selectedPublicBriefing = briefing;
  dom.publicLatestMeta.textContent = `${briefing.title} | ${briefing.briefing_date} | ${briefing.headline_count} headlines`;
  dom.publicLatestView.textContent = briefing.summary_markdown;
  renderPublicThemes(briefing.top_themes || []);
}

function renderPublicSummary(summary) {
  if (!summary || !summary.report_count) {
    dom.publicSummaryView.textContent = "The rolling public summary will appear after public daily briefings accumulate.";
    return;
  }
  dom.publicSummaryView.textContent = summary.markdown;
}

function updateSummaryButtons() {
  document.querySelectorAll("[data-summary-days]").forEach((button) => {
    button.classList.toggle("is-active", Number(button.getAttribute("data-summary-days")) === state.selectedSummaryDays);
  });
}

function renderPublicBriefingList(items) {
  if (!items.length) {
    dom.publicBriefingList.innerHTML = emptyCard("No public briefings have been published yet.");
    return;
  }
  dom.publicBriefingList.innerHTML = items
    .map(
      (item) => `
        <div class="card">
          <h4>${escapeHtml(item.title)}</h4>
          <p>${escapeHtml(item.briefing_date)} | ${escapeHtml(item.headline_count)} headlines</p>
          <p>${escapeHtml(item.summary_excerpt)}</p>
          <div class="chip-row chip-row-compact">
            ${(item.top_themes || [])
              .slice(0, 3)
              .map((theme) => `<span class="topic-chip">${escapeHtml(theme.theme)}</span>`)
              .join("")}
          </div>
          <div class="actions">
            <button type="button" class="secondary" data-public-slug="${item.slug}">Open</button>
            <button type="button" class="secondary" data-copy-public-url="${escapeHtml(item.share_url || item.detail_path || "")}">Copy link</button>
          </div>
        </div>
      `,
    )
    .join("");
}

async function fetchHealth() {
  const [health, bootstrap] = await Promise.all([
    api("/api/health", {}, false),
    api("/api/bootstrap", {}, false),
  ]);
  state.bootstrap = bootstrap;
  dom.healthStatus.textContent = `${health.status} | ${bootstrap.supported_llm_kinds.length} provider types`;
  dom.publicStatus.textContent = bootstrap.public_digest_enabled
    ? `Daily after ${bootstrap.public_digest_local_time} ${bootstrap.public_digest_timezone}`
    : "Disabled";
}

async function loadPublicSummary(days = state.selectedSummaryDays) {
  state.selectedSummaryDays = Number(days) || 7;
  const summaryResponse = await api(`/api/public/summary?days=${state.selectedSummaryDays}`, {}, false);
  state.publicSummary = summaryResponse;
  renderPublicSummary(summaryResponse);
  updateSummaryButtons();
}

function syncPublicUrl(briefing) {
  if (!briefing) {
    return;
  }
  const nextPath = briefing.detail_path || `/briefings/${briefing.slug}`;
  if (window.location.pathname !== nextPath) {
    window.history.replaceState({}, "", nextPath);
  }
}

async function loadPublicData() {
  const requestedSlug = extractBriefingSlugFromLocation();
  const [latestResponse, listResponse, detailResponse] = await Promise.all([
    api("/api/public/briefings/latest", {}, false),
    api("/api/public/briefings?limit=12", {}, false),
    requestedSlug ? api(`/api/public/briefings/${requestedSlug}`, {}, false) : Promise.resolve({ briefing: null }),
  ]);
  state.publicBriefings = listResponse.items || [];
  const latest = detailResponse.briefing || latestResponse.briefing || state.publicBriefings[0] || null;
  renderPublicLatest(latest);
  if (requestedSlug && latest) {
    syncPublicUrl(latest);
  }
  await loadPublicSummary(state.selectedSummaryDays);
  renderPublicBriefingList(state.publicBriefings);
}

async function loadSession() {
  if (!state.token) {
    renderSession();
    renderWorkspaceOptions();
    clearPrivateLists();
    return;
  }
  const payload = await api("/api/auth/me");
  state.user = payload.user;
  state.workspaces = payload.workspaces || [];
  if (!state.workspaces.some((item) => item.id === state.selectedWorkspaceId)) {
    state.selectedWorkspaceId = state.workspaces[0]?.id || "";
    if (state.selectedWorkspaceId) {
      localStorage.setItem(storageKeys.workspaceId, state.selectedWorkspaceId);
    }
  }
  renderSession();
  renderWorkspaceOptions();
  await refreshWorkspaceData();
}

async function refreshWorkspaceData() {
  ensureWorkspace();
  const workspaceId = state.selectedWorkspaceId;
  const [integrations, briefings, literature, assets, knowledge, schedules] = await Promise.all([
    api("/api/integrations"),
    api(`/api/workspaces/${workspaceId}/briefings`),
    api(`/api/workspaces/${workspaceId}/literature`),
    api(`/api/workspaces/${workspaceId}/assets`),
    api(`/api/workspaces/${workspaceId}/knowledge`),
    api(`/api/workspaces/${workspaceId}/schedules`),
  ]);
  renderIntegrations(integrations.items || []);
  renderBriefings(briefings.items || []);
  renderLiterature(literature.items || []);
  renderAssets(assets.items || []);
  renderKnowledge(knowledge.items || []);
  renderSchedules(schedules.items || []);
}

async function handleRegister(event) {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
  const response = await api(
    "/api/auth/register",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    false,
  );
  setSession(response);
  await refreshWorkspaceData();
  event.currentTarget.reset();
  showToast("Account created.");
}

async function handleLogin(event) {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
  const response = await api(
    "/api/auth/login",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    false,
  );
  setSession(response);
  await refreshWorkspaceData();
  event.currentTarget.reset();
  showToast("Signed in.");
}

async function handleCreateWorkspace(event) {
  event.preventDefault();
  ensureSignedIn();
  const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
  const response = await api("/api/workspaces", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  state.workspaces.push(response.workspace);
  state.selectedWorkspaceId = response.workspace.id;
  localStorage.setItem(storageKeys.workspaceId, state.selectedWorkspaceId);
  renderWorkspaceOptions();
  await refreshWorkspaceData();
  event.currentTarget.reset();
  showToast("Workspace created.");
}

async function handleIntegration(event) {
  event.preventDefault();
  ensureSignedIn();
  const formData = new FormData(event.currentTarget);
  const payload = Object.fromEntries(formData.entries());
  payload.is_default = formData.get("is_default") === "on";
  const response = await api("/api/integrations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await refreshWorkspaceData();
  event.currentTarget.reset();
  showToast(`Saved connection: ${response.integration.label}`);
}

async function handleBriefing(event) {
  event.preventDefault();
  ensureWorkspace();
  const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
  await api(`/api/workspaces/${state.selectedWorkspaceId}/briefings/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await refreshWorkspaceData();
  showToast("Private briefing generated.");
}

async function handleOpenAlexSearch(event) {
  event.preventDefault();
  const formData = new FormData(event.currentTarget);
  const params = new URLSearchParams({
    q: formData.get("query").toString(),
    max_results: "8",
    open_access_only: formData.get("open_access_only") === "on" ? "true" : "false",
  });
  const response = await api(`/api/openalex/search?${params.toString()}`, {}, false);
  state.openAlexResults = response.items || [];
  renderOpenAlexResults(state.openAlexResults);
  showToast(`Found ${state.openAlexResults.length} literature items.`);
}

async function handleOpenAlexImport() {
  ensureWorkspace();
  if (!state.openAlexResults.length) {
    throw new Error("Run a literature search first.");
  }
  await api(`/api/workspaces/${state.selectedWorkspaceId}/literature/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ works: state.openAlexResults }),
  });
  await refreshWorkspaceData();
  showToast("Literature imported into your private library.");
}

async function handleUpload(event) {
  event.preventDefault();
  ensureWorkspace();
  const formData = new FormData(event.currentTarget);
  await api(`/api/workspaces/${state.selectedWorkspaceId}/assets/upload`, {
    method: "POST",
    body: formData,
  });
  await refreshWorkspaceData();
  event.currentTarget.reset();
  showToast("File uploaded.");
}

async function handleKnowledge(event) {
  event.preventDefault();
  ensureWorkspace();
  const formData = new FormData(event.currentTarget);
  const payload = Object.fromEntries(formData.entries());
  payload.tags = payload.tags ? payload.tags.split(",").map((item) => item.trim()).filter(Boolean) : [];
  payload.metadata = {};
  await api(`/api/workspaces/${state.selectedWorkspaceId}/knowledge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await refreshWorkspaceData();
  event.currentTarget.reset();
  showToast("Private note saved.");
}

async function handleSchedule(event) {
  event.preventDefault();
  ensureWorkspace();
  const formData = new FormData(event.currentTarget);
  const payload = {
    name: formData.get("name"),
    local_time: formData.get("local_time"),
    timezone_name: "Asia/Shanghai",
    job_type: "economic_briefing",
    config: {
      query_text: formData.get("query_text"),
      title: formData.get("name"),
    },
  };
  await api(`/api/workspaces/${state.selectedWorkspaceId}/schedules`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await refreshWorkspaceData();
  event.currentTarget.reset();
  showToast("Private daily job created.");
}

async function handleOls(event) {
  event.preventDefault();
  ensureWorkspace();
  const formData = new FormData(event.currentTarget);
  const payload = {
    asset_id: formData.get("asset_id"),
    dependent: formData.get("dependent"),
    independents: formData
      .get("independents")
      .toString()
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
  };
  const response = await api(`/api/workspaces/${state.selectedWorkspaceId}/analysis/ols`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  dom.analysisOutput.textContent = JSON.stringify(response, null, 2);
  await refreshWorkspaceData();
  showToast("OLS completed.");
}

async function handleIntegrationActions(event) {
  const testId = event.target.getAttribute("data-test-integration");
  const deleteId = event.target.getAttribute("data-delete-integration");
  if (testId) {
    const response = await api(`/api/integrations/${testId}/test`, { method: "POST" });
    showToast(response.preview || "Connection test succeeded.");
    return;
  }
  if (deleteId) {
    await api(`/api/integrations/${deleteId}`, { method: "DELETE" });
    await refreshWorkspaceData();
    showToast("Connection deleted.");
  }
}

async function downloadAsset(assetId) {
  const response = await fetch(`/api/assets/${assetId}/download`, {
    headers: { Authorization: `Bearer ${state.token}` },
  });
  if (!response.ok) {
    throw new Error("Download failed.");
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/i);
  const filename = match?.[1] || `${assetId}.bin`;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

async function copyToClipboard(text) {
  if (!text) {
    throw new Error("Nothing to copy.");
  }
  await navigator.clipboard.writeText(absolutePublicUrl(text));
}

async function handleAssetActions(event) {
  const cleanId = event.target.getAttribute("data-clean-asset");
  const downloadId = event.target.getAttribute("data-download-asset");
  if (cleanId) {
    await api(`/api/workspaces/${state.selectedWorkspaceId}/assets/${cleanId}/clean`, { method: "POST" });
    await refreshWorkspaceData();
    showToast("Cleaned dataset generated.");
    return;
  }
  if (downloadId) {
    await downloadAsset(downloadId);
    showToast("Download started.");
  }
}

async function handlePublicActions(event) {
  const slug = event.target.getAttribute("data-public-slug");
  const publicUrl = event.target.getAttribute("data-copy-public-url");
  if (publicUrl) {
    await copyToClipboard(publicUrl);
    showToast("Public link copied.");
    return;
  }
  if (!slug) {
    return;
  }
  const cached = state.publicBriefings.find((item) => item.slug === slug);
  if (cached) {
    renderPublicLatest(cached);
    syncPublicUrl(cached);
    return;
  }
  const response = await api(`/api/public/briefings/${slug}`, {}, false);
  if (response.briefing) {
    renderPublicLatest(response.briefing);
    syncPublicUrl(response.briefing);
  }
}

function wrap(handler) {
  return async (event) => {
    try {
      await handler(event);
    } catch (error) {
      showToast(error.message || "Something went wrong.", true);
    }
  };
}

function bind() {
  document.getElementById("register-form").addEventListener("submit", wrap(handleRegister));
  document.getElementById("login-form").addEventListener("submit", wrap(handleLogin));
  document.getElementById("workspace-form").addEventListener("submit", wrap(handleCreateWorkspace));
  document.getElementById("integration-form").addEventListener("submit", wrap(handleIntegration));
  document.getElementById("briefing-form").addEventListener("submit", wrap(handleBriefing));
  document.getElementById("openalex-form").addEventListener("submit", wrap(handleOpenAlexSearch));
  document.getElementById("import-openalex").addEventListener("click", wrap(handleOpenAlexImport));
  document.getElementById("upload-form").addEventListener("submit", wrap(handleUpload));
  document.getElementById("knowledge-form").addEventListener("submit", wrap(handleKnowledge));
  document.getElementById("schedule-form").addEventListener("submit", wrap(handleSchedule));
  document.getElementById("ols-form").addEventListener("submit", wrap(handleOls));
  dom.refreshPublicButton.addEventListener("click", wrap(async () => {
    await loadPublicData();
    showToast("Public feed refreshed.");
  }));
  dom.copyPublicLinkButton.addEventListener("click", wrap(async () => {
    const briefing = state.selectedPublicBriefing;
    if (!briefing) {
      throw new Error("No public briefing selected.");
    }
    await copyToClipboard(briefing.share_url || window.location.href);
    showToast("Public link copied.");
  }));
  document.querySelectorAll("[data-summary-days]").forEach((button) => {
    button.addEventListener(
      "click",
      wrap(async () => {
        await loadPublicSummary(Number(button.getAttribute("data-summary-days")));
        showToast(`Loaded ${button.getAttribute("data-summary-days")}-day summary.`);
      }),
    );
  });
  dom.workspaceSelect.addEventListener(
    "change",
    wrap(async (event) => {
      state.selectedWorkspaceId = event.target.value;
      localStorage.setItem(storageKeys.workspaceId, state.selectedWorkspaceId);
      await refreshWorkspaceData();
    }),
  );
  dom.integrationList.addEventListener("click", wrap(handleIntegrationActions));
  dom.assetList.addEventListener("click", wrap(handleAssetActions));
  dom.publicBriefingList.addEventListener("click", wrap(handlePublicActions));
}

async function init() {
  bind();
  clearPrivateLists();
  renderSession();
  renderWorkspaceOptions();
  try {
    await fetchHealth();
    await loadPublicData();
    await loadSession();
  } catch (error) {
    showToast(error.message || "Initialization failed.", true);
  }
}

init();
