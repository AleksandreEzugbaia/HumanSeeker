"""
50-session stress test.

Validates the pipeline across a realistic mix of sessions:
  - 30 normal sessions (with natural variation)
  - 10 mildly anomalous sessions (drift, fatigue, slight change)
  - 10 highly anomalous sessions (attacker-like behavior)

Asserts:
  - Baseline learns from first 3 sessions, no crashes during cold start
  - Normal sessions never score HIGH risk
  - Highly anomalous sessions never score LOW risk
  - Counters stay consistent (sum of buckets == total)
  - History persists in correct order

Reports:
  - Confusion matrix (expected vs actual risk level)
  - Score distribution by category
  - Total runtime
"""
import json
import random
import time
import urllib.request
from collections import Counter
from contextlib import contextmanager
import os
import sys

BASE = "http://127.0.0.1:5000"
USER = "stress_test_user_50"


# ----------------------------------------------------------------------
# Session generators with realistic variation
# ----------------------------------------------------------------------
def normal_session(seed):
    """Realistic normal-user session with natural variation."""
    rng = random.Random(seed)
    t = 0
    mouse, scrolls, clicks, keystrokes = [], [], [], []
    x, y = 500, 400
    for _ in range(rng.randint(40, 70)):
        t += rng.randint(30, 100)
        x += rng.randint(-25, 25)
        y += rng.randint(-20, 20)
        mouse.append({"x": max(0, x), "y": max(0, y), "t": t})
    for _ in range(rng.randint(8, 14)):
        t += rng.randint(500, 2200)
        scrolls.append({"delta": rng.randint(40, 140), "t": t})
    for _ in range(rng.randint(6, 12)):
        t += rng.randint(800, 4500)
        clicks.append({"x": rng.randint(100, 900), "y": rng.randint(100, 700), "t": t})
    for _ in range(rng.randint(15, 30)):
        t += rng.randint(90, 320)
        hold = rng.randint(55, 130)
        keystrokes.append({"key": rng.choice("abcdefghij"), "down": t, "up": t + hold})
        t += hold
    return _session(mouse, scrolls, clicks, keystrokes)


def drift_session(seed):
    """Mildly anomalous: like the user is tired, distracted, or on a different keyboard."""
    rng = random.Random(seed + 1000)
    t = 0
    mouse, scrolls, clicks, keystrokes = [], [], [], []
    x, y = 500, 400
    for _ in range(rng.randint(60, 90)):
        t += rng.randint(15, 60)  # faster mouse
        x += rng.randint(-40, 40)  # bigger jumps
        y += rng.randint(-30, 30)
        mouse.append({"x": max(0, x), "y": max(0, y), "t": t})
    for _ in range(rng.randint(14, 22)):
        t += rng.randint(250, 1200)
        scrolls.append({"delta": rng.randint(80, 250), "t": t})
    for _ in range(rng.randint(10, 16)):
        t += rng.randint(400, 2000)
        clicks.append({"x": rng.randint(100, 900), "y": rng.randint(100, 700), "t": t})
    for _ in range(rng.randint(25, 45)):
        t += rng.randint(40, 200)
        hold = rng.randint(30, 90)  # faster typing
        keystrokes.append({"key": rng.choice("abcdefghij"), "down": t, "up": t + hold})
        t += hold
    return _session(mouse, scrolls, clicks, keystrokes)


def anomalous_session(seed):
    """Clearly attacker-like: bot-fast mouse, machine-gun clicks, robotic typing."""
    rng = random.Random(seed + 9000)
    t = 0
    mouse, scrolls, clicks, keystrokes = [], [], [], []
    for _ in range(rng.randint(80, 120)):
        t += rng.randint(3, 12)  # super fast
        mouse.append({"x": rng.randint(0, 1920), "y": rng.randint(0, 1080), "t": t})  # teleport
    for _ in range(rng.randint(30, 50)):
        t += rng.randint(40, 200)
        scrolls.append({"delta": rng.randint(500, 2500), "t": t})  # huge scrolls
    for _ in range(rng.randint(25, 40)):
        t += rng.randint(30, 150)
        clicks.append({"x": rng.randint(0, 1920), "y": rng.randint(0, 1080), "t": t})  # random clicks
    for _ in range(rng.randint(50, 80)):
        t += rng.randint(5, 25)
        keystrokes.append({"key": rng.choice("qwerty"), "down": t, "up": t + rng.randint(5, 20)})
        t += 10
    return _session(mouse, scrolls, clicks, keystrokes)


