from __future__ import annotations

from copy import deepcopy
from urllib.parse import urlencode

from .model_library_support import engine_metadata


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


PROCESSING_VARIANT_PRESETS: dict[str, list[dict[str, object]]] = {
    "sample_preparation": [
        {
            "label": "Strict row eligibility",
            "description": "Keep duplicate removal and required-field filtering on so the prepared sample is maximally clean before modeling.",
            "spec": {
                "drop_duplicates": True,
                "drop_missing_required": True,
            },
        },
        {
            "label": "Loose eligibility review",
            "description": "Temporarily keep duplicate and missing-row rules off so you can inspect borderline rows before imposing final eligibility filters.",
            "spec": {
                "drop_duplicates": False,
                "drop_missing_required": False,
            },
        },
    ],
    "cleaning_transforms": [
        {
            "label": "Median + conservative tails",
            "description": "Median imputation with conservative winsor bounds and IQR outlier filtering.",
            "spec": {
                "impute_method": "median",
                "winsor_lower_quantile": 0.02,
                "winsor_upper_quantile": 0.98,
                "outlier_method": "iqr",
                "outlier_threshold": 1.5,
            },
        },
        {
            "label": "Mean + z-score trim",
            "description": "Mean imputation with wider tails and z-score outlier trimming for a looser robustness pass.",
            "spec": {
                "impute_method": "mean",
                "winsor_lower_quantile": 0.01,
                "winsor_upper_quantile": 0.99,
                "outlier_method": "zscore",
                "outlier_threshold": 3.0,
            },
        },
    ],
    "time_series_features": [
        {
            "label": "Short-horizon returns",
            "description": "Use log returns with one-step lags/leads and a short rolling window for monthly-style macro-finance panels.",
            "spec": {
                "return_method": "log",
                "lag_periods": 1,
                "lead_periods": 1,
                "rolling_window": 5,
            },
        },
        {
            "label": "Longer smoothing window",
            "description": "Keep simple returns but use longer dynamic windows for slower-moving macro variables.",
            "spec": {
                "return_method": "simple",
                "lag_periods": 2,
                "lead_periods": 2,
                "rolling_window": 12,
            },
        },
    ],
    "visualization": [
        {
            "label": "High-resolution export",
            "description": "Use a denser chart output budget so diagnostics retain more points before export.",
            "spec": {
                "max_points": 800,
            },
        },
        {
            "label": "Compact review chart",
            "description": "Keep chart exports lighter for quick manual review and notebook-style iteration.",
            "spec": {
                "max_points": 200,
            },
        },
    ],
}


MODEL_FAMILY_VARIANT_PRESETS: dict[str, list[dict[str, object]]] = {
    "econometrics_baseline": [
        {
            "label": "Robust covariance",
            "description": "Use heteroskedasticity-robust covariance as the default empirical baseline.",
            "spec": {"robust_covariance": True},
        },
        {
            "label": "Classical covariance",
            "description": "Re-run the same design with classical covariance for a direct table-to-table comparison.",
            "spec": {"robust_covariance": False},
        },
    ],
    "time_series_finance": [
        {
            "label": "Short horizon",
            "description": "Use a short forecast and impulse-response horizon with one lag.",
            "spec": {"forecast_steps": 4, "irf_horizon": 8, "var_lags": 1},
        },
        {
            "label": "Long horizon",
            "description": "Stretch the dynamic horizon and lag order to inspect persistence and longer spillovers.",
            "spec": {"forecast_steps": 12, "irf_horizon": 20, "var_lags": 2},
        },
    ],
    "corporate_finance": [
        {
            "label": "Balance-sheet focus",
            "description": "A bookkeeping-focused corporate-finance pass that keeps the emphasis on balance-sheet variables.",
            "spec": {},
        },
    ],
    "risk_management": [
        {
            "label": "Tighter confidence",
            "description": "Estimate risk metrics at a 99 percent confidence level.",
            "spec": {"confidence_level": 0.99},
        },
        {
            "label": "Multi-day horizon",
            "description": "Expand the holding period to inspect longer horizon loss aggregation.",
            "spec": {"holding_period_days": 5},
        },
    ],
    "derivatives_pricing": [
        {
            "label": "Call baseline",
            "description": "Keep call-option pricing with a moderate binomial tree depth.",
            "spec": {"option_type": "call", "option_steps": 50},
        },
        {
            "label": "Put robustness",
            "description": "Re-price with a put payoff and a denser tree for a robustness comparison.",
            "spec": {"option_type": "put", "option_steps": 100},
        },
    ],
    "macro_finance_dsge": [
        {
            "label": "Moderate persistence",
            "description": "Use a moderate shock persistence and horizon suitable for a first DSGE-style impulse pass.",
            "spec": {"dsge_shock_persistence": 0.9, "dsge_impulse_horizon": 12},
        },
        {
            "label": "High persistence",
            "description": "Increase shock persistence and horizon to inspect more durable macro propagation.",
            "spec": {"dsge_shock_persistence": 0.97, "dsge_impulse_horizon": 20},
        },
    ],
    "portfolio_allocation": [
        {
            "label": "Long-only benchmark",
            "description": "Keep the portfolio constrained to long-only allocations.",
            "spec": {"long_only": True, "risk_aversion": 3.0},
        },
        {
            "label": "Flexible allocation",
            "description": "Relax the long-only constraint and reduce risk aversion for a more aggressive allocation design.",
            "spec": {"long_only": False, "risk_aversion": 2.0},
        },
    ],
    "asset_pricing": [
        {
            "label": "Robust factor regression",
            "description": "Use robust covariance in the asset-pricing regression baseline.",
            "spec": {"robust_covariance": True},
        },
        {
            "label": "Classical factor regression",
            "description": "Re-run the factor regression with classical covariance for comparison against robust inference.",
            "spec": {"robust_covariance": False},
        },
    ],
}


