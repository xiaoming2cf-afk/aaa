from __future__ import annotations

from copy import deepcopy
from urllib.parse import urlencode


PROCESSING_FAMILY_CATALOG: list[dict[str, object]] = [
    {
        "slug": "sample_preparation",
        "title": "Sample Preparation",
        "category": "data_processing",
        "category_label": "Data Processing",
        "summary": "Build an analysis-ready sample before cleaning, plotting, or model estimation.",
        "description": "Use this family when the main question is whether the sample itself is well-formed. It focuses on variable inclusion, required fields, numeric and binary coercion, date parsing, and row eligibility rules.",
        "key_inputs": [
            "Keep columns and required columns",
            "Force numeric, binary, or date parsing",
            "Duplicate-row removal and missing-value drop rules",
        ],
        "manual_checks": [
            "Confirm every required field survives after type coercion.",
            "Recount dropped rows against the raw file before moving to modeling.",
            "Verify binary and date columns against the original labels in the preview table.",
        ],
        "methods": [
            {
                "slug": "column_selection",
                "name": "Column Selection",
                "description": "Restrict the working sample to the columns needed for the research design.",
            },
            {
                "slug": "required_fields",
                "name": "Required Field Filter",
                "description": "Drop observations that do not contain the minimum fields required for identification.",
            },
            {
                "slug": "type_coercion",
                "name": "Type Coercion",
                "description": "Force variables into numeric, binary, or date types before downstream transformations.",
            },
            {
                "slug": "duplicate_and_missing_rules",
                "name": "Duplicate and Missing Rules",
                "description": "Apply explicit duplicate-row removal and missing-value policies before saving the prepared sample.",
            },
        ],
        "default_workbench_query": {
            "workflow": "data_processing",
            "processing_family": "sample_preparation",
        },
    },
    {
        "slug": "cleaning_transforms",
        "title": "Cleaning & Transforms",
        "category": "data_processing",
        "category_label": "Data Processing",
        "summary": "Normalize variables, cap extremes, and generate transformed regressors with explicit thresholds.",
        "description": "Use this family when the raw sample already exists but its scale, outliers, or missingness would distort inference. The point is to make every cleaning step explicit and reproducible.",
        "key_inputs": [
            "Imputation method and target columns",
            "Winsorization bounds and columns",
            "Log transform, standardization, min-max scaling, and outlier thresholds",
        ],
        "manual_checks": [
            "Recompute each transformed column from the downloaded prepared sample.",
            "Check that winsorized variables do not exceed the declared quantile bounds.",
            "Compare the transformed preview rows against a manual spreadsheet calculation.",
        ],
        "methods": [
            {
                "slug": "imputation",
                "name": "Imputation",
                "description": "Fill missing values with mean, median, zero, forward-fill, or backward-fill rules.",
            },
            {
                "slug": "winsorization",
                "name": "Winsorization",
                "description": "Clip tail observations using transparent lower and upper quantile thresholds.",
            },
            {
                "slug": "transformations",
                "name": "Log, Standardize, Min-Max",
                "description": "Generate comparable scales for regression and charting workflows.",
            },
            {
                "slug": "outlier_filters",
                "name": "Outlier Filters",
                "description": "Remove extreme values using IQR or z-score rules with explicit cutoffs.",
            },
        ],
        "default_workbench_query": {
            "workflow": "data_processing",
            "processing_family": "cleaning_transforms",
        },
    },
    {
        "slug": "time_series_features",
        "title": "Time-Series Features",
        "category": "data_processing",
        "category_label": "Data Processing",
        "summary": "Generate differences, returns, lags, leads, and rolling diagnostics before time-series or finance models.",
        "description": "Use this family when the identification or forecasting logic depends on ordered observations. It exposes the exact sort variable, grouping variable, and transformation windows used to construct derived series.",
        "key_inputs": [
            "Sort column and optional panel/time grouping column",
            "Difference, return, lag, and lead targets",
            "Rolling mean and rolling volatility windows",
        ],
        "manual_checks": [
            "Verify the sort order before recomputing returns or lags.",
            "Rebuild at least one derived series by hand to confirm the grouping logic.",
            "Check that rolling windows use the documented horizon and missing-value behavior.",
        ],
        "methods": [
            {
                "slug": "differences",
                "name": "Differences",
                "description": "Create first differences or grouped differences for trend-stationary analysis.",
            },
            {
                "slug": "returns",
                "name": "Simple and Log Returns",
                "description": "Construct finance-style return series from prices or levels using transparent formulas.",
            },
            {
                "slug": "lags_and_leads",
                "name": "Lags and Leads",
                "description": "Create dynamic explanatory variables for event studies, ARIMA, VAR, and panel models.",
            },
            {
                "slug": "rolling_statistics",
                "name": "Rolling Statistics",
                "description": "Compute rolling means and volatility windows for macro-finance diagnostics.",
            },
        ],
        "default_workbench_query": {
            "workflow": "data_processing",
            "processing_family": "time_series_features",
        },
    },
    {
        "slug": "visualization",
        "title": "Visualization",
        "category": "data_processing",
        "category_label": "Data Processing",
        "summary": "Render line, scatter, bar, and histogram charts and export them as PNG assets.",
        "description": "Use this family when the immediate goal is to inspect the shape of the data, validate a transformation, or produce a transparent figure that can be downloaded and checked independently.",
        "key_inputs": [
            "Chart type, x-variable, and y-variable selection",
            "Optional group/color dimension",
            "Exportable PNG output with direct download",
        ],
        "manual_checks": [
            "Confirm plotted columns match the selected variables in the chart form.",
            "Compare chart points against the downloaded source sample or prepared sample.",
            "Download the PNG and verify its title, axes, and grouping choices before reuse.",
        ],
        "methods": [
            {
                "slug": "line_chart",
                "name": "Line Chart",
                "description": "Inspect trajectories, trends, and series comovement over ordered observations.",
            },
            {
                "slug": "scatter_chart",
                "name": "Scatter Chart",
                "description": "Check bivariate relationships, clustering, and possible nonlinear patterns.",
            },
            {
                "slug": "bar_chart",
                "name": "Bar Chart",
                "description": "Compare grouped levels, shares, or event counts across categories.",
            },
            {
                "slug": "histogram",
                "name": "Histogram",
                "description": "Inspect empirical distributions before choosing transformations or tail-risk models.",
            },
        ],
        "default_workbench_query": {
            "workflow": "data_processing",
            "processing_family": "visualization",
        },
    },
]