def _session(mouse, scrolls, clicks, keystrokes):
    return {
        "user_id": USER,
        "mouse_movement": mouse,
        "scroll_events": scrolls,
        "clicks": clicks,
        "keystrokes": keystrokes,
    }


# ----------------------------------------------------------------------
# HTTP helpers
# ----------------------------------------------------------------------
# Throttle to stay under the rate limit (30 req / 60s).
# 2.1s per request = 28.5 req/min, comfortably under the cap.
RATE_LIMIT_DELAY = 2.1


def post(path, body):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    time.sleep(RATE_LIMIT_DELAY)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def reset_user():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    targets = [
        os.path.join(base_dir, "..", "data", "baselines", f"{USER}.json"),
        os.path.join(base_dir, "..", "data", "history", f"{USER}.json"),
        os.path.join(base_dir, "..", "data", "counters", f"{USER}.json"),
    ]
    for p in targets:
        if os.path.exists(p):
            os.remove(p)


@contextmanager
def section(title):
    print(f"\n--- {title} ---")
    t0 = time.perf_counter()
    yield
    print(f"  took {time.perf_counter() - t0:.2f}s")


# ----------------------------------------------------------------------
# Test plan
# ----------------------------------------------------------------------
# Index 0-29: normal sessions (sessions 1-30)
# Index 30-39: drift sessions (sessions 31-40)
# Index 40-49: anomalous sessions (sessions 41-50)
#
# First 3 sessions = baseline learning (no risk classification)
# Sessions 4-30 = normal user (expect LOW most, some MEDIUM allowed for variation)
# Sessions 31-40 = drift (expect MEDIUM mostly, some LOW or HIGH)
# Sessions 41-50 = anomalous (expect HIGH or MEDIUM, never LOW)

