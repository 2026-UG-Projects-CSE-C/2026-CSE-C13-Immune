"""Deterministic SQLite-backed order-management environment and tools."""

from __future__ import annotations

import sqlite3
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar, cast

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Connection

from immune.core.context import ExecutionContext
from immune.core.errors import VerificationReadError
from immune.core.events import EventStatus, EventType
from immune.core.run_context import RunContext
from immune.faults.injector import FaultInjector
from immune.models.order_lab import Address, Customer, Order, OrderStatus
from immune.telemetry.event_store import EventConflictError, EventStore
from immune.telemetry.hashing import sha256_json
from immune.telemetry.lab_events import LabEventRecorder, json_value
from immune.telemetry.sqlite_config import open_read_only, sqlite_path

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ToolResult(Generic[T]):
    """Structured result separating tool execution from semantic correctness."""

    ok: bool
    value: T | None
    error_code: str | None
    message: str


class ScenarioStateError(RuntimeError):
    """Raised when a scenario database is not fresh and isolated."""


class OrderVerificationView(AbstractContextManager["OrderVerificationView"]):
    """Read-only state interface backed by a separate SQLite read-only handle."""

    def __init__(self, database_url: str) -> None:
        path = sqlite_path(database_url)
        if path == ":memory:":
            raise VerificationReadError(
                "read-only verification requires a file-backed SQLite database"
            )
        try:
            self._connection = open_read_only(database_url)
        except sqlite3.Error as error:
            raise VerificationReadError(
                "verification database is unavailable"
            ) from error

    def read_customer(self, customer_id: str) -> Customer | None:
        row = self._read_one(
            "SELECT customer_id, name FROM customers WHERE customer_id = ?",
            (customer_id,),
        )
        return None if row is None else Customer(row["customer_id"], row["name"])

    def read_addresses(self, customer_id: str) -> list[Address]:
        rows = self._read_all(
            """
            SELECT address_id, customer_id, street, city, version, is_current
            FROM addresses WHERE customer_id = ? ORDER BY address_id
            """,
            (customer_id,),
        )
        return [
            Address(
                row["address_id"],
                row["customer_id"],
                row["street"],
                row["city"],
                row["version"],
                bool(row["is_current"]),
            )
            for row in rows
        ]

    def read_order(self, order_id: str) -> Order | None:
        row = self._read_one(
            """
            SELECT order_id, customer_id, shipping_address_id, status, version
            FROM orders WHERE order_id = ?
            """,
            (order_id,),
        )
        return (
            None
            if row is None
            else Order(
                row["order_id"],
                row["customer_id"],
                row["shipping_address_id"],
                OrderStatus(row["status"]),
                row["version"],
            )
        )

    def order_update_count(self, order_id: str) -> int:
        row = self._read_one(
            "SELECT COUNT(*) AS update_count FROM order_update_history WHERE order_id = ?",
            (order_id,),
        )
        if row is None:
            raise VerificationReadError("update history count could not be read")
        return int(row["update_count"])

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> OrderVerificationView:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _read_one(self, query: str, parameters: tuple[str, ...]) -> sqlite3.Row | None:
        try:
            return cast(
                sqlite3.Row | None,
                self._connection.execute(query, parameters).fetchone(),
            )
        except sqlite3.Error as error:
            raise VerificationReadError("verification read failed") from error

    def _read_all(self, query: str, parameters: tuple[str, ...]) -> list[sqlite3.Row]:
        try:
            return self._connection.execute(query, parameters).fetchall()
        except sqlite3.Error as error:
            raise VerificationReadError("verification read failed") from error


