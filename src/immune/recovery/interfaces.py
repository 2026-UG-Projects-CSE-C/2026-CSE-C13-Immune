"""Interfaces required by the order recovery controller."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from immune.core.context import ExecutionContext
from immune.models.order_lab import Address, Customer, Order


class OrderTaskReadView(Protocol):
    def read_customer(self, customer_id: str) -> Customer | None: ...
    def read_addresses(self, customer_id: str) -> list[Address]: ...
    def read_order(self, order_id: str) -> Order | None: ...
    def order_update_count(self, order_id: str) -> int: ...


class RuntimeToolResponse(Protocol):
    ok: bool
    value: object | None


class OrderTaskRuntime(Protocol):
    def get_addresses(
        self, customer_id: str, *, context: ExecutionContext | None = None
    ) -> object: ...
    def get_order(
        self, order_id: str, *, context: ExecutionContext | None = None
    ) -> object: ...
    def update_order_shipping_address(
        self, order_id: str, address_id: str, *, context: ExecutionContext | None = None
    ) -> object: ...
    def verification_view(self) -> AbstractContextManager[OrderTaskReadView]: ...
