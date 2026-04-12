"""
Session Classifier: local heuristic engine using weighted multi-signal scoring.

All classification is done locally using configurable sensitivity thresholds
and a weighted scoring system across multiple behavioral metrics.
"""

import os

# ---------------------------------------------------------------------------
# Sensitivity configuration (set via /api/sensitivity endpoint)
# ---------------------------------------------------------------------------
_SENSITIVITY_THRESHOLDS = {
    "low":    {"safe": 0.50, "medium": 0.65, "high": 0.80},
    "medium": {"safe": 0.30, "medium": 0.50, "high": 0.70},
    "high":   {"safe": 0.15, "medium": 0.35, "high": 0.55},
    "max":    {"safe": 0.05, "medium": 0.20, "high": 0.40},
}

# How much each metric matters in the weighted score
_METRIC_WEIGHTS = {
    "mouse_variance":          0.25,
    "scroll_delta":            0.10,
    "click_frequency":         0.20,
    "keystroke_drift":         0.30,
    "session_duration_anomaly": 0.15,
}

# Human-readable labels for the reason string
_METRIC_LABELS = {
    "mouse_variance":          "mouse movement",
    "scroll_delta":            "scroll behavior",
    "click_frequency":         "click patterns",
    "keystroke_drift":         "keystroke timing",
    "session_duration_anomaly": "session duration",
}


def _get_thresholds():
    sensitivity = os.environ.get("BSM_SENSITIVITY", "medium")
    return _SENSITIVITY_THRESHOLDS.get(sensitivity, _SENSITIVITY_THRESHOLDS["medium"])


def _local_classify(deviation_scores: dict) -> dict:
    """Classify using weighted multi-signal heuristic scoring."""

    thresholds = _get_thresholds()

    # Weighted average score
    total_weight = 0.0
    weighted_sum = 0.0
    for metric, score in deviation_scores.items():
        w = _METRIC_WEIGHTS.get(metric, 0.1)
        weighted_sum += score * w
        total_weight += w

    avg_score = weighted_sum / total_weight if total_weight > 0 else 0.0

    # Find the top anomalous signals for the reason string
    sorted_metrics = sorted(deviation_scores.items(), key=lambda x: x[1], reverse=True)
    flagged = [(k, v) for k, v in sorted_metrics if v >= thresholds["safe"]]

    # Determine risk level
    if avg_score < thresholds["safe"]:
        level = "low"
    elif avg_score < thresholds["medium"]:
        level = "medium"
    elif avg_score < thresholds["high"]:
        level = "medium"
    else:
        level = "high"

    # Boost to high if any single metric is extremely anomalous (>0.85)
    max_metric = sorted_metrics[0] if sorted_metrics else ("", 0)
    if max_metric[1] >= 0.85 and level != "high":
        level = "high"

    # Confidence: higher when signals agree, lower when they're mixed
    scores = list(deviation_scores.values())
    if scores:
        spread = max(scores) - min(scores)
        # Tight cluster = high confidence, wide spread = lower
        base_conf = min(avg_score + 0.3, 0.95)
        confidence = round(base_conf - (spread * 0.15), 2)
        confidence = max(0.45, min(confidence, 0.99))
    else:
        confidence = 0.5

    # Build reason
    if level == "low":
        reason = "Session behavior is within normal baseline parameters."
    elif not flagged:
        reason = f"Mild overall deviation detected (score: {avg_score:.2f})."
    else:
        top_names = [_METRIC_LABELS.get(k, k) for k, v in flagged[:3]]
        if len(top_names) == 1:
            signal_str = top_names[0]
        elif len(top_names) == 2:
            signal_str = f"{top_names[0]} and {top_names[1]}"
        else:
            signal_str = f"{top_names[0]}, {top_names[1]}, and {top_names[2]}"

        if level == "high":
            reason = f"Significant anomaly detected in {signal_str}. Behavior deviates strongly from established baseline (score: {avg_score:.2f})."
        else:
            reason = f"Moderate deviation in {signal_str}. Behavior differs from baseline but not conclusively anomalous (score: {avg_score:.2f})."

    return {
        "risk_level": level,
        "confidence": confidence,
        "reason": reason,
    }


def classify_session(deviation_scores: dict) -> dict:
    """Classify a user session based on behavioral deviation scores.

    Uses the local heuristic engine with weighted multi-signal scoring.

    Args:
        deviation_scores: Dict of metric names to float scores (0.0-1.0).

    Returns:
        Dict with risk_level, confidence, and reason.
    """
    return _local_classify(deviation_scores)
