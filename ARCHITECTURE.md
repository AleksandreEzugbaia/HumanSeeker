# HumanSeeker Architecture

## Overview

HumanSeeker is a desktop application that detects account takeover and session anomalies by analyzing user behavioral biometrics in real time. It is built as a self-contained Flask backend with a browser-based frontend, packaged as a single-file Windows executable via PyInstaller and wrapped in a native desktop window via `pywebview`.

The system runs entirely on the local machine. There are no outbound network calls, no third-party APIs, and no telemetry pipelines. All behavioral baselines and detection events are stored locally as JSON.

---

## System diagram

```
+--------------------------------------------------------------------+
|                          HumanSeeker.exe                            |
|                                                                    |
|  +-----------------------------+    +----------------------------+ |
|  |          pywebview          |    |       Flask backend        | |
|  |   (Edge WebView2 wrapper)   |    |     (127.0.0.1:<port>)     | |
|  |                             |    |                            | |
|  |  +-----------------------+  |    |  +----------------------+  | |
|  |  |   tracker.js          |  |    |  |   feature_extractor  |  | |
|  |  |   (browser capture)   |  |    |  |   8 behavioral feats |  | |
|  |  +-----------+-----------+  |    |  +----------+-----------+  | |
|  |              |              |    |             |              | |
|  |              | telemetry    |    |             v              | |
|  |              | POST /session|    |  +----------------------+  | |
|  |              +-------------------->  baseline_manager        | |
|  |                             |    |  (EMA, per-user JSON)    | |
|  |  +-----------------------+  |    |  +----------+-----------+  | |
|  |  |   dashboard.html      |  |    |             |              | |
|  |  |   demo.html           |  |    |             v              | |
|  |  |   settings.html       |  |    |  +----------------------+  | |
|  |  +-----------------------+  |    |  | deviation_scorer     |  | |
|  |              ^              |    |  | (z-score per feature)|  | |
|  |              | GET /latest  |    |  +----------+-----------+  | |
|  |              | GET /api/*   |    |             |              | |
|  |              +--------------------+            v              | |
|  |                             |    |  +----------------------+  | |
|  |                             |    |  | classifier           |  | |
|  |                             |    |  | (weighted heuristic) |  | |
|  |                             |    |  +----------+-----------+  | |
|  |                             |    |             |              | |
|  |                             |    |             v              | |
|  |                             |    |  +----------------------+  | |
|  |                             |    |  | security             |  | |
|  |                             |    |  | - validation         |  | |
|  |                             |    |  | - rate limit         |  | |
|  |                             |    |  | - JSONL detection log|  | |
|  |                             |    |  | - sec headers / CSP  |  | |
|  |                             |    |  +----------------------+  | |
|  +-----------------------------+    +----------------------------+ |
|                                                                    |
|                            +-----------------+                     |
|                            |   Local disk    |                     |
|                            | baselines/*.json|                     |
|                            | logs/*.jsonl    |                     |
|                            +-----------------+                     |
+--------------------------------------------------------------------+
                                  (no outbound)
```

---

## Data flow

A single behavioral session follows this path:

1. **Capture (browser).** `tracker.js` records mouse movement events, keystroke down/up events, click events, and scroll events into in-memory buffers. No keystroke content is captured — only timing and a key category.
2. **Submit.** Every ~60 seconds (configurable), the tracker POSTs the buffered events as JSON to `/session` on the loopback Flask server.
3. **Validate.** The backend enforces input validation (`backend/security.py`): user_id charset and length, event-array length caps, payload structure. Malformed payloads return 422 and are logged to `logs/security.jsonl`. The request is rate-limited per `user_id`.
4. **Extract features.** `feature_extractor.py` derives eight numerical features from the raw event lists — keystroke dwell, keystroke flight, mouse velocity, mouse curvature, click rate, scroll velocity, scroll regularity, and session-duration anomaly.
5. **Update baseline.** `baseline_manager.py` updates the per-user behavioral baseline using an exponential moving average. The baseline file lives in `data/baselines/<user_id>.json`.
6. **Cold-start gate.** If fewer than three sessions have been observed, the response is `learning` (HTTP 202) and the session is not scored.
7. **Score deviation.** `deviation_scorer.py` computes a z-score per feature against the baseline mean and standard deviation, with sensitivity-aware capping.
8. **Classify.** `classifier.py` applies a weighted heuristic over the deviation vector, producing a `risk_level` in {low, medium, high} and a confidence in [0, 1].
9. **Persist + log.** The verdict is added to in-memory counters and verdict history for the dashboard. A structured detection event is appended to `logs/detections.jsonl` (SIEM-ready, one JSON object per line).
10. **Respond.** The JSON verdict is returned to the browser, which updates the dashboard live.

