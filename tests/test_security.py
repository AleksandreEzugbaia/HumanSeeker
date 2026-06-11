"""
Unit tests for backend.security:
- Input validation (accept good, reject bad)
- Rate limiting (allow under cap, reject over cap)
- Version info shape
- Detection event log writes
"""
import json
import os
import sys

import pytest

# Ensure project root importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.security import (
    validate_session_payload,
    ValidationError,
    check_rate_limit,
    get_version_info,
    log_detection_event,
    log_security_event,
    RATE_LIMIT_MAX_REQUESTS,
    MAX_USER_ID_LENGTH,
    MAX_EVENTS_PER_TYPE,
)


# -------------------- Input validation --------------------

def test_validate_accepts_minimal_payload():
    validate_session_payload({"user_id": "alice"})


def test_validate_accepts_full_payload():
    validate_session_payload({
        "user_id": "alice_2",
        "mouse_movement": [{"x": 0, "y": 0, "t": 0}],
        "scroll_events": [{"delta": 10, "t": 1}],
        "clicks": [{"x": 0, "y": 0, "t": 2}],
        "keystrokes": [{"key": "a", "down": 3, "up": 4}],
    })


def test_validate_rejects_non_dict():
    with pytest.raises(ValidationError):
        validate_session_payload([])

    with pytest.raises(ValidationError):
        validate_session_payload("not a dict")


def test_validate_rejects_missing_user_id():
    with pytest.raises(ValidationError) as exc:
        validate_session_payload({})
    assert exc.value.field == "user_id"


def test_validate_rejects_invalid_user_id_chars():
    with pytest.raises(ValidationError) as exc:
        validate_session_payload({"user_id": "alice; DROP TABLE users"})
    assert exc.value.field == "user_id"


def test_validate_rejects_long_user_id():
    with pytest.raises(ValidationError):
        validate_session_payload({"user_id": "a" * (MAX_USER_ID_LENGTH + 1)})


def test_validate_rejects_non_list_events():
    with pytest.raises(ValidationError):
        validate_session_payload({"user_id": "alice", "mouse_movement": "not a list"})


def test_validate_rejects_too_many_events():
    with pytest.raises(ValidationError):
        validate_session_payload({
            "user_id": "alice",
            "mouse_movement": [{}] * (MAX_EVENTS_PER_TYPE + 1),
        })


def test_validate_rejects_oversized_keystroke_key():
    with pytest.raises(ValidationError):
        validate_session_payload({
            "user_id": "alice",
            "keystrokes": [{"key": "x" * 1000, "down": 0, "up": 1}],
        })


# -------------------- Rate limiting --------------------

def test_rate_limit_allows_under_cap():
    user_id = "rl_test_under"
    for _ in range(RATE_LIMIT_MAX_REQUESTS):
        assert check_rate_limit(user_id) is True


def test_rate_limit_rejects_over_cap():
    user_id = "rl_test_over"
    for _ in range(RATE_LIMIT_MAX_REQUESTS):
        check_rate_limit(user_id)
    # Next one should be rejected
    assert check_rate_limit(user_id) is False


def test_rate_limit_per_user_isolated():
    for _ in range(RATE_LIMIT_MAX_REQUESTS):
        check_rate_limit("user_a")
    # Different user should still pass
    assert check_rate_limit("user_b") is True


# -------------------- Version info --------------------

def test_version_info_shape():
    info = get_version_info()
    assert info["name"] == "HumanSeeker"
    assert "version" in info
    assert "api_version" in info
    assert "build_date" in info
    assert "python" in info
    assert "frozen" in info


def test_version_string_format():
    info = get_version_info()
    # Semver-style: major.minor.patch
    parts = info["version"].split(".")
    assert len(parts) == 3
    for p in parts:
        assert p.isdigit()


# -------------------- Detection event logging --------------------

def test_log_detection_event_writes_jsonl(tmp_path, monkeypatch):
    # Redirect logs dir to tmp
    import backend.security as sec

    def fake_logs_dir():
        return tmp_path
    monkeypatch.setattr(sec, "_logs_dir", fake_logs_dir)

    log_detection_event(
        user_id="alice",
        risk_level="high",
        confidence=0.95,
        reason="Test event",
        deviation_scores={"mouse_variance": 0.8},
        baseline_ready=True,
    )

    log_path = tmp_path / "detections.jsonl"
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8").strip()
    event = json.loads(content)

    assert event["event_type"] == "behavioral_detection"
    assert event["app"] == "HumanSeeker"
    assert event["user_id"] == "alice"
    assert event["risk_level"] == "high"
    assert event["confidence"] == 0.95
    assert event["baseline_ready"] is True
    assert event["deviation_scores"] == {"mouse_variance": 0.8}
    assert "ts" in event
    # ISO 8601 with timezone
    assert "T" in event["ts"]


def test_log_security_event_writes_jsonl(tmp_path, monkeypatch):
    import backend.security as sec
    monkeypatch.setattr(sec, "_logs_dir", lambda: tmp_path)

    log_security_event("invalid_payload", {"user_id": "x", "field": "mouse_movement"})

    log_path = tmp_path / "security.jsonl"
    assert log_path.exists()
    event = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert event["event_type"] == "invalid_payload"
    assert event["user_id"] == "x"
    assert event["field"] == "mouse_movement"


def test_logging_failure_does_not_raise(monkeypatch):
    """Logging must never break the request path; OSError must be swallowed."""
    import backend.security as sec

    class BadPath:
        def __truediv__(self, other):
            raise OSError("disk full")

    monkeypatch.setattr(sec, "_logs_dir", lambda: BadPath())

    # Should NOT raise
    log_detection_event("alice", "low", 0.5, "test")
    log_security_event("test_event", {})