def _model_method_variant_presets(method_slug: str) -> list[dict[str, object]]:
    presets: dict[str, list[dict[str, object]]] = {
        "ols": MODEL_FAMILY_VARIANT_PRESETS["econometrics_baseline"],
        "ppml": MODEL_FAMILY_VARIANT_PRESETS["econometrics_baseline"],
        "logit": MODEL_FAMILY_VARIANT_PRESETS["econometrics_baseline"],
        "probit": MODEL_FAMILY_VARIANT_PRESETS["econometrics_baseline"],
        "did": [
            {
                "label": "Robust DID baseline",
                "description": "Keep robust covariance for the main DID table.",
                "spec": {"robust_covariance": True},
            },
            {
                "label": "Classical DID comparison",
                "description": "Turn robust covariance off for a table-to-table comparison against the baseline.",
                "spec": {"robust_covariance": False},
            },
        ],
        "event_study": [
            {
                "label": "Narrow event window",
                "description": "Use a tighter lead-lag window for compact treatment dynamics.",
                "spec": {"lead_window": 2, "lag_window": 4, "omitted_period": -1},
            },
            {
                "label": "Wide event window",
                "description": "Use a wider event window to inspect longer-run anticipation and adjustment paths.",
                "spec": {"lead_window": 4, "lag_window": 8, "omitted_period": -1},
            },
        ],
        "rdd": [
            {
                "label": "Local linear RDD",
                "description": "Estimate the discontinuity with a local linear specification.",
                "spec": {"rdd_polynomial_order": 1, "rdd_bandwidth": 1.0, "treat_above_cutoff": True},
            },
            {
                "label": "Quadratic bandwidth check",
                "description": "Expand the bandwidth and fit a quadratic polynomial for robustness.",
                "spec": {"rdd_polynomial_order": 2, "rdd_bandwidth": 2.0, "treat_above_cutoff": True},
            },
        ],
        "fixed_effects": [
            {
                "label": "Entity effects only",
                "description": "Estimate with entity effects only.",
                "spec": {"include_time_effects": False},
            },
            {
                "label": "Two-way effects",
                "description": "Add time effects for a two-way fixed-effects robustness check.",
                "spec": {"include_time_effects": True},
            },
        ],
        "gravity": [
            {
                "label": "Robust gravity",
                "description": "Run the gravity model with robust covariance.",
                "spec": {"robust_covariance": True},
            },
            {
                "label": "Classical gravity",
                "description": "Run the same gravity design with classical covariance for comparison.",
                "spec": {"robust_covariance": False},
            },
        ],
        "iv_2sls": [
            {
                "label": "Robust IV",
                "description": "Use robust covariance in the 2SLS baseline.",
                "spec": {"robust_covariance": True},
            },
            {
                "label": "Classical IV",
                "description": "Turn robust covariance off to compare with conventional 2SLS output.",
                "spec": {"robust_covariance": False},
            },
        ],
        "panel_iv": [
            {
                "label": "Entity IV",
                "description": "Use panel IV without time effects.",
                "spec": {"include_time_effects": False},
            },
            {
                "label": "Two-way panel IV",
                "description": "Add time effects to the panel IV setup.",
                "spec": {"include_time_effects": True},
            },
        ],
        "arima": [
            {
                "label": "ARIMA short-memory",
                "description": "Use a compact ARIMA(1,0,1) configuration with short forecast steps.",
                "spec": {"arima_p": 1, "arima_d": 0, "arima_q": 1, "forecast_steps": 4},
            },
            {
                "label": "ARIMA differenced trend",
                "description": "Difference once and extend the forecast horizon for persistence checks.",
                "spec": {"arima_p": 2, "arima_d": 1, "arima_q": 1, "forecast_steps": 8},
            },
        ],
        "arch": [
            {
                "label": "ARCH(1) baseline",
                "description": "A simple ARCH-style volatility specification.",
                "spec": {"garch_p": 1, "garch_q": 0, "forecast_steps": 6},
            },
            {
                "label": "ARCH(2) check",
                "description": "Increase ARCH order for a sensitivity pass on short volatility clustering.",
                "spec": {"garch_p": 2, "garch_q": 0, "forecast_steps": 8},
            },
        ],
        "garch": [
            {
                "label": "GARCH(1,1) benchmark",
                "description": "Use the canonical GARCH(1,1) specification.",
                "spec": {"garch_p": 1, "garch_q": 1, "forecast_steps": 6},
            },
            {
                "label": "GARCH(2,1) persistence check",
                "description": "Increase the ARCH order and forecast horizon for a persistence comparison.",
                "spec": {"garch_p": 2, "garch_q": 1, "forecast_steps": 10},
            },
        ],
        "var": [
            {
                "label": "VAR short lag",
                "description": "Use one lag and a shorter forecast window.",
                "spec": {"var_lags": 1, "forecast_steps": 4},
            },
            {
                "label": "VAR longer lag",
                "description": "Use two lags and extend the forecast horizon for a richer dynamic comparison.",
                "spec": {"var_lags": 2, "forecast_steps": 8},
            },
        ],
        "svar_irf": [
            {
                "label": "SVAR compact IRF",
                "description": "Use a shorter horizon for compact impulse-response tables and figures.",
                "spec": {"var_lags": 1, "irf_horizon": 8},
            },
            {
                "label": "SVAR extended IRF",
                "description": "Use more lags and a longer horizon to inspect persistent structural responses.",
                "spec": {"var_lags": 2, "irf_horizon": 16},
            },
        ],
        "virf": [
            {
                "label": "One-sigma shock",
                "description": "Trace the volatility impulse response from a one-sigma shock.",
                "spec": {"virf_shock_size": 1.0, "forecast_steps": 6},
            },
            {
                "label": "Two-sigma shock",
                "description": "Increase the shock size to inspect stronger volatility propagation.",
                "spec": {"virf_shock_size": 2.0, "forecast_steps": 10},
            },
        ],
        "dy_connectedness": [
            {
                "label": "Short spillover window",
                "description": "Use a compact connectedness horizon with one lag.",
                "spec": {"var_lags": 1, "irf_horizon": 8},
            },
            {
                "label": "Extended spillover window",
                "description": "Extend both lag order and horizon for longer connectedness diagnostics.",
                "spec": {"var_lags": 2, "irf_horizon": 16},
            },
        ],
        "bk_connectedness": [
            {
                "label": "Short/medium frequency split",
                "description": "Use tighter short and medium frequency cutoffs.",
                "spec": {"var_lags": 1, "irf_horizon": 12, "bk_short_horizon": 4, "bk_medium_horizon": 16},
            },
            {
                "label": "Longer frequency split",
                "description": "Expand the BK horizons to emphasize slower cyclical connectedness.",
                "spec": {"var_lags": 2, "irf_horizon": 20, "bk_short_horizon": 6, "bk_medium_horizon": 24},
            },
        ],
        "historical_var": MODEL_FAMILY_VARIANT_PRESETS["risk_management"],
        "parametric_var": MODEL_FAMILY_VARIANT_PRESETS["risk_management"],
        "ewma_volatility": [
            {
                "label": "Baseline lambda",
                "description": "Use the canonical RiskMetrics-style lambda.",
                "spec": {"ewma_lambda": 0.94, "forecast_steps": 10},
            },
            {
                "label": "Faster decay",
                "description": "Reduce lambda to emphasize recent shocks more aggressively.",
                "spec": {"ewma_lambda": 0.90, "forecast_steps": 10},
            },
        ],
        "black_scholes": MODEL_FAMILY_VARIANT_PRESETS["derivatives_pricing"],
        "binomial_option": MODEL_FAMILY_VARIANT_PRESETS["derivatives_pricing"],
        "taylor_rule": [
            {
                "label": "Baseline policy rule",
                "description": "Keep the baseline Taylor-rule style specification.",
                "spec": {"robust_covariance": True},
            },
            {
                "label": "Classical policy rule",
                "description": "Use classical covariance for a specification comparison.",
                "spec": {"robust_covariance": False},
            },
        ],
        "toy_dsge": MODEL_FAMILY_VARIANT_PRESETS["macro_finance_dsge"],
        "mean_variance": MODEL_FAMILY_VARIANT_PRESETS["portfolio_allocation"],
        "minimum_variance": MODEL_FAMILY_VARIANT_PRESETS["portfolio_allocation"],
        "risk_parity": MODEL_FAMILY_VARIANT_PRESETS["portfolio_allocation"],
        "capm": MODEL_FAMILY_VARIANT_PRESETS["asset_pricing"],
        "ff3": MODEL_FAMILY_VARIANT_PRESETS["asset_pricing"],
        "altman_z": MODEL_FAMILY_VARIANT_PRESETS["corporate_finance"],
        "dupont": MODEL_FAMILY_VARIANT_PRESETS["corporate_finance"],
    }
    return deepcopy(presets.get(method_slug, []))


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
    detail["variant_presets"] = deepcopy(
        PROCESSING_VARIANT_PRESETS.get(slug, []) if kind == "processing" else MODEL_FAMILY_VARIANT_PRESETS.get(slug, [])
    )
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
            method_copy["variant_presets"] = _model_method_variant_presets(method_slug)
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
        "suite_requirements": {
            "optimization": {
                "min_algorithms": 3,
                "min_functions": 3,
                "min_runs": 3,
            }
        },
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
        "variant_presets": list(method.get("variant_presets") or family.get("variant_presets") or []),
        "paper_template": _paper_results_template(method_slug, str(method.get("name") or method_slug), guide),
        "paper_table_preview": _paper_table_preview(method_slug, str(method.get("name") or method_slug)),
        "engine": method.get("engine") or "baseline",
        "engine_label": method.get("engine_label") or "Baseline",
        "engine_available": bool(method.get("engine_available", True)),
        "engine_version": method.get("engine_version") or "",
        "engine_note": method.get("engine_note") or "",
        "baseline_engine": method.get("baseline_engine") or method.get("engine") or "baseline",
        "candidate_engine": method.get("candidate_engine") or "",
        "comparison_required": bool(method.get("comparison_required", False)),
        "comparison_status": method.get("comparison_status") or "pending",
        "async_only": bool(method.get("async_only", False)),
        "requires_optional_dependency": bool(method.get("requires_optional_dependency", False)),
        "variant_schema": deepcopy(method.get("variant_schema") or family.get("variant_schema") or {}),
        "paper_output_contract": deepcopy(method.get("paper_output_contract") or {}),
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
        "variant_presets": list(method.get("variant_presets") or family.get("variant_presets") or []),
        "paper_template": _paper_results_template(method_slug, str(method["name"]), guide),
        "paper_table_preview": _paper_table_preview(method_slug, str(method["name"])),
        "engine": method.get("engine") or "baseline",
        "engine_label": method.get("engine_label") or "Baseline",
        "engine_available": bool(method.get("engine_available", True)),
        "engine_version": method.get("engine_version") or "",
        "engine_note": method.get("engine_note") or "",
        "baseline_engine": method.get("baseline_engine") or method.get("engine") or "baseline",
        "candidate_engine": method.get("candidate_engine") or "",
        "comparison_required": bool(method.get("comparison_required", False)),
        "comparison_status": method.get("comparison_status") or "pending",
        "async_only": bool(method.get("async_only", False)),
        "requires_optional_dependency": bool(method.get("requires_optional_dependency", False)),
        "variant_schema": deepcopy(method.get("variant_schema") or family.get("variant_schema") or {}),
        "paper_output_contract": deepcopy(method.get("paper_output_contract") or {}),
    }


