"""
Pipeline Integration Test
Simulates 5 sessions for a single user:
  Sessions 1-3: build the baseline (normal behavior)
  Session 4:    normal session, should score low risk
  Session 5:    anomalous session, should score high risk

Run from the project root:
    python -m tests.test_pipeline
"""

import json
import os
import random
import sys

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from config import ENV_PATH

load_dotenv(ENV_PATH)

from backend.feature_extractor import extract_features
from backend.baseline_manager import get_baseline, update_baseline, BASELINES_DIR
from backend.deviation_scorer import score_deviation, map_to_classifier_format
from backend.classifier import classify_session

TEST_USER = "test_user_pipeline"


def generate_normal_session(seed: int) -> dict:
    """Generate a realistic normal browsing session."""
    rng = random.Random(seed)
    base_t = 0

    mouse = []
    x, y = 500, 400
    for _ in range(50):
        base_t += rng.randint(30, 80)
        x += rng.randint(-20, 20)
        y += rng.randint(-15, 15)
        mouse.append({"x": max(0, x), "y": max(0, y), "t": base_t})

    scrolls = []
    for _ in range(10):
        base_t += rng.randint(500, 2000)
        scrolls.append({"delta": rng.randint(40, 120), "t": base_t})

    clicks = []
    for _ in range(8):
        base_t += rng.randint(1000, 4000)
        clicks.append({"x": rng.randint(100, 800), "y": rng.randint(100, 600), "t": base_t})

    keystrokes = []
    for _ in range(20):
        base_t += rng.randint(100, 300)
        hold = rng.randint(60, 120)
        keystrokes.append({
            "key": rng.choice("abcdefghijklmnop"),
            "down": base_t,
            "up": base_t + hold,
        })
        base_t += hold

    return {
        "user_id": TEST_USER,
        "mouse_movement": mouse,
        "scroll_events": scrolls,
        "clicks": clicks,
        "keystrokes": keystrokes,
    }


def generate_anomalous_session() -> dict:
    """Generate a clearly anomalous session."""
    rng = random.Random(999)
    base_t = 0

    mouse = []
    for _ in range(50):
        base_t += rng.randint(5, 15)
        mouse.append({"x": rng.randint(0, 1920), "y": rng.randint(0, 1080), "t": base_t})

    scrolls = []
    for _ in range(40):
        base_t += rng.randint(50, 200)
        scrolls.append({"delta": rng.randint(500, 2000), "t": base_t})

    clicks = []
    for _ in range(30):
        base_t += rng.randint(50, 200)
        clicks.append({"x": rng.randint(0, 1920), "y": rng.randint(0, 1080), "t": base_t})

    keystrokes = []
    for _ in range(60):
        base_t += rng.randint(5, 20)
        keystrokes.append({
            "key": rng.choice("qwertyuiop"),
            "down": base_t,
            "up": base_t + rng.randint(5, 15),
        })
        base_t += 10

    return {
        "user_id": TEST_USER,
        "mouse_movement": mouse,
        "scroll_events": scrolls,
        "clicks": clicks,
        "keystrokes": keystrokes,
    }


def run_session(session_num: int, raw_session: dict) -> dict | None:
    user_id = raw_session["user_id"]
    features = extract_features(raw_session)
    update_baseline(user_id, features)

    baseline = get_baseline(user_id)
    if baseline is None:
        print(f"  Session {session_num}: Baseline learning ({session_num}/3 sessions collected)")
        return None

    raw_scores = score_deviation(features, baseline)
    deviation_scores = map_to_classifier_format(raw_scores)
    print(f"  Deviation scores: {json.dumps(deviation_scores, indent=4)}")

    verdict = classify_session(deviation_scores)
    return {
        "user_id": user_id,
        "risk_level": verdict["risk_level"],
        "confidence": verdict["confidence"],
        "reason": verdict["reason"],
    }


def main():
    test_baseline_path = os.path.join(BASELINES_DIR, f"{TEST_USER}.json")
    if os.path.exists(test_baseline_path):
        os.remove(test_baseline_path)

    print("=" * 65)
    print("BEHAVIORAL PIPELINE INTEGRATION TEST")
    print("=" * 65)

    print("\n--- Phase 1: Baseline Learning (Sessions 1-3) ---")
    for i in range(1, 4):
        session = generate_normal_session(seed=i)
        run_session(i, session)

    print("\n--- Phase 2: Normal Session (Session 4) ---")
    normal_session = generate_normal_session(seed=42)
    result_normal = run_session(4, normal_session)
    if result_normal:
        print(f"\n  VERDICT: {json.dumps(result_normal, indent=4)}")

    print("\n--- Phase 3: Anomalous Session (Session 5) ---")
    anomalous_session = generate_anomalous_session()
    result_anomalous = run_session(5, anomalous_session)
    if result_anomalous:
        print(f"\n  VERDICT: {json.dumps(result_anomalous, indent=4)}")

    print("\n" + "=" * 65)

    if os.path.exists(test_baseline_path):
        os.remove(test_baseline_path)
        print("Test baseline cleaned up.")


if __name__ == "__main__":
    main()
