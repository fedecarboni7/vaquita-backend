from fastapi import HTTPException

from app.routers.transcribe import _parse_session_api_key


def test_parse_session_api_key_accepts_valid_json_payload() -> None:
    payload = _parse_session_api_key('{"provider":"groq","api_key":"gsk_test_123"}')

    assert payload is not None
    assert payload.provider.value == "groq"
    assert payload.api_key == "gsk_test_123"


def test_parse_session_api_key_returns_none_when_field_is_missing() -> None:
    assert _parse_session_api_key(None) is None


def test_parse_session_api_key_rejects_invalid_json() -> None:
    try:
        _parse_session_api_key("not-json")
    except HTTPException as exc:
        assert exc.status_code == 422
        assert exc.detail == "Invalid session_api_key payload"
    else:
        raise AssertionError("Expected HTTPException for invalid JSON payload")


def test_parse_session_api_key_rejects_non_object_payload() -> None:
    try:
        _parse_session_api_key('["provider","groq"]')
    except HTTPException as exc:
        assert exc.status_code == 422
        assert exc.detail == "Invalid session_api_key payload"
    else:
        raise AssertionError("Expected HTTPException for non-object JSON payload")
