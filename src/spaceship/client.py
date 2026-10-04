"""Main Spaceship client."""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

import httpx

from .config import Config
from .errors import ConfigurationError
from .logging import set_log_level

if TYPE_CHECKING:
    from typing import Self

    from ._api.contacts import ContactsAPI
    from ._api.domains import DomainsAPI
    from ._api.operations import OperationsAPI


class Spaceship:
    """
    The main Spaceship client.

    Examples:
        >>> sp = Spaceship()  # Loads SPACESHIP_API_KEY/SECRET from environment
        >>> sp = Spaceship(api_key="...", api_secret="...")  # Explicit
        >>> sp = Spaceship.from_env_file(".env.prod")  # From specific env file

        >>> # Check domain availability (free endpoint)
        >>> sp.domains.check("example.com")

        >>> # Use as context manager
        >>> with Spaceship() as sp:
        ...     op = sp.operations.get("abc123")
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_secret: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        log_level: str | None = None,
    ) -> None:
        """
        Initialize the Spaceship client with smart defaults.

        Args:
            api_key: Spaceship API key (or set SPACESHIP_API_KEY env var)
            api_secret: Spaceship API secret (or set SPACESHIP_API_SECRET env var)
            base_url: API base URL (default: https://spaceship.dev/api/v1)
            timeout: Request timeout in seconds (default: 30.0)
            log_level: Logging level (default: INFO)

        Raises:
            ConfigurationError: If required configuration is missing
        """
        try:
            self.config = Config.from_env(
                api_key=api_key,
                api_secret=api_secret,
                base_url=base_url,
                timeout=timeout,
                log_level=log_level,
            )
            set_log_level(self.config.log_level)
        except Exception as e:
            raise ConfigurationError(
                "Failed to load configuration. Ensure you have set:\n"
                "- SPACESHIP_API_KEY\n"
                "- SPACESHIP_API_SECRET\n"
                "Or pass them as parameters to the client."
            ) from e

        self._http = httpx.Client(timeout=self.config.timeout)

    @classmethod
    def from_env_file(cls, path: str = ".env") -> Self:
        """Create a client from a specific env file."""
        from dotenv import load_dotenv

        load_dotenv(path)
        return cls()

    @cached_property
    def operations(self) -> OperationsAPI:
        """Async operation tracking."""
        from ._api.operations import OperationsAPI

        return OperationsAPI(self)

    @cached_property
    def domains(self) -> DomainsAPI:
        """Domain availability, registration, renewal and transfer."""
        from ._api.domains import DomainsAPI

        return DomainsAPI(self)

    @cached_property
    def contacts(self) -> ContactsAPI:
        """Contact save/read (IDs used by domain operations)."""
        from ._api.contacts import ContactsAPI

        return ContactsAPI(self)

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"<Spaceship(base_url={self.config.base_url!r})>"
