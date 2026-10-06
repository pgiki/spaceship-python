"""Storefront pricing (``pricing-bff/getPrices``): bulk TLD prices, no API key.

The public Spaceship API (``docs.spaceship.dev``) only returns ``premiumPricing``
for premium domains, so there is no official bulk TLD pricing endpoint. The
storefront pricing tab (``/domain-search/?tab=pricing``) instead calls an
internal same-origin BFF::

    POST https://www.spaceship.com/gateway/api/v1/pricing-bff/price/getPrices

with up to ~25 ``productSlug`` entries per call. ``productSlug`` is the TLD
with ``.`` mapped to ``_`` (``co.in`` -> ``co_in``, ``it.com`` -> ``it_com``).

Response shape (per product, ``period=P1Y``)::

    {"products": [{"product": {"productSlug": "com"}, "plan": {...},
      "prices": [
        {"priceType": "purchase",
         "error": null,
         "total": {"USD": {"price": {"amount": "9.68", ...},
                            "regularPrice": {"amount": "10.18", ...}}}},
        {"priceType": "renewal", ...}]}]}}

There is no ``priceType: "transfer"`` block; ``transferFee`` components are
``0.00``. Transfer pricing surfaces as the ``purchase`` leg when the request
uses ``pricingPlanParams.transfer=1``. This client therefore does two passes
per chunk: ``transfer=0`` (``purchase`` -> register, ``renewal`` -> renew)
and ``transfer=1`` (``purchase`` -> transfer).

``0.00`` amounts mean "not offered" and become ``None``, never ``0``.
ICANN surcharges under ``components.icannFee`` are *not* added to totals.

Cloudflare note: the BFF sits behind Cloudflare bot management, so plain HTTP
POSTs (``fetcher="direct"``) only work while cookies are fresh. The default
``fetcher="playwright"`` (optional ``pricing`` extra) visits the pricing page
in real Chrome and POSTs from inside the page via ``fetch()``, which carries
Chrome's TLS fingerprint and auto-refreshed cookies.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .errors import PricingError
from .logging import get_logger
from .models import TldPrice

logger = get_logger("pricing")

#: Proven batch size from browser captures (25 products per call).
DEFAULT_BATCH_SIZE = 25

#: Dummy SLD used by the storefront when quoting bare TLD prices.
DEFAULT_SLD = "spaceship-query1"

DEFAULT_BFF_URL = "https://www.spaceship.com/gateway/api/v1/pricing-bff/price/getPrices"
DEFAULT_PRICING_PAGE_URL = "https://www.spaceship.com/domain-search/?tab=pricing&query="

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/154.0.0.0 Safari/537.36"
)


class PricingConfig(BaseModel):
    """Storefront pricing configuration with validation."""

    bff_url: str = Field(default=DEFAULT_BFF_URL, description="pricing-bff getPrices URL")
    pricing_page_url: str = Field(
        default=DEFAULT_PRICING_PAGE_URL, description="Storefront pricing page (Playwright entry point)"
    )
    currency: str = Field(default="USD", description="Billing currency (BFF + z-currency header)")
    sld: str = Field(default=DEFAULT_SLD, description="Dummy SLD for bare-TLD quotes")
    batch_size: int = Field(default=DEFAULT_BATCH_SIZE, ge=1, description="Product slugs per BFF call")
    timeout: float = Field(default=20.0, description="Request timeout in seconds")
    request_delay: float = Field(default=1.0, ge=0, description="Politeness delay between chunks (seconds)")
    fetcher: str = Field(default="playwright", description="Transport: direct, playwright, scraping_api")
    cookies: dict[str, str] = Field(default_factory=dict, description="Static cookies for the direct fetcher")
    scrape_api_url: str = Field(default="", description="Scraping-proxy URL for the scraping_api fetcher")
    scrape_api_key: str = Field(default="", description="Scraping-proxy API key")

    model_config = ConfigDict(str_strip_whitespace=True, validate_default=True)

    @classmethod
    def from_env(cls, **overrides: Any) -> PricingConfig:
        """Build config from explicit args with ``SPACESHIP_PRICING_*`` env fallback."""
        env = os.environ.get
        cookies = overrides.get("cookies")
        if cookies is None:
            cookies = _parse_cookies(env("SPACESHIP_PRICING_COOKIES", ""))
        return cls(
            bff_url=overrides.get("bff_url") or env("SPACESHIP_PRICING_BFF_URL", "") or DEFAULT_BFF_URL,
            pricing_page_url=overrides.get("pricing_page_url")
            or env("SPACESHIP_PRICING_PAGE_URL", "")
            or DEFAULT_PRICING_PAGE_URL,
            currency=overrides.get("currency") or env("SPACESHIP_PRICING_CURRENCY", "") or "USD",
            sld=overrides.get("sld") or env("SPACESHIP_PRICING_SLD", "") or DEFAULT_SLD,
            batch_size=overrides.get("batch_size")
            if overrides.get("batch_size") is not None
            else int(env("SPACESHIP_PRICING_BATCH_SIZE", "") or DEFAULT_BATCH_SIZE),
            timeout=overrides.get("timeout")
            if overrides.get("timeout") is not None
            else float(env("SPACESHIP_PRICING_TIMEOUT", "") or 20.0),
            request_delay=overrides.get("request_delay")
            if overrides.get("request_delay") is not None
            else float(env("SPACESHIP_PRICING_DELAY", "") or 1.0),
            fetcher=(overrides.get("fetcher") or env("SPACESHIP_PRICING_FETCHER", "") or "playwright").lower(),
            cookies=cookies,
            scrape_api_url=overrides.get("scrape_api_url") or env("SPACESHIP_PRICING_SCRAPE_API_URL", ""),
            scrape_api_key=overrides.get("scrape_api_key") or env("SPACESHIP_PRICING_SCRAPE_API_KEY", ""),
        )


def normalize_slug_tld(raw: str) -> str:
    """Bare extension without leading dot (``.CO.IN`` -> ``co.in``)."""
    return str(raw or "").strip().lower().lstrip(".")


def tld_to_slug(tld: str) -> str:
    """``co.in`` -> ``co_in`` (storefront product slug; idempotent for slugs)."""
    return normalize_slug_tld(tld).replace(".", "_")


def slug_to_tld(slug: str) -> str:
    """``co_in`` -> ``co.in``."""
    return str(slug or "").strip().lower().replace("_", ".")


def _parse_cookies(raw: Any) -> dict[str, str]:
    """Parse a ``Cookie`` header string (or passthrough dict) for direct POSTs."""
    if isinstance(raw, dict):
        return dict(raw)
    out: dict[str, str] = {}
    for part in str(raw or "").split(";"):
        if "=" in part:
            k, _, v = part.partition("=")
            k, v = k.strip(), v.strip()
            if k:
                out[k] = v
    return out


def _parse_amount(raw: Any) -> Decimal | None:
    """Promo-applied amount; ``0``/empty means unavailable (never store 0)."""
    if raw is None or raw == "":
        return None
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError, TypeError, AttributeError):
        return None
    if value <= 0:
        return None
    return value


def _price_amount(entry: dict[str, Any], currency: str) -> Decimal | None:
    """Extract ``total.<CUR>.price.amount`` from one ``prices[]`` entry."""
    try:
        total = (entry or {}).get("total") or {}
        bucket = total.get(currency) or total.get(currency.lower()) or {}
        return _parse_amount((bucket.get("price") or {}).get("amount"))
    except Exception:
        return None


def parse_bff_response(
    payload: dict[str, Any],
    *,
    transfer_mode: bool,
    currency: str = "USD",
) -> dict[str, dict[str, Decimal]]:
    """Parse one BFF response into ``{slug: {register?, renew?, transfer?}}``.

    ``transfer_mode=False`` (request ``transfer=0``): ``purchase`` fills
    ``register``, ``renewal`` fills ``renew``. ``transfer_mode=True``
    (request ``transfer=1``): ``purchase`` fills ``transfer`` (transfer promo
    leg); ``renewal`` is ignored (already captured in pass A). A future
    ``priceType == "transfer"`` block is honored in either mode.
    """
    out: dict[str, dict[str, Decimal]] = {}
    products = (payload or {}).get("products")
    if not isinstance(products, list):
        raise PricingError("BFF payload has no products list.")
    for product in products:
        if not isinstance(product, dict):
            continue
        inner = product.get("product")
        slug = ""
        if isinstance(inner, dict):
            slug = str(inner.get("productSlug") or "").strip().lower()
        if not slug:
            continue
        bucket = out.setdefault(slug, {})
        prices = product.get("prices")
        if not isinstance(prices, list):
            continue
        for entry in prices:
            if not isinstance(entry, dict):
                continue
            if entry.get("error"):
                continue
            ptype = str(entry.get("priceType") or "").strip().lower()
            amount = _price_amount(entry, currency)
            if amount is None:
                continue
            if ptype == "transfer":
                bucket["transfer"] = amount
            elif ptype == "purchase":
                bucket["transfer" if transfer_mode else "register"] = amount
            elif ptype == "renewal" and not transfer_mode:
                bucket["renew"] = amount
    return out


class StorefrontPricing:
    """Bulk TLD prices from the Spaceship storefront pricing BFF (keyless).

    Example:
        >>> pricing = StorefrontPricing()  # fetcher="playwright" by default
        >>> prices = pricing.fetch(["com", "org", "ai"])
        >>> [(p.tld, p.register, p.renew, p.transfer) for p in prices]
    """

    def __init__(self, config: PricingConfig | None = None, **overrides: Any) -> None:
        if config is not None and overrides:
            config = config.model_copy(update=overrides)
        self.config = config if config is not None else PricingConfig.from_env(**overrides)

    @classmethod
    def from_env(cls, **overrides: Any) -> StorefrontPricing:
        """Build from explicit args with ``SPACESHIP_PRICING_*`` env fallback."""
        return cls(PricingConfig.from_env(**overrides))

    # -- request building --

    def _headers(self) -> dict[str, str]:
        return {
            "accept": "*/*",
            "content-type": "application/json",
            "origin": "https://www.spaceship.com",
            "referer": "https://www.spaceship.com/domain-search/?tab=pricing&query=",
            "z-currency": self.config.currency.upper(),
            "user-agent": USER_AGENT,
        }

    def _build_body(self, slugs: list[str], *, transfer: int) -> dict[str, Any]:
        return {
            "currencies": [self.config.currency.upper()],
            "includeBasePrice": True,
            "includeFields": [
                "components",
                "modifiers",
                "params",
                "discount",
                "pricePerPeriod",
                "outputValues",
                "reducers",
            ],
            "products": [
                {
                    "priceTypes": ["purchase", "renewal"],
                    "product": {
                        "productSlug": slug,
                        "plan": {
                            "pricingPlanParams": {"transfer": int(transfer), "sld": self.config.sld},
                            "pricingPlanSlug": "regular",
                            "period": "P1Y",
                        },
                    },
                }
                for slug in slugs
            ],
        }

    # -- transports --

    def _post_direct(self, body: dict[str, Any]) -> dict[str, Any]:
        """Direct POST (works while Cloudflare cookies are fresh)."""
        try:
            r = httpx.post(
                self.config.bff_url,
                json=body,
                headers=self._headers(),
                cookies=self.config.cookies or None,
                timeout=self.config.timeout,
            )
        except Exception as exc:
            raise PricingError(f"Spaceship BFF request failed: {exc}") from exc
        text = (r.text or "")[:200]
        if r.status_code in (401, 403):
            raise PricingError(
                "Spaceship BFF blocked "
                f"(HTTP {r.status_code}; Cloudflare/cookies need refresh): {text}."
            )
        if r.status_code != 200:
            raise PricingError(f"Spaceship BFF HTTP {r.status_code}: {text}.")
        try:
            payload = r.json()
        except Exception as exc:
            raise PricingError(f"Spaceship BFF invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise PricingError("Spaceship BFF returned non-object JSON.")
        return payload

    def _post_playwright(self, body: dict[str, Any]) -> dict[str, Any]:
        """POST from a Playwright context (auto-handles Cloudflare cookies)."""
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except ImportError as exc:
            raise PricingError(
                "Playwright fetcher requested but `playwright` is not installed "
                "(pip install spaceship-python[pricing] && playwright install chromium)."
            ) from exc
        try:
            with sync_playwright() as p:
                try:
                    # Real Chrome (not headless-shell): much better fingerprint
                    # against Cloudflare bot management.
                    browser = p.chromium.launch(headless=True, channel="chrome")
                except Exception:
                    browser = p.chromium.launch(headless=True)
                try:
                    context = browser.new_context(user_agent=USER_AGENT, locale="en-US")
                    page = context.new_page()
                    page.goto(
                        self.config.pricing_page_url,
                        wait_until="domcontentloaded",
                        timeout=int(self.config.timeout * 1000),
                    )
                    # Let Cloudflare challenge / session cookies settle.
                    page.wait_for_timeout(8000)
                    # POST from *inside* the page: fetch() uses Chrome's real
                    # network stack (TLS fingerprint + cookies). Playwright's
                    # context.request.post() uses its own HTTP client, which
                    # Cloudflare flags even when cookies are valid.
                    result = page.evaluate(
                        """async ({url, body, currency}) => {
                            const r = await fetch(url, {
                                method: 'POST',
                                headers: {
                                    'content-type': 'application/json',
                                    'z-currency': currency,
                                },
                                body: JSON.stringify(body),
                            });
                            return {status: r.status, text: await r.text()};
                        }""",
                        {
                            "url": self.config.bff_url,
                            "body": body,
                            "currency": self.config.currency.upper(),
                        },
                    )
                    status = (result or {}).get("status")
                    if status != 200:
                        raise PricingError(f"Spaceship BFF via Playwright HTTP {status}.")
                    try:
                        payload = json.loads((result or {}).get("text") or "")
                    except Exception as exc:
                        raise PricingError(
                            f"Spaceship BFF via Playwright invalid JSON: {exc}"
                        ) from exc
                finally:
                    browser.close()
        except PricingError:
            raise
        except Exception as exc:
            raise PricingError(f"Playwright fetch failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise PricingError("Spaceship BFF returned non-object JSON.")
        return payload

    def _post_scraping_api(self, body: dict[str, Any]) -> dict[str, Any]:
        """Forward the BFF POST through a configured scraping proxy.

        POSTs ``{"url", "method", "headers", "body"}`` to the configured
        proxy with ``Authorization: Bearer <key>`` and expects the upstream
        JSON back (either raw or wrapped in ``{"result": ...}``).
        """
        if not self.config.scrape_api_url or not self.config.scrape_api_key:
            raise PricingError(
                "Scraping-API fetcher requested but scrape_api_url/key are not configured."
            )
        try:
            r = httpx.post(
                self.config.scrape_api_url,
                json={
                    "url": self.config.bff_url,
                    "method": "POST",
                    "headers": self._headers(),
                    "body": body,
                },
                headers={
                    "Authorization": f"Bearer {self.config.scrape_api_key}",
                    "content-type": "application/json",
                },
                timeout=self.config.timeout + 30,
            )
        except Exception as exc:
            raise PricingError(f"Scraping API request failed: {exc}") from exc
        if r.status_code != 200:
            raise PricingError(f"Scraping API HTTP {r.status_code}.")
        try:
            payload = r.json()
        except Exception as exc:
            raise PricingError(f"Scraping API invalid JSON: {exc}") from exc
        if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
            payload = payload["result"]
        if not isinstance(payload, dict) or not isinstance(payload.get("products"), list):
            raise PricingError("Scraping API did not return a BFF payload.")
        return payload

    def _post(self, body: dict[str, Any], fetcher: str | None = None) -> dict[str, Any]:
        name = (fetcher or self.config.fetcher).lower()
        if name == "playwright":
            return self._post_playwright(body)
        if name in ("scraping_api", "scraping-api", "api"):
            return self._post_scraping_api(body)
        return self._post_direct(body)

    # -- public fetch --

    @staticmethod
    def _chunks(items: list[str], size: int):
        size = max(1, int(size))
        for i in range(0, len(items), size):
            yield items[i : i + size]

    def resolve_slugs(self, tlds: Iterable[str]) -> list[str]:
        """Normalize + de-dupe TLDs/slugs, preserving order."""
        seen: set[str] = set()
        out: list[str] = []
        for t in tlds:
            s = tld_to_slug(str(t))
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        if not out:
            raise PricingError("At least one TLD is required.")
        return out

    def fetch(
        self,
        tlds: Iterable[str],
        *,
        fetcher: str | None = None,
        include_transfer: bool = True,
    ) -> list[TldPrice]:
        """Fetch register/renew (+transfer) prices; ``None`` for unavailable legs.

        Raises :class:`PricingError` when no chunk succeeds at all; per-TLD
        gaps are skipped (never fatal).
        """
        slugs = self.resolve_slugs(tlds)
        currency = self.config.currency.upper()
        merged: dict[str, dict[str, Decimal]] = {s: {} for s in slugs}
        ok_chunks = 0
        last_error: Exception | None = None
        for chunk in self._chunks(slugs, self.config.batch_size):
            # Pass A: register + renew.
            try:
                payload_a = self._post(self._build_body(chunk, transfer=0), fetcher)
                for slug, vals in parse_bff_response(
                    payload_a, transfer_mode=False, currency=currency
                ).items():
                    merged.setdefault(slug, {}).update(vals)
                ok_chunks += 1
            except PricingError as exc:
                last_error = exc
                logger.warning("Spaceship pass A failed for %d slug(s): %s", len(chunk), exc)
                continue
            # Pass B: transfer leg.
            if include_transfer:
                try:
                    payload_b = self._post(self._build_body(chunk, transfer=1), fetcher)
                    for slug, vals in parse_bff_response(
                        payload_b, transfer_mode=True, currency=currency
                    ).items():
                        if vals.get("transfer") is not None:
                            merged.setdefault(slug, {})["transfer"] = vals["transfer"]
                except PricingError as exc:
                    last_error = exc
                    logger.warning("Spaceship pass B failed for %d slug(s): %s", len(chunk), exc)
            if self.config.request_delay:
                time.sleep(self.config.request_delay)
        if ok_chunks == 0:
            raise PricingError(f"Spaceship fetch failed for all {len(slugs)} slug(s): {last_error}")
        prices: list[TldPrice] = []
        for slug in slugs:
            vals = merged.get(slug) or {}
            if not vals.get("register") and not vals.get("renew") and not vals.get("transfer"):
                logger.warning("Spaceship has no usable price for .%s; skipping.", slug_to_tld(slug))
                continue
            prices.append(
                TldPrice(
                    tld=slug_to_tld(slug),
                    register=vals.get("register"),
                    renew=vals.get("renew"),
                    transfer=vals.get("transfer"),
                    currency=currency,
                )
            )
        return prices
