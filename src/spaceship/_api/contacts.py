"""Contact management (``/v1/contacts``)."""

from __future__ import annotations

from typing import Any

from ..models import Contact
from .base import BaseAPI


class ContactsAPI(BaseAPI):
    """Save and read contact details (returns IDs used by domain operations)."""

    def save(self, contact: Contact | dict[str, Any]) -> str:
        """Create a contact; returns its ID.

        Rate limit: documented per-account limits apply; validation rules
        for ``stateProvince``/``postalCode`` depend on ``country``.
        """
        fields = contact.api_fields() if isinstance(contact, Contact) else dict(contact)
        data = self._request("PUT", "/contacts", json=fields)
        payload = data if isinstance(data, dict) else {}
        for key in ("id", "contactId", "contact_id"):
            if payload.get(key):
                return str(payload[key])
        # Some responses nest the created object.
        for value in payload.values():
            if isinstance(value, dict):
                for key in ("id", "contactId", "contact_id"):
                    if value.get(key):
                        return str(value[key])
        raise ValueError(f"Contact save did not return an id: {payload!r}")

    def read(self, contact_id: str) -> Contact:
        """Read contact details by ID."""
        data = self._request("GET", f"/contacts/{contact_id}")
        return Contact.from_api(data if isinstance(data, dict) else {})

    def ensure(self, contact: Contact | dict[str, Any]) -> str:
        """Return a usable contact ID: verify a given ID or save new details."""
        if isinstance(contact, Contact) and contact.id:
            return self.read(contact.id).id or contact.id
        if isinstance(contact, dict):
            for key in ("id", "contactId", "contact_id"):
                if contact.get(key):
                    return self.read(str(contact[key])).id or str(contact[key])
        return self.save(contact)

    def save_attributes(self, attributes: dict[str, Any]) -> Any:
        """Save extended (TLD-specific) contact attributes (thin passthrough)."""
        return self._request("PUT", "/contacts/attributes", json=attributes)

    def get_attributes(self, contact_id: str) -> Any:
        """Read extended contact attributes."""
        return self._request("GET", f"/contacts/attributes/{contact_id}")
