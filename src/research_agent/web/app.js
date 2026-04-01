const storageKeys = {
  token: "erp.session.token",
  workspaceId: "erp.workspace.id",
  caseId: "erp.knowledge.caseId",
};

const state = {
  token: localStorage.getItem(storageKeys.token) || "",
  user: null,
  workspaces: [],
  selectedWorkspaceId: localStorage.getItem(storageKeys.workspaceId) || "",
  labTemplates: [],
  integrations: [],
  privateBriefings: [],
  literatureEntries: [],
  workspaceAssets: [],
  workspaceKnowledge: [],
  workspaceCases: [],
  workspaceSchedules: [],
  knowledgeDetails: {},
  knowledgeRelated: {},
  caseDetails: {},
  selectedKnowledgeCaseId: localStorage.getItem(storageKeys.caseId) || "",
  selectedKnowledgeRecordId: "",
  knowledgeSearchQuery: "",
  knowledgeStatusFilter: "active",
  knowledgeTypeFilter: "all",
  knowledgeTagFilter: "all",
  editingKnowledgeRecordId: "",
  editingKnowledgeCaseId: "",
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
  optimizationCatalog: null,
  optimizationResults: [],
  currentOptimizationResult: null,
  variableGuideResult: null,
  resultPreviewUrls: [],
  currentResultDetail: null,
  publicSourceView: "official",
  publicSourceTypeFilter: "all",
  publicSourceCountryFilter: "all",
  publicSourceRegionFilter: "all",
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

const KNOWLEDGE_TEMPLATES = {
  research_memo: {
    label: "Research Memo",
    title: "Research Memo:",
    tags: ["memo", "workspace", "research"],
    content: `## Research question

- What question am I trying to answer?

## Why it matters

- Why does this matter for the project or workspace?

## Variables and evidence

- Outcome:
- Key explanatory variables:
- Data source:

## Next checks

-`,
  },
  reading_note: {
    label: "Reading Note",
    title: "Reading Note:",
    tags: ["reading-note", "literature", "review"],
    content: `## Citation

-

## Main contribution

-

## Variables and design

- Outcome:
- Treatment / shock:
- Controls:
- Identification:

## Follow-up questions

-`,
  },
  hypothesis_log: {
    label: "Hypothesis Log",
    title: "Hypothesis Log:",
    tags: ["hypothesis", "research-design"],
    content: `## Hypothesis

-

## Expected sign or effect

-

## Mechanism

-

## Risks to identification

-

## Next validation step

-`,
  },
  meeting_takeaway: {
    label: "Meeting Takeaway",
    title: "Meeting Takeaway:",
    tags: ["meeting", "internal-summary"],
    content: `## Decisions

-

## Open questions

-

## Assigned follow-ups

-

## Deadline or next review point

-`,
  },
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
  publicSourcePanel: document.getElementById("public-source-panel"),
  publicSourceView: document.getElementById("public-source-view"),
  publicSourceTypeFilter: document.getElementById("public-source-type-filter"),
  publicSourceCountryFilter: document.getElementById("public-source-country-filter"),
  publicSourceRegionFilter: document.getElementById("public-source-region-filter"),
  publicReviewNote: document.getElementById("public-review-note"),
  publicReviewList: document.getElementById("public-review-list"),
  publicExcludedList: document.getElementById("public-excluded-list"),
  publicClusterList: document.getElementById("public-cluster-list"),
  publicReadingList: document.getElementById("public-reading-list"),
  publicSummaryTitle: document.getElementById("public-summary-title"),
  publicSummaryMeta: document.getElementById("public-summary-meta"),
  publicSummaryView: document.getElementById("public-summary-view"),
  publicSummaryPages: document.getElementById("public-summary-pages"),
  publicSummaryFeatured: document.getElementById("public-summary-featured"),
  publicBriefingList: document.getElementById("public-briefing-list"),
  publicSnapshotGrid: document.getElementById("public-snapshot-grid"),
  refreshPublicButton: document.getElementById("refresh-public"),
  copyPublicLinkButton: document.getElementById("copy-public-link"),
  sessionIndicator: document.getElementById("session-indicator"),
  userSummary: document.getElementById("user-summary"),
  workspaceSelect: document.getElementById("workspace-select"),
  cockpitWorkspaceName: document.getElementById("cockpit-workspace-name"),
  cockpitWorkspaceMeta: document.getElementById("cockpit-workspace-meta"),
  cockpitNextActionTitle: document.getElementById("cockpit-next-action-title"),
  cockpitNextActionCopy: document.getElementById("cockpit-next-action-copy"),
  cockpitStatGrid: document.getElementById("cockpit-stat-grid"),
  cockpitStepGrid: document.getElementById("cockpit-step-grid"),
  cockpitLinkageGrid: document.getElementById("cockpit-linkage-grid"),
  cockpitActionList: document.getElementById("cockpit-action-list"),
  cockpitActivityList: document.getElementById("cockpit-activity-list"),
  cockpitFlowList: document.getElementById("cockpit-flow-list"),
  integrationList: document.getElementById("integration-list"),
  integrationProviderHint: document.getElementById("integration-provider-hint"),
  integrationProviderDocs: document.getElementById("integration-provider-docs"),
  briefingList: document.getElementById("briefing-list"),
  openalexResults: document.getElementById("openalex-results"),
  literatureList: document.getElementById("literature-list"),
  assetList: document.getElementById("asset-list"),
  knowledgeCaseSummaryGrid: document.getElementById("knowledge-case-summary-grid"),
  knowledgeCaseList: document.getElementById("knowledge-case-list"),
  knowledgeCasePreview: document.getElementById("knowledge-case-preview"),
  knowledgeCaseFormTitle: document.getElementById("knowledge-case-form-title"),
  knowledgeCaseFormStatus: document.getElementById("knowledge-case-form-status"),
  knowledgeCaseSubmitButton: document.getElementById("knowledge-case-submit-button"),
  knowledgeCaseCancelButton: document.getElementById("knowledge-case-cancel-button"),
  knowledgeCaseActiveSelect: document.getElementById("active-case-select"),
  knowledgeList: document.getElementById("knowledge-list"),
  knowledgeSummaryGrid: document.getElementById("knowledge-summary-grid"),
  knowledgeLinkageGrid: document.getElementById("knowledge-linkage-grid"),
  knowledgeSearchForm: document.getElementById("knowledge-search-form"),
  knowledgeSearchInput: document.getElementById("knowledge-search-input"),
  knowledgeStatusFilter: document.getElementById("knowledge-status-filter"),
  knowledgeTypeFilter: document.getElementById("knowledge-type-filter"),
  knowledgeTagFilter: document.getElementById("knowledge-tag-filter"),
  knowledgeResetButton: document.getElementById("knowledge-reset-button"),
  knowledgePreview: document.getElementById("knowledge-preview"),
  knowledgeFormTitle: document.getElementById("knowledge-form-title"),
  knowledgeFormStatus: document.getElementById("knowledge-form-status"),
  knowledgeSubmitButton: document.getElementById("knowledge-submit-button"),
  knowledgeCancelButton: document.getElementById("knowledge-cancel-button"),
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
  labCaseSelect: document.getElementById("lab-case-select"),
  labCaseMeta: document.getElementById("lab-case-meta"),
  labCaseHomeLink: document.getElementById("lab-case-home-link"),
  labContextNextAction: document.getElementById("lab-context-next-action"),
  labContextDetailLink: document.getElementById("lab-context-detail-link"),
  labActiveFamilyEyebrow: document.getElementById("lab-active-family-eyebrow"),
  labActiveFamilyTitle: document.getElementById("lab-active-family-title"),
  labActiveFamilySummary: document.getElementById("lab-active-family-summary"),
  labActiveFamilyMethods: document.getElementById("lab-active-family-methods"),
  labActiveFamilyChecks: document.getElementById("lab-active-family-checks"),
  labActiveFamilyLink: document.getElementById("lab-active-family-link"),
  labRunDesignTitle: document.getElementById("lab-run-design-title"),
  labRunDesignCopy: document.getElementById("lab-run-design-copy"),
  labRunDesignSurfaces: document.getElementById("lab-run-design-surfaces"),
  labRunDesignChecks: document.getElementById("lab-run-design-checks"),
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
  labModelMethodEyebrow: document.getElementById("lab-model-method-eyebrow"),
  labModelMethodTitle: document.getElementById("lab-model-method-title"),
  labModelMethodSummary: document.getElementById("lab-model-method-summary"),
  labModelMethodFamily: document.getElementById("lab-model-method-family"),
  labModelMethodHeading: document.getElementById("lab-model-method-heading"),
  labModelMethodDescription: document.getElementById("lab-model-method-description"),
  labModelMethodFamilyLink: document.getElementById("lab-model-method-family-link"),
  labModelMethodTeachingLink: document.getElementById("lab-model-method-teaching-link"),
  labModelMethodWorkbenchLink: document.getElementById("lab-model-method-workbench-link"),
  labModelMethodEquation: document.getElementById("lab-model-method-equation"),
  labModelMethodInputs: document.getElementById("lab-model-method-inputs"),
  labModelMethodOutputs: document.getElementById("lab-model-method-outputs"),
  labModelMethodPaper: document.getElementById("lab-model-method-paper"),
  labModelMethodPreview: document.getElementById("lab-model-method-preview"),
  labModelMethodAudit: document.getElementById("lab-model-method-audit"),
  labModelMethodSnapshot: document.getElementById("lab-model-method-snapshot"),
  labModelMethodRunbook: document.getElementById("lab-model-method-runbook"),
  labTeachingEyebrow: document.getElementById("lab-teaching-eyebrow"),
  labTeachingTitle: document.getElementById("lab-teaching-title"),
  labTeachingSummary: document.getElementById("lab-teaching-summary"),
  labTeachingFamily: document.getElementById("lab-teaching-family"),
  labTeachingHeading: document.getElementById("lab-teaching-heading"),
  labTeachingDescription: document.getElementById("lab-teaching-description"),
  labTeachingMethodLink: document.getElementById("lab-teaching-method-link"),
  labTeachingWorkbenchLink: document.getElementById("lab-teaching-workbench-link"),
  labTeachingSections: document.getElementById("lab-teaching-sections"),
  labTeachingPaper: document.getElementById("lab-teaching-paper"),
  labTeachingPreview: document.getElementById("lab-teaching-preview"),
  labTeachingSnapshot: document.getElementById("lab-teaching-snapshot"),
  labTeachingRunbook: document.getElementById("lab-teaching-runbook"),
  labResultEyebrow: document.getElementById("lab-result-eyebrow"),
  labResultTitle: document.getElementById("lab-result-title"),
  labResultSummary: document.getElementById("lab-result-summary"),
  labResultType: document.getElementById("lab-result-type"),
  labResultHeading: document.getElementById("lab-result-heading"),
  labResultDescription: document.getElementById("lab-result-description"),
  labResultWorkbenchLink: document.getElementById("lab-result-workbench-link"),
  labResultMetrics: document.getElementById("lab-result-metrics"),
  labResultInterpretation: document.getElementById("lab-result-interpretation"),
  labResultSpecification: document.getElementById("lab-result-specification"),
  labResultTables: document.getElementById("lab-result-tables"),
  labResultAudit: document.getElementById("lab-result-audit"),
  labResultPreview: document.getElementById("lab-result-preview"),
  labResultGallery: document.getElementById("lab-result-gallery"),
  labResultRaw: document.getElementById("lab-result-raw"),
  labResultSnapshot: document.getElementById("lab-result-snapshot"),
  labResultActions: document.getElementById("lab-result-actions"),
  labResultExportBoard: document.getElementById("lab-result-export-board"),
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
  const response = await fetch(path, { credentials: "same-origin", ...options, headers });
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

function normalizePublicMonitorViewSlug(slug) {
  const value = (slug || "").trim().toLowerCase();
  if (!value) {
    return "official";
  }
  if (value === "all") {
    return "all";
  }
  if (value === "official" || value === "official-first") {
    return "official";
  }
  if (value === "us" || value === "united-states") {
    return "us";
  }
  if (value === "cn" || value === "china") {
    return "cn";
  }
  if (value === "developed" || value === "developed-markets") {
    return "developed";
  }
  return "official";
}

function publicMonitorPathForView(view) {
  const normalized = normalizePublicMonitorViewSlug(view);
  if (normalized === "official") {
    return "/public-monitor";
  }
  if (normalized === "all") {
    return "/public-monitor/all";
  }
  if (normalized === "us") {
    return "/public-monitor/us";
  }
  if (normalized === "cn") {
    return "/public-monitor/china";
  }
  if (normalized === "developed") {
    return "/public-monitor/developed-markets";
  }
  return "/public-monitor";
}

function extractPublicMonitorViewRoute() {
  const match = window.location.pathname.match(/^\/(?:public-monitor|macro-desk)(?:\/([^/]+))?$/);
  if (!match) {
    return "";
  }
  return normalizePublicMonitorViewSlug(match[1] || "");
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

function extractDataLabModelMethodRoute() {
  const match = window.location.pathname.match(/^\/data-lab\/models\/([^/]+)\/([^/]+)$/);
  if (!match) {
    return null;
  }
  return {
    family: decodeURIComponent(match[1]),
    method: decodeURIComponent(match[2]),
  };
}

function extractDataLabTeachingRoute() {
  const match = window.location.pathname.match(/^\/data-lab\/learn\/models\/([^/]+)\/([^/]+)$/);
  if (!match) {
    return null;
  }
  return {
    family: decodeURIComponent(match[1]),
    method: decodeURIComponent(match[2]),
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

function extractOptimizationResultRoute() {
  const match = window.location.pathname.match(/^\/(?:optimization-lab\/results|data-lab\/results\/optimization)\/([^/]+)$/);
  if (!match) {
    return null;
  }
  return { id: decodeURIComponent(match[1]) };
}

function detectPageMode() {
  if (window.location.pathname === "/") {
    return "home";
  }
  if (window.location.pathname === "/data-lab") {
    return "data-lab";
  }
  if (extractDataLabTeachingRoute()) {
    return "data-lab-teaching";
  }
  if (extractDataLabModelMethodRoute()) {
    return "data-lab-model-method";
  }
  if (extractDataLabMethodRoute()) {
    return "data-lab-method-detail";
  }
  if (extractDataLabResultRoute()) {
    return "data-lab-result-detail";
  }
  if (extractOptimizationResultRoute()) {
    return "optimization-result-detail";
  }
  if (extractPublicMonitorViewRoute()) {
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

function isTrustedLocalHost() {
  const host = (window.location.hostname || "").toLowerCase();
  return !host || host === "localhost" || host === "127.0.0.1" || host === "::1" || host === "testserver";
}

function shouldLockExperience() {
  return detectPageMode() !== "home" && !state.user;
}

function renderPrivateNavigationState() {
  const shouldHide = !state.user;
  document.querySelectorAll("[data-private-nav]").forEach((element) => {
    element.classList.toggle("hidden", shouldHide);
  });
}

function renderHomeSessionSections() {
  const show = detectPageMode() === "home" && Boolean(state.user);
  document.querySelectorAll("[data-home-session-only]").forEach((element) => {
    element.classList.toggle("hidden", !show);
  });
}

function renderAuthSurface() {
  const pageMode = detectPageMode();
  const hasAuthForms = Boolean(document.getElementById("register-form") || document.getElementById("login-form"));
  const showHomeForms = pageMode === "home" && !state.user;
  renderHomeSessionSections();
  document.querySelectorAll("[data-auth-form]").forEach((element) => {
    element.classList.toggle("hidden", !showHomeForms);
  });
  toggleHidden(dom.workspaceBox, !state.user);
  toggleHidden(dom.sessionSignoutButton, !state.user);
  dom.authGrid?.classList.toggle("auth-grid-logged-in", Boolean(state.user));
  if (!dom.authPanelTitle || !dom.authPanelCopy) {
    return;
  }
  if (!state.user) {
    if (pageMode === "home") {
      dom.authPanelTitle.textContent = "Private Workspace Access";
      dom.authPanelCopy.textContent = "Sign in to unlock Data Lab, Provider Center, Paper Library, the Private Knowledge Base, and all other private modules.";
    } else {
      dom.authPanelTitle.textContent = "Workspace Session";
      dom.authPanelCopy.textContent = "Return to the homepage to sign in, then come back here to use the private workspace.";
    }
    if (!hasAuthForms && !state.user) {
      toggleHidden(dom.workspaceBox, true);
    }
    return;
  }
  dom.authPanelTitle.textContent = pageMode === "home" ? "Workspace Session" : "Private Workspace Session";
  dom.authPanelCopy.textContent = "You are signed in. Select a workspace, create a new one if needed, and continue into the private modules without re-entering credentials.";
}

function applyAccessGateState() {
  const gates = Array.from(document.querySelectorAll("[data-access-gate]"));
  if (!gates.length) {
    renderPrivateNavigationState();
    renderHomeSessionSections();
    return;
  }
  const shouldLock = shouldLockExperience();
  document.body.classList.toggle("experience-locked", shouldLock);
  gates.forEach((gate) => gate.classList.toggle("hidden", !shouldLock));
  renderPrivateNavigationState();
  renderHomeSessionSections();
}

function isExperienceLocked() {
  return document.body.classList.contains("experience-locked");
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
  const payload = await api("/api/data-lab/catalog");
  state.dataLabCatalog = payload;
  return payload;
}

async function loadOptimizationCatalog() {
  if (state.optimizationCatalog) {
    return state.optimizationCatalog;
  }
  const payload = await api("/api/optimization/catalog");
  state.optimizationCatalog = payload;
  return payload;
}

function optimizationElement(id) {
  return document.getElementById(id);
}

function setMultiSelectValues(element, values) {
  if (!element) {
    return;
  }
  const selected = new Set(values || []);
  Array.from(element.options).forEach((option) => {
    option.selected = selected.has(option.value);
  });
}

function selectedValues(element) {
  if (!element) {
    return [];
  }
  return Array.from(element.selectedOptions || []).map((option) => option.value).filter(Boolean);
}

async function ensureAuthenticatedUser() {
  if (state.user) {
    return state.user;
  }
  const payload = await api("/api/auth/me", {}, false);
  if (!payload?.user) {
    throw new Error("Sign in on the homepage before opening private result details.");
  }
  state.user = payload.user;
  state.workspaces = payload.workspaces || [];
  return state.user;
}

async function maybeLoadPublicIdentity() {
  if (state.user) {
    return state.user;
  }
  try {
    const payload = await api("/api/auth/me", {}, false);
    if (!payload?.user) {
      state.user = null;
      state.workspaces = [];
      return null;
    }
    state.user = payload.user;
    state.workspaces = payload.workspaces || [];
    return state.user;
  } catch {
    state.user = null;
    state.workspaces = [];
    return null;
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

function renderPaperTemplateCards(target, sections) {
  if (!target) {
    return;
  }
  if (!sections || !sections.length) {
    target.innerHTML = emptyCard("No paper-template metadata is available for this method yet.");
    return;
  }
  target.innerHTML = sections
    .map(
      (section) => `
        <article class="card paper-template-card">
          <p class="eyebrow eyebrow-compact">${escapeHtml(section.title || "Template Section")}</p>
          <p>${escapeHtml(section.body || "")}</p>
          ${
            Array.isArray(section.items) && section.items.length
              ? `
                <ul class="detail-bullet-list">
                  ${section.items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
                </ul>
              `
              : ""
          }
        </article>
      `,
    )
    .join("");
}

function renderPaperTablePreviewCards(target, tables) {
  if (!target) {
    return;
  }
  if (!tables || !tables.length) {
    target.innerHTML = emptyCard("No paper-style table preview is available for this method yet.");
    return;
  }
  target.innerHTML = tables
    .map((table) => {
      const columns = Array.isArray(table.columns) ? table.columns : [];
      const rows = Array.isArray(table.rows) ? table.rows : [];
      const headers = columns.length
        ? `<tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr>`
        : "";
      const body = rows.length
        ? rows
            .map(
              (row) =>
                `<tr>${(Array.isArray(row) ? row : []).map((cell) => `<td>${escapeHtml(cell ?? "")}</td>`).join("")}</tr>`,
            )
            .join("")
        : `<tr><td>${escapeHtml("Preview rows are not available.")}</td></tr>`;
      return `
        <article class="card paper-template-card paper-table-preview-card">
          <p class="eyebrow eyebrow-compact">${escapeHtml(table.title || "Paper Table Preview")}</p>
          ${table.note ? `<p>${escapeHtml(table.note)}</p>` : ""}
          <div class="table-shell">
            <table class="data-table paper-preview-table">
              <thead>${headers}</thead>
              <tbody>${body}</tbody>
            </table>
          </div>
        </article>
      `;
    })
    .join("");
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

function mergePlainObjects(...values) {
  const merged = {};
  for (const value of values) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      continue;
    }
    Object.assign(merged, value);
  }
  return merged;
}

function findCurrentModelMethodDetail() {
  const family = state.dataLabCatalog?.model_families?.find((item) => item.slug === currentModelFamily());
  if (!family) {
    return null;
  }
  return (family.methods || []).find((item) => item.slug === (dom.modelType?.value || "")) || null;
}

function labBuilderElement(prefix, suffix) {
  return document.getElementById(`${prefix}-${suffix}`);
}

function getProcessingVariantPresets() {
  const family = state.dataLabCatalog?.processing_families?.find((item) => item.slug === currentProcessingFamily());
  return family?.variant_presets || [];
}

function getModelVariantPresets() {
  const detail = findCurrentModelMethodDetail();
  if (detail?.variant_presets?.length) {
    return detail.variant_presets;
  }
  const family = state.dataLabCatalog?.model_families?.find((item) => item.slug === currentModelFamily());
  return family?.variant_presets || [];
}

function getOptimizationVariantPresets() {
  return state.optimizationCatalog?.variant_presets || [];
}

function templateContextForPrefix(prefix) {
  if (prefix === "prepare") {
    return {
      workflow_type: "data_processing",
      family: currentProcessingFamily(),
      method: "",
      variant_presets: getProcessingVariantPresets(),
      title: currentFamilyDetail()?.title || "Processing workflow",
    };
  }
  if (prefix === "model") {
    return {
      workflow_type: "model",
      family: currentModelFamily(),
      method: dom.modelType?.value || "",
      variant_presets: getModelVariantPresets(),
      title: currentModelLabel(),
    };
  }
  return {
    workflow_type: "optimization",
    family: "optimization",
    method: "suite",
    variant_presets: getOptimizationVariantPresets(),
    title: "Optimization suite",
  };
}

function filteredTemplatesForContext(context) {
  return (state.labTemplates || []).filter((item) => {
    if (item.workflow_type !== context.workflow_type) {
      return false;
    }
    if (item.family && context.family && item.family !== context.family) {
      return false;
    }
    if (item.method && context.method && item.method !== context.method) {
      return false;
    }
    return true;
  });
}

function updateBuilderStatus(prefix, message) {
  const target = labBuilderElement(prefix, "template-status");
  if (target) {
    target.textContent = message;
  }
}

function renderLabTemplateBuilder(prefix) {
  const context = templateContextForPrefix(prefix);
  const templateSelect = labBuilderElement(prefix, "template-select");
  const variantSelect = labBuilderElement(prefix, "variant-select");
  const variantJson = labBuilderElement(prefix, "variant-json");
  if (!templateSelect && !variantSelect && !variantJson) {
    return;
  }
  const templates = filteredTemplatesForContext(context);
  const previousTemplate = templateSelect?.value || "";
  const previousVariant = variantSelect?.value || "";
  if (templateSelect) {
    templateSelect.innerHTML = [
      `<option value="">No saved template</option>`,
      ...templates.map(
        (item) =>
          `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}${item.is_default ? " (Default)" : ""}</option>`,
      ),
    ].join("");
    if (templates.some((item) => item.id === previousTemplate)) {
      templateSelect.value = previousTemplate;
    } else {
      const defaultTemplate = templates.find((item) => item.is_default);
      templateSelect.value = defaultTemplate?.id || "";
    }
  }
  if (variantSelect) {
    variantSelect.innerHTML = [
      `<option value="">No preset variant</option>`,
      ...context.variant_presets.map(
        (item, index) =>
          `<option value="${escapeHtml(String(index))}">${escapeHtml(item.label || `Preset ${index + 1}`)}</option>`,
      ),
    ].join("");
    if (context.variant_presets.some((_, index) => String(index) === previousVariant)) {
      variantSelect.value = previousVariant;
    }
  }
  if (variantJson && !variantJson.dataset.boundPreset) {
    variantJson.value = "";
  }
  const selectedTemplate = templates.find((item) => item.id === (templateSelect?.value || ""));
  const selectedPreset = currentVariantPreset(prefix);
  updateBuilderStatus(
    prefix,
    `${templates.length} template${templates.length === 1 ? "" : "s"} | ${context.variant_presets.length} preset variant${context.variant_presets.length === 1 ? "" : "s"} for ${context.title}.${selectedTemplate ? ` Active template: ${selectedTemplate.name}.` : ""}${selectedPreset ? ` Active preset: ${selectedPreset.label || "Preset variant"}.` : ""}`,
  );
}

function renderAllLabTemplateBuilders() {
  renderLabTemplateBuilder("prepare");
  renderLabTemplateBuilder("model");
  renderLabTemplateBuilder("optimization");
}

function currentVariantPreset(prefix) {
  const select = labBuilderElement(prefix, "variant-select");
  const context = templateContextForPrefix(prefix);
  const index = Number(select?.value || -1);
  return Number.isInteger(index) && index >= 0 ? context.variant_presets[index] || null : null;
}

function parseVariantSpec(prefix) {
  const preset = currentVariantPreset(prefix);
  const textarea = labBuilderElement(prefix, "variant-json");
  const raw = String(textarea?.value || "").trim();
  let parsed = {};
  if (raw) {
    try {
      const value = JSON.parse(raw);
      if (!value || typeof value !== "object" || Array.isArray(value)) {
        throw new Error("Advanced specification must be a JSON object.");
      }
      parsed = value;
    } catch (error) {
      throw new Error(`${templateContextForPrefix(prefix).title}: ${error.message || "Invalid JSON in advanced specification."}`);
    }
  }
  const merged = mergePlainObjects(preset?.spec || {}, parsed);
  const labels = [preset?.label || "", raw ? "Custom override" : ""].filter(Boolean);
  return {
    template_id: String(labBuilderElement(prefix, "template-select")?.value || "").trim(),
    variant_label: labels.join(" + "),
    variant_spec: merged,
  };
}

function compactPayload(value) {
  if (Array.isArray(value)) {
    const items = value
      .map((item) => compactPayload(item))
      .filter((item) => item !== undefined);
    return items.length ? items : undefined;
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value)
      .map(([key, item]) => [key, compactPayload(item)])
      .filter(([, item]) => item !== undefined);
    return entries.length ? Object.fromEntries(entries) : undefined;
  }
  if (value === undefined || value === null) {
    return undefined;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed ? trimmed : undefined;
  }
  return value;
}

function valuesEqual(left, right) {
  if (Array.isArray(left) && Array.isArray(right)) {
    return left.length === right.length && left.every((item, index) => valuesEqual(item, right[index]));
  }
  if (left && typeof left === "object" && right && typeof right === "object") {
    const leftKeys = Object.keys(left);
    const rightKeys = Object.keys(right);
    return leftKeys.length === rightKeys.length && leftKeys.every((key) => valuesEqual(left[key], right[key]));
  }
  return left === right;
}

function stripDefaultValues(payload, defaults, requiredKeys = []) {
  const next = {};
  for (const [key, value] of Object.entries(payload || {})) {
    if (!requiredKeys.includes(key) && Object.prototype.hasOwnProperty.call(defaults || {}, key) && valuesEqual(value, defaults[key])) {
      continue;
    }
    next[key] = value;
  }
  return next;
}

const PREPARE_DEFAULTS = {
  workflow_group: "sample_preparation",
  include_columns: [],
  required_columns: [],
  numeric_columns: [],
  binary_columns: [],
  date_columns: [],
  impute_columns: [],
  impute_method: "none",
  winsorize_columns: [],
  winsor_lower_quantile: 0.01,
  winsor_upper_quantile: 0.99,
  log_transform_columns: [],
  standardize_columns: [],
  minmax_scale_columns: [],
  outlier_columns: [],
  outlier_method: "none",
  outlier_threshold: 1.5,
  sort_column: "",
  time_group_column: "",
  difference_columns: [],
  return_columns: [],
  return_method: "simple",
  lag_columns: [],
  lag_periods: 1,
  lead_columns: [],
  lead_periods: 1,
  rolling_mean_columns: [],
  rolling_volatility_columns: [],
  rolling_window: 5,
  drop_duplicates: true,
  drop_missing_required: true,
};

const MODEL_DEFAULTS = {
  model_family: "",
  model_type: "ols",
  dependent: "",
  independents: [],
  controls: [],
  series_columns: [],
  treatment_column: "",
  post_column: "",
  event_time_column: "",
  lead_window: 4,
  lag_window: 4,
  omitted_period: -1,
  origin_mass_column: "",
  destination_mass_column: "",
  distance_column: "",
  running_column: "",
  rdd_cutoff: 0,
  rdd_bandwidth: 0,
  rdd_polynomial_order: 1,
  treat_above_cutoff: true,
  entity_column: "",
  time_column: "",
  include_time_effects: false,
  endogenous_column: "",
  instrument_columns: [],
  market_column: "",
  risk_free_column: "",
  smb_column: "",
  hml_column: "",
  spot_column: "",
  strike_column: "",
  maturity_column: "",
  rate_column: "",
  volatility_column: "",
  working_capital_column: "",
  retained_earnings_column: "",
  ebit_column: "",
  market_equity_column: "",
  total_assets_column: "",
  total_liabilities_column: "",
  sales_column: "",
  net_income_column: "",
  revenue_column: "",
  equity_column: "",
  inflation_gap_column: "",
  output_gap_column: "",
  arima_p: 1,
  arima_d: 0,
  arima_q: 0,
  garch_p: 1,
  garch_q: 1,
  forecast_steps: 5,
  var_lags: 1,
  irf_horizon: 12,
  impulse_column: "",
  response_column: "",
  virf_shock_size: 1,
  bk_short_horizon: 5,
  bk_medium_horizon: 20,
  confidence_level: 0.95,
  holding_period_days: 1,
  ewma_lambda: 0.94,
  option_type: "call",
  option_steps: 50,
  risk_aversion: 3,
  long_only: true,
  dsge_alpha: 0.33,
  dsge_beta: 0.99,
  dsge_delta: 0.025,
  dsge_productivity: 1,
  dsge_labor: 0.33,
  dsge_shock_persistence: 0.9,
  dsge_shock_size: 0.01,
  dsge_impulse_horizon: 12,
  robust_covariance: true,
};

const OPTIMIZATION_DEFAULTS = {
  suite_label: "Optimization Suite",
  optimizer_names: [],
  function_names: [],
  dimension: 30,
  epoch: 50,
  pop_size: 30,
  runs: 5,
  workers: 0,
  seed_base: 20260331,
};

function buildPreparePayload(assetId) {
  const template = parseVariantSpec("prepare");
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
    drop_duplicates: dom.prepareForm?.querySelector('[name="drop_duplicates"]')?.checked ?? true,
    drop_missing_required: dom.prepareForm?.querySelector('[name="drop_missing_required"]')?.checked ?? true,
    template_id: template.template_id,
    variant_label: template.variant_label,
    variant_spec: template.variant_spec,
  };
  return compactPayload(stripDefaultValues(payload, PREPARE_DEFAULTS, ["asset_id", "workflow_group"]));
}

function buildModelPayload(assetId) {
  const modelType = dom.modelType?.value || "ols";
  const template = parseVariantSpec("model");
  const useSeriesTimeColumn = ["arima", "arch", "garch", "virf", "var", "svar_irf", "dy_connectedness", "bk_connectedness", "historical_var", "parametric_var", "ewma_volatility"].includes(modelType);
  const payload = {
    asset_id: assetId,
    model_family: dom.modelFamily?.value || "",
    model_type: modelType,
    dependent: dom.modelDependent?.value || "",
    independents: getSelectedValues(dom.modelIndependents),
    controls: getSelectedValues(dom.modelControls),
    series_columns: getSelectedValues(dom.modelSeriesColumns),
    treatment_column: modelType === "event_study" ? dom.eventTreatmentColumn?.value || "" : dom.didTreatmentColumn?.value || "",
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
    template_id: template.template_id,
    variant_label: template.variant_label,
    variant_spec: template.variant_spec,
  };
  return compactPayload(stripDefaultValues(payload, MODEL_DEFAULTS, ["asset_id", "model_family", "model_type"]));
}

function buildOptimizationPayload() {
  const template = parseVariantSpec("optimization");
  const payload = {
    suite_label: optimizationElement("optimization-suite-label")?.value || "Optimization Suite",
    optimizer_names: selectedValues(optimizationElement("optimization-optimizer-select")),
    function_names: selectedValues(optimizationElement("optimization-function-select")),
    dimension: Number(optimizationElement("optimization-dimension")?.value || 30),
    epoch: Number(optimizationElement("optimization-epoch")?.value || 50),
    pop_size: Number(optimizationElement("optimization-pop-size")?.value || 30),
    runs: Number(optimizationElement("optimization-runs")?.value || 5),
    workers: Number(optimizationElement("optimization-workers")?.value || 0),
    template_id: template.template_id,
    variant_label: template.variant_label,
    variant_spec: template.variant_spec,
  };
  return compactPayload(stripDefaultValues(payload, OPTIMIZATION_DEFAULTS, ["suite_label", "optimizer_names", "function_names"]));
}

async function saveCurrentLabTemplate(prefix) {
  ensureWorkspace();
  const context = templateContextForPrefix(prefix);
  let specification = {};
  if (prefix === "prepare") {
    const assetId = dom.analysisAssetSelect?.value || state.selectedAnalysisAssetId;
    if (!assetId) {
      throw new Error("Select a dataset asset before saving a processing template.");
    }
    specification = buildPreparePayload(assetId);
    delete specification.asset_id;
  } else if (prefix === "model") {
    const assetId = dom.analysisAssetSelect?.value || state.selectedAnalysisAssetId;
    if (!assetId) {
      throw new Error("Select a dataset asset before saving a model template.");
    }
    specification = buildModelPayload(assetId);
    delete specification.asset_id;
  } else {
    specification = buildOptimizationPayload();
  }
  const defaultName = `${context.title} Template`;
  const name = window.prompt("Template name", defaultName);
  if (!name) {
    updateBuilderStatus(prefix, "Template save cancelled.");
    return;
  }
  const description = window.prompt("Optional description", `Reusable ${context.title.toLowerCase()} configuration.`) || "";
  const isDefault = window.confirm("Set this as the default template for this family?");
  const payload = compactPayload({
    template_scope: "workspace",
    workflow_type: context.workflow_type,
    family: context.family,
    method: context.method,
    name,
    description,
    specification,
    metadata: {
      title: context.title,
      saved_from_page: detectPageMode(),
      saved_at: new Date().toISOString(),
    },
    is_default: isDefault,
  });
  const response = await api(`/api/workspaces/${state.selectedWorkspaceId}/lab-templates`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await refreshWorkspaceData();
  const templateSelect = labBuilderElement(prefix, "template-select");
  if (templateSelect && response.template?.id) {
    templateSelect.value = response.template.id;
  }
  updateBuilderStatus(prefix, `Saved template "${response.template?.name || name}".`);
}

function applyVariantPresetSelection(prefix) {
  const textarea = labBuilderElement(prefix, "variant-json");
  if (!textarea) {
    return;
  }
  const preset = currentVariantPreset(prefix);
  if (!preset) {
    if (textarea.dataset.boundPreset === "1") {
      textarea.value = "";
    }
    textarea.dataset.boundPreset = "0";
    renderLabTemplateBuilder(prefix);
    return;
  }
  textarea.value = JSON.stringify(preset.spec || {}, null, 2);
  textarea.dataset.boundPreset = "1";
  updateBuilderStatus(prefix, `Preset selected: ${preset.label || "Preset variant"}.`);
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

function currentWorkspace() {
  return state.workspaces.find((item) => item.id === state.selectedWorkspaceId) || null;
}

function currentKnowledgeCase() {
  return state.workspaceCases.find((item) => item.id === state.selectedKnowledgeCaseId) || null;
}

function knowledgeTypeSpec(item) {
  const metadata = item?.metadata || {};
  const derivativeMode = String(metadata.derivative_mode || "").trim();
  const noteTemplate = String(metadata.note_template || "").trim();
  if (metadata.model_type || metadata.workflow_type === "model") {
    return {
      key: "model_result",
      label: "Model Result",
      description: metadata.model_label || metadata.model_type || "Saved model output",
      relatedPath: metadata.result_detail_path || `/data-lab/results/models/${item.id}`,
    };
  }
  if (metadata.source_type === "paper_library") {
    if (derivativeMode === "summary") {
      return { key: "paper_summary", label: "Paper Summary", description: "Condensed literature takeaway" };
    }
    if (derivativeMode === "annotation") {
      return { key: "paper_annotation", label: "Paper Annotation", description: "Structured reading template" };
    }
    if (derivativeMode === "question_breakdown") {
      return { key: "paper_questions", label: "Question Breakdown", description: "Variables and follow-up checklist" };
    }
    return { key: "paper_note", label: "Paper Note", description: "Imported literature note" };
  }
  if (metadata.briefing_id) {
    return { key: "briefing_note", label: "Briefing Note", description: "Generated from a private daily briefing" };
  }
  if (metadata.source_type === "workspace_digest") {
    return { key: "workspace_digest", label: "Workspace Digest", description: "Cross-module digest created from recent workspace materials" };
  }
  if (noteTemplate && KNOWLEDGE_TEMPLATES[noteTemplate]) {
    return {
      key: `template_${noteTemplate}`,
      label: KNOWLEDGE_TEMPLATES[noteTemplate].label,
      description: "Manual note created from a workspace template",
    };
  }
  return { key: "manual_note", label: "Manual Note", description: "Workspace-authored note or memo" };
}

function knowledgeSourceCategory(item) {
  const spec = knowledgeTypeSpec(item);
  if (spec.key === "model_result") {
    return {
      key: "model",
      label: "Data Lab model outputs",
      description: "Model results saved from Data Lab into reusable private notes.",
    };
  }
  if (spec.key === "briefing_note") {
    return {
      key: "briefing",
      label: "Briefing notes",
      description: "Private briefings captured into the knowledge base.",
    };
  }
  if (spec.key === "workspace_digest") {
    return {
      key: "digest",
      label: "Workspace digests",
      description: "Cross-module synthesis notes built from recent workspace materials.",
    };
  }
  if (spec.key.startsWith("paper_")) {
    return {
      key: "literature",
      label: "Literature notes",
      description: "Imported papers and follow-up reading notes from the Paper Library.",
    };
  }
  return {
    key: "manual",
    label: "Manual notes",
    description: "Workspace-authored memos, checklists, and freeform notes.",
  };
}

function summarizeKnowledgeSourceCounts(items) {
  const buckets = new Map();
  (items || []).forEach((item) => {
    const source = knowledgeSourceCategory(item);
    const current = buckets.get(source.key) || { ...source, count: 0 };
    current.count += 1;
    buckets.set(source.key, current);
  });
  return [...buckets.values()].sort((left, right) => right.count - left.count);
}

function knowledgeSearchableText(item) {
  const metadata = item?.metadata || {};
  const tags = Array.isArray(item?.tags) ? item.tags.join(" ") : "";
  return [
    item?.title,
    item?.content_excerpt,
    item?.content,
    tags,
    metadata.citation_text,
    metadata.model_type,
    metadata.model_label,
    metadata.derivative_mode,
    metadata.note_template,
    metadata.venue,
    metadata.doi,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function collectKnowledgeTags(items) {
  const tags = new Set();
  (items || []).forEach((item) => {
    (item.tags || []).forEach((tag) => {
      const normalized = String(tag || "").trim();
      if (normalized) {
        tags.add(normalized);
      }
    });
  });
  return [...tags].sort((left, right) => left.localeCompare(right));
}

function buildKnowledgeTypeOptions(items) {
  const options = [{ value: "all", label: "All note types" }];
  const seen = new Set(["all"]);
  (items || []).forEach((item) => {
    const spec = knowledgeTypeSpec(item);
    if (!seen.has(spec.key)) {
      seen.add(spec.key);
      options.push({ value: spec.key, label: spec.label });
    }
  });
  return options;
}

function filteredKnowledgeItems(items = state.workspaceKnowledge) {
  const query = String(state.knowledgeSearchQuery || "").trim().toLowerCase();
  return [...(items || [])].filter((item) => {
    const archived = isKnowledgeArchived(item);
    if (state.knowledgeStatusFilter === "active" && archived) {
      return false;
    }
    if (state.knowledgeStatusFilter === "archived" && !archived) {
      return false;
    }
    const typeSpec = knowledgeTypeSpec(item);
    if (state.knowledgeTypeFilter !== "all" && typeSpec.key !== state.knowledgeTypeFilter) {
      return false;
    }
    if (state.knowledgeTagFilter !== "all" && !(item.tags || []).includes(state.knowledgeTagFilter)) {
      return false;
    }
    if (query && !knowledgeSearchableText(item).includes(query)) {
      return false;
    }
    return true;
  });
}

function mergeKnowledgeRecord(recordId) {
  const summaryRecord = (state.workspaceKnowledge || []).find((item) => item.id === recordId) || null;
  const detailRecord = state.knowledgeDetails[recordId] || null;
  if (!summaryRecord && !detailRecord) {
    return null;
  }
  return {
    ...(summaryRecord || {}),
    ...(detailRecord || {}),
    metadata: {
      ...(summaryRecord?.metadata || {}),
      ...(detailRecord?.metadata || {}),
    },
    tags: detailRecord?.tags || summaryRecord?.tags || [],
  };
}

function isKnowledgeArchived(item) {
  return Boolean(item?.is_archived);
}

function resetKnowledgeComposer() {
  const knowledgeForm = document.getElementById("knowledge-form");
  if (!knowledgeForm) {
    return;
  }
  knowledgeForm.reset();
  delete knowledgeForm.dataset.template;
  state.editingKnowledgeRecordId = "";
  const recordIdField = knowledgeForm.elements.namedItem("record_id");
  if (recordIdField) {
    recordIdField.value = "";
  }
  if (dom.knowledgeFormTitle) {
    dom.knowledgeFormTitle.textContent = "Create note";
  }
  if (dom.knowledgeFormStatus) {
    dom.knowledgeFormStatus.textContent = "Save a new private workspace note or use a template as a starting point.";
  }
  if (dom.knowledgeSubmitButton) {
    dom.knowledgeSubmitButton.textContent = "Save note";
  }
  toggleHidden(dom.knowledgeCancelButton, true);
}

function renderRelatedKnowledgeSection(items) {
  const relatedItems = items || [];
  if (!relatedItems.length) {
    return `
      <section class="knowledge-related-block">
        <h4>Related notes</h4>
        <p class="compact-note muted">No closely related private notes were found yet.</p>
      </section>
    `;
  }
  return `
    <section class="knowledge-related-block">
      <h4>Related notes</h4>
      <div class="card-list card-list-inline knowledge-related-list">
        ${relatedItems
          .map(
            (item) => `
              <article class="card compact-card">
                <h4>${escapeHtml(item.title)}</h4>
                <p class="compact-note">${escapeHtml(knowledgeTypeSpec(item).label)} | score ${escapeHtml(item.relation_score || 0)}</p>
                <p class="compact-note muted">${escapeHtml((item.relation_reasons || []).join(" | ") || item.content_excerpt || "Related workspace note")}</p>
                <div class="actions compact-actions">
                  <button type="button" class="secondary" data-open-knowledge-record="${escapeHtml(item.id)}">Open note</button>
                </div>
              </article>
            `,
          )
          .join("")}
      </div>
    </section>
  `;
}

async function startKnowledgeEdit(recordId) {
  const knowledgeForm = document.getElementById("knowledge-form");
  if (!knowledgeForm || !recordId) {
    return false;
  }
  const record = mergeKnowledgeRecord(recordId)?.content ? mergeKnowledgeRecord(recordId) : await loadKnowledgeDetail(recordId);
  if (!record) {
    return false;
  }
  state.editingKnowledgeRecordId = recordId;
  const recordIdField = knowledgeForm.elements.namedItem("record_id");
  const titleField = knowledgeForm.elements.namedItem("title");
  const tagsField = knowledgeForm.elements.namedItem("tags");
  const contentField = knowledgeForm.elements.namedItem("content");
  if (recordIdField) {
    recordIdField.value = record.id;
  }
  if (titleField) {
    titleField.value = record.title || "";
  }
  if (tagsField) {
    tagsField.value = (record.tags || []).join(", ");
  }
  if (contentField) {
    contentField.value = record.content || "";
  }
  if (dom.knowledgeFormTitle) {
    dom.knowledgeFormTitle.textContent = "Edit note";
  }
  if (dom.knowledgeFormStatus) {
    dom.knowledgeFormStatus.textContent = isKnowledgeArchived(record)
      ? "This archived note is loaded for editing. Restore it if you want it back in the default active view."
      : "Update the selected private note. Metadata and related links are preserved unless you explicitly change them.";
  }
  if (dom.knowledgeSubmitButton) {
    dom.knowledgeSubmitButton.textContent = "Update note";
  }
  toggleHidden(dom.knowledgeCancelButton, false);
  focusKnowledgeRecord(recordId);
  return true;
}

function renderKnowledgeFilterOptions(items) {
  if (dom.knowledgeStatusFilter) {
    dom.knowledgeStatusFilter.value = state.knowledgeStatusFilter;
  }
  const typeOptions = buildKnowledgeTypeOptions(items);
  if (!typeOptions.some((option) => option.value === state.knowledgeTypeFilter)) {
    state.knowledgeTypeFilter = "all";
  }
  if (dom.knowledgeTypeFilter) {
    dom.knowledgeTypeFilter.innerHTML = typeOptions
      .map(
        (option) =>
          `<option value="${escapeHtml(option.value)}"${option.value === state.knowledgeTypeFilter ? " selected" : ""}>${escapeHtml(option.label)}</option>`,
      )
      .join("");
  }
  const tags = collectKnowledgeTags(items);
  if (state.knowledgeTagFilter !== "all" && !tags.includes(state.knowledgeTagFilter)) {
    state.knowledgeTagFilter = "all";
  }
  if (dom.knowledgeTagFilter) {
    dom.knowledgeTagFilter.innerHTML = [
      `<option value="all"${state.knowledgeTagFilter === "all" ? " selected" : ""}>All tags</option>`,
      ...tags.map(
        (tag) =>
          `<option value="${escapeHtml(tag)}"${tag === state.knowledgeTagFilter ? " selected" : ""}>${escapeHtml(tag)}</option>`,
      ),
    ].join("");
  }
  if (dom.knowledgeSearchInput) {
    dom.knowledgeSearchInput.value = state.knowledgeSearchQuery;
  }
}

function renderKnowledgeSummary(items, filteredItems) {
  if (!dom.knowledgeSummaryGrid) {
    return;
  }
  if (!items.length) {
    dom.knowledgeSummaryGrid.innerHTML = "";
    renderKnowledgeLinkageBoard([]);
    return;
  }
  const typeCounts = new Map();
  items.forEach((item) => {
    const spec = knowledgeTypeSpec(item);
    typeCounts.set(spec.label, (typeCounts.get(spec.label) || 0) + 1);
  });
  const sourceCounts = summarizeKnowledgeSourceCounts(items);
  const archivedCount = items.filter((item) => isKnowledgeArchived(item)).length;
  const topTags = collectKnowledgeTags(items).slice(0, 4);
  const latestItem = [...items].sort((left, right) => new Date(right.updated_at || right.created_at || 0) - new Date(left.updated_at || left.created_at || 0))[0];
  const linkedRecordCount = items.filter((item) => {
    const metadata = item.metadata || {};
    return Boolean(
      metadata.result_detail_path ||
        metadata.briefing_id ||
        metadata.doi ||
        metadata.base_knowledge_record_id ||
        metadata.workspace_id,
    );
  }).length;
  dom.knowledgeSummaryGrid.innerHTML = `
    <article class="knowledge-summary-card">
      <span>Total notes</span>
      <strong>${escapeHtml(items.length)}</strong>
      <p class="muted">All private notes currently stored in this workspace.</p>
    </article>
    <article class="knowledge-summary-card">
      <span>Visible after filters</span>
      <strong>${escapeHtml(filteredItems.length)}</strong>
      <p class="muted">Current search and filter output for this workspace.</p>
    </article>
    <article class="knowledge-summary-card">
      <span>Archived notes</span>
      <strong>${escapeHtml(archivedCount)}</strong>
      <p class="muted">Hidden from the default active view until restored.</p>
    </article>
    <article class="knowledge-summary-card">
      <span>Top note types</span>
      <strong>${escapeHtml([...typeCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 2).map(([label]) => label).join(" / ") || "n/a")}</strong>
      <p class="muted">${escapeHtml([...typeCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3).map(([label, count]) => `${label}: ${count}`).join(" | ") || "No typed notes yet.")}</p>
    </article>
    <article class="knowledge-summary-card">
      <span>Top tags</span>
      <strong>${escapeHtml(topTags.join(", ") || "No tags")}</strong>
      <p class="muted">${escapeHtml(latestItem ? `Latest update: ${prettyDate(latestItem.updated_at || latestItem.created_at)}` : "No update history yet.")}</p>
    </article>
    <article class="knowledge-summary-card">
      <span>Linked from other modules</span>
      <strong>${escapeHtml(linkedRecordCount)}</strong>
      <p class="muted">Notes with a paper, briefing, model result, or digest link that can be traced back to another workspace surface.</p>
    </article>
    <article class="knowledge-summary-card">
      <span>Top source families</span>
      <strong>${escapeHtml(sourceCounts.slice(0, 2).map((item) => item.label).join(" / ") || "n/a")}</strong>
      <p class="muted">${escapeHtml(sourceCounts.slice(0, 3).map((item) => `${item.label}: ${item.count}`).join(" | ") || "No linked sources yet.")}</p>
    </article>
  `;
  renderKnowledgeLinkageBoard(items);
}

function renderKnowledgeLinkageBoard(items) {
  if (!dom.knowledgeLinkageGrid) {
    return;
  }
  if (!items.length) {
    dom.knowledgeLinkageGrid.innerHTML = "";
    return;
  }
  const sourceCounts = summarizeKnowledgeSourceCounts(items);
  const byKey = Object.fromEntries(sourceCounts.map((item) => [item.key, item]));
  const cards = [
    {
      eyebrow: "Paper Library",
      title: "Literature -> Knowledge",
      count: byKey.literature?.count || 0,
      copy: "Imported papers, summaries, annotations, and question breakdowns stay reusable inside the private workspace.",
      action: `<button type="button" class="secondary" data-scroll-target="paper-library-panel">Open Paper Library</button>`,
    },
    {
      eyebrow: "Private Briefing",
      title: "Briefings -> Knowledge",
      count: byKey.briefing?.count || 0,
      copy: "Private daily briefings can be captured into notes and re-used later in synthesis or case workspaces.",
      action: `<button type="button" class="secondary" data-scroll-target="private-briefing-panel">Open briefings</button>`,
    },
    {
      eyebrow: "Data Lab",
      title: "Model outputs -> Knowledge",
      count: byKey.model?.count || 0,
      copy: "Transparent model runs should end up here so the specification, tables, and result page remain traceable.",
      action: `<a href="/data-lab" class="button-link secondary-link">Open Data Lab</a>`,
    },
    {
      eyebrow: "Workspace",
      title: "Manual notes & digests",
      count: (byKey.manual?.count || 0) + (byKey.digest?.count || 0),
      copy: "Manual notes hold hypotheses and interpretation; digests turn recent workspace materials into a reusable synthesis layer.",
      action: `<button type="button" class="secondary" data-create-workspace-digest="true">Build workspace digest</button>`,
    },
  ];
  dom.knowledgeLinkageGrid.innerHTML = cards
    .map(
      (item) => `
        <article class="guide-card">
          <p class="eyebrow eyebrow-compact">${escapeHtml(item.eyebrow)}</p>
          <h4>${escapeHtml(item.title)}</h4>
          <p>${escapeHtml(item.copy)}</p>
          <div class="chip-row chip-row-compact">
            <span class="topic-chip">Count <strong>${escapeHtml(item.count)}</strong></span>
          </div>
          <div class="actions compact-actions">${item.action}</div>
        </article>
      `,
    )
    .join("");
}

function resetKnowledgeCaseComposer() {
  const caseForm = document.getElementById("knowledge-case-form");
  if (!caseForm) {
    return;
  }
  caseForm.reset();
  const caseIdField = caseForm.elements.namedItem("case_id");
  if (caseIdField) {
    caseIdField.value = "";
  }
  state.editingKnowledgeCaseId = "";
  if (dom.knowledgeCaseFormTitle) {
    dom.knowledgeCaseFormTitle.textContent = "Create case";
  }
  if (dom.knowledgeCaseFormStatus) {
    dom.knowledgeCaseFormStatus.textContent = "Create a private case file to group notes, papers, briefings, datasets, and Data Lab outputs.";
  }
  if (dom.knowledgeCaseSubmitButton) {
    dom.knowledgeCaseSubmitButton.textContent = "Save case";
  }
  dom.knowledgeCaseCancelButton?.classList.add("hidden");
}

function renderKnowledgeCaseSummary(cases) {
  if (!dom.knowledgeCaseSummaryGrid) {
    return;
  }
  const totalItems = (cases || []).reduce((sum, item) => sum + Number(item.item_count || 0), 0);
  const activeCase = currentKnowledgeCase();
  dom.knowledgeCaseSummaryGrid.innerHTML = `
    <article class="knowledge-summary-card">
      <span>Cases</span>
      <strong>${escapeHtml((cases || []).length)}</strong>
      <p class="muted">User-built private case files inside the current workspace.</p>
    </article>
    <article class="knowledge-summary-card">
      <span>Stored items</span>
      <strong>${escapeHtml(totalItems)}</strong>
      <p class="muted">Notes, papers, briefings, and Data Lab outputs linked into cases.</p>
    </article>
    <article class="knowledge-summary-card">
      <span>Active case</span>
      <strong>${escapeHtml(activeCase?.title || "No active case")}</strong>
      <p class="muted">${escapeHtml(activeCase ? `${activeCase.item_count || 0} linked items` : "Select a case to receive Data Lab results.")}</p>
    </article>
  `;
}

function syncKnowledgeCaseOptions() {
  const options = [`<option value="">No active case</option>`]
    .concat(
      (state.workspaceCases || []).map(
        (item) => `<option value="${escapeHtml(item.id)}"${item.id === state.selectedKnowledgeCaseId ? " selected" : ""}>${escapeHtml(item.title)}</option>`,
      ),
    )
    .join("");
  if (dom.knowledgeCaseActiveSelect) {
    dom.knowledgeCaseActiveSelect.innerHTML = options;
  }
  if (dom.labCaseSelect) {
    dom.labCaseSelect.innerHTML = options;
  }
  if (dom.labCaseMeta) {
    const currentCase = currentKnowledgeCase();
    dom.labCaseMeta.textContent = currentCase
      ? `${currentCase.item_count || 0} items currently linked. Processing and model outputs can be sent into this case from the cards below.`
      : "Choose a case to send processing results, model outputs, and datasets into the private workspace case file.";
  }
}

async function loadKnowledgeCaseDetail(caseId, force = false) {
  if (!caseId || !state.selectedWorkspaceId || !state.user) {
    return null;
  }
  if (!force && state.caseDetails[caseId]) {
    return state.caseDetails[caseId];
  }
  const response = await api(`/api/workspaces/${state.selectedWorkspaceId}/knowledge-cases/${caseId}`);
  state.caseDetails[caseId] = response;
  if (state.selectedKnowledgeCaseId === caseId) {
    renderKnowledgeCasePreview(response);
  }
  return response;
}

function startKnowledgeCaseEdit(caseId) {
  const caseForm = document.getElementById("knowledge-case-form");
  if (!caseForm) {
    return false;
  }
  const record = currentKnowledgeCase()?.id === caseId ? currentKnowledgeCase() : (state.workspaceCases || []).find((item) => item.id === caseId);
  if (!record) {
    return false;
  }
  state.editingKnowledgeCaseId = caseId;
  const caseIdField = caseForm.elements.namedItem("case_id");
  const titleField = caseForm.elements.namedItem("title");
  const tagsField = caseForm.elements.namedItem("tags");
  const descriptionField = caseForm.elements.namedItem("description");
  if (caseIdField) {
    caseIdField.value = record.id;
  }
  if (titleField) {
    titleField.value = record.title || "";
  }
  if (tagsField) {
    tagsField.value = (record.tags || []).join(", ");
  }
  if (descriptionField) {
    descriptionField.value = record.description || "";
  }
  if (dom.knowledgeCaseFormTitle) {
    dom.knowledgeCaseFormTitle.textContent = "Edit case";
  }
  if (dom.knowledgeCaseFormStatus) {
    dom.knowledgeCaseFormStatus.textContent = "Update the case title, scope, or labels before linking more workspace outputs.";
  }
  if (dom.knowledgeCaseSubmitButton) {
    dom.knowledgeCaseSubmitButton.textContent = "Update case";
  }
  dom.knowledgeCaseCancelButton?.classList.remove("hidden");
  return true;
}

function renderKnowledgeCasePreview(detail) {
  if (!dom.knowledgeCasePreview) {
    return;
  }
  const caseRecord = detail?.case || currentKnowledgeCase() || null;
  if (!caseRecord) {
    dom.knowledgeCasePreview.innerHTML = emptyCard("Create or select a case to organize private notes, papers, briefings, datasets, and Data Lab outputs.");
    return;
  }
  const items = detail?.items || state.caseDetails[caseRecord.id]?.items || [];
  dom.knowledgeCasePreview.innerHTML = `
    <article class="card knowledge-preview-card">
      <div class="panel-head panel-head-wrap">
        <div>
          <p class="eyebrow eyebrow-compact">Private case workspace</p>
          <h3>${escapeHtml(caseRecord.title)}</h3>
        </div>
        <div class="chip-row chip-row-compact">
          <span class="pill">${escapeHtml(prettyDate(caseRecord.updated_at || caseRecord.created_at))}</span>
          <span class="pill">${escapeHtml(caseRecord.item_count || items.length || 0)} items</span>
        </div>
      </div>
      <p class="muted">${escapeHtml(caseRecord.description || "No case description yet.")}</p>
      <div class="chip-row chip-row-compact">
        ${(caseRecord.tags || []).map((tag) => `<span class="topic-chip">${escapeHtml(tag)}</span>`).join("")}
      </div>
      <div class="actions compact-actions">
        <button type="button" class="secondary" data-edit-knowledge-case="${escapeHtml(caseRecord.id)}">Edit</button>
        <button type="button" class="secondary danger" data-delete-knowledge-case="${escapeHtml(caseRecord.id)}">Delete</button>
        <button type="button" class="secondary" data-scroll-target="knowledge-base-panel">Open knowledge notes</button>
        <a href="/data-lab" class="button-link secondary-link">Open Data Lab</a>
      </div>
      ${
        items.length
          ? `
            <div class="card-list card-list-inline">
              ${items
                .map(
                  (item) => `
                    <article class="card">
                      <p class="eyebrow eyebrow-compact">${escapeHtml(item.item_type.replaceAll("_", " "))}</p>
                      <h4>${escapeHtml(item.title || item.title_snapshot || "Linked item")}</h4>
                      <p class="compact-note muted">${escapeHtml(truncateText(item.summary || item.summary_snapshot || "No summary.", 180))}</p>
                      <div class="actions compact-actions">
                        ${item.detail_path ? `<a href="${escapeHtml(item.detail_path)}" class="button-link secondary-link">Open detail</a>` : ""}
                        ${item.download_path ? `<button type="button" class="secondary" data-download-asset="${escapeHtml(item.ref_id)}">Download</button>` : ""}
                        ${item.item_type === "knowledge_record" ? `<button type="button" class="secondary" data-open-knowledge-record="${escapeHtml(item.ref_id)}">Open note</button>` : ""}
                        ${item.source_url ? `<a href="${escapeHtml(item.source_url)}" class="button-link secondary-link" target="_blank" rel="noreferrer">Source</a>` : ""}
                        <button type="button" class="secondary danger" data-remove-case-item="${escapeHtml(item.id)}" data-case-id="${escapeHtml(caseRecord.id)}">Remove</button>
                      </div>
                      ${item.exists ? "" : `<p class="compact-note muted">The original item is no longer available. Snapshot preserved inside the case.</p>`}
                    </article>
                  `,
                )
                .join("")}
            </div>
          `
          : `<div class="card-list card-list-inline">${emptyCard("No linked items yet. Select this case, then import Data Lab outputs or other workspace materials into it.")}</div>`
      }
    </article>
  `;
}

function renderKnowledgeCases(items) {
  state.workspaceCases = items || [];
  if (state.selectedKnowledgeCaseId && !(state.workspaceCases || []).some((item) => item.id === state.selectedKnowledgeCaseId)) {
    state.selectedKnowledgeCaseId = "";
    localStorage.removeItem(storageKeys.caseId);
  }
  if (!state.selectedKnowledgeCaseId && state.workspaceCases.length) {
    state.selectedKnowledgeCaseId = state.workspaceCases[0].id;
    localStorage.setItem(storageKeys.caseId, state.selectedKnowledgeCaseId);
  }
  state.caseDetails = Object.fromEntries(
    Object.entries(state.caseDetails || {}).filter(([caseId]) => (state.workspaceCases || []).some((item) => item.id === caseId)),
  );
  renderKnowledgeCaseSummary(state.workspaceCases);
  syncKnowledgeCaseOptions();
  if (dom.knowledgeCaseList) {
    dom.knowledgeCaseList.innerHTML = state.workspaceCases.length
      ? state.workspaceCases
          .map(
            (item) => `
              <article class="card knowledge-card${item.id === state.selectedKnowledgeCaseId ? " is-selected" : ""}" data-knowledge-case-id="${escapeHtml(item.id)}">
                <div class="panel-head panel-head-wrap">
                  <div>
                    <h4>${escapeHtml(item.title)}</h4>
                    <p class="compact-note muted">${escapeHtml(item.description || "No description")}</p>
                  </div>
                  <span class="pill">${escapeHtml(item.item_count || 0)} items</span>
                </div>
                <div class="chip-row chip-row-compact">
                  ${(item.tags || []).slice(0, 5).map((tag) => `<span class="topic-chip">${escapeHtml(tag)}</span>`).join("")}
                </div>
                <div class="actions compact-actions">
                  <button type="button" class="secondary" data-select-knowledge-case="${escapeHtml(item.id)}">${item.id === state.selectedKnowledgeCaseId ? "Selected" : "Select"}</button>
                  <button type="button" class="secondary" data-edit-knowledge-case="${escapeHtml(item.id)}">Edit</button>
                </div>
              </article>
            `,
          )
          .join("")
      : emptyCard("No cases yet. Create one to collect notes, papers, briefings, and Data Lab outputs.");
  }
  if (state.selectedKnowledgeCaseId) {
    void loadKnowledgeCaseDetail(state.selectedKnowledgeCaseId);
  } else {
    renderKnowledgeCasePreview(null);
  }
  renderLabContext();
  renderWorkspaceCockpit();
}

function focusKnowledgeCase(caseId) {
  if (!caseId || !(state.workspaceCases || []).some((item) => item.id === caseId)) {
    return false;
  }
  state.selectedKnowledgeCaseId = caseId;
  localStorage.setItem(storageKeys.caseId, caseId);
  syncKnowledgeCaseOptions();
  renderKnowledgeCases(state.workspaceCases);
  dom.knowledgeCaseList?.querySelector(`[data-knowledge-case-id="${String(caseId).replaceAll('"', '\\"')}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  return true;
}

function renderKnowledgePreview(record, { loading = false } = {}) {
  if (!dom.knowledgePreview) {
    return;
  }
  if (!record) {
    dom.knowledgePreview.innerHTML = emptyCard("Select a note to inspect its full content, metadata, and source links.");
    return;
  }
  const typeSpec = knowledgeTypeSpec(record);
  const metadata = record.metadata || {};
  const tags = (record.tags || []).filter(Boolean);
  const archived = isKnowledgeArchived(record);
  const relatedItems = state.knowledgeRelated[record.id] || [];
  const relatedLinks = [];
  if (typeSpec.relatedPath) {
    relatedLinks.push(`<a href="${escapeHtml(typeSpec.relatedPath)}" class="button-link secondary-link">Open related detail</a>`);
  }
  if (metadata.landing_page_url) {
    relatedLinks.push(`<a href="${escapeHtml(metadata.landing_page_url)}" target="_blank" rel="noreferrer" class="button-link secondary-link">Open source page</a>`);
  }
  if (metadata.pdf_url) {
    relatedLinks.push(`<a href="${escapeHtml(metadata.pdf_url)}" target="_blank" rel="noreferrer" class="button-link secondary-link">Open source PDF</a>`);
  }
  if (metadata.briefing_id) {
    relatedLinks.push(`<button type="button" class="secondary" data-scroll-target="private-briefing-panel">Jump to briefings</button>`);
  }
  dom.knowledgePreview.innerHTML = `
    <article class="card knowledge-preview-card${archived ? " is-archived" : ""}">
      <div class="panel-head panel-head-wrap">
        <div>
          <p class="eyebrow eyebrow-compact">${escapeHtml(typeSpec.label)}</p>
          <h3>${escapeHtml(record.title || "Untitled note")}</h3>
        </div>
        <div class="chip-row chip-row-compact">
          ${archived ? `<span class="pill pill-archived">Archived</span>` : ""}
          <span class="pill">${escapeHtml(prettyDate(record.updated_at || record.created_at))}</span>
        </div>
      </div>
      <p class="muted">${escapeHtml(typeSpec.description || "Private knowledge record")}</p>
      <div class="chip-row chip-row-compact">
        <span class="topic-chip">Chars <strong>${escapeHtml(record.content_length || 0)}</strong></span>
        ${(tags || []).slice(0, 6).map((tag) => `<span class="topic-chip">${escapeHtml(tag)}</span>`).join("")}
      </div>
      <div class="actions compact-actions">
        <button type="button" class="secondary" data-edit-knowledge="${escapeHtml(record.id)}">Edit</button>
        <button type="button" class="secondary" data-${archived ? "restore" : "archive"}-knowledge="${escapeHtml(record.id)}">${archived ? "Restore" : "Archive"}</button>
        <button type="button" class="secondary danger" data-delete-knowledge="${escapeHtml(record.id)}">Delete</button>
        ${state.selectedKnowledgeCaseId ? `<button type="button" class="secondary" data-add-case-item="${escapeHtml(record.id)}" data-case-item-type="knowledge_record">Add to case</button>` : ""}
        <button type="button" class="secondary" data-copy-knowledge-markdown="${escapeHtml(record.id)}">Copy markdown</button>
        <button type="button" class="secondary" data-download-knowledge-markdown="${escapeHtml(record.id)}">Download .md</button>
        ${relatedLinks.join("")}
      </div>
      ${
        archived
          ? `<p class="compact-note muted">Archived ${escapeHtml(prettyDate(record.archived_at || record.updated_at))}${record.archived_reason ? ` | ${escapeHtml(record.archived_reason)}` : ""}</p>`
          : ""
      }
      ${
        loading
          ? `<p class="muted">Loading full note body...</p>`
          : `<div class="markdown-body">${markdownToHtml(record.content || record.content_excerpt || "No note body.")}</div>`
      }
      ${renderRelatedKnowledgeSection(relatedItems)}
      <details class="result-json-toggle">
        <summary>Open metadata</summary>
        <pre>${escapeHtml(JSON.stringify(metadata, null, 2))}</pre>
      </details>
    </article>
  `;
}

function renderCockpitLinkageMap() {
  if (!dom.cockpitLinkageGrid) {
    return;
  }
  const workspace = currentWorkspace();
  if (!state.user || !workspace) {
    dom.cockpitLinkageGrid.innerHTML = `
      <article class="guide-card">
        <p class="eyebrow eyebrow-compact">Workspace</p>
        <h4>Cross-module map</h4>
        <p>Sign in and select a workspace to see how providers, papers, Data Lab runs, notes, and cases connect.</p>
      </article>
    `;
    return;
  }
  const sourceCounts = Object.fromEntries(summarizeKnowledgeSourceCounts(state.workspaceKnowledge).map((item) => [item.key, item.count]));
  const activeCase = currentKnowledgeCase();
  const linkageCards = [
    {
      eyebrow: "Provider Center",
      title: "Providers -> Briefings & Data Lab",
      copy: state.integrations.length
        ? `${state.integrations.length} provider connection(s) are ready for private briefings, diagnostics, and model execution.`
        : "No provider is connected yet, so private generation and diagnostics remain blocked.",
      chips: [`Providers ${state.integrations.length}`, `Schedules ${state.workspaceSchedules.length}`],
      action: `<button type="button" class="secondary" data-scroll-target="provider-center-panel">Open Provider Center</button>`,
    },
    {
      eyebrow: "Paper Library",
      title: "Papers -> Notes -> Cases",
      copy: state.literatureEntries.length
        ? `${state.literatureEntries.length} paper(s) are in the workspace and ${sourceCounts.literature || 0} literature note(s) are already reusable in the knowledge base.`
        : "Import papers first, then branch them into base notes, summaries, and case-linked evidence.",
      chips: [`Papers ${state.literatureEntries.length}`, `Paper notes ${sourceCounts.literature || 0}`],
      action: `<button type="button" class="secondary" data-scroll-target="paper-library-panel">Open Paper Library</button>`,
    },
    {
      eyebrow: "Data Lab",
      title: "Datasets -> Results -> Knowledge",
      copy:
        state.workspaceAssets.length || sourceCounts.model
          ? `${processingHistoryItems().length} processing output(s) and ${sourceCounts.model || 0} model note(s) are available for manual review and reuse.`
          : "Profile a dataset, run a model, then capture the result into notes and case workspaces.",
      chips: [`Assets ${state.workspaceAssets.length}`, `Model notes ${sourceCounts.model || 0}`],
      action: `<a href="/data-lab" class="button-link secondary-link">Open Data Lab</a>`,
    },
    {
      eyebrow: "Private Knowledge Base",
      title: activeCase ? `Knowledge -> Active Case: ${activeCase.title}` : "Knowledge -> Case Workspace",
      copy: activeCase
        ? `${state.workspaceKnowledge.length} note(s) and ${activeCase.item_count || 0} linked case item(s) can be reviewed together in the active case.`
        : `${state.workspaceKnowledge.length} note(s) are available. Select an active case when you want to group outputs from multiple modules.`,
      chips: [`Notes ${state.workspaceKnowledge.length}`, `Cases ${state.workspaceCases.length}`],
      action: `<button type="button" class="secondary" data-scroll-target="knowledge-base-panel">Open Knowledge Base</button>`,
    },
  ];
  dom.cockpitLinkageGrid.innerHTML = linkageCards
    .map(
      (item) => `
        <article class="guide-card">
          <p class="eyebrow eyebrow-compact">${escapeHtml(item.eyebrow)}</p>
          <h4>${escapeHtml(item.title)}</h4>
          <p>${escapeHtml(item.copy)}</p>
          <div class="chip-row chip-row-compact">
            ${item.chips.map((chip) => `<span class="topic-chip">${escapeHtml(chip)}</span>`).join("")}
          </div>
          <div class="actions compact-actions">${item.action}</div>
        </article>
      `,
    )
    .join("");
}

function renderWorkspaceCockpit() {
  if (
    !dom.cockpitWorkspaceName ||
    !dom.cockpitStatGrid ||
    !dom.cockpitStepGrid ||
    !dom.cockpitActionList ||
    !dom.cockpitActivityList ||
    !dom.cockpitFlowList
  ) {
    return;
  }
  const workspace = currentWorkspace();
  const hasAccess = Boolean(state.user && workspace);
  const stats = {
    providers: state.integrations.length,
    briefings: state.privateBriefings.length,
    literature: state.literatureEntries.length,
    assets: state.workspaceAssets.length,
    notes: state.workspaceKnowledge.length,
    cases: state.workspaceCases.length,
    schedules: state.workspaceSchedules.length,
  };
  if (!hasAccess) {
    dom.cockpitWorkspaceName.textContent = state.user ? "Create or select a workspace" : "Sign in to begin";
    dom.cockpitWorkspaceMeta.textContent = state.user
      ? "Choose a workspace to unlock private providers, literature, notes, and recurring jobs."
      : "Private cockpit data appears after authentication.";
    dom.cockpitNextActionTitle.textContent = state.user ? "Select a workspace" : "Sign in";
    dom.cockpitNextActionCopy.textContent = state.user
      ? "Once a workspace is active, the cockpit will map providers, materials, and outputs."
      : "Register or log in first, then create a workspace and connect a provider.";
    dom.cockpitStatGrid.innerHTML = [
      ["Providers", 0, "No private connections loaded yet."],
      ["Papers", 0, "Private literature appears here after import."],
      ["Cases", 0, "Build case files to group workspace evidence."],
      ["Notes", 0, "Knowledge records will accumulate here."],
      ["Schedules", 0, "Recurring jobs appear after setup."],
    ]
      .map(
        ([label, value, copy]) => `
          <article class="cockpit-stat-card">
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(value)}</strong>
            <p class="muted">${escapeHtml(copy)}</p>
          </article>
        `,
      )
      .join("");
    dom.cockpitStepGrid.innerHTML = [
      ["1. Access", "Authenticate and choose a workspace.", "active"],
      ["2. Connect", "Save at least one provider or data source.", "pending"],
      ["3. Collect", "Import papers or create notes.", "pending"],
      ["4. Reuse", "Schedule work or review outputs.", "pending"],
    ]
      .map(
        ([title, copy, stateName]) => `
          <article class="workflow-step-card${stateName === "active" ? " is-active" : ""}">
            <h4>${escapeHtml(title)}</h4>
            <p>${escapeHtml(copy)}</p>
          </article>
        `,
      )
      .join("");
    dom.cockpitActionList.innerHTML = `
      <button type="button" class="button-link" data-scroll-target="provider-center-panel">Open Provider Center</button>
      <button type="button" class="button-link secondary-link" data-scroll-target="knowledge-base-panel">Open Knowledge Base</button>
      <button type="button" class="button-link secondary-link" data-create-workspace-digest="true">Build workspace digest</button>
      <a href="/public-monitor" class="button-link secondary-link">Browse Public Daily Monitor</a>
      <a href="/data-lab" class="button-link secondary-link">Open standalone Data Lab</a>
    `;
    dom.cockpitActivityList.innerHTML = emptyCard("No private workspace activity yet.");
    dom.cockpitFlowList.innerHTML = emptyCard("Sign in and select a workspace to unlock guided cross-module flows.");
    renderCockpitLinkageMap();
    return;
  }
  const nextAction = !stats.providers
    ? {
        title: "Connect your first provider",
        copy: "Save an LLM or data-source connection so research generation and diagnostics can run inside this workspace.",
      }
    : !stats.literature && !stats.assets
      ? {
          title: "Collect private research materials",
          copy: "Search OpenAlex, import papers, or switch to Data Lab to work with datasets.",
        }
      : !stats.notes
        ? {
            title: "Create reusable notes",
            copy: "Convert papers and private outputs into searchable knowledge records inside the workspace.",
          }
        : !stats.schedules
          ? {
              title: "Automate a recurring task",
              copy: "Add a daily job so the workspace continues to collect briefings without manual intervention.",
            }
          : {
              title: "Review and extend the workspace",
              copy: "Use the cockpit to jump to the most recent outputs and continue from the last completed step.",
            };
  dom.cockpitWorkspaceName.textContent = workspace.name;
  dom.cockpitWorkspaceMeta.textContent = workspace.description
    ? `${workspace.description} | ${stats.providers} providers | ${stats.cases} cases | ${stats.notes} notes | ${stats.schedules} schedules`
    : `${stats.providers} providers | ${stats.literature} papers | ${stats.assets} assets | ${stats.cases} cases | ${stats.notes} notes`;
  dom.cockpitNextActionTitle.textContent = nextAction.title;
  dom.cockpitNextActionCopy.textContent = nextAction.copy;
  dom.cockpitStatGrid.innerHTML = [
    ["Providers", stats.providers, "Saved model and data-source connections."],
    ["Briefings", stats.briefings, "Private macro briefings stored in this workspace."],
    ["Paper Library", stats.literature, "Imported OpenAlex entries and follow-up notes."],
    ["Assets", stats.assets, "Datasets, PDFs, charts, and processed outputs."],
    ["Cases", stats.cases, "Case files that group evidence across modules."],
    ["Knowledge", stats.notes, "Manual notes, paper notes, and model outputs."],
    ["Schedules", stats.schedules, "Recurring private jobs waiting to run."],
  ]
    .map(
      ([label, value, copy]) => `
        <article class="cockpit-stat-card">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
          <p class="muted">${escapeHtml(copy)}</p>
        </article>
      `,
    )
    .join("");
  const stepCards = [
    {
      title: "1. Workspace access",
      copy: `Signed in as ${state.user.full_name || state.user.email} with ${workspace.name} selected.`,
      complete: true,
    },
    {
      title: "2. Provider setup",
      copy: stats.providers ? `${stats.providers} provider connection(s) saved.` : "No provider yet. Start from Provider Center.",
      active: !stats.providers,
      complete: Boolean(stats.providers),
    },
    {
      title: "3. Research materials",
      copy: stats.literature || stats.assets
        ? `${stats.literature} papers and ${stats.assets} assets currently available.`
        : "Import literature or move to Data Lab for datasets.",
      active: stats.providers && !(stats.literature || stats.assets),
      complete: Boolean(stats.literature || stats.assets),
    },
    {
      title: "4. Reusable outputs",
      copy: stats.notes || stats.briefings || stats.schedules
        ? `${stats.notes} notes, ${stats.briefings} briefings, ${stats.schedules} schedules.`
        : "Create notes, generate a briefing, or add a recurring job.",
      active: (stats.literature || stats.assets) && !(stats.notes || stats.briefings || stats.schedules),
      complete: Boolean(stats.notes || stats.briefings || stats.schedules),
    },
  ];
  dom.cockpitStepGrid.innerHTML = stepCards
    .map(
      (step) => `
        <article class="workflow-step-card${step.complete ? " is-complete" : step.active ? " is-active" : ""}">
          <h4>${escapeHtml(step.title)}</h4>
          <p>${escapeHtml(step.copy)}</p>
        </article>
      `,
    )
    .join("");
  dom.cockpitActionList.innerHTML = [
    { label: "Connect provider", target: "provider-center-panel" },
    { label: "Generate briefing", target: "private-briefing-panel" },
    { label: "Search papers", target: "paper-library-panel" },
    { label: "Manage cases", target: "knowledge-base-panel" },
    { label: "Open knowledge base", target: "knowledge-base-panel" },
    { label: "Create schedule", target: "schedule-panel" },
    { label: "Build workspace digest", digest: true },
  ]
    .map(
      (action) =>
        action.digest
          ? `<button type="button" class="button-link secondary-link" data-create-workspace-digest="true">${escapeHtml(action.label)}</button>`
          : `<button type="button" class="button-link secondary-link" data-scroll-target="${escapeHtml(action.target)}">${escapeHtml(action.label)}</button>`,
    )
    .join("") +
    `<a href="/data-lab" class="button-link">Open standalone Data Lab</a>`;
  const activityItems = [
    state.privateBriefings[0]
      ? {
          title: state.privateBriefings[0].title,
          meta: `Briefing | ${prettyDate(state.privateBriefings[0].created_at)}`,
          copy: truncateText(state.privateBriefings[0].summary_markdown, 150),
          target: "private-briefing-panel",
        }
      : null,
    state.literatureEntries[0]
      ? {
          title: state.literatureEntries[0].title,
          meta: `Paper | ${state.literatureEntries[0].publication_year || "n/a"} | ${state.literatureEntries[0].venue || "Unknown venue"}`,
          copy: truncateText(state.literatureEntries[0].citation_text || state.literatureEntries[0].abstract_excerpt || "", 150),
          target: "paper-library-panel",
        }
      : null,
    state.workspaceKnowledge[0]
      ? {
          title: state.workspaceKnowledge[0].title,
          meta: `${knowledgeTypeSpec(state.workspaceKnowledge[0]).label} | ${prettyDate(state.workspaceKnowledge[0].updated_at || state.workspaceKnowledge[0].created_at)}`,
          copy: truncateText(state.workspaceKnowledge[0].content_excerpt || "", 150),
          target: "knowledge-base-panel",
        }
      : null,
    state.workspaceCases[0]
      ? {
          title: state.workspaceCases[0].title,
          meta: `Case | ${state.workspaceCases[0].item_count || 0} linked item(s)`,
          copy: truncateText(state.workspaceCases[0].description || "Private case file for grouped workspace evidence.", 150),
          target: "knowledge-base-panel",
        }
      : null,
    state.workspaceSchedules[0]
      ? {
          title: state.workspaceSchedules[0].name,
          meta: `Schedule | next ${prettyDate(state.workspaceSchedules[0].next_run_at)}`,
          copy: truncateText(state.workspaceSchedules[0].job_type || "Recurring private job", 150),
          target: "schedule-panel",
        }
      : null,
  ].filter(Boolean);
  dom.cockpitActivityList.innerHTML = activityItems.length
    ? activityItems
        .map(
          (item) => `
            <article class="card">
              <h4>${escapeHtml(item.title)}</h4>
              <p class="compact-note">${escapeHtml(item.meta)}</p>
              <p class="compact-note muted">${escapeHtml(item.copy)}</p>
              <div class="actions compact-actions">
                <button type="button" class="secondary" data-scroll-target="${escapeHtml(item.target)}">Open module</button>
              </div>
            </article>
          `,
        )
        .join("")
    : emptyCard("Generate a briefing, import papers, or create notes to populate the cockpit activity rail.");

  const latestBriefing = state.privateBriefings[0] || null;
  const latestPaper = state.literatureEntries[0] || null;
  const latestDataset = state.workspaceAssets.find((item) => String(item.kind || "").startsWith("dataset")) || null;
  const latestModelNote = modelHistoryItems()[0] || null;
  const activeCase = currentKnowledgeCase();
  const flowCards = [
    latestBriefing
      ? {
          title: "Briefing -> Knowledge",
          copy: latestBriefing.workspace_knowledge_record_id
            ? "The latest private briefing is already reusable as a knowledge note."
            : "Capture the latest private briefing into the knowledge base for later synthesis and citation.",
          actions: latestBriefing.workspace_knowledge_record_id
            ? [
                `<button type="button" class="button-link secondary-link" data-open-knowledge-record="${escapeHtml(latestBriefing.workspace_knowledge_record_id)}">Open briefing note</button>`,
                `<button type="button" class="button-link secondary-link" data-scroll-target="private-briefing-panel">Open briefing module</button>`,
              ]
            : [
                `<button type="button" class="button-link" data-import-briefing-knowledge="${escapeHtml(latestBriefing.id)}">Save briefing note</button>`,
                `<button type="button" class="button-link secondary-link" data-scroll-target="private-briefing-panel">Open briefing module</button>`,
              ],
        }
      : null,
    latestPaper
      ? {
          title: "Paper Library -> Knowledge",
          copy: latestPaper.workspace_knowledge_record_id
            ? "The latest imported paper already has a base note and can branch into summary or annotation notes."
            : "Turn the latest paper into a private knowledge note before generating annotations or question lists.",
          actions: latestPaper.workspace_knowledge_record_id
            ? [
                `<button type="button" class="button-link secondary-link" data-open-knowledge-record="${escapeHtml(latestPaper.workspace_knowledge_record_id)}">Open paper note</button>`,
                `<button type="button" class="button-link secondary-link" data-scroll-target="paper-library-panel">Open paper library</button>`,
              ]
            : [
                `<button type="button" class="button-link" data-import-literature-knowledge="${escapeHtml(latestPaper.id)}">Create paper note</button>`,
                `<button type="button" class="button-link secondary-link" data-scroll-target="paper-library-panel">Open paper library</button>`,
              ],
        }
      : null,
    latestDataset
      ? {
          title: activeCase ? "Dataset -> Active Case" : "Dataset -> Data Lab",
          copy: activeCase
            ? `Latest dataset: ${latestDataset.title}. Use Data Lab and send outputs into the active case "${activeCase.title}".`
            : `Latest dataset: ${latestDataset.title}. Move into the standalone Data Lab for profiling, processing, and model runs.`,
          actions: [
            `<a href="/data-lab" class="button-link">Open Data Lab</a>`,
            `<button type="button" class="button-link secondary-link" data-scroll-target="data-lab-entry-panel">Review Data Lab entry</button>`,
          ],
        }
      : null,
    latestModelNote
      ? {
          title: "Model Result -> Verification",
          copy: "The latest model output already lives in the knowledge base. Open the linked result page or inspect the note.",
          actions: [
            latestModelNote.metadata?.result_detail_path
              ? `<a href="${escapeHtml(latestModelNote.metadata.result_detail_path)}" class="button-link">Open result detail</a>`
              : `<button type="button" class="button-link secondary-link" data-scroll-target="knowledge-base-panel">Open knowledge base</button>`,
            `<button type="button" class="button-link secondary-link" data-open-knowledge-record="${escapeHtml(latestModelNote.id)}">Open model note</button>`,
          ],
        }
      : null,
  ].filter(Boolean);
  dom.cockpitFlowList.innerHTML = flowCards.length
    ? flowCards
        .map(
          (item) => `
            <article class="card cockpit-flow-card">
              <h4>${escapeHtml(item.title)}</h4>
              <p class="compact-note muted">${escapeHtml(item.copy)}</p>
              <div class="actions compact-actions">${item.actions.join("")}</div>
            </article>
          `,
        )
        .join("")
    : emptyCard("Import at least one briefing, paper, or dataset to unlock guided cross-module flows.");
  renderCockpitLinkageMap();
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

function currentRunDesignSummary() {
  const detail = currentFamilyDetail();
  const workflowLabel = currentWorkflowLabel();
  const surfaces =
    currentWorkflowType() === "model"
      ? ["Coefficient table", "Result detail page", "Knowledge note", "Case link"]
      : currentProcessingFamily() === "visualization"
        ? ["PNG chart", "Saved plot asset", "Result detail page", "Case link"]
        : ["Prepared sample", "Processing detail page", "Downloadable dataset", "Case link"];
  const checks = (detail?.manual_checks || []).slice(0, 4);
  let copy = "Choose a family to see what the run expects and what it exports.";
  if (detail) {
    copy =
      currentWorkflowType() === "model"
        ? `${workflowLabel} mode is set to ${detail.title}. Expect estimation output plus a transparent specification, tables, and audit trail.`
        : `${workflowLabel} mode is set to ${detail.title}. Expect a transformed asset plus an explicit record of processing operations.`;
  }
  return {
    title: detail ? `${workflowLabel}: ${detail.title}` : `${workflowLabel}: select a family`,
    copy,
    surfaces,
    checks,
  };
}

function renderLabRunDesign() {
  if (!dom.labRunDesignTitle || !dom.labRunDesignCopy) {
    return;
  }
  const design = currentRunDesignSummary();
  dom.labRunDesignTitle.textContent = design.title;
  dom.labRunDesignCopy.textContent = design.copy;
  if (dom.labRunDesignSurfaces) {
    dom.labRunDesignSurfaces.innerHTML = design.surfaces
      .map((item) => `<span class="topic-chip">${escapeHtml(item)}</span>`)
      .join("");
  }
  renderListCards(dom.labRunDesignChecks, design.checks, (item) => `
    <article class="card compact-card">
      <p>${escapeHtml(item)}</p>
    </article>
  `);
  if (!design.checks.length && dom.labRunDesignChecks) {
    dom.labRunDesignChecks.innerHTML = emptyCard("Manual verification checkpoints will appear here.");
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
  const activeCase = currentKnowledgeCase();

  dom.labContextAccess && (dom.labContextAccess.textContent = state.user ? "Signed in" : "Signed out");
  dom.labContextWorkspace && (dom.labContextWorkspace.textContent = workspace?.name || "No workspace selected");
  dom.labContextDataset &&
    (dom.labContextDataset.textContent = dataset ? `${dataset.title} | ${dataset.kind}${profile ? ` | ${profile.rows} rows` : ""}` : "No dataset selected");
  dom.labContextWorkflow && (dom.labContextWorkflow.textContent = currentWorkflowLabel());
  dom.labContextFamily && (dom.labContextFamily.textContent = family?.title || (currentWorkflowType() === "model" ? currentModelFamily() : currentProcessingFamily()));
  dom.labContextModel &&
    (dom.labContextModel.textContent = currentWorkflowType() === "model" ? currentModelLabel() : "Not applicable for data processing");
  if (dom.labCaseSelect) {
    dom.labCaseSelect.value = state.selectedKnowledgeCaseId || "";
  }
  if (dom.labCaseMeta) {
    dom.labCaseMeta.textContent = activeCase
      ? `Active case: ${activeCase.title} | ${activeCase.item_count || 0} linked items. New processing and model outputs can be attached from the history cards below.`
      : "No active case selected. Choose one if you want to organize Data Lab outputs inside a private case file.";
  }
  if (dom.labCaseHomeLink) {
    dom.labCaseHomeLink.href = activeCase ? "/#knowledge-base-panel" : "/#knowledge-base-panel";
    dom.labCaseHomeLink.textContent = activeCase ? "Open active case on homepage" : "Open case workspace on homepage";
  }
  dom.labContextNextAction && (dom.labContextNextAction.textContent = nextLabAction());
  if (dom.labContextDetailLink) {
    dom.labContextDetailLink.href = currentFamilyDetailPath();
  }
  renderWorkflowGuide();
  renderActiveFamilySummary();
  renderLabRunDesign();
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
    const caseButton = state.selectedKnowledgeCaseId
      ? `<button type="button" class="secondary" data-add-case-item="${escapeHtml(item.id)}" data-case-item-type="data_asset">Add to case</button>`
      : "";
    return `
      <article class="card">
        <h4>${escapeHtml(item.title)}</h4>
        <p>${escapeHtml(family)} | ${escapeHtml(prettyDate(item.updated_at || item.created_at))}</p>
        <p>${escapeHtml(truncateText(summary))}</p>
        <div class="actions">
          ${detailPath ? `<a href="${escapeHtml(detailPath)}" class="button-link secondary-link">Open detail</a>` : ""}
          ${useButton}
          ${caseButton}
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
    const caseButton = state.selectedKnowledgeCaseId
      ? `<button type="button" class="secondary" data-add-case-item="${escapeHtml(item.id)}" data-case-item-type="knowledge_record">Add to case</button>`
      : "";
    return `
      <article class="card">
        <h4>${escapeHtml(metadata.model_label || item.title)}</h4>
        <p>${escapeHtml(metadata.model_type || "model")} | ${escapeHtml(prettyDate(item.updated_at || item.created_at))}</p>
        <p>${escapeHtml(truncateText(summary))}</p>
        <div class="actions">
          <a href="${escapeHtml(detailPath)}" class="button-link secondary-link">Open detail</a>
          ${caseButton}
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
  renderAllLabTemplateBuilders();
  renderLabContext();
}

function hasPrivateWorkspaceUI() {
  return Boolean(dom.workspaceSelect);
}

function hasPublicMonitorUI() {
  return Boolean(dom.publicLatestView && dom.publicSummaryView && dom.publicBriefingList);
}

function hasOptimizationLabUI() {
  return Boolean(optimizationElement("optimization-suite-form"));
}

function renderOptimizationCatalog() {
  if (!hasOptimizationLabUI() || !state.optimizationCatalog) {
    return;
  }
  const catalog = state.optimizationCatalog;
  const snapshot = optimizationElement("optimization-snapshot-grid");
  const optimizerSelect = optimizationElement("optimization-optimizer-select");
  const functionSelect = optimizationElement("optimization-function-select");
  const requirements = optimizationElement("optimization-suite-requirements");
  const explorer = optimizationElement("optimization-catalog-explorer");
  const exportBoard = optimizationElement("optimization-validation-export-board");
  const optimizerBody = optimizationElement("optimization-optimizer-table")?.querySelector("tbody");
  const functionBody = optimizationElement("optimization-function-table")?.querySelector("tbody");
  const summary = catalog.summary || {};
  const suiteRequirements = catalog.suite_requirements || {};
  if (optimizationElement("optimization-health-status")) {
    optimizationElement("optimization-health-status").textContent =
      `${summary.optimizer_available_count || 0}/${summary.optimizer_count || 0} optimizers | ${summary.function_available_count || 0}/${summary.function_count || 0} functions`;
  }
  if (snapshot) {
    snapshot.innerHTML = [
      { label: "Mealpy optimizers", value: `${summary.optimizer_available_count || 0} available`, copy: `${summary.optimizer_count || 0} discovered locally.` },
      { label: "Opfunu functions", value: `${summary.function_available_count || 0} available`, copy: `${summary.function_count || 0} discovered locally.` },
      { label: "Default suite", value: `${(catalog.defaults?.optimizers || []).length} x ${(catalog.defaults?.functions || []).length}`, copy: "The default standard suite is the minimum valid comparative configuration." },
      { label: "Outputs", value: "Tables + PNG + JSON", copy: "Each suite exports score tables, significance tests, ranking visuals, and raw process traces." },
    ].map((item) => `
      <article class="snapshot-card">
        <span>${escapeHtml(item.label)}</span>
        <strong>${escapeHtml(item.value)}</strong>
        <p>${escapeHtml(item.copy)}</p>
      </article>
    `).join("");
  }
  if (requirements) {
    requirements.innerHTML = `
      <article class="card">
        <p class="eyebrow eyebrow-compact">Strict suite rules</p>
        <h4>Standard comparative benchmark</h4>
        <p class="muted">This module will not downgrade statistical validation. A valid comparative suite must meet every condition below before Friedman, Wilcoxon, sign, and rank outputs are produced.</p>
        <div class="chip-row chip-row-compact">
          <span class="topic-chip">Algorithms >= ${escapeHtml(suiteRequirements.min_algorithms || 3)}</span>
          <span class="topic-chip">Functions >= ${escapeHtml(suiteRequirements.min_functions || 3)}</span>
          <span class="topic-chip">Runs >= ${escapeHtml(suiteRequirements.min_runs || 3)}</span>
        </div>
      </article>
    `;
  }
  if (optimizerSelect) {
    optimizerSelect.innerHTML = (catalog.optimizers || [])
      .filter((item) => item.availability?.status === "available")
      .map((item) => `<option value="${escapeHtml(item.name)}">${escapeHtml(item.label)} | ${escapeHtml(item.module)}</option>`)
      .join("");
    setMultiSelectValues(optimizerSelect, catalog.defaults?.optimizers || []);
  }
  if (functionSelect) {
    functionSelect.innerHTML = (catalog.functions || [])
      .filter((item) => item.availability?.status === "available")
      .map((item) => `<option value="${escapeHtml(item.name)}">${escapeHtml(item.label)} | dim ${escapeHtml(item.dimension || "n/a")}</option>`)
      .join("");
    setMultiSelectValues(functionSelect, catalog.defaults?.functions || []);
  }
  if (explorer) {
    const optimizerGroups = Object.values(
      (catalog.optimizers || []).reduce((groups, item) => {
        const key = `${item.library || "mealpy"}::${item.group || "unknown"}::${item.family || "unknown"}`;
        groups[key] ||= { title: `${item.library || "mealpy"} / ${item.group || "unknown"} / ${item.family || "unknown"}`, items: [] };
        groups[key].items.push(item);
        return groups;
      }, {}),
    );
    const functionGroups = Object.values(
      (catalog.functions || []).reduce((groups, item) => {
        const key = `${item.library || "opfunu"}::${item.family || item.module || "unknown"}`;
        groups[key] ||= { title: `${item.library || "opfunu"} / ${item.family || item.module || "unknown"}`, items: [] };
        groups[key].items.push(item);
        return groups;
      }, {}),
    );
    explorer.innerHTML = `
      <article class="panel public-section nested-panel">
        <div class="panel-head panel-head-wrap">
          <div>
            <h4>Catalog Explorer</h4>
            <span class="muted">Browse the available libraries by family before you add items into the suite builder.</span>
          </div>
        </div>
        <div class="catalog-explorer-grid">
          <div class="catalog-group-column">
            <h5>Mealpy families</h5>
            ${optimizerGroups.map((group) => `
              <article class="catalog-group-card">
                <p class="eyebrow eyebrow-compact">${escapeHtml(group.title)}</p>
                <div class="chip-row chip-row-compact">
                  <span class="topic-chip">${escapeHtml(group.items.filter((item) => item.availability?.status === "available").length)} available</span>
                  <span class="topic-chip">${escapeHtml(group.items.length)} discovered</span>
                </div>
                <div class="catalog-inline-list">
                  ${group.items.slice(0, 8).map((item) => `<span class="catalog-inline-pill ${item.availability?.status !== "available" ? "muted-pill" : ""}">${escapeHtml(item.label || item.name)}</span>`).join("")}
                  ${group.items.length > 8 ? `<span class="catalog-inline-pill muted-pill">+${group.items.length - 8} more</span>` : ""}
                </div>
              </article>
            `).join("")}
          </div>
          <div class="catalog-group-column">
            <h5>Opfunu families</h5>
            ${functionGroups.map((group) => `
              <article class="catalog-group-card">
                <p class="eyebrow eyebrow-compact">${escapeHtml(group.title)}</p>
                <div class="chip-row chip-row-compact">
                  <span class="topic-chip">${escapeHtml(group.items.filter((item) => item.availability?.status === "available").length)} available</span>
                  <span class="topic-chip">${escapeHtml(group.items.length)} discovered</span>
                </div>
                <div class="catalog-inline-list">
                  ${group.items.slice(0, 8).map((item) => `<span class="catalog-inline-pill ${item.availability?.status !== "available" ? "muted-pill" : ""}">${escapeHtml(item.label || item.name)}</span>`).join("")}
                  ${group.items.length > 8 ? `<span class="catalog-inline-pill muted-pill">+${group.items.length - 8} more</span>` : ""}
                </div>
              </article>
            `).join("")}
          </div>
        </div>
      </article>
    `;
  }
  if (exportBoard) {
    exportBoard.innerHTML = `
      <article class="card">
        <p class="eyebrow eyebrow-compact">Validation & Export</p>
        <div class="card-list card-list-inline">
          <div class="card"><p>Average convergence curve, per-algorithm process curves, radar and ranking visuals are exported as PNG assets.</p></div>
          <div class="card"><p>Friedman, Wilcoxon, sign, ranking, score, and raw process tables are exported as downloadable CSV assets.</p></div>
          <div class="card"><p>Every successful suite is stored in the current workspace and can be routed into cases or the private knowledge base.</p></div>
        </div>
      </article>
    `;
  }
  if (optimizerBody) {
    optimizerBody.innerHTML = (catalog.optimizers || []).map((item) => `
      <tr>
        <td>${escapeHtml(item.name)}</td>
        <td>${escapeHtml(item.module || "")}</td>
        <td>${escapeHtml(item.availability?.status || "unknown")}</td>
        <td>${escapeHtml(item.availability?.note || "")}</td>
      </tr>
    `).join("");
  }
  if (functionBody) {
    functionBody.innerHTML = (catalog.functions || []).map((item) => `
      <tr>
        <td>${escapeHtml(item.name)}</td>
        <td>${escapeHtml(item.module || "")}</td>
        <td>${escapeHtml(item.dimension || "n/a")}</td>
        <td>${escapeHtml(item.availability?.status || "unknown")}</td>
        <td>${escapeHtml(item.availability?.note || "")}</td>
      </tr>
    `).join("");
  }
}

function renderOptimizationResults(items) {
  const target = optimizationElement("optimization-results-list");
  if (!target) {
    return;
  }
  if (!items?.length) {
    target.innerHTML = emptyCard("No optimization suites have been saved in this workspace yet.");
    return;
  }
  target.innerHTML = items.map((item) => {
    const summary = item.summary || {};
    return `
      <article class="card">
        <h4>${escapeHtml(item.title || item.suite_label || "Optimization suite")}</h4>
        <p>${escapeHtml(`Algorithms ${summary.algorithm_count || 0} | Functions ${summary.function_count || 0} | Runs ${summary.run_count || 0}`)}</p>
        <p class="compact-note">${escapeHtml(`Successful tasks ${summary.success_count || 0}/${summary.task_count || 0}`)}</p>
        <div class="actions">
          <a class="button-link secondary-link" href="${escapeHtml(item.result_detail_path || `/data-lab/results/optimization/${item.id}`)}">Open result</a>
        </div>
      </article>
    `;
  }).join("");
}

async function refreshOptimizationResults() {
  if (!state.selectedWorkspaceId) {
    renderOptimizationResults([]);
    return;
  }
  const payload = await api(`/api/workspaces/${state.selectedWorkspaceId}/optimization/results`);
  state.optimizationResults = payload.items || [];
  renderOptimizationResults(state.optimizationResults);
}

async function handleOptimizationSuiteRun(event) {
  event.preventDefault();
  ensureWorkspace();
  const payload = buildOptimizationPayload();
  const requirements = state.optimizationCatalog?.suite_requirements || {};
  const selectedOptimizers = payload.optimizer_names || [];
  const selectedFunctions = payload.function_names || [];
  const selectedRuns = Number(payload.runs || OPTIMIZATION_DEFAULTS.runs);
  if (selectedOptimizers.length < Number(requirements.min_algorithms || 3)) {
    throw new Error(`Optimization suites require at least ${requirements.min_algorithms || 3} algorithms; got ${selectedOptimizers.length}.`);
  }
  if (selectedFunctions.length < Number(requirements.min_functions || 3)) {
    throw new Error(`Optimization suites require at least ${requirements.min_functions || 3} benchmark functions; got ${selectedFunctions.length}.`);
  }
  if (selectedRuns < Number(requirements.min_runs || 3)) {
    throw new Error(`Optimization suites require at least ${requirements.min_runs || 3} runs per algorithm-function pair; got ${selectedRuns}.`);
  }
  const response = await api(`/api/workspaces/${state.selectedWorkspaceId}/optimization/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  state.currentOptimizationResult = response;
  const result = response.result || {};
  const summary = result.summary || {};
  const target = optimizationElement("optimization-run-summary");
  if (target) {
    target.innerHTML = `
      <article class="card">
        <h4>${escapeHtml(result.suite_label || payload.suite_label)}</h4>
        <p>${escapeHtml(`Successful tasks ${summary.success_count || 0}/${summary.task_count || 0} | Workers ${summary.worker_count || 1}`)}</p>
        <p class="compact-note">${escapeHtml(`Algorithms ${summary.algorithm_count || 0} | Functions ${summary.function_count || 0} | Runs ${summary.run_count || 0}`)}</p>
        ${summary.friedman?.note ? `<p class="compact-note">${escapeHtml(summary.friedman.note)}</p>` : ""}
        <div class="actions">
          <a class="button-link" href="${escapeHtml(result.result_detail_path || `/data-lab/results/optimization/${response.record?.id || ""}`)}">Open result page</a>
        </div>
      </article>
    `;
  }
  await refreshOptimizationResults();
  showToast("Optimization suite completed.");
}

async function loadOptimizationResultPage() {
  const route = extractOptimizationResultRoute();
  if (!route || isExperienceLocked()) {
    return;
  }
  await ensureAuthenticatedUser();
  const payload = await api(`/api/optimization/results/${route.id}`);
  state.currentOptimizationResult = payload;
  const result = payload.result || {};
  const summary = result.summary || {};
  const figures = result.artifacts?.figures || [];
  const tables = result.artifacts?.tables || [];
  const ranking = result.ranking_preview || [];
  if (optimizationElement("optimization-result-title")) {
    optimizationElement("optimization-result-title").textContent = result.suite_label || payload.record?.title || "Optimization suite";
  }
  if (optimizationElement("optimization-result-summary")) {
    optimizationElement("optimization-result-summary").textContent =
      `Algorithms ${summary.algorithm_count || 0} | Functions ${summary.function_count || 0} | Runs ${summary.run_count || 0} | Successful tasks ${summary.success_count || 0}/${summary.task_count || 0}`;
  }
  const snapshot = optimizationElement("optimization-result-snapshot");
  if (snapshot) {
    snapshot.innerHTML = [
      { label: "Suite label", value: result.suite_label || payload.record?.title || "Optimization suite", copy: "Private result record stored in the selected workspace." },
      { label: "Task success", value: `${summary.success_count || 0}/${summary.task_count || 0}`, copy: "Successful optimization tasks across all algorithm-function-run pairs." },
      { label: "Top rank", value: ranking[0]?.optimizer_name || "n/a", copy: ranking[0] ? `Average rank ${ranking[0].average_rank}` : "Ranking preview unavailable." },
      { label: "Workers", value: `${summary.worker_count || 1}`, copy: "Parallel task workers used for the suite." },
    ].map((item) => `
      <article class="snapshot-card">
        <span>${escapeHtml(item.label)}</span>
        <strong>${escapeHtml(item.value)}</strong>
        <p>${escapeHtml(item.copy)}</p>
      </article>
    `).join("");
  }
  const assetCard = (asset, kind) => `
    <article class="card">
      <h4>${escapeHtml(asset.title || kind)}</h4>
      <p>${escapeHtml(asset.description || "")}</p>
      <div class="actions">
        <button type="button" class="secondary" data-download-asset="${escapeHtml(asset.id)}">Download</button>
      </div>
    </article>
  `;
  const figuresTarget = optimizationElement("optimization-result-figures");
  if (figuresTarget) {
    figuresTarget.innerHTML = figures.length
      ? figures.map((asset) => assetCard(asset, "Figure")).join("")
      : emptyCard("No figure assets were generated.");
  }
  const tablesTarget = optimizationElement("optimization-result-tables");
  if (tablesTarget) {
    tablesTarget.innerHTML = tables.length
      ? tables.map((asset) => assetCard(asset, "Table")).join("")
      : emptyCard("No table assets were generated.");
  }
  const exportTarget = optimizationElement("optimization-result-assets");
  if (exportTarget) {
    exportTarget.innerHTML = [...figures, ...tables].length
      ? [...figures, ...tables].map((asset) => assetCard(asset, asset.kind || "Asset")).join("")
      : emptyCard("No export assets were attached to this result.");
  }
  if (optimizationElement("optimization-result-raw")) {
    optimizationElement("optimization-result-raw").textContent = JSON.stringify(payload, null, 2);
  }
}

function clearPrivateLists() {
  if (!hasPrivateWorkspaceUI()) {
    return;
  }
  state.integrations = [];
  state.privateBriefings = [];
  state.literatureEntries = [];
  state.workspaceAssets = [];
  state.workspaceKnowledge = [];
  state.workspaceCases = [];
  state.workspaceSchedules = [];
  state.knowledgeDetails = {};
  state.knowledgeRelated = {};
  state.caseDetails = {};
  state.selectedKnowledgeCaseId = "";
  state.selectedKnowledgeRecordId = "";
  state.knowledgeSearchQuery = "";
  state.knowledgeStatusFilter = "active";
  state.knowledgeTypeFilter = "all";
  state.knowledgeTagFilter = "all";
  state.editingKnowledgeRecordId = "";
  state.editingKnowledgeCaseId = "";
  localStorage.removeItem(storageKeys.caseId);
  resetKnowledgeCaseComposer();
  resetKnowledgeComposer();
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
  if (dom.knowledgeSummaryGrid) {
    dom.knowledgeSummaryGrid.innerHTML = "";
  }
  if (dom.knowledgeLinkageGrid) {
    dom.knowledgeLinkageGrid.innerHTML = "";
  }
  if (dom.knowledgePreview) {
    dom.knowledgePreview.innerHTML = emptyCard("Select a note to inspect its full content, metadata, and source links.");
  }
  if (dom.knowledgeCaseList) {
    dom.knowledgeCaseList.innerHTML = emptyCard("Create a case to group private workspace evidence.");
  }
  if (dom.knowledgeCaseSummaryGrid) {
    dom.knowledgeCaseSummaryGrid.innerHTML = "";
  }
  if (dom.knowledgeCasePreview) {
    dom.knowledgeCasePreview.innerHTML = emptyCard("Create or select a case to organize private notes, papers, briefings, datasets, and Data Lab outputs.");
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
  state.currentResultDetail = null;
  renderDataLabPlaceholders();
  renderProcessingHistory([]);
  renderModelHistory([]);
  renderWorkspaceCockpit();
}

function ensureSignedIn() {
  if (!state.user) {
    throw new Error("Please sign in first.");
  }
}

function ensureWorkspace() {
  ensureSignedIn();
  if (!state.selectedWorkspaceId) {
    throw new Error("Select a workspace first.");
  }
}

function clearSession(options = {}) {
  const { redirect = true } = options;
  state.token = "";
  state.user = null;
  state.workspaces = [];
  state.selectedWorkspaceId = "";
  state.assetProfiles = {};
  state.selectedAnalysisAssetId = "";
  state.knowledgeDetails = {};
  state.knowledgeRelated = {};
  state.caseDetails = {};
  state.workspaceCases = [];
  state.selectedKnowledgeCaseId = "";
  state.selectedKnowledgeRecordId = "";
  localStorage.removeItem(storageKeys.token);
  localStorage.removeItem(storageKeys.workspaceId);
  localStorage.removeItem(storageKeys.caseId);
  revokeResultPreviewUrls();
  applyAccessGateState();
  if (hasPrivateWorkspaceUI()) {
    renderSession();
    renderWorkspaceOptions();
    clearPrivateLists();
  }
  if (redirect && detectPageMode() !== "home") {
    window.location.assign("/");
  }
}

function setSession(payload) {
  state.token = payload.session_token;
  state.user = payload.user;
  state.workspaces = payload.workspaces || [];
  state.selectedWorkspaceId = state.selectedWorkspaceId || state.workspaces[0]?.id || "";
  state.knowledgeDetails = {};
  state.knowledgeRelated = {};
  state.caseDetails = {};
  state.selectedKnowledgeRecordId = "";
  localStorage.setItem(storageKeys.token, state.token);
  if (state.selectedWorkspaceId) {
    localStorage.setItem(storageKeys.workspaceId, state.selectedWorkspaceId);
  }
  applyAccessGateState();
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
    applyAccessGateState();
    renderLabContext();
    renderWorkspaceCockpit();
    return;
  }
  dom.sessionIndicator.textContent = "Signed in";
  dom.userSummary.textContent = `${state.user.full_name} | ${state.user.email}`;
  applyAccessGateState();
  renderLabContext();
  renderWorkspaceCockpit();
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
  renderWorkspaceCockpit();
}

function getProviderCatalog() {
  return state.bootstrap?.provider_catalog || { llm: [], data_source: [] };
}

function getProviderSpec(kind) {
  const providerCatalog = getProviderCatalog();
  return [...(providerCatalog.llm || []), ...(providerCatalog.data_source || [])].find((item) => item.kind === kind) || null;
}

function formatProviderHint(spec) {
  if (!spec) {
    return "Use a saved provider preset or enter a custom OpenAI-compatible endpoint.";
  }
  const details = [spec.description];
  if (spec.default_base_url) {
    details.push(`Default base URL: ${spec.default_base_url}`);
  }
  if (spec.default_model) {
    details.push(`Default model: ${spec.default_model}`);
  }
  return details.join(" ");
}

function applyIntegrationProviderPreset(kind) {
  const integrationForm = document.getElementById("integration-form");
  if (!integrationForm) {
    return;
  }
  const spec = getProviderSpec(kind);
  const categoryField = integrationForm.elements.namedItem("category");
  const labelField = integrationForm.elements.namedItem("label");
  const modelField = integrationForm.elements.namedItem("model");
  const baseUrlField = integrationForm.elements.namedItem("base_url");
  if (!categoryField || !labelField || !modelField || !baseUrlField) {
    return;
  }
  const previousModelPreset = modelField.dataset.appliedPreset || "";
  const previousBasePreset = baseUrlField.dataset.appliedPreset || "";
  if (spec?.category) {
    categoryField.value = spec.category;
  }
  if (spec?.label && !String(labelField.value || "").trim()) {
    labelField.value = spec.label;
  }
  if (spec?.default_model && (!String(modelField.value || "").trim() || modelField.value === previousModelPreset)) {
    modelField.value = spec.default_model;
  }
  if (!spec?.default_model && modelField.value === previousModelPreset) {
    modelField.value = "";
  }
  if (spec?.default_base_url && (!String(baseUrlField.value || "").trim() || baseUrlField.value === previousBasePreset)) {
    baseUrlField.value = spec.default_base_url;
  }
  if (!spec?.default_base_url && baseUrlField.value === previousBasePreset) {
    baseUrlField.value = "";
  }
  modelField.dataset.appliedPreset = spec?.default_model || "";
  baseUrlField.dataset.appliedPreset = spec?.default_base_url || "";
  if (dom.integrationProviderHint) {
    dom.integrationProviderHint.textContent = formatProviderHint(spec);
  }
  if (dom.integrationProviderDocs) {
    if (spec?.docs_url) {
      dom.integrationProviderDocs.href = spec.docs_url;
      dom.integrationProviderDocs.hidden = false;
    } else {
      dom.integrationProviderDocs.hidden = true;
      dom.integrationProviderDocs.removeAttribute("href");
    }
  }
}

function renderIntegrations(items) {
  state.integrations = items || [];
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
          <p>${escapeHtml(item.category)} | ${escapeHtml(item.provider_name || item.kind)} | ${escapeHtml(item.model || "default model")}</p>
          <p>${escapeHtml(item.base_url || "Provider default base URL")}</p>
          <p>${item.is_default ? "Default connection" : "Saved connection"}</p>
          <div class="actions">
            <button type="button" class="secondary" data-test-integration="${item.id}">Test</button>
            <button type="button" class="secondary" data-delete-integration="${item.id}">Delete</button>
            ${item.docs_url ? `<a class="secondary action-link" href="${escapeHtml(item.docs_url)}" target="_blank" rel="noreferrer">Docs</a>` : ""}
          </div>
        </div>
      `,
    )
    .join("");
}

function renderBriefings(items) {
  state.privateBriefings = items || [];
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
          <div class="literature-status-grid">
            <article class="literature-status-card">
              <p class="eyebrow eyebrow-compact">Knowledge Link</p>
              <strong>${item.workspace_knowledge_record_id ? "Ready" : "Missing"}</strong>
              <p class="compact-note muted">${item.workspace_knowledge_record_id ? escapeHtml(item.workspace_knowledge_record_title || "Briefing note") : "Capture this briefing in the private knowledge base to reuse it elsewhere."}</p>
              ${item.workspace_knowledge_record_id ? `<button type="button" class="secondary" data-open-knowledge-record="${item.workspace_knowledge_record_id}">Open note</button>` : `<button type="button" class="secondary" data-import-briefing-knowledge="${item.id}">Save to knowledge base</button>`}
              ${state.selectedKnowledgeCaseId ? `<button type="button" class="secondary" data-add-case-item="${item.id}" data-case-item-type="briefing">Add to case</button>` : ""}
            </article>
          </div>
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
          <p>${escapeHtml(item.venue || "Unknown venue")}</p>
          <p class="compact-note">${escapeHtml(item.abstract_excerpt || item.abstract || "")}</p>
          <div class="actions">
            ${item.landing_page_url ? `<a class="action-link" href="${escapeHtml(item.landing_page_url)}" target="_blank" rel="noreferrer">Open source page</a>` : ""}
            ${item.pdf_url ? `<a class="action-link" href="${escapeHtml(item.pdf_url)}" target="_blank" rel="noreferrer">Open OA PDF</a>` : ""}
          </div>
        </div>
      `,
    )
    .join("");
}

function renderLiterature(items) {
  state.literatureEntries = items || [];
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
          <p class="compact-note">${escapeHtml(item.citation_text || "")}</p>
          <p class="compact-note">${escapeHtml(item.abstract_excerpt || item.abstract || "")}</p>
          <div class="actions compact-actions">
            ${item.landing_page_url ? `<a class="action-link" href="${escapeHtml(item.landing_page_url)}" target="_blank" rel="noreferrer">Source page</a>` : ""}
            ${item.pdf_url ? `<a class="action-link" href="${escapeHtml(item.pdf_url)}" target="_blank" rel="noreferrer">Open OA PDF</a>` : ""}
            ${item.has_open_access_pdf && !item.workspace_pdf_asset_id ? `<button type="button" class="secondary" data-import-literature-pdf="${item.id}">Import PDF</button>` : ""}
            ${item.workspace_pdf_asset_id ? `<button type="button" class="secondary" data-download-literature-asset="${item.workspace_pdf_asset_id}">Download private copy</button>` : ""}
            ${!item.workspace_knowledge_record_id ? `<button type="button" class="secondary" data-import-literature-knowledge="${item.id}">Save to knowledge base</button>` : ""}
            ${state.selectedKnowledgeCaseId ? `<button type="button" class="secondary" data-add-case-item="${item.id}" data-case-item-type="literature_entry">Add to case</button>` : ""}
          </div>
          <div class="literature-status-grid">
            <article class="literature-status-card">
              <p class="eyebrow eyebrow-compact">Private PDF</p>
              <strong>${item.workspace_pdf_asset_id ? "Imported" : item.has_open_access_pdf ? "Available" : "Unavailable"}</strong>
              <p class="compact-note muted">
                ${item.workspace_pdf_asset_id ? `Saved as ${escapeHtml(item.workspace_pdf_asset_title || "paper PDF")}.` : item.has_open_access_pdf ? "Open-access source is available for import." : "No downloadable OA source exposed by this entry."}
              </p>
            </article>
            <article class="literature-status-card">
              <p class="eyebrow eyebrow-compact">Paper Note</p>
              <strong>${item.workspace_knowledge_record_id ? "Ready" : "Missing"}</strong>
              <p class="compact-note muted">${item.workspace_knowledge_record_id ? escapeHtml(item.workspace_knowledge_record_title || "Paper note") : "Create the base note before generating follow-up notes."}</p>
              ${item.workspace_knowledge_record_id ? `<button type="button" class="secondary" data-open-knowledge-record="${item.workspace_knowledge_record_id}">Open note</button>` : ""}
            </article>
            <article class="literature-status-card">
              <p class="eyebrow eyebrow-compact">Summary</p>
              <strong>${item.workspace_summary_record_id ? "Ready" : item.workspace_knowledge_record_id ? "Not created" : "Locked"}</strong>
              <p class="compact-note muted">${item.workspace_summary_record_id ? escapeHtml(item.workspace_summary_record_title || "Summary note") : item.workspace_knowledge_record_id ? "Create a concise private summary note." : "Requires the base paper note first."}</p>
              ${item.workspace_summary_record_id ? `<button type="button" class="secondary" data-open-knowledge-record="${item.workspace_summary_record_id}">Open summary</button>` : item.workspace_knowledge_record_id ? `<button type="button" class="secondary" data-derive-literature-note="${item.id}" data-derive-literature-mode="summary">Create summary note</button>` : ""}
            </article>
            <article class="literature-status-card">
              <p class="eyebrow eyebrow-compact">Annotation</p>
              <strong>${item.workspace_annotation_record_id ? "Ready" : item.workspace_knowledge_record_id ? "Not created" : "Locked"}</strong>
              <p class="compact-note muted">${item.workspace_annotation_record_id ? escapeHtml(item.workspace_annotation_record_title || "Annotation template") : item.workspace_knowledge_record_id ? "Prepare a reading and margin-note template." : "Requires the base paper note first."}</p>
              ${item.workspace_annotation_record_id ? `<button type="button" class="secondary" data-open-knowledge-record="${item.workspace_annotation_record_id}">Open annotation</button>` : item.workspace_knowledge_record_id ? `<button type="button" class="secondary" data-derive-literature-note="${item.id}" data-derive-literature-mode="annotation">Create annotation template</button>` : ""}
            </article>
            <article class="literature-status-card">
              <p class="eyebrow eyebrow-compact">Question Breakdown</p>
              <strong>${item.workspace_question_record_id ? "Ready" : item.workspace_knowledge_record_id ? "Not created" : "Locked"}</strong>
              <p class="compact-note muted">${item.workspace_question_record_id ? escapeHtml(item.workspace_question_record_title || "Question breakdown") : item.workspace_knowledge_record_id ? "Split the paper into variables, checks, and follow-up questions." : "Requires the base paper note first."}</p>
              ${item.workspace_question_record_id ? `<button type="button" class="secondary" data-open-knowledge-record="${item.workspace_question_record_id}">Open questions</button>` : item.workspace_knowledge_record_id ? `<button type="button" class="secondary" data-derive-literature-note="${item.id}" data-derive-literature-mode="question_breakdown">Create question breakdown</button>` : ""}
            </article>
          </div>
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
            ${state.selectedKnowledgeCaseId ? `<button type="button" class="secondary" data-add-case-item="${item.id}" data-case-item-type="data_asset">Add to case</button>` : ""}
          </div>
        </div>
      `,
    )
    .join("");
  renderProcessingHistory(processingHistoryItems());
}

function renderKnowledge(items) {
  state.workspaceKnowledge = items || [];
  renderKnowledgeFilterOptions(state.workspaceKnowledge);
  const filteredItems = filteredKnowledgeItems(state.workspaceKnowledge);
  renderKnowledgeSummary(state.workspaceKnowledge, filteredItems);
  if (!filteredItems.length) {
    state.selectedKnowledgeRecordId = "";
    if (dom.knowledgeList) {
      dom.knowledgeList.innerHTML = emptyCard("No notes match the current knowledge filters.");
    }
    renderKnowledgePreview(null);
    renderModelHistory(modelHistoryItems());
    renderWorkspaceCockpit();
    return;
  }
  if (!filteredItems.some((item) => item.id === state.selectedKnowledgeRecordId)) {
    state.selectedKnowledgeRecordId = filteredItems[0].id;
  }
  if (dom.knowledgeList) {
    dom.knowledgeList.innerHTML = filteredItems
      .map((item) => {
        const typeSpec = knowledgeTypeSpec(item);
        const selected = item.id === state.selectedKnowledgeRecordId;
        const relatedPath = typeSpec.relatedPath || "";
        const archived = isKnowledgeArchived(item);
        return `
          <article class="card knowledge-card${selected ? " is-selected" : ""}${archived ? " is-archived" : ""}" data-knowledge-record-id="${escapeHtml(item.id)}">
            <div class="panel-head panel-head-wrap">
              <div>
                <h4>${escapeHtml(item.title)}</h4>
                <p class="compact-note">${escapeHtml(typeSpec.label)} | ${escapeHtml(prettyDate(item.updated_at || item.created_at))}</p>
              </div>
              <div class="chip-row chip-row-compact">
                ${archived ? `<span class="pill pill-archived">Archived</span>` : ""}
                <span class="pill">${escapeHtml(item.content_length || 0)} chars</span>
              </div>
            </div>
            <div class="chip-row chip-row-compact">
              ${(item.tags || []).slice(0, 5).map((tag) => `<span class="topic-chip">${escapeHtml(tag)}</span>`).join("") || `<span class="muted">No tags</span>`}
            </div>
            <p class="compact-note muted">${escapeHtml(item.content_excerpt || "No note body.")}</p>
            <div class="actions compact-actions">
              <button type="button" class="secondary" data-select-knowledge="${escapeHtml(item.id)}">Preview</button>
              <button type="button" class="secondary" data-edit-knowledge="${escapeHtml(item.id)}">Edit</button>
              <button type="button" class="secondary" data-${archived ? "restore" : "archive"}-knowledge="${escapeHtml(item.id)}">${archived ? "Restore" : "Archive"}</button>
              <button type="button" class="secondary danger" data-delete-knowledge="${escapeHtml(item.id)}">Delete</button>
              ${relatedPath ? `<a href="${escapeHtml(relatedPath)}" class="action-link">Open related detail</a>` : ""}
            </div>
          </article>
        `;
      })
      .join("");
  }
  const selectedRecord = mergeKnowledgeRecord(state.selectedKnowledgeRecordId);
  const loading = !selectedRecord?.content && Boolean(state.selectedWorkspaceId && state.user);
  renderKnowledgePreview(selectedRecord, { loading });
  if (loading) {
    void loadKnowledgeDetail(state.selectedKnowledgeRecordId).catch((error) => {
      showToast(error.message || "Failed to load the full knowledge note.", true);
    });
  }
  if (selectedRecord?.id) {
    void loadKnowledgeRelated(selectedRecord.id).catch((error) => {
      console.warn("Failed to load related knowledge", error);
    });
  }
  renderModelHistory(modelHistoryItems());
  renderWorkspaceCockpit();
}

async function loadKnowledgeDetail(recordId, force = false) {
  if (!recordId || !state.selectedWorkspaceId || !state.user) {
    return null;
  }
  if (!force && state.knowledgeDetails[recordId]?.content) {
    return state.knowledgeDetails[recordId];
  }
  const response = await api(`/api/workspaces/${state.selectedWorkspaceId}/knowledge/${recordId}`);
  state.knowledgeDetails[recordId] = response.record;
  if (state.selectedKnowledgeRecordId === recordId) {
    renderKnowledge(state.workspaceKnowledge);
  }
  return response.record;
}

async function loadKnowledgeRelated(recordId, force = false) {
  if (!recordId || !state.selectedWorkspaceId || !state.user) {
    return [];
  }
  if (!force && state.knowledgeRelated[recordId]) {
    return state.knowledgeRelated[recordId];
  }
  const response = await api(`/api/workspaces/${state.selectedWorkspaceId}/knowledge/${recordId}/related?limit=4`);
  state.knowledgeRelated[recordId] = response.items || [];
  if (state.selectedKnowledgeRecordId === recordId) {
    renderKnowledge(state.workspaceKnowledge);
  }
  return state.knowledgeRelated[recordId];
}

function focusKnowledgeRecord(recordId) {
  if (!recordId || !dom.knowledgeList) {
    return false;
  }
  if (!(state.workspaceKnowledge || []).some((item) => item.id === recordId)) {
    return false;
  }
  if (!filteredKnowledgeItems(state.workspaceKnowledge).some((item) => item.id === recordId)) {
    state.knowledgeSearchQuery = "";
    state.knowledgeStatusFilter = "all";
    state.knowledgeTypeFilter = "all";
    state.knowledgeTagFilter = "all";
  }
  state.selectedKnowledgeRecordId = recordId;
  renderKnowledge(state.workspaceKnowledge);
  const selector = `[data-knowledge-record-id="${String(recordId).replaceAll('"', '\\"')}"]`;
  const target = dom.knowledgeList.querySelector(selector);
  if (!target) {
    dom.knowledgeList.scrollIntoView({ behavior: "smooth", block: "start" });
    void loadKnowledgeDetail(recordId);
    return false;
  }
  dom.knowledgeList.querySelectorAll(".knowledge-card.is-highlighted").forEach((node) => node.classList.remove("is-highlighted"));
  target.classList.add("is-highlighted");
  target.scrollIntoView({ behavior: "smooth", block: "center" });
  window.clearTimeout(focusKnowledgeRecord.timer);
  focusKnowledgeRecord.timer = window.setTimeout(() => target.classList.remove("is-highlighted"), 2200);
  void loadKnowledgeDetail(recordId);
  void loadKnowledgeRelated(recordId);
  return true;
}

function renderSchedules(items) {
  state.workspaceSchedules = items || [];
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

function hasPublicModerationAccess() {
  return Boolean(state.user && state.token);
}

function buildOptions(options, selected, allLabel) {
  const rows = [{ value: "all", label: allLabel }, ...(options || []).map((value) => ({ value, label: value }))];
  return rows
    .map(
      (row) =>
        `<option value="${escapeHtml(row.value)}"${row.value === selected ? " selected" : ""}>${escapeHtml(row.label)}</option>`,
    )
    .join("");
}

function applyPublicSourceView(row) {
  const view = state.publicSourceView || "all";
  if (!row || view === "all") {
    return true;
  }
  if (view === "official") {
    return (row.source_type || "") === "official";
  }
  if (view === "us") {
    return (row.source_country || "") === "US";
  }
  if (view === "cn") {
    return (row.source_country || "") === "CN";
  }
  if (view === "developed") {
    return ["US", "GB", "EA", "JP", "CA"].includes(row.source_country || "");
  }
  return true;
}

function applyPublicSourceFilters(row) {
  if (!row) {
    return false;
  }
  if (!applyPublicSourceView(row)) {
    return false;
  }
  if (state.publicSourceTypeFilter !== "all" && (row.source_type || "") !== state.publicSourceTypeFilter) {
    return false;
  }
  if (state.publicSourceCountryFilter !== "all" && (row.source_country || "") !== state.publicSourceCountryFilter) {
    return false;
  }
  if (state.publicSourceRegionFilter !== "all" && (row.region_focus || "") !== state.publicSourceRegionFilter) {
    return false;
  }
  return true;
}

function renderPublicSourcePanel(panel) {
  if (!dom.publicSourcePanel) {
    return;
  }
  if (!panel) {
    dom.publicSourcePanel.innerHTML = emptyCard("Source mix and feed-health metadata will appear with the current public edition.");
    return;
  }
  const overview = Array.isArray(panel.overview) ? panel.overview : [];
  const domains = Array.isArray(panel.domains) ? panel.domains : [];
  const countries = Array.isArray(panel.countries) ? panel.countries : [];
  const feeds = Array.isArray(panel.feeds) ? panel.feeds : [];
  const typeBreakdown = Array.isArray(panel.type_breakdown) ? panel.type_breakdown : [];
  const regionBreakdown = Array.isArray(panel.region_breakdown) ? panel.region_breakdown : [];
  const sourceDirectory = Array.isArray(panel.source_directory) ? panel.source_directory : [];
  const notes = Array.isArray(panel.notes) ? panel.notes : [];
  const availableFilters = panel.available_filters || {};
  if (dom.publicSourceView) {
    const views = Array.isArray(availableFilters.priority_views) ? availableFilters.priority_views : [];
    dom.publicSourceView.innerHTML = views.length
      ? views
          .map(
            (view) =>
              `<option value="${escapeHtml(view.slug)}"${view.slug === state.publicSourceView ? " selected" : ""}>${escapeHtml(view.label)}</option>`,
          )
          .join("")
      : `<option value="all">All Sources</option>`;
  }
  if (dom.publicSourceTypeFilter) {
    dom.publicSourceTypeFilter.innerHTML = buildOptions(availableFilters.source_types || [], state.publicSourceTypeFilter, "All Types");
  }
  if (dom.publicSourceCountryFilter) {
    dom.publicSourceCountryFilter.innerHTML = buildOptions(
      availableFilters.countries || [],
      state.publicSourceCountryFilter,
      "All Countries",
    );
  }
  if (dom.publicSourceRegionFilter) {
    dom.publicSourceRegionFilter.innerHTML = buildOptions(
      availableFilters.regions || [],
      state.publicSourceRegionFilter,
      "All Regions",
    );
  }
  const filteredSourceDirectory = sourceDirectory.filter((row) => applyPublicSourceFilters(row));
  const filteredFeeds = feeds.filter((row) => applyPublicSourceFilters(row));
  dom.publicSourcePanel.innerHTML = `
    <article class="source-panel-card">
      <h4>Edition Overview</h4>
      <div class="chip-row chip-row-compact">
        ${overview
          .map((item) => `<span class="topic-chip">${escapeHtml(item.label)} <strong>${escapeHtml(item.value)}</strong></span>`)
          .join("") || `<span class="muted">No overview metrics yet.</span>`}
      </div>
      <p class="muted">GDELT status: ${escapeHtml(panel.gdelt?.status || "unknown")} | Items scanned: ${escapeHtml(panel.gdelt?.item_count ?? 0)}</p>
      ${
        notes.length
          ? `<div class="stack compact-stack">${notes.map((note) => `<p class="muted">${escapeHtml(note)}</p>`).join("")}</div>`
          : ""
      }
    </article>
    <article class="source-panel-card">
      <h4>Source Types</h4>
      <div class="source-list">
        ${
          typeBreakdown.length
            ? typeBreakdown
                .map(
                  (item) => `
                    <div class="source-list-row">
                      <strong>${escapeHtml(item.type)}</strong>
                      <span>Visible ${escapeHtml(item.active_count)} | Filtered ${escapeHtml(item.excluded_count)}</span>
                    </div>
                  `,
                )
                .join("")
            : `<p class="muted">No source-type breakdown yet.</p>`
        }
      </div>
    </article>
    <article class="source-panel-card">
      <h4>Region Focus</h4>
      <div class="source-list">
        ${
          regionBreakdown.length
            ? regionBreakdown
                .map(
                  (item) => `
                    <div class="source-list-row">
                      <strong>${escapeHtml(item.region)}</strong>
                      <span>Visible ${escapeHtml(item.active_count)} | Filtered ${escapeHtml(item.excluded_count)}</span>
                    </div>
                  `,
                )
                .join("")
            : `<p class="muted">No region-focus breakdown yet.</p>`
        }
      </div>
    </article>
    <article class="source-panel-card">
      <h4>Domain Mix</h4>
      <div class="source-list">
        ${
          domains.length
            ? domains
                .map(
                  (item) => `
                    <div class="source-list-row">
                      <strong>${escapeHtml(item.domain)}</strong>
                      <span>Visible ${escapeHtml(item.active_count)} | Filtered ${escapeHtml(item.excluded_count)}</span>
                    </div>
                  `,
                )
                .join("")
            : `<p class="muted">No domain breakdown yet.</p>`
        }
      </div>
    </article>
    <article class="source-panel-card">
      <h4>Geography Mix</h4>
      <div class="source-list">
        ${
          countries.length
            ? countries
                .map(
                  (item) => `
                    <div class="source-list-row">
                      <strong>${escapeHtml(item.country)}</strong>
                      <span>Visible ${escapeHtml(item.active_count)} | Filtered ${escapeHtml(item.excluded_count)}</span>
                    </div>
                  `,
                )
                .join("")
            : `<p class="muted">No source-country mix yet.</p>`
        }
      </div>
    </article>
    <article class="source-panel-card">
      <h4>Source Directory</h4>
      <div class="source-list">
        ${
          filteredSourceDirectory.length
            ? filteredSourceDirectory
                .map(
                  (row) => `
                    <div class="source-directory-row">
                      <div class="source-directory-head">
                        <strong>${escapeHtml(row.name)}</strong>
                        <span>${escapeHtml(row.source_type || "media")} | ${escapeHtml(row.source_country || "N/A")} | ${escapeHtml(row.kind || "rss")}</span>
                      </div>
                      <span class="muted">${escapeHtml(row.region_focus || "Global")} | ${escapeHtml(row.credibility || "source")}</span>
                      <span class="muted">Status ${escapeHtml(row.status || "unknown")} | matched ${escapeHtml(row.matched_items ?? 0)} | visible ${escapeHtml(row.visible_count ?? 0)} | filtered ${escapeHtml(row.excluded_count ?? 0)}</span>
                      ${row.note ? `<p>${escapeHtml(row.note)}</p>` : ""}
                      ${row.message ? `<p class="muted source-error">${escapeHtml(row.message)}</p>` : ""}
                    </div>
                  `,
                )
                .join("")
            : `<p class="muted">No configured sources match the current filter view.</p>`
        }
      </div>
    </article>
    <article class="source-panel-card">
      <h4>Feed Health</h4>
      <div class="source-list">
        ${
          filteredFeeds.length
            ? filteredFeeds
                .map(
                  (feed) => `
                    <div class="source-list-row">
                      <strong>${escapeHtml(feed.name)}</strong>
                      <span>${escapeHtml(feed.status)} | ${escapeHtml(feed.source_type || "media")} | matched ${escapeHtml(feed.matched_items)}</span>
                    </div>
                    <p class="muted">${escapeHtml(feed.region_focus || "Global")} | ${escapeHtml(feed.credibility || "source")}</p>
                    ${feed.message ? `<p class="muted source-error">${escapeHtml(feed.message)}</p>` : ""}
                  `,
                )
                .join("")
            : `<p class="muted">No feed rows match the current filter view.</p>`
        }
      </div>
    </article>
  `;
}

function publicReviewCard(item, actionLabel, actionName, enabled) {
  const metaParts = [
    item.source_name,
    item.source_type,
    item.domain,
    item.source_country,
    item.region_focus,
    (item.themes || []).slice(0, 2).join(", "),
  ]
    .filter(Boolean)
    .map((part) => escapeHtml(part));
  return `
    <article class="review-card">
      <div class="panel-head panel-head-wrap">
        <div>
          <h4>${escapeHtml(item.title || "Untitled headline")}</h4>
          <span class="muted">${metaParts.join(" | ") || "Public headline"}</span>
        </div>
        ${
          enabled
            ? `<button
                type="button"
                class="secondary"
                data-public-moderation="${escapeHtml(actionName)}"
                data-public-url="${escapeHtml(item.url || "")}"
                data-public-title="${escapeHtml(item.title || "")}"
              >${escapeHtml(actionLabel)}</button>`
            : ""
        }
      </div>
      ${item.credibility ? `<p><strong>Credibility:</strong> ${escapeHtml(item.credibility)}</p>` : ""}
      ${item.source_note ? `<p>${escapeHtml(item.source_note)}</p>` : ""}
      ${item.excerpt ? `<p>${escapeHtml(item.excerpt)}</p>` : ""}
      <div class="actions actions-wrap compact-actions">
        ${item.url ? `<a class="button-link secondary-link" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">Open source article</a>` : ""}
      </div>
    </article>
  `;
}

function renderPublicReviewQueue(briefing) {
  if (!dom.publicReviewList || !dom.publicExcludedList || !dom.publicReviewNote) {
    return;
  }
  if (!briefing) {
    dom.publicReviewNote.textContent = "Moderation controls will appear once a public edition is available.";
    dom.publicReviewList.innerHTML = emptyCard("No visible headlines are available yet.");
    dom.publicExcludedList.innerHTML = emptyCard("No excluded headlines yet.");
    return;
  }
  const canModerate = hasPublicModerationAccess();
  const moderation = briefing.moderation || {};
  dom.publicReviewNote.textContent = canModerate
    ? `Signed in as ${state.user?.full_name || state.user?.email || "moderator"} | visible ${moderation.active_count ?? briefing.headline_count} | filtered ${moderation.excluded_count ?? 0}`
    : "Sign in on the main platform to manually exclude or restore headlines. Anonymous visitors can only browse.";
  const reviewItems = Array.isArray(briefing.review_items) ? briefing.review_items : [];
  const excludedItems = Array.isArray(briefing.excluded_items) ? briefing.excluded_items : [];
  dom.publicReviewList.innerHTML = reviewItems.length
    ? reviewItems.map((item) => publicReviewCard(item, "Exclude", "exclude", canModerate)).join("")
    : emptyCard("No visible headlines are available for this edition.");
  dom.publicExcludedList.innerHTML = excludedItems.length
    ? excludedItems.map((item) => publicReviewCard(item, "Restore", "restore", canModerate)).join("")
    : emptyCard("No headlines have been manually removed from this edition.");
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

function renderPublicSnapshot(briefing) {
  if (!dom.publicSnapshotGrid) {
    return;
  }
  if (!briefing) {
    dom.publicSnapshotGrid.innerHTML = emptyCard("The edition snapshot will appear once the latest public briefing is available.");
    return;
  }
  const sourcePanel = briefing.source_panel || {};
  const typeBreakdown = Array.isArray(sourcePanel.type_breakdown) ? sourcePanel.type_breakdown : [];
  const countryBreakdown = Array.isArray(sourcePanel.countries) ? sourcePanel.countries : [];
  const officialCount = typeBreakdown.find((item) => item.type === "official")?.active_count ?? 0;
  const mediaCount = typeBreakdown.find((item) => item.type === "media")?.active_count ?? 0;
  const topTheme = Array.isArray(briefing.top_themes) && briefing.top_themes.length ? briefing.top_themes[0].theme : "No dominant theme yet";
  const leadCountry = countryBreakdown.length ? countryBreakdown[0].country : "Global";
  const cards = [
    {
      label: "Edition date",
      value: briefing.briefing_date || "Latest",
      copy: `${briefing.headline_count || 0} headlines in the current public note`,
    },
    {
      label: "Source mix",
      value: `${officialCount} official / ${mediaCount} media`,
      copy: "Visible items after current source filtering",
    },
    {
      label: "Lead geography",
      value: leadCountry,
      copy: "Most represented country in the current edition",
    },
    {
      label: "Top theme",
      value: topTheme,
      copy: "First theme extracted from the current edition",
    },
  ];
  dom.publicSnapshotGrid.innerHTML = cards
    .map(
      (item) => `
        <article class="snapshot-card">
          <span>${escapeHtml(item.label)}</span>
          <strong>${escapeHtml(item.value)}</strong>
          <p>${escapeHtml(item.copy)}</p>
        </article>
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
    renderPublicSourcePanel(null);
    renderPublicReviewQueue(null);
    renderPublicClusters([]);
    renderRecommendedReading(null);
    renderPublicSnapshot(null);
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
  renderPublicSourcePanel(briefing.source_panel || null);
  renderPublicReviewQueue(briefing);
  renderPublicClusters(briefing.news_clusters || []);
  renderRecommendedReading(briefing.recommended_reading || null);
  renderPublicSnapshot(briefing);
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
      ${
        detail.category === "model"
          ? `
            <div class="actions actions-wrap compact-actions">
              <a class="button-link secondary-link" href="${escapeHtml(item.detail_path || "#")}">Method page</a>
              <a class="button-link secondary-link" href="${escapeHtml(item.teaching_path || "#")}">Teaching page</a>
              <a class="button-link" href="${escapeHtml(item.workbench_path || "/data-lab")}">Open in workbench</a>
            </div>
          `
          : ""
      }
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

function renderModelMethodSnapshot(detail) {
  if (!dom.labModelMethodSnapshot) {
    return;
  }
  const snapshotCards = [
    {
      label: "Family",
      value: detail.family_title || "Model family",
      copy: detail.category_label || "Model method",
    },
    {
      label: "Inputs",
      value: String((detail.inputs || []).length || 0),
      copy: "Required field or design checks",
    },
    {
      label: "Outputs",
      value: String((detail.outputs || []).length + (detail.normal_result ? 1 : 0)),
      copy: "Normal output surfaces",
    },
    {
      label: "Audit",
      value: String((detail.manual_checks || []).length || 0),
      copy: "Manual verification checks",
    },
  ];
  dom.labModelMethodSnapshot.innerHTML = snapshotCards
    .map(
      (item) => `
        <article class="snapshot-card">
          <span>${escapeHtml(item.label)}</span>
          <strong>${escapeHtml(item.value)}</strong>
          <p>${escapeHtml(item.copy)}</p>
        </article>
      `,
    )
    .join("");
}

function renderModelMethodRunbook(detail) {
  if (!dom.labModelMethodRunbook) {
    return;
  }
  const steps = [
    {
      title: "1. Inspect inputs",
      body: "Check the required variables and confirm that the dataset profile supports the fields this method needs.",
    },
    {
      title: "2. Open workbench",
      body: "Use the workbench link to open Data Lab with the correct family and model preselected.",
    },
    {
      title: "3. Read the output package",
      body: "Expect a result detail page with tables, figures if applicable, specification metadata, and an audit trail.",
    },
  ];
  dom.labModelMethodRunbook.innerHTML = steps
    .map(
      (step) => `
        <article class="guide-card">
          <h4>${escapeHtml(step.title)}</h4>
          <p>${escapeHtml(step.body)}</p>
        </article>
      `,
    )
    .join("");
}

function renderModelMethodPage(detail) {
  if (!detail) {
    throw new Error("Model method not found.");
  }
  dom.labModelMethodEyebrow && (dom.labModelMethodEyebrow.textContent = "Model Method");
  dom.labModelMethodTitle && (dom.labModelMethodTitle.textContent = detail.name || "Model Method");
  dom.labModelMethodSummary &&
    (dom.labModelMethodSummary.textContent =
      detail.summary || "Review the method, then open the workbench with the correct settings preselected.");
  dom.labModelMethodFamily && (dom.labModelMethodFamily.textContent = detail.family_title || "Model family");
  dom.labModelMethodHeading && (dom.labModelMethodHeading.textContent = detail.name || "Model Method Detail");
  dom.labModelMethodDescription &&
    (dom.labModelMethodDescription.textContent = detail.overview || detail.summary || "");
  dom.labModelMethodFamilyLink && (dom.labModelMethodFamilyLink.href = detail.family_path || "/data-lab");
  dom.labModelMethodTeachingLink && (dom.labModelMethodTeachingLink.href = detail.teaching_path || "/data-lab");
  dom.labModelMethodWorkbenchLink && (dom.labModelMethodWorkbenchLink.href = detail.workbench_path || "/data-lab");
  renderListCards(dom.labModelMethodEquation, [detail], (item) => `
    <article class="card">
      <h4>${escapeHtml(item.name || "Specification")}</h4>
      <p class="console-box">${escapeHtml(item.equation || "Equation not provided.")}</p>
      <p>${escapeHtml(item.overview || item.summary || "")}</p>
    </article>
  `);
  renderListCards(dom.labModelMethodInputs, detail.inputs || [], (item) => `
    <article class="card">
      <p>${escapeHtml(item)}</p>
    </article>
  `);
  const outputItems = [...(detail.outputs || []), ...(detail.normal_result ? [detail.normal_result] : [])];
  renderListCards(dom.labModelMethodOutputs, outputItems, (item, index) => `
    <article class="card">
      <p>${escapeHtml(item)}</p>
    </article>
  `);
  renderPaperTemplateCards(dom.labModelMethodPaper, detail.paper_template || []);
  renderPaperTablePreviewCards(dom.labModelMethodPreview, detail.paper_table_preview || []);
  renderListCards(dom.labModelMethodAudit, detail.manual_checks || [], (item) => `
    <article class="card">
      <p>${escapeHtml(item)}</p>
    </article>
  `);
  renderModelMethodSnapshot(detail);
  renderModelMethodRunbook(detail);
  updateDocumentTitle();
}

function renderModelTeachingPage(guide) {
  if (!guide) {
    throw new Error("Teaching guide not found.");
  }
  dom.labTeachingEyebrow && (dom.labTeachingEyebrow.textContent = "Teaching Page");
  dom.labTeachingTitle && (dom.labTeachingTitle.textContent = `${guide.name || "Model"} Teaching Page`);
  dom.labTeachingSummary &&
    (dom.labTeachingSummary.textContent =
      guide.summary || "Use this page to learn the model before opening the workbench.");
  dom.labTeachingFamily && (dom.labTeachingFamily.textContent = guide.family_title || "Model family");
  dom.labTeachingHeading && (dom.labTeachingHeading.textContent = `${guide.name || "Model"} Teaching Page`);
  dom.labTeachingDescription &&
    (dom.labTeachingDescription.textContent =
      guide.equation ? `Core equation: ${guide.equation}` : "Review the sections below before estimation.");
  dom.labTeachingMethodLink && (dom.labTeachingMethodLink.href = guide.detail_path || "/data-lab");
  dom.labTeachingWorkbenchLink && (dom.labTeachingWorkbenchLink.href = guide.workbench_path || "/data-lab");
  renderListCards(dom.labTeachingSections, guide.sections || [], (section) => `
    <article class="card">
      <p class="eyebrow eyebrow-compact">${escapeHtml(section.title || "Section")}</p>
      <p>${escapeHtml(section.body || "")}</p>
    </article>
  `);
  renderPaperTemplateCards(dom.labTeachingPaper, guide.paper_template || []);
  renderPaperTablePreviewCards(dom.labTeachingPreview, guide.paper_table_preview || []);
  if (dom.labTeachingSnapshot) {
    const snapshotCards = [
      {
        label: "Family",
        value: guide.family_title || "Model family",
        copy: "Teaching page",
      },
      {
        label: "Lessons",
        value: String((guide.sections || []).length || 0),
        copy: "Core lesson blocks",
      },
      {
        label: "Paper blocks",
        value: String((guide.paper_template || []).length || 0),
        copy: "Paper reporting modules",
      },
      {
        label: "Preview tables",
        value: String((guide.paper_table_preview || []).length || 0),
        copy: "Illustrative table layouts",
      },
    ];
    dom.labTeachingSnapshot.innerHTML = snapshotCards
      .map(
        (item) => `
          <article class="snapshot-card">
            <span>${escapeHtml(item.label)}</span>
            <strong>${escapeHtml(item.value)}</strong>
            <p>${escapeHtml(item.copy)}</p>
          </article>
        `,
      )
      .join("");
  }
  if (dom.labTeachingRunbook) {
    const steps = [
      {
        title: "1. Read the core lessons",
        body: "Start with the lesson blocks to understand when the model is appropriate and what assumptions matter.",
      },
      {
        title: "2. Check paper reporting",
        body: "Use the paper template and table preview to understand how the output should look in a paper.",
      },
      {
        title: "3. Open the workbench",
        body: "Only after the teaching page is clear should you open the workbench and run the model on a private dataset.",
      },
    ];
    dom.labTeachingRunbook.innerHTML = steps
      .map(
        (step) => `
          <article class="guide-card">
            <h4>${escapeHtml(step.title)}</h4>
            <p>${escapeHtml(step.body)}</p>
          </article>
        `,
      )
      .join("");
  }
  updateDocumentTitle();
}

function significanceStars(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "";
  }
  if (numeric < 0.01) {
    return "***";
  }
  if (numeric < 0.05) {
    return "**";
  }
  if (numeric < 0.1) {
    return "*";
  }
  return "";
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

function renderResultInterpretation(target, result) {
  if (!target) {
    return;
  }
  const interpretation = result.interpretation || {};
  const sections = Array.isArray(interpretation.sections) ? interpretation.sections : [];
  const paperOutputs = Array.isArray(interpretation.paper_outputs) ? interpretation.paper_outputs : [];
  const specification = result.specification || {};
  const quickFacts = [
    specification.equation ? `Equation: ${specification.equation}` : "",
    result.audit_trail?.rows_used ? `Rows used: ${result.audit_trail.rows_used}` : "",
    specification.covariance_type ? `Covariance: ${specification.covariance_type}` : "",
    Array.isArray(result.figures) ? `Figures: ${result.figures.length}` : "",
    result.tables && typeof result.tables === "object" ? `Tables: ${Object.keys(result.tables).length}` : "",
  ].filter(Boolean);
  if (!sections.length && !paperOutputs.length) {
    target.innerHTML = emptyCard("No interpretation metadata is available for this result yet.");
    return;
  }
  target.innerHTML = `
    <article class="card interpretation-lead">
      <h4>Interpretation headline</h4>
      <p>${escapeHtml(interpretation.headline || "Use the result together with its tables, figures, and sample metadata.")}</p>
    </article>
    ${
      quickFacts.length
        ? `
          <article class="card">
            <h4>Quick replication facts</h4>
            <div class="chip-row chip-row-compact">
              ${quickFacts.map((item) => `<span class="topic-chip">${escapeHtml(item)}</span>`).join("")}
            </div>
          </article>
        `
        : ""
    }
    ${
      sections.length
        ? `
          <div class="interpretation-grid">
            ${sections
              .map(
                (section) => `
                  <article class="card interpretation-card">
                    <h4>${escapeHtml(section.title || "Interpretation")}</h4>
                    <div class="stack compact">
                      ${(Array.isArray(section.items) ? section.items : [])
                        .map((item) => `<p>${escapeHtml(item)}</p>`)
                        .join("")}
                    </div>
                  </article>
                `,
              )
              .join("")}
          </div>
        `
        : ""
    }
    ${
      paperOutputs.length
        ? `
          <article class="card">
            <h4>Expected paper outputs</h4>
            <div class="chip-row chip-row-compact">
              ${paperOutputs.map((item) => `<span class="topic-chip">${escapeHtml(item)}</span>`).join("")}
            </div>
          </article>
        `
        : ""
    }
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
        <p class="muted">Significance legend: *** p&lt;0.01, ** p&lt;0.05, * p&lt;0.10.</p>
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
                      <td>${escapeHtml(row.coefficient ?? "")}${row.p_value != null ? `<span class="sig-star">${escapeHtml(significanceStars(row.p_value))}</span>` : ""}</td>
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

function renderResultSnapshot(target, payload, result, route) {
  if (!target) {
    return;
  }
  const audit = result.audit_trail || {};
  const snapshotCards = [
    {
      label: "Result type",
      value: result.model_label || result.processing_family || route.category,
      copy: route.category === "models" ? "Model estimation output" : "Data processing output",
    },
    {
      label: "Dataset",
      value: result.asset?.title || payload.record?.title || "Workspace asset",
      copy: "Primary asset behind this result",
    },
    {
      label: "Rows used",
      value: String(audit.rows_used ?? result.observations ?? result.summary?.rows_after_prepare ?? "N/A"),
      copy: "Sample size reflected in the result",
    },
    {
      label: "Figures",
      value: String(Array.isArray(result.figures) ? result.figures.length : 0),
      copy: "Chart or figure outputs attached to the result",
    },
  ];
  target.innerHTML = snapshotCards
    .map(
      (item) => `
        <article class="snapshot-card">
          <span>${escapeHtml(item.label)}</span>
          <strong>${escapeHtml(item.value)}</strong>
          <p>${escapeHtml(item.copy)}</p>
        </article>
      `,
    )
    .join("");
}

function renderResultActions(target, payload, result, route) {
  if (!target) {
    return;
  }
  const audit = result.audit_trail || {};
  const actions = [
    {
      title: "Back to workbench",
      body: "Return to the standalone Data Lab with the correct workflow mode preselected.",
      controls: `<a href="${escapeHtml(route.category === "models" ? "/data-lab?workflow=model#data-lab-workbench" : "/data-lab?workflow=data_processing#data-lab-workbench")}" class="button-link">Open workbench</a>`,
    },
    audit.prepared_asset_id
      ? {
          title: "Prepared sample",
          body: "Download the prepared sample used or generated by this result for manual replication outside the app.",
          controls: `<button type="button" class="secondary" data-download-asset="${escapeHtml(audit.prepared_asset_id)}">Download prepared sample</button>`,
        }
      : null,
    audit.sample_asset_id
      ? {
          title: "Sample used",
          body: "Download the exact sample used in estimation if you want to reproduce the model step by step.",
          controls: `<button type="button" class="secondary" data-download-asset="${escapeHtml(audit.sample_asset_id)}">Download sample used</button>`,
        }
      : null,
    {
      title: "Main workspace",
      body: "Move back to the homepage workspace cockpit, case workspace, or private knowledge base.",
      controls: `<a href="/" class="button-link secondary-link">Open main platform</a>`,
    },
  ].filter(Boolean);
  target.innerHTML = actions
    .map(
      (item) => `
        <article class="action-deck-card">
          <h4>${escapeHtml(item.title)}</h4>
          <p>${escapeHtml(item.body)}</p>
          <div class="actions">${item.controls}</div>
        </article>
      `,
    )
    .join("");
}

function renderResultExportBoard(target, payload, result, route) {
  if (!target) {
    return;
  }
  const audit = result.audit_trail || {};
  const figureCount = Array.isArray(result.figures) ? result.figures.length : 0;
  const cards = [
    {
      eyebrow: "Export",
      title: "Download package",
      copy: "Collect the prepared sample, the exact estimation sample, figures, and the raw JSON payload for manual replication.",
      controls: [
        audit.prepared_asset_id
          ? `<button type="button" class="secondary" data-download-asset="${escapeHtml(audit.prepared_asset_id)}">Prepared sample</button>`
          : "",
        audit.sample_asset_id
          ? `<button type="button" class="secondary" data-download-asset="${escapeHtml(audit.sample_asset_id)}">Sample used</button>`
          : "",
        figureCount ? `<a href="#lab-result-gallery-card" class="button-link secondary-link">Figures (${escapeHtml(figureCount)})</a>` : "",
        `<button type="button" class="secondary" data-download-result-json="true">Raw JSON</button>`,
      ]
        .filter(Boolean)
        .join(""),
    },
    {
      eyebrow: "Verification",
      title: "Manual check surfaces",
      copy: "Move directly to the metrics, specification, audit trail, and raw payload anchors before exporting or citing the result.",
      controls: [
        `<a href="#lab-result-metrics-card" class="button-link secondary-link">Metrics</a>`,
        `<a href="#lab-result-specification-card" class="button-link secondary-link">Specification</a>`,
        `<a href="#lab-result-audit-card" class="button-link secondary-link">Audit trail</a>`,
        `<a href="#lab-result-raw-card" class="button-link secondary-link">Raw JSON</a>`,
      ].join(""),
    },
    {
      eyebrow: "Workspace",
      title: route.category === "models" ? "Result -> Knowledge reuse" : "Prepared output -> Reuse path",
      copy:
        route.category === "models"
          ? `This model result is designed to stay reusable inside the private workspace as ${payload.record?.title || "a knowledge note"}.`
          : "This processing output can feed the next Data Lab step or move back into the main workspace case and knowledge surfaces.",
      controls: [
        `<a href="/#workspace-cockpit-panel" class="button-link secondary-link">Workspace cockpit</a>`,
        `<a href="/#knowledge-base-panel" class="button-link secondary-link">Knowledge base</a>`,
        `<a href="/data-lab" class="button-link secondary-link">Data Lab</a>`,
      ].join(""),
    },
    {
      eyebrow: "Surface map",
      title: route.category === "models" ? "Where this result belongs" : "Where this output should go next",
      copy:
        route.category === "models"
          ? "Model runs should end in the private knowledge base, remain traceable through the result page, and optionally be grouped inside a case workspace."
          : "Processing results should feed a model run, become a reusable asset, or be grouped inside a case workspace for later review.",
      controls: [
        `<span class="topic-chip">Workbench</span>`,
        `<span class="topic-chip">Knowledge Base</span>`,
        `<span class="topic-chip">Case Workspace</span>`,
      ].join(""),
    },
  ];
  target.innerHTML = cards
    .map(
      (item) => `
        <article class="guide-card">
          <p class="eyebrow eyebrow-compact">${escapeHtml(item.eyebrow)}</p>
          <h4>${escapeHtml(item.title)}</h4>
          <p>${escapeHtml(item.copy)}</p>
          <div class="actions compact-actions">${item.controls}</div>
        </article>
      `,
    )
    .join("");
}

async function renderResultPreview(previewTarget, galleryTarget, result) {
  if (!previewTarget && !galleryTarget) {
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
  if (previewTarget) {
    previewTarget.innerHTML = blocks.join("") || emptyCard("No preview rows are available for this result.");
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
    if (galleryTarget) {
      galleryTarget.innerHTML = `
        <article class="card">
          <h4>Figures</h4>
          <div class="result-figure-grid">${figureCards.join("")}</div>
        </article>
      `;
    }
  } else if (galleryTarget) {
    galleryTarget.innerHTML = emptyCard("No figures are attached to this result.");
  }
}

async function loadMethodDetailPage() {
  const route = extractDataLabMethodRoute();
  if (!route || isExperienceLocked()) {
    return;
  }
  const payload = await api(`/api/data-lab/${route.category}/${route.family}`, {}, false);
  renderDataLabMethodDetail(payload.family);
}

async function loadModelMethodPage() {
  const route = extractDataLabModelMethodRoute();
  if (!route || isExperienceLocked()) {
    return;
  }
  const payload = await api(`/api/data-lab/models/${route.family}/${route.method}`, {}, false);
  renderModelMethodPage(payload.method);
}

async function loadTeachingGuidePage() {
  const route = extractDataLabTeachingRoute();
  if (!route || isExperienceLocked()) {
    return;
  }
  const payload = await api(`/api/data-lab/learn/models/${route.family}/${route.method}`, {}, false);
  renderModelTeachingPage(payload.guide);
}

async function loadResultDetailPage() {
  const route = extractDataLabResultRoute();
  if (!route || isExperienceLocked()) {
    return;
  }
  await ensureAuthenticatedUser();
  const payload = await api(`/api/data-lab/results/${route.category}/${route.id}`);
  state.currentResultDetail = payload;
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
  renderResultSnapshot(dom.labResultSnapshot, payload, result, route);
  renderResultActions(dom.labResultActions, payload, result, route);
  renderResultExportBoard(dom.labResultExportBoard, payload, result, route);
  renderResultMetrics(dom.labResultMetrics, result);
  renderResultInterpretation(dom.labResultInterpretation, result);
  renderResultSpecification(dom.labResultSpecification, result);
  renderResultTables(dom.labResultTables, result);
  renderResultAudit(dom.labResultAudit, result);
  await renderResultPreview(dom.labResultPreview, dom.labResultGallery, result);
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
  const integrationKind = document.querySelector('#integration-form select[name="kind"]');
  if (integrationKind) {
    applyIntegrationProviderPreset(integrationKind.value);
  }
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
  let nextPath = publicMonitorPathForView(state.publicSourceView);
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
  const publicView = extractPublicMonitorViewRoute();
  if (briefingSlug && state.selectedPublicBriefing?.title) {
    document.title = `${state.selectedPublicBriefing.title} | Economic Research Platform`;
    return;
  }
  if (summaryWindow && state.publicSummary?.title) {
    document.title = `${state.publicSummary.title} | Economic Research Platform`;
    return;
  }
  if (pageMode === "public-monitor") {
    if (publicView === "us") {
      document.title = "United States | Public Daily Monitor";
      return;
    }
    if (publicView === "cn") {
      document.title = "China | Public Daily Monitor";
      return;
    }
    if (publicView === "developed") {
      document.title = "Developed Markets | Public Daily Monitor";
      return;
    }
    document.title = "Public Daily Monitor | Economic Research Platform";
    return;
  }
  if (pageMode === "data-lab") {
    document.title = "Data Lab | Economic Research Platform";
    return;
  }
  if (pageMode === "data-lab-model-method" && dom.labModelMethodTitle?.textContent) {
    document.title = `${dom.labModelMethodTitle.textContent} | Economic Research Platform`;
    return;
  }
  if (pageMode === "data-lab-teaching" && dom.labTeachingTitle?.textContent) {
    document.title = `${dom.labTeachingTitle.textContent} | Economic Research Platform`;
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
  await maybeLoadPublicIdentity();
  state.publicSourceView = extractPublicMonitorViewRoute() || "official";
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
  try {
    const payload = await api("/api/auth/me", {}, false);
    if (!payload?.user) {
      throw new Error("No active session");
    }
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
      if (state.selectedWorkspaceId) {
        await refreshWorkspaceData();
      } else {
        clearPrivateLists();
      }
      if (hasOptimizationLabUI() && state.selectedWorkspaceId) {
        await refreshOptimizationResults();
      } else {
        renderOptimizationResults([]);
      }
    } catch {
    clearSession({ redirect: false });
    renderSession();
    renderWorkspaceOptions();
    clearPrivateLists();
  }
}

async function refreshWorkspaceData() {
  ensureWorkspace();
  const workspaceId = state.selectedWorkspaceId;
  const [integrations, briefings, literature, assets, knowledge, schedules, cases, templates] = await Promise.all([
    api("/api/integrations"),
    api(`/api/workspaces/${workspaceId}/briefings`),
    api(`/api/workspaces/${workspaceId}/literature`),
    api(`/api/workspaces/${workspaceId}/assets`),
    api(`/api/workspaces/${workspaceId}/knowledge?view=summary&status=all`),
    api(`/api/workspaces/${workspaceId}/schedules`),
    api(`/api/workspaces/${workspaceId}/knowledge-cases`),
    api(`/api/workspaces/${workspaceId}/lab-templates`),
  ]);
  state.labTemplates = templates.items || [];
  state.knowledgeDetails = Object.fromEntries(
    Object.entries(state.knowledgeDetails || {}).filter(([recordId]) => (knowledge.items || []).some((item) => item.id === recordId)),
  );
  state.knowledgeRelated = Object.fromEntries(
    Object.entries(state.knowledgeRelated || {}).filter(([recordId]) => (knowledge.items || []).some((item) => item.id === recordId)),
  );
  state.caseDetails = Object.fromEntries(
    Object.entries(state.caseDetails || {}).filter(([caseId]) => (cases.items || []).some((item) => item.id === caseId)),
  );
  renderIntegrations(integrations.items || []);
  renderBriefings(briefings.items || []);
  renderLiterature(literature.items || []);
  renderAssets(assets.items || []);
  renderKnowledgeCases(cases.items || []);
  renderKnowledge(knowledge.items || []);
  renderSchedules(schedules.items || []);
  renderAllLabTemplateBuilders();
  if (state.selectedAnalysisAssetId && dom.analysisAssetSelect) {
    try {
      await loadSelectedAssetProfile();
    } catch (error) {
      showToast(error.message || "Failed to load dataset profile.", true);
    }
  }
  renderWorkspaceCockpit();
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

async function handleBulkLiteraturePdfImport() {
  ensureWorkspace();
  const response = await api(`/api/workspaces/${state.selectedWorkspaceId}/literature/import-pdfs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ entry_ids: [] }),
  });
  await refreshWorkspaceData();
  showToast(`Paper Library PDF import finished: ${response.imported_count} imported, ${response.skipped_count} skipped, ${response.failed_count} failed.`);
}

async function handleBulkLiteratureKnowledgeImport() {
  ensureWorkspace();
  const response = await api(`/api/workspaces/${state.selectedWorkspaceId}/literature/import-knowledge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ entry_ids: [] }),
  });
  await refreshWorkspaceData();
  showToast(`Knowledge note import finished: ${response.imported_count} processed, ${response.failed_count} failed.`);
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
  const recordId = String(payload.record_id || "").trim();
  delete payload.record_id;
  payload.tags = payload.tags ? payload.tags.split(",").map((item) => item.trim()).filter(Boolean) : [];
  const templateKey = event.currentTarget.dataset.template || "";
  if (!recordId) {
    payload.metadata = templateKey ? { source_type: "manual_workspace", note_template: templateKey } : { source_type: "manual_workspace" };
  } else {
    delete payload.metadata;
  }
  const response = await api(`/api/workspaces/${state.selectedWorkspaceId}/knowledge${recordId ? `/${recordId}` : ""}`, {
    method: recordId ? "PATCH" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  state.selectedKnowledgeRecordId = response.record?.id || state.selectedKnowledgeRecordId;
  await refreshWorkspaceData();
  if (response.record?.id) {
    await loadKnowledgeDetail(response.record.id);
  }
  resetKnowledgeComposer();
  showToast(recordId ? "Private note updated." : "Private note saved.");
}

async function handleKnowledgeCase(event) {
  event.preventDefault();
  ensureWorkspace();
  const formData = new FormData(event.currentTarget);
  const payload = Object.fromEntries(formData.entries());
  const caseId = String(payload.case_id || "").trim();
  delete payload.case_id;
  payload.tags = payload.tags ? payload.tags.split(",").map((item) => item.trim()).filter(Boolean) : [];
  const response = await api(`/api/workspaces/${state.selectedWorkspaceId}/knowledge-cases${caseId ? `/${caseId}` : ""}`, {
    method: caseId ? "PATCH" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await refreshWorkspaceData();
  const targetCaseId = response.case?.id || caseId;
  if (targetCaseId) {
    focusKnowledgeCase(targetCaseId);
  }
  resetKnowledgeCaseComposer();
  showToast(caseId ? "Private case updated." : "Private case created.");
}

async function addItemToSelectedCase(itemType, refId, metadata = {}) {
  ensureWorkspace();
  if (!state.selectedKnowledgeCaseId) {
    throw new Error("Select or create a case first.");
  }
  const response = await api(`/api/workspaces/${state.selectedWorkspaceId}/knowledge-cases/${state.selectedKnowledgeCaseId}/items`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      item_type: itemType,
      ref_id: refId,
      metadata,
    }),
  });
  await refreshWorkspaceData();
  focusKnowledgeCase(state.selectedKnowledgeCaseId);
  showToast(`${response.created === false ? "Already linked in case" : "Added to case"}: ${response.item?.title || "workspace item"}`);
}

function applyKnowledgeFiltersFromDom() {
  state.knowledgeSearchQuery = dom.knowledgeSearchInput?.value || "";
  state.knowledgeStatusFilter = dom.knowledgeStatusFilter?.value || "active";
  state.knowledgeTypeFilter = dom.knowledgeTypeFilter?.value || "all";
  state.knowledgeTagFilter = dom.knowledgeTagFilter?.value || "all";
  renderKnowledge(state.workspaceKnowledge);
}

function resetKnowledgeFilters() {
  state.knowledgeSearchQuery = "";
  state.knowledgeStatusFilter = "active";
  state.knowledgeTypeFilter = "all";
  state.knowledgeTagFilter = "all";
  renderKnowledge(state.workspaceKnowledge);
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

async function handleSignOut() {
  try {
    await api("/api/auth/logout", { method: "POST" }, false);
  } catch {
    // Ignore server-side logout failures and clear local state anyway.
  }
  clearSession({ redirect: detectPageMode() !== "home" });
  showToast("Signed out.");
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
  const payload = buildPreparePayload(assetId);
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
  const payload = buildModelPayload(assetId);
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
  const headers = new Headers();
  if (state.token) {
    headers.set("Authorization", `Bearer ${state.token}`);
  }
  const response = await fetch(`/api/assets/${result.asset.id}/download`, {
    credentials: "same-origin",
    headers,
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
    const details = [response.provider_name, response.resolved_model].filter(Boolean).join(" | ");
    showToast(`${details ? `${details}: ` : ""}${response.preview || "Connection test succeeded."}`);
    return;
  }
  if (deleteId) {
    await api(`/api/integrations/${deleteId}`, { method: "DELETE" });
    await refreshWorkspaceData();
    showToast("Connection deleted.");
  }
  renderAllLabTemplateBuilders();
}

async function downloadAsset(assetId) {
  const headers = new Headers();
  if (state.token) {
    headers.set("Authorization", `Bearer ${state.token}`);
  }
  const response = await fetch(`/api/assets/${assetId}/download`, {
    credentials: "same-origin",
    headers,
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

async function copyPlainTextToClipboard(text) {
  if (!text) {
    throw new Error("Nothing to copy.");
  }
  await navigator.clipboard.writeText(text);
}

function downloadTextFile(filename, content) {
  const blob = new Blob([content || ""], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function sanitizeFilenameBase(value) {
  return String(value || "knowledge-note")
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fff]+/g, "-")
    .replace(/^-+|-+$/g, "") || "knowledge-note";
}

async function copyToClipboard(text) {
  if (!text) {
    throw new Error("Nothing to copy.");
  }
  await navigator.clipboard.writeText(absolutePublicUrl(text));
}

function scrollToTarget(targetId) {
  if (!targetId) {
    return false;
  }
  const target = document.getElementById(targetId);
  if (!target) {
    return false;
  }
  document.querySelectorAll(".panel.is-spotlit").forEach((node) => node.classList.remove("is-spotlit"));
  target.classList.add("is-spotlit");
  target.scrollIntoView({ behavior: "smooth", block: "start" });
  window.clearTimeout(scrollToTarget.timer);
  scrollToTarget.timer = window.setTimeout(() => target.classList.remove("is-spotlit"), 2200);
  return true;
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

async function handleLiteratureActions(event) {
  const target = event.target.closest("[data-import-literature-pdf], [data-download-literature-asset], [data-derive-literature-note]");
  if (!target) {
    return;
  }
  ensureWorkspace();
  const importId = target.getAttribute("data-import-literature-pdf");
  const downloadId = target.getAttribute("data-download-literature-asset");
  const deriveId = target.getAttribute("data-derive-literature-note");
  const deriveMode = target.getAttribute("data-derive-literature-mode");
  if (importId) {
    const response = await api(`/api/workspaces/${state.selectedWorkspaceId}/literature/${importId}/import-pdf`, {
      method: "POST",
    });
    await refreshWorkspaceData();
    const assetTitle = response.asset?.title || response.entry?.workspace_pdf_asset_title || "paper PDF";
    showToast(`${response.imported === false ? "Private copy already exists" : "Paper imported"}: ${assetTitle}`);
    return;
  }
  if (downloadId) {
    await downloadAsset(downloadId);
    showToast("Private paper download started.");
    return;
  }
  if (deriveId && deriveMode) {
    const response = await api(`/api/workspaces/${state.selectedWorkspaceId}/literature/${deriveId}/derive-note`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: deriveMode }),
    });
    await refreshWorkspaceData();
    const recordTitle = response.record?.title || "derived note";
    showToast(`${response.imported === false ? "Follow-up note already exists" : "Follow-up note created"}: ${recordTitle}`);
    focusKnowledgeRecord(response.record?.id || "");
  }
}

function applyKnowledgeTemplate(templateKey) {
  const template = KNOWLEDGE_TEMPLATES[templateKey];
  const knowledgeForm = document.getElementById("knowledge-form");
  if (!template || !knowledgeForm) {
    return;
  }
  if (state.editingKnowledgeRecordId) {
    resetKnowledgeComposer();
  }
  const titleField = knowledgeForm.elements.namedItem("title");
  const tagsField = knowledgeForm.elements.namedItem("tags");
  const contentField = knowledgeForm.elements.namedItem("content");
  if (titleField) {
    titleField.value = template.title;
  }
  if (tagsField) {
    tagsField.value = template.tags.join(", ");
  }
  if (contentField) {
    contentField.value = template.content;
  }
  knowledgeForm.dataset.template = templateKey;
}

async function handleWorkbenchActions(event) {
  const target = event.target.closest("[data-scroll-target], [data-knowledge-template], [data-select-knowledge], [data-open-knowledge-record], [data-copy-knowledge-markdown], [data-download-knowledge-markdown], [data-edit-knowledge], [data-archive-knowledge], [data-restore-knowledge], [data-delete-knowledge], [data-import-briefing-knowledge], [data-import-literature-knowledge], [data-create-workspace-digest], [data-select-knowledge-case], [data-edit-knowledge-case], [data-delete-knowledge-case], [data-add-case-item], [data-remove-case-item], [data-download-result-json]");
  if (!target) {
    return;
  }
  const scrollTarget = target.getAttribute("data-scroll-target");
  if (scrollTarget) {
    if (!scrollToTarget(scrollTarget)) {
      throw new Error("Target panel not found.");
    }
    return;
  }
  const templateKey = target.getAttribute("data-knowledge-template");
  if (templateKey) {
    applyKnowledgeTemplate(templateKey);
    const knowledgePanelFound = scrollToTarget("knowledge-base-panel");
    if (knowledgePanelFound) {
      const titleField = document.querySelector('#knowledge-form input[name="title"]');
      titleField?.focus();
    }
    showToast(`Template loaded: ${KNOWLEDGE_TEMPLATES[templateKey]?.label || "Note template"}`);
    return;
  }
  const downloadResultJson = target.getAttribute("data-download-result-json");
  if (downloadResultJson) {
    if (!state.currentResultDetail) {
      throw new Error("No result payload is loaded.");
    }
    const route = extractDataLabResultRoute();
    const filenameBase = route?.category === "models" ? "data-lab-model-result" : "data-lab-processing-result";
    downloadTextFile(`${filenameBase}.json`, JSON.stringify(state.currentResultDetail, null, 2), "application/json");
    showToast("Result JSON download started.");
    return;
  }
  const createDigest = target.getAttribute("data-create-workspace-digest");
  if (createDigest) {
    ensureWorkspace();
    const response = await api(`/api/workspaces/${state.selectedWorkspaceId}/knowledge/digest`, {
      method: "POST",
    });
    await refreshWorkspaceData();
    focusKnowledgeRecord(response.record?.id || "");
    scrollToTarget("knowledge-base-panel");
    showToast(`Workspace digest created: ${response.record?.title || "digest"}`);
    return;
  }
  const caseId = target.getAttribute("data-select-knowledge-case");
  if (caseId) {
    const found = focusKnowledgeCase(caseId);
    if (found) {
      scrollToTarget("knowledge-base-panel");
    }
    showToast(found ? "Active case updated." : "Case not found.");
    return;
  }
  const editCaseId = target.getAttribute("data-edit-knowledge-case");
  if (editCaseId) {
    const loaded = startKnowledgeCaseEdit(editCaseId);
    if (!loaded) {
      throw new Error("Case not found.");
    }
    scrollToTarget("knowledge-base-panel");
    showToast("Case loaded for editing.");
    return;
  }
  const deleteCaseId = target.getAttribute("data-delete-knowledge-case");
  if (deleteCaseId) {
    ensureWorkspace();
    if (!window.confirm("Delete this case and all of its linked item references?")) {
      return;
    }
    await api(`/api/workspaces/${state.selectedWorkspaceId}/knowledge-cases/${deleteCaseId}`, {
      method: "DELETE",
    });
    if (state.selectedKnowledgeCaseId === deleteCaseId) {
      state.selectedKnowledgeCaseId = "";
      localStorage.removeItem(storageKeys.caseId);
    }
    if (state.editingKnowledgeCaseId === deleteCaseId) {
      resetKnowledgeCaseComposer();
    }
    await refreshWorkspaceData();
    showToast("Case deleted.");
    return;
  }
  const addCaseItemId = target.getAttribute("data-add-case-item");
  const addCaseItemType = target.getAttribute("data-case-item-type");
  if (addCaseItemId && addCaseItemType) {
    await addItemToSelectedCase(addCaseItemType, addCaseItemId, {
      source_panel: detectPageMode() === "data-lab" ? "data_lab" : "workspace",
    });
    return;
  }
  const removeCaseItemId = target.getAttribute("data-remove-case-item");
  const removeCaseId = target.getAttribute("data-case-id");
  if (removeCaseItemId && removeCaseId) {
    ensureWorkspace();
    await api(`/api/workspaces/${state.selectedWorkspaceId}/knowledge-cases/${removeCaseId}/items/${removeCaseItemId}`, {
      method: "DELETE",
    });
    await refreshWorkspaceData();
    focusKnowledgeCase(removeCaseId);
    showToast("Case item removed.");
    return;
  }
  const recordId = target.getAttribute("data-select-knowledge");
  if (recordId) {
    focusKnowledgeRecord(recordId);
    return;
  }
  const openKnowledgeId = target.getAttribute("data-open-knowledge-record");
  if (openKnowledgeId) {
    const found = focusKnowledgeRecord(openKnowledgeId);
    if (found) {
      scrollToTarget("knowledge-base-panel");
    }
    showToast(found ? "Scrolled to the private note." : "Private note is not available in the current filter view.");
    return;
  }
  const editKnowledgeId = target.getAttribute("data-edit-knowledge");
  if (editKnowledgeId) {
    const loaded = await startKnowledgeEdit(editKnowledgeId);
    if (!loaded) {
      throw new Error("Knowledge note could not be loaded for editing.");
    }
    scrollToTarget("knowledge-base-panel");
    document.querySelector('#knowledge-form input[name="title"]')?.focus();
    showToast("Knowledge note loaded into the editor.");
    return;
  }
  const archiveKnowledgeId = target.getAttribute("data-archive-knowledge");
  if (archiveKnowledgeId) {
    ensureWorkspace();
    const archiveReason = window.prompt("Archive reason (optional)", "") ?? null;
    if (archiveReason === null) {
      return;
    }
    await api(`/api/workspaces/${state.selectedWorkspaceId}/knowledge/${archiveKnowledgeId}/archive`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: archiveReason }),
    });
    if (state.editingKnowledgeRecordId === archiveKnowledgeId) {
      resetKnowledgeComposer();
    }
    await refreshWorkspaceData();
    showToast("Knowledge note archived.");
    return;
  }
  const restoreKnowledgeId = target.getAttribute("data-restore-knowledge");
  if (restoreKnowledgeId) {
    ensureWorkspace();
    await api(`/api/workspaces/${state.selectedWorkspaceId}/knowledge/${restoreKnowledgeId}/restore`, {
      method: "POST",
    });
    await refreshWorkspaceData();
    focusKnowledgeRecord(restoreKnowledgeId);
    showToast("Knowledge note restored.");
    return;
  }
  const deleteKnowledgeId = target.getAttribute("data-delete-knowledge");
  if (deleteKnowledgeId) {
    ensureWorkspace();
    if (!window.confirm("Delete this knowledge note permanently?")) {
      return;
    }
    await api(`/api/workspaces/${state.selectedWorkspaceId}/knowledge/${deleteKnowledgeId}`, {
      method: "DELETE",
    });
    if (state.editingKnowledgeRecordId === deleteKnowledgeId) {
      resetKnowledgeComposer();
    }
    await refreshWorkspaceData();
    showToast("Knowledge note deleted.");
    return;
  }
  const briefingKnowledgeId = target.getAttribute("data-import-briefing-knowledge");
  if (briefingKnowledgeId) {
    ensureWorkspace();
    const response = await api(`/api/workspaces/${state.selectedWorkspaceId}/briefings/${briefingKnowledgeId}/import-knowledge`, {
      method: "POST",
    });
    await refreshWorkspaceData();
    focusKnowledgeRecord(response.record?.id || "");
    showToast(`${response.imported === false ? "Briefing note already exists" : "Briefing captured in the knowledge base"}: ${response.record?.title || "briefing note"}`);
    return;
  }
  const literatureKnowledgeId = target.getAttribute("data-import-literature-knowledge");
  if (literatureKnowledgeId) {
    ensureWorkspace();
    const response = await api(`/api/workspaces/${state.selectedWorkspaceId}/literature/${literatureKnowledgeId}/import-knowledge`, {
      method: "POST",
    });
    await refreshWorkspaceData();
    focusKnowledgeRecord(response.record?.id || "");
    showToast(`${response.imported === false ? "Knowledge note already exists" : "Saved to knowledge base"}: ${response.record?.title || "paper note"}`);
    return;
  }
  const copyRecordId = target.getAttribute("data-copy-knowledge-markdown");
  if (copyRecordId) {
    const previewRecord = mergeKnowledgeRecord(copyRecordId);
    const record = previewRecord?.content ? previewRecord : (await loadKnowledgeDetail(copyRecordId)) || previewRecord;
    await copyPlainTextToClipboard(record?.content || record?.content_excerpt || "");
    showToast("Knowledge note copied.");
    return;
  }
  const downloadRecordId = target.getAttribute("data-download-knowledge-markdown");
  if (downloadRecordId) {
    const previewRecord = mergeKnowledgeRecord(downloadRecordId);
    const record = previewRecord?.content ? previewRecord : (await loadKnowledgeDetail(downloadRecordId)) || previewRecord;
    downloadTextFile(`${sanitizeFilenameBase(record?.title || "knowledge-note")}.md`, record?.content || record?.content_excerpt || "");
    showToast("Knowledge note download started.");
  }
}

async function handlePublicActions(event) {
  const target = event.target.closest("[data-public-slug], [data-copy-public-url], [data-public-moderation]");
  if (!target) {
    return;
  }
  const slug = target.getAttribute("data-public-slug");
  const publicUrl = target.getAttribute("data-copy-public-url");
  const moderationAction = target.getAttribute("data-public-moderation");
  if (publicUrl) {
    await copyToClipboard(publicUrl);
    showToast("Public link copied.");
    return;
  }
  if (moderationAction) {
    const briefingSlug = state.selectedPublicBriefing?.slug || extractBriefingSlugFromLocation();
    if (!briefingSlug) {
      throw new Error("No public briefing is selected.");
    }
    await ensureAuthenticatedUser();
    await api(`/api/public/briefings/${briefingSlug}/moderation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: moderationAction,
        url: target.getAttribute("data-public-url") || "",
        title: target.getAttribute("data-public-title") || "",
      }),
    });
    await loadPublicData();
    showToast(moderationAction === "restore" ? "Headline restored to the public edition." : "Headline removed from the public edition.");
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
  const integrationKind = integrationForm?.elements.namedItem("kind");
  const briefingForm = document.getElementById("briefing-form");
  const openalexForm = document.getElementById("openalex-form");
  const importOpenalexButton = document.getElementById("import-openalex");
  const importLiteraturePdfsButton = document.getElementById("import-literature-pdfs");
  const importLiteratureKnowledgeButton = document.getElementById("import-literature-knowledge");
  const uploadForm = document.getElementById("upload-form");
  const knowledgeCaseForm = document.getElementById("knowledge-case-form");
  const knowledgeForm = document.getElementById("knowledge-form");
  const knowledgeSearchForm = document.getElementById("knowledge-search-form");
  const scheduleForm = document.getElementById("schedule-form");
  const variableGuideForm = document.getElementById("variable-guide-form");
  const prepareForm = document.getElementById("prepare-form");
  const modelForm = document.getElementById("model-form");
  const plotForm = document.getElementById("plot-form");
  const optimizationSuiteForm = document.getElementById("optimization-suite-form");
  const optimizationDefaultsButton = document.getElementById("optimization-defaults-button");
  const optimizationClearSelection = document.getElementById("optimization-clear-selection");

  registerForm?.addEventListener("submit", wrap(handleRegister));
  loginForm?.addEventListener("submit", wrap(handleLogin));
  workspaceForm?.addEventListener("submit", wrap(handleCreateWorkspace));
  integrationForm?.addEventListener("submit", wrap(handleIntegration));
  integrationKind?.addEventListener("change", (event) => {
    applyIntegrationProviderPreset(event.target.value);
  });
  briefingForm?.addEventListener("submit", wrap(handleBriefing));
  openalexForm?.addEventListener("submit", wrap(handleOpenAlexSearch));
  importOpenalexButton?.addEventListener("click", wrap(handleOpenAlexImport));
  importLiteraturePdfsButton?.addEventListener("click", wrap(handleBulkLiteraturePdfImport));
  importLiteratureKnowledgeButton?.addEventListener("click", wrap(handleBulkLiteratureKnowledgeImport));
  uploadForm?.addEventListener("submit", wrap(handleUpload));
  knowledgeCaseForm?.addEventListener("submit", wrap(handleKnowledgeCase));
  knowledgeForm?.addEventListener("submit", wrap(handleKnowledge));
  knowledgeSearchForm?.addEventListener("submit", wrap(async (event) => {
    event.preventDefault();
    applyKnowledgeFiltersFromDom();
  }));
  dom.knowledgeSearchInput?.addEventListener("input", applyKnowledgeFiltersFromDom);
  dom.knowledgeStatusFilter?.addEventListener("change", applyKnowledgeFiltersFromDom);
  dom.knowledgeTypeFilter?.addEventListener("change", applyKnowledgeFiltersFromDom);
  dom.knowledgeTagFilter?.addEventListener("change", applyKnowledgeFiltersFromDom);
  dom.knowledgeResetButton?.addEventListener("click", () => resetKnowledgeFilters());
  dom.knowledgeCaseCancelButton?.addEventListener("click", () => resetKnowledgeCaseComposer());
  dom.knowledgeCancelButton?.addEventListener("click", () => resetKnowledgeComposer());
  scheduleForm?.addEventListener("submit", wrap(handleSchedule));
  variableGuideForm?.addEventListener("submit", wrap(handleVariableGuide));
  prepareForm?.addEventListener("submit", wrap(handlePrepareSample));
  modelForm?.addEventListener("submit", wrap(handleModelRun));
  plotForm?.addEventListener("submit", wrap(handlePlot));
  optimizationSuiteForm?.addEventListener("submit", wrap(handleOptimizationSuiteRun));
  optimizationDefaultsButton?.addEventListener("click", () => {
    if (!state.optimizationCatalog) {
      return;
    }
    setMultiSelectValues(optimizationElement("optimization-optimizer-select"), state.optimizationCatalog.defaults?.optimizers || []);
    setMultiSelectValues(optimizationElement("optimization-function-select"), state.optimizationCatalog.defaults?.functions || []);
    updateBuilderStatus("optimization", "Applied the default comparative optimization suite.");
  });
  optimizationClearSelection?.addEventListener("click", () => {
    setMultiSelectValues(optimizationElement("optimization-optimizer-select"), []);
    setMultiSelectValues(optimizationElement("optimization-function-select"), []);
    updateBuilderStatus("optimization", "Cleared the current optimization selection.");
  });
  ["prepare", "model", "optimization"].forEach((prefix) => {
    labBuilderElement(prefix, "template-select")?.addEventListener("change", () => renderLabTemplateBuilder(prefix));
    labBuilderElement(prefix, "variant-select")?.addEventListener("change", () => applyVariantPresetSelection(prefix));
    labBuilderElement(prefix, "variant-json")?.addEventListener("input", () => {
      const textarea = labBuilderElement(prefix, "variant-json");
      if (textarea) {
        textarea.dataset.boundPreset = "0";
      }
      updateBuilderStatus(prefix, "Advanced specification updated. Save as a template to reuse it later.");
    });
    labBuilderElement(prefix, "save-template")?.addEventListener("click", wrap(async () => {
      await saveCurrentLabTemplate(prefix);
    }));
  });
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
  dom.publicSourceView?.addEventListener("change", () => {
    state.publicSourceView = dom.publicSourceView?.value || "all";
    const nextPath = publicMonitorPathForView(state.publicSourceView);
    if (detectPageMode() === "public-monitor" && window.location.pathname !== nextPath) {
      window.history.replaceState({}, "", nextPath);
      updateDocumentTitle();
    }
    renderPublicSourcePanel(state.selectedPublicBriefing?.source_panel || null);
  });
  dom.publicSourceTypeFilter?.addEventListener("change", () => {
    state.publicSourceTypeFilter = dom.publicSourceTypeFilter?.value || "all";
    renderPublicSourcePanel(state.selectedPublicBriefing?.source_panel || null);
  });
  dom.publicSourceCountryFilter?.addEventListener("change", () => {
    state.publicSourceCountryFilter = dom.publicSourceCountryFilter?.value || "all";
    renderPublicSourcePanel(state.selectedPublicBriefing?.source_panel || null);
  });
  dom.publicSourceRegionFilter?.addEventListener("change", () => {
    state.publicSourceRegionFilter = dom.publicSourceRegionFilter?.value || "all";
    renderPublicSourcePanel(state.selectedPublicBriefing?.source_panel || null);
  });
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
      state.knowledgeDetails = {};
      state.knowledgeRelated = {};
      state.caseDetails = {};
      state.workspaceCases = [];
      state.selectedKnowledgeCaseId = "";
      state.selectedKnowledgeRecordId = "";
      state.knowledgeSearchQuery = "";
      state.knowledgeTypeFilter = "all";
      state.knowledgeTagFilter = "all";
      localStorage.removeItem(storageKeys.caseId);
      await refreshWorkspaceData();
      if (hasOptimizationLabUI()) {
        await refreshOptimizationResults();
      }
    }),
  );
  dom.knowledgeCaseActiveSelect?.addEventListener("change", (event) => {
    state.selectedKnowledgeCaseId = event.target.value || "";
    if (state.selectedKnowledgeCaseId) {
      localStorage.setItem(storageKeys.caseId, state.selectedKnowledgeCaseId);
      void loadKnowledgeCaseDetail(state.selectedKnowledgeCaseId);
    } else {
      localStorage.removeItem(storageKeys.caseId);
      renderKnowledgeCasePreview(null);
    }
    syncKnowledgeCaseOptions();
    renderWorkspaceCockpit();
    renderLabContext();
  });
  dom.labCaseSelect?.addEventListener("change", (event) => {
    state.selectedKnowledgeCaseId = event.target.value || "";
    if (state.selectedKnowledgeCaseId) {
      localStorage.setItem(storageKeys.caseId, state.selectedKnowledgeCaseId);
      void loadKnowledgeCaseDetail(state.selectedKnowledgeCaseId);
    } else {
      localStorage.removeItem(storageKeys.caseId);
      renderKnowledgeCasePreview(null);
    }
    syncKnowledgeCaseOptions();
    renderWorkspaceCockpit();
    renderLabContext();
  });
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
  document.body?.addEventListener("click", wrap(handleWorkbenchActions));
  dom.literatureList?.addEventListener("click", wrap(handleLiteratureActions));
  dom.publicDateSwitcher?.addEventListener("click", wrap(handlePublicActions));
  dom.publicBriefingList?.addEventListener("click", wrap(handlePublicActions));
  dom.publicSummaryFeatured?.addEventListener("click", wrap(handlePublicActions));
  dom.publicReviewList?.addEventListener("click", wrap(handlePublicActions));
  dom.publicExcludedList?.addEventListener("click", wrap(handlePublicActions));
  if (integrationKind) {
    applyIntegrationProviderPreset(integrationKind.value);
  }
  initializeDataLabFromLocation();
  updateWorkflowVisibility();
}

async function init() {
  bind();
  try {
    await fetchHealth();
    await maybeLoadPublicIdentity();
    applyAccessGateState();
    const pageMode = detectPageMode();
    if (hasPrivateWorkspaceUI() && !isExperienceLocked()) {
      clearPrivateLists();
      renderSession();
      renderWorkspaceOptions();
      await loadSession();
    } else if (hasPrivateWorkspaceUI()) {
      renderSession();
    }
    if (!isExperienceLocked() && (
      pageMode === "data-lab" ||
      pageMode === "data-lab-method-detail" ||
      pageMode === "data-lab-model-method" ||
      pageMode === "data-lab-teaching"
    )) {
      await loadDataLabCatalog();
      if (pageMode === "data-lab" && hasOptimizationLabUI()) {
        try {
          await loadOptimizationCatalog();
          renderOptimizationCatalog();
        } catch (error) {
          renderOptimizationCatalog();
          showToast(error.message || "Failed to load the optimization catalog.", true);
        }
      }
    }
    if (pageMode === "data-lab" && !isExperienceLocked()) {
      renderLabContext();
      renderProcessingHistory([]);
      renderModelHistory([]);
      renderOptimizationResults([]);
    }
    if (pageMode === "data-lab-method-detail") {
      await loadMethodDetailPage();
    }
    if (pageMode === "data-lab-model-method") {
      await loadModelMethodPage();
    }
    if (pageMode === "data-lab-teaching") {
      await loadTeachingGuidePage();
    }
    if (pageMode === "data-lab-result-detail") {
      await loadResultDetailPage();
    }
    if (pageMode === "optimization-result-detail") {
      await loadOptimizationResultPage();
    }
    if (hasPublicMonitorUI() && !document.body.classList.contains("experience-locked")) {
      await loadPublicData();
    }
    applyAccessGateState();
  } catch (error) {
    showToast(error.message || "Initialization failed.", true);
  }
}

init();