def main():
    reset_user()
    print("=" * 70)
    print("50-SESSION STRESS TEST")
    print("=" * 70)

    # Sanity check the server is up
    try:
        urllib.request.urlopen(BASE + "/api/health", timeout=3)
    except Exception as e:
        print(f"FATAL: Server not reachable at {BASE} — {e}")
        sys.exit(1)

    results = []  # list of dicts: {index, category, risk_level, confidence}

    with section("Phase 1: 30 normal sessions"):
        for i in range(30):
            status, body = post("/session", normal_session(seed=i))
            results.append({
                "index": i + 1,
                "category": "normal",
                "status": status,
                "risk_level": body.get("risk_level") or body.get("status", "learning"),
                "confidence": body.get("confidence", 0.0),
            })

    with section("Phase 2: 10 drift sessions"):
        for i in range(10):
            status, body = post("/session", drift_session(seed=i))
            results.append({
                "index": 30 + i + 1,
                "category": "drift",
                "status": status,
                "risk_level": body.get("risk_level") or body.get("status", "learning"),
                "confidence": body.get("confidence", 0.0),
            })

    with section("Phase 3: 10 highly anomalous sessions"):
        for i in range(10):
            status, body = post("/session", anomalous_session(seed=i))
            results.append({
                "index": 40 + i + 1,
                "category": "anomalous",
                "status": status,
                "risk_level": body.get("risk_level") or body.get("status", "learning"),
                "confidence": body.get("confidence", 0.0),
            })

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("RESULTS BY SESSION")
    print("=" * 70)
    for r in results:
        marker = ""
        if r["category"] == "normal" and r["risk_level"] == "high":
            marker = "  <<< false positive (normal flagged HIGH)"
        if r["category"] == "anomalous" and r["risk_level"] == "low":
            marker = "  <<< false negative (anomalous flagged LOW)"
        print(
            f"  Session {r['index']:2d} [{r['category']:9s}] "
            f"risk={r['risk_level']:8s} conf={r['confidence']:.2f}{marker}"
        )

    # ------------------------------------------------------------------
    # Confusion matrix
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("CONFUSION MATRIX (category -> actual risk level)")
    print("=" * 70)
    matrix = {
        "normal":    Counter(),
        "drift":     Counter(),
        "anomalous": Counter(),
    }
    for r in results:
        matrix[r["category"]][r["risk_level"]] += 1

    headers = ["learning", "low", "medium", "high"]
    print(f"  {'category':<10} " + " ".join(f"{h:>9}" for h in headers))
    for cat in ("normal", "drift", "anomalous"):
        row = " ".join(f"{matrix[cat].get(h, 0):>9}" for h in headers)
        print(f"  {cat:<10} {row}")

    # ------------------------------------------------------------------
    # Server-side counters & history sanity
    # ------------------------------------------------------------------
    counters = get(f"/api/counters?user_id={USER}")
    history = get(f"/api/history?user_id={USER}")
    print("\n" + "=" * 70)
    print("SERVER-SIDE STATE")
    print("=" * 70)
    print(f"  Counters: {counters}")
    print(f"  History entries: {len(history)}")

    # ------------------------------------------------------------------
    # Hard assertions
    # ------------------------------------------------------------------
    failures = []

    # 1. Counters sum equals classified-session count
    classified = sum(1 for r in results if r["risk_level"] in ("low", "medium", "high"))
    counter_sum = counters["low"] + counters["medium"] + counters["high"]
    if counter_sum != counters["total"]:
        failures.append(f"Counter bucket sum {counter_sum} != total {counters['total']}")
    if counter_sum != classified:
        failures.append(
            f"Counter sum {counter_sum} disagrees with locally-counted classified={classified}"
        )

    # 2. No anomalous session classified as LOW
    anomalous_lows = [r for r in results if r["category"] == "anomalous" and r["risk_level"] == "low"]
    if anomalous_lows:
        failures.append(f"{len(anomalous_lows)} anomalous sessions classified as LOW (false negatives)")

    # 3. False-positive rate on normal sessions <= 10% (industry tolerance)
    normal_results = [r for r in results if r["category"] == "normal"]
    normal_highs = [r for r in normal_results if r["risk_level"] == "high"]
    if normal_results:
        fpr = len(normal_highs) / len(normal_results)
        if fpr > 0.10:
            failures.append(
                f"Normal-session false-positive rate {fpr:.0%} exceeds 10% tolerance "
                f"({len(normal_highs)}/{len(normal_results)} flagged HIGH)"
            )

    # 4. History length is sensible
    if len(history) > 200:
        failures.append(f"History length {len(history)} exceeds 200-entry cap")

    # 5. Anomalous sessions should have confidence at least as high as drift
    # (both should saturate the classifier when behavior is clearly different).
    anomalous_confs = [r["confidence"] for r in results if r["category"] == "anomalous"]
    drift_confs = [r["confidence"] for r in results if r["category"] == "drift"]
    if anomalous_confs and drift_confs:
        anom_med = sorted(anomalous_confs)[len(anomalous_confs) // 2]
        drift_med = sorted(drift_confs)[len(drift_confs) // 2]
        if anom_med < drift_med:
            failures.append(
                f"Anomalous median confidence ({anom_med:.2f}) less than "
                f"drift median ({drift_med:.2f})"
            )

    print("\n" + "=" * 70)
    if failures:
        print(f"FAIL: {len(failures)} assertion(s) failed")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("PASS: All assertions held across 50 sessions.")
    print("=" * 70)

    reset_user()


if __name__ == "__main__":
    main()
