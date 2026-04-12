"""
Deviation Scorer
Compares a session's extracted features against the user's stored baseline
using z-score normalization, clamped to the 0.0-1.0 range.
"""

import math
import os

# z-score at which the output is clamped to 1.0
# Lower MAX_Z = more sensitive (smaller deviations score higher)
_SENSITIVITY_MAX_Z = {
    "low":    4.0,
    "medium": 3.0,
    "high":   2.0,
    "max":    1.5,
}


def _get_max_z():
    sensitivity = os.environ.get("BSM_SENSITIVITY", "medium")
    return _SENSITIVITY_MAX_Z.get(sensitivity, 3.0)


def score_deviation(features: dict, baseline: dict) -> dict:
    """Produce a 0.0-1.0 deviation score for each feature.

    Uses |z-score| / MAX_Z, clamped to [0, 1].
    If a feature's baseline variance is near zero, any deviation is treated
    as maximally anomalous; no deviation is treated as 0.

    Args:
        features: Current session's extracted feature values.
        baseline: Stored baseline with 'means' and 'variances' dicts.

    Returns:
        Dict mapping each feature to a float in [0.0, 1.0].
    """
    means = baseline.get("means", {})
    variances = baseline.get("variances", {})

    scores = {}
    for key, value in features.items():
        mean = means.get(key, value)
        var = variances.get(key, 0.0)
        std = math.sqrt(var) if var > 0 else 0.0

        if std < 1e-9:
            # Variance essentially zero: any difference is anomalous
            scores[key] = 1.0 if abs(value - mean) > 1e-9 else 0.0
        else:
            z = abs(value - mean) / std
            scores[key] = min(z / _get_max_z(), 1.0)

    return scores


def map_to_classifier_format(raw_scores: dict) -> dict:
    """Collapse granular feature scores into the 5-field format
    expected by classify_session().

    Mapping:
        mouse_variance     <- max(mouse_avg_speed, mouse_speed_variance)
        scroll_delta       <- max(scroll_avg_delta, scroll_events_per_min)
        click_frequency    <- max(clicks_per_min, click_avg_interval)
        keystroke_drift    <- max(key_avg_hold, key_avg_interval)
        session_duration_anomaly <- mean of all scores (general anomaly proxy)
    """
    def _max(*keys):
        vals = [raw_scores.get(k, 0.0) for k in keys]
        return max(vals) if vals else 0.0

    mapped = {
        "mouse_variance": _max("mouse_avg_speed", "mouse_speed_variance"),
        "scroll_delta": _max("scroll_avg_delta", "scroll_events_per_min"),
        "click_frequency": _max("clicks_per_min", "click_avg_interval"),
        "keystroke_drift": _max("key_avg_hold", "key_avg_interval"),
        "session_duration_anomaly": (
            sum(raw_scores.values()) / len(raw_scores) if raw_scores else 0.0
        ),
    }
    return mapped
