"""Async operation tracking (``GET /v1/async-operations/{id}``)."""

from __future__ import annotations

import time

from ..errors import AsyncOperationError
from ..models import AsyncOperation
from .base import BaseAPI


class OperationsAPI(BaseAPI):
    """Poll long-running operations to completion."""

    def get(self, operation_id: str) -> AsyncOperation:
        """Fetch the current state of an async operation."""
        data = self._request("GET", f"/async-operations/{operation_id}")
        payload = data if isinstance(data, dict) else {}
        return AsyncOperation.model_validate({"id": operation_id, **payload})

    def wait_for(
        self,
        operation_id: str,
        *,
        timeout: float = 300.0,
        poll_interval: float = 5.0,
    ) -> AsyncOperation:
        """Block until the operation succeeds, fails, or times out.

        Returns the final operation on success. Raises
        :class:`AsyncOperationError` when the operation fails and
        :class:`TimeoutError` when the timeout expires.
        """
        deadline = time.monotonic() + max(timeout, 0)
        last: AsyncOperation | None = None
        while True:
            last = self.get(operation_id)
            if last.status == "success":
                return last
            if last.status == "failed":
                raise AsyncOperationError(operation_id, last.details)
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Async operation {operation_id} did not finish "
                    f"within {timeout:.0f}s."
                )
            time.sleep(max(poll_interval, 0))
