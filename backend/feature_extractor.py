"""
Feature Extraction Module
Reduces raw behavioral event arrays from Christian's frontend
into summary statistics suitable for baseline comparison.
"""

import math
import statistics


def extract_features(raw_session: dict) -> dict:
    """Convert raw browser events into numeric feature summaries.

    Args:
        raw_session: Dict with mouse_movement, scroll_events, clicks, keystrokes arrays
                     and an optional session duration hint.

    Returns:
        Dict of feature_name -> float summary statistics.
    """
    features = {}

    # --- Mouse movement: average speed and variance ---
    mouse = raw_session.get("mouse_movement", [])
    if len(mouse) >= 2:
        speeds = []
        for i in range(1, len(mouse)):
            dx = mouse[i]["x"] - mouse[i - 1]["x"]
            dy = mouse[i]["y"] - mouse[i - 1]["y"]
            dt = mouse[i]["t"] - mouse[i - 1]["t"]
            if dt > 0:
                distance = math.sqrt(dx ** 2 + dy ** 2)
                speeds.append(distance / dt)
        features["mouse_avg_speed"] = statistics.mean(speeds) if speeds else 0.0
        features["mouse_speed_variance"] = statistics.variance(speeds) if len(speeds) >= 2 else 0.0
    else:
        features["mouse_avg_speed"] = 0.0
        features["mouse_speed_variance"] = 0.0

    # --- Scroll: average delta and events per minute ---
    scrolls = raw_session.get("scroll_events", [])
    if scrolls:
        deltas = [abs(s["delta"]) for s in scrolls]
        features["scroll_avg_delta"] = statistics.mean(deltas)
        # Estimate session span from scroll timestamps
        time_span_ms = scrolls[-1]["t"] - scrolls[0]["t"] if len(scrolls) >= 2 else 60000
        time_span_min = max(time_span_ms / 60000, 0.01)  # avoid division by zero
        features["scroll_events_per_min"] = len(scrolls) / time_span_min
    else:
        features["scroll_avg_delta"] = 0.0
        features["scroll_events_per_min"] = 0.0

    # --- Clicks: per minute and average inter-click time ---
    clicks = raw_session.get("clicks", [])
    if clicks:
        timestamps = [c["t"] for c in clicks]
        time_span_ms = timestamps[-1] - timestamps[0] if len(timestamps) >= 2 else 60000
        time_span_min = max(time_span_ms / 60000, 0.01)
        features["clicks_per_min"] = len(clicks) / time_span_min

        if len(timestamps) >= 2:
            intervals = [timestamps[i] - timestamps[i - 1] for i in range(1, len(timestamps))]
            features["click_avg_interval"] = statistics.mean(intervals)
        else:
            features["click_avg_interval"] = 0.0
    else:
        features["clicks_per_min"] = 0.0
        features["click_avg_interval"] = 0.0

    # --- Keystrokes: avg hold duration and avg inter-key time ---
    keys = raw_session.get("keystrokes", [])
    if keys:
        hold_durations = [k["up"] - k["down"] for k in keys if k["up"] > k["down"]]
        features["key_avg_hold"] = statistics.mean(hold_durations) if hold_durations else 0.0

        if len(keys) >= 2:
            inter_key = [keys[i]["down"] - keys[i - 1]["up"] for i in range(1, len(keys))]
            # Filter out negative gaps (simultaneous keys)
            inter_key = [gap for gap in inter_key if gap > 0]
            features["key_avg_interval"] = statistics.mean(inter_key) if inter_key else 0.0
        else:
            features["key_avg_interval"] = 0.0
    else:
        features["key_avg_hold"] = 0.0
        features["key_avg_interval"] = 0.0

    return features
