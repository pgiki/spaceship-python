"""DNS record management (``/v1/dns/records/{domain}``).

The API is whole-zone oriented (PUT replaces the zone); single-record
helpers below are read-modify-write over ``get`` + ``set``.
"""

from __future__ import annotations

from typing import Any

from ..models import DNSRecord
from .base import BaseAPI

#: Page size for GET list pagination.
PAGE_SIZE = 100


class DnsAPI(BaseAPI):
    """DNS resource records for domains on Spaceship nameservers."""

    @staticmethod
    def _short_name(name: str, zone: str) -> str:
        n = (name or "").strip().rstrip(".").lower()
        z = zone.strip().rstrip(".").lower()
        if not n or n == "@" or n == z:
            return "@"
        if n.endswith("." + z):
            return n[: -(len(z) + 1)]
        return n

    def get(self, zone: str, *, page: int = 1, page_size: int = PAGE_SIZE) -> list[DNSRecord]:
        """One page of records for a zone."""
        data = self._request(
            "GET",
            f"/dns/records/{zone.strip().rstrip('.')}",
            params={"take": max(1, min(int(page_size), 500)), "skip": (max(page, 1) - 1) * int(page_size)},
        )
        rows = (data or {}).get("items", []) if isinstance(data, dict) else []
        return [DNSRecord.model_validate(r) for r in rows if isinstance(r, dict)]

    def list(self, zone: str) -> list[DNSRecord]:
        """All records for a zone (auto-paginates)."""
        out: list[DNSRecord] = []
        page = 1
        while True:
            rows = self.get(zone, page=page)
            out.extend(rows)
            if len(rows) < PAGE_SIZE:
                break
            page += 1
        return out

    def set(self, zone: str, records: list[DNSRecord | dict[str, Any]], *, force: bool = True) -> None:
        """Replace the whole zone (204 on success)."""
        items = [r.to_api() if isinstance(r, DNSRecord) else dict(r) for r in records]
        self._request(
            "PUT",
            f"/dns/records/{zone.strip().rstrip('.')}",
            json={"force": bool(force), "items": items},
        )

    def add(self, zone: str, record: DNSRecord | dict[str, Any]) -> DNSRecord:
        """Append one record (read-modify-write); returns the added record."""
        new = record if isinstance(record, DNSRecord) else DNSRecord.model_validate(dict(record))
        rows = self.list(zone)
        rows.append(new)
        self.set(zone, rows)
        return new

    def delete(
        self,
        zone: str,
        *,
        name: str | None = None,
        record_type: str | None = None,
        value: str | None = None,
    ) -> int:
        """Delete matching records (read-modify-write); returns deleted count.

        ``name`` accepts FQDN or relative form (``@`` for apex). Matching is
        case-insensitive, like the API (TXT excepted upstream).
        """
        zone = zone.strip().rstrip(".")
        short = self._short_name(name, zone) if name else None
        rows = self.list(zone)
        keep: list[DNSRecord] = []
        doomed: list[DNSRecord] = []
        for rec in rows:
            if short is not None and rec.name.lower() != short:
                keep.append(rec)
                continue
            if record_type is not None and rec.type.upper() != record_type.upper():
                keep.append(rec)
                continue
            if value is not None and (rec.address or "") != value:
                keep.append(rec)
                continue
            if short is None and record_type is None and value is None:
                keep.append(rec)
                continue
            doomed.append(rec)
        if not doomed:
            return 0
        self.set(zone, keep)
        return len(doomed)

    def delete_exact(self, zone: str, records: list[DNSRecord | dict[str, Any]]) -> None:
        """Delete exact records via the API endpoint (204 on success)."""
        items = []
        for r in records:
            rec = r if isinstance(r, DNSRecord) else DNSRecord.model_validate(dict(r))
            item = {"type": rec.type.upper(), "name": rec.name or "@"}
            if rec.address:
                item["address"] = rec.address
            items.append(item)
        if items:
            self._request("DELETE", f"/dns/records/{zone.strip().rstrip('.')}", json={"records": items})

    # -- fikashop-style record conveniences --
    def create_record(
        self,
        zone: str,
        name: str,
        record_type: str,
        content: str,
        ttl: int | None = None,
        *,
        prio: int = 0,
        port: Any = None,
        weight: Any = None,
    ) -> DNSRecord:
        """Create one record; returns it in API form."""
        return self.add(
            zone,
            DNSRecord(
                type=record_type.upper(),
                name=self._short_name(name, zone),
                address=content,
                ttl=ttl,
                priority=int(prio) if record_type.upper() == "MX" else None,
                port=int(port) if port not in (None, "") else None,
                weight=int(weight) if weight not in (None, "") else None,
            ),
        )

    def set_a_records(
        self,
        zone: str,
        domain: str,
        ip: str,
        include_www: bool = True,
        include_wildcard: bool = False,
        ttl: int | None = None,
    ) -> list[DNSRecord]:
        """Replace A records for ``domain`` (+www/wildcard) with ``ip``."""
        zone = zone.strip().rstrip(".")
        names = {self._short_name(domain, zone)}
        if include_www:
            names.add(self._short_name(f"www.{domain.rstrip('.')}", zone))
        if include_wildcard:
            names.add(self._short_name(f"*.{domain.rstrip('.')}", zone))
        rows = [r for r in self.list(zone) if not (r.type.upper() == "A" and r.name.lower() in names)]
        for short in sorted(names):
            rows.append(DNSRecord(type="A", name=short, address=ip, ttl=ttl))
        self.set(zone, rows)
        return self.list(zone)
