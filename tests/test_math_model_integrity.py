from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research_agent.model_engine_bayesian import _bayes_settings
from research_agent.model_engine_causal import _fit_simplex_synthetic_weights, _require_binary_indicator
from research_agent.model_engine_quant import _strategy_curve
from research_agent.platform_core import _validate_binary_outcome_series
from scripts.compare_model_engines import _pick_winner


def test_binary_outcome_validation_rejects_threshold_coercion():
    with pytest.raises(ValueError, match="coercive thresholding"):
        _validate_binary_outcome_series(pd.Series([0, 1, 2]), column_name="defaulted")

    validated = _validate_binary_outcome_series(pd.Series(["yes", "no", "1", "0"]), column_name="defaulted")
    assert validated.tolist() == [1.0, 0.0, 1.0, 0.0]


def test_bayesian_default_is_nuts_and_advi_must_be_explicit():
    assert _bayes_settings({}) == (150, 150, 2, "nuts")
    assert _bayes_settings({"bayesian_inference_method": "advi"}) == (150, 150, 2, "advi_preview")
    with pytest.raises(ValueError, match="bayesian_inference_method"):
        _bayes_settings({"bayesian_inference_method": "fast"})


def test_synthetic_control_weights_are_simplex_constrained():
    x_pre = np.array([[1.0, 0.0], [0.8, 0.2], [0.6, 0.4], [0.4, 0.6]])
    y_pre = np.array([0.9, 0.74, 0.58, 0.42])

    weights, audit = _fit_simplex_synthetic_weights(x_pre, y_pre)

    assert np.isclose(weights.sum(), 1.0)
    assert np.all(weights >= 0.0)
    assert audit["optimizer"] == "scipy.optimize.minimize:SLSQP"
    assert audit["success"] is True


def test_causal_treatment_indicator_rejects_silent_rounding_or_missing_values():
    with pytest.raises(ValueError, match="silent rounding or clipping"):
        _require_binary_indicator(pd.Series([0, 1, 0.49]), column_name="treated")

    with pytest.raises(ValueError, match="missing or nonnumeric"):
        _require_binary_indicator(pd.Series([0, 1, None]), column_name="treated")

    validated = _require_binary_indicator(pd.Series([0.0, 1.0, 1]), column_name="treated")
    assert validated.tolist() == [0, 1, 1]


def test_quant_strategy_uses_lagged_signal_and_transaction_costs():
    frame = pd.DataFrame(
        {
            "prediction": [1.0, -1.0, -1.0],
            "actual": [0.10, 0.20, -0.10],
        }
    )

    strategy = _strategy_curve(frame, label="test", transaction_cost_bps=10.0)

    assert strategy["executed_signal"].tolist() == [0.0, 1.0, -1.0]
    assert strategy["strategy_return"].round(6).tolist() == [0.0, 0.199, 0.098]
    assert strategy["transaction_cost_bps"].tolist() == [10.0, 10.0, 10.0]


def test_model_engine_comparison_does_not_pick_candidate_on_speed_only():
    baseline = {
        "accuracy_score": 80.0,
        "completeness_score": 95.0,
        "stability_score": 100.0,
        "speed_score": 10.0,
    }
    candidate = {
        "accuracy_score": 80.0,
        "completeness_score": 95.0,
        "stability_score": 100.0,
        "speed_score": 100.0,
    }

    assert _pick_winner(baseline, candidate, "fast_engine") == "baseline"