MODEL_FAMILY_CATALOG: list[dict[str, object]] = [
    {
        "slug": "econometrics_baseline",
        "title": "Econometrics Baseline",
        "category": "model",
        "category_label": "Model",
        "summary": "Classical empirical economics workflows for treatment effects, structural breaks, and panel-style identification.",
        "description": "This family groups the baseline empirical designs most users need first: linear regression, binary response models, treatment-effect estimators, fixed effects, gravity, and IV designs.",
        "key_inputs": [
            "Outcome variable and explanatory variables",
            "Treatment, post, running, entity, time, endogenous, and instrument fields when applicable",
            "Robust covariance toggle and transparent coefficient output",
        ],
        "manual_checks": [
            "Rebuild the design matrix from the prepared sample and compare term order with the coefficient table.",
            "Check treatment, post, running, or instrument fields directly in the downloaded sample.",
            "Re-estimate at least one specification externally using the same covariance setting.",
        ],
        "methods": [
            {"slug": "ols", "name": "OLS", "description": "Baseline linear model for average partial effects."},
            {"slug": "ppml", "name": "PPML", "description": "Poisson pseudo-maximum likelihood for nonnegative outcomes and flow data."},
            {"slug": "logit", "name": "Logit", "description": "Binary response model with logistic link."},
            {"slug": "probit", "name": "Probit", "description": "Binary response model with normal link."},
            {"slug": "did", "name": "Difference-in-Differences", "description": "Two-group/two-period style treatment-effect estimation."},
            {"slug": "event_study", "name": "Event Study", "description": "Dynamic treatment effects around an event window."},
            {"slug": "rdd", "name": "Regression Discontinuity", "description": "Local identification around an observed cutoff."},
            {"slug": "fixed_effects", "name": "Fixed Effects", "description": "Entity and optional time fixed-effects estimation."},
            {"slug": "gravity", "name": "Gravity Model", "description": "Trade- and flow-style models using mass and distance terms."},
            {"slug": "iv_2sls", "name": "IV-2SLS", "description": "Instrumental-variables regression for endogeneity correction."},
            {"slug": "panel_iv", "name": "Panel IV", "description": "Panel-style IV with entity and time structure."},
        ],
        "default_workbench_query": {
            "workflow": "model",
            "model_family": "econometrics_baseline",
            "model_type": "ols",
        },
    },
    {
        "slug": "time_series_finance",
        "title": "Time Series & Econometric Finance",
        "category": "model",
        "category_label": "Model",
        "summary": "Forecasting, volatility, impulse-response, and connectedness models for ordered macro-finance data.",
        "description": "Use this family when time ordering is central to the question. These models cover univariate forecasting, volatility clustering, multivariate dynamic interactions, recursive structural impulse responses, and spillover-connectedness diagnostics.",
        "key_inputs": [
            "Time column",
            "Series variable or multivariate series selection",
            "Lag order, ARIMA / ARCH / GARCH order, horizon, and optional recursive shock ordering",
        ],
        "manual_checks": [
            "Confirm the time column sorts correctly before estimation.",
            "Recompute lagged design terms or volatility recursions in the downloaded sample.",
            "Verify forecast horizons, lag order, and recursive ordering assumptions against the model specification panel.",
        ],
        "methods": [
            {"slug": "arima", "name": "ARIMA Forecast", "description": "Univariate forecasting with explicit ARIMA(p,d,q) inputs."},
            {"slug": "arch", "name": "ARCH", "description": "Conditional heteroskedasticity model for volatility clustering in return series."},
            {"slug": "garch", "name": "GARCH", "description": "Generalized ARCH model for persistent conditional variance dynamics."},
            {"slug": "var", "name": "Vector Autoregression", "description": "Multivariate dynamic system for macro-finance spillovers."},
            {"slug": "svar_irf", "name": "SVAR IRF", "description": "Recursive-identified structural impulse responses and cumulative response paths."},
            {"slug": "virf", "name": "VIRF", "description": "Volatility impulse response path implied by a fitted GARCH(1,1) process."},
            {"slug": "dy_connectedness", "name": "DY Connectedness", "description": "Diebold-Yilmaz spillover table and total connectedness index from generalized FEVD."},
            {"slug": "bk_connectedness", "name": "BK Connectedness", "description": "Barunik-Krehlik frequency connectedness decomposition across short, medium, and long horizons."},
        ],
        "default_workbench_query": {
            "workflow": "model",
            "model_family": "time_series_finance",
            "model_type": "arima",
        },
    },
    {
        "slug": "corporate_finance",
        "title": "Corporate Finance",
        "category": "model",
        "category_label": "Model",
        "summary": "Transparent ratio-based diagnostics for firm health and profitability structure.",
        "description": "Use this family when the main need is interpretability rather than structural estimation. It exposes each financial ratio and lets users cross-check the accounting arithmetic directly.",
        "key_inputs": [
            "Working capital, retained earnings, EBIT, market equity, assets, liabilities, sales",
            "Net income, revenue, and equity for DuPont decomposition",
        ],
        "manual_checks": [
            "Recompute every ratio from the raw firm-level columns.",
            "Check sign conventions and units before interpreting score thresholds.",
            "Compare the displayed metrics against a manual spreadsheet calculation.",
        ],
        "methods": [
            {"slug": "altman_z", "name": "Altman Z-Score", "description": "Firm distress screening using the classic Z-Score ratio combination."},
            {"slug": "dupont", "name": "DuPont Analysis", "description": "Profit margin, asset turnover, and leverage decomposition of ROE."},
        ],
        "default_workbench_query": {
            "workflow": "model",
            "model_family": "corporate_finance",
            "model_type": "altman_z",
        },
    },
    {
        "slug": "risk_management",
        "title": "Risk Management",
        "category": "model",
        "category_label": "Model",
        "summary": "Loss and volatility diagnostics for market risk workflows.",
        "description": "Use this family when the focus is downside risk, volatility persistence, or stress-style tail diagnostics rather than causal inference.",
        "key_inputs": [
            "Return or loss series",
            "Confidence level and holding period",
            "EWMA decay parameter for volatility tracking",
        ],
        "manual_checks": [
            "Recompute the empirical tail cutoff from the downloaded sample.",
            "Check confidence level and holding-period scaling before comparing VaR numbers.",
            "Verify EWMA recursion against a hand-built spreadsheet for at least several rows.",
        ],
        "methods": [
            {"slug": "historical_var", "name": "Historical VaR / ES", "description": "Nonparametric tail-risk calculation from the empirical distribution."},
            {"slug": "parametric_var", "name": "Parametric VaR / ES", "description": "Normal-style VaR and expected shortfall from estimated mean and volatility."},
            {"slug": "ewma_volatility", "name": "EWMA Volatility", "description": "Exponentially weighted volatility dynamics for recent-history emphasis."},
        ],
        "default_workbench_query": {
            "workflow": "model",
            "model_family": "risk_management",
            "model_type": "historical_var",
        },
    },
    {
        "slug": "derivatives_pricing",
        "title": "Derivatives Pricing",
        "category": "model",
        "category_label": "Model",
        "summary": "Vanilla option-pricing workflows with transparent parameter exposure.",
        "description": "Use this family for direct pricing of standard European-style calls and puts. The page shows all pricing inputs so the result can be checked against a calculator or spreadsheet.",
        "key_inputs": [
            "Spot, strike, time to maturity, rate, and volatility inputs",
            "Option type and binomial step count",
        ],
        "manual_checks": [
            "Verify the units of maturity and volatility before comparing prices.",
            "Check the sign and scale of the risk-free rate.",
            "Reproduce the price with an independent Black-Scholes or binomial calculator.",
        ],
        "methods": [
            {"slug": "black_scholes", "name": "Black-Scholes", "description": "Closed-form pricing for European vanilla options."},
            {"slug": "binomial_option", "name": "Binomial Option Pricing", "description": "Discrete-time lattice pricing with user-specified step count."},
        ],
        "default_workbench_query": {
            "workflow": "model",
            "model_family": "derivatives_pricing",
            "model_type": "black_scholes",
        },
    },
    {
        "slug": "macro_finance_dsge",
        "title": "Macro Finance & DSGE",
        "category": "model",
        "category_label": "Model",
        "summary": "Policy-rule diagnostics and a lightweight dynamic general-equilibrium sandbox.",
        "description": "Use this family when the question is macro-policy oriented. It exposes simple policy-rule and toy equilibrium parameters transparently rather than hiding them behind a black-box calibration.",
        "key_inputs": [
            "Inflation gap and output gap variables for Taylor-rule estimation",
            "RBC/DSGE preference, technology, depreciation, and shock parameters",
        ],
        "manual_checks": [
            "Confirm gap variables are already constructed consistently with the research design.",
            "Recompute the Taylor-rule regression externally with the same specification.",
            "For the toy DSGE module, verify calibration inputs and impulse horizon manually.",
        ],
        "methods": [
            {"slug": "taylor_rule", "name": "Taylor Rule", "description": "Transparent reduced-form policy-rule regression."},
            {"slug": "rbc_dsge", "name": "Toy RBC / DSGE", "description": "A simple calibration-style dynamic general-equilibrium sandbox."},
        ],
        "default_workbench_query": {
            "workflow": "model",
            "model_family": "macro_finance_dsge",
            "model_type": "taylor_rule",
        },
    },
    {
        "slug": "portfolio_allocation",
        "title": "Portfolio Allocation",
        "category": "model",
        "category_label": "Model",
        "summary": "Weight-construction workflows for mean-variance, minimum-variance, and risk-parity portfolios.",
        "description": "Use this family when the output of interest is portfolio weights rather than a coefficient table. The emphasis is on explicit return inputs, risk preferences, and weight vectors that can be checked manually.",
        "key_inputs": [
            "Return series for each asset",
            "Risk-aversion and long-only choice",
        ],
        "manual_checks": [
            "Rebuild the sample covariance matrix from the prepared sample.",
            "Verify the optimizer constraints, especially long-only assumptions.",
            "Check that final weights sum to one and match the reported allocation table.",
        ],
        "methods": [
            {"slug": "mean_variance", "name": "Mean-Variance Portfolio", "description": "Classic risk-return frontier allocation using expected returns and covariances."},
            {"slug": "minimum_variance", "name": "Minimum Variance Portfolio", "description": "Variance-minimizing allocation under the chosen constraint set."},
            {"slug": "risk_parity", "name": "Risk Parity Portfolio", "description": "Allocation that balances risk contribution across assets."},
        ],
        "default_workbench_query": {
            "workflow": "model",
            "model_family": "portfolio_allocation",
            "model_type": "mean_variance",
        },
    },
    {
        "slug": "asset_pricing",
        "title": "Asset Pricing",
        "category": "model",
        "category_label": "Model",
        "summary": "Factor-based return regressions with exposed excess-return construction.",
        "description": "Use this family when the focus is factor exposure and expected-return decomposition. The page keeps factor construction explicit so users can verify each excess-return series before estimation.",
        "key_inputs": [
            "Asset return series, market factor, and risk-free rate",
            "SMB and HML factors for the Fama-French specification",
        ],
        "manual_checks": [
            "Rebuild asset excess returns and market excess returns from the downloaded sample.",
            "Check factor alignment and frequency before comparing alphas and betas.",
            "Re-estimate the regression externally and compare coefficients term by term.",
        ],
        "methods": [
            {"slug": "capm", "name": "CAPM", "description": "Single-factor pricing regression with market excess returns."},
            {"slug": "fama_french_3", "name": "Fama-French 3-Factor", "description": "Multi-factor pricing regression with SMB and HML exposures."},
        ],
        "default_workbench_query": {
            "workflow": "model",
            "model_family": "asset_pricing",
            "model_type": "capm",
        },
    },
]