def _make_method_guide(
    overview: str,
    equation: str,
    outputs: list[str],
    normal_result: str,
    manual_checks: list[str] | None = None,
) -> dict[str, object]:
    return {
        "overview": overview,
        "equation": equation,
        "outputs": outputs,
        "normal_result": normal_result,
        "manual_checks": manual_checks or [],
    }


def _paper_output_contract(
    primary_tables: list[str],
    figures: list[str],
    *,
    robustness_tables: list[str] | None = None,
    diagnostics: list[str] | None = None,
) -> dict[str, object]:
    return {
        "primary_tables": primary_tables,
        "robustness_tables": robustness_tables or [],
        "figures": figures,
        "diagnostics": diagnostics or [],
    }


def _find_model_family_mutable(slug: str) -> dict[str, object] | None:
    for family in MODEL_FAMILY_CATALOG:
        if family.get("slug") == slug:
            return family
    return None


def _append_methods(family_slug: str, methods: list[dict[str, object]]) -> None:
    family = _find_model_family_mutable(family_slug)
    if not family:
        raise KeyError(f"Unknown model family: {family_slug}")
    existing = {str(method.get("slug")) for method in family.get("methods") or []}
    for method in methods:
        if str(method.get("slug")) not in existing:
            family.setdefault("methods", []).append(method)


def _append_family(family: dict[str, object]) -> None:
    if _find_model_family_mutable(str(family.get("slug"))):
        return
    MODEL_FAMILY_CATALOG.append(family)


def _extend_method_guides(guides: dict[str, dict[str, object]]) -> None:
    MODEL_METHOD_GUIDES.update(guides)


def _update_method_metadata(family_slug: str, updates: dict[str, dict[str, object]]) -> None:
    family = _find_model_family_mutable(family_slug)
    if not family:
        return
    for method in family.get("methods") or []:
        slug = str(method.get("slug") or "")
        if slug in updates:
            method.update(deepcopy(updates[slug]))


COMMON_REGRESSION_SCHEMA = {
    "shared": [
        "dependent",
        "independents",
        "controls",
        "entity_column",
        "time_column",
        "robust_covariance",
        "subset_filter",
        "lag_terms",
        "lead_terms",
        "log_transform_columns",
        "interaction_terms",
        "quadratic_terms",
    ],
}


TIME_SERIES_SCHEMA = {
    "shared": [
        "dependent",
        "series_columns",
        "time_column",
        "forecast_steps",
        "lag_order",
        "difference_order",
        "distribution",
        "volatility_family",
        "impulse_column",
        "response_column",
    ],
}


PORTFOLIO_SCHEMA = {
    "shared": [
        "series_columns",
        "objective",
        "weight_bounds",
        "long_only",
        "risk_free_rate",
        "market_neutral",
        "target_return",
        "target_risk",
    ],
}


