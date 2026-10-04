"""Spaceship API error handling."""

from __future__ import annotations

from typing import Any


class SpaceshipError(Exception):
    """Base exception for all Spaceship API errors."""

    def __init__(
        self,
        message: str,
        status_code: int = 0,
        code: str | None = None,
        details: Any | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.code = code or ""
        self.details = details
        # Aliases matching the sibling SDKs' error shapes.
        self.response_text = message
        super().__init__(str(self))

    def __str__(self) -> str:
        prefix = f"Spaceship API error {self.status_code}" if self.status_code else "Spaceship API error"
        if self.code:
            return f"{prefix} [{self.code}]: {self.message}"
        return f"{prefix}: {self.message}"

    @classmethod
    def from_response(cls, status_code: int, data: Any) -> SpaceshipError:
        """Build an error from a JSON body (``application/problem+json`` or plain)."""
        if isinstance(data, dict):
            message = (
                data.get("detail")
                or data.get("message")
                or data.get("title")
                or f"HTTP {status_code}"
            )
            code = data.get("code") or data.get("type")
            return cls(str(message), status_code, code, data)
        return cls(str(data) if data else f"HTTP {status_code}", status_code, None, data)


class ConfigurationError(Exception):
    """Raised when client configuration is invalid."""

    pass


class NotSupportedError(Exception):
    """Raised when an operation has no Spaceship endpoint.

    Carries an ``alternative`` hint pointing at the supported way to
    achieve the same result.
    """

    def __init__(self, message: str, alternative: str = "") -> None:
        self.alternative = alternative
        super().__init__(f"{message} Alternative: {alternative}" if alternative else message)


class AsyncOperationError(SpaceshipError):
    """A polled async operation finished with ``failed`` status."""

    def __init__(self, operation_id: str, details: Any | None = None) -> None:
        self.operation_id = operation_id
        super().__init__(
            f"Async operation {operation_id} failed.",
            0,
            "async_operation_failed",
            details,
        )
