"""
Security utilities for HumanSeeker.

Provides:
- Security headers middleware (CSP, X-Frame-Options, X-Content-Type-Options, etc.)
- Structured JSON detection event logging (SIEM-ready)
- Input validation for the /session endpoint
- Version info for /api/version
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ----------------------------------------------------------------------
# Version info
# ----------------------------------------------------------------------
VERSION = "1.0.0"
BUILD_DATE = "2026-06-10"
API_VERSION = "v1"


def get_version_info() -> dict:
    """Return version/build metadata for /api/version."""
    return {
        "name": "HumanSeeker",
        "version": VERSION,
        "api_version": API_VERSION,
        "build_date": BUILD_DATE,
        "python": sys.version.split()[0],
        "frozen": getattr(sys, "frozen", False),
    }


# ----------------------------------------------------------------------
# Security headers
# ----------------------------------------------------------------------
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    # SAMEORIGIN — the nav shell loads sub-pages in same-origin iframes by design.
    # External framing is still forbidden.
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}

# Content Security Policy:
# - Local app, no external resources, all inline styles allowed (single-origin app)
# - 'self' for scripts and styles, no eval
# - frame-ancestors 'self' so the nav shell can iframe its own sub-pages
CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-src 'self'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'self';"
)


def apply_security_headers(response):
    """Apply hardened security headers to a Flask response."""
    for key, value in SECURITY_HEADERS.items():
        response.headers[key] = value
    response.headers["Content-Security-Policy"] = CSP_POLICY
    return response


# ----------------------------------------------------------------------
# Input validation
# ----------------------------------------------------------------------
class ValidationError(Exception):
    """Raised on invalid session payload."""
    def __init__(self, message: str, field: str = ""):
        super().__init__(message)
        self.field = field


# Hard caps to prevent resource abuse
MAX_USER_ID_LENGTH = 128
MAX_EVENTS_PER_TYPE = 5000
MAX_KEYSTROKE_KEY_LENGTH = 32

ALLOWED_USER_ID_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-."
)


def validate_session_payload(data) -> None:
    """
    Validate a /session POST body. Raises ValidationError on any issue.

    Required:
      - data is a dict
      - user_id: non-empty string, alphanumeric + - _ . only, <= 128 chars

    Optional (validated if present):
      - mouse_movement, scroll_events, clicks, keystrokes: lists, capped length
      - timestamps and coords: numbers
    """
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object.", field="body")

    user_id = data.get("user_id")
    if not user_id or not isinstance(user_id, str):
        raise ValidationError("user_id is required and must be a string.", field="user_id")
    if len(user_id) > MAX_USER_ID_LENGTH:
        raise ValidationError(
            f"user_id exceeds {MAX_USER_ID_LENGTH} characters.", field="user_id"
        )
    if not all(c in ALLOWED_USER_ID_CHARS for c in user_id):
        raise ValidationError(
            "user_id contains invalid characters (alphanumeric, - _ . only).",
            field="user_id",
        )

    for field_name in ("mouse_movement", "scroll_events", "clicks", "keystrokes"):
        if field_name in data:
            value = data[field_name]
            if not isinstance(value, list):
                raise ValidationError(
                    f"{field_name} must be a list.", field=field_name
                )
            if len(value) > MAX_EVENTS_PER_TYPE:
                raise ValidationError(
                    f"{field_name} exceeds maximum of {MAX_EVENTS_PER_TYPE} events.",
                    field=field_name,
                )

    # Keystroke key length cap (prevents storing huge strings as "keys")
    for ks in data.get("keystrokes", []):
        if isinstance(ks, dict):
            key = ks.get("key", "")
            if isinstance(key, str) and len(key) > MAX_KEYSTROKE_KEY_LENGTH:
                raise ValidationError(
                    "keystroke key exceeds maximum length.", field="keystrokes"
                )


# ----------------------------------------------------------------------
# Structured detection event logging
# ----------------------------------------------------------------------
def _logs_dir() -> Path:
    """Return logs directory, creating it if needed. Works in frozen and dev modes."""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent.parent
    logs = base / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return logs


def log_detection_event(
    user_id: str,
    risk_level: str,
    confidence: float,
    reason: str,
    deviation_scores: dict | None = None,
    baseline_ready: bool = True,
) -> None:
    """
    Append a structured JSON detection event to logs/detections.jsonl.

    Format is SIEM-ready (JSON Lines, one event per line, ISO 8601 timestamps in UTC).
    Designed to be ingested by Splunk, Elastic, Datadog, or any log shipper.
    """
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_type": "behavioral_detection",
        "app": "HumanSeeker",
        "version": VERSION,
        "user_id": user_id,
        "risk_level": risk_level,
        "confidence": confidence,
        "reason": reason,
        "baseline_ready": baseline_ready,
        "deviation_scores": deviation_scores or {},
    }
    try:
        path = _logs_dir() / "detections.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, separators=(",", ":")) + "\n")
    except OSError:
        # Logging must never break the request path
        pass


def log_security_event(event_type: str, details: dict) -> None:
    """
    Append a structured JSON security event (validation rejections, etc.) to
    logs/security.jsonl.
    """
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "app": "HumanSeeker",
        "version": VERSION,
        **details,
    }
    try:
        path = _logs_dir() / "security.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, separators=(",", ":")) + "\n")
    except OSError:
        pass


# ----------------------------------------------------------------------
# Rate limiting (simple in-memory, per-user-id)
# ----------------------------------------------------------------------
_RATE_BUCKETS: dict[str, list[float]] = {}
RATE_LIMIT_WINDOW_SEC = 60
RATE_LIMIT_MAX_REQUESTS = 30  # 30 sessions/min per user is generous for the legit case


def check_rate_limit(user_id: str) -> bool:
    """
    Returns True if the request is within the per-user rate limit, False otherwise.
    Sliding-window approach: drop timestamps older than the window, count remaining.
    """
    now = time.time()
    bucket = _RATE_BUCKETS.setdefault(user_id, [])
    cutoff = now - RATE_LIMIT_WINDOW_SEC

    # Drop stale entries (in-place)
    bucket[:] = [t for t in bucket if t > cutoff]

    if len(bucket) >= RATE_LIMIT_MAX_REQUESTS:
        return False

    bucket.append(now)
    return True