CAUSAL_SCHEMA = {
    "shared": [
        "dependent",
        "treatment_column",
        "post_column",
        "event_time_column",
        "running_column",
        "cutoff",
        "bandwidth",
        "entity_column",
        "time_column",
        "include_time_effects",
        "donor_pool",
        "placebo_checks",
        "pretrend_checks",
    ],
}


BAYESIAN_SCHEMA = {
    "shared": [
        "dependent",
        "independents",
        "controls",
        "priors",
        "chains",
        "draws",
        "tune",
        "target_accept",
        "hdi_prob",
        "posterior_predictive",
    ],
}


def _candidate_method(
    *,
    slug: str,
    name: str,
    description: str,
    engine: str,
    paper_contract: dict[str, object],
    variant_schema: dict[str, object],
    baseline_engine: str = "baseline",
    candidate_engine: str = "",
    comparison_required: bool = False,
    async_only: bool = False,
    optional: bool = True,
) -> dict[str, object]:
    method = {
        "slug": slug,
        "name": name,
        "description": description,
        "paper_output_contract": deepcopy(paper_contract),
        "variant_schema": deepcopy(variant_schema),
        "baseline_engine": baseline_engine,
        "candidate_engine": candidate_engine or engine,
        "comparison_required": comparison_required,
        "comparison_status": "pending" if comparison_required else "not_required",
    }
    method.update(engine_metadata(engine, async_only=async_only, optional=optional))
    return method


_append_methods(
    "econometrics_baseline",
    [
        _candidate_method(
            slug="random_effects",
            name="Random Effects",
            description="Panel random-effects estimator for partially pooled entity variation.",
            engine="linearmodels",
            paper_contract=_paper_output_contract(
                ["Random-effects main table", "Variance decomposition table"],
                ["Residual distribution plot"],
                robustness_tables=["Hausman-style comparison table"],
            ),
            variant_schema=COMMON_REGRESSION_SCHEMA,
        ),
        _candidate_method(
            slug="first_difference",
            name="First Difference",
            description="Panel first-difference estimator that removes time-invariant heterogeneity.",
            engine="linearmodels",
            paper_contract=_paper_output_contract(
                ["First-difference main table", "Differenced sample audit table"],
                ["Differenced outcome diagnostic plot"],
                robustness_tables=["Alternative lag/lead specification table"],
            ),
            variant_schema=COMMON_REGRESSION_SCHEMA,
        ),
        _candidate_method(
            slug="between_ols",
            name="Between OLS",
            description="Between estimator using unit-level averages across time.",
            engine="linearmodels",
            paper_contract=_paper_output_contract(
                ["Between-estimator main table", "Entity-average sample audit table"],
                ["Entity-average comparison plot"],
            ),
            variant_schema=COMMON_REGRESSION_SCHEMA,
        ),
        _candidate_method(
            slug="pooled_ols",
            name="Pooled OLS",
            description="Pooled panel regression benchmark without fixed effects.",
            engine="linearmodels",
            paper_contract=_paper_output_contract(
                ["Pooled OLS table", "Model comparison table"],
                ["Residual diagnostic plot"],
                robustness_tables=["Robust covariance comparison table"],
            ),
            variant_schema=COMMON_REGRESSION_SCHEMA,
        ),
        _candidate_method(
            slug="fama_macbeth",
            name="Fama-MacBeth",
            description="Cross-sectional asset-pricing regression with time-series aggregation of coefficients.",
            engine="linearmodels",
            paper_contract=_paper_output_contract(
                ["Fama-MacBeth coefficient table", "Period-by-period summary table"],
                ["Factor premium path plot"],
                robustness_tables=["Alternative factor specification table"],
            ),
            variant_schema=COMMON_REGRESSION_SCHEMA,
        ),
        _candidate_method(
            slug="iv_liml",
            name="IV-LIML",
            description="Limited-information maximum likelihood estimator for weak-instrument settings.",
            engine="linearmodels",
            paper_contract=_paper_output_contract(
                ["IV-LIML main table", "Weak-instrument diagnostic table"],
                ["First-stage fit plot"],
                robustness_tables=["2SLS vs LIML comparison table"],
            ),
            variant_schema=COMMON_REGRESSION_SCHEMA,
        ),
        _candidate_method(
            slug="iv_gmm",
            name="IV-GMM",
            description="Generalized-method-of-moments IV estimator with over-identification diagnostics.",
            engine="linearmodels",
            paper_contract=_paper_output_contract(
                ["IV-GMM main table", "Over-identification diagnostic table"],
                ["Moment-condition diagnostic plot"],
                robustness_tables=["Alternative weighting matrix table"],
            ),
            variant_schema=COMMON_REGRESSION_SCHEMA,
        ),
        _candidate_method(
            slug="absorbing_ls",
            name="Absorbing Least Squares",
            description="High-dimensional fixed-effects regression using absorbed dummies.",
            engine="linearmodels",
            paper_contract=_paper_output_contract(
                ["Absorbing-LS main table", "Absorbed-effects audit table"],
                ["Residual by group plot"],
            ),
            variant_schema=COMMON_REGRESSION_SCHEMA,
        ),
        _candidate_method(
            slug="sur",
            name="SUR",
            description="Seemingly unrelated regression for correlated system equations.",
            engine="linearmodels",
            paper_contract=_paper_output_contract(
                ["SUR system table", "Equation covariance table"],
                ["System residual correlation heatmap"],
            ),
            variant_schema=COMMON_REGRESSION_SCHEMA,
        ),
        _candidate_method(
            slug="iv_3sls",
            name="IV-3SLS",
            description="Three-stage least squares for simultaneous-equation systems with instruments.",
            engine="linearmodels",
            paper_contract=_paper_output_contract(
                ["3SLS system table", "Instrument validity table"],
                ["Equation residual plot"],
            ),
            variant_schema=COMMON_REGRESSION_SCHEMA,
        ),
        _candidate_method(
            slug="system_gmm",
            name="System GMM",
            description="System-GMM style estimator for dynamic panel equations.",
            engine="linearmodels",
            paper_contract=_paper_output_contract(
                ["System-GMM main table", "Serial-correlation and Hansen table"],
                ["Dynamic fit plot"],
            ),
            variant_schema=COMMON_REGRESSION_SCHEMA,
            async_only=True,
        ),
    ],
)

