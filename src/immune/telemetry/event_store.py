"""Append-only SQLite storage for execution events."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, Sequence

from sqlalchemy import (
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    insert,
    select,
)
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from immune.core.events import EventStatus, EventType, ExecutionEvent
from immune.core.run_context import RunContext
from immune.telemetry.sqlite_config import configure_sqlite


class EventStoreError(ValueError):
    """Base error for EventStore domain failures."""


class EventReferenceError(EventStoreError):
    """Raised when an event has invalid causal references."""


class EventConflictError(EventStoreError):
    """Raised when an event conflicts with an existing event."""


class EventStoreUnavailableError(EventStoreError):
    """Raised when SQLite is unavailable or locked."""


class EventStore:
    """An append-only, one-writer-per-run SQLite event store."""

    def __init__(self, database_url: str, context: RunContext | None = None) -> None:
        if not database_url.startswith("sqlite:"):
            raise ValueError("EventStore requires a SQLite database URL")
        self.database_url = database_url
        self.context = context
        self._engine: Engine = create_engine(
            database_url,
            future=True,
            connect_args={"timeout": 1.0},
        )
        sqlalchemy_event.listen(self._engine, "connect", configure_sqlite)
        metadata = MetaData()
        self._events = Table(
            "execution_events",
            metadata,
            Column("event_id", String, primary_key=True),
            Column("run_id", String, nullable=False),
            Column("step", Integer, nullable=False),
            Column("timestamp", Text, nullable=False),
            Column("event_type", String, nullable=False),
            Column("actor_id", String, nullable=False),
            Column("operation", String, nullable=False),
            Column("tool_name", String, nullable=True),
            Column("status", String, nullable=False),
            Column("parent_event_id", String, nullable=True),
            Column("dependency_event_ids", Text, nullable=False),
            Column("input_hash", String, nullable=True),
            Column("output_hash", String, nullable=True),
            Column("state_before_hash", String, nullable=True),
            Column("state_after_hash", String, nullable=True),
            Column("latency_ms", Float, nullable=True),
            Column("metadata", Text, nullable=False),
            Column("checkpoint_id", String, nullable=True),
            UniqueConstraint("run_id", "step", name="uq_execution_events_run_step"),
        )
        self._run_metadata = Table(
            "run_metadata",
            metadata,
            Column("run_id", String, primary_key=True),
            Column("experiment_id", String, nullable=False),
            Column("mode", String, nullable=False),
            Column("scenario_id", String, nullable=False),
            Column("scenario_version", String, nullable=False),
            Column("random_seed", Integer, nullable=False),
        )
        self._metadata = metadata
        self._failure_injections = 0
        self._post_commit_failures = 0
        self._closed = False

    def _ensure_open(self) -> None:
        if self._closed:
            raise EventStoreUnavailableError("event store is closed")

    def initialize(self) -> None:
        """Create the event table if it does not already exist."""
        self._ensure_open()
        try:
            self._metadata.create_all(self._engine)
            if self.context is not None:
                self.bind_context(self.context)
        except OperationalError as error:
            raise EventStoreUnavailableError("event store is unavailable") from error

    def bind_context(self, context: RunContext) -> None:
        """Persist and enforce immutable run metadata."""
        self._ensure_open()
        try:
            with self._engine.begin() as connection:
                row = (
                    connection.execute(
                        select(self._run_metadata).where(
                            self._run_metadata.c.run_id == context.run_id
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                values = {
                    "run_id": context.run_id,
                    "experiment_id": context.experiment_id,
                    "mode": context.mode.value,
                    "scenario_id": context.scenario_id,
                    "scenario_version": context.scenario_version,
                    "random_seed": context.random_seed,
                }
                if row is None:
                    connection.execute(insert(self._run_metadata).values(**values))
                elif any(row[key] != value for key, value in values.items()):
                    raise EventStoreError(
                        "RunContext does not match persisted run metadata"
                    )
        except EventStoreError:
            raise
        except SQLAlchemyError as error:
            raise EventStoreError("run metadata persistence failed") from error

    def fail_next_append_for_test(self) -> None:
        """Deliberately fail the next append to test atomicity."""
        self._failure_injections += 1

    def fail_after_commit_for_test(self) -> None:
        """Raise after a successful commit to test runtime-cursor handling."""
        self._ensure_open()
        self._post_commit_failures += 1

    def _fail_after_commit_if_requested(self) -> None:
        if self._post_commit_failures:
            self._post_commit_failures -= 1
            raise EventStoreError("injected post-commit runtime failure")

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        """Yield one transaction for infrastructure-owned atomic work."""
        self._ensure_open()
        try:
            with self._engine.begin() as connection:
                yield connection
            self._fail_after_commit_if_requested()
        except OperationalError as error:
            raise EventStoreUnavailableError("event store is unavailable") from error
        except SQLAlchemyError as error:
            raise EventStoreError("event store transaction failed") from error

    def append(self, event: ExecutionEvent) -> None:
        """Append one event atomically."""
        self._ensure_open()
        if self.context is not None:
            self.context.require_same_run(event.run_id)
        try:
            with self._engine.begin() as connection:
                self.append_in_transaction(connection, event, allow_test_failure=False)
            self._fail_after_commit_if_requested()
        except EventStoreError:
            raise
        except OperationalError as error:
            raise EventStoreUnavailableError("event store is unavailable") from error
        except SQLAlchemyError as error:
            raise EventStoreError("event store append failed") from error

    def append_in_transaction(
        self,
        connection: Connection,
        event: ExecutionEvent,
        *,
        allow_test_failure: bool = True,
    ) -> None:
        """Append using an already-open infrastructure transaction."""
        self._ensure_open()
        if self.context is not None:
            self.context.require_same_run(event.run_id)
        if allow_test_failure and self._failure_injections:
            self._failure_injections -= 1
            raise EventStoreUnavailableError("injected telemetry persistence failure")
        self._validate_references(connection, event)
        try:
            connection.execute(insert(self._events).values(**_event_to_row(event)))
        except IntegrityError as error:
            raise EventConflictError("event conflicts with existing history") from error
        except OperationalError as error:
            raise EventStoreUnavailableError("event store is unavailable") from error
        except SQLAlchemyError as error:
            raise EventStoreError("event store append failed") from error

    def get(self, event_id: str) -> ExecutionEvent | None:
        self._ensure_open()
        try:
            with self._engine.connect() as connection:
                row = (
                    connection.execute(
                        select(self._events).where(self._events.c.event_id == event_id)
                    )
                    .mappings()
                    .one_or_none()
                )
        except OperationalError as error:
            raise EventStoreUnavailableError("event store is unavailable") from error
        return None if row is None else _row_to_event(row)

    def events_for_run(self, run_id: str) -> list[ExecutionEvent]:
        self._ensure_open()
        try:
            with self._engine.connect() as connection:
                rows = (
                    connection.execute(
                        select(self._events)
                        .where(self._events.c.run_id == run_id)
                        .order_by(self._events.c.step)
                    )
                    .mappings()
                    .all()
                )
        except OperationalError as error:
            raise EventStoreUnavailableError("event store is unavailable") from error
        return [_row_to_event(row) for row in rows]

    def latest_event(self, run_id: str) -> ExecutionEvent | None:
        self._ensure_open()
        try:
            with self._engine.connect() as connection:
                row = (
                    connection.execute(
                        select(self._events)
                        .where(self._events.c.run_id == run_id)
                        .order_by(self._events.c.step.desc())
                        .limit(1)
                    )
                    .mappings()
                    .one_or_none()
                )
        except OperationalError as error:
            raise EventStoreUnavailableError("event store is unavailable") from error
        return None if row is None else _row_to_event(row)

    def count(self, run_id: str) -> int:
        self._ensure_open()
        try:
            with self._engine.connect() as connection:
                result = connection.execute(
                    select(func.count())
                    .select_from(self._events)
                    .where(self._events.c.run_id == run_id)
                ).scalar_one()
        except OperationalError as error:
            raise EventStoreUnavailableError("event store is unavailable") from error
        return int(result)

    def total_count(self) -> int:
        """Return the total number of events in this run-scoped database."""
        self._ensure_open()
        try:
            with self._engine.connect() as connection:
                result = connection.execute(
                    select(func.count()).select_from(self._events)
                ).scalar_one()
        except OperationalError as error:
            raise EventStoreUnavailableError("event store is unavailable") from error
        return int(result)

    def close(self) -> None:
        """Dispose all pooled SQLite connections; safe to call repeatedly."""
        if not self._closed:
            self._engine.dispose()
            self._closed = True

    def __enter__(self) -> EventStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _validate_references(
        self, connection: Connection, event: ExecutionEvent
    ) -> None:
        referenced_ids = set(event.dependency_event_ids)
        if event.parent_event_id is not None:
            referenced_ids.add(event.parent_event_id)
        rows: Sequence[Any] = []
        if referenced_ids:
            rows = connection.execute(
                select(
                    self._events.c.event_id,
                    self._events.c.run_id,
                    self._events.c.step,
                    self._events.c.event_type,
                    self._events.c.tool_name,
                    self._events.c.operation,
                    self._events.c.parent_event_id,
                ).where(self._events.c.event_id.in_(referenced_ids))
            ).all()
        records = {row.event_id: row for row in rows}

        if event.parent_event_id is not None:
            parent = records.get(event.parent_event_id)
            if parent is None:
                raise EventReferenceError(
                    "parent_event_id references a nonexistent event"
                )
            if parent.run_id != event.run_id:
                raise EventReferenceError("parent event must belong to the same run")
            if parent.step >= event.step:
                raise EventReferenceError(
                    "parent event must precede the appended event"
                )

        for dependency_id in event.dependency_event_ids:
            dependency = records.get(dependency_id)
            if dependency is None:
                raise EventReferenceError(
                    "dependency_event_ids references a nonexistent event"
                )
            if dependency.run_id != event.run_id:
                raise EventReferenceError(
                    "dependency event must belong to the same run"
                )
            if dependency.step >= event.step:
                raise EventReferenceError(
                    "dependency event must precede the appended event"
                )

        if event.event_type is EventType.TOOL_RESULT:
            if event.parent_event_id is not None:
                parent = records[event.parent_event_id]
                if parent.event_type == EventType.TOOL_CALL.value:
                    call = parent
                elif (
                    parent.event_type == EventType.FAULT_INJECTED.value
                    and parent.parent_event_id
                ):
                    call = records.get(parent.parent_event_id)
                    if call is None:
                        call = connection.execute(
                            select(
                                self._events.c.event_id,
                                self._events.c.run_id,
                                self._events.c.step,
                                self._events.c.event_type,
                                self._events.c.tool_name,
                                self._events.c.operation,
                                self._events.c.parent_event_id,
                            ).where(self._events.c.event_id == parent.parent_event_id)
                        ).one_or_none()
                else:
                    call = None
                if call is not None and call.event_type != EventType.TOOL_CALL.value:
                    raise EventReferenceError(
                        "TOOL_RESULT must follow a related TOOL_CALL"
                    )
                if call is not None and (
                    call.operation != event.operation
                    or call.tool_name != event.tool_name
                ):
                    raise EventReferenceError(
                        "TOOL_RESULT operation does not match TOOL_CALL"
                    )
                if call is not None and event.status is EventStatus.OK:
                    existing_success = connection.execute(
                        select(self._events.c.event_id).where(
                            (self._events.c.parent_event_id == call.event_id)
                            & (self._events.c.event_type == EventType.TOOL_RESULT.value)
                            & (self._events.c.status == EventStatus.OK.value)
                        )
                    ).first()
                    if existing_success is not None:
                        raise EventReferenceError(
                            "a TOOL_CALL cannot have multiple successful results"
                        )

        if event.event_type is EventType.RECOVERY_COMPLETED:
            if (
                event.parent_event_id is None
                or records[event.parent_event_id].event_type
                != EventType.VERIFICATION.value
            ):
                raise EventReferenceError("RECOVERY_COMPLETED must follow VERIFICATION")
            current_id = event.parent_event_id
            saw_recovery_start = False
            while current_id is not None:
                row = connection.execute(
                    select(
                        self._events.c.event_type,
                        self._events.c.parent_event_id,
                    ).where(self._events.c.event_id == current_id)
                ).one_or_none()
                if row is None:
                    break
                if row.event_type == EventType.RECOVERY_STARTED.value:
                    saw_recovery_start = True
                    break
                current_id = row.parent_event_id
            if not saw_recovery_start:
                raise EventReferenceError(
                    "RECOVERY_COMPLETED must belong to a recovery continuation"
                )


def _event_to_row(event: ExecutionEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "run_id": event.run_id,
        "step": event.step,
        "timestamp": event.timestamp.isoformat(),
        "event_type": event.event_type.value,
        "actor_id": event.actor_id,
        "operation": event.operation,
        "tool_name": event.tool_name,
        "status": event.status.value,
        "parent_event_id": event.parent_event_id,
        "dependency_event_ids": json.dumps(
            list(event.dependency_event_ids), separators=(",", ":")
        ),
        "input_hash": event.input_hash,
        "output_hash": event.output_hash,
        "state_before_hash": event.state_before_hash,
        "state_after_hash": event.state_after_hash,
        "latency_ms": event.latency_ms,
        "metadata": json.dumps(
            dict(event.metadata),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ),
        "checkpoint_id": event.checkpoint_id,
    }


def _row_to_event(row: Any) -> ExecutionEvent:
    return ExecutionEvent(
        event_id=row["event_id"],
        run_id=row["run_id"],
        step=row["step"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        event_type=EventType(row["event_type"]),
        actor_id=row["actor_id"],
        operation=row["operation"],
        tool_name=row["tool_name"],
        status=EventStatus(row["status"]),
        parent_event_id=row["parent_event_id"],
        dependency_event_ids=tuple(json.loads(row["dependency_event_ids"])),
        input_hash=row["input_hash"],
        output_hash=row["output_hash"],
        state_before_hash=row["state_before_hash"],
        state_after_hash=row["state_after_hash"],
        latency_ms=row["latency_ms"],
        metadata=json.loads(row["metadata"]),
        checkpoint_id=row["checkpoint_id"],
    )
