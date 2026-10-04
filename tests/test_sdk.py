"""Offline tests for spaceship-python (no network)."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from spaceship import (
    AsyncOperation,
    AsyncOperationError,
    ConfigurationError,
    NotSupportedError,
    Spaceship,
    SpaceshipError,
)
from spaceship.idn import from_punycode, to_punycode


def _client(**overrides):
    env = {"SPACESHIP_API_KEY": "key", "SPACESHIP_API_SECRET": "secret"}
    os.environ.update(env)
    kwargs = {"api_key": "key", "api_secret": "secret"}
    kwargs.update(overrides)
    return Spaceship(**kwargs)


def _response(status=200, payload=None, headers=None):
    import json as jsonlib

    return SimpleNamespace(
        status_code=status,
        headers=headers or {},
        content=jsonlib.dumps(payload) if payload is not None else b"",
        json=(lambda: payload),
    )


def test_config_missing_raises():
    for k in ("SPACESHIP_API_KEY", "SPACESHIP_API_SECRET"):
        os.environ.pop(k, None)
    with pytest.raises(ConfigurationError):
        Spaceship()
    os.environ.update({"SPACESHIP_API_KEY": "k", "SPACESHIP_API_SECRET": "s"})


def test_config_invalid_log_level():
    with pytest.raises(ConfigurationError):
        Spaceship(api_key="k", api_secret="s", log_level="VERBOSE")


def test_client_context_manager():
    sp = _client()
    sp._http = MagicMock()
    with sp as ctx:
        assert ctx is sp
    sp._http.close.assert_called_once()


def test_auth_headers():
    sp = _client(api_key="K", api_secret="S")
    captured = {}

    def fake_request(method, url, **kwargs):
        captured.update(kwargs.get("headers") or {})
        return _response(200, {"ok": True})

    sp._http = MagicMock()
    sp._http.request.side_effect = fake_request
    from spaceship._api.base import BaseAPI

    BaseAPI(sp)._request("GET", "/domains")
    assert captured["X-Api-Key"] == "K"
    assert captured["X-Api-Secret"] == "S"


def test_error_from_problem_json():
    sp = _client()
    sp._http = MagicMock()
    sp._http.request.return_value = _response(
        400, {"detail": "Bad domain", "code": "E1"}
    )
    from spaceship._api.base import BaseAPI

    with pytest.raises(SpaceshipError) as exc_info:
        BaseAPI(sp)._request("GET", "/domains/x")
    err = exc_info.value
    assert err.status_code == 400
    assert "Bad domain" in str(err)
    assert err.code == "E1"


def test_error_non_json_body():
    sp = _client()
    bad = SimpleNamespace(status_code=500, headers={}, content=b"oops", text="oops")
    bad.json = MagicMock(side_effect=ValueError("no json"))
    sp._http = MagicMock()
    sp._http.request.return_value = bad
    from spaceship._api.base import BaseAPI

    with pytest.raises(SpaceshipError) as exc_info:
        BaseAPI(sp)._request("GET", "/x")
    assert exc_info.value.status_code == 500
    assert "oops" in str(exc_info.value)


def test_not_supported_error_hint():
    err = NotSupportedError("No endpoint.", alternative="Use X instead.")
    assert "Use X instead." in str(err)


def test_operations_get_parses():
    sp = _client()
    sp._http = MagicMock()
    sp._http.request.return_value = _response(
        200, {"status": "success", "type": "domains_Create", "details": {"a": 1}}
    )
    op = sp.operations.get("abc123")
    assert isinstance(op, AsyncOperation)
    assert op.id == "abc123"
    assert op.succeeded and op.done


def test_operations_wait_success_after_pending():
    sp = _client()
    sp._http = MagicMock()
    sp._http.request.side_effect = [
        _response(200, {"status": "pending", "type": "domains_Create"}),
        _response(200, {"status": "pending", "type": "domains_Create"}),
        _response(200, {"status": "success", "type": "domains_Create"}),
    ]
    op = sp.operations.wait_for("op1", timeout=30, poll_interval=0)
    assert op.succeeded
    assert sp._http.request.call_count == 3


def test_operations_wait_failed_raises():
    sp = _client()
    sp._http = MagicMock()
    sp._http.request.return_value = _response(
        200, {"status": "failed", "details": {"reason": "taken"}}
    )
    with pytest.raises(AsyncOperationError) as exc_info:
        sp.operations.wait_for("op9", timeout=30, poll_interval=0)
    assert exc_info.value.operation_id == "op9"


def test_operations_wait_timeout():
    sp = _client()
    sp._http = MagicMock()
    sp._http.request.return_value = _response(200, {"status": "pending"})
    with pytest.raises(TimeoutError):
        sp.operations.wait_for("op0", timeout=0, poll_interval=0)
    assert sp._http.request.call_count == 1


def test_idn_roundtrip():
    assert to_punycode("Example.COM.") == "example.com"
    assert from_punycode("example.com") == "example.com"
    assert to_punycode("münchen.de") == "xn--mnchen-3ya.de"
    assert from_punycode("xn--mnchen-3ya.de") == "münchen.de"