_append_methods(
    "time_series_finance",
    [
        _candidate_method(
            slug="varmax",
            name="VARMAX",
            description="State-space VARMAX model for multivariate dynamics with moving-average terms.",
            engine="statsmodels",
            paper_contract=_paper_output_contract(
                ["VARMAX system table", "Forecast summary table"],
                ["Forecast path plot", "Residual diagnostics plot"],
            ),
            variant_schema=TIME_SERIES_SCHEMA,
        ),
        _candidate_method(
            slug="vecm",
            name="VECM",
            description="Vector error-correction model for cointegrated multivariate systems.",
            engine="statsmodels",
            paper_contract=_paper_output_contract(
                ["VECM coefficient table", "Cointegration summary table"],
                ["Impulse-response plot", "Error-correction path plot"],
            ),
            variant_schema=TIME_SERIES_SCHEMA,
        ),
        _candidate_method(
            slug="markov_switching",
            name="Markov Switching",
            description="Regime-switching model with latent states and filtered probabilities.",
            engine="statsmodels",
            paper_contract=_paper_output_contract(
                ["Markov-switching summary table", "State probability table"],
                ["Smoothed state probability plot"],
            ),
            variant_schema=TIME_SERIES_SCHEMA,
        ),
        _candidate_method(
            slug="unobserved_components",
            name="Unobserved Components",
            description="State-space decomposition into trend, cycle, and irregular components.",
            engine="statsmodels",
            paper_contract=_paper_output_contract(
                ["Component summary table", "Trend/cycle decomposition table"],
                ["Trend decomposition plot", "Component contribution plot"],
            ),
            variant_schema=TIME_SERIES_SCHEMA,
        ),
        _candidate_method(
            slug="exponential_smoothing",
            name="Exponential Smoothing",
            description="ETS forecast model with level, trend, and seasonality controls.",
            engine="statsmodels",
            paper_contract=_paper_output_contract(
                ["ETS summary table", "Forecast comparison table"],
                ["Forecast path plot"],
            ),
            variant_schema=TIME_SERIES_SCHEMA,
        ),
        _candidate_method(
            slug="egarch",
            name="EGARCH",
            description="Exponential GARCH model for asymmetric volatility responses.",
            engine="arch",
            paper_contract=_paper_output_contract(
                ["EGARCH parameter table", "Volatility forecast table"],
                ["Conditional volatility plot", "Forecast volatility plot"],
                diagnostics=["Residual diagnostic table"],
            ),
            variant_schema=TIME_SERIES_SCHEMA,
        ),
        _candidate_method(
            slug="gjr_garch",
            name="GJR-GARCH",
            description="Threshold GARCH model with leverage effects.",
            engine="arch",
            paper_contract=_paper_output_contract(
                ["GJR-GARCH parameter table", "Volatility forecast table"],
                ["Conditional volatility plot", "Forecast volatility plot"],
                diagnostics=["Residual diagnostic table"],
            ),
            variant_schema=TIME_SERIES_SCHEMA,
        ),
        _candidate_method(
            slug="harx",
            name="HARX",
            description="Heterogeneous autoregressive model with exogenous features for realized-volatility style problems.",
            engine="arch",
            paper_contract=_paper_output_contract(
                ["HARX parameter table", "Forecast table"],
                ["Forecast path plot"],
            ),
            variant_schema=TIME_SERIES_SCHEMA,
        ),
        _candidate_method(
            slug="adf_test",
            name="ADF Unit Root Test",
            description="Augmented Dickey-Fuller unit root test with lag and trend options.",
            engine="arch",
            paper_contract=_paper_output_contract(
                ["ADF test table", "Lag selection table"],
                ["Series level plot"],
            ),
            variant_schema=TIME_SERIES_SCHEMA,
        ),
        _candidate_method(
            slug="kpss_test",
            name="KPSS Stationarity Test",
            description="KPSS stationarity test with level or trend null.",
            engine="arch",
            paper_contract=_paper_output_contract(
                ["KPSS test table", "Bandwidth table"],
                ["Series level plot"],
            ),
            variant_schema=TIME_SERIES_SCHEMA,
        ),
        _candidate_method(
            slug="pp_test",
            name="Phillips-Perron Test",
            description="Phillips-Perron unit root test with heteroskedasticity-robust correction.",
            engine="arch",
            paper_contract=_paper_output_contract(
                ["Phillips-Perron test table", "Bandwidth table"],
                ["Series level plot"],
            ),
            variant_schema=TIME_SERIES_SCHEMA,
        ),
        _candidate_method(
            slug="zivot_andrews",
            name="Zivot-Andrews Break Test",
            description="Unit root test with a single endogenous structural break.",
            engine="arch",
            paper_contract=_paper_output_contract(
                ["Zivot-Andrews test table", "Break-date summary table"],
                ["Series with break marker plot"],
            ),
            variant_schema=TIME_SERIES_SCHEMA,
        ),
        _candidate_method(
            slug="engle_granger",
            name="Engle-Granger Cointegration",
            description="Residual-based cointegration test for long-run equilibrium relationships.",
            engine="arch",
            paper_contract=_paper_output_contract(
                ["Cointegration test table", "Long-run regression table"],
                ["Residual stationarity plot"],
            ),
            variant_schema=TIME_SERIES_SCHEMA,
        ),
        _candidate_method(
            slug="dynamic_ols",
            name="Dynamic OLS",
            description="Cointegration estimator with leads and lags of first differences.",
            engine="arch",
            paper_contract=_paper_output_contract(
                ["Dynamic OLS main table", "Lead-lag audit table"],
                ["Fitted long-run relation plot"],
            ),
            variant_schema=TIME_SERIES_SCHEMA,
        ),
        _candidate_method(
            slug="fm_ols",
            name="Fully Modified OLS",
            description="Cointegration estimator robust to endogeneity and serial correlation.",
            engine="arch",
            paper_contract=_paper_output_contract(
                ["FM-OLS main table", "Kernel/bandwidth audit table"],
                ["Long-run fit plot"],
            ),
            variant_schema=TIME_SERIES_SCHEMA,
        ),
    ],
)

