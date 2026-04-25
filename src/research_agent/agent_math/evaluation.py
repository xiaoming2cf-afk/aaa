from __future__ import annotations

from typing import Any


def brier_score(predictions: list[float], labels: list[bool]) -> float:
    if len(predictions) != len(labels) or not predictions:
        raise ValueError("brier_score requires equally sized non-empty predictions and labels.")
    return sum((float(predictions[idx]) - (1.0 if labels[idx] else 0.0)) ** 2 for idx in range(len(predictions))) / len(predictions)


def expected_calibration_error(predictions: list[float], labels: list[bool], *, bins: int = 10) -> float:
    if len(predictions) != len(labels) or not predictions:
        raise ValueError("expected_calibration_error requires equally sized non-empty predictions and labels.")
    bin_count = max(1, int(bins))
    total = len(predictions)
    ece = 0.0
    for bin_index in range(bin_count):
        lower = bin_index / bin_count
        upper = (bin_index + 1) / bin_count
        if bin_index == bin_count - 1:
            in_bin = [
                idx
                for idx, prediction in enumerate(predictions)
                if lower <= float(prediction) <= upper
            ]
        else:
            in_bin = [
                idx
                for idx, prediction in enumerate(predictions)
                if lower <= float(prediction) < upper
            ]
        if not in_bin:
            continue
        confidence = sum(float(predictions[idx]) for idx in in_bin) / len(in_bin)
        accuracy = sum(1.0 if labels[idx] else 0.0 for idx in in_bin) / len(in_bin)
        ece += (len(in_bin) / total) * abs(confidence - accuracy)
    return ece


def delivery_classification_metrics(predictions: list[float], labels: list[bool], *, threshold: float) -> dict[str, float]:
    if len(predictions) != len(labels) or not predictions:
        raise ValueError("delivery_classification_metrics requires equally sized non-empty predictions and labels.")
    predicted_labels = [float(value) >= float(threshold) for value in predictions]
    negative_count = sum(1 for label in labels if not label)
    positive_count = sum(1 for label in labels if label)
    false_publish = sum(1 for idx, predicted in enumerate(predicted_labels) if predicted and not labels[idx])
    false_block = sum(1 for idx, predicted in enumerate(predicted_labels) if not predicted and labels[idx])
    return {
        "brier_score": brier_score(predictions, labels),
        "expected_calibration_error": expected_calibration_error(predictions, labels),
        "false_publish_rate": false_publish / max(1, negative_count),
        "false_block_rate": false_block / max(1, positive_count),
        "calibration_sample_count": float(len(predictions)),
    }


def top_k_recall(cases: list[dict[str, Any]], *, key: str, k: int) -> float:
    if not cases:
        raise ValueError("top_k_recall requires at least one case.")
    hits = 0
    for case in cases:
        expected_ids = {str(item) for item in case.get("expected_ids", [])}
        ranked_ids = [str(item) for item in case.get(key, [])[: max(1, int(k))]]
        if expected_ids and expected_ids.intersection(ranked_ids):
            hits += 1
    return hits / len(cases)


def binary_rate(rows: list[dict[str, Any]], *, numerator_key: str, denominator_key: str | None = None) -> float:
    if not rows:
        raise ValueError("binary_rate requires at least one row.")
    if denominator_key:
        denominator_rows = [row for row in rows if bool(row.get(denominator_key))]
    else:
        denominator_rows = rows
    if not denominator_rows:
        return 0.0
    return sum(1 for row in denominator_rows if bool(row.get(numerator_key))) / len(denominator_rows)
