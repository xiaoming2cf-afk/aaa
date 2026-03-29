const storageKeys = {
  token: "erp.session.token",
  workspaceId: "erp.workspace.id",
};

const state = {
  token: localStorage.getItem(storageKeys.token) || "",
  user: null,
  workspaces: [],
  selectedWorkspaceId: localStorage.getItem(storageKeys.workspaceId) || "",
  workspaceAssets: [],
  workspaceKnowledge: [],
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
  dataLabCatalog: null,
  variableGuideResult: null,
  resultPreviewUrls: [],
};

const MODEL_FAMILY_OPTIONS = {
  econometrics_baseline: [
    { value: "ols", label: "OLS" },
    { value: "ppml", label: "PPML" },
    { value: "logit", label: "Logit" },
    { value: "probit", label: "Probit" },
    { value: "did", label: "Difference-in-Differences" },
    { value: "event_study", label: "Event Study" },
    { value: "rdd", label: "Regression Discontinuity" },
    { value: "fixed_effects", label: "Fixed Effects" },
    { value: "gravity", label: "Gravity Model" },
    { value: "iv_2sls", label: "IV-2SLS" },
    { value: "panel_iv", label: "Panel IV" },
  ],
  time_series_finance: [
    { value: "arima", label: "ARIMA Forecast" },
    { value: "arch", label: "ARCH" },
    { value: "garch", label: "GARCH" },
    { value: "var", label: "Vector Autoregression" },
    { value: "svar_irf", label: "SVAR.IRF" },
    { value: "virf", label: "VIRF" },
    { value: "dy_connectedness", label: "DY Connectedness" },
    { value: "bk_connectedness", label: "BK Connectedness" },
  ],
  corporate_finance: [
    { value: "altman_z", label: "Altman Z-Score" },
    { value: "dupont", label: "DuPont Analysis" },
  ],
  risk_management: [
    { value: "historical_var", label: "Historical VaR / ES" },
    { value: "parametric_var", label: "Parametric VaR / ES" },
    { value: "ewma_volatility", label: "EWMA Volatility" },
  ],
  derivatives_pricing: [
    { value: "black_scholes", label: "Black-Scholes" },
    { value: "binomial_option", label: "Binomial Option Pricing" },
  ],
  macro_finance_dsge: [
    { value: "taylor_rule", label: "Taylor Rule" },
    { value: "rbc_dsge", label: "Toy RBC / DSGE" },
  ],
  portfolio_allocation: [
    { value: "mean_variance", label: "Mean-Variance Portfolio" },
    { value: "minimum_variance", label: "Minimum Variance Portfolio" },
    { value: "risk_parity", label: "Risk Parity Portfolio" },
  ],
  asset_pricing: [
    { value: "capm", label: "CAPM" },
    { value: "fama_french_3", label: "Fama-French 3-Factor" },
  ],
};

