"""
Flask Server: POST /session, GET /latest, settings API, frontend serving.
Refactored into a factory function for the desktop app launcher.
"""

import os
from datetime import datetime, timezone
from collections import defaultdict

from flask import Flask, request, jsonify
from dotenv import load_dotenv, set_key

from backend.feature_extractor import extract_features
from backend.baseline_manager import get_baseline, update_baseline, BASELINE_WINDOW
from backend.deviation_scorer import score_deviation, map_to_classifier_format
from backend.classifier import classify_session
from backend.security import (
    apply_security_headers,
    validate_session_payload,
    ValidationError,
    log_detection_event,
    log_security_event,
    check_rate_limit,
    get_version_info,
    RATE_LIMIT_MAX_REQUESTS,
    RATE_LIMIT_WINDOW_SEC,
)
from config import FRONTEND_DIR, ENV_PATH

# In-memory stores
latest_verdicts = {}                        # user_id -> latest verdict dict
verdict_history = defaultdict(list)          # user_id -> list of all verdicts with timestamps
session_counters = defaultdict(lambda: {"total": 0, "low": 0, "medium": 0, "high": 0})


def create_app():
    """Build and return the Flask application."""

    load_dotenv(ENV_PATH)

    app = Flask(
        __name__,
        static_folder=FRONTEND_DIR,
        static_url_path="",
    )

    # ------------------------------------------------------------------
    # CORS (loopback-only app, restricted to local origin) + security headers
    # ------------------------------------------------------------------
    @app.after_request
    def add_response_headers(response):
        # Loopback-only CORS — this app only serves 127.0.0.1.
        response.headers["Access-Control-Allow-Origin"] = "http://127.0.0.1"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        # Apply hardened security headers (CSP, X-Frame-Options, etc.)
        return apply_security_headers(response)

    # ------------------------------------------------------------------
    # Version endpoint
    # ------------------------------------------------------------------
    @app.route("/api/version")
    def version():
        return jsonify(get_version_info())

    # ------------------------------------------------------------------
    # Reset baseline for a user (and clear that user's in-memory state)
    # ------------------------------------------------------------------
    @app.route("/api/baseline", methods=["DELETE"])
    def reset_baseline():
        user_id = request.args.get("user_id")
        if not user_id:
            return jsonify({"error": "user_id required"}), 400
        # Validate user_id charset to prevent path traversal
        from backend.security import ALLOWED_USER_ID_CHARS
        if not all(c in ALLOWED_USER_ID_CHARS for c in user_id):
            return jsonify({"error": "user_id contains invalid characters."}), 400

        from backend.baseline_manager import BASELINES_DIR
        path = os.path.join(BASELINES_DIR, f"{user_id}.json")
        removed = False
        if os.path.exists(path):
            os.remove(path)
            removed = True

        # Clear in-memory state for this user too
        latest_verdicts.pop(user_id, None)
        verdict_history.pop(user_id, None)
        session_counters.pop(user_id, None)

        log_security_event("baseline_reset", {
            "user_id": user_id,
            "removed_file": removed,
        })
        return jsonify({"success": True, "user_id": user_id, "removed_file": removed})

    # ------------------------------------------------------------------
    # Frontend routes
    # ------------------------------------------------------------------
    @app.route("/")
    def index():
        return app.send_static_file("index.html")

    # ------------------------------------------------------------------
    # Health check (used by main.py to detect Flask readiness)
    # ------------------------------------------------------------------
    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"})

    # ------------------------------------------------------------------
    # Behavioral pipeline: POST /session
    # ------------------------------------------------------------------
    @app.route("/session", methods=["POST"])
    def handle_session():
        # Parse + validate the request body
        try:
            data = request.get_json(force=True, silent=False)
        except Exception:
            log_security_event("malformed_json", {
                "remote": request.remote_addr,
                "path": "/session",
            })
            return jsonify({"error": "Body must be valid JSON."}), 400

        try:
            validate_session_payload(data)
        except ValidationError as ve:
            log_security_event("invalid_payload", {
                "remote": request.remote_addr,
                "path": "/session",
                "field": ve.field,
                "message": str(ve),
            })
            return jsonify({
                "error": str(ve),
                "field": ve.field,
            }), 422

        user_id = data["user_id"]

        # Rate limiting (per user_id)
        if not check_rate_limit(user_id):
            log_security_event("rate_limit_exceeded", {
                "remote": request.remote_addr,
                "user_id": user_id,
                "limit": RATE_LIMIT_MAX_REQUESTS,
                "window_sec": RATE_LIMIT_WINDOW_SEC,
            })
            return jsonify({
                "error": (
                    f"Rate limit exceeded: max {RATE_LIMIT_MAX_REQUESTS} "
                    f"requests per {RATE_LIMIT_WINDOW_SEC} seconds per user."
                )
            }), 429

        # Step 1: Feature extraction
        features = extract_features(data)

        # Step 2: Get the existing baseline BEFORE applying this session.
        # We score new sessions against the prior baseline; only trusted
        # sessions are allowed to update it (anti-poisoning).
        baseline = get_baseline(user_id)
        if baseline is None:
            # Still in the cold-start learning window — accumulate this
            # session into the baseline unconditionally.
            update_baseline(user_id, features, trusted=True)
            log_detection_event(
                user_id=user_id,
                risk_level="learning",
                confidence=0.0,
                reason="Accumulating baseline data.",
                baseline_ready=False,
            )
            return jsonify({
                "user_id": user_id,
                "status": "learning",
                "message": f"Accumulating baseline data ({BASELINE_WINDOW} sessions needed).",
            }), 202

        # Step 3: Score deviation
        raw_scores = score_deviation(features, baseline)

        # Step 4: Map to classifier input format
        deviation_scores = map_to_classifier_format(raw_scores)

        # Step 5: Classification (local engine)
        verdict = classify_session(deviation_scores)

        # Step 6: Anti-poisoning baseline update.
        # - LOW (normal): full EMA update — the baseline absorbs the session
        # - MEDIUM (suspicious but not confirmed): full EMA update so natural
        #   user drift (new keyboard, fatigue, etc.) doesn't get stuck flagged
        # - HIGH (confirmed anomalous): skip the update — prevents a
        #   sustained attacker from poisoning the baseline to look normal
        update_baseline(
            user_id,
            features,
            trusted=(verdict["risk_level"] != "high"),
        )

        # Step 7: Build response, store for polling + history
        # (kept numbered for traceability with the architecture doc)
        now = datetime.now(timezone.utc).isoformat()
        result = {
            "user_id": user_id,
            "risk_level": verdict["risk_level"],
            "confidence": verdict["confidence"],
            "reason": verdict["reason"],
            "timestamp": now,
        }
        latest_verdicts[user_id] = result

        # Update counters
        session_counters[user_id]["total"] += 1
        session_counters[user_id][verdict["risk_level"]] += 1

        # Append to full history (keep last 200)
        verdict_history[user_id].append(result)
        if len(verdict_history[user_id]) > 200:
            verdict_history[user_id] = verdict_history[user_id][-200:]

        # Structured JSON detection event log (SIEM-ready)
        log_detection_event(
            user_id=user_id,
            risk_level=verdict["risk_level"],
            confidence=verdict["confidence"],
            reason=verdict["reason"],
            deviation_scores=deviation_scores,
            baseline_ready=True,
        )

        return jsonify(result)

    # ------------------------------------------------------------------
    # Dashboard polling: GET /latest
    # ------------------------------------------------------------------
    @app.route("/latest", methods=["GET"])
    def get_latest():
        user_id = request.args.get("user_id")
        if not user_id:
            return jsonify({"error": "user_id query parameter is required"}), 400

        verdict = latest_verdicts.get(user_id)
        if verdict is None:
            baseline = get_baseline(user_id)
            if baseline is None:
                return jsonify({
                    "status": "learning",
                    "message": f"No verdict yet: baseline still accumulating ({BASELINE_WINDOW} sessions needed).",
                }), 200
            return jsonify({
                "status": "waiting",
                "message": "Baseline is ready but no session has been scored yet.",
            }), 200

        return jsonify(verdict)

    # ------------------------------------------------------------------
    # Sensitivity / detection settings
    # ------------------------------------------------------------------
    @app.route("/api/sensitivity", methods=["GET"])
    def get_sensitivity():
        return jsonify({
            "sensitivity": os.environ.get("BSM_SENSITIVITY", "medium"),
            "baseline_sessions": int(os.environ.get("BSM_BASELINE_SESSIONS", "3")),
            "auto_send_interval": int(os.environ.get("BSM_AUTO_SEND", "60")),
        })

    @app.route("/api/sensitivity", methods=["POST"])
    def set_sensitivity():
        data = request.get_json(force=True)

        if not os.path.exists(ENV_PATH):
            with open(ENV_PATH, "w") as f:
                f.write("")

        if "sensitivity" in data:
            val = data["sensitivity"]
            if val not in ("low", "medium", "high", "max"):
                return jsonify({"error": "Sensitivity must be low, medium, high, or max."}), 400
            os.environ["BSM_SENSITIVITY"] = val
            set_key(ENV_PATH, "BSM_SENSITIVITY", val)

        if "baseline_sessions" in data:
            val = int(data["baseline_sessions"])
            if val < 1 or val > 10:
                return jsonify({"error": "Baseline sessions must be 1-10."}), 400
            os.environ["BSM_BASELINE_SESSIONS"] = str(val)
            set_key(ENV_PATH, "BSM_BASELINE_SESSIONS", str(val))

        if "auto_send_interval" in data:
            val = int(data["auto_send_interval"])
            if val < 10 or val > 300:
                return jsonify({"error": "Auto-send interval must be 10-300 seconds."}), 400
            os.environ["BSM_AUTO_SEND"] = str(val)
            set_key(ENV_PATH, "BSM_AUTO_SEND", str(val))

        return jsonify({"success": True})

    # ------------------------------------------------------------------
    # Edition / tier management
    # ------------------------------------------------------------------
    @app.route("/api/edition", methods=["GET"])
    def get_edition():
        tier = os.environ.get("BSM_EDITION", "free")
        return jsonify({"edition": tier})

    @app.route("/api/edition", methods=["POST"])
    def set_edition():
        data = request.get_json(force=True)
        tier = data.get("edition", "free").lower()
        if tier not in ("free", "starter", "pro", "enterprise"):
            return jsonify({"error": "Invalid edition."}), 400
        os.environ["BSM_EDITION"] = tier
        # Persist to .env
        if not os.path.exists(ENV_PATH):
            with open(ENV_PATH, "w") as f:
                f.write("")
        set_key(ENV_PATH, "BSM_EDITION", tier)
        return jsonify({"success": True, "edition": tier})

    # ------------------------------------------------------------------
    # Demo status: persists across app restarts via .env
    # ------------------------------------------------------------------
    @app.route("/api/demo-status", methods=["GET"])
    def get_demo_status():
        done = os.environ.get("BSM_DEMO_COMPLETED", "false")
        return jsonify({"completed": done == "true"})

    @app.route("/api/demo-status", methods=["POST"])
    def set_demo_status():
        os.environ["BSM_DEMO_COMPLETED"] = "true"
        if not os.path.exists(ENV_PATH):
            with open(ENV_PATH, "w") as f:
                f.write("")
        set_key(ENV_PATH, "BSM_DEMO_COMPLETED", "true")
        return jsonify({"success": True})

    # ------------------------------------------------------------------
    # Dashboard: GET /api/counters
    # ------------------------------------------------------------------
    @app.route("/api/counters", methods=["GET"])
    def get_counters():
        user_id = request.args.get("user_id")
        if not user_id:
            return jsonify({"error": "user_id required"}), 400
        c = session_counters.get(user_id, {"total": 0, "low": 0, "medium": 0, "high": 0})
        return jsonify(c)

    # ------------------------------------------------------------------
    # Dashboard: GET /api/history (all verdicts, newest first)
    # ------------------------------------------------------------------
    @app.route("/api/history", methods=["GET"])
    def get_history():
        user_id = request.args.get("user_id")
        if not user_id:
            return jsonify({"error": "user_id required"}), 400
        hist = verdict_history.get(user_id, [])
        return jsonify(list(reversed(hist)))  # newest first

    # ------------------------------------------------------------------
    # Appearance settings: theme, accent color, nav layout
    # ------------------------------------------------------------------
    @app.route("/api/appearance", methods=["GET"])
    def get_appearance():
        return jsonify({
            "theme": os.environ.get("BSM_THEME", "dark"),
            "accent": os.environ.get("BSM_ACCENT", "#58a6ff"),
            "nav_layout": os.environ.get("BSM_NAV_LAYOUT", "row"),
        })

    @app.route("/api/appearance", methods=["POST"])
    def set_appearance():
        data = request.get_json(force=True)

        if not os.path.exists(ENV_PATH):
            with open(ENV_PATH, "w") as f:
                f.write("")

        if "theme" in data:
            val = data["theme"]
            if val not in ("light", "dark"):
                return jsonify({"error": "Theme must be light or dark."}), 400
            os.environ["BSM_THEME"] = val
            set_key(ENV_PATH, "BSM_THEME", val)

        if "accent" in data:
            val = data["accent"].strip()
            if not val.startswith("#") or len(val) not in (4, 7):
                return jsonify({"error": "Accent must be a hex color (e.g. #58a6ff)."}), 400
            os.environ["BSM_ACCENT"] = val
            set_key(ENV_PATH, "BSM_ACCENT", val)

        if "nav_layout" in data:
            val = data["nav_layout"]
            if val not in ("row", "column"):
                return jsonify({"error": "Nav layout must be row or column."}), 400
            os.environ["BSM_NAV_LAYOUT"] = val
            set_key(ENV_PATH, "BSM_NAV_LAYOUT", val)

        return jsonify({"success": True})

    return app
