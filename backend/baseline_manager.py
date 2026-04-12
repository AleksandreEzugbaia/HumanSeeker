"""
Baseline Manager
Stores and updates per-user behavioral baselines as JSON files.
A baseline is created from the first BASELINE_WINDOW sessions,
then updated incrementally via rolling average.
"""

import json
import os
import sys
import statistics

# Use config path if available (works in both dev and frozen .exe)
try:
    from config import BASELINES_DIR
except ImportError:
    BASELINES_DIR = os.path.join(os.path.dirname(__file__), "baselines")
BASELINE_WINDOW = 3  # number of initial sessions before baseline is "ready"


def _baseline_path(user_id: str) -> str:
    return os.path.join(BASELINES_DIR, f"{user_id}.json")


def get_baseline(user_id: str) -> dict | None:
    """Load the stored baseline for a user, or None if not enough data yet."""
    path = _baseline_path(user_id)
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        data = json.load(f)
    # Baseline is only usable after BASELINE_WINDOW sessions
    if data.get("session_count", 0) < BASELINE_WINDOW:
        return None
    return data


def _load_raw(user_id: str) -> dict:
    """Load the raw baseline file (even if not yet ready)."""
    path = _baseline_path(user_id)
    if not os.path.exists(path):
        return {"session_count": 0, "means": {}, "variances": {}, "history": []}
    with open(path, "r") as f:
        return json.load(f)


def _save_raw(user_id: str, data: dict) -> None:
    os.makedirs(BASELINES_DIR, exist_ok=True)
    with open(_baseline_path(user_id), "w") as f:
        json.dump(data, f, indent=2)


def update_baseline(user_id: str, features: dict) -> None:
    """Add a session's features to the user's baseline.

    - During the first BASELINE_WINDOW sessions: accumulates raw history.
    - Once the window is reached: computes initial mean + variance.
    - After that: incrementally updates via exponential moving average.
    """
    data = _load_raw(user_id)
    data["session_count"] = data.get("session_count", 0) + 1

    if data["session_count"] <= BASELINE_WINDOW:
        # Accumulate raw history
        data.setdefault("history", []).append(features)

        if data["session_count"] == BASELINE_WINDOW:
            # Compute initial baseline from collected sessions
            all_keys = set()
            for h in data["history"]:
                all_keys.update(h.keys())

            means = {}
            variances = {}
            for key in all_keys:
                values = [h.get(key, 0.0) for h in data["history"]]
                means[key] = statistics.mean(values)
                variances[key] = statistics.variance(values) if len(values) >= 2 else 0.0
            data["means"] = means
            data["variances"] = variances
            # Clear history to save space
            data["history"] = []
    else:
        # Incremental update with exponential moving average (alpha = 0.2)
        alpha = 0.2
        for key, value in features.items():
            old_mean = data["means"].get(key, value)
            new_mean = old_mean * (1 - alpha) + value * alpha
            # Update variance incrementally
            old_var = data["variances"].get(key, 0.0)
            new_var = old_var * (1 - alpha) + alpha * (value - old_mean) ** 2
            data["means"][key] = new_mean
            data["variances"][key] = new_var

    _save_raw(user_id, data)