const MODEL_CONFIG = {
  ols: { dependentKind: "numeric", independents: true, controls: true, robust: true },
  ppml: { dependentKind: "numeric", independents: true, controls: true, robust: true },
  logit: { dependentKind: "binary", independents: true, controls: true, robust: true },
  probit: { dependentKind: "binary", independents: true, controls: true, robust: true },
  did: { dependentKind: "numeric", controls: true, did: true, robust: true },
  event_study: { dependentKind: "numeric", controls: true, eventStudy: true, fe: true, robust: true },
  rdd: { dependentKind: "numeric", controls: true, rdd: true, robust: true },
  fixed_effects: { dependentKind: "numeric", independents: true, controls: true, fe: true, robust: true },
  gravity: { dependentKind: "numeric", controls: true, gravity: true, robust: true, dependentLabel: "Outcome / flow variable" },
  iv_2sls: { dependentKind: "numeric", independents: true, controls: true, iv: true, robust: true },
  panel_iv: { dependentKind: "numeric", independents: true, controls: true, fe: true, iv: true, robust: true },
  arima: { dependentKind: "numeric", timeColumn: true, forecast: true, arima: true },
  arch: { dependentKind: "numeric", timeColumn: true, forecast: true, garch: true },
  garch: { dependentKind: "numeric", timeColumn: true, forecast: true, garch: true },
  var: { series: true, timeColumn: true, forecast: true, var: true },
  svar_irf: { series: true, timeColumn: true, irf: true, var: true },
  virf: { dependentKind: "numeric", timeColumn: true, garch: true, irf: true },
  dy_connectedness: { series: true, timeColumn: true, var: true, irf: true },
  bk_connectedness: { series: true, timeColumn: true, var: true, irf: true, bk: true },
  historical_var: { dependentKind: "numeric", timeColumn: true, risk: true },
  parametric_var: { dependentKind: "numeric", timeColumn: true, risk: true },
  ewma_volatility: { dependentKind: "numeric", timeColumn: true, risk: true },
  altman_z: { corporateAltman: true },
  dupont: { corporateDupont: true },
  black_scholes: { derivative: true },
  binomial_option: { derivative: true },
  taylor_rule: { dependentKind: "numeric", controls: true, macroTaylor: true, robust: true },
  rbc_dsge: { dsge: true },
  mean_variance: { series: true, portfolio: true },
  minimum_variance: { series: true, portfolio: true },
  risk_parity: { series: true, portfolio: true },
  capm: { dependentKind: "numeric", assetPricing: true, robust: true, dependentLabel: "Asset return series" },
  fama_french_3: { dependentKind: "numeric", assetPricing: true, ff3: true, robust: true, dependentLabel: "Asset return series" },
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
  labWorkflowType: document.getElementById("lab-workflow-type"),
  processingFamilyWrap: document.getElementById("processing-family-wrap"),
  processingFamily: document.getElementById("processing-family"),
  modelFamilyWrap: document.getElementById("model-family-wrap"),
  modelFamily: document.getElementById("model-family"),
  labStepAccess: document.getElementById("lab-step-access"),
  labStepAccessText: document.getElementById("lab-step-access-text"),
  labStepDataset: document.getElementById("lab-step-dataset"),
  labStepDatasetText: document.getElementById("lab-step-dataset-text"),
  labStepWorkflow: document.getElementById("lab-step-workflow"),
  labStepWorkflowText: document.getElementById("lab-step-workflow-text"),
  labStepOutput: document.getElementById("lab-step-output"),
  labStepOutputText: document.getElementById("lab-step-output-text"),
  labContextAccess: document.getElementById("lab-context-access"),
  labContextWorkspace: document.getElementById("lab-context-workspace"),
  labContextDataset: document.getElementById("lab-context-dataset"),
  labContextWorkflow: document.getElementById("lab-context-workflow"),
  labContextFamily: document.getElementById("lab-context-family"),
  labContextModel: document.getElementById("lab-context-model"),
  labContextNextAction: document.getElementById("lab-context-next-action"),
  labContextDetailLink: document.getElementById("lab-context-detail-link"),
  labActiveFamilyEyebrow: document.getElementById("lab-active-family-eyebrow"),
  labActiveFamilyTitle: document.getElementById("lab-active-family-title"),
  labActiveFamilySummary: document.getElementById("lab-active-family-summary"),
  labActiveFamilyMethods: document.getElementById("lab-active-family-methods"),
  labActiveFamilyChecks: document.getElementById("lab-active-family-checks"),
  labActiveFamilyLink: document.getElementById("lab-active-family-link"),
  labRecentProcessingList: document.getElementById("lab-recent-processing-list"),
  labRecentModelList: document.getElementById("lab-recent-model-list"),
  variableGuideForm: document.getElementById("variable-guide-form"),
  variableGuidePrompt: document.getElementById("variable-guide-prompt"),
  variableGuideMeta: document.getElementById("variable-guide-meta"),
  variableGuideSummary: document.getElementById("variable-guide-summary"),
  variableGuideRoles: document.getElementById("variable-guide-roles"),
  variableGuideChecks: document.getElementById("variable-guide-checks"),
  variableGuideApply: document.getElementById("variable-guide-apply"),
  variableGuideRaw: document.getElementById("variable-guide-raw"),
  prepareForm: document.getElementById("prepare-form"),
  prepareCoreFields: document.getElementById("prepare-core-fields"),
  prepareCleaningFields: document.getElementById("prepare-cleaning-fields"),
  prepareTimeSeriesFields: document.getElementById("prepare-time-series-fields"),
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
  prepareMinmaxScaleColumns: document.getElementById("prepare-minmax-scale-columns"),
  prepareOutlierColumns: document.getElementById("prepare-outlier-columns"),
  prepareOutlierMethod: document.getElementById("prepare-outlier-method"),
  prepareOutlierThreshold: document.getElementById("prepare-outlier-threshold"),
  prepareSortColumn: document.getElementById("prepare-sort-column"),
  prepareTimeGroupColumn: document.getElementById("prepare-time-group-column"),
  prepareDifferenceColumns: document.getElementById("prepare-difference-columns"),
  prepareReturnColumns: document.getElementById("prepare-return-columns"),
  prepareReturnMethod: document.getElementById("prepare-return-method"),
  prepareLagColumns: document.getElementById("prepare-lag-columns"),
  prepareLagPeriods: document.getElementById("prepare-lag-periods"),
  prepareLeadColumns: document.getElementById("prepare-lead-columns"),
  prepareLeadPeriods: document.getElementById("prepare-lead-periods"),
  prepareRollingMeanColumns: document.getElementById("prepare-rolling-mean-columns"),
  prepareRollingVolatilityColumns: document.getElementById("prepare-rolling-volatility-columns"),
  prepareRollingWindow: document.getElementById("prepare-rolling-window"),
  prepareOutput: document.getElementById("prepare-output"),
  modelForm: document.getElementById("model-form"),
  modelType: document.getElementById("model-type"),
  modelDependent: document.getElementById("model-dependent"),
  modelIndependents: document.getElementById("model-independents"),
  modelControls: document.getElementById("model-controls"),
  modelRobustCovariance: document.getElementById("model-robust-covariance"),
  seriesModelFields: document.getElementById("series-model-fields"),
  modelSeriesColumns: document.getElementById("model-series-columns"),
  timeSeriesModelFields: document.getElementById("time-series-model-fields"),
  modelTimeColumn: document.getElementById("model-time-column"),
  forecastSteps: document.getElementById("forecast-steps"),
  arimaFields: document.getElementById("arima-fields"),
  arimaP: document.getElementById("arima-p"),
  arimaD: document.getElementById("arima-d"),
  arimaQ: document.getElementById("arima-q"),
  varFields: document.getElementById("var-fields"),
  varLags: document.getElementById("var-lags"),
  garchFields: document.getElementById("garch-fields"),
  garchP: document.getElementById("garch-p"),
  garchQ: document.getElementById("garch-q"),
  virfShockSize: document.getElementById("virf-shock-size"),
  irfFields: document.getElementById("irf-fields"),
  irfHorizon: document.getElementById("irf-horizon"),
  impulseColumn: document.getElementById("impulse-column"),
  responseColumn: document.getElementById("response-column"),
  bkFields: document.getElementById("bk-fields"),
  bkShortHorizon: document.getElementById("bk-short-horizon"),
  bkMediumHorizon: document.getElementById("bk-medium-horizon"),
  didFields: document.getElementById("did-fields"),
  didTreatmentColumn: document.getElementById("did-treatment-column"),
  didPostColumn: document.getElementById("did-post-column"),
  eventStudyFields: document.getElementById("event-study-fields"),
  eventStudyWindowFields: document.getElementById("event-study-window-fields"),
  eventTreatmentColumn: document.getElementById("event-treatment-column"),
  eventTimeColumn: document.getElementById("event-time-column"),
  eventLeadWindow: document.getElementById("event-lead-window"),
  eventLagWindow: document.getElementById("event-lag-window"),
  eventOmittedPeriod: document.getElementById("event-omitted-period"),
  rddFields: document.getElementById("rdd-fields"),
  rddConfigFields: document.getElementById("rdd-config-fields"),
  rddRunningColumn: document.getElementById("rdd-running-column"),
  rddCutoff: document.getElementById("rdd-cutoff"),
  rddBandwidth: document.getElementById("rdd-bandwidth"),
  rddPolynomialOrder: document.getElementById("rdd-polynomial-order"),
  rddTreatAboveCutoff: document.getElementById("rdd-treat-above-cutoff"),
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
  riskFields: document.getElementById("risk-fields"),
  confidenceLevel: document.getElementById("confidence-level"),
  holdingPeriodDays: document.getElementById("holding-period-days"),
  ewmaLambda: document.getElementById("ewma-lambda"),
  corporateAltmanFields: document.getElementById("corporate-altman-fields"),
  corporateAltmanFields2: document.getElementById("corporate-altman-fields-2"),
  corporateDupontFields: document.getElementById("corporate-dupont-fields"),
  workingCapitalColumn: document.getElementById("working-capital-column"),
  retainedEarningsColumn: document.getElementById("retained-earnings-column"),
  ebitColumn: document.getElementById("ebit-column"),
  marketEquityColumn: document.getElementById("market-equity-column"),
  totalAssetsColumn: document.getElementById("total-assets-column"),
  totalLiabilitiesColumn: document.getElementById("total-liabilities-column"),
  salesColumn: document.getElementById("sales-column"),
  netIncomeColumn: document.getElementById("net-income-column"),
  revenueColumn: document.getElementById("revenue-column"),
  equityColumn: document.getElementById("equity-column"),
  derivativeFields: document.getElementById("derivative-fields"),
  derivativeFields2: document.getElementById("derivative-fields-2"),
  spotColumn: document.getElementById("spot-column"),
  strikeColumn: document.getElementById("strike-column"),
  maturityColumn: document.getElementById("maturity-column"),
  rateColumn: document.getElementById("rate-column"),
  volatilityColumn: document.getElementById("volatility-column"),
  optionType: document.getElementById("option-type"),
  optionSteps: document.getElementById("option-steps"),
  macroTaylorFields: document.getElementById("macro-taylor-fields"),
  inflationGapColumn: document.getElementById("inflation-gap-column"),
  outputGapColumn: document.getElementById("output-gap-column"),
  dsgeFields: document.getElementById("dsge-fields"),
  dsgeFields2: document.getElementById("dsge-fields-2"),
  dsgeAlpha: document.getElementById("dsge-alpha"),
  dsgeBeta: document.getElementById("dsge-beta"),
  dsgeDelta: document.getElementById("dsge-delta"),
  dsgeProductivity: document.getElementById("dsge-productivity"),
  dsgeLabor: document.getElementById("dsge-labor"),
  dsgeShockPersistence: document.getElementById("dsge-shock-persistence"),
  dsgeShockSize: document.getElementById("dsge-shock-size"),
  dsgeImpulseHorizon: document.getElementById("dsge-impulse-horizon"),
  portfolioFields: document.getElementById("portfolio-fields"),
  portfolioRiskAversion: document.getElementById("portfolio-risk-aversion"),
  portfolioLongOnly: document.getElementById("portfolio-long-only"),
  assetPricingFields: document.getElementById("asset-pricing-fields"),
  ff3Fields: document.getElementById("ff3-fields"),
  marketColumn: document.getElementById("market-column"),
  riskFreeColumn: document.getElementById("risk-free-column"),
  smbColumn: document.getElementById("smb-column"),
  hmlColumn: document.getElementById("hml-column"),
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
  prepareResultMeta: document.getElementById("prepare-result-meta"),
  prepareResultSummary: document.getElementById("prepare-result-summary"),
  prepareResultLink: document.getElementById("prepare-result-link"),
  analysisOutput: document.getElementById("analysis-output"),
  analysisResultMeta: document.getElementById("analysis-result-meta"),
  analysisResultSummary: document.getElementById("analysis-result-summary"),
  analysisResultLink: document.getElementById("analysis-result-link"),
  labDetailEyebrow: document.getElementById("lab-detail-eyebrow"),
  labDetailTitle: document.getElementById("lab-detail-title"),
  labDetailSummary: document.getElementById("lab-detail-summary"),
  labDetailCategory: document.getElementById("lab-detail-category"),
  labDetailHeading: document.getElementById("lab-detail-heading"),
  labDetailDescription: document.getElementById("lab-detail-description"),
  labDetailWorkbenchLink: document.getElementById("lab-detail-workbench-link"),
  labDetailMethodList: document.getElementById("lab-detail-method-list"),
  labDetailInputList: document.getElementById("lab-detail-input-list"),
  labDetailAuditList: document.getElementById("lab-detail-audit-list"),
  labResultEyebrow: document.getElementById("lab-result-eyebrow"),
  labResultTitle: document.getElementById("lab-result-title"),
  labResultSummary: document.getElementById("lab-result-summary"),
  labResultType: document.getElementById("lab-result-type"),
  labResultHeading: document.getElementById("lab-result-heading"),
  labResultDescription: document.getElementById("lab-result-description"),
  labResultWorkbenchLink: document.getElementById("lab-result-workbench-link"),
  labResultMetrics: document.getElementById("lab-result-metrics"),
  labResultSpecification: document.getElementById("lab-result-specification"),
  labResultTables: document.getElementById("lab-result-tables"),
  labResultAudit: document.getElementById("lab-result-audit"),
  labResultPreview: document.getElementById("lab-result-preview"),
  labResultRaw: document.getElementById("lab-result-raw"),
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

function extractDataLabMethodRoute() {
  const match = window.location.pathname.match(/^\/data-lab\/(processing|models)\/([^/]+)$/);
  if (!match) {
    return null;
  }
  return {
    category: decodeURIComponent(match[1]),
    family: decodeURIComponent(match[2]),
  };
}

function extractDataLabResultRoute() {
  const match = window.location.pathname.match(/^\/data-lab\/results\/(processing|models)\/([^/]+)$/);
  if (!match) {
    return null;
  }
  return {
    category: decodeURIComponent(match[1]),
    id: decodeURIComponent(match[2]),
  };
}

function detectPageMode() {
  if (window.location.pathname === "/") {
    return "home";
  }
  if (window.location.pathname === "/data-lab") {
    return "data-lab";
  }
  if (extractDataLabMethodRoute()) {
    return "data-lab-method-detail";
  }
  if (extractDataLabResultRoute()) {
    return "data-lab-result-detail";
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

function detailPathToAbsolute(path) {
  if (!path) {
    return "";
  }
  try {
    return new URL(path, window.location.origin).pathname + new URL(path, window.location.origin).search + new URL(path, window.location.origin).hash;
  } catch {
    return path;
  }
}

function dataLabQueryValue(key) {
  return new URLSearchParams(window.location.search).get(key) || "";
}

async function loadDataLabCatalog() {
  if (state.dataLabCatalog) {
    return state.dataLabCatalog;
  }
  const payload = await api("/api/data-lab/catalog", {}, false);
  state.dataLabCatalog = payload;
  return payload;
}

async function ensureAuthenticatedUser() {
  if (!state.token) {
    throw new Error("Sign in on the standalone Data Lab page before opening private result details.");
  }
  if (state.user) {
    return state.user;
  }
  const payload = await api("/api/auth/me");
  state.user = payload.user;
  state.workspaces = payload.workspaces || [];
  return state.user;
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

function renderListCards(target, items, formatter) {
  if (!target) {
    return;
  }
  if (!items || !items.length) {
    target.innerHTML = emptyCard("No items available.");
    return;
  }
  target.innerHTML = items.map(formatter).join("");
}

function resultMetricCards(result) {
  const metrics = [];
  if (result.model_label) {
    metrics.push({ label: "Model", value: result.model_label });
  }
  if (result.processing_family) {
    metrics.push({ label: "Processing family", value: result.processing_family });
  }
  if (result.observations !== undefined && result.observations !== null) {
    metrics.push({ label: "Observations", value: String(result.observations) });
  }
  if (result.r_squared !== undefined && result.r_squared !== null) {
    metrics.push({ label: "R-squared", value: Number(result.r_squared).toFixed(4) });
  }
  if (result.pseudo_r_squared !== undefined && result.pseudo_r_squared !== null) {
    metrics.push({ label: "Pseudo R-squared", value: Number(result.pseudo_r_squared).toFixed(4) });
  }
  if (result.aic !== undefined && result.aic !== null) {
    metrics.push({ label: "AIC", value: Number(result.aic).toFixed(4) });
  }
  if (result.bic !== undefined && result.bic !== null) {
    metrics.push({ label: "BIC", value: Number(result.bic).toFixed(4) });
  }
  Object.entries(result.metrics || {}).forEach(([key, value]) => {
    if (value === null || value === undefined || typeof value === "object") {
      return;
    }
    metrics.push({ label: key, value: String(value) });
  });
  return metrics;
}

function renderResultSummaryCard(target, payload, { type }) {
  if (!target) {
    return;
  }
  const metrics = resultMetricCards(payload);
  const detailPath = payload.result_detail_path || "";
  const narrative = (payload.narrative || []).slice(0, 4);
  target.innerHTML = `
    <article class="card">
      <h4>${escapeHtml(payload.model_label || payload.processing_family || (type === "model" ? "Model result" : "Processing result"))}</h4>
      <div class="chip-row chip-row-compact">
        ${metrics.map((item) => `<span class="topic-chip">${escapeHtml(item.label)} <strong>${escapeHtml(item.value)}</strong></span>`).join("")}
      </div>
      <div>${narrative.length ? narrative.map((line) => `<p>${escapeHtml(line)}</p>`).join("") : `<p>${escapeHtml(payload.summary?.rows_after_prepare ? `Rows after prepare: ${payload.summary.rows_after_prepare}` : "Result is ready.")}</p>`}</div>
      <div class="actions">
        ${detailPath ? `<a href="${escapeHtml(detailPath)}" class="button-link secondary-link">Open detail page</a>` : ""}
      </div>
    </article>
  `;
}

function renderProcessingResultSummary(payload) {
  if (dom.prepareResultMeta) {
    dom.prepareResultMeta.textContent = `${payload.processing_family || "data_processing"} | asset ${payload.asset?.title || "prepared sample"}`;
  }
  renderResultSummaryCard(dom.prepareResultSummary, payload, { type: "processing" });
  if (dom.prepareResultLink) {
    const href = payload.result_detail_path || "";
    dom.prepareResultLink.href = href || "#";
    dom.prepareResultLink.classList.toggle("hidden", !href);
  }
}

function renderModelResultSummary(payload) {
  if (dom.analysisResultMeta) {
    dom.analysisResultMeta.textContent = `${payload.model_label || payload.model_type || "model"} | ${payload.asset?.title || "dataset"}`;
  }
  renderResultSummaryCard(dom.analysisResultSummary, payload, { type: "model" });
  if (dom.analysisResultLink) {
    const href = payload.result_detail_path || "";
    dom.analysisResultLink.href = href || "#";
    dom.analysisResultLink.classList.toggle("hidden", !href);
  }
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

function toggleHidden(element, hidden) {
  if (!element) {
    return;
  }
  element.classList.toggle("hidden", hidden);
}

function closestWrap(element, selector = ".stack.compact") {
  return element?.closest(selector) || null;
}

function currentWorkflowType() {
  return dom.labWorkflowType?.value || "data_processing";
}

function currentProcessingFamily() {
  return dom.processingFamily?.value || "sample_preparation";
}

function currentModelFamily() {
  return dom.modelFamily?.value || "econometrics_baseline";
}

function currentWorkflowLabel() {
  return currentWorkflowType() === "model" ? "Model" : "Data Processing";
}

function selectedDatasetAsset() {
  const assetId = dom.analysisAssetSelect?.value || state.selectedAnalysisAssetId || "";
  return (state.workspaceAssets || []).find((item) => item.id === assetId) || null;
}

function currentFamilyDetail() {
  if (!state.dataLabCatalog) {
    return null;
  }
  const collection = currentWorkflowType() === "model"
    ? state.dataLabCatalog.model_families || []
    : state.dataLabCatalog.processing_families || [];
  const slug = currentWorkflowType() === "model" ? currentModelFamily() : currentProcessingFamily();
  return collection.find((item) => item.slug === slug) || null;
}

function currentFamilyDetailPath() {
  const detail = currentFamilyDetail();
  if (detail?.slug) {
    return detail.category === "model" ? `/data-lab/models/${detail.slug}` : `/data-lab/processing/${detail.slug}`;
  }
  return currentWorkflowType() === "model" ? `/data-lab/models/${currentModelFamily()}` : `/data-lab/processing/${currentProcessingFamily()}`;
}

function currentModelLabel() {
  const modelType = dom.modelType?.value || "";
  const options = MODEL_FAMILY_OPTIONS[currentModelFamily()] || [];
  return options.find((item) => item.value === modelType)?.label || (modelType ? modelType.replaceAll("_", " ") : "Not applicable");
}

function processingHistoryItems() {
  return [...(state.workspaceAssets || [])]
    .filter((item) => item.metadata?.processing_result || item.metadata?.analysis_kind === "plot")
    .sort((left, right) => new Date(right.updated_at || right.created_at || 0) - new Date(left.updated_at || left.created_at || 0));
}

function modelHistoryItems() {
  return [...(state.workspaceKnowledge || [])]
    .filter((item) => item.metadata?.model_type || item.metadata?.workflow_type === "model")
    .sort((left, right) => new Date(right.updated_at || right.created_at || 0) - new Date(left.updated_at || left.created_at || 0));
}

function truncateText(value, maxLength = 160) {
  const text = (value || "").toString().trim();
  if (!text) {
    return "";
  }
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
}

function setWorkflowStep(card, textNode, stateName, copy) {
  if (!card || !textNode) {
    return;
  }
  card.classList.remove("is-complete", "is-active");
  if (stateName === "complete") {
    card.classList.add("is-complete");
  }
  if (stateName === "active") {
    card.classList.add("is-active");
  }
  textNode.textContent = copy;
}

function renderWorkflowGuide() {
  const hasAccess = Boolean(state.user && state.selectedWorkspaceId);
  const hasDataset = Boolean(selectedDatasetAsset());
  const hasProfile = Boolean(currentAssetProfile());
  const workflowLabel = currentWorkflowLabel();
  const processingRuns = processingHistoryItems();
  const modelRuns = modelHistoryItems();
  const hasOutput = currentWorkflowType() === "model" ? Boolean(modelRuns.length) : Boolean(processingRuns.length);

  setWorkflowStep(
    dom.labStepAccess,
    dom.labStepAccessText,
    hasAccess ? "complete" : "active",
    hasAccess
      ? `Workspace access is ready through ${state.workspaces.find((item) => item.id === state.selectedWorkspaceId)?.name || "the selected workspace"}.`
      : "Sign in and select a workspace to unlock private datasets, models, and downloads.",
  );
  setWorkflowStep(
    dom.labStepDataset,
    dom.labStepDatasetText,
    hasDataset && hasProfile ? "complete" : hasAccess ? "active" : "pending",
    hasDataset && hasProfile
      ? `Dataset profile loaded for ${selectedDatasetAsset()?.title || "the selected asset"}, including columns and preview rows.`
      : hasDataset
        ? "A dataset is selected; load its profile to populate variables and preview rows."
        : "Upload or select a dataset, then load its profile before running anything.",
  );
  setWorkflowStep(
    dom.labStepWorkflow,
    dom.labStepWorkflowText,
    hasDataset && hasProfile ? "active" : "pending",
    `${workflowLabel} is selected with ${currentFamilyDetail()?.title || (currentWorkflowType() === "model" ? currentModelFamily() : currentProcessingFamily())}. Confirm the family and method before execution.`,
  );
  setWorkflowStep(
    dom.labStepOutput,
    dom.labStepOutputText,
    hasOutput ? "complete" : hasDataset && hasProfile ? "active" : "pending",
    hasOutput
      ? `Recent ${currentWorkflowType() === "model" ? "model" : "processing"} outputs are available below for download and manual verification.`
      : "Open the result detail page, inspect the audit trail, and download samples or charts after the run completes.",
  );
}

function renderActiveFamilySummary() {
  const detail = currentFamilyDetail();
  if (!dom.labActiveFamilyTitle || !dom.labActiveFamilySummary) {
    return;
  }
  if (!detail) {
    dom.labActiveFamilyEyebrow && (dom.labActiveFamilyEyebrow.textContent = currentWorkflowType() === "model" ? "Model Family" : "Data Processing Family");
    dom.labActiveFamilyTitle.textContent = currentWorkflowType() === "model" ? "Model family" : "Processing family";
    dom.labActiveFamilySummary.textContent = "Catalog metadata will appear here after the family index finishes loading.";
    dom.labActiveFamilyMethods && (dom.labActiveFamilyMethods.innerHTML = "");
    dom.labActiveFamilyChecks && (dom.labActiveFamilyChecks.innerHTML = emptyCard("No audit checklist available yet."));
    if (dom.labActiveFamilyLink) {
      dom.labActiveFamilyLink.href = currentFamilyDetailPath();
    }
    return;
  }
  dom.labActiveFamilyEyebrow && (dom.labActiveFamilyEyebrow.textContent = detail.category === "model" ? "Model Family" : "Data Processing Family");
  dom.labActiveFamilyTitle.textContent = detail.title || "Family";
  dom.labActiveFamilySummary.textContent = detail.summary || detail.description || "";
  if (dom.labActiveFamilyMethods) {
    dom.labActiveFamilyMethods.innerHTML = (detail.methods || [])
      .slice(0, 5)
      .map((item) => `<span class="topic-chip">${escapeHtml(item.name || item.slug || "Method")}</span>`)
      .join("");
  }
  renderListCards(dom.labActiveFamilyChecks, (detail.manual_checks || []).slice(0, 3), (item) => `
    <article class="card">
      <p>${escapeHtml(item)}</p>
    </article>
  `);
  if (dom.labActiveFamilyLink) {
    dom.labActiveFamilyLink.href = currentFamilyDetailPath();
  }
}

function nextLabAction() {
  if (!state.user) {
    return "Next action: sign in or create an account.";
  }
  if (!state.selectedWorkspaceId) {
    return "Next action: create or select a workspace.";
  }
  if (!selectedDatasetAsset()) {
    return "Next action: upload or select a dataset asset.";
  }
  if (!currentAssetProfile()) {
    return "Next action: load the dataset profile to populate variables and preview rows.";
  }
  if (currentWorkflowType() === "data_processing") {
    return currentProcessingFamily() === "visualization"
      ? "Next action: configure the chart fields and generate a PNG preview."
      : "Next action: configure the preparation fields and create an analysis-ready sample.";
  }
  return `Next action: confirm variables for ${currentModelLabel()} and run the model.`;
}

function renderLabContext() {
  const workspace = state.workspaces.find((item) => item.id === state.selectedWorkspaceId) || null;
  const dataset = selectedDatasetAsset();
  const profile = currentAssetProfile();
  const family = currentFamilyDetail();

  dom.labContextAccess && (dom.labContextAccess.textContent = state.user ? "Signed in" : "Signed out");
  dom.labContextWorkspace && (dom.labContextWorkspace.textContent = workspace?.name || "No workspace selected");
  dom.labContextDataset &&
    (dom.labContextDataset.textContent = dataset ? `${dataset.title} | ${dataset.kind}${profile ? ` | ${profile.rows} rows` : ""}` : "No dataset selected");
  dom.labContextWorkflow && (dom.labContextWorkflow.textContent = currentWorkflowLabel());
  dom.labContextFamily && (dom.labContextFamily.textContent = family?.title || (currentWorkflowType() === "model" ? currentModelFamily() : currentProcessingFamily()));
  dom.labContextModel &&
    (dom.labContextModel.textContent = currentWorkflowType() === "model" ? currentModelLabel() : "Not applicable for data processing");
  dom.labContextNextAction && (dom.labContextNextAction.textContent = nextLabAction());
  if (dom.labContextDetailLink) {
    dom.labContextDetailLink.href = currentFamilyDetailPath();
  }
  renderWorkflowGuide();
  renderActiveFamilySummary();
}

function renderProcessingHistory(items = processingHistoryItems()) {
  if (!dom.labRecentProcessingList) {
    return;
  }
  if (!items.length) {
    dom.labRecentProcessingList.innerHTML = emptyCard("No processing history yet.");
    return;
  }
  dom.labRecentProcessingList.innerHTML = items.slice(0, 6).map((item) => {
    const processing = item.metadata?.processing_result || null;
    const isPlot = item.metadata?.analysis_kind === "plot";
    const family = processing?.processing_family || (isPlot ? "visualization" : "data_processing");
    const summary = processing?.summary?.rows_after_prepare !== undefined
      ? `Rows after prepare: ${processing.summary.rows_after_prepare}`
      : item.metadata?.summary || item.description || "Processing output saved in workspace assets.";
    const detailPath = processing?.result_detail_path || "";
    const useButton = item.kind?.startsWith("dataset")
      ? `<button type="button" class="secondary" data-select-asset="${escapeHtml(item.id)}">Use in lab</button>`
      : "";
    return `
      <article class="card">
        <h4>${escapeHtml(item.title)}</h4>
        <p>${escapeHtml(family)} | ${escapeHtml(prettyDate(item.updated_at || item.created_at))}</p>
        <p>${escapeHtml(truncateText(summary))}</p>
        <div class="actions">
          ${detailPath ? `<a href="${escapeHtml(detailPath)}" class="button-link secondary-link">Open detail</a>` : ""}
          ${useButton}
          <button type="button" class="secondary" data-download-asset="${escapeHtml(item.id)}">${isPlot ? "Download chart" : "Download asset"}</button>
        </div>
      </article>
    `;
  }).join("");
}

function renderModelHistory(items = modelHistoryItems()) {
  if (!dom.labRecentModelList) {
    return;
  }
  if (!items.length) {
    dom.labRecentModelList.innerHTML = emptyCard("No model history yet.");
    return;
  }
  dom.labRecentModelList.innerHTML = items.slice(0, 6).map((item) => {
    const metadata = item.metadata || {};
    const detailPath = metadata.result_detail_path || `/data-lab/results/models/${item.id}`;
    const summary = metadata.equation || metadata.model_family || item.content || "Model output recorded in the private knowledge base.";
    return `
      <article class="card">
        <h4>${escapeHtml(metadata.model_label || item.title)}</h4>
        <p>${escapeHtml(metadata.model_type || "model")} | ${escapeHtml(prettyDate(item.updated_at || item.created_at))}</p>
        <p>${escapeHtml(truncateText(summary))}</p>
        <div class="actions">
          <a href="${escapeHtml(detailPath)}" class="button-link secondary-link">Open detail</a>
        </div>
      </article>
    `;
  }).join("");
}

function focusWorkbench() {
  document.getElementById("data-lab-workbench")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function activateProcessingFamily(family) {
  if (!dom.labWorkflowType || !dom.processingFamily) {
    return;
  }
  dom.labWorkflowType.value = "data_processing";
  dom.processingFamily.value = family;
  updateWorkflowVisibility();
  focusWorkbench();
}

function activateModelFamily(family, modelType = "") {
  if (!dom.labWorkflowType || !dom.modelFamily) {
    return;
  }
  dom.labWorkflowType.value = "model";
  dom.modelFamily.value = family;
  syncModelTypeOptions();
  if (modelType && dom.modelType) {
    dom.modelType.value = modelType;
  }
  updateWorkflowVisibility();
  focusWorkbench();
}

function initializeDataLabFromLocation() {
  if (detectPageMode() !== "data-lab") {
    return;
  }
  const workflow = dataLabQueryValue("workflow");
  const processingFamily = dataLabQueryValue("processing_family");
  const modelFamily = dataLabQueryValue("model_family");
  const modelType = dataLabQueryValue("model_type");
  if (workflow === "data_processing" && processingFamily) {
    dom.labWorkflowType && (dom.labWorkflowType.value = "data_processing");
    dom.processingFamily && (dom.processingFamily.value = processingFamily);
  }
  if (workflow === "model" && modelFamily) {
    dom.labWorkflowType && (dom.labWorkflowType.value = "model");
    dom.modelFamily && (dom.modelFamily.value = modelFamily);
    syncModelTypeOptions();
    if (modelType && dom.modelType) {
      dom.modelType.value = modelType;
    }
  }
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

function setSelectValue(select, value = "") {
  if (!select) {
    return;
  }
  select.value = value || "";
}

function setMultiSelectValues(select, values = []) {
  if (!select) {
    return;
  }
  const selectedSet = new Set((values || []).filter(Boolean));
  Array.from(select.options || []).forEach((option) => {
    option.selected = selectedSet.has(option.value);
  });
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

function revokeResultPreviewUrls() {
  for (const url of state.resultPreviewUrls || []) {
    URL.revokeObjectURL(url);
  }
  state.resultPreviewUrls = [];
}

async function fetchPrivateAssetPreviewUrl(assetId) {
  const response = await fetch(`/api/assets/${assetId}/download`, {
    headers: { Authorization: `Bearer ${state.token}` },
  });
  if (!response.ok) {
    throw new Error("Preview asset download failed.");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  state.resultPreviewUrls.push(url);
  return url;
}

function renderDataLabPlaceholders() {
  dom.analysisAssetOverview && (dom.analysisAssetOverview.innerHTML = `<p>Select a dataset to inspect rows, missingness, variable roles, and preview records.</p>`);
  dom.analysisColumnGrid && (dom.analysisColumnGrid.innerHTML = emptyCard("Column roles and missingness will appear here."));
  dom.analysisPreviewTable && (dom.analysisPreviewTable.innerHTML = `<p class="muted">Dataset preview will appear here after you load a profile.</p>`);
  dom.prepareOutput && (dom.prepareOutput.textContent = "Waiting for sample preparation.");
  dom.analysisOutput && (dom.analysisOutput.textContent = "Waiting for model output.");
  dom.prepareResultMeta && (dom.prepareResultMeta.textContent = "Waiting for sample preparation.");
  dom.analysisResultMeta && (dom.analysisResultMeta.textContent = "Waiting for model output.");
  dom.prepareResultSummary && (dom.prepareResultSummary.innerHTML = emptyCard("No prepared sample has been created in this session yet."));
  dom.analysisResultSummary && (dom.analysisResultSummary.innerHTML = emptyCard("No model has been run in this session yet."));
  dom.prepareResultLink?.classList.add("hidden");
  dom.analysisResultLink?.classList.add("hidden");
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
  renderVariableGuide(null);
  renderLabContext();
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
  renderLabContext();
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
  setSelectOptions(dom.prepareMinmaxScaleColumns, numericColumns, { multiple: true });
  setSelectOptions(dom.prepareOutlierColumns, numericColumns, { multiple: true });
  setSelectOptions(dom.prepareSortColumn, allColumns, { placeholder: "Select sort column" });
  setSelectOptions(dom.prepareTimeGroupColumn, allColumns, { placeholder: "Optional grouping column" });
  setSelectOptions(dom.prepareDifferenceColumns, numericColumns, { multiple: true });
  setSelectOptions(dom.prepareReturnColumns, numericColumns, { multiple: true });
  setSelectOptions(dom.prepareLagColumns, numericColumns, { multiple: true });
  setSelectOptions(dom.prepareLeadColumns, numericColumns, { multiple: true });
  setSelectOptions(dom.prepareRollingMeanColumns, numericColumns, { multiple: true });
  setSelectOptions(dom.prepareRollingVolatilityColumns, numericColumns, { multiple: true });

  setSelectOptions(dom.modelIndependents, numericColumns, { multiple: true });
  setSelectOptions(dom.modelControls, numericColumns, { multiple: true });
  setSelectOptions(dom.didTreatmentColumn, binaryColumns, { placeholder: "Select treatment indicator" });
  setSelectOptions(dom.didPostColumn, binaryColumns, { placeholder: "Select post indicator" });
  setSelectOptions(dom.eventTreatmentColumn, binaryColumns, { placeholder: "Select treatment indicator" });
  setSelectOptions(dom.eventTimeColumn, numericColumns, { placeholder: "Select relative event time" });
  setSelectOptions(dom.rddRunningColumn, numericColumns, { placeholder: "Select running variable" });
  setSelectOptions(dom.gravityOriginMassColumn, numericColumns, { placeholder: "Select origin mass" });
  setSelectOptions(dom.gravityDestinationMassColumn, numericColumns, { placeholder: "Select destination mass" });
  setSelectOptions(dom.gravityDistanceColumn, numericColumns, { placeholder: "Select distance variable" });
  setSelectOptions(dom.panelEntityColumn, allColumns, { placeholder: "Select entity column" });
  setSelectOptions(dom.panelTimeColumn, allColumns, { placeholder: "Select time column" });
  setSelectOptions(dom.modelSeriesColumns, numericColumns, { multiple: true });
  setSelectOptions(dom.modelTimeColumn, allColumns, { placeholder: "Select time column" });
  setSelectOptions(dom.impulseColumn, numericColumns, { placeholder: "Select impulse variable" });
  setSelectOptions(dom.responseColumn, numericColumns, { placeholder: "Optional response variable" });
  setSelectOptions(dom.ivEndogenousColumn, numericColumns, { placeholder: "Select endogenous regressor" });
  setSelectOptions(dom.ivInstrumentColumns, numericColumns, { multiple: true });
  setSelectOptions(dom.marketColumn, numericColumns, { placeholder: "Select market return / factor" });
  setSelectOptions(dom.riskFreeColumn, numericColumns, { placeholder: "Optional risk-free rate" });
  setSelectOptions(dom.smbColumn, numericColumns, { placeholder: "Select SMB factor" });
  setSelectOptions(dom.hmlColumn, numericColumns, { placeholder: "Select HML factor" });
  setSelectOptions(dom.spotColumn, numericColumns, { placeholder: "Select spot price column" });
  setSelectOptions(dom.strikeColumn, numericColumns, { placeholder: "Select strike column" });
  setSelectOptions(dom.maturityColumn, numericColumns, { placeholder: "Select maturity column" });
  setSelectOptions(dom.rateColumn, numericColumns, { placeholder: "Select rate column" });
  setSelectOptions(dom.volatilityColumn, numericColumns, { placeholder: "Select volatility column" });
  setSelectOptions(dom.workingCapitalColumn, numericColumns, { placeholder: "Select working capital" });
  setSelectOptions(dom.retainedEarningsColumn, numericColumns, { placeholder: "Select retained earnings" });
  setSelectOptions(dom.ebitColumn, numericColumns, { placeholder: "Select EBIT" });
  setSelectOptions(dom.marketEquityColumn, numericColumns, { placeholder: "Select market equity" });
  setSelectOptions(dom.totalAssetsColumn, numericColumns, { placeholder: "Select total assets" });
  setSelectOptions(dom.totalLiabilitiesColumn, numericColumns, { placeholder: "Select total liabilities" });
  setSelectOptions(dom.salesColumn, numericColumns, { placeholder: "Select sales" });
  setSelectOptions(dom.netIncomeColumn, numericColumns, { placeholder: "Select net income" });
  setSelectOptions(dom.revenueColumn, numericColumns, { placeholder: "Select revenue" });
  setSelectOptions(dom.equityColumn, numericColumns, { placeholder: "Select equity" });
  setSelectOptions(dom.inflationGapColumn, numericColumns, { placeholder: "Select inflation gap" });
  setSelectOptions(dom.outputGapColumn, numericColumns, { placeholder: "Select output gap" });

  setSelectOptions(dom.plotXColumn, allColumns, { placeholder: "Select X variable" });
  setSelectOptions(dom.plotYColumns, numericColumns, { multiple: true });
  setSelectOptions(dom.plotGroupColumn, columns, { placeholder: "Optional group column" });
  syncModelTypeOptions();
  updateWorkflowVisibility();
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
  renderLabContext();
}

function refreshModelVariableOptions() {
  const profile = currentAssetProfile();
  const numericColumns = (profile?.column_roles?.numeric || []).map((value) => ({ value, label: value }));
  const binaryColumns = (profile?.column_roles?.binary || []).map((value) => ({ value, label: value }));
  const modelType = dom.modelType?.value || "ols";
  const config = MODEL_CONFIG[modelType] || {};
  const currentDependent = dom.modelDependent?.value || "";
  const placeholder = config.dependentLabel
    || (modelType === "gravity"
      ? "Select a flow variable"
      : modelType === "logit" || modelType === "probit"
        ? "Select a binary outcome"
        : modelType.includes("var") || modelType === "svar_irf" || modelType === "virf" || modelType === "capm" || modelType === "fama_french_3"
          ? "Select a return series"
          : "Select an outcome variable");
  const options = config.dependentKind === "binary" ? binaryColumns : numericColumns;
  setSelectOptions(dom.modelDependent, options, {
    placeholder: config.dependentKind ? placeholder : "This model does not use an outcome variable",
    selected: currentDependent,
  });
}

function syncModelTypeOptions() {
  const family = currentModelFamily();
  const options = MODEL_FAMILY_OPTIONS[family] || MODEL_FAMILY_OPTIONS.econometrics_baseline;
  const current = dom.modelType?.value || "";
  const selected = options.some((item) => item.value === current) ? current : options[0]?.value || "ols";
  setSelectOptions(dom.modelType, options, { placeholder: "Select a model", selected });
  if (dom.modelType) {
    dom.modelType.value = selected;
  }
}

function updateModelFieldVisibility() {
  const modelType = dom.modelType?.value || "ols";
  const config = MODEL_CONFIG[modelType] || {};
  toggleHidden(closestWrap(dom.modelDependent), !config.dependentKind);
  toggleHidden(dom.olsFields, !config.independents);
  toggleHidden(closestWrap(dom.modelControls), !config.controls);
  toggleHidden(dom.didFields, !config.did);
  toggleHidden(dom.eventStudyFields, !config.eventStudy);
  toggleHidden(dom.eventStudyWindowFields, !config.eventStudy);
  toggleHidden(dom.rddFields, !config.rdd);
  toggleHidden(dom.rddConfigFields, !config.rdd);
  toggleHidden(dom.gravityFields, !config.gravity);
  toggleHidden(dom.gravityDistanceWrap, !config.gravity);
  toggleHidden(dom.seriesModelFields, !config.series);
  toggleHidden(dom.timeSeriesModelFields, !(config.timeColumn || config.forecast));
  toggleHidden(closestWrap(dom.modelTimeColumn), !config.timeColumn);
  toggleHidden(closestWrap(dom.forecastSteps), !config.forecast);
  toggleHidden(dom.arimaFields, !config.arima);
  toggleHidden(dom.varFields, !config.var);
  toggleHidden(dom.garchFields, !config.garch);
  toggleHidden(dom.irfFields, !config.irf);
  toggleHidden(dom.bkFields, !config.bk);
  toggleHidden(dom.feFields, !config.fe);
  toggleHidden(dom.feTimeToggle, !config.fe);
  toggleHidden(dom.ivFields, !config.iv);
  toggleHidden(dom.riskFields, !config.risk);
  toggleHidden(closestWrap(dom.ewmaLambda), modelType !== "ewma_volatility");
  toggleHidden(dom.corporateAltmanFields, !config.corporateAltman);
  toggleHidden(dom.corporateAltmanFields2, !config.corporateAltman);
  toggleHidden(dom.corporateDupontFields, !config.corporateDupont);
  toggleHidden(dom.derivativeFields, !config.derivative);
  toggleHidden(dom.derivativeFields2, !config.derivative);
  toggleHidden(dom.macroTaylorFields, !config.macroTaylor);
  toggleHidden(dom.dsgeFields, !config.dsge);
  toggleHidden(dom.dsgeFields2, !config.dsge);
  toggleHidden(dom.portfolioFields, !config.portfolio);
  toggleHidden(dom.assetPricingFields, !config.assetPricing);
  toggleHidden(dom.ff3Fields, !config.ff3);
  toggleHidden(dom.modelRobustCovariance?.closest("label.checkbox"), !config.robust);
  refreshModelVariableOptions();
}

function updateWorkflowVisibility() {
  const workflowType = currentWorkflowType();
  const processingFamily = currentProcessingFamily();
  const isProcessing = workflowType === "data_processing";
  const isVisualization = isProcessing && processingFamily === "visualization";

  toggleHidden(dom.processingFamilyWrap, !isProcessing);
  toggleHidden(dom.modelFamilyWrap, isProcessing);
  toggleHidden(dom.prepareForm, !isProcessing || isVisualization);
  toggleHidden(dom.plotForm, !isVisualization);
  toggleHidden(dom.modelForm, isProcessing);

  if (isProcessing && !isVisualization) {
    toggleHidden(dom.prepareCoreFields, processingFamily !== "sample_preparation");
    toggleHidden(dom.prepareCleaningFields, processingFamily !== "cleaning_transforms");
    toggleHidden(dom.prepareTimeSeriesFields, processingFamily !== "time_series_features");
  }

  if (!isProcessing) {
    syncModelTypeOptions();
    updateModelFieldVisibility();
  }
  renderLabContext();
}

function hasPrivateWorkspaceUI() {
  return Boolean(
    dom.workspaceSelect &&
      (dom.analysisAssetSelect ||
        dom.assetList ||
        dom.integrationList ||
        dom.briefingList ||
        dom.literatureList ||
        dom.knowledgeList ||
        dom.scheduleList),
  );
}

function hasPublicMonitorUI() {
  return Boolean(dom.publicLatestView && dom.publicSummaryView && dom.publicBriefingList);
}

function clearPrivateLists() {
  if (!hasPrivateWorkspaceUI()) {
    return;
  }
  state.workspaceAssets = [];
  state.workspaceKnowledge = [];
  if (dom.integrationList) {
    dom.integrationList.innerHTML = emptyCard("Log in to view saved provider connections.");
  }
  if (dom.briefingList) {
    dom.briefingList.innerHTML = emptyCard("Log in to generate private briefings.");
  }
  if (dom.openalexResults) {
    dom.openalexResults.innerHTML = emptyCard("Search results will appear here.");
  }
  if (dom.literatureList) {
    dom.literatureList.innerHTML = emptyCard("Your imported literature will appear here.");
  }
  if (dom.assetList) {
    dom.assetList.innerHTML = emptyCard("Your uploaded data assets will appear here.");
  }
  if (dom.knowledgeList) {
    dom.knowledgeList.innerHTML = emptyCard("Your private notes will appear here.");
  }
  if (dom.scheduleList) {
    dom.scheduleList.innerHTML = emptyCard("Your scheduled jobs will appear here.");
  }
  if (dom.analysisOutput) {
    dom.analysisOutput.textContent = "Waiting for analysis output.";
  }
  if (dom.analysisAssetSelect) {
    dom.analysisAssetSelect.innerHTML = `<option value="">Select a dataset asset</option>`;
  }
  renderDataLabPlaceholders();
  renderProcessingHistory([]);
  renderModelHistory([]);
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
  state.assetProfiles = {};
  state.selectedAnalysisAssetId = "";
  localStorage.removeItem(storageKeys.token);
  localStorage.removeItem(storageKeys.workspaceId);
  revokeResultPreviewUrls();
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
    renderLabContext();
    return;
  }
  dom.sessionIndicator.textContent = "Signed in";
  dom.userSummary.textContent = `${state.user.full_name} | ${state.user.email}`;
  renderLabContext();
}

function renderWorkspaceOptions() {
  if (!dom.workspaceSelect) {
    return;
  }
  dom.workspaceSelect.innerHTML = "";
  if (!state.workspaces.length) {
    dom.workspaceSelect.innerHTML = `<option value="">No workspace yet</option>`;
    renderLabContext();
    return;
  }
  for (const workspace of state.workspaces) {
    const option = document.createElement("option");
    option.value = workspace.id;
    option.textContent = workspace.name;
    option.selected = workspace.id === state.selectedWorkspaceId;
    dom.workspaceSelect.appendChild(option);
  }
  renderLabContext();
}

function renderIntegrations(items) {
  if (!dom.integrationList) {
    return;
  }
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
  if (!dom.briefingList) {
    return;
  }
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
  if (!dom.openalexResults) {
    return;
  }
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
  if (!dom.literatureList) {
    return;
  }
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
  state.workspaceAssets = items || [];
  syncDataLabAssetOptions(items);
  if (!dom.assetList) {
    renderProcessingHistory(processingHistoryItems());
    return;
  }
  if (!items.length) {
    dom.assetList.innerHTML = emptyCard("No uploaded assets yet.");
    renderProcessingHistory([]);
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
  renderProcessingHistory(processingHistoryItems());
}

function renderKnowledge(items) {
  state.workspaceKnowledge = items || [];
  if (!dom.knowledgeList) {
    renderModelHistory(modelHistoryItems());
    return;
  }
  if (!items.length) {
    dom.knowledgeList.innerHTML = emptyCard("No private notes yet.");
    renderModelHistory([]);
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
  renderModelHistory(modelHistoryItems());
}

function renderSchedules(items) {
  if (!dom.scheduleList) {
    return;
  }
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

function renderDataLabMethodDetail(detail) {
  if (!detail) {
    throw new Error("Method detail not found.");
  }
  if (dom.labDetailEyebrow) {
    dom.labDetailEyebrow.textContent = detail.category === "model" ? "Model Family" : "Data Processing Family";
  }
  dom.labDetailTitle && (dom.labDetailTitle.textContent = detail.title || "Method Detail");
  dom.labDetailSummary && (dom.labDetailSummary.textContent = detail.summary || "");
  dom.labDetailCategory && (dom.labDetailCategory.textContent = detail.category_label || detail.category || "Data Lab");
  dom.labDetailHeading && (dom.labDetailHeading.textContent = detail.title || "Method Detail");
  dom.labDetailDescription && (dom.labDetailDescription.textContent = detail.description || "");
  if (dom.labDetailWorkbenchLink) {
    dom.labDetailWorkbenchLink.href = detail.workbench_path || "/data-lab";
  }
  renderListCards(dom.labDetailMethodList, detail.methods || [], (item) => `
    <article class="method-card">
      <p class="eyebrow eyebrow-compact">${escapeHtml(detail.category_label || detail.category || "Method")}</p>
      <h4>${escapeHtml(item.name || item.slug || "Method")}</h4>
      <p>${escapeHtml(item.description || "")}</p>
    </article>
  `);
  renderListCards(dom.labDetailInputList, detail.key_inputs || [], (item) => `
    <article class="card">
      <p>${escapeHtml(item)}</p>
    </article>
  `);
  renderListCards(dom.labDetailAuditList, detail.manual_checks || [], (item) => `
    <article class="card">
      <p>${escapeHtml(item)}</p>
    </article>
  `);
  updateDocumentTitle();
}

function renderResultMetrics(target, result) {
  if (!target) {
    return;
  }
  const narrativeHtml = (result.narrative || []).map((line) => `<p>${escapeHtml(line)}</p>`).join("");
  const metrics = resultMetricCards(result);
  const metricHtml = metrics.length
    ? `<div class="chip-row chip-row-compact">${metrics.map((item) => `<span class="topic-chip">${escapeHtml(item.label)} <strong>${escapeHtml(item.value)}</strong></span>`).join("")}</div>`
    : "";
  target.innerHTML = `
    <article class="card">
      <h4>${escapeHtml(result.model_label || result.processing_family || "Result")}</h4>
      ${metricHtml}
      <div>${narrativeHtml || `<p>${escapeHtml(result.summary?.rows_after_prepare ? `Rows after prepare: ${result.summary.rows_after_prepare}` : "No narrative available.")}</p>`}</div>
    </article>
  `;
}

function renderResultSpecification(target, result) {
  if (!target) {
    return;
  }
  const specification = result.specification || {};
  const summary = result.summary || {};
  const rows = Object.entries(specification).concat(
    result.workflow_type === "data_processing" ? Object.entries(summary).filter(([key]) => ["rows_before_prepare", "rows_after_prepare", "columns", "derived_columns"].includes(key)) : [],
  );
  if (!rows.length) {
    target.innerHTML = emptyCard("No specification metadata available.");
    return;
  }
  target.innerHTML = `
    <article class="card">
      ${rows
        .map(([key, value]) => `<p><strong>${escapeHtml(key)}:</strong> ${escapeHtml(Array.isArray(value) ? value.join(", ") : typeof value === "object" ? JSON.stringify(value) : String(value ?? ""))}</p>`)
        .join("")}
    </article>
  `;
}

function renderResultTables(target, result) {
  if (!target) {
    return;
  }
  const coefficients = result.coefficients || [];
  const tables = result.tables || {};
  const blocks = [];
  const renderTabularCard = (title, rows) => {
    const normalizedRows = Array.isArray(rows) ? rows.filter((item) => item && typeof item === "object" && !Array.isArray(item)) : [];
    if (!normalizedRows.length) {
      return `
        <article class="card">
          <h4>${escapeHtml(title)}</h4>
          <pre class="console-box">${escapeHtml(JSON.stringify(rows, null, 2))}</pre>
        </article>
      `;
    }
    const columns = Array.from(new Set(normalizedRows.flatMap((row) => Object.keys(row))));
    return `
      <article class="card">
        <h4>${escapeHtml(title)}</h4>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr>
            </thead>
            <tbody>
              ${normalizedRows
                .map(
                  (row) => `
                    <tr>${columns.map((column) => `<td>${escapeHtml(row?.[column] ?? "")}</td>`).join("")}</tr>
                  `,
                )
                .join("")}
            </tbody>
          </table>
        </div>
      </article>
    `;
  };
  if (coefficients.length) {
    blocks.push(`
      <article class="card">
        <h4>Coefficient Table</h4>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr><th>Term</th><th>Coef.</th><th>Std. Err.</th><th>t/z</th><th>p-value</th></tr>
            </thead>
            <tbody>
              ${coefficients
                .map(
                  (row) => `
                    <tr>
                      <td>${escapeHtml(row.term)}</td>
                      <td>${escapeHtml(row.coefficient ?? "")}</td>
                      <td>${escapeHtml(row.std_error ?? "")}</td>
                      <td>${escapeHtml(row.t_stat ?? "")}</td>
                      <td>${escapeHtml(row.p_value ?? "")}</td>
                    </tr>
                  `,
                )
                .join("")}
            </tbody>
          </table>
        </div>
      </article>
    `);
  }
  Object.entries(tables).forEach(([name, table]) => {
    blocks.push(renderTabularCard(name, table));
  });
  target.innerHTML = blocks.join("") || "";
}

function renderResultAudit(target, result) {
  if (!target) {
    return;
  }
  const audit = result.audit_trail || {};
  const checklist = audit.manual_checklist || [];
  const downloads = [
    audit.prepared_asset_id ? `<button type="button" class="secondary" data-download-asset="${escapeHtml(audit.prepared_asset_id)}">Download prepared sample</button>` : "",
    audit.sample_asset_id ? `<button type="button" class="secondary" data-download-asset="${escapeHtml(audit.sample_asset_id)}">Download sample used</button>` : "",
  ].filter(Boolean);
  target.innerHTML = `
    <article class="card">
      ${Object.entries(audit)
        .filter(([key]) => !["manual_checklist", "operations"].includes(key))
        .map(([key, value]) => `<p><strong>${escapeHtml(key)}:</strong> ${escapeHtml(typeof value === "object" ? JSON.stringify(value) : String(value ?? ""))}</p>`)
        .join("")}
      ${downloads.length ? `<div class="actions">${downloads.join("")}</div>` : ""}
    </article>
    <article class="card">
      <h4>Manual Checklist</h4>
      ${checklist.length ? checklist.map((item) => `<p>${escapeHtml(item)}</p>`).join("") : `<p>No checklist available.</p>`}
    </article>
    ${
      audit.operations
        ? `<article class="card"><h4>Operations</h4><pre class="console-box">${escapeHtml(JSON.stringify(audit.operations, null, 2))}</pre></article>`
        : ""
    }
  `;
}

async function renderResultPreview(target, result) {
  if (!target) {
    return;
  }
  revokeResultPreviewUrls();
  const previewRows = result.preview_rows || result.sample_preview || result.profile?.preview_rows || [];
  const blocks = [];
  if (previewRows.length) {
    const columns = Array.from(new Set(previewRows.flatMap((row) => Object.keys(row || {}))));
    blocks.push(`
      <article class="card">
        <h4>Sample Preview</h4>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr>
            </thead>
            <tbody>
              ${previewRows
                .map(
                  (row) => `
                    <tr>${columns.map((column) => `<td>${escapeHtml(row?.[column] ?? "")}</td>`).join("")}</tr>
                  `,
                )
                .join("")}
            </tbody>
          </table>
        </div>
      </article>
    `);
  }
  const figures = Array.isArray(result.figures) ? result.figures : [];
  if (figures.length) {
    const figureCards = await Promise.all(
      figures.map(async (figure, index) => {
        let imageContent = `<p class="muted">Preview unavailable.</p>`;
        try {
          const previewUrl = await fetchPrivateAssetPreviewUrl(figure.asset_id);
          imageContent = `<img class="result-figure-frame" src="${previewUrl}" alt="${escapeHtml(figure.title || `Result figure ${index + 1}`)}" />`;
        } catch (error) {
          imageContent = `<p class="muted">${escapeHtml(error.message || "Preview unavailable.")}</p>`;
        }
        return `
          <article class="result-figure-card">
            <div class="panel-head panel-head-wrap">
              <div>
                <h4>${escapeHtml(figure.title || `Figure ${index + 1}`)}</h4>
                <span class="muted">${escapeHtml(figure.filename || "")}</span>
              </div>
            </div>
            <div class="figure-preview-box">${imageContent}</div>
            <p class="muted">${escapeHtml(figure.summary || "")}</p>
            <div class="actions">
              <button type="button" class="secondary" data-download-asset="${escapeHtml(figure.asset_id)}">Download figure PNG</button>
            </div>
          </article>
        `;
      }),
    );
    blocks.push(`
      <article class="card">
        <h4>Figures</h4>
        <div class="result-figure-grid">${figureCards.join("")}</div>
      </article>
    `);
  }
  target.innerHTML = blocks.join("") || emptyCard("No preview rows or figures are available for this result.");
}

async function loadMethodDetailPage() {
  const route = extractDataLabMethodRoute();
  if (!route) {
    return;
  }
  const payload = await api(`/api/data-lab/${route.category}/${route.family}`, {}, false);
  renderDataLabMethodDetail(payload.family);
}

async function loadResultDetailPage() {
  const route = extractDataLabResultRoute();
  if (!route) {
    return;
  }
  await ensureAuthenticatedUser();
  const payload = await api(`/api/data-lab/results/${route.category}/${route.id}`);
  const result = payload.result || payload;
  dom.labResultType && (dom.labResultType.textContent = result.model_label || result.processing_family || route.category);
  dom.labResultEyebrow &&
    (dom.labResultEyebrow.textContent = route.category === "models" ? "Model Result" : "Processing Result");
  dom.labResultTitle &&
    (dom.labResultTitle.textContent =
      route.category === "models"
        ? payload.record?.title || result.model_label || "Model Result"
        : result.asset?.title || "Processing Result");
  dom.labResultSummary &&
    (dom.labResultSummary.textContent =
      route.category === "models"
        ? `${result.model_label || result.model_type || "Model"} on ${result.asset?.title || "dataset"}`
        : `${result.processing_family || "data_processing"} result for ${result.asset?.title || "prepared sample"}`);
  dom.labResultHeading &&
    (dom.labResultHeading.textContent = route.category === "models" ? "Model Result Detail" : "Processing Result Detail");
  if (dom.labResultWorkbenchLink) {
    dom.labResultWorkbenchLink.href = route.category === "models" ? "/data-lab?workflow=model#data-lab-workbench" : "/data-lab?workflow=data_processing#data-lab-workbench";
  }
  renderResultMetrics(dom.labResultMetrics, result);
  renderResultSpecification(dom.labResultSpecification, result);
  renderResultTables(dom.labResultTables, result);
  renderResultAudit(dom.labResultAudit, result);
  await renderResultPreview(dom.labResultPreview, result);
  if (dom.labResultRaw) {
    dom.labResultRaw.textContent = JSON.stringify(payload, null, 2);
  }
  updateDocumentTitle();
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
  if (pageMode === "data-lab") {
    document.title = "Data Lab | Economic Research Platform";
    return;
  }
  if (pageMode === "data-lab-method-detail" && dom.labDetailTitle?.textContent) {
    document.title = `${dom.labDetailTitle.textContent} | Economic Research Platform`;
    return;
  }
  if (pageMode === "data-lab-result-detail" && dom.labResultTitle?.textContent) {
    document.title = `${dom.labResultTitle.textContent} | Economic Research Platform`;
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
  renderVariableGuide(null);
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
  if (state.selectedAnalysisAssetId && dom.analysisAssetSelect) {
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

function renderVariableGuide(result) {
  state.variableGuideResult = result || null;
  if (!result) {
    if (dom.variableGuideMeta) dom.variableGuideMeta.textContent = "No variable guide output yet.";
    if (dom.variableGuideSummary) dom.variableGuideSummary.innerHTML = `<p class="muted">Describe your question in plain language and run the guide.</p>`;
    if (dom.variableGuideRoles) dom.variableGuideRoles.innerHTML = "";
    if (dom.variableGuideChecks) dom.variableGuideChecks.innerHTML = "";
    if (dom.variableGuideRaw) dom.variableGuideRaw.textContent = "";
    if (dom.variableGuideApply) {
      dom.variableGuideApply.disabled = true;
      dom.variableGuideApply.classList.add("hidden");
    }
    return;
  }
  const recommendation = result.workflow_recommendation || {};
  const matchedTerms = (result.transparency?.matched_intent_terms || []).join(", ");
  if (dom.variableGuideMeta) {
    dom.variableGuideMeta.textContent = [
      recommendation.label || "Recommendation",
      recommendation.workflow_type || "",
      recommendation.model_type || recommendation.processing_family || "",
      matchedTerms ? `signals: ${matchedTerms}` : "",
    ]
      .filter(Boolean)
      .join(" | ");
  }
  if (dom.variableGuideSummary) {
    dom.variableGuideSummary.innerHTML = `
      <p>${escapeHtml(result.summary || "")}</p>
      ${(result.reasoning || []).map((item) => `<p class="muted">${escapeHtml(item)}</p>`).join("")}
    `;
  }
  if (dom.variableGuideRoles) {
    const roles = result.suggested_roles || [];
    dom.variableGuideRoles.innerHTML = roles.length
      ? roles
          .map(
            (role) => `
              <article class="card compact-card">
                <h4>${escapeHtml(role.label || role.role)}</h4>
                <p><strong>${escapeHtml(role.value || "Not selected")}</strong></p>
                <p class="muted">${escapeHtml((role.reasoning || []).join(" | ") || "Chosen from dataset profile and prompt matching.")}</p>
              </article>
            `,
          )
          .join("")
      : emptyCard("No clear variable roles were inferred.");
  }
  if (dom.variableGuideChecks) {
    const checks = result.manual_checklist || [];
    dom.variableGuideChecks.innerHTML = checks.length
      ? checks.map((item) => `<p>${escapeHtml(item)}</p>`).join("")
      : `<p class="muted">No manual checklist available.</p>`;
  }
  if (dom.variableGuideRaw) {
    dom.variableGuideRaw.textContent = JSON.stringify(result, null, 2);
  }
  if (dom.variableGuideApply) {
    dom.variableGuideApply.disabled = false;
    dom.variableGuideApply.classList.remove("hidden");
  }
}

function applyVariableGuidePrefill() {
  const result = state.variableGuideResult;
  if (!result) {
    throw new Error("Run the variable guide first.");
  }
  const prefill = result.prefill || {};
  const workflowType = prefill.workflow_type || result.workflow_recommendation?.workflow_type || "model";
  if (workflowType === "data_processing") {
    const family = prefill.processing_family || result.workflow_recommendation?.processing_family || "sample_preparation";
    activateProcessingFamily(family);
    setMultiSelectValues(dom.prepareKeepColumns, prefill.include_columns || []);
    setMultiSelectValues(dom.prepareRequiredColumns, prefill.required_columns || []);
    setMultiSelectValues(dom.prepareNumericColumns, prefill.numeric_columns || []);
    setMultiSelectValues(dom.prepareBinaryColumns, prefill.binary_columns || []);
    setMultiSelectValues(dom.prepareDateColumns, prefill.date_columns || []);
    setSelectValue(dom.prepareSortColumn, prefill.sort_column || "");
    setSelectValue(dom.prepareTimeGroupColumn, prefill.time_group_column || "");
    setMultiSelectValues(dom.prepareDifferenceColumns, prefill.difference_columns || []);
    setMultiSelectValues(dom.prepareReturnColumns, prefill.return_columns || []);
    setSelectValue(dom.plotXColumn, prefill.plot_x_column || "");
    setMultiSelectValues(dom.plotYColumns, prefill.plot_y_columns || []);
    setSelectValue(dom.plotGroupColumn, prefill.plot_group_column || "");
  } else {
    const family = prefill.model_family || result.workflow_recommendation?.model_family || "econometrics_baseline";
    const modelType = prefill.model_type || result.workflow_recommendation?.model_type || "ols";
    activateModelFamily(family, modelType);
    setSelectValue(dom.modelDependent, prefill.dependent || "");
    setMultiSelectValues(dom.modelIndependents, prefill.independents || []);
    setMultiSelectValues(dom.modelControls, prefill.controls || []);
    setMultiSelectValues(dom.modelSeriesColumns, prefill.series_columns || []);
    setSelectValue(dom.didTreatmentColumn, prefill.treatment_column || "");
    setSelectValue(dom.eventTreatmentColumn, prefill.treatment_column || "");
    setSelectValue(dom.didPostColumn, prefill.post_column || "");
    setSelectValue(dom.eventTimeColumn, prefill.event_time_column || "");
    setSelectValue(dom.panelEntityColumn, prefill.entity_column || "");
    setSelectValue(dom.panelTimeColumn, prefill.time_column || "");
    setSelectValue(dom.modelTimeColumn, prefill.time_column || "");
    setSelectValue(dom.rddRunningColumn, prefill.running_column || "");
    setSelectValue(dom.gravityOriginMassColumn, prefill.origin_mass_column || "");
    setSelectValue(dom.gravityDestinationMassColumn, prefill.destination_mass_column || "");
    setSelectValue(dom.gravityDistanceColumn, prefill.distance_column || "");
    setSelectValue(dom.ivEndogenousColumn, prefill.endogenous_column || "");
    setMultiSelectValues(dom.ivInstrumentColumns, prefill.instrument_columns || []);
    setSelectValue(dom.marketColumn, prefill.market_column || "");
    setSelectValue(dom.riskFreeColumn, prefill.risk_free_column || "");
    setSelectValue(dom.smbColumn, prefill.smb_column || "");
    setSelectValue(dom.hmlColumn, prefill.hml_column || "");
    setSelectValue(dom.spotColumn, prefill.spot_column || "");
    setSelectValue(dom.strikeColumn, prefill.strike_column || "");
    setSelectValue(dom.maturityColumn, prefill.maturity_column || "");
    setSelectValue(dom.rateColumn, prefill.rate_column || "");
    setSelectValue(dom.volatilityColumn, prefill.volatility_column || "");
    setSelectValue(dom.workingCapitalColumn, prefill.working_capital_column || "");
    setSelectValue(dom.retainedEarningsColumn, prefill.retained_earnings_column || "");
    setSelectValue(dom.ebitColumn, prefill.ebit_column || "");
    setSelectValue(dom.marketEquityColumn, prefill.market_equity_column || "");
    setSelectValue(dom.totalAssetsColumn, prefill.total_assets_column || "");
    setSelectValue(dom.totalLiabilitiesColumn, prefill.total_liabilities_column || "");
    setSelectValue(dom.salesColumn, prefill.sales_column || "");
    setSelectValue(dom.netIncomeColumn, prefill.net_income_column || "");
    setSelectValue(dom.revenueColumn, prefill.revenue_column || "");
    setSelectValue(dom.equityColumn, prefill.equity_column || "");
    setSelectValue(dom.inflationGapColumn, prefill.inflation_gap_column || "");
    setSelectValue(dom.outputGapColumn, prefill.output_gap_column || "");
    setSelectValue(dom.impulseColumn, prefill.impulse_column || "");
    setSelectValue(dom.responseColumn, prefill.response_column || "");
  }
  renderLabContext();
  showToast("Variable guide suggestions applied to the workbench.");
}

async function handleVariableGuide(event) {
  event.preventDefault();
  ensureWorkspace();
  const assetId = dom.analysisAssetSelect?.value || state.selectedAnalysisAssetId;
  if (!assetId) {
    throw new Error("Select a dataset asset first.");
  }
  const prompt = (dom.variableGuidePrompt?.value || "").trim();
  if (prompt.length < 8) {
    throw new Error("Describe the research question in more detail.");
  }
  const response = await api(`/api/workspaces/${state.selectedWorkspaceId}/analysis/variable-guide`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ asset_id: assetId, prompt }),
  });
  renderVariableGuide(response);
  showToast("Variable guide updated.");
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
    workflow_group: dom.processingFamily?.value || "sample_preparation",
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
    minmax_scale_columns: getSelectedValues(dom.prepareMinmaxScaleColumns),
    outlier_columns: getSelectedValues(dom.prepareOutlierColumns),
    outlier_method: dom.prepareOutlierMethod?.value || "none",
    outlier_threshold: Number(dom.prepareOutlierThreshold?.value || 1.5),
    sort_column: dom.prepareSortColumn?.value || "",
    time_group_column: dom.prepareTimeGroupColumn?.value || "",
    difference_columns: getSelectedValues(dom.prepareDifferenceColumns),
    return_columns: getSelectedValues(dom.prepareReturnColumns),
    return_method: dom.prepareReturnMethod?.value || "simple",
    lag_columns: getSelectedValues(dom.prepareLagColumns),
    lag_periods: Number(dom.prepareLagPeriods?.value || 1),
    lead_columns: getSelectedValues(dom.prepareLeadColumns),
    lead_periods: Number(dom.prepareLeadPeriods?.value || 1),
    rolling_mean_columns: getSelectedValues(dom.prepareRollingMeanColumns),
    rolling_volatility_columns: getSelectedValues(dom.prepareRollingVolatilityColumns),
    rolling_window: Number(dom.prepareRollingWindow?.value || 5),
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
  renderProcessingResultSummary(response);
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
  const useSeriesTimeColumn = ["arima", "arch", "garch", "virf", "var", "svar_irf", "dy_connectedness", "bk_connectedness", "historical_var", "parametric_var", "ewma_volatility"].includes(modelType);
  const payload = {
    asset_id: assetId,
    model_family: dom.modelFamily?.value || "",
    model_type: modelType,
    dependent: dom.modelDependent?.value || "",
    independents: getSelectedValues(dom.modelIndependents),
    controls: getSelectedValues(dom.modelControls),
    series_columns: getSelectedValues(dom.modelSeriesColumns),
    treatment_column:
      modelType === "event_study" ? dom.eventTreatmentColumn?.value || "" : dom.didTreatmentColumn?.value || "",
    post_column: dom.didPostColumn?.value || "",
    event_time_column: dom.eventTimeColumn?.value || "",
    lead_window: Number(dom.eventLeadWindow?.value || 4),
    lag_window: Number(dom.eventLagWindow?.value || 4),
    omitted_period: Number(dom.eventOmittedPeriod?.value || -1),
    origin_mass_column: dom.gravityOriginMassColumn?.value || "",
    destination_mass_column: dom.gravityDestinationMassColumn?.value || "",
    distance_column: dom.gravityDistanceColumn?.value || "",
    running_column: dom.rddRunningColumn?.value || "",
    rdd_cutoff: Number(dom.rddCutoff?.value || 0),
    rdd_bandwidth: Number(dom.rddBandwidth?.value || 0),
    rdd_polynomial_order: Number(dom.rddPolynomialOrder?.value || 1),
    treat_above_cutoff: dom.rddTreatAboveCutoff?.checked ?? true,
    entity_column: dom.panelEntityColumn?.value || "",
    time_column: useSeriesTimeColumn ? dom.modelTimeColumn?.value || "" : dom.panelTimeColumn?.value || "",
    include_time_effects: dom.includeTimeEffects?.checked ?? false,
    endogenous_column: dom.ivEndogenousColumn?.value || "",
    instrument_columns: getSelectedValues(dom.ivInstrumentColumns),
    market_column: dom.marketColumn?.value || "",
    risk_free_column: dom.riskFreeColumn?.value || "",
    smb_column: dom.smbColumn?.value || "",
    hml_column: dom.hmlColumn?.value || "",
    spot_column: dom.spotColumn?.value || "",
    strike_column: dom.strikeColumn?.value || "",
    maturity_column: dom.maturityColumn?.value || "",
    rate_column: dom.rateColumn?.value || "",
    volatility_column: dom.volatilityColumn?.value || "",
    working_capital_column: dom.workingCapitalColumn?.value || "",
    retained_earnings_column: dom.retainedEarningsColumn?.value || "",
    ebit_column: dom.ebitColumn?.value || "",
    market_equity_column: dom.marketEquityColumn?.value || "",
    total_assets_column: dom.totalAssetsColumn?.value || "",
    total_liabilities_column: dom.totalLiabilitiesColumn?.value || "",
    sales_column: dom.salesColumn?.value || "",
    net_income_column: dom.netIncomeColumn?.value || "",
    revenue_column: dom.revenueColumn?.value || "",
    equity_column: dom.equityColumn?.value || "",
    inflation_gap_column: dom.inflationGapColumn?.value || "",
    output_gap_column: dom.outputGapColumn?.value || "",
    arima_p: Number(dom.arimaP?.value || 1),
    arima_d: Number(dom.arimaD?.value || 0),
    arima_q: Number(dom.arimaQ?.value || 0),
    garch_p: Number(dom.garchP?.value || 1),
    garch_q: Number(dom.garchQ?.value || 1),
    forecast_steps: Number(dom.forecastSteps?.value || 5),
    var_lags: Number(dom.varLags?.value || 1),
    irf_horizon: Number(dom.irfHorizon?.value || 12),
    impulse_column: dom.impulseColumn?.value || "",
    response_column: dom.responseColumn?.value || "",
    virf_shock_size: Number(dom.virfShockSize?.value || 1),
    bk_short_horizon: Number(dom.bkShortHorizon?.value || 5),
    bk_medium_horizon: Number(dom.bkMediumHorizon?.value || 20),
    confidence_level: Number(dom.confidenceLevel?.value || 0.95),
    holding_period_days: Number(dom.holdingPeriodDays?.value || 1),
    ewma_lambda: Number(dom.ewmaLambda?.value || 0.94),
    option_type: dom.optionType?.value || "call",
    option_steps: Number(dom.optionSteps?.value || 50),
    risk_aversion: Number(dom.portfolioRiskAversion?.value || 3),
    long_only: dom.portfolioLongOnly?.checked ?? true,
    dsge_alpha: Number(dom.dsgeAlpha?.value || 0.33),
    dsge_beta: Number(dom.dsgeBeta?.value || 0.99),
    dsge_delta: Number(dom.dsgeDelta?.value || 0.025),
    dsge_productivity: Number(dom.dsgeProductivity?.value || 1),
    dsge_labor: Number(dom.dsgeLabor?.value || 0.33),
    dsge_shock_persistence: Number(dom.dsgeShockPersistence?.value || 0.9),
    dsge_shock_size: Number(dom.dsgeShockSize?.value || 0.01),
    dsge_impulse_horizon: Number(dom.dsgeImpulseHorizon?.value || 12),
    robust_covariance: dom.modelRobustCovariance?.checked ?? true,
  };
  const response = await api(`/api/workspaces/${state.selectedWorkspaceId}/analysis/models`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  dom.analysisOutput.textContent = JSON.stringify(response, null, 2);
  renderModelResultSummary(response);
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
  const variableGuideForm = document.getElementById("variable-guide-form");
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
  variableGuideForm?.addEventListener("submit", wrap(handleVariableGuide));
  prepareForm?.addEventListener("submit", wrap(handlePrepareSample));
  modelForm?.addEventListener("submit", wrap(handleModelRun));
  plotForm?.addEventListener("submit", wrap(handlePlot));
  dom.variableGuideApply?.addEventListener("click", wrap(async () => {
    applyVariableGuidePrefill();
  }));

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
  document.querySelectorAll("[data-open-processing-family]").forEach((button) => {
    button.addEventListener("click", () => activateProcessingFamily(button.getAttribute("data-open-processing-family")));
  });
  document.querySelectorAll("[data-open-model-family]").forEach((button) => {
    button.addEventListener("click", () =>
      activateModelFamily(button.getAttribute("data-open-model-family"), button.getAttribute("data-open-model-type") || ""),
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
  dom.labWorkflowType?.addEventListener("change", () => updateWorkflowVisibility());
  dom.processingFamily?.addEventListener("change", () => updateWorkflowVisibility());
  dom.modelFamily?.addEventListener("change", () => {
    syncModelTypeOptions();
    updateModelFieldVisibility();
  });
  dom.modelType?.addEventListener("change", () => updateModelFieldVisibility());
  dom.downloadPlotButton?.addEventListener("click", wrap(async () => {
    if (!state.currentPlotAssetId) {
      throw new Error("Generate a chart first.");
    }
    await downloadAsset(state.currentPlotAssetId);
    showToast("Chart download started.");
  }));
  dom.integrationList?.addEventListener("click", wrap(handleIntegrationActions));
  document.body?.addEventListener("click", wrap(handleAssetActions));
  dom.publicDateSwitcher?.addEventListener("click", wrap(handlePublicActions));
  dom.publicBriefingList?.addEventListener("click", wrap(handlePublicActions));
  dom.publicSummaryFeatured?.addEventListener("click", wrap(handlePublicActions));
  initializeDataLabFromLocation();
  updateWorkflowVisibility();
}

async function init() {
  bind();
  try {
    await fetchHealth();
    const pageMode = detectPageMode();
    if (pageMode === "data-lab" || pageMode === "data-lab-method-detail") {
      await loadDataLabCatalog();
    }
    if (pageMode === "data-lab") {
      renderLabContext();
      renderProcessingHistory([]);
      renderModelHistory([]);
    }
    if (pageMode === "data-lab-method-detail") {
      await loadMethodDetailPage();
    }
    if (pageMode === "data-lab-result-detail") {
      await loadResultDetailPage();
    }
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
