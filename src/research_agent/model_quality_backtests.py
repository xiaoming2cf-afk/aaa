from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.optimize import minimize
from statsmodels.tsa.arima.model import ARIMA

from .model_engine_causal import _fit_simplex_synthetic_weights


def _record(name: str, metric: float, threshold: float, *, direction: str = "max") -> dict[str, Any]:
    if direction == "min":
        passed = metric >= threshold
    else:
        passed = metric <= threshold
    return {
        "name": name,
        "metric": round(float(metric), 6),
        "threshold": round(float(threshold), 6),
        "direction": direction,
        "passed": bool(passed),
    }


def _ols_backtest(seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=220)
    y = 1.0 + 2.0 * x + rng.normal(scale=0.05, size=len(x))
    fitted = sm.OLS(y, sm.add_constant(pd.DataFrame({"x": x}))).fit()
    error = abs(float(fitted.params["x"]) - 2.0)
    return _record("ols_truth_coefficient_error", error, 0.08)


def _did_backtest(seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, float]] = []
    effect = 1.5
    for unit in range(80):
        treated = 1.0 if unit >= 40 else 0.0
        unit_effect = rng.normal(scale=0.1)
        for period in range(4):
            post = 1.0 if period >= 2 else 0.0
            y = 0.4 + unit_effect + 0.2 * post + 0.1 * treated + effect * treated * post + rng.normal(scale=0.04)
            rows.append({"y": y, "treated": treated, "post": post, "did": treated * post})
    frame = pd.DataFrame(rows)
    fitted = sm.OLS(frame["y"], sm.add_constant(frame[["treated", "post", "did"]])).fit()
    error = abs(float(fitted.params["did"]) - effect)
    return _record("did_truth_effect_error", error, 0.12)


def _rdd_backtest(seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    running = np.linspace(-1.0, 1.0, 260)
    treatment = (running >= 0.0).astype(float)
    effect = 1.2
    y = 0.3 + 0.8 * running + effect * treatment + rng.normal(scale=0.04, size=len(running))
    frame = pd.DataFrame({"y": y, "running": running, "treatment": treatment})
    local = frame.loc[frame["running"].abs() <= 0.45]
    fitted = sm.OLS(local["y"], sm.add_constant(local[["running", "treatment"]])).fit()
    error = abs(float(fitted.params["treatment"]) - effect)
    return _record("rdd_truth_discontinuity_error", error, 0.12)


def _iv_backtest(seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    z = rng.normal(size=260)
    confounder = rng.normal(size=len(z))
    x = 0.9 * z + 0.5 * confounder + rng.normal(scale=0.08, size=len(z))
    y = 0.8 * x + 0.6 * confounder + rng.normal(scale=0.05, size=len(z))
    first_stage = sm.OLS(x, sm.add_constant(pd.DataFrame({"z": z}))).fit()
    x_hat = first_stage.predict(sm.add_constant(pd.DataFrame({"z": z})))
    second_stage = sm.OLS(y, sm.add_constant(pd.DataFrame({"x_hat": x_hat}))).fit()
    error = abs(float(second_stage.params["x_hat"]) - 0.8)
    return _record("iv_truth_effect_error", error, 0.16)


def _bayesian_backtest(seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=180)
    y = -0.3 + 1.4 * x + rng.normal(scale=0.08, size=len(x))
    design = np.column_stack([np.ones(len(x)), x])
    prior_precision = np.eye(2) * 0.01
    noise_precision = 1.0 / (0.08**2)
    posterior_precision = prior_precision + noise_precision * (design.T @ design)
    posterior_mean = np.linalg.solve(posterior_precision, noise_precision * design.T @ y)
    error = abs(float(posterior_mean[1]) - 1.4)
    return _record("bayesian_conjugate_posterior_mean_error", error, 0.1)


def _synthetic_control_backtest(seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    donors = rng.normal(size=(36, 4)).cumsum(axis=0)
    truth_weights = np.array([0.5, 0.3, 0.2, 0.0])
    treated = donors @ truth_weights + rng.normal(scale=0.01, size=36)
    treated[24:] += 1.0
    weights, audit = _fit_simplex_synthetic_weights(donors[:24], treated[:24])
    pre_gap = treated[:24] - donors[:24] @ weights
    error = float(np.sqrt(np.mean(np.square(pre_gap))))
    weight_sum_error = abs(float(audit["weight_sum"]) - 1.0)
    passed = error <= 0.08 and weight_sum_error <= 1e-6 and bool(audit["success"])
    return {
        "name": "synthetic_control_simplex_pre_rmse",
        "metric": round(error, 6),
        "threshold": 0.08,
        "direction": "max",
        "weight_sum_error": round(weight_sum_error, 9),
        "passed": passed,
    }


def _portfolio_backtest(seed: int) -> dict[str, Any]:
    _ = seed
    cov = np.array(
        [
            [0.0025, 0.0002, 0.0001],
            [0.0002, 0.0004, 0.0001],
            [0.0001, 0.0001, 0.0064],
        ],
        dtype=float,
    )

    def objective(weights: np.ndarray) -> float:
        return float(weights @ cov @ weights)

    result = minimize(
        objective,
        np.repeat(1 / 3, 3),
        method="SLSQP",
        bounds=[(0.0, 1.0)] * 3,
        constraints=[{"type": "eq", "fun": lambda weights: float(np.sum(weights) - 1.0)}],
    )
    if not result.success:
        return _record("portfolio_min_variance_solver_failed", 1.0, 0.0)
    weights = np.asarray(result.x)
    variance = objective(weights)
    equal_variance = objective(np.repeat(1 / 3, 3))
    relative_improvement = (equal_variance - variance) / max(equal_variance, 1e-12)
    return _record("portfolio_min_variance_relative_improvement", relative_improvement, 0.05, direction="min")


def _time_series_backtest(seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    phi = 0.62
    series = [0.0]
    for _ in range(180):
        series.append(phi * series[-1] + rng.normal(scale=0.05))
    fitted = ARIMA(series[1:], order=(1, 0, 0)).fit()
    estimate = float(fitted.arparams[0])
    error = abs(estimate - phi)
    if math.isnan(error):
        error = 1.0
    return _record("time_series_ar1_phi_error", error, 0.12)


def run_synthetic_truth_backtests(*, seed: int = 20260424) -> dict[str, Any]:
    checks = [
        _ols_backtest(seed + 1),
        _did_backtest(seed + 2),
        _rdd_backtest(seed + 3),
        _iv_backtest(seed + 4),
        _bayesian_backtest(seed + 5),
        _synthetic_control_backtest(seed + 6),
        _portfolio_backtest(seed + 7),
        _time_series_backtest(seed + 8),
    ]
    return {
        "passed": all(bool(item["passed"]) for item in checks),
        "checks": checks,
    }
