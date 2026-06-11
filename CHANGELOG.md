# Changelog

All notable changes to HumanSeeker are documented in this file. This format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-06-10

### Added
- Hardened HTTP security headers on all responses: Content-Security-Policy, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, Cross-Origin-Opener-Policy, Cross-Origin-Resource-Policy.
- Strict input validation on the `/session` endpoint with structured error responses (HTTP 422) and rejection logging.
- Per-user rate limiting on `/session` (30 requests / 60 seconds, sliding window).
- Structured JSON detection event logging to `logs/detections.jsonl` (SIEM-ready, JSON Lines, ISO-8601 timestamps).
- Structured security event logging to `logs/security.jsonl` for validation rejections and rate-limit events.
- `/api/version` endpoint exposing version, build date, API version, Python version, and frozen-status.
- `THREAT_MODEL.md`: STRIDE-style threat model covering detection scope, explicit non-goals, trust boundaries, assumptions, and known limitations.
- `SECURITY.md`: responsible disclosure policy, supported versions, response SLAs, hardening notes for operators.
- `ARCHITECTURE.md`: full system architecture, data flow diagram, module responsibilities, storage layout, security design decisions.
- `LICENSE` (MIT).
- Custom application icon (`frontend/static/icon.ico`) — shield + scope motif — embedded in the EXE and used by the pywebview window.
- `make_icon.py` script for regenerating the multi-resolution icon (16/24/32/48/64/128/256).
- `HumanSeeker.spec` PyInstaller configuration with icon embedded, frontend assets bundled, and console suppressed.
- GitHub Actions CI workflow (`.github/workflows/ci.yml`) running pytest on push and pull requests.
- Unit tests for `classifier`, `feature_extractor`, `deviation_scorer`, `baseline_manager`, and `security` modules.
- `test_api_pipeline.py`: live HTTP integration test harness for end-to-end pipeline verification.

### Changed
- Restricted CORS to `http://127.0.0.1` (loopback only) instead of wildcard. The app is single-origin by design.
- Path resolution in `main.py` is now `sys._MEIPASS`-aware so the icon and frontend assets resolve correctly in PyInstaller-frozen mode.

### Security
- Behavioral biometric capture is keystroke-content-free by design. Only timing (dwell, flight) and a non-content key category are recorded. This has been documented and reinforced in `THREAT_MODEL.md`.
- All event log writes are wrapped in error handling so logging failures never break the request path.

## [0.1.0] - 2026-03-15

### Added
- Initial proof-of-concept release.
- Flask backend with `/session`, `/latest`, settings, edition, demo-status, counters, history, appearance endpoints.
- Browser-side behavioral tracker (`tracker.js`) capturing mouse, keystroke, click, and scroll events.
- Feature extractor producing eight behavioral features per session.
- Baseline manager using exponential moving averages, per-user JSON storage.
- Deviation scorer with z-score normalization and sensitivity-aware capping.
- Heuristic risk classifier producing Low / Medium / High verdicts with confidence.
- Frontend pages: dashboard, demo, settings, edition, navigation hub.
- Integration test (`tests/test_pipeline.py`) covering baseline learning, normal-session scoring, and anomalous-session scoring.

[Unreleased]: https://github.com/AleksandreEzugbaia/HumanSeeker/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/AleksandreEzugbaia/HumanSeeker/releases/tag/v1.0.0
[0.1.0]: https://github.com/AleksandreEzugbaia/HumanSeeker/releases/tag/v0.1.0