def _prefilled_data_lab_link(query: dict[str, str]) -> str:
    return "/data-lab?" + urlencode(query) + "#data-lab-workbench"


def _family_detail_path(kind: str, slug: str) -> str:
    return f"/data-lab/{kind}/{slug}"


def _model_method_detail_path(family_slug: str, method_slug: str) -> str:
    return f"/data-lab/models/{family_slug}/{method_slug}"


def _model_teaching_path(family_slug: str, method_slug: str) -> str:
    return f"/data-lab/learn/models/{family_slug}/{method_slug}"


def _decorate_family(item: dict[str, object], *, kind: str) -> dict[str, object]:
    detail = deepcopy(item)
    slug = str(detail["slug"])
    default_query = deepcopy(detail.get("default_workbench_query") or {})
    detail["detail_path"] = _family_detail_path("processing" if kind == "processing" else "models", slug)
    detail["workbench_path"] = _prefilled_data_lab_link(default_query)
    methods = []
    for method in detail.get("methods") or []:
        method_copy = deepcopy(method)
        method_slug = str(method_copy.get("slug") or "")
        if kind == "models":
            method_copy["detail_path"] = _model_method_detail_path(slug, method_slug)
            method_copy["teaching_path"] = _model_teaching_path(slug, method_slug)
            method_copy["workbench_path"] = _prefilled_data_lab_link(
                {
                    "workflow": "model",
                    "model_family": slug,
                    "model_type": method_slug,
                }
            )
        methods.append(method_copy)
    detail["methods"] = methods
    return detail


