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
