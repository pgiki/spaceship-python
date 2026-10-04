"""Base transport for all Spaceship endpoint groups."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from ..errors import SpaceshipError
from ..logging import get_logger

if TYPE_CHECKING:
    from ..client import Spaceship

logger = get_logger("api")

#: Header carrying the async operation id on 202 responses.
ASYNC_OPERATION_HEADER = "spaceship-async-operationid"


class BaseAPI:
    """Shared request handling: auth headers, error mapping, 202 capture."""

    def __init__(self, client: Spaceship) -> None:
        self._client = client

    @property
    def _http(self) -> httpx.Client:
        return self._client._http

    def _url(self, path: str) -> str:
        base = self._client.config.base_url.rstrip("/")
        return f"{base}/{path.lstrip('/')}"

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "X-Api-Key": self._client.config.api_key,
            "X-Api-Secret": self._client.config.api_secret,
            "Accept": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def _raise_for_response(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        try:
            data = response.json()
        except Exception:
            data = response.text
        raise SpaceshipError.from_response(response.status_code, data)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
    ) -> Any:
        """Send a request and return the decoded JSON body (2xx only)."""
        try:
            response = self._http.request(
                method, self._url(path), params=params, json=json,
                headers=self._headers({"Content-Type": "application/json"} if json is not None else None),
            )
        except SpaceshipError:
            raise
        except Exception as e:
            raise SpaceshipError(f"Request failed: {e}") from e
        if response.status_code == 202:
            # Async operations carry no JSON body; callers use _request_raw.
            return None
        self._raise_for_response(response)
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except Exception as e:
            raise SpaceshipError(f"Invalid JSON response: {e}", response.status_code) from e

    def _request_raw(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
    ) -> httpx.Response:
        """Send a request and return the raw response (for 202 header capture)."""
        try:
            response = self._http.request(
                method, self._url(path), params=params, json=json,
                headers=self._headers({"Content-Type": "application/json"} if json is not None else None),
            )
        except Exception as e:
            raise SpaceshipError(f"Request failed: {e}") from e
        self._raise_for_response(response)
        return response

    def _async_operation_id(self, response: httpx.Response) -> str:
        op_id = response.headers.get(ASYNC_OPERATION_HEADER, "")
        if not op_id:
            raise SpaceshipError(
                "Expected 202 async operation response without "
                f"'{ASYNC_OPERATION_HEADER}' header.",
                response.status_code,
            )
        return op_id