---

## Module responsibilities

| Module | Responsibility |
|---|---|
| `main.py` | Entry point. Starts Flask in a daemon thread, finds a free loopback port, then either opens a `pywebview` native window or a browser tab. |
| `config.py` | Resolves paths for both source-run and PyInstaller-frozen contexts (`sys._MEIPASS`). |
| `backend/app.py` | Flask factory. Defines all routes, wires the response middleware, and connects the pipeline. |
| `backend/feature_extractor.py` | Converts raw browser events into the eight behavioral features. |
| `backend/baseline_manager.py` | Per-user baseline storage with exponential moving average updates. |
| `backend/deviation_scorer.py` | Z-score normalization with sensitivity-aware capping. |
| `backend/classifier.py` | Weighted multi-signal heuristic. |
| `backend/security.py` | Hardened response headers, CSP, input validation, rate limiting, structured detection and security event logging, version info. |
| `frontend/tracker.js` | Browser-side capture of mouse/keystroke/click/scroll events. |
| `frontend/*.html` | Dashboard, demo, settings, navigation. |

---

## Storage layout

```
HumanSeeker/
├── data/
│   ├── baselines/<user_id>.json   # per-user EMA baseline
│   ├── counters/<user_id>.json    # session counts by risk level
│   └── history/<user_id>.json     # bounded verdict history (last 200)
├── logs/
│   ├── detections.jsonl           # SIEM-ready detection events
│   └── security.jsonl             # validation rejections, rate-limit events
└── .env                           # user-configurable settings
```

All files are plain JSON / JSON Lines. Nothing is encrypted at rest. This is intentional for the local single-user model — users can read, audit, and delete their own data without tooling.

---

## Security design decisions

These are documented in `THREAT_MODEL.md` in full. Brief summary:

- **Loopback only.** The Flask server binds to `127.0.0.1`. The app makes no outbound calls.
- **No keystroke content captured.** Only timing (dwell, flight) and key category. This is a privacy choice.
- **Hardened response headers.** CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, Cross-Origin-Opener-Policy. Applied on every response by middleware in `backend/security.py`.
- **Input validation.** Strict charset for `user_id`, length caps, list-size caps, type checks. Rejections logged to `logs/security.jsonl`.
- **Rate limiting.** 30 requests per 60 seconds per `user_id` (configurable). Sliding window, in-memory.
- **Detection event log.** Structured JSON Lines format. SIEM-ready. Designed to be ingested by Splunk, Elastic, Datadog, or any log shipper.
- **No third-party services.** Air-gap deployable.

---

## Packaging

The application is built with PyInstaller from `HumanSeeker.spec`:

- Single-file executable, no Python install required on the target machine.
- All frontend assets (`frontend/`) and the `.env.example` template are bundled.
- The application icon (`frontend/static/icon.ico`) is embedded as the EXE resource and used by `pywebview` for the window/taskbar icon.
- `console=False` so no terminal flashes on launch.
- Path resolution is `sys._MEIPASS`-aware so frontend serving works identically when frozen.

Build with:

```powershell
python make_icon.py             # only if the icon design changes
pyinstaller HumanSeeker.spec --noconfirm
```

Result: `dist/HumanSeeker.exe` (~18 MB).