_append_methods(
    "portfolio_allocation",
    [
        _candidate_method(
            slug="efficient_frontier",
            name="Efficient Frontier",
            description="Mean-variance frontier and optimal portfolio under configurable objectives.",
            engine="pypfopt",
            paper_contract=_paper_output_contract(
                ["Weight table", "Risk-return summary table"],
                ["Efficient frontier plot", "Weight allocation plot"],
            ),
            variant_schema=PORTFOLIO_SCHEMA,
        ),
        _candidate_method(
            slug="semivariance_frontier",
            name="Efficient Semivariance",
            description="Downside-risk frontier using semivariance instead of total variance.",
            engine="pypfopt",
            paper_contract=_paper_output_contract(
                ["Semivariance allocation table", "Downside-risk summary table"],
                ["Semivariance frontier plot"],
            ),
            variant_schema=PORTFOLIO_SCHEMA,
        ),
        _candidate_method(
            slug="cvar_frontier",
            name="Efficient CVaR",
            description="Tail-risk-aware allocation using CVaR optimization.",
            engine="pypfopt",
            paper_contract=_paper_output_contract(
                ["CVaR allocation table", "Tail-risk summary table"],
                ["CVaR frontier plot"],
            ),
            variant_schema=PORTFOLIO_SCHEMA,
        ),
        _candidate_method(
            slug="black_litterman",
            name="Black-Litterman",
            description="Bayesian portfolio combination of equilibrium returns and user views.",
            engine="pypfopt",
            paper_contract=_paper_output_contract(
                ["Black-Litterman weights table", "Posterior return table"],
                ["Posterior allocation plot", "View impact plot"],
            ),
            variant_schema=PORTFOLIO_SCHEMA,
            async_only=True,
        ),
        _candidate_method(
            slug="hrp",
            name="Hierarchical Risk Parity",
            description="Clustering-based portfolio construction with hierarchical risk parity.",
            engine="pypfopt",
            paper_contract=_paper_output_contract(
                ["HRP weights table", "Cluster risk table"],
                ["Dendrogram plot", "Risk contribution plot"],
            ),
            variant_schema=PORTFOLIO_SCHEMA,
        ),
        _candidate_method(
            slug="discrete_allocation",
            name="Discrete Allocation",
            description="Translate continuous weights into integer holdings for implementable portfolios.",
            engine="pypfopt",
            paper_contract=_paper_output_contract(
                ["Discrete allocation table", "Cash remainder table"],
                ["Allocation value plot"],
            ),
            variant_schema=PORTFOLIO_SCHEMA,
        ),
    ],
)

_append_family(
    {
        "slug": "causal_inference",
        "title": "Causal Inference",
        "category": "model",
        "category_label": "Model",
        "summary": "Policy-evaluation and design-based causal estimators with explicit identification checks.",
        "description": "Use this family for quasi-experimental designs such as staggered adoption, synthetic controls, interrupted time series, and regression-kink style identification.",
        "key_inputs": ["Outcome, treatment, time, design variables", "Donor pool or pre-treatment structure", "Placebo and pre-trend settings"],
        "manual_checks": ["Confirm treatment timing definitions.", "Inspect donor/pre-period balance.", "Validate placebo or sensitivity outputs against the design narrative."],
        "variant_schema": CAUSAL_SCHEMA,
        "methods": [
            _candidate_method(slug="staggered_did", name="Staggered DID", description="Difference-in-differences with staggered adoption timing and cohort-time effects.", engine="causalpy", paper_contract=_paper_output_contract(["Main staggered DID table", "Cohort-time effect table"], ["Dynamic treatment effect plot"], robustness_tables=["Placebo or alternative timing table"]), variant_schema=CAUSAL_SCHEMA, async_only=True),
            _candidate_method(slug="synthetic_control", name="Synthetic Control", description="Construct a synthetic counterfactual from donor units for case-study treatment analysis.", engine="causalpy", paper_contract=_paper_output_contract(["Synthetic-control fit table", "Donor weight table"], ["Observed vs synthetic path plot", "Gap plot"], diagnostics=["Pre-treatment fit diagnostics"]), variant_schema=CAUSAL_SCHEMA, async_only=True),
            _candidate_method(slug="interrupted_time_series", name="Interrupted Time Series", description="Estimate level and slope changes after a policy interruption in ordered data.", engine="causalpy", paper_contract=_paper_output_contract(["ITS coefficient table", "Pre/post slope summary table"], ["Observed vs fitted ITS plot"], robustness_tables=["Alternative break-date table"]), variant_schema=CAUSAL_SCHEMA),
            _candidate_method(slug="regression_kink", name="Regression Kink", description="Causal identification from slope changes at a known kink point.", engine="causalpy", paper_contract=_paper_output_contract(["Regression kink table", "Bandwidth and slope audit table"], ["Kink diagnostic plot"]), variant_schema=CAUSAL_SCHEMA),
            _candidate_method(slug="instrumental_causal", name="Instrumental Variable Causal", description="CausalPy IV workflow with design-oriented diagnostics.", engine="causalpy", paper_contract=_paper_output_contract(["Causal IV main table", "First-stage diagnostic table"], ["Fitted treatment plot"]), variant_schema=CAUSAL_SCHEMA),
            _candidate_method(slug="inverse_propensity_weighting", name="Inverse Propensity Weighting", description="Reweight observational samples using estimated treatment propensities.", engine="causalpy", paper_contract=_paper_output_contract(["IPW treatment-effect table", "Propensity summary table"], ["Propensity overlap plot"], diagnostics=["Balance diagnostic table"]), variant_schema=CAUSAL_SCHEMA),
        ],
        "default_workbench_query": {"workflow": "model", "model_family": "causal_inference", "model_type": "staggered_did"},
    }
)

_append_family(
    {
        "slug": "bayesian",
        "title": "Bayesian Modeling",
        "category": "model",
        "category_label": "Model",
        "summary": "Bayesian regression, causal, and panel models with posterior diagnostics.",
        "description": "Use this family when posterior uncertainty, priors, or hierarchical structure is the primary research requirement.",
        "key_inputs": ["Outcome and predictor variables", "Prior settings and sampler configuration", "Posterior predictive checks"],
        "manual_checks": ["Inspect trace diagnostics and divergences.", "Check prior sensitivity against posterior summaries.", "Verify HDI and predictive plots against posterior tables."],
        "variant_schema": BAYESIAN_SCHEMA,
        "methods": [
            _candidate_method(slug="bayesian_linear_regression", name="Bayesian Linear Regression", description="Linear regression estimated with priors and posterior inference.", engine="pymc", paper_contract=_paper_output_contract(["Posterior summary table", "Predictor contribution table"], ["Trace plot", "Posterior predictive plot"], diagnostics=["Sampler diagnostic table"]), variant_schema=BAYESIAN_SCHEMA, async_only=True),
            _candidate_method(slug="bayesian_panel", name="Bayesian Panel", description="Hierarchical panel regression with unit-level random structure.", engine="pymc", paper_contract=_paper_output_contract(["Posterior coefficient table", "Group-level variance table"], ["Trace plot", "Posterior predictive panel plot"], diagnostics=["Sampler diagnostic table"]), variant_schema=BAYESIAN_SCHEMA, async_only=True),
            _candidate_method(slug="bayesian_did", name="Bayesian DID", description="Bayesian treatment-effect estimation for before-after designs.", engine="pymc", paper_contract=_paper_output_contract(["Posterior treatment-effect table", "Cell-mean posterior table"], ["Trace plot", "Posterior treatment effect plot"], diagnostics=["Sampler diagnostic table"]), variant_schema=BAYESIAN_SCHEMA, async_only=True),
            _candidate_method(slug="bayesian_its", name="Bayesian ITS", description="Bayesian interrupted time-series with posterior intervention effects.", engine="pymc", paper_contract=_paper_output_contract(["Posterior intervention table", "Slope change posterior table"], ["Trace plot", "Posterior path plot"], diagnostics=["Sampler diagnostic table"]), variant_schema=BAYESIAN_SCHEMA, async_only=True),
        ],
        "default_workbench_query": {"workflow": "model", "model_family": "bayesian", "model_type": "bayesian_linear_regression"},
    }
)