def list_processing_families() -> list[dict[str, object]]:
    return [_decorate_family(item, kind="processing") for item in PROCESSING_FAMILY_CATALOG]


def list_model_families() -> list[dict[str, object]]:
    return [_decorate_family(item, kind="models") for item in MODEL_FAMILY_CATALOG]


def get_processing_family(slug: str) -> dict[str, object] | None:
    for item in PROCESSING_FAMILY_CATALOG:
        if item["slug"] == slug:
            return _decorate_family(item, kind="processing")
    return None


def get_model_family(slug: str) -> dict[str, object] | None:
    for item in MODEL_FAMILY_CATALOG:
        if item["slug"] == slug:
            return _decorate_family(item, kind="models")
    return None


def get_data_lab_catalog() -> dict[str, object]:
    return {
        "processing_families": list_processing_families(),
        "model_families": list_model_families(),
    }


MODEL_METHOD_GUIDES: dict[str, dict[str, object]] = {
    "ols": {
        "overview": "Estimate the conditional mean effect of regressors on a continuous outcome with a transparent coefficient table.",
        "equation": "y_i = alpha + X_i beta + epsilon_i",
        "outputs": ["Coefficient table", "Model fit metrics", "Residual scale and audit trail"],
        "normal_result": "A normal paper-style output shows coefficients, standard errors, significance marks, N, and R-squared.",
    },
    "ppml": {
        "overview": "Estimate multiplicative effects for nonnegative outcomes or flow data while keeping zeros in the sample.",
        "equation": "E[y_i | X_i] = exp(alpha + X_i beta)",
        "outputs": ["Coefficient table", "Pseudo log-likelihood diagnostics", "Audit trail"],
        "normal_result": "A normal output reports coefficients, robust standard errors, convergence status, and row counts.",
    },
    "logit": {
        "overview": "Model a binary outcome through the logistic link and inspect the direction and significance of each regressor.",
        "equation": "Pr(y_i = 1 | X_i) = 1 / (1 + exp(-(alpha + X_i beta)))",
        "outputs": ["Coefficient table", "Classification fit metrics", "Audit trail"],
        "normal_result": "A normal output shows coefficients, standard errors, p-values, and the number of positive cases.",
    },
    "probit": {
        "overview": "Model a binary outcome through the standard-normal link when the research design prefers probit interpretation.",
        "equation": "Pr(y_i = 1 | X_i) = Phi(alpha + X_i beta)",
        "outputs": ["Coefficient table", "Model fit metrics", "Audit trail"],
        "normal_result": "A normal output shows coefficients, standard errors, p-values, and convergence diagnostics.",
    },
    "did": {
        "overview": "Estimate the average treatment effect from treatment and post indicators with an explicit DID interaction term.",
        "equation": "y_it = alpha + beta1 treated_i + beta2 post_t + beta3 treated_i*post_t + controls + epsilon_it",
        "outputs": ["Coefficient table with DID interaction", "2x2 cell means", "Manual audit trail"],
        "normal_result": "A normal output includes the DID interaction row and a 2x2 means table for treated/control before/after.",
    },
    "event_study": {
        "overview": "Estimate dynamic treatment effects across leads and lags around an event date.",
        "equation": "y_it = alpha_i + gamma_t + sum_k beta_k event_time_k + controls + epsilon_it",
        "outputs": ["Lead/lag coefficient table", "Event-study figure", "Audit trail"],
        "normal_result": "A normal output includes relative-time coefficients and a lead-lag figure centered on the omitted period.",
    },
    "rdd": {
        "overview": "Estimate a local discontinuity around a known cutoff using a running variable and explicit bandwidth choice.",
        "equation": "y_i = alpha + tau D_i + f(running_i - cutoff) + controls + epsilon_i",
        "outputs": ["Coefficient table", "RDD diagnostic figure", "Bandwidth and cutoff metadata"],
        "normal_result": "A normal output shows the treatment jump, bandwidth, polynomial order, and a cutoff figure.",
    },
    "fixed_effects": {
        "overview": "Control for unit-specific heterogeneity through entity and optional time fixed effects.",
        "equation": "y_it = alpha_i + gamma_t + X_it beta + epsilon_it",
        "outputs": ["Coefficient table", "Panel fit metrics", "Audit trail"],
        "normal_result": "A normal output reports coefficients on time-varying regressors and states which fixed effects were included.",
    },
    "gravity": {
        "overview": "Estimate trade- or flow-style relations using origin mass, destination mass, and distance terms.",
        "equation": "log(flow_ij) = alpha + beta1 log(origin_i) + beta2 log(destination_j) - beta3 log(distance_ij) + epsilon_ij",
        "outputs": ["Coefficient table", "Gravity term diagnostics", "Audit trail"],
        "normal_result": "A normal output shows mass terms with positive signs, a distance term with a negative sign, and sample counts.",
    },
    "iv_2sls": {
        "overview": "Estimate causal effects when one regressor is endogenous and instruments are available.",
        "equation": "Stage 1: x_endog = Z pi + W delta + u; Stage 2: y = alpha + x_hat beta + W gamma + epsilon",
        "outputs": ["Second-stage coefficient table", "First-stage diagnostics", "Audit trail"],
        "normal_result": "A normal output shows both stages or at least first-stage strength and second-stage coefficients.",
    },
    "panel_iv": {
        "overview": "Combine panel structure with instrumental variables when endogeneity appears in repeated observations.",
        "equation": "y_it = alpha_i + gamma_t + x_hat_it beta + W_it delta + epsilon_it",
        "outputs": ["Panel IV coefficient table", "Instrument diagnostics", "Audit trail"],
        "normal_result": "A normal output states the panel dimensions, fixed-effect choices, and IV diagnostics.",
    },
    "arima": {
        "overview": "Fit a univariate forecasting model with explicit ARIMA order and horizon choices.",
        "equation": "phi(L)(1-L)^d y_t = theta(L) epsilon_t",
        "outputs": ["Forecast table", "Observed vs forecast figure", "Order metadata"],
        "normal_result": "A normal output shows fitted order, out-of-sample forecast values, and a forecast-path figure.",
    },
    "arch": {
        "overview": "Model volatility clustering with an ARCH process using lagged squared shocks.",
        "equation": "sigma_t^2 = omega + sum_i alpha_i epsilon_{t-i}^2",
        "outputs": ["Variance parameter table", "In-sample volatility figure", "Forecast volatility figure"],
        "normal_result": "A normal output shows positive variance parameters and both in-sample and forecast volatility plots.",
    },
    "garch": {
        "overview": "Model persistent conditional variance through ARCH and lagged variance terms.",
        "equation": "sigma_t^2 = omega + sum_i alpha_i epsilon_{t-i}^2 + sum_j beta_j sigma_{t-j}^2",
        "outputs": ["Variance parameter table", "In-sample volatility figure", "Forecast volatility figure"],
        "normal_result": "A normal output shows positive alpha/beta terms and volatility figures for fitted and forecast periods.",
    },
    "var": {
        "overview": "Estimate a multivariate dynamic system to trace interactions across several ordered series.",
        "equation": "Y_t = c + A_1 Y_{t-1} + ... + A_p Y_{t-p} + u_t",
        "outputs": ["Coefficient blocks", "Forecast table", "Forecast path figure"],
        "normal_result": "A normal output reports lag order, coefficient blocks, and a multivariate forecast figure.",
    },
    "svar_irf": {
        "overview": "Estimate recursively identified structural impulse responses from a fitted VAR system.",
        "equation": "A_0 Y_t = c + A_1 Y_{t-1} + ... + A_p Y_{t-p} + e_t",
        "outputs": ["IRF table", "Orthogonalized IRF figure", "Cumulative IRF figure"],
        "normal_result": "A normal output includes an IRF table and at least one impulse-response figure across the chosen horizon.",
    },
    "virf": {
        "overview": "Track how a volatility shock propagates through a fitted GARCH-style variance process.",
        "equation": "VIRF_h = E[sigma^2_{t+h} | shock] - E[sigma^2_{t+h}]",
        "outputs": ["Volatility response table", "Volatility response figure", "Variance response figure"],
        "normal_result": "A normal output includes a volatility-response path and a companion variance-response figure.",
    },
    "dy_connectedness": {
        "overview": "Measure directional spillovers across a system using generalized FEVD-based connectedness.",
        "equation": "Connectedness = function(FEVD_h across all variables)",
        "outputs": ["Connectedness matrix", "Heatmap figure", "Net directional spillover figure"],
        "normal_result": "A normal output includes a connectedness table, a heatmap, and a net-spillover summary graphic.",
    },
    "bk_connectedness": {
        "overview": "Decompose connectedness into short-, medium-, and long-horizon frequency bands.",
        "equation": "Frequency connectedness = spectral decomposition of generalized FEVD",
        "outputs": ["Band total connectedness table", "Band heatmap figure", "Band summary figure"],
        "normal_result": "A normal output includes frequency-band summaries and figures for each horizon bucket.",
    },
    "historical_var": {
        "overview": "Compute tail risk directly from the empirical distribution of returns or losses.",
        "equation": "VaR_alpha = empirical quantile_alpha(losses); ES_alpha = mean(losses beyond VaR)",
        "outputs": ["VaR and ES table", "Tail sample diagnostics", "Audit trail"],
        "normal_result": "A normal output shows VaR, ES, confidence level, and holding period information.",
    },
    "parametric_var": {
        "overview": "Compute VaR and ES under a parametric distribution, typically normal, using mean and volatility estimates.",
        "equation": "VaR_alpha = mu + sigma z_alpha",
        "outputs": ["VaR and ES table", "Distribution parameters", "Audit trail"],
        "normal_result": "A normal output reports mean, volatility, VaR, ES, and the confidence level used.",
    },
    "ewma_volatility": {
        "overview": "Track recent volatility with exponentially decaying weights.",
        "equation": "sigma_t^2 = lambda sigma_{t-1}^2 + (1-lambda) r_{t-1}^2",
        "outputs": ["EWMA volatility table", "Latest volatility metric", "Audit trail"],
        "normal_result": "A normal output reports lambda, recent conditional volatility, and the effective sample size logic.",
    },
    "altman_z": {
        "overview": "Compute a transparent distress score from classic accounting ratios.",
        "equation": "Z = 1.2 X1 + 1.4 X2 + 3.3 X3 + 0.6 X4 + 1.0 X5",
        "outputs": ["Ratio breakdown", "Z-score table", "Audit trail"],
        "normal_result": "A normal output lists each ratio component and the final Z-score by firm or observation.",
    },
    "dupont": {
        "overview": "Decompose return on equity into profitability, turnover, and leverage components.",
        "equation": "ROE = Net Profit Margin * Asset Turnover * Equity Multiplier",
        "outputs": ["DuPont component table", "ROE breakdown", "Audit trail"],
        "normal_result": "A normal output reports margin, turnover, multiplier, and reconstructed ROE.",
    },
    "black_scholes": {
        "overview": "Price a vanilla European option from spot, strike, maturity, rate, and volatility inputs.",
        "equation": "C = S N(d1) - K e^{-rT} N(d2)",
        "outputs": ["Option valuation table", "Pricing inputs", "Audit trail"],
        "normal_result": "A normal output lists the pricing inputs and the resulting call or put value.",
    },
    "binomial_option": {
        "overview": "Price a vanilla option from a discrete-time lattice with an explicit step count.",
        "equation": "Option price = backward induction on a recombining binomial tree",
        "outputs": ["Option valuation table", "Tree parameter metadata", "Audit trail"],
        "normal_result": "A normal output reports step count, up/down factors or equivalents, and the final price.",
    },
    "taylor_rule": {
        "overview": "Estimate a reduced-form policy rule relating the policy rate to inflation and output gaps.",
        "equation": "i_t = alpha + beta_pi inflation_gap_t + beta_y output_gap_t + epsilon_t",
        "outputs": ["Coefficient table", "Policy-rule fit metrics", "Audit trail"],
        "normal_result": "A normal output includes inflation-gap and output-gap coefficients with standard errors.",
    },
    "rbc_dsge": {
        "overview": "Run a lightweight calibrated dynamic macro model to inspect impulse-style trajectories.",
        "equation": "Toy RBC / DSGE calibration with alpha, beta, delta, shock persistence, and horizon",
        "outputs": ["Calibration table", "Impulse-style paths", "Audit trail"],
        "normal_result": "A normal output reports calibration inputs and impulse-style responses for key variables.",
    },
    "mean_variance": {
        "overview": "Construct portfolio weights from expected returns and the covariance matrix.",
        "equation": "w* = argmax_w (mu'w - gamma/2 * w'Sigma w)",
        "outputs": ["Weight table", "Portfolio mean/variance metrics", "Audit trail"],
        "normal_result": "A normal output reports final weights, expected return, and risk metrics, with weights summing to one.",
    },
    "minimum_variance": {
        "overview": "Construct the variance-minimizing portfolio under the chosen constraints.",
        "equation": "w* = argmin_w w'Sigma w",
        "outputs": ["Weight table", "Portfolio variance metrics", "Audit trail"],
        "normal_result": "A normal output reports minimum-variance weights and the achieved portfolio variance.",
    },
    "risk_parity": {
        "overview": "Construct weights so each asset contributes roughly equal marginal risk.",
        "equation": "Choose w so risk contributions are approximately equal across assets",
        "outputs": ["Weight table", "Risk contribution table", "Audit trail"],
        "normal_result": "A normal output reports final weights and a risk-contribution breakdown across assets.",
    },
    "capm": {
        "overview": "Estimate a single-factor return regression against market excess returns.",
        "equation": "r_i - r_f = alpha + beta (r_m - r_f) + epsilon",
        "outputs": ["Alpha and beta table", "Fit metrics", "Audit trail"],
        "normal_result": "A normal output shows alpha, market beta, standard errors, and the excess-return construction.",
    },
    "fama_french_3": {
        "overview": "Estimate a three-factor return regression using market, SMB, and HML factors.",
        "equation": "r_i - r_f = alpha + beta_m MKT + beta_s SMB + beta_h HML + epsilon",
        "outputs": ["Factor loading table", "Fit metrics", "Audit trail"],
        "normal_result": "A normal output reports alpha and three factor loadings with standard errors and sample counts.",
    },
}


