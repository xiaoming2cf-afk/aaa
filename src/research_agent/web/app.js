const storageKeys = {
  token: "erp.session.token",
  workspaceId: "erp.workspace.id",
};

const state = {
  token: localStorage.getItem(storageKeys.token) || "",
  user: null,
  workspaces: [],
  selectedWorkspaceId: localStorage.getItem(storageKeys.workspaceId) || "",
  assetProfiles: {},
  selectedAnalysisAssetId: "",
  currentPlotAssetId: "",
  currentPlotUrl: "",
  openAlexResults: [],
  publicBriefings: [],
  publicSummary: null,
  selectedPublicBriefing: null,
  selectedSummaryDays: 7,
  selectedSummaryWindow: "",
  bootstrap: null,
};

const dom = {
  publicPanel: document.getElementById("public-panel"),
  toast: document.getElementById("toast"),
  healthStatus: document.getElementById("health-status"),
  publicStatus: document.getElementById("public-status"),
  publicCurrentTitle: document.getElementById("public-current-title"),
  publicCurrentMeta: document.getElementById("public-current-meta"),
  publicDateSwitcher: document.getElementById("public-date-switcher"),
  publicLatestMeta: document.getElementById("public-latest-meta"),
  publicLatestView: document.getElementById("public-latest-view"),
  publicThemeStrip: document.getElementById("public-theme-strip"),
  publicClusterList: document.getElementById("public-cluster-list"),
  publicReadingList: document.getElementById("public-reading-list"),
  publicSummaryTitle: document.getElementById("public-summary-title"),
  publicSummaryMeta: document.getElementById("public-summary-meta"),
  publicSummaryView: document.getElementById("public-summary-view"),
  publicSummaryPages: document.getElementById("public-summary-pages"),
  publicSummaryFeatured: document.getElementById("public-summary-featured"),
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
  analysisAssetSelect: document.getElementById("analysis-asset-select"),
  refreshAssetProfileButton: document.getElementById("refresh-asset-profile"),
  analysisAssetOverview: document.getElementById("analysis-asset-overview"),
  analysisColumnGrid: document.getElementById("analysis-column-grid"),
  analysisPreviewTable: document.getElementById("analysis-preview-table"),
  prepareForm: document.getElementById("prepare-form"),
  prepareKeepColumns: document.getElementById("prepare-keep-columns"),
  prepareRequiredColumns: document.getElementById("prepare-required-columns"),
  prepareNumericColumns: document.getElementById("prepare-numeric-columns"),
  prepareBinaryColumns: document.getElementById("prepare-binary-columns"),
  prepareDateColumns: document.getElementById("prepare-date-columns"),
  prepareImputeMethod: document.getElementById("prepare-impute-method"),
  prepareImputeColumns: document.getElementById("prepare-impute-columns"),
  prepareWinsorizeColumns: document.getElementById("prepare-winsorize-columns"),
  prepareWinsorLower: document.getElementById("prepare-winsor-lower"),
  prepareWinsorUpper: document.getElementById("prepare-winsor-upper"),
  prepareLogTransformColumns: document.getElementById("prepare-log-transform-columns"),
  prepareStandardizeColumns: document.getElementById("prepare-standardize-columns"),
  prepareOutlierColumns: document.getElementById("prepare-outlier-columns"),
  prepareOutlierMethod: document.getElementById("prepare-outlier-method"),
  prepareOutlierThreshold: document.getElementById("prepare-outlier-threshold"),
  prepareOutput: document.getElementById("prepare-output"),
  modelForm: document.getElementById("model-form"),
  modelType: document.getElementById("model-type"),
  modelDependent: document.getElementById("model-dependent"),
  modelIndependents: document.getElementById("model-independents"),
  modelControls: document.getElementById("model-controls"),
  modelRobustCovariance: document.getElementById("model-robust-covariance"),
  didFields: document.getElementById("did-fields"),
  didTreatmentColumn: document.getElementById("did-treatment-column"),
  didPostColumn: document.getElementById("did-post-column"),
  gravityFields: document.getElementById("gravity-fields"),
  gravityDistanceWrap: document.getElementById("gravity-distance-wrap"),
  gravityOriginMassColumn: document.getElementById("gravity-origin-mass-column"),
  gravityDestinationMassColumn: document.getElementById("gravity-destination-mass-column"),
  gravityDistanceColumn: document.getElementById("gravity-distance-column"),
  feFields: document.getElementById("fe-fields"),
  panelEntityColumn: document.getElementById("panel-entity-column"),
  panelTimeColumn: document.getElementById("panel-time-column"),
  includeTimeEffects: document.getElementById("include-time-effects"),
  feTimeToggle: document.getElementById("fe-time-toggle"),
  ivFields: document.getElementById("iv-fields"),
  ivEndogenousColumn: document.getElementById("iv-endogenous-column"),
  ivInstrumentColumns: document.getElementById("iv-instrument-columns"),
  olsFields: document.getElementById("ols-fields"),
  plotForm: document.getElementById("plot-form"),
  plotType: document.getElementById("plot-type"),
  plotXColumn: document.getElementById("plot-x-column"),
  plotYColumns: document.getElementById("plot-y-columns"),
  plotGroupColumn: document.getElementById("plot-group-column"),
  plotTitle: document.getElementById("plot-title"),
  plotPreviewPanel: document.getElementById("plot-preview-panel"),
  plotPreviewMeta: document.getElementById("plot-preview-meta"),
  plotPreviewImage: document.getElementById("plot-preview-image"),
  downloadPlotButton: document.getElementById("download-plot"),
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

function extractSummaryWindowFromLocation() {
  const match = window.location.pathname.match(/^\/summaries\/(weekly|monthly)$/);
  return match ? decodeURIComponent(match[1]) : "";
}

function detectPageMode() {
  if (window.location.pathname === "/") {
    return "home";
  }
  if (window.location.pathname === "/public-monitor" || window.location.pathname === "/macro-desk") {
    return "public-monitor";
  }
  if (extractBriefingSlugFromLocation()) {
    return "briefing";
  }
  if (extractSummaryWindowFromLocation()) {
    return "summary";
  }
  return "home";
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

function formatInlineMarkdown(text) {
  const escaped = escapeHtml(text || "");
  return escaped.replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noreferrer">$1</a>');
}

function markdownToHtml(markdown) {
  const lines = (markdown || "").split(/\r?\n/);
  const html = [];
  let inList = false;

  const closeList = () => {
    if (inList) {
      html.push("</ul>");
      inList = false;
    }
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      closeList();
      continue;
    }
    if (line.startsWith("# ")) {
      closeList();
      html.push(`<h2>${formatInlineMarkdown(line.slice(2))}</h2>`);
      continue;
    }
    if (line.startsWith("## ")) {
      closeList();
      html.push(`<h3>${formatInlineMarkdown(line.slice(3))}</h3>`);
      continue;
    }
    if (line.startsWith("### ")) {
      closeList();
      html.push(`<h4>${formatInlineMarkdown(line.slice(4))}</h4>`);
      continue;
    }
    if (line.startsWith("- ")) {
      if (!inList) {
        html.push("<ul>");
        inList = true;
      }
      html.push(`<li>${formatInlineMarkdown(line.slice(2))}</li>`);
      continue;
    }
    closeList();
    html.push(`<p>${formatInlineMarkdown(line)}</p>`);
  }

  closeList();
  return html.join("") || `<p class="muted">No content yet.</p>`;
}

function defaultSummaryPages() {
  return [
    {
      window: "weekly",
      days: 7,
      title: "Weekly Macro Roundup",
      subtitle: "Standalone 7-day page for the latest macro and market themes.",
      detail_path: "/summaries/weekly",
      share_url: "/summaries/weekly",
    },
    {
      window: "monthly",
      days: 30,
      title: "Monthly Macro Review",
      subtitle: "Standalone 30-day page for broader economic trend review.",
      detail_path: "/summaries/monthly",
      share_url: "/summaries/monthly",
    },
  ];
}

function emptyCard(message) {
  return `<div class="card"><p>${escapeHtml(message)}</p></div>`;
}

function getSelectedValues(select) {
  if (!select) {
    return [];
  }
  return Array.from(select.selectedOptions || []).map((option) => option.value).filter(Boolean);
}

function setSelectOptions(select, items, { multiple = false, placeholder = "Select an option", selected = [] } = {}) {
  if (!select) {
    return;
  }
  const selectedSet = new Set(Array.isArray(selected) ? selected : [selected].filter(Boolean));
  const includeBlank = !multiple;
  select.innerHTML = includeBlank ? `<option value="">${escapeHtml(placeholder)}</option>` : "";
  for (const item of items) {
    const option = document.createElement("option");
    option.value = item.value;
    option.textContent = item.label;
    option.selected = selectedSet.has(item.value);
    select.appendChild(option);
  }
}

function datasetAssets(items) {
  return (items || []).filter((item) => (item.kind || "").startsWith("dataset"));
}

function currentAssetProfile() {
  return state.assetProfiles[state.selectedAnalysisAssetId] || null;
}

function revokeCurrentPlotUrl() {
  if (state.currentPlotUrl) {
    URL.revokeObjectURL(state.currentPlotUrl);
    state.currentPlotUrl = "";
  }
}

function renderDataLabPlaceholders() {
  dom.analysisAssetOverview && (dom.analysisAssetOverview.innerHTML = `<p>Select a dataset to inspect rows, missingness, variable roles, and preview records.</p>`);
  dom.analysisColumnGrid && (dom.analysisColumnGrid.innerHTML = emptyCard("Column roles and missingness will appear here."));
  dom.analysisPreviewTable && (dom.analysisPreviewTable.innerHTML = `<p class="muted">Dataset preview will appear here after you load a profile.</p>`);
  dom.prepareOutput && (dom.prepareOutput.textContent = "Waiting for sample preparation.");
  dom.analysisOutput && (dom.analysisOutput.textContent = "Waiting for model output.");
  if (dom.plotPreviewPanel) {
    dom.plotPreviewPanel.classList.add("hidden");
  }
  if (dom.plotPreviewMeta) {
    dom.plotPreviewMeta.textContent = "No chart generated yet.";
  }
  if (dom.plotPreviewImage) {
    dom.plotPreviewImage.removeAttribute("src");
  }
  state.currentPlotAssetId = "";
  revokeCurrentPlotUrl();
}

function syncDataLabAssetOptions(items) {
  const datasets = datasetAssets(items);
  const options = datasets.map((item) => ({
    value: item.id,
    label: `${item.title} | ${item.kind}`,
  }));
  const stillExists = datasets.some((item) => item.id === state.selectedAnalysisAssetId);
  if (!stillExists) {
    state.selectedAnalysisAssetId = datasets[0]?.id || "";
  }
  setSelectOptions(dom.analysisAssetSelect, options, {
    placeholder: "Select a dataset asset",
    selected: state.selectedAnalysisAssetId,
  });
  if (!datasets.length) {
    renderDataLabPlaceholders();
  }
}

function renderPreviewTable(rows) {
  if (!dom.analysisPreviewTable) {
    return;
  }
  if (!rows || !rows.length) {
    dom.analysisPreviewTable.innerHTML = `<p class="muted">No preview rows are available for this dataset.</p>`;
    return;
  }
  const columns = Object.keys(rows[0] || {});
  dom.analysisPreviewTable.innerHTML = `
    <div class="table-scroll">
      <table>
        <thead>
          <tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (row) => `
                <tr>
                  ${columns.map((column) => `<td>${escapeHtml(row[column] ?? "")}</td>`).join("")}
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function populateDataLabSelectors(profile) {
  const columns = (profile?.column_profiles || []).map((item) => ({
    value: item.name,
    label: `${item.name} | ${item.role}`,
  }));
  const numericColumns = (profile?.column_roles?.numeric || []).map((value) => ({ value, label: value }));
  const binaryColumns = (profile?.column_roles?.binary || []).map((value) => ({ value, label: value }));
  const allColumns = columns;

  setSelectOptions(dom.prepareKeepColumns, allColumns, { multiple: true });
  setSelectOptions(dom.prepareRequiredColumns, allColumns, { multiple: true });
  setSelectOptions(dom.prepareNumericColumns, allColumns, { multiple: true });
  setSelectOptions(dom.prepareBinaryColumns, binaryColumns, { multiple: true });
  setSelectOptions(dom.prepareDateColumns, allColumns, { multiple: true });
  setSelectOptions(dom.prepareImputeColumns, allColumns, { multiple: true });
  setSelectOptions(dom.prepareWinsorizeColumns, numericColumns, { multiple: true });
  setSelectOptions(dom.prepareLogTransformColumns, numericColumns, { multiple: true });
  setSelectOptions(dom.prepareStandardizeColumns, numericColumns, { multiple: true });
  setSelectOptions(dom.prepareOutlierColumns, numericColumns, { multiple: true });

  setSelectOptions(dom.modelIndependents, numericColumns, { multiple: true });
  setSelectOptions(dom.modelControls, numericColumns, { multiple: true });
  setSelectOptions(dom.didTreatmentColumn, binaryColumns, { placeholder: "Select treatment indicator" });
  setSelectOptions(dom.didPostColumn, binaryColumns, { placeholder: "Select post indicator" });
  setSelectOptions(dom.gravityOriginMassColumn, numericColumns, { placeholder: "Select origin mass" });
  setSelectOptions(dom.gravityDestinationMassColumn, numericColumns, { placeholder: "Select destination mass" });
  setSelectOptions(dom.gravityDistanceColumn, numericColumns, { placeholder: "Select distance variable" });
  setSelectOptions(dom.panelEntityColumn, allColumns, { placeholder: "Select entity column" });
  setSelectOptions(dom.panelTimeColumn, allColumns, { placeholder: "Select time column" });
  setSelectOptions(dom.ivEndogenousColumn, numericColumns, { placeholder: "Select endogenous regressor" });
  setSelectOptions(dom.ivInstrumentColumns, numericColumns, { multiple: true });

  setSelectOptions(dom.plotXColumn, allColumns, { placeholder: "Select X variable" });
  setSelectOptions(dom.plotYColumns, numericColumns, { multiple: true });
  setSelectOptions(dom.plotGroupColumn, columns, { placeholder: "Optional group column" });
  refreshModelVariableOptions();
  updateModelFieldVisibility();
}

function renderAssetProfile(profile) {
  if (!profile) {
    renderDataLabPlaceholders();
    return;
  }
  if (dom.analysisAssetOverview) {
    dom.analysisAssetOverview.innerHTML = `
      <h4>${escapeHtml(profile.asset.title)}</h4>
      <p>${escapeHtml(profile.rows)} rows | ${escapeHtml(profile.columns)} columns | duplicate rows detected: ${escapeHtml(profile.duplicate_rows_detected)}</p>
      <p>${escapeHtml((profile.suggested_models || []).join(", ")) || "No suggested models yet."}</p>
    `;
  }
  if (dom.analysisColumnGrid) {
    dom.analysisColumnGrid.innerHTML = (profile.column_profiles || [])
      .map(
        (column) => `
          <article class="column-card">
            <h4>${escapeHtml(column.name)}</h4>
            <p>${escapeHtml(column.role)} | missing ${escapeHtml(column.missing_count)} | unique ${escapeHtml(column.unique_count)}</p>
            <p class="muted">Source: ${escapeHtml(column.source_name)}</p>
          </article>
        `,
      )
      .join("");
  }
  renderPreviewTable(profile.preview_rows || []);
  populateDataLabSelectors(profile);
}

function refreshModelVariableOptions() {
  const profile = currentAssetProfile();
  const numericColumns = (profile?.column_roles?.numeric || []).map((value) => ({ value, label: value }));
  const binaryColumns = (profile?.column_roles?.binary || []).map((value) => ({ value, label: value }));
  const modelType = dom.modelType?.value || "ols";
  const currentDependent = dom.modelDependent?.value || "";
  const placeholder =
    modelType === "gravity"
      ? "Select a flow variable"
      : modelType === "logit" || modelType === "probit"
        ? "Select a binary outcome"
        : "Select an outcome variable";
  const options = modelType === "logit" || modelType === "probit" ? binaryColumns : numericColumns;
  setSelectOptions(dom.modelDependent, options, { placeholder, selected: currentDependent });
}

function updateModelFieldVisibility() {
  const modelType = dom.modelType?.value || "ols";
  const usesCoreRegressionFields = ["ols", "logit", "probit", "fixed_effects", "iv_2sls"].includes(modelType);
  dom.olsFields?.classList.toggle("hidden", !usesCoreRegressionFields);
  dom.didFields?.classList.toggle("hidden", modelType !== "did");
  dom.gravityFields?.classList.toggle("hidden", modelType !== "gravity");
  dom.gravityDistanceWrap?.classList.toggle("hidden", modelType !== "gravity");
  dom.feFields?.classList.toggle("hidden", modelType !== "fixed_effects");
  dom.feTimeToggle?.classList.toggle("hidden", modelType !== "fixed_effects");
  dom.ivFields?.classList.toggle("hidden", modelType !== "iv_2sls");
  refreshModelVariableOptions();
}

function hasPrivateWorkspaceUI() {
  return Boolean(dom.workspaceSelect && dom.integrationList);
}

function hasPublicMonitorUI() {
  return Boolean(dom.publicLatestView && dom.publicSummaryView && dom.publicBriefingList);
}

function clearPrivateLists() {
  if (!hasPrivateWorkspaceUI()) {
    return;
  }
  dom.integrationList.innerHTML = emptyCard("Log in to view saved provider connections.");
  dom.briefingList.innerHTML = emptyCard("Log in to generate private briefings.");
  dom.openalexResults.innerHTML = emptyCard("Search results will appear here.");
  dom.literatureList.innerHTML = emptyCard("Your imported literature will appear here.");
  dom.assetList.innerHTML = emptyCard("Your uploaded data assets will appear here.");
  dom.knowledgeList.innerHTML = emptyCard("Your private notes will appear here.");
  dom.scheduleList.innerHTML = emptyCard("Your scheduled jobs will appear here.");
  dom.analysisOutput.textContent = "Waiting for analysis output.";
  if (dom.analysisAssetSelect) {
    dom.analysisAssetSelect.innerHTML = `<option value="">Select a dataset asset</option>`;
  }
  renderDataLabPlaceholders();
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
  if (hasPrivateWorkspaceUI()) {
    renderSession();
    renderWorkspaceOptions();
    clearPrivateLists();
  }
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
  if (hasPrivateWorkspaceUI()) {
    renderSession();
    renderWorkspaceOptions();
  }
}

function renderSession() {
  if (!dom.sessionIndicator || !dom.userSummary) {
    return;
  }
  if (!state.user) {
    dom.sessionIndicator.textContent = "Signed out";
    dom.userSummary.textContent = "Register or log in to access your private workspace.";
    return;
  }
  dom.sessionIndicator.textContent = "Signed in";
  dom.userSummary.textContent = `${state.user.full_name} | ${state.user.email}`;
}

function renderWorkspaceOptions() {
  if (!dom.workspaceSelect) {
    return;
  }
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
  syncDataLabAssetOptions(items);
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
            ${item.kind.startsWith("dataset") ? `<button type="button" class="secondary" data-select-asset="${item.id}">Use in lab</button>` : ""}
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
  if (!dom.publicThemeStrip) {
    return;
  }
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

function renderPublicDateSwitcher(items, selectedSlug) {
  if (!dom.publicDateSwitcher) {
    return;
  }
  if (!items || !items.length) {
    dom.publicDateSwitcher.innerHTML = `<span class="muted">Recent editions will appear here.</span>`;
    return;
  }
  dom.publicDateSwitcher.innerHTML = items
    .slice(0, 10)
    .map(
      (item) => `
        <button
          type="button"
          class="date-pill${item.slug === selectedSlug ? " is-active" : ""}"
          data-public-slug="${item.slug}"
          title="${escapeHtml(item.title)}"
        >
          <span>${escapeHtml(item.briefing_date)}</span>
          <strong>${escapeHtml(item.headline_count)}</strong>
        </button>
      `,
    )
    .join("");
}

function renderPublicClusters(clusters) {
  if (!dom.publicClusterList) {
    return;
  }
  if (!clusters || !clusters.length) {
    dom.publicClusterList.innerHTML = emptyCard("No stable clustering signal is available for this public edition yet.");
    return;
  }
  dom.publicClusterList.innerHTML = clusters
    .map(
      (cluster) => `
        <article class="cluster-card">
          <div class="panel-head panel-head-wrap">
            <div>
              <h4>${escapeHtml(cluster.label)}</h4>
              <span class="muted">${escapeHtml(cluster.headline_count)} clustered headline(s)</span>
            </div>
          </div>
          <p>${escapeHtml(cluster.summary)}</p>
          <div class="chip-row chip-row-compact">
            ${(cluster.domains || [])
              .slice(0, 3)
              .map((item) => `<span class="topic-chip">${escapeHtml(item.domain)} <strong>${escapeHtml(item.count)}</strong></span>`)
              .join("")}
          </div>
          <div class="cluster-links">
            ${(cluster.items || [])
              .map((item) =>
                item.url
                  ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a>`
                  : `<span>${escapeHtml(item.title)}</span>`,
              )
              .join("")}
          </div>
        </article>
      `,
    )
    .join("");
}

function renderRecommendedReading(payload) {
  if (!dom.publicReadingList) {
    return;
  }
  const sections = [
    {
      label: "Source Articles",
      items: payload?.source_articles || [],
    },
    {
      label: "Related Daily Editions",
      items: payload?.related_briefings || [],
    },
    {
      label: "Summary Pages",
      items: payload?.summary_pages || [],
    },
  ].filter((section) => section.items.length);

  if (!sections.length) {
    dom.publicReadingList.innerHTML = emptyCard("Recommended reading will appear once related sources and themes accumulate.");
    return;
  }

  dom.publicReadingList.innerHTML = sections
    .map(
      (section) => `
        <article class="reading-card">
          <h4>${escapeHtml(section.label)}</h4>
          <div class="reading-links">
            ${section.items
              .map(
                (item) => `
                  <a href="${escapeHtml(item.url)}" target="${item.kind === "article" ? "_blank" : "_self"}" rel="${item.kind === "article" ? "noreferrer" : ""}">
                    <strong>${escapeHtml(item.title)}</strong>
                    <span>${escapeHtml(item.subtitle || "")}</span>
                  </a>
                `,
              )
              .join("")}
          </div>
        </article>
      `,
    )
    .join("");
}

function renderSummaryPages(pages) {
  if (!dom.publicSummaryPages) {
    return;
  }
  const items = pages && pages.length ? pages : defaultSummaryPages();
  const activeWindow = extractSummaryWindowFromLocation();
  dom.publicSummaryPages.innerHTML = items
    .map(
      (item) => `
        <a class="summary-page-card${activeWindow === item.window ? " is-active" : ""}" href="${escapeHtml(item.detail_path || item.share_url || "/")}">
          <span class="pill">${escapeHtml(item.days)}D</span>
          <h4>${escapeHtml(item.title)}</h4>
          <p>${escapeHtml(item.subtitle)}</p>
        </a>
      `,
    )
    .join("");
}

function renderSummaryFeatured(items) {
  if (!dom.publicSummaryFeatured) {
    return;
  }
  if (!items || !items.length) {
    dom.publicSummaryFeatured.innerHTML = emptyCard("No contributing editions are available for the current summary window yet.");
    return;
  }
  dom.publicSummaryFeatured.innerHTML = items
    .map(
      (item) => `
        <div class="card">
          <h4>${escapeHtml(item.title)}</h4>
          <p>${escapeHtml(item.briefing_date)} | ${escapeHtml(item.headline_count)} headlines</p>
          <div class="actions">
            <button type="button" class="secondary" data-public-slug="${item.slug}">Open</button>
          </div>
        </div>
      `,
    )
    .join("");
}

function renderPublicLatest(briefing) {
  if (!hasPublicMonitorUI()) {
    return;
  }
  if (!briefing) {
    state.selectedPublicBriefing = null;
    if (dom.publicCurrentTitle) {
      dom.publicCurrentTitle.textContent = "No public edition yet";
    }
    if (dom.publicCurrentMeta) {
      dom.publicCurrentMeta.textContent = "Waiting for the first scheduled public briefing.";
    }
    dom.publicLatestMeta.textContent = "No public briefing has been published yet.";
    dom.publicLatestView.innerHTML = `<p class="muted">The public daily monitor will appear here after the first scheduled collection.</p>`;
    renderPublicDateSwitcher(state.publicBriefings || [], "");
    renderPublicThemes([]);
    renderPublicClusters([]);
    renderRecommendedReading(null);
    return;
  }
  state.selectedPublicBriefing = briefing;
  if (dom.publicCurrentTitle) {
    dom.publicCurrentTitle.textContent = briefing.title;
  }
  if (dom.publicCurrentMeta) {
    dom.publicCurrentMeta.textContent = `${briefing.briefing_date} | ${briefing.headline_count} headlines | ${briefing.timezone_name}`;
  }
  dom.publicLatestMeta.textContent = `${briefing.title} | ${briefing.briefing_date} | ${briefing.headline_count} headlines`;
  dom.publicLatestView.innerHTML = markdownToHtml(briefing.summary_markdown);
  renderPublicDateSwitcher(state.publicBriefings || [], briefing.slug);
  renderPublicThemes(briefing.top_themes || []);
  renderPublicClusters(briefing.news_clusters || []);
  renderRecommendedReading(briefing.recommended_reading || null);
}

function renderPublicSummary(summary) {
  if (!dom.publicSummaryView || !dom.publicSummaryTitle || !dom.publicSummaryMeta) {
    return;
  }
  if (!summary || !summary.report_count) {
    dom.publicSummaryTitle.textContent = "Rolling Summary";
    dom.publicSummaryMeta.textContent = "Recent multi-day view";
    dom.publicSummaryView.innerHTML = `<p class="muted">The rolling public summary will appear after public daily briefings accumulate.</p>`;
    renderSummaryPages(summary?.available_pages || defaultSummaryPages());
    renderSummaryFeatured([]);
    return;
  }
  dom.publicSummaryTitle.textContent = summary.title || "Rolling Summary";
  dom.publicSummaryMeta.textContent = summary.subtitle || `${summary.days}-day public view`;
  dom.publicSummaryView.innerHTML = markdownToHtml(summary.markdown);
  renderSummaryPages(summary.available_pages || defaultSummaryPages());
  renderSummaryFeatured(summary.featured_briefings || []);
}

function updateSummaryButtons() {
  document.querySelectorAll("[data-summary-days]").forEach((button) => {
    button.classList.toggle("is-active", Number(button.getAttribute("data-summary-days")) === state.selectedSummaryDays);
  });
}

function renderPublicBriefingList(items) {
  if (!dom.publicBriefingList) {
    return;
  }
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
  if (dom.healthStatus) {
    dom.healthStatus.textContent = `${health.status} | ${bootstrap.supported_llm_kinds.length} provider types`;
  }
  if (dom.publicStatus) {
    dom.publicStatus.textContent = bootstrap.public_digest_enabled
      ? `Daily after ${bootstrap.public_digest_local_time} ${bootstrap.public_digest_timezone}`
      : "Disabled";
  }
}

async function loadPublicSummary(days = state.selectedSummaryDays, windowName = state.selectedSummaryWindow) {
  let summaryResponse;
  if (windowName) {
    state.selectedSummaryWindow = windowName;
    summaryResponse = await api(`/api/public/summaries/${windowName}`, {}, false);
    state.selectedSummaryDays = Number(summaryResponse.days) || Number(days) || 7;
  } else {
    state.selectedSummaryWindow = "";
    state.selectedSummaryDays = Number(days) || 7;
    summaryResponse = await api(`/api/public/summary?days=${state.selectedSummaryDays}`, {}, false);
  }
  state.publicSummary = summaryResponse;
  renderPublicSummary(summaryResponse);
  updateSummaryButtons();
  updateDocumentTitle();
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

function syncSummaryUrl(windowName) {
  const pageMode = detectPageMode();
  let nextPath = "/public-monitor";
  if (windowName) {
    nextPath = `/summaries/${windowName}`;
  } else if (pageMode === "home") {
    nextPath = "/";
  }
  if (window.location.pathname !== nextPath) {
    window.history.replaceState({}, "", nextPath);
  }
}

function updateDocumentTitle() {
  const pageMode = detectPageMode();
  const summaryWindow = extractSummaryWindowFromLocation();
  const briefingSlug = extractBriefingSlugFromLocation();
  if (briefingSlug && state.selectedPublicBriefing?.title) {
    document.title = `${state.selectedPublicBriefing.title} | Economic Research Platform`;
    return;
  }
  if (summaryWindow && state.publicSummary?.title) {
    document.title = `${state.publicSummary.title} | Economic Research Platform`;
    return;
  }
  if (pageMode === "public-monitor") {
    document.title = "Public Daily Monitor | Economic Research Platform";
    return;
  }
  document.title = "Economic Research Platform";
}

async function loadPublicData() {
  const requestedSlug = extractBriefingSlugFromLocation();
  state.selectedSummaryWindow = extractSummaryWindowFromLocation();
  const [latestResponse, listResponse, detailResponse] = await Promise.all([
    api("/api/public/briefings/latest", {}, false),
    api("/api/public/briefings?limit=12", {}, false),
    requestedSlug ? api(`/api/public/briefings/${requestedSlug}`, {}, false) : Promise.resolve({ briefing: null }),
  ]);
  state.publicBriefings = listResponse.items || [];
  const latest = detailResponse.briefing || latestResponse.briefing || state.publicBriefings[0] || null;
  renderPublicDateSwitcher(state.publicBriefings, latest?.slug || requestedSlug);
  renderPublicLatest(latest);
  if (requestedSlug && latest) {
    syncPublicUrl(latest);
  }
  await loadPublicSummary(state.selectedSummaryDays, state.selectedSummaryWindow);
  renderPublicBriefingList(state.publicBriefings);
  updateDocumentTitle();
}

async function loadSelectedAssetProfile(force = false) {
  ensureWorkspace();
  const assetId = dom.analysisAssetSelect?.value || state.selectedAnalysisAssetId;
  if (!assetId) {
    renderDataLabPlaceholders();
    return null;
  }
  state.selectedAnalysisAssetId = assetId;
  if (!force && state.assetProfiles[assetId]) {
    renderAssetProfile(state.assetProfiles[assetId]);
    return state.assetProfiles[assetId];
  }
  const profile = await api(`/api/workspaces/${state.selectedWorkspaceId}/assets/${assetId}/profile`);
  state.assetProfiles[assetId] = profile;
  renderAssetProfile(profile);
  return profile;
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
  if (state.selectedAnalysisAssetId) {
    try {
      await loadSelectedAssetProfile();
    } catch (error) {
      showToast(error.message || "Failed to load dataset profile.", true);
    }
  }
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
  state.assetProfiles = {};
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

async function handlePrepareSample(event) {
  event.preventDefault();
  ensureWorkspace();
  const assetId = dom.analysisAssetSelect?.value || state.selectedAnalysisAssetId;
  if (!assetId) {
    throw new Error("Select a dataset asset first.");
  }
  const payload = {
    asset_id: assetId,
    include_columns: getSelectedValues(dom.prepareKeepColumns),
    required_columns: getSelectedValues(dom.prepareRequiredColumns),
    numeric_columns: getSelectedValues(dom.prepareNumericColumns),
    binary_columns: getSelectedValues(dom.prepareBinaryColumns),
    date_columns: getSelectedValues(dom.prepareDateColumns),
    impute_columns: getSelectedValues(dom.prepareImputeColumns),
    impute_method: dom.prepareImputeMethod?.value || "none",
    winsorize_columns: getSelectedValues(dom.prepareWinsorizeColumns),
    winsor_lower_quantile: Number(dom.prepareWinsorLower?.value || 0.01),
    winsor_upper_quantile: Number(dom.prepareWinsorUpper?.value || 0.99),
    log_transform_columns: getSelectedValues(dom.prepareLogTransformColumns),
    standardize_columns: getSelectedValues(dom.prepareStandardizeColumns),
    outlier_columns: getSelectedValues(dom.prepareOutlierColumns),
    outlier_method: dom.prepareOutlierMethod?.value || "none",
    outlier_threshold: Number(dom.prepareOutlierThreshold?.value || 1.5),
    drop_duplicates: event.currentTarget.querySelector('[name=\"drop_duplicates\"]')?.checked ?? true,
    drop_missing_required:
      event.currentTarget.querySelector('[name=\"drop_missing_required\"]')?.checked ?? true,
  };
  const response = await api(`/api/workspaces/${state.selectedWorkspaceId}/analysis/prepare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  dom.prepareOutput.textContent = JSON.stringify(response, null, 2);
  state.assetProfiles = {};
  state.selectedAnalysisAssetId = response.asset.id;
  await refreshWorkspaceData();
  showToast("Prepared analysis sample created.");
}

async function handleModelRun(event) {
  event.preventDefault();
  ensureWorkspace();
  const assetId = dom.analysisAssetSelect?.value || state.selectedAnalysisAssetId;
  if (!assetId) {
    throw new Error("Select a dataset asset first.");
  }
  const modelType = dom.modelType?.value || "ols";
  const payload = {
    asset_id: assetId,
    model_type: modelType,
    dependent: dom.modelDependent?.value || "",
    independents: getSelectedValues(dom.modelIndependents),
    controls: getSelectedValues(dom.modelControls),
    treatment_column: dom.didTreatmentColumn?.value || "",
    post_column: dom.didPostColumn?.value || "",
    origin_mass_column: dom.gravityOriginMassColumn?.value || "",
    destination_mass_column: dom.gravityDestinationMassColumn?.value || "",
    distance_column: dom.gravityDistanceColumn?.value || "",
    entity_column: dom.panelEntityColumn?.value || "",
    time_column: dom.panelTimeColumn?.value || "",
    include_time_effects: dom.includeTimeEffects?.checked ?? false,
    endogenous_column: dom.ivEndogenousColumn?.value || "",
    instrument_columns: getSelectedValues(dom.ivInstrumentColumns),
    robust_covariance: dom.modelRobustCovariance?.checked ?? true,
  };
  const response = await api(`/api/workspaces/${state.selectedWorkspaceId}/analysis/models`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  dom.analysisOutput.textContent = JSON.stringify(response, null, 2);
  await refreshWorkspaceData();
  showToast(`${response.model_label || "Model"} completed.`);
}

async function renderPlotPreview(result) {
  if (!result?.asset?.id) {
    return;
  }
  revokeCurrentPlotUrl();
  const response = await fetch(`/api/assets/${result.asset.id}/download`, {
    headers: { Authorization: `Bearer ${state.token}` },
  });
  if (!response.ok) {
    throw new Error("Chart preview download failed.");
  }
  const blob = await response.blob();
  state.currentPlotUrl = URL.createObjectURL(blob);
  state.currentPlotAssetId = result.asset.id;
  if (dom.plotPreviewImage) {
    dom.plotPreviewImage.src = state.currentPlotUrl;
  }
  if (dom.plotPreviewMeta) {
    dom.plotPreviewMeta.textContent = result.summary || result.title || "Chart generated.";
  }
  dom.plotPreviewPanel?.classList.remove("hidden");
}

async function handlePlot(event) {
  event.preventDefault();
  ensureWorkspace();
  const assetId = dom.analysisAssetSelect?.value || state.selectedAnalysisAssetId;
  if (!assetId) {
    throw new Error("Select a dataset asset first.");
  }
  const formData = new FormData(event.currentTarget);
  const payload = {
    asset_id: assetId,
    chart_type: formData.get("chart_type"),
    x_column: formData.get("x_column"),
    y_columns: getSelectedValues(dom.plotYColumns),
    group_column: formData.get("group_column"),
    title: formData.get("title"),
  };
  const response = await api(`/api/workspaces/${state.selectedWorkspaceId}/analysis/plot`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await renderPlotPreview(response);
  await refreshWorkspaceData();
  showToast("Chart generated.");
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

function currentPublicShareTarget() {
  const summaryWindow = extractSummaryWindowFromLocation();
  if (summaryWindow && state.publicSummary?.share_url) {
    return state.publicSummary.share_url;
  }
  return state.selectedPublicBriefing?.share_url || window.location.href;
}

async function handleAssetActions(event) {
  const target = event.target.closest("[data-clean-asset], [data-download-asset], [data-select-asset]");
  if (!target) {
    return;
  }
  const cleanId = target.getAttribute("data-clean-asset");
  const downloadId = target.getAttribute("data-download-asset");
  const selectId = target.getAttribute("data-select-asset");
  if (selectId) {
    state.selectedAnalysisAssetId = selectId;
    if (dom.analysisAssetSelect) {
      dom.analysisAssetSelect.value = selectId;
    }
    await loadSelectedAssetProfile();
    showToast("Dataset loaded into Data Lab.");
    return;
  }
  if (cleanId) {
    await api(`/api/workspaces/${state.selectedWorkspaceId}/assets/${cleanId}/clean`, { method: "POST" });
    state.assetProfiles = {};
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
  const target = event.target.closest("[data-public-slug], [data-copy-public-url]");
  if (!target) {
    return;
  }
  const slug = target.getAttribute("data-public-slug");
  const publicUrl = target.getAttribute("data-copy-public-url");
  if (publicUrl) {
    await copyToClipboard(publicUrl);
    showToast("Public link copied.");
    return;
  }
  if (!slug) {
    return;
  }
  const response = await api(`/api/public/briefings/${slug}`, {}, false);
  if (response.briefing) {
    renderPublicLatest(response.briefing);
    syncPublicUrl(response.briefing);
    updateDocumentTitle();
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
  const registerForm = document.getElementById("register-form");
  const loginForm = document.getElementById("login-form");
  const workspaceForm = document.getElementById("workspace-form");
  const integrationForm = document.getElementById("integration-form");
  const briefingForm = document.getElementById("briefing-form");
  const openalexForm = document.getElementById("openalex-form");
  const importOpenalexButton = document.getElementById("import-openalex");
  const uploadForm = document.getElementById("upload-form");
  const knowledgeForm = document.getElementById("knowledge-form");
  const scheduleForm = document.getElementById("schedule-form");
  const prepareForm = document.getElementById("prepare-form");
  const modelForm = document.getElementById("model-form");
  const plotForm = document.getElementById("plot-form");

  registerForm?.addEventListener("submit", wrap(handleRegister));
  loginForm?.addEventListener("submit", wrap(handleLogin));
  workspaceForm?.addEventListener("submit", wrap(handleCreateWorkspace));
  integrationForm?.addEventListener("submit", wrap(handleIntegration));
  briefingForm?.addEventListener("submit", wrap(handleBriefing));
  openalexForm?.addEventListener("submit", wrap(handleOpenAlexSearch));
  importOpenalexButton?.addEventListener("click", wrap(handleOpenAlexImport));
  uploadForm?.addEventListener("submit", wrap(handleUpload));
  knowledgeForm?.addEventListener("submit", wrap(handleKnowledge));
  scheduleForm?.addEventListener("submit", wrap(handleSchedule));
  prepareForm?.addEventListener("submit", wrap(handlePrepareSample));
  modelForm?.addEventListener("submit", wrap(handleModelRun));
  plotForm?.addEventListener("submit", wrap(handlePlot));

  dom.refreshPublicButton?.addEventListener("click", wrap(async () => {
    await loadPublicData();
    showToast("Public feed refreshed.");
  }));
  dom.copyPublicLinkButton?.addEventListener("click", wrap(async () => {
    const target = currentPublicShareTarget();
    if (!target) {
      throw new Error("No public briefing selected.");
    }
    await copyToClipboard(target);
    showToast("Public link copied.");
  }));
  document.querySelectorAll("[data-summary-days]").forEach((button) => {
    button.addEventListener(
      "click",
      wrap(async () => {
        const days = Number(button.getAttribute("data-summary-days"));
        const nextWindow = days === 7 ? "weekly" : days === 30 ? "monthly" : "";
        if (nextWindow) {
          syncSummaryUrl(nextWindow);
        } else {
          syncSummaryUrl("");
        }
        await loadPublicSummary(days, nextWindow);
        showToast(`Loaded ${button.getAttribute("data-summary-days")}-day summary.`);
      }),
    );
  });
  dom.workspaceSelect?.addEventListener(
    "change",
    wrap(async (event) => {
      state.selectedWorkspaceId = event.target.value;
      localStorage.setItem(storageKeys.workspaceId, state.selectedWorkspaceId);
      state.assetProfiles = {};
      state.selectedAnalysisAssetId = "";
      await refreshWorkspaceData();
    }),
  );
  dom.analysisAssetSelect?.addEventListener("change", wrap(async (event) => {
    state.selectedAnalysisAssetId = event.target.value;
    await loadSelectedAssetProfile();
  }));
  dom.refreshAssetProfileButton?.addEventListener("click", wrap(async () => {
    await loadSelectedAssetProfile(true);
    showToast("Dataset profile refreshed.");
  }));
  dom.modelType?.addEventListener("change", () => updateModelFieldVisibility());
  dom.downloadPlotButton?.addEventListener("click", wrap(async () => {
    if (!state.currentPlotAssetId) {
      throw new Error("Generate a chart first.");
    }
    await downloadAsset(state.currentPlotAssetId);
    showToast("Chart download started.");
  }));
  dom.integrationList?.addEventListener("click", wrap(handleIntegrationActions));
  dom.assetList?.addEventListener("click", wrap(handleAssetActions));
  dom.publicDateSwitcher?.addEventListener("click", wrap(handlePublicActions));
  dom.publicBriefingList?.addEventListener("click", wrap(handlePublicActions));
  dom.publicSummaryFeatured?.addEventListener("click", wrap(handlePublicActions));
  updateModelFieldVisibility();
}

async function init() {
  bind();
  try {
    await fetchHealth();
    if (hasPublicMonitorUI()) {
      await loadPublicData();
    }
    if (hasPrivateWorkspaceUI()) {
      clearPrivateLists();
      renderSession();
      renderWorkspaceOptions();
      await loadSession();
    }
  } catch (error) {
    showToast(error.message || "Initialization failed.", true);
  }
}

init();
