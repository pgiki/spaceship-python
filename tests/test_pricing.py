"""Offline tests for storefront pricing (no network, no browser)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from spaceship import (
    PricingConfig,
    PricingError,
    StorefrontPricing,
    TldPrice,
    parse_bff_response,
    slug_to_tld,
    tld_to_slug,
)


def _price(ptype, amount, regular=None):
    return {
        "priceType": ptype,
        "error": None,
        "total": {
            "USD": {
                "price": {"amount": amount, "currency": "USD"},
                "regularPrice": {"amount": regular or amount, "currency": "USD"},
            }
        },
        "components": {},
    }


BFF_PASS_A = {
    "products": [
        {
            "product": {"productSlug": "com"},
            "prices": [_price("purchase", "9.68", "10.18"), _price("renewal", "10.18")],
        },
        {
            "product": {"productSlug": "org"},
            "prices": [_price("purchase", "11.29", "11.59"), _price("renewal", "11.59")],
        },
        {
            # 0.00 purchase = registration unavailable -> register None.
            "product": {"productSlug": "si"},
            "prices": [_price("purchase", "0.00"), _price("renewal", "11.98")],
        },
        {
            "product": {"productSlug": "it_com"},
            "prices": [_price("purchase", "25.88"), _price("renewal", "25.88")],
        },
    ]
}

BFF_PASS_B = {
    "products": [
        {
            "product": {"productSlug": "com"},
            "prices": [_price("purchase", "9.68"), _price("renewal", "10.18")],
        },
        {
            "product": {"productSlug": "org"},
            "prices": [_price("purchase", "11.29"), _price("renewal", "11.59")],
        },
        {
            "product": {"productSlug": "si"},
            "prices": [_price("purchase", "0.00"), _price("renewal", "11.98")],
        },
        {
            "product": {"productSlug": "it_com"},
            "prices": [_price("purchase", "25.88"), _price("renewal", "25.88")],
        },
    ]
}


def _resp(status=200, payload=None):
    resp = MagicMock()
    resp.status_code = status
    resp.text = "" if status == 200 else "blocked"
    if payload is not None:
        resp.json.return_value = payload
    else:
        resp.json.side_effect = ValueError("no json")
    return resp


def _pricing(**overrides):
    kwargs = {"fetcher": "direct", "request_delay": 0}
    kwargs.update(overrides)
    return StorefrontPricing(PricingConfig(**kwargs))


def test_slug_helpers():
    assert tld_to_slug("co.in") == "co_in"
    assert tld_to_slug("IT.COM") == "it_com"
    assert tld_to_slug("it_com") == "it_com"
    assert slug_to_tld("it_com") == "it.com"


def test_parse_pass_a_register_renew():
    out = parse_bff_response(BFF_PASS_A, transfer_mode=False)
    assert out["com"]["register"] == Decimal("9.68")
    assert out["com"]["renew"] == Decimal("10.18")
    assert "transfer" not in out["com"]
    assert "register" not in out["si"]
    assert out["si"]["renew"] == Decimal("11.98")


def test_parse_pass_b_transfer_leg():
    out = parse_bff_response(BFF_PASS_B, transfer_mode=True)
    assert out["com"]["transfer"] == Decimal("9.68")
    assert "renew" not in out["com"]
    assert "transfer" not in out["si"]


def test_parse_bad_payload_raises():
    with pytest.raises(PricingError):
        parse_bff_response({"nope": 1}, transfer_mode=False)


def test_fetch_two_pass_merge():
    with patch(
        "spaceship.pricing.httpx.post",
        side_effect=[_resp(200, BFF_PASS_A), _resp(200, BFF_PASS_B)],
    ) as mock_post:
        prices = _pricing().fetch(["com", "org", "si", "it.com"])
    assert mock_post.call_count == 2
    bodies = [c[1]["json"] for c in mock_post.call_args_list]
    assert bodies[0]["products"][0]["product"]["plan"]["pricingPlanParams"]["transfer"] == 0
    assert bodies[1]["products"][0]["product"]["plan"]["pricingPlanParams"]["transfer"] == 1
    by_tld = {p.tld: p for p in prices}
    assert by_tld["com"].register == Decimal("9.68")
    assert by_tld["com"].renew == Decimal("10.18")
    assert by_tld["com"].transfer == Decimal("9.68")
    assert by_tld["si"].register is None
    assert by_tld["si"].renew == Decimal("11.98")
    assert by_tld["si"].transfer is None
    assert "it.com" in by_tld
    assert all(isinstance(p, TldPrice) for p in prices)


def test_fetch_cloudflare_block_raises():
    with (
        patch("spaceship.pricing.httpx.post", return_value=_resp(status=403)),
        pytest.raises(PricingError, match="blocked"),
    ):
        _pricing().fetch(["com"])


def test_fetch_empty_scope_raises():
    with pytest.raises(PricingError):
        _pricing().fetch([])


def test_config_from_env_defaults():
    cfg = PricingConfig.from_env()
    assert cfg.currency == "USD"
    assert cfg.batch_size == 25
    assert cfg.fetcher == "playwright"


def test_pricing_error_is_spaceship_error():
    from spaceship import SpaceshipError

    assert issubclass(PricingError, SpaceshipError)
    err = PricingError("boom")
    assert err.code == "pricing_fetch_failed"