def _paper_table_expectations(method_slug: str, method_name: str) -> list[str]:
    table_map: dict[str, list[str]] = {
        "ols": ["Main regression table with coefficients, standard errors, significance stars, N, and R-squared."],
        "ppml": ["PPML coefficient table with robust standard errors, convergence flag, and row count."],
        "logit": ["Binary-response table with coefficients, standard errors, and the positive-case share."],
        "probit": ["Binary-response table with coefficients, standard errors, and convergence diagnostics."],
        "did": ["DID regression table with the treated x post interaction highlighted.", "2x2 cell-means table for treated/control before/after."],
        "event_study": ["Lead-lag coefficient table indexed by event time.", "Reference period note showing the omitted relative-time bin."],
        "rdd": ["RDD estimate table with cutoff, bandwidth, polynomial order, and local sample size."],
        "fixed_effects": ["Coefficient table on time-varying regressors plus a note on entity/time fixed effects."],
        "gravity": ["Gravity regression table with origin mass, destination mass, and distance coefficients."],
        "iv_2sls": ["Second-stage coefficient table.", "First-stage or weak-instrument diagnostics table."],
        "panel_iv": ["Panel-IV coefficient table.", "Instrument-strength and fixed-effects diagnostics table."],
        "arima": ["Forecast table with horizon, point forecast, and any confidence interval columns."],
        "arch": ["Variance-parameter table with ARCH terms and positivity checks."],
        "garch": ["Variance-parameter table with omega, alpha, and beta terms."],
        "var": ["Coefficient-block summary by equation and lag.", "Forecast table for each series across the chosen horizon."],
        "svar_irf": ["Impulse-response table by horizon, impulse, and response variable."],
        "virf": ["Volatility-response table by horizon."],
        "dy_connectedness": ["Connectedness matrix with from/to/NET spillover totals."],
        "bk_connectedness": ["Frequency-band connectedness table for short, medium, and long horizons."],
        "historical_var": ["Risk table with VaR, Expected Shortfall, confidence level, and holding period."],
        "parametric_var": ["Risk table with mean, volatility, VaR, and Expected Shortfall under the chosen distribution."],
        "ewma_volatility": ["Latest EWMA volatility summary with lambda and recent conditional variance."],
        "altman_z": ["Component ratio table plus final Z-score by firm or observation."],
        "dupont": ["Margin, turnover, and leverage breakdown table reconstructing ROE."],
        "black_scholes": ["Input-and-price table listing spot, strike, maturity, rate, volatility, and option value."],
        "binomial_option": ["Tree-parameter table with step count and final option price."],
        "taylor_rule": ["Policy-rule regression table with inflation-gap and output-gap coefficients."],
        "rbc_dsge": ["Calibration table with alpha, beta, delta, persistence, and shock size."],
        "mean_variance": ["Portfolio weight table plus expected return and variance metrics."],
        "minimum_variance": ["Portfolio weight table plus achieved minimum-variance metric."],
        "risk_parity": ["Portfolio weight table plus risk-contribution breakdown."],
        "capm": ["Factor table with alpha, market beta, standard errors, and fit statistics."],
        "fama_french_3": ["Factor-loading table with alpha, market, SMB, and HML coefficients."],
    }
    return table_map.get(
        method_slug,
        [f"Main empirical table for {method_name}, including coefficients or calibrated metrics and the final sample count."],
    )


