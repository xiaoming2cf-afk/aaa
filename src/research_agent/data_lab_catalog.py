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


def _decorate_family(item: dict[str, object], *, kind: str) -> dict[str, object]:
    detail = deepcopy(item)
    slug = str(detail["slug"])
    default_query = deepcopy(detail.get("default_workbench_query") or {})
    detail["detail_path"] = _family_detail_path("processing" if kind == "processing" else "models", slug)
    detail["workbench_path"] = _prefilled_data_lab_link(default_query)
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
