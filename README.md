# HumanSeeker

[![CI](https://github.com/AleksandreEzugbaia/HumanSeeker/actions/workflows/ci.yml/badge.svg)](https://github.com/AleksandreEzugbaia/HumanSeeker/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0-brightgreen.svg)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

**Behavioral biometrics for account takeover detection.** A desktop application that detects unauthorized access by analyzing real-time behavioral signals: mouse dynamics, keystroke timing, click cadence, and scroll patterns.

> **Premise: valid credentials are not enough to confirm identity.** Even with the right password and a valid session token, an attacker does not type, move the mouse, click, or scroll the way the real user does. HumanSeeker treats behavioral signature as a continuous soft factor that works *after* the front-door check has passed.

---

## Why this matters in 2026

- The Carnival Corporation breach (April 2026) — attackers got in via social engineering, used valid employee credentials, and had four days of internal access before detection. ~6 million customer records exposed.
- The Hasbro ransomware attack — weeks of operational downtime. Most modern ransomware starts with credential compromise, then has a dwell window of 10–21 days before encryption fires.
- MFA bypass via session theft is now standard practice in phishing kits.

In all three patterns the credentials were valid. The behavior was wrong. Behavioral biometrics is the detection layer that closes the dwell window.

---

## What HumanSeeker does

1. **Browser-side capture** (`frontend/tracker.js`) — records mouse velocity, keystroke timing (dwell + flight), click patterns, scroll behavior. No keystroke *content* is captured.
2. **Baseline learning** — first 3 sessions build a per-user behavioral profile using exponential moving averages.
3. **Z-score deviation scoring** — each new session compared against the baseline across 8 behavioral features.
4. **Heuristic classification** — weighted multi-signal engine outputs **Low / Medium / High** risk with confidence in [0, 1].
5. **Structured detection logging** — every classification appends a JSON event to `logs/detections.jsonl` (SIEM-ready).

---

## Screenshots

### Dashboard
![Dashboard](screenshots/dashboard.png)

### Settings
![Settings](screenshots/settings.png)

### Demo
![Demo](screenshots/demo.png)

---

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system architecture, data flow diagram, module responsibilities, and security design decisions.

```
Browser (tracker.js) --POST /session--> Flask (127.0.0.1) --> feature_extractor
                                                          --> baseline_manager (EMA)
                                                          --> deviation_scorer (z-score)
                                                          --> classifier (heuristic)
                                                          --> logs/detections.jsonl (SIEM)
```

---

## Security model

See [THREAT_MODEL.md](THREAT_MODEL.md) for the full threat model. Highlights:

- **Loopback only.** The Flask server binds to `127.0.0.1`. The app makes no outbound network calls. Air-gap deployable.
- **No keystroke content captured.** Only timing and a non-content key category. This is a deliberate privacy choice.
- **Hardened HTTP response headers.** Content-Security-Policy, X-Frame-Options: DENY, X-Content-Type-Options: nosniff, Referrer-Policy, Permissions-Policy, Cross-Origin-Opener-Policy.
- **Input validation on every API request.** Strict charset for `user_id`, length caps, list-size caps, type checks. Rejections are logged to `logs/security.jsonl`.
- **Per-user rate limiting.** 30 requests per 60 seconds, sliding window. Excess requests return HTTP 429 and are logged.
- **Structured detection event log.** SIEM-ready JSON Lines (`logs/detections.jsonl`) with ISO-8601 UTC timestamps. Drop-in for Splunk, Elastic, Datadog, or any log shipper.

See [SECURITY.md](SECURITY.md) for the responsible disclosure policy.

---

## API

| Method | Path | Purpose |
|---|---|---|
| GET  | `/api/health`         | Liveness probe. Returns `{"status":"ok"}`. |
| GET  | `/api/version`        | App + API + build metadata. |
| POST | `/session`            | Submit behavioral session, get risk classification. |
| GET  | `/latest`             | Most recent verdict for a user. |
| GET  | `/api/counters`       | Session counts by risk level for a user. |
| GET  | `/api/history`        | Verdict history for a user (last 200, newest first). |
| GET  | `/api/sensitivity`    | Read sensitivity settings. |
| POST | `/api/sensitivity`    | Update sensitivity settings (low/medium/high/max). |
| GET  | `/api/appearance`     | Read theme + accent. |
| POST | `/api/appearance`     | Update theme + accent. |
| GET  | `/api/demo-status`    | Whether the demo has been completed. |
| POST | `/api/demo-status`    | Mark the demo as completed. |
| GET  | `/api/edition`        | Read edition/tier setting. |
| POST | `/api/edition`        | Update edition/tier setting. |

---

## Project Structure

```
HumanSeeker/
  main.py                          # Entry point: Flask thread + pywebview window
  config.py                        # Path resolution (dev vs frozen .exe)
  make_icon.py                     # Multi-resolution icon generator
  requirements.txt
  HumanSeeker.spec                 # PyInstaller config

  backend/
    app.py                         # Flask app factory + routes
    classifier.py                  # Weighted multi-signal heuristic
    feature_extractor.py           # 8 behavioral features from raw session data
    baseline_manager.py            # Per-user EMA baseline (JSON storage)
    deviation_scorer.py            # Z-score normalization (sensitivity-aware)
    security.py                    # Headers, validation, rate limit, JSONL logging

  frontend/
    static/icon.ico, icon.png      # App icon
    index.html                     # Navigation shell
    dashboard.html                 # Live counters, verdicts, alert log
    demo.html                      # Calibration + anomaly testing
    edition.html                   # Plan/tier selection
    settings.html                  # Sensitivity + appearance
    tracker.js                     # Browser behavioral data capture

  tests/
    test_pipeline.py               # End-to-end pipeline integration test
    test_security.py               # Input validation, rate limit, logging tests

  logs/
    detections.jsonl               # SIEM-ready detection events
    security.jsonl                 # Validation rejections, rate-limit events

  .github/workflows/ci.yml         # CI: pytest + ruff + bandit

  THREAT_MODEL.md
  SECURITY.md
  ARCHITECTURE.md
  CHANGELOG.md
  LICENSE
  README.md
```

---

## Running from Source

```bash
pip install -r requirements.txt
pip install pywebview          # optional, for native window instead of browser
python main.py
```

The app will open in a native window (if `pywebview` is installed) or fall back to your default browser.

## Running tests

```bash
pip install pytest
pytest -v
```

## Building the Windows .exe

```bash
pip install pyinstaller
python make_icon.py            # only needed if you change the icon design
pyinstaller HumanSeeker.spec --noconfirm
```

The resulting `dist/HumanSeeker.exe` is a single-file Windows executable (~18 MB) with the icon embedded. No Python install required on the target machine.

---

## License

MIT. See [LICENSE](LICENSE).