class OrderManagementEnvironment:
    """The seeded deterministic environment exposed through order tools."""

    def __init__(
        self,
        database_url: str,
        recorder: LabEventRecorder,
        fault_injector: FaultInjector | None = None,
        event_store: EventStore | None = None,
        execution_context: ExecutionContext | None = None,
        run_context: RunContext | None = None,
        seed: bool = True,
    ) -> None:
        self._owns_event_store = event_store is None
        self._event_store = event_store or EventStore(database_url)
        self._run_context = run_context or RunContext(recorder.run_id, recorder.run_id)
        if self._run_context.run_id != recorder.run_id:
            raise ValueError("environment RunContext does not match recorder")
        if (
            self._event_store.context is not None
            and self._event_store.context != self._run_context
        ):
            raise ValueError("environment RunContext does not match EventStore")
        if self._owns_event_store:
            self._event_store.initialize()
        if self._event_store.database_url != database_url:
            raise ValueError(
                "environment and event store must use the same database URL"
            )
        self._event_store.bind_context(self._run_context)
        self._recorder = recorder
        self._fault_injector = fault_injector
        self._default_context = execution_context or ExecutionContext(
            recorder.run_id, "environment"
        )
        self._metadata, self._tables = _state_tables()
        if seed:
            self.initialize()
        else:
            self._metadata.create_all(self._event_store._engine)

    def initialize(self) -> None:
        """Create and seed a fresh canonical scenario; never inherit state."""
        self._metadata.create_all(self._event_store._engine)
        with self._event_store.transaction() as connection:
            existing = [
                connection.execute(select(table)).first() for table in self._tables
            ]
            if any(row is not None for row in existing):
                raise ScenarioStateError(
                    "scenario database is not fresh; create a new run-scoped database"
                )
            if self._event_store.total_count() != 0:
                raise ScenarioStateError(
                    "event history already exists in this database"
                )
            connection.execute(
                insert(self._tables[0]).values(customer_id="C001", name="Ada Lovelace")
            )
            connection.execute(
                insert(self._tables[1]),
                [
                    {
                        "address_id": "A001",
                        "customer_id": "C001",
                        "street": "1 Old Street",
                        "city": "London",
                        "version": 1,
                        "is_current": 0,
                    },
                    {
                        "address_id": "A002",
                        "customer_id": "C001",
                        "street": "2 Current Street",
                        "city": "London",
                        "version": 1,
                        "is_current": 1,
                    },
                ],
            )
            connection.execute(
                insert(self._tables[2]).values(
                    order_id="O001",
                    customer_id="C001",
                    shipping_address_id="A001",
                    status=OrderStatus.CONFIRMED.value,
                    version=1,
                )
            )

    def verification_view(self) -> OrderVerificationView:
        return OrderVerificationView(self._event_store.database_url)

    def get_customer(
        self, customer_id: str, *, context: ExecutionContext | None = None
    ) -> ToolResult[Customer]:
        return self._read_tool(
            "get_customer",
            {"customer_id": customer_id},
            lambda connection: self._get_customer(connection, customer_id),
            context=context,
        )

    def get_addresses(
        self, customer_id: str, *, context: ExecutionContext | None = None
    ) -> ToolResult[list[Address]]:
        return self._read_tool(
            "get_addresses",
            {"customer_id": customer_id},
            lambda connection: self._get_addresses(connection, customer_id),
            context=context,
            missing_error_code="CUSTOMER_NOT_FOUND",
        )

    def get_order(
        self, order_id: str, *, context: ExecutionContext | None = None
    ) -> ToolResult[Order]:
        return self._read_tool(
            "get_order",
            {"order_id": order_id},
            lambda connection: self._get_order(connection, order_id),
            context=context,
        )

    def update_order_shipping_address(
        self,
        order_id: str,
        address_id: str,
        *,
        context: ExecutionContext | None = None,
    ) -> ToolResult[Order]:
        resolved_context = context or self._default_context
        arguments = {"order_id": order_id, "address_id": address_id}
        self._recorder.record(
            EventType.TOOL_CALL,
            "update_order_shipping_address",
            context=resolved_context,
            status=EventStatus.UNKNOWN,
            tool_name="update_order_shipping_address",
            input_value=arguments,
        )
        failure: ToolResult[Order] | None = None
        committed_result: ToolResult[Order] | None = None
        with self._event_store.transaction() as connection:
            before = self._get_order(connection, order_id)
            if before is None:
                failure = ToolResult(
                    False, None, "ORDER_NOT_FOUND", "Order was not found."
                )
            elif before.status not in (OrderStatus.DRAFT, OrderStatus.CONFIRMED):
                failure = ToolResult(
                    False,
                    None,
                    "ORDER_STATUS_FORBIDDEN",
                    "Shipping address can only change for DRAFT or CONFIRMED orders.",
                )
            else:
                address = self._get_address(connection, address_id)
                if address is None:
                    failure = ToolResult(
                        False, None, "ADDRESS_NOT_FOUND", "Address was not found."
                    )
                elif address.customer_id != before.customer_id:
                    failure = ToolResult(
                        False,
                        None,
                        "ADDRESS_CUSTOMER_MISMATCH",
                        "Address does not belong to the order's customer.",
                    )
                else:
                    before_hash = sha256_json(json_value(before))
                    is_no_op = before.shipping_address_id == address_id
                    if not is_no_op:
                        mutation_result = connection.execute(
                            update(self._tables[2])
                            .where(
                                (self._tables[2].c.order_id == order_id)
                                & (self._tables[2].c.version == before.version)
                            )
                            .values(
                                shipping_address_id=address_id,
                                version=self._tables[2].c.version + 1,
                            )
                        )
                        if mutation_result.rowcount != 1:
                            raise EventConflictError(
                                "order changed while the mutation was in progress"
                            )
                        connection.execute(
                            insert(self._tables[3]).values(
                                order_id=order_id,
                                previous_address_id=before.shipping_address_id,
                                new_address_id=address_id,
                            )
                        )
                    after = self._get_order(connection, order_id)
                    if after is None:
                        raise RuntimeError("updated order could not be read")
                    result = ToolResult(
                        True,
                        after,
                        None,
                        "Order already used the requested address."
                        if is_no_op
                        else "Order shipping address updated.",
                    )
                    self._record_result(
                        "update_order_shipping_address",
                        arguments,
                        result,
                        context=resolved_context,
                        state_before_hash=before_hash,
                        state_after_hash=sha256_json(json_value(after)),
                        mutation="NO_OP" if is_no_op else "REAL",
                        connection=connection,
                    )
                    committed_result = result
        if committed_result is not None:
            return committed_result
        if failure is None:
            raise RuntimeError("mutation did not produce a result")
        self._record_result(
            "update_order_shipping_address",
            arguments,
            failure,
            context=resolved_context,
            mutation="REJECTED",
        )
        return failure

    def close(self) -> None:
        if self._owns_event_store:
            self._event_store.close()

    def __enter__(self) -> OrderManagementEnvironment:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _read_tool(
        self,
        tool_name: str,
        arguments: dict[str, str],
        operation: Callable[[Connection], T | None],
        *,
        context: ExecutionContext | None,
        missing_error_code: str = "NOT_FOUND",
    ) -> ToolResult[T]:
        resolved_context = context or self._default_context
        self._recorder.record(
            EventType.TOOL_CALL,
            tool_name,
            context=resolved_context,
            status=EventStatus.UNKNOWN,
            tool_name=tool_name,
            input_value=arguments,
        )
        with self._event_store._engine.connect() as connection:
            value = operation(connection)
        if value is None:
            result: ToolResult[T] = ToolResult(
                False, None, missing_error_code, f"{tool_name} target was not found."
            )
        else:
            result = ToolResult(True, value, None, "OK")
            if self._fault_injector is not None:
                result = self._fault_injector.intercept(
                    tool_name,
                    result,
                    ground_truth_step=self._recorder.next_step + 1,
                )
            result = self._validate_tool_result(tool_name, result)
        self._record_result(
            tool_name,
            arguments,
            result,
            context=resolved_context,
        )
        return result

    @staticmethod
    def _validate_tool_result(tool_name: str, result: ToolResult[T]) -> ToolResult[T]:
        if tool_name == "get_addresses" and result.ok:
            if not isinstance(result.value, list) or not all(
                isinstance(address, Address) for address in result.value
            ):
                return ToolResult(
                    False,
                    None,
                    "MALFORMED_TOOL_RESULT",
                    "Tool result schema was invalid.",
                )
        return result

    def _record_result(
        self,
        tool_name: str,
        arguments: dict[str, str],
        result: ToolResult[T],
        *,
        context: ExecutionContext,
        state_before_hash: str | None = None,
        state_after_hash: str | None = None,
        mutation: str | None = None,
        connection: Connection | None = None,
    ) -> None:
        metadata: dict[str, str | bool | None] = {
            "ok": result.ok,
            "error_code": result.error_code,
            "message": result.message,
        }
        if mutation is not None:
            metadata["mutation"] = mutation
        self._recorder.record(
            EventType.TOOL_RESULT,
            tool_name,
            context=context,
            status=EventStatus.OK if result.ok else EventStatus.ERROR,
            tool_name=tool_name,
            input_value=arguments,
            output_value=json_value(result.value),
            state_before_hash=state_before_hash,
            state_after_hash=state_after_hash,
            metadata=metadata,
            connection=connection,
        )

    @staticmethod
    def _get_customer(connection: Connection, customer_id: str) -> Customer | None:
        customer_table = _state_tables()[1][0]
        row = (
            connection.execute(
                select(customer_table).where(
                    customer_table.c.customer_id == customer_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else Customer(row["customer_id"], row["name"])

    @staticmethod
    def _get_addresses(
        connection: Connection, customer_id: str
    ) -> list[Address] | None:
        customer = OrderManagementEnvironment._get_customer(connection, customer_id)
        if customer is None:
            return None
        address_table = _state_tables()[1][1]
        rows = (
            connection.execute(
                select(address_table)
                .where(address_table.c.customer_id == customer_id)
                .order_by(address_table.c.address_id)
            )
            .mappings()
            .all()
        )
        return [_address_from_row(row) for row in rows]

    @staticmethod
    def _get_address(connection: Connection, address_id: str) -> Address | None:
        address_table = _state_tables()[1][1]
        row = (
            connection.execute(
                select(address_table).where(address_table.c.address_id == address_id)
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _address_from_row(row)

    @staticmethod
    def _get_order(connection: Connection, order_id: str) -> Order | None:
        order_table = _state_tables()[1][2]
        row = (
            connection.execute(
                select(order_table).where(order_table.c.order_id == order_id)
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _order_from_row(row)


def _state_tables() -> tuple[MetaData, list[Table]]:
    metadata = MetaData()
    customers = Table(
        "customers",
        metadata,
        Column("customer_id", String, primary_key=True),
        Column("name", String, nullable=False),
    )
    addresses = Table(
        "addresses",
        metadata,
        Column("address_id", String, primary_key=True),
        Column(
            "customer_id", String, ForeignKey("customers.customer_id"), nullable=False
        ),
        Column("street", String, nullable=False),
        Column("city", String, nullable=False),
        Column("version", Integer, CheckConstraint("version >= 0"), nullable=False),
        Column(
            "is_current",
            Integer,
            CheckConstraint("is_current IN (0, 1)"),
            nullable=False,
        ),
    )
    orders = Table(
        "orders",
        metadata,
        Column("order_id", String, primary_key=True),
        Column(
            "customer_id", String, ForeignKey("customers.customer_id"), nullable=False
        ),
        Column(
            "shipping_address_id",
            String,
            ForeignKey("addresses.address_id"),
            nullable=False,
        ),
        Column(
            "status",
            String,
            CheckConstraint("status IN ('DRAFT', 'CONFIRMED', 'SHIPPED', 'CANCELLED')"),
            nullable=False,
        ),
        Column("version", Integer, CheckConstraint("version >= 0"), nullable=False),
    )
    history = Table(
        "order_update_history",
        metadata,
        Column("update_id", Integer, primary_key=True, autoincrement=True),
        Column("order_id", String, ForeignKey("orders.order_id"), nullable=False),
        Column(
            "previous_address_id",
            String,
            ForeignKey("addresses.address_id"),
            nullable=False,
        ),
        Column(
            "new_address_id", String, ForeignKey("addresses.address_id"), nullable=False
        ),
    )
    return metadata, [customers, addresses, orders, history]


def _address_from_row(row: object) -> Address:
    mapping = row
    return Address(
        mapping["address_id"],  # type: ignore[index]
        mapping["customer_id"],  # type: ignore[index]
        mapping["street"],  # type: ignore[index]
        mapping["city"],  # type: ignore[index]
        mapping["version"],  # type: ignore[index]
        bool(mapping["is_current"]),  # type: ignore[index]
    )


def _order_from_row(row: object) -> Order:
    mapping = row
    return Order(
        mapping["order_id"],  # type: ignore[index]
        mapping["customer_id"],  # type: ignore[index]
        mapping["shipping_address_id"],  # type: ignore[index]
        OrderStatus(mapping["status"]),  # type: ignore[index]
        mapping["version"],  # type: ignore[index]
    )