_append_family(
    {
        "slug": "quant_research",
        "title": "Quant Research",
        "category": "model",
        "category_label": "Model",
        "summary": "Prediction, signal evaluation, and lightweight backtest workflows inspired by qlib.",
        "description": "Use this family for predictive alpha research and strategy diagnostics within the current workspace, without depending on qlib online services.",
        "key_inputs": ["Feature columns", "Label horizon", "Backtest or ranking configuration"],
        "manual_checks": ["Verify feature/label definitions.", "Check train-test split dates.", "Compare reported IC and return metrics against exported predictions."],
        "variant_schema": {"shared": ["feature_columns", "label_column", "split_date", "model_config", "strategy_config", "backtest_config"]},
        "methods": [
            _candidate_method(slug="quant_linear_model", name="Quant Linear Model", description="Linear predictive model for alpha research with IC diagnostics.", engine="qlib", paper_contract=_paper_output_contract(["Prediction metric table", "IC summary table"], ["Prediction path plot", "Cumulative return plot"]), variant_schema={"shared": ["feature_columns", "label_column", "split_date", "holding_period"]}, async_only=True),
            _candidate_method(slug="quant_lightgbm", name="Quant LightGBM", description="Gradient-boosted alpha model with ranked-signal evaluation.", engine="lightgbm", paper_contract=_paper_output_contract(["Prediction metric table", "Feature importance table"], ["Feature importance plot", "Cumulative return plot"]), variant_schema={"shared": ["feature_columns", "label_column", "split_date", "holding_period", "num_leaves", "learning_rate"]}, async_only=True),
            _candidate_method(slug="quant_backtest_report", name="Quant Backtest Report", description="Signal ranking and portfolio backtest report with position analysis.", engine="qlib", paper_contract=_paper_output_contract(["Backtest metric table", "Position analysis table"], ["Strategy equity curve", "Turnover plot"]), variant_schema={"shared": ["prediction_asset_id", "backtest_config", "transaction_cost"]}, async_only=True),
        ],
        "default_workbench_query": {"workflow": "model", "model_family": "quant_research", "model_type": "quant_linear_model"},
    }
)

_update_method_metadata(
    "econometrics_baseline",
    {
        "ols": {
            **engine_metadata("statsmodels", optional=False),
            "baseline_engine": "baseline",
            "candidate_engine": "statsmodels",
            "comparison_required": True,
            "comparison_status": "pending",
            "variant_schema": COMMON_REGRESSION_SCHEMA,
        },
        "ppml": {
            **engine_metadata("statsmodels", optional=False),
            "baseline_engine": "baseline",
            "candidate_engine": "statsmodels",
            "comparison_required": True,
            "comparison_status": "pending",
            "variant_schema": COMMON_REGRESSION_SCHEMA,
        },
        "logit": {
            **engine_metadata("statsmodels", optional=False),
            "baseline_engine": "baseline",
            "candidate_engine": "statsmodels",
            "comparison_required": True,
            "comparison_status": "pending",
            "variant_schema": COMMON_REGRESSION_SCHEMA,
        },
        "probit": {
            **engine_metadata("statsmodels", optional=False),
            "baseline_engine": "baseline",
            "candidate_engine": "statsmodels",
            "comparison_required": True,
            "comparison_status": "pending",
            "variant_schema": COMMON_REGRESSION_SCHEMA,
        },
        "fixed_effects": {
            **engine_metadata("linearmodels", optional=False),
            "baseline_engine": "baseline",
            "candidate_engine": "linearmodels",
            "comparison_required": True,
            "comparison_status": "pending",
            "variant_schema": COMMON_REGRESSION_SCHEMA,
        },
        "panel_iv": {
            **engine_metadata("linearmodels", optional=False),
            "baseline_engine": "baseline",
            "candidate_engine": "linearmodels",
            "comparison_required": True,
            "comparison_status": "pending",
            "variant_schema": COMMON_REGRESSION_SCHEMA,
        },
        "did": {
            **engine_metadata("causalpy"),
            "baseline_engine": "baseline",
            "candidate_engine": "causalpy",
            "comparison_required": True,
            "comparison_status": "pending",
            "variant_schema": CAUSAL_SCHEMA,
        },
        "event_study": {
            **engine_metadata("causalpy"),
            "baseline_engine": "baseline",
            "candidate_engine": "causalpy",
            "comparison_required": True,
            "comparison_status": "pending",
            "variant_schema": CAUSAL_SCHEMA,
        },
        "rdd": {
            **engine_metadata("causalpy"),
            "baseline_engine": "baseline",
            "candidate_engine": "causalpy",
            "comparison_required": True,
            "comparison_status": "pending",
            "variant_schema": CAUSAL_SCHEMA,
        },
    },
)

_update_method_metadata(
    "time_series_finance",
    {
        "arima": {
            **engine_metadata("statsmodels", optional=False),
            "baseline_engine": "baseline",
            "candidate_engine": "statsmodels",
            "comparison_required": True,
            "comparison_status": "pending",
            "variant_schema": TIME_SERIES_SCHEMA,
        },
        "var": {
            **engine_metadata("statsmodels", optional=False),
            "baseline_engine": "baseline",
            "candidate_engine": "statsmodels",
            "comparison_required": True,
            "comparison_status": "pending",
            "variant_schema": TIME_SERIES_SCHEMA,
        },
        "svar_irf": {
            **engine_metadata("statsmodels", optional=False),
            "baseline_engine": "baseline",
            "candidate_engine": "statsmodels",
            "comparison_required": True,
            "comparison_status": "pending",
            "variant_schema": TIME_SERIES_SCHEMA,
        },
        "arch": {
            **engine_metadata("arch", optional=False),
            "baseline_engine": "baseline",
            "candidate_engine": "arch",
            "comparison_required": True,
            "comparison_status": "pending",
            "variant_schema": TIME_SERIES_SCHEMA,
        },
        "garch": {
            **engine_metadata("arch", optional=False),
            "baseline_engine": "baseline",
            "candidate_engine": "arch",
            "comparison_required": True,
            "comparison_status": "pending",
            "variant_schema": TIME_SERIES_SCHEMA,
        },
    },
)

