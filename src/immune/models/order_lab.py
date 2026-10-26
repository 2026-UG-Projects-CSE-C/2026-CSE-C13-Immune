"""Domain entities for the deterministic order-management lab."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class OrderStatus(StrEnum):
    """Statuses supported by the simulated order system."""

    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    SHIPPED = "SHIPPED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class Customer:
    customer_id: str
    name: str


@dataclass(frozen=True, slots=True)
class Address:
    address_id: str
    customer_id: str
    street: str
    city: str
    version: int
    is_current: bool


@dataclass(frozen=True, slots=True)
class Order:
    order_id: str
    customer_id: str
    shipping_address_id: str
    status: OrderStatus
    version: int
