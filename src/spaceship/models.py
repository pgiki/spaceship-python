"""Pydantic models for Spaceship API responses."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AsyncOperationStatus = Literal["pending", "success", "failed"]


class SpaceshipModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True, extra="allow")


class AsyncOperation(SpaceshipModel):
    """A long-running operation (``spaceship-async-operationid``)."""

    id: str = ""
    status: AsyncOperationStatus = "pending"
    type: str = ""
    details: Any = None
    created_at: datetime | None = Field(default=None, alias="createdAt")
    modified_at: datetime | None = Field(default=None, alias="modifiedAt")

    @property
    def done(self) -> bool:
        return self.status in ("success", "failed")

    @property
    def succeeded(self) -> bool:
        return self.status == "success"


class DomainPrice(SpaceshipModel):
    """A priced operation for a domain (availability ``premiumPricing``)."""

    operation: str = ""
    price: Decimal | None = None
    currency: str = ""

    @field_validator("price", mode="before")
    @classmethod
    def _parse_price(cls, v: Any) -> Decimal | None:
        if v is None or v == "":
            return None
        try:
            return Decimal(str(v))
        except Exception:
            return None


class DomainCheck(SpaceshipModel):
    """Availability result for one domain (``POST /v1/domains/available``)."""

    domain: str = ""
    result: str = ""
    premium_pricing: list[DomainPrice] = Field(default_factory=list, alias="premiumPricing")

    @property
    def available(self) -> bool:
        return self.result.strip().lower() == "available"

    @property
    def premium(self) -> bool:
        return bool(self.premium_pricing)

    @property
    def price(self) -> Decimal | None:
        """Best register price: first ``register`` entry, else first entry."""
        for entry in self.premium_pricing:
            if entry.operation.strip().lower() == "register":
                return entry.price
        return self.premium_pricing[0].price if self.premium_pricing else None

    @property
    def currency(self) -> str:
        for entry in self.premium_pricing:
            if entry.operation.strip().lower() == "register" and entry.currency:
                return entry.currency
        return self.premium_pricing[0].currency if self.premium_pricing else ""


class DomainPrivacy(SpaceshipModel):
    contact_form: bool = Field(default=False, alias="contactForm")
    level: str = ""


class DomainNameservers(SpaceshipModel):
    provider: str = ""
    hosts: list[str] = Field(default_factory=list)


class DomainContacts(SpaceshipModel):
    """Contact IDs attached to a domain (registrant/admin/tech/billing)."""

    registrant: str = ""
    admin: str = ""
    tech: str = ""
    billing: str = ""
    attributes: list[str] = Field(default_factory=list)


class Domain(SpaceshipModel):
    """A domain in the account (list/get info shapes)."""

    name: str = ""
    unicode_name: str = Field(default="", alias="unicodeName")
    is_premium: bool = Field(default=False, alias="isPremium")
    auto_renew: bool = Field(default=False, alias="autoRenew")
    registration_date: datetime | None = Field(default=None, alias="registrationDate")
    expiration_date: datetime | None = Field(default=None, alias="expirationDate")
    lifecycle_status: str = Field(default="", alias="lifecycleStatus")
    verification_status: str = Field(default="", alias="verificationStatus")
    epp_statuses: list[str] = Field(default_factory=list, alias="eppStatuses")
    privacy: DomainPrivacy = Field(default_factory=DomainPrivacy, alias="privacyProtection")
    nameservers: DomainNameservers = Field(default_factory=DomainNameservers)
    contacts: DomainContacts = Field(default_factory=DomainContacts)


class Contact(SpaceshipModel):
    """A contact person (``PUT /v1/contacts`` fields + id when known)."""

    id: str = ""
    first_name: str = Field(default="", alias="firstName")
    last_name: str = Field(default="", alias="lastName")
    organization: str | None = None
    email: str = ""
    address1: str = ""
    address2: str | None = None
    city: str = ""
    country: str = ""
    state_province: str | None = Field(default=None, alias="stateProvince")
    postal_code: str | None = Field(default=None, alias="postalCode")
    phone: str = ""
    phone_ext: str | None = Field(default=None, alias="phoneExt")
    fax: str | None = None
    fax_ext: str | None = Field(default=None, alias="faxExt")
    tax_number: str | None = Field(default=None, alias="taxNumber")

    def api_fields(self) -> dict[str, Any]:
        """Field payload for ``PUT /v1/contacts`` (alias names, no empties)."""
        data = self.model_dump(by_alias=True, exclude_none=True)
        data.pop("id", None)
        data.pop("contactId", None)
        return {k: v for k, v in data.items() if v not in ("", None)}

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Contact:
        """Parse a contact payload accepting ``id`` or ``contactId``."""
        data = dict(data or {})
        if not data.get("id") and data.get("contactId"):
            data["id"] = data.pop("contactId")
        return cls.model_validate(data)


class DNSRecord(SpaceshipModel):
    """A DNS resource record (API form: ``@`` apex, otherwise relative names)."""

    type: str = ""
    name: str = "@"
    address: str | None = None
    ttl: int | None = None
    priority: int | None = None
    port: int | None = None
    weight: int | None = None
    service: str | None = None
    protocol: str | None = None
    flag: int | None = None
    tag: str | None = None

    @field_validator("type", mode="before")
    @classmethod
    def _upper(cls, v: Any) -> Any:
        return str(v).upper() if v else v

    def fqdn(self, zone: str) -> str:
        """Fully qualified name of this record inside ``zone``."""
        z = zone.strip().rstrip(".").lower()
        n = (self.name or "").strip().rstrip(".")
        if not n or n == "@" or n.lower() == z:
            return z
        if n.lower().endswith("." + z):
            return n.lower()
        return f"{n}.{z}".lower()

    def to_api(self) -> dict[str, Any]:
        """PUT-item payload (alias names, no empties)."""
        data: dict[str, Any] = {"type": self.type.upper(), "name": self.name or "@"}
        for key in ("address", "ttl", "priority", "port", "weight",
                    "service", "protocol", "flag", "tag"):
            value = getattr(self, key)
            if value not in (None, ""):
                data[key] = value
        return data
