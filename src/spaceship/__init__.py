"""spaceship-python — a friendly Python SDK for the Spaceship API.

Example:
    >>> from spaceship import Spaceship
    >>> sp = Spaceship()  # auto-loads SPACESHIP_API_KEY/SECRET from environment
    >>> checks = sp.domains.check("example.com", "myproject.dev")
    >>> [c.price for c in checks if c.available]
"""

from __future__ import annotations

from .client import Spaceship
from .config import Config
from .errors import (
    AsyncOperationError,
    ConfigurationError,
    NotSupportedError,
    SpaceshipError,
)
from .models import (
    AsyncOperation,
    Contact,
    DNSRecord,
    Domain,
    DomainCheck,
    DomainContacts,
    DomainNameservers,
    DomainPrice,
    DomainPrivacy,
)

__version__ = "0.1.0"
__all__ = [
    "AsyncOperation",
    "AsyncOperationError",
    "Config",
    "ConfigurationError",
    "Contact",
    "DNSRecord",
    "Domain",
    "DomainCheck",
    "DomainContacts",
    "DomainNameservers",
    "DomainPrice",
    "DomainPrivacy",
    "NotSupportedError",
    "Spaceship",
    "SpaceshipError",
]
