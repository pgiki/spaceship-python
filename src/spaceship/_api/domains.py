"""Domain management (``/v1/domains``): availability, register, renew, transfer."""

from __future__ import annotations

from typing import Any

from ..errors import NotSupportedError
from ..idn import to_punycode
from ..models import AsyncOperation, Contact, Domain, DomainCheck
from .base import BaseAPI
from .contacts import ContactsAPI

#: Batch size for POST /v1/domains/available (API allows 1..20).
CHECK_BATCH_SIZE = 20


def _privacy_payload(whois_protection: bool | None) -> dict[str, Any] | None:
    if whois_protection is None:
        return None
    if whois_protection:
        return {"level": "high", "userConsent": True}
    return {"level": "public", "userConsent": True}


class DomainsAPI(BaseAPI):
    """Domain availability, registration, renewal, transfer and settings."""

    # -- availability --
    def check(self, *domains: str, include_pricing: bool = True) -> list[DomainCheck]:  # noqa: ARG002
        """Check availability; premium pricing included when the API returns it.

        ``POST /v1/domains/available`` only populates ``premiumPricing`` for
        premium domains — standard domains come back with an empty list, so
        ``DomainCheck.price``/``.currency`` are ``None``/``""`` for them even
        when available. Callers must handle priceless available domains
        (no register price known) instead of assuming a price is present.

        Batches of up to 20 domains per request.
        """
        names = [to_punycode(d) for d in domains if (d or "").strip()]
        out: list[DomainCheck] = []
        for i in range(0, len(names), CHECK_BATCH_SIZE):
            data = self._request("POST", "/domains/available", json={"domains": names[i : i + CHECK_BATCH_SIZE]})
            rows = (data or {}).get("domains", []) if isinstance(data, dict) else []
            out.extend(DomainCheck.model_validate(r) for r in rows if isinstance(r, dict))
        return out

    def check_single(self, domain: str) -> DomainCheck:
        """Check a single domain (``GET /v1/domains/{domain}/available``)."""
        data = self._request("GET", f"/domains/{to_punycode(domain)}/available")
        return DomainCheck.model_validate(data if isinstance(data, dict) else {"domain": domain})

    # -- listing / info --
    def list(self, *, page: int = 1, page_size: int = 20) -> list[Domain]:
        """List domains in the account (``take``/``skip`` pagination)."""
        size = max(1, min(int(page_size), 100))
        data = self._request("GET", "/domains", params={"take": size, "skip": (max(page, 1) - 1) * size})
        rows = (data or {}).get("items", []) if isinstance(data, dict) else []
        return [Domain.model_validate(r) for r in rows if isinstance(r, dict)]

    def get_info(self, domain: str) -> Domain:
        """Detailed info about a domain (status, dates, nameservers, contacts)."""
        data = self._request("GET", f"/domains/{to_punycode(domain)}")
        return Domain.model_validate(data if isinstance(data, dict) else {"name": domain})

    get = get_info

    # -- contacts helpers --
    def _resolve_contact_ids(self, contact: Contact | dict[str, Any]) -> dict[str, Any]:
        """Contact fields -> ``{registrant, admin, tech, billing}`` id mapping.

        A ``Contact`` (or field dict) is saved once and mirrored into all
        four roles; a dict that already holds role ids is used as-is.
        """
        if isinstance(contact, dict) and any(contact.get(role) for role in ("registrant", "admin", "tech", "billing")):
            out = {role: str(contact.get(role) or "") for role in ("registrant", "admin", "tech", "billing")}
            if contact.get("attributes"):
                out["attributes"] = contact["attributes"]
            return out
        contact_id = ContactsAPI(self._client).ensure(contact)
        return {
            "registrant": contact_id,
            "admin": contact_id,
            "tech": contact_id,
            "billing": contact_id,
        }

    # -- registration / renewal / restore --
    def register(
        self,
        domain: str,
        *,
        contact: Contact | dict[str, Any],
        years: int = 1,
        auto_renew: bool = False,
        whois_protection: bool | None = True,
        nameservers: list[str] | None = None,
        wait: bool = True,
        timeout: float = 300.0,
        poll_interval: float = 5.0,
    ) -> Domain | AsyncOperation:
        """Register a domain (charges the account).

        Blocks until the async operation finishes by default (returns the
        fresh ``Domain``); with ``wait=False`` returns the pending
        ``AsyncOperation`` immediately. ``nameservers`` (custom hosts) are
        applied after registration completes.
        """
        name = to_punycode(domain)
        body: dict[str, Any] = {
            "autoRenew": bool(auto_renew),
            "years": int(years),
            "contacts": self._resolve_contact_ids(contact),
        }
        privacy = _privacy_payload(whois_protection)
        if privacy is not None:
            body["privacyProtection"] = privacy
        response = self._request_raw("POST", f"/domains/{name}", json=body)
        op_id = self._async_operation_id(response)
        if not wait:
            return self._client.operations.get(op_id)
        self._client.operations.wait_for(op_id, timeout=timeout, poll_interval=poll_interval)
        info = self.get_info(name)
        if nameservers:
            self.set_nameservers(name, nameservers)
            info = self.get_info(name)
        return info

    def renew(
        self,
        domain: str,
        *,
        years: int = 1,
        current_expiration_date: str | None = None,
        wait: bool = True,
        timeout: float = 300.0,
        poll_interval: float = 5.0,
    ) -> Domain | AsyncOperation:
        """Renew a domain. ``currentExpirationDate`` is fetched when omitted."""
        name = to_punycode(domain)
        if current_expiration_date is None:
            info = self.get_info(name)
            current_expiration_date = info.expiration_date.isoformat() if info.expiration_date else ""
        response = self._request_raw(
            "POST",
            f"/domains/{name}/renew",
            json={"years": int(years), "currentExpirationDate": current_expiration_date},
        )
        op_id = self._async_operation_id(response)
        if not wait:
            return self._client.operations.get(op_id)
        self._client.operations.wait_for(op_id, timeout=timeout, poll_interval=poll_interval)
        return self.get_info(name)

    def restore(self, domain: str, *, wait: bool = True, timeout: float = 300.0, poll_interval: float = 5.0) -> Any:
        """Request domain restoration (redemption)."""
        name = to_punycode(domain)
        response = self._request_raw("POST", f"/domains/{name}/restore")
        op_id = self._async_operation_id(response)
        if not wait:
            return self._client.operations.get(op_id)
        return self._client.operations.wait_for(op_id, timeout=timeout, poll_interval=poll_interval)

    # -- transfer --
    def transfer(
        self,
        domain: str,
        *,
        contact: Contact | dict[str, Any],
        auth_code: str | None = None,
        auto_renew: bool = False,
        whois_protection: bool | None = True,
        wait: bool = True,
        timeout: float = 300.0,
        poll_interval: float = 5.0,
    ) -> Domain | AsyncOperation:
        """Transfer a domain in (charges the account)."""
        name = to_punycode(domain)
        body: dict[str, Any] = {
            "autoRenew": bool(auto_renew),
            "contacts": self._resolve_contact_ids(contact),
        }
        privacy = _privacy_payload(whois_protection)
        if privacy is not None:
            body["privacyProtection"] = privacy
        if auth_code:
            body["authCode"] = auth_code
        response = self._request_raw("POST", f"/domains/{name}/transfer", json=body)
        op_id = self._async_operation_id(response)
        if not wait:
            return self._client.operations.get(op_id)
        self._client.operations.wait_for(op_id, timeout=timeout, poll_interval=poll_interval)
        return self.get_info(name)

    def transfer_info(self, domain: str) -> Any:
        """Transfer details for a domain."""
        return self._request("GET", f"/domains/{to_punycode(domain)}/transfer")

    def get_auth_code(self, domain: str) -> str:
        """EPP auth code for a domain (for transferring it away)."""
        data = self._request("GET", f"/domains/{to_punycode(domain)}/transfer/auth-code")
        payload = data if isinstance(data, dict) else {}
        return str(payload.get("authCode") or "")

    def set_lock(self, domain: str, locked: bool) -> bool:
        """Set the transfer lock; returns the resulting state."""
        data = self._request("PUT", f"/domains/{to_punycode(domain)}/transfer/lock", json={"isLocked": bool(locked)})
        payload = data if isinstance(data, dict) else {}
        return bool(payload.get("isLocked", locked))

    def lock(self, domain: str):
        """Enable the transfer lock."""
        return self.set_lock(domain, True)

    def unlock(self, domain: str):
        """Disable the transfer lock."""
        return self.set_lock(domain, False)

    # -- settings --
    def set_autorenew(self, domain: str, enabled: bool) -> bool:
        """Set the autorenewal state; returns the resulting state."""
        data = self._request("PUT", f"/domains/{to_punycode(domain)}/autorenew", json={"isEnabled": bool(enabled)})
        payload = data if isinstance(data, dict) else {}
        return bool(payload.get("isEnabled", enabled))

    def get_contacts(self, domain: str) -> dict[str, Any]:
        """Contact IDs attached to a domain."""
        return self.get_info(domain).contacts.model_dump()

    def set_contacts(self, domain: str, contacts: dict[str, Any]) -> Any:
        """Replace the contact IDs attached to a domain."""
        return self._request("PUT", f"/domains/{to_punycode(domain)}/contacts", json=dict(contacts))

    def set_nameservers(self, domain: str, hosts: list[str] | None) -> Any:
        """Point a domain at custom nameservers (or back to ``basic``)."""
        if not hosts:
            return self._request("PUT", f"/domains/{to_punycode(domain)}/nameservers", json={"provider": "basic"})
        return self._request(
            "PUT",
            f"/domains/{to_punycode(domain)}/nameservers",
            json={"provider": "custom", "hosts": list(hosts)},
        )

    def get_nameservers(self, domain: str) -> list[str]:
        """Nameserver hosts for a domain (``basic`` provider yields ``[]``)."""
        return list(self.get_info(domain).nameservers.hosts or [])

    def set_privacy(self, level: str, domain: str, *, user_consent: bool = True) -> Any:
        """Set privacy preference (``public`` or ``high``)."""
        return self._request(
            "PUT",
            f"/domains/{to_punycode(domain)}/privacy/preference",
            json={"privacyLevel": level, "userConsent": bool(user_consent)},
        )

    def set_email_protection(self, domain: str, *, contact_form: bool) -> Any:
        """Set the WHOIS email protection (contact-form) preference."""
        return self._request(
            "PUT",
            f"/domains/{to_punycode(domain)}/privacy/email-protection-preference",
            json={"contactForm": bool(contact_form)},
        )

    def get_tld_list(self) -> list:
        raise NotSupportedError(
            "get_tld_list() has no Spaceship endpoint.",
            alternative="Derive supported TLDs from availability checks.",
        )

    def suggest(self, domain: str, **params: Any) -> list:
        raise NotSupportedError(
            f"suggest({domain}) has no Spaceship endpoint.",
            alternative="Fan check() out over candidate FQDNs instead.",
        )