def _paper_figure_expectations(method_slug: str) -> list[str]:
    figure_map: dict[str, list[str]] = {
        "did": ["Optional coefficient/event-timing graphic if the paper supplements the main DID table with dynamics."],
        "event_study": ["Lead-lag coefficient plot centered on the omitted period with confidence intervals."],
        "rdd": ["Cutoff figure with local fit or binned scatter on both sides of the threshold."],
        "arima": ["Observed-versus-forecast path for the target series."],
        "arch": ["In-sample conditional-volatility figure.", "Forecast volatility path over the selected horizon."],
        "garch": ["In-sample conditional-volatility figure.", "Forecast volatility path over the selected horizon."],
        "var": ["Observed and forecast paths for the core endogenous series."],
        "svar_irf": ["Orthogonalized impulse-response figure by horizon.", "Cumulative impulse-response companion figure."],
        "virf": ["Volatility-response figure.", "Variance-response companion figure."],
        "dy_connectedness": ["Connectedness heatmap.", "Net directional spillover bar chart."],
        "bk_connectedness": ["Frequency-band heatmap.", "Frequency-band total connectedness summary figure."],
        "rbc_dsge": ["Impulse-style transition paths for capital, output, and consumption."],
    }
    return figure_map.get(method_slug, [])


def _paper_appendix_expectations(method_slug: str) -> list[str]:
    appendix_map: dict[str, list[str]] = {
        "did": ["Appendix should restate treatment coding, timing logic, and any robustness variants on the sample."],
        "event_study": ["Appendix should record lead/lag window choice, omitted period, and fixed-effects specification."],
        "rdd": ["Appendix should show bandwidth choice, polynomial order, and any alternate local windows."],
        "iv_2sls": ["Appendix should restate the instrument list, first-stage strength, and exclusion restriction discussion."],
        "panel_iv": ["Appendix should report panel dimensions, fixed-effects choice, and instrument diagnostics."],
        "gravity": ["Appendix should state how zeros, logs, and distance scaling were handled."],
        "arch": ["Appendix should restate variance-order choice and the return construction used."],
        "garch": ["Appendix should restate variance-order choice and the return construction used."],
        "svar_irf": ["Appendix should state recursive ordering, horizon length, and any identifying restrictions."],
        "virf": ["Appendix should state the fitted volatility process and shock size used for the response path."],
        "dy_connectedness": ["Appendix should document VAR lag order, FEVD horizon, and series ordering."],
        "bk_connectedness": ["Appendix should document frequency-band cutoffs and VAR lag order."],
    }
    return appendix_map.get(
        method_slug,
        ["Appendix should preserve the exact sample, variable construction, and diagnostics needed to reproduce the reported result."],
    )