_update_method_metadata(
    "portfolio_allocation",
    {
        "mean_variance": {
            **engine_metadata("pypfopt", optional=False),
            "baseline_engine": "baseline",
            "candidate_engine": "pypfopt",
            "comparison_required": True,
            "comparison_status": "pending",
            "variant_schema": PORTFOLIO_SCHEMA,
        },
        "minimum_variance": {
            **engine_metadata("pypfopt", optional=False),
            "baseline_engine": "baseline",
            "candidate_engine": "pypfopt",
            "comparison_required": True,
            "comparison_status": "pending",
            "variant_schema": PORTFOLIO_SCHEMA,
        },
        "risk_parity": {
            **engine_metadata("pypfopt", optional=False),
            "baseline_engine": "baseline",
            "candidate_engine": "pypfopt",
            "comparison_required": True,
            "comparison_status": "pending",
            "variant_schema": PORTFOLIO_SCHEMA,
        },
    },
)

_append_methods(
    "econometrics_baseline",
    [
        _candidate_method(
            slug="glm",
            name="GLM",
            description="Generalized linear model with configurable family and link.",
            engine="statsmodels",
            paper_contract=_paper_output_contract(
                ["GLM coefficient table", "Family/link audit table"],
                ["Fitted vs actual plot"],
                robustness_tables=["Alternative family table"],
            ),
            variant_schema=COMMON_REGRESSION_SCHEMA,
        ),
        _candidate_method(
            slug="quantile_regression",
            name="Quantile Regression",
            description="Estimate conditional quantiles instead of the conditional mean.",
            engine="statsmodels",
            paper_contract=_paper_output_contract(
                ["Quantile coefficient table", "Quantile comparison table"],
                ["Coefficient path by quantile"],
            ),
            variant_schema=COMMON_REGRESSION_SCHEMA,
        ),
        _candidate_method(
            slug="gee",
            name="GEE",
            description="Generalized estimating equations for correlated outcomes.",
            engine="statsmodels",
            paper_contract=_paper_output_contract(
                ["GEE coefficient table", "Working-correlation summary table"],
                ["Cluster diagnostic plot"],
            ),
            variant_schema=COMMON_REGRESSION_SCHEMA,
        ),
        _candidate_method(
            slug="mnlogit",
            name="Multinomial Logit",
            description="Multinomial discrete-choice model for outcomes with more than two categories.",
            engine="statsmodels",
            paper_contract=_paper_output_contract(
                ["MNLogit coefficient table", "Class probability table"],
                ["Predicted class distribution plot"],
            ),
            variant_schema=COMMON_REGRESSION_SCHEMA,
        ),
        _candidate_method(
            slug="negative_binomial",
            name="Negative Binomial",
            description="Over-dispersed count model with explicit dispersion parameter.",
            engine="statsmodels",
            paper_contract=_paper_output_contract(
                ["Negative-binomial main table", "Dispersion summary table"],
                ["Predicted vs observed count plot"],
            ),
            variant_schema=COMMON_REGRESSION_SCHEMA,
        ),
        _candidate_method(
            slug="zero_inflated_count",
            name="Zero-Inflated Count",
            description="Zero-inflated Poisson or negative-binomial count specification.",
            engine="statsmodels",
            paper_contract=_paper_output_contract(
                ["Zero-inflated count table", "Inflation probability table"],
                ["Observed vs fitted count plot"],
            ),
            variant_schema=COMMON_REGRESSION_SCHEMA,
        ),
        _candidate_method(
            slug="mixedlm",
            name="Mixed Linear Model",
            description="Linear mixed-effects model with group-specific random structure.",
            engine="statsmodels",
            paper_contract=_paper_output_contract(
                ["MixedLM coefficient table", "Random-effect variance table"],
                ["Fitted vs actual grouped plot"],
                diagnostics=["Random-effect summary table"],
            ),
            variant_schema=COMMON_REGRESSION_SCHEMA,
        ),
    ],
)

_append_methods(
    "asset_pricing",
    [
        _candidate_method(
            slug="traded_factor_model",
            name="Traded Factor Model",
            description="Linear factor model for traded factors with alpha and risk-premia diagnostics.",
            engine="linearmodels",
            paper_contract=_paper_output_contract(
                ["Risk premia table", "Alpha table", "Beta loading table"],
                ["Factor pricing summary plot"],
                diagnostics=["J-test or pricing-error summary"],
            ),
            variant_schema=COMMON_REGRESSION_SCHEMA,
        ),
        _candidate_method(
            slug="linear_factor_gmm",
            name="Linear Factor GMM",
            description="GMM-based linear factor pricing model for non-traded or estimated factors.",
            engine="linearmodels",
            paper_contract=_paper_output_contract(
                ["Risk premia table", "Moment condition table", "Factor loading table"],
                ["Pricing error comparison plot"],
                diagnostics=["GMM objective and over-identification table"],
            ),
            variant_schema=COMMON_REGRESSION_SCHEMA,
        ),
    ],
)

_append_methods(
    "portfolio_allocation",
    [
        _candidate_method(
            slug="cdar_frontier",
            name="CDaR Frontier",
            description="Portfolio optimization using Conditional Drawdown at Risk as the risk objective.",
            engine="pypfopt",
            paper_contract=_paper_output_contract(
                ["Weight table", "Drawdown risk table", "Allocation summary table"],
                ["Drawdown frontier plot", "Weight allocation plot"],
                diagnostics=["Constraint audit table"],
            ),
            variant_schema=PORTFOLIO_SCHEMA,
        ),
    ],
)

_append_methods(
    "quant_research",
    [
        _candidate_method(
            slug="quant_catboost",
            name="Quant CatBoost",
            description="Gradient-boosted tree alpha model using CatBoost with cross-sectional prediction diagnostics.",
            engine="catboost",
            paper_contract=_paper_output_contract(
                ["Prediction metric table", "Feature importance table", "IC summary table"],
                ["Feature importance plot", "Cumulative return plot", "Prediction spread plot"],
            ),
            variant_schema={"shared": ["feature_columns", "label_column", "split_date", "holding_period", "iterations", "depth", "learning_rate"]},
            async_only=True,
        ),
        _candidate_method(
            slug="position_analysis",
            name="Position Analysis",
            description="Qlib-style position and contribution diagnostics for an existing prediction or backtest output.",
            engine="qlib",
            paper_contract=_paper_output_contract(
                ["Position analysis table", "Turnover table", "Contribution table"],
                ["Position concentration plot", "Turnover path plot", "Contribution breakdown plot"],
            ),
            variant_schema={"shared": ["prediction_asset_id", "position_weight_column", "date_column", "instrument_column"]},
            async_only=True,
        ),
    ],
)
