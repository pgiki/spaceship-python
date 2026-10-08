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
    Contact,
    Domain,
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
    sp._http.request.return_value = _response(400, {"detail": "Bad domain", "code": "E1"})
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
    sp._http.request.return_value = _response(200, {"status": "success", "type": "domains_Create", "details": {"a": 1}})
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
    sp._http.request.return_value = _response(200, {"status": "failed", "details": {"reason": "taken"}})
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


def _transport(*responses):
    sp = _client()
    sp._http = MagicMock()
    sp._http.request.side_effect = list(responses)
    return sp


def _ok(payload, headers=None):
    return _response(200, payload, headers)


def _accepted(op_id):
    return _response(202, None, {"spaceship-async-operationid": op_id})


def _contact_fields():
    return {
        "firstName": "John",
        "lastName": "Doe",
        "email": "john@example.com",
        "address1": "123 Main St",
        "city": "Austin",
        "country": "US",
        "phone": "+1.5125551234",
    }


def test_check_parses_pricing():
    sp = _transport(
        _ok(
            {
                "domains": [
                    {
                        "domain": "cool.ai",
                        "result": "available",
                        "premiumPricing": [{"operation": "register", "price": 69.99, "currency": "USD"}],
                    },
                    {"domain": "taken.com", "result": "unavailable", "premiumPricing": []},
                ]
            }
        )
    )
    rows = sp.domains.check("cool.ai", "taken.com")
    assert [r.available for r in rows] == [True, False]
    assert rows[0].premium is True
    assert str(rows[0].price) == "69.99"
    assert rows[0].currency == "USD"
    assert rows[1].price is None
    body = sp._http.request.call_args[1]["json"]
    assert body == {"domains": ["cool.ai", "taken.com"]}


def test_check_standard_domain_has_no_price():
    """Availability endpoint omits standard pricing: available domains come
    back with empty premiumPricing, so price/currency stay empty."""
    sp = _transport(
        _ok(
            {
                "domains": [
                    {"domain": "maishaplus.com", "result": "available", "premiumPricing": []},
                ]
            }
        )
    )
    (row,) = sp.domains.check("maishaplus.com")
    assert row.available is True
    assert row.premium is False
    assert row.price is None
    assert row.currency == ""


def test_get_info_parses_full_shape():
    sp = _transport(
        _ok(
            {
                "name": "example.com",
                "unicodeName": "example.com",
                "isPremium": False,
                "autoRenew": True,
                "registrationDate": "2024-01-01T00:00:00.000Z",
                "expirationDate": "2026-01-01T00:00:00.000Z",
                "lifecycleStatus": "registered",
                "privacyProtection": {"contactForm": True, "level": "high"},
                "nameservers": {"provider": "custom", "hosts": ["ns1.x.test"]},
                "contacts": {"registrant": "C1", "admin": "C1", "tech": "C1", "billing": "C1"},
            }
        )
    )
    d = sp.domains.get_info("Example.COM")
    assert isinstance(d, Domain)
    assert d.name == "example.com"
    assert d.auto_renew is True
    assert d.expiration_date is not None
    assert d.nameservers.hosts == ["ns1.x.test"]
    assert d.contacts.registrant == "C1"


def _register_script(*, nameservers=None):
    calls = [
        _ok({"id": "C9"}),  # PUT /contacts (ensure)
        _accepted("op-1"),  # POST register
        _ok({"status": "pending", "type": "domains_Create"}),
        _ok({"status": "success", "type": "domains_Create"}),
        _ok({"name": "example.com", "expirationDate": "2027-01-01T00:00:00.000Z"}),
    ]
    if nameservers:
        calls.append(_ok({"provider": "custom", "hosts": nameservers}))
        calls.append(_ok({"name": "example.com"}))
    return calls


def test_register_blocks_and_returns_domain():
    sp = _transport(*_register_script(nameservers=["ns1.x.test", "ns2.x.test"]))
    out = sp.domains.register(
        "example.com",
        contact=_contact_fields(),
        years=2,
        nameservers=["ns1.x.test", "ns2.x.test"],
        poll_interval=0,
    )
    assert isinstance(out, Domain)
    assert out.name == "example.com"
    register_call = sp._http.request.call_args_list[1]
    assert register_call[0][1].endswith("/domains/example.com")
    body = register_call[1]["json"]
    assert body["years"] == 2
    assert body["autoRenew"] is False
    assert body["contacts"] == {
        "registrant": "C9",
        "admin": "C9",
        "tech": "C9",
        "billing": "C9",
    }
    assert body["privacyProtection"] == {"level": "high", "userConsent": True}


def test_register_async_returns_operation():
    sp = _transport(_ok({"id": "C9"}), _accepted("op-2"), _ok({"status": "pending"}))
    out = sp.domains.register("example.com", contact=_contact_fields(), wait=False)
    assert isinstance(out, AsyncOperation)
    assert out.id == "op-2"
    assert not out.done


def test_renew_fetches_expiry_when_omitted():
    sp = _transport(
        _ok({"name": "example.com", "expirationDate": "2026-01-01T00:00:00.000Z"}),
        _accepted("op-3"),
        _ok({"status": "success"}),
        _ok({"name": "example.com", "expirationDate": "2027-01-01T00:00:00.000Z"}),
    )
    out = sp.domains.renew("example.com", years=2, poll_interval=0)
    assert isinstance(out, Domain)
    renew_call = sp._http.request.call_args_list[1]
    assert renew_call[0][1].endswith("/domains/example.com/renew")
    assert renew_call[1]["json"]["currentExpirationDate"].startswith("2026-01-01")