def _paper_results_template(method_slug: str, method_name: str, guide: dict[str, object]) -> list[dict[str, object]]:
    figures = _paper_figure_expectations(method_slug)
    return [
        {
            "title": "Main Table In The Paper Body",
            "body": "This is the first table a reader should see if the method is part of the main empirical result.",
            "items": _paper_table_expectations(method_slug, method_name),
        },
        {
            "title": "Main Figure In The Paper Body",
            "body": "Only include a figure when the model is inherently dynamic, graphical, or identification depends on a visual diagnostic.",
            "items": figures
            or ["No dedicated figure is required for the main text if the core evidence is already transparent in the result table."],
        },
        {
            "title": "Reporting Notes Under The Result",
            "body": "These notes help a reader verify that the reported output is the same one generated in the workbench.",
            "items": [
                "State the exact sample definition and final observation count.",
                "State the covariance type, lag order, horizon, bandwidth, or calibration values used in the run.",
                guide.get("normal_result") or "Summarize what a normal result should look like before claiming interpretation.",
            ],
        },
        {
            "title": "Appendix And Replication Material",
            "body": "Keep enough detail for a referee or coauthor to reproduce the same result manually.",
            "items": _paper_appendix_expectations(method_slug),
        },
    ]


def _paper_table_preview(method_slug: str, method_name: str) -> list[dict[str, object]]:
    regression_table = {
        "title": "Main Regression Table Preview",
        "caption": "Illustrative journal-style layout. Replace the placeholders with the actual workbench output.",
        "columns": ["Term", "Coefficient", "Std. Error", "t / z", "p-value"],
        "rows": [
            ["Core regressor", "0.128**", "(0.051)", "2.51", "0.012"],
            ["Control variable", "-0.044", "(0.037)", "-1.18", "0.238"],
            ["Observations", "1,248", "", "", ""],
            ["R-squared / Pseudo R-squared", "0.312", "", "", ""],
        ],
    }
    dynamic_table = {
        "title": "Dynamic Response Table Preview",
        "caption": "Use a horizon-by-horizon table when the method produces forecasts, impulse responses, or volatility paths.",
        "columns": ["Horizon", "Impulse / Variable", "Response", "Estimate", "Confidence Band"],
        "rows": [
            ["0", "Policy shock", "Output", "0.000", "[0.000, 0.000]"],
            ["1", "Policy shock", "Output", "-0.182", "[-0.301, -0.063]"],
            ["2", "Policy shock", "Output", "-0.137", "[-0.246, -0.028]"],
        ],
    }
    metrics_table = {
        "title": "Metrics Table Preview",
        "caption": "Use a compact metric table when the method returns calibrated scores, risk metrics, or portfolio allocations.",
        "columns": ["Metric", "Value", "Interpretation", "Sample / Horizon"],
        "rows": [
            ["Main metric", "0.482", "Economically meaningful estimate", "Full sample"],
            ["Secondary metric", "0.119", "Diagnostic or supporting statistic", "Full sample"],
            ["Observations / assets", "240", "Rows used in the run", "Input data"],
        ],
    }
    preview_map: dict[str, list[dict[str, object]]] = {
        "did": [
            {
                "title": "DID Main Table Preview",
                "caption": "Highlight the treated × post interaction and keep treatment/post main effects visible.",
                "columns": ["Term", "Coefficient", "Std. Error", "p-value", "Interpretation"],
                "rows": [
                    ["Treated × Post", "0.153***", "(0.041)", "0.001", "Average treatment effect"],
                    ["Treated", "0.027", "(0.039)", "0.489", "Baseline treated-control gap"],
                    ["Post", "-0.018", "(0.022)", "0.408", "Common post-period shift"],
                ],
            },
            {
                "title": "2x2 Cell-Means Preview",
                "caption": "Include this compact table so a referee can visually verify the DID logic before looking at the regression output.",
                "columns": ["Group", "Pre", "Post", "Change"],
                "rows": [
                    ["Control", "1.024", "1.011", "-0.013"],
                    ["Treated", "1.030", "1.170", "0.140"],
                ],
            },
        ],
        "event_study": [
            {
                "title": "Lead-Lag Coefficient Preview",
                "caption": "A paper table should align with the plotted event-study path and identify the omitted reference period.",
                "columns": ["Event time", "Estimate", "Std. Error", "95% CI low", "95% CI high"],
                "rows": [
                    ["-2", "0.012", "(0.021)", "-0.029", "0.053"],
                    ["0", "0.087**", "(0.035)", "0.018", "0.156"],
                    ["+2", "0.103**", "(0.041)", "0.023", "0.183"],
                ],
            }
        ],
        "rdd": [
            {
                "title": "RDD Estimate Preview",
                "caption": "Show the local bandwidth, polynomial order, and the discontinuity estimate in the same table block.",
                "columns": ["Bandwidth", "Polynomial", "Estimate", "Std. Error", "p-value"],
                "rows": [
                    ["0.50", "1", "0.214**", "(0.094)", "0.024"],
                    ["1.00", "2", "0.187*", "(0.101)", "0.067"],
                ],
            }
        ],
        "gravity": [
            {
                "title": "Gravity Regression Preview",
                "caption": "Flow models are usually presented with log-mass and log-distance elasticities in one compact table.",
                "columns": ["Term", "Coefficient", "Std. Error", "p-value", "Elasticity meaning"],
                "rows": [
                    ["log(origin mass)", "0.541***", "(0.083)", "0.000", "Origin-scale elasticity"],
                    ["log(destination mass)", "0.463***", "(0.078)", "0.000", "Destination-scale elasticity"],
                    ["log(distance)", "-0.712***", "(0.066)", "0.000", "Trade-friction elasticity"],
                ],
            }
        ],
        "iv_2sls": [
            regression_table,
            {
                "title": "First-Stage Diagnostics Preview",
                "caption": "A paper should usually surface instrument relevance rather than hiding it in the appendix.",
                "columns": ["Statistic", "Value", "Threshold / Benchmark", "Comment"],
                "rows": [
                    ["First-stage F", "18.7", "> 10", "Instrument relevance looks acceptable"],
                    ["Number of instruments", "1", "", "Exactly identified design"],
                ],
            },
        ],
        "panel_iv": [
            regression_table,
            {
                "title": "Panel-IV Diagnostics Preview",
                "caption": "Keep instrument strength and the panel structure visible in the same reporting bundle.",
                "columns": ["Statistic", "Value", "Comment"],
                "rows": [
                    ["Entities", "42", "Panel cross-sectional units"],
                    ["Time periods", "36", "Balanced monthly panel"],
                    ["First-stage F", "14.2", "Instrument remains relevant with fixed effects"],
                ],
            },
        ],
        "arima": [dynamic_table],
        "var": [dynamic_table],
        "svar_irf": [dynamic_table],
        "virf": [dynamic_table],
        "arch": [dynamic_table],
        "garch": [dynamic_table],
        "dy_connectedness": [
            {
                "title": "Connectedness Matrix Preview",
                "caption": "A paper table should show directional spillovers and the net position of each series.",
                "columns": ["Series", "From others", "To others", "Net", "Own share"],
                "rows": [
                    ["Asset A", "34.2", "28.6", "-5.6", "65.8"],
                    ["Asset B", "41.1", "44.7", "3.6", "58.9"],
                    ["Asset C", "37.8", "39.8", "2.0", "62.2"],
                ],
            }
        ],
        "bk_connectedness": [
            {
                "title": "Frequency-Band Preview",
                "caption": "Report short-, medium-, and long-horizon connectedness in a compact band table.",
                "columns": ["Band", "Total connectedness", "Dominant sender", "Dominant receiver"],
                "rows": [
                    ["Short", "42.5", "Asset B", "Asset A"],
                    ["Medium", "31.4", "Asset C", "Asset B"],
                    ["Long", "18.9", "Asset A", "Asset C"],
                ],
            }
        ],
        "historical_var": [metrics_table],
        "parametric_var": [metrics_table],
        "ewma_volatility": [metrics_table],
        "altman_z": [metrics_table],
        "dupont": [metrics_table],
        "black_scholes": [metrics_table],
        "binomial_option": [metrics_table],
        "taylor_rule": [regression_table],
        "rbc_dsge": [metrics_table],
        "mean_variance": [metrics_table],
        "minimum_variance": [metrics_table],
        "risk_parity": [metrics_table],
        "capm": [regression_table],
        "fama_french_3": [regression_table],
    }
    return deepcopy(preview_map.get(method_slug, [regression_table if "coefficient" in method_name.lower() else metrics_table]))


