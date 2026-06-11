"""
Live API integration test:
Submit synthetic sessions to /session and verify the full pipeline
(baseline learning -> deviation scoring -> classification) works through the HTTP layer.
"""
import json
import random
import urllib.request
import sys

BASE = "http://127.0.0.1:5050"
USER = "api_test_user"


def normal_session(seed):
    rng = random.Random(seed)
    t = 0
    mouse, scrolls, clicks, keystrokes = [], [], [], []
    x, y = 500, 400
    for _ in range(50):
        t += rng.randint(30, 80)
        x += rng.randint(-20, 20); y += rng.randint(-15, 15)
        mouse.append({"x": max(0, x), "y": max(0, y), "t": t})
    for _ in range(10):
        t += rng.randint(500, 2000)
        scrolls.append({"delta": rng.randint(40, 120), "t": t})
    for _ in range(8):
        t += rng.randint(1000, 4000)
        clicks.append({"x": rng.randint(100, 800), "y": rng.randint(100, 600), "t": t})
    for _ in range(20):
        t += rng.randint(100, 300)
        hold = rng.randint(60, 120)
        keystrokes.append({"key": rng.choice("abcdef"), "down": t, "up": t + hold})
        t += hold
    return {"user_id": USER, "mouse_movement": mouse, "scroll_events": scrolls, "clicks": clicks, "keystrokes": keystrokes}


def anomalous_session():
    rng = random.Random(999)
    t = 0
    mouse, scrolls, clicks, keystrokes = [], [], [], []
    for _ in range(50):
        t += rng.randint(5, 15)
        mouse.append({"x": rng.randint(0, 1920), "y": rng.randint(0, 1080), "t": t})
    for _ in range(40):
        t += rng.randint(50, 200)
        scrolls.append({"delta": rng.randint(500, 2000), "t": t})
    for _ in range(30):
        t += rng.randint(50, 200)
        clicks.append({"x": rng.randint(0, 1920), "y": rng.randint(0, 1080), "t": t})
    for _ in range(60):
        t += rng.randint(5, 20)
        keystrokes.append({"key": rng.choice("qwerty"), "down": t, "up": t + rng.randint(5, 15)})
        t += 10
    return {"user_id": USER, "mouse_movement": mouse, "scroll_events": scrolls, "clicks": clicks, "keystrokes": keystrokes}


def post(path, body):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def reset_user():
    """Clear baseline + counters by wiping the baseline file directly."""
    import os
    import shutil
    base_dir = os.path.dirname(os.path.abspath(__file__))
    targets = [
        os.path.join(base_dir, "data", "baselines", f"{USER}.json"),
        os.path.join(base_dir, "data", "history", f"{USER}.json"),
        os.path.join(base_dir, "data", "counters", f"{USER}.json"),
    ]
    for p in targets:
        if os.path.exists(p):
            os.remove(p)


def main():
    reset_user()
    print("=" * 60)
    print("LIVE API PIPELINE TEST")
    print("=" * 60)

    for i in range(1, 4):
        result = post("/session", normal_session(seed=i))
        print(f"  Session {i} (baseline): {result.get('status', result.get('risk_level'))}")

    print()
    result = post("/session", normal_session(seed=42))
    print(f"  Session 4 (normal expected LOW): risk={result.get('risk_level')} confidence={result.get('confidence')}")
    assert result.get("risk_level") in ("low", "medium"), f"Unexpected risk for normal session: {result}"

    print()
    result = post("/session", anomalous_session())
    print(f"  Session 5 (anomalous expected HIGH or MEDIUM): risk={result.get('risk_level')} confidence={result.get('confidence')}")
    assert result.get("risk_level") in ("medium", "high"), f"Anomalous session did not flag: {result}"

    print()
    counters = get(f"/api/counters?user_id={USER}")
    history = get(f"/api/history?user_id={USER}")
    print(f"  Counters: {counters}")
    print(f"  History entries: {len(history)}")

    print()
    print("[PASS] All assertions held. Pipeline working through HTTP layer.")
    reset_user()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[FAIL] {type(e).__name__}: {e}")
        sys.exit(1)