def test_transfer_lock_cycle():
    sp = _transport(
        _ok({"id": "C9"}),
        _accepted("op-4"),
        _ok({"status": "success"}),
        _ok({"name": "example.com"}),
        _ok({"isLocked": True}),
        _ok({"isLocked": False}),
        _ok({"authCode": "secret123", "expires": "2100-01-01T00:00:00.000Z"}),
    )
    out = sp.domains.transfer("example.com", contact=_contact_fields(), auth_code="secret123", poll_interval=0)
    assert isinstance(out, Domain)
    transfer_body = sp._http.request.call_args_list[1][1]["json"]
    assert transfer_body["authCode"] == "secret123"
    assert sp.domains.lock("example.com") is True
    assert sp.domains.unlock("example.com") is False
    assert sp.domains.get_auth_code("example.com") == "secret123"


def test_settings_endpoints():
    sp = _transport(
        _ok({"isEnabled": True}),
        _ok({"provider": "basic"}),
        _ok({"provider": "custom", "hosts": ["ns1.x.test"]}),
        _ok({"privacyLevel": "high"}),
    )
    assert sp.domains.set_autorenew("example.com", True) is True
    assert sp.domains.set_nameservers("example.com", None)["provider"] == "basic"
    assert sp.domains.set_nameservers("example.com", ["ns1.x.test"])["provider"] == "custom"
    assert sp.domains.set_privacy("high", "example.com")["privacyLevel"] == "high"


def test_contacts_save_read_ensure():
    sp = _transport(
        _ok({"id": "C7"}),
        _ok({"id": "C7", **_contact_fields()}),
        _ok({"id": "C8", **_contact_fields()}),
    )
    assert sp.contacts.save(_contact_fields()) == "C7"
    assert sp.contacts.read("C7").first_name == "John"
    assert sp.contacts.ensure({"id": "C8"}) == "C8"
    assert sp._http.request.call_count == 3


def test_contact_model_api_fields():
    c = Contact(first_name="J", last_name="D", email="j@d.test", address1="x", city="y", country="US", phone="+1.1")
    fields = c.api_fields()
    assert fields["firstName"] == "J"
    assert "id" not in fields
    assert Contact.from_api({"contactId": "ZZ", **_contact_fields()}).id == "ZZ"


def test_unsupported_endpoints_raise():
    sp = _client()
    with pytest.raises(NotSupportedError):
        sp.domains.get_tld_list()
    with pytest.raises(NotSupportedError):
        sp.domains.suggest("example.com")


def _dns_rows():
    return {
        "items": [
            {"type": "A", "name": "@", "address": "1.2.3.4", "ttl": 3600},
            {"type": "A", "name": "www", "address": "1.2.3.4", "ttl": 3600},
            {"type": "MX", "name": "@", "address": "mail.example.com", "ttl": 3600},
        ],
        "total": 3,
    }


def test_dns_list_and_name_translation():
    from spaceship import DNSRecord

    sp = _transport(_ok(_dns_rows()))
    rows = sp.dns.list("Example.COM.")
    assert [r.fqdn("example.com") for r in rows] == [
        "example.com",
        "www.example.com",
        "example.com",
    ]
    assert rows[0].to_api() == {
        "type": "A",
        "name": "@",
        "address": "1.2.3.4",
        "ttl": 3600,
    }
    assert DNSRecord(type="a", name="@", address="x").fqdn("example.com") == "example.com"


def test_dns_add_and_delete_roundtrip():
    sp = _transport(
        _ok(_dns_rows()),
        _response(204, None),
        _ok(_dns_rows()),
        _response(204, None),
        _ok(_dns_rows()),
    )

    added = sp.dns.create_record("example.com", "shop", "A", "5.6.7.8", ttl=300)
    assert added.name == "shop" and added.address == "5.6.7.8"
    put_body = sp._http.request.call_args_list[1][1]["json"]
    assert put_body["force"] is True
    assert len(put_body["items"]) == 4
    assert sp.dns.delete("example.com", record_type="MX") == 1
    put_body2 = sp._http.request.call_args_list[3][1]["json"]
    assert all(i["type"] != "MX" for i in put_body2["items"])
    assert sp.dns.delete("example.com", record_type="NOPE") == 0


def test_dns_set_a_records():
    rows = _dns_rows()
    sp = _transport(_ok(rows), _response(204, None), _ok({**rows, "items": []}))
    out = sp.dns.set_a_records("example.com", "example.com", "9.9.9.9")
    assert isinstance(out, list)
    put_body = sp._http.request.call_args_list[1][1]["json"]
    a_rows = [i for i in put_body["items"] if i["type"] == "A"]
    assert {(i["name"], i["address"]) for i in a_rows} == {
        ("@", "9.9.9.9"),
        ("www", "9.9.9.9"),
    }


def test_dns_delete_exact():
    sp = _transport(_response(204, None))
    sp.dns.delete_exact("example.com", [{"type": "A", "name": "@", "address": "1.2.3.4"}])
    call = sp._http.request.call_args
    assert call[0][1].endswith("/dns/records/example.com")
    assert call[1]["json"] == {"records": [{"type": "A", "name": "@", "address": "1.2.3.4"}]}