def _teaching_sections(method_name: str, family: dict[str, object], guide: dict[str, object]) -> list[dict[str, object]]:
    return [
        {
            "title": "What this method is for",
            "body": guide.get("overview") or f"{method_name} belongs to {family['title']} and is documented as a transparent workflow.",
            "items": [],
        },
        {
            "title": "What data shape you need",
            "body": "Before running the workbench, make sure the uploaded dataset already has the variables named in the input list and has passed profile inspection.",
            "items": list(family.get("key_inputs") or []),
        },
        {
            "title": "What a normal result should look like",
            "body": guide.get("normal_result") or "The output should include a result table, explicit sample metadata, and any figures required by the method family.",
            "items": list(guide.get("outputs") or []),
        },
        {
            "title": "Manual verification checklist",
            "body": "Use the published audit trail, prepared sample download, and raw JSON to challenge the run manually.",
            "items": list(guide.get("manual_checks") or family.get("manual_checks") or []),
        },
    ]


def get_model_method(family_slug: str, method_slug: str) -> dict[str, object] | None:
    family = get_model_family(family_slug)
    if not family:
        return None
    method = next((item for item in family.get("methods") or [] if item.get("slug") == method_slug), None)
    if not method:
        return None
    guide = MODEL_METHOD_GUIDES.get(method_slug, {})
    return {
        "family_slug": family_slug,
        "family_title": family["title"],
        "family_path": family["detail_path"],
        "category": "model",
        "category_label": "Model",
        "slug": method_slug,
        "name": method.get("name") or method_slug,
        "summary": method.get("description") or guide.get("overview") or family.get("summary") or "",
        "overview": guide.get("overview") or method.get("description") or "",
        "equation": guide.get("equation") or "",
        "detail_path": method.get("detail_path") or _model_method_detail_path(family_slug, method_slug),
        "teaching_path": method.get("teaching_path") or _model_teaching_path(family_slug, method_slug),
        "workbench_path": method.get("workbench_path") or _prefilled_data_lab_link(
            {"workflow": "model", "model_family": family_slug, "model_type": method_slug}
        ),
        "inputs": list(family.get("key_inputs") or []),
        "outputs": list(guide.get("outputs") or []),
        "manual_checks": list(guide.get("manual_checks") or family.get("manual_checks") or []),
        "normal_result": guide.get("normal_result") or "",
        "paper_template": _paper_results_template(method_slug, str(method.get("name") or method_slug), guide),
        "paper_table_preview": _paper_table_preview(method_slug, str(method.get("name") or method_slug)),
    }


def get_model_teaching_guide(family_slug: str, method_slug: str) -> dict[str, object] | None:
    method = get_model_method(family_slug, method_slug)
    if not method:
        return None
    family = get_model_family(family_slug)
    guide = MODEL_METHOD_GUIDES.get(method_slug, {})
    return {
        "family_slug": family_slug,
        "family_title": method["family_title"],
        "family_path": method["family_path"],
        "slug": method_slug,
        "name": method["name"],
        "summary": f"Teaching page for {method['name']} in {method['family_title']}.",
        "equation": method["equation"],
        "detail_path": method["detail_path"],
        "workbench_path": method["workbench_path"],
        "sections": _teaching_sections(str(method["name"]), family or {}, guide),
        "paper_template": _paper_results_template(method_slug, str(method["name"]), guide),
        "paper_table_preview": _paper_table_preview(method_slug, str(method["name"])),
    }
