"""Deterministic logical-time event recording for IMMUNE-Lab."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from sqlalchemy.engine import Connection

from immune.core.context import ExecutionContext
from immune.core.events import EventStatus, EventType, ExecutionEvent, JsonPrimitive
from immune.telemetry.event_store import EventStore, EventStoreError
from immune.telemetry.hashing import sha256_json


class LabClock:
    """Deterministic simulated execution clock, not a wall-clock timer."""

    def __init__(self) -> None:
        self._base_timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def timestamp_for_step(self, step: int) -> datetime:
        """Return the monotonic logical timestamp for an event step."""
        return self._base_timestamp + timedelta(milliseconds=step)


class LabEventRecorder:
    """Create deterministic, sequential events for one lab execution run."""

    def __init__(self, event_store: EventStore, run_id: str) -> None:
        self._event_store = event_store
        self._run_id = run_id
        self._next_step = 0
        self._last_event_id: str | None = None
        self._clock = LabClock()

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def next_step(self) -> int:
        return self._next_step

    @property
    def last_event_id(self) -> str | None:
        return self._last_event_id

    def operation_occurrence(self, operation: str) -> int:
        """Return the run-global count of recorded calls for an operation."""
        return sum(
            1
            for event in self._event_store.events_for_run(self._run_id)
            if event.event_type is EventType.TOOL_CALL and event.operation == operation
        )

    def record(
        self,
        event_type: EventType,
        operation: str,
        *,
        actor_id: str | None = None,
        context: ExecutionContext | None = None,
        status: EventStatus,
        tool_name: str | None = None,
        input_value: object | None = None,
        output_value: object | None = None,
        state_before_hash: str | None = None,
        state_after_hash: str | None = None,
        metadata: Mapping[str, JsonPrimitive] | None = None,
        connection: Connection | None = None,
    ) -> ExecutionEvent:
        """Append one event, optionally inside an infrastructure transaction."""
        resolved_actor = context.actor_id if context is not None else actor_id
        if resolved_actor is None:
            raise ValueError("an actor_id or ExecutionContext is required")
        if context is not None and context.run_id != self._run_id:
            raise ValueError("execution context run_id does not match recorder")
        event = ExecutionEvent(
            event_id=f"{self._run_id}-event-{self._next_step:04d}",
            run_id=self._run_id,
            step=self._next_step,
            timestamp=self._clock.timestamp_for_step(self._next_step),
            event_type=event_type,
            actor_id=resolved_actor,
            operation=operation,
            tool_name=tool_name,
            status=status,
            parent_event_id=self._last_event_id,
            dependency_event_ids=(),
            input_hash=None if input_value is None else sha256_json(input_value),
            output_hash=None if output_value is None else sha256_json(output_value),
            state_before_hash=state_before_hash,
            state_after_hash=state_after_hash,
            latency_ms=0.0,
            metadata={} if metadata is None else metadata,
            checkpoint_id=None,
        )
        if connection is None:
            try:
                self._event_store.append(event)
            except EventStoreError:
                self._reconcile_cursor()
                raise
        else:
            self._event_store.append_in_transaction(connection, event)
        self._next_step += 1
        self._last_event_id = event.event_id
        return event

    def _reconcile_cursor(self) -> None:
        """Recover the in-memory cursor from canonical history after append errors."""
        events = self._event_store.events_for_run(self._run_id)
        if not events:
            self._next_step = 0
            self._last_event_id = None
            return
        latest = max(events, key=lambda item: item.step)
        self._next_step = latest.step + 1
        self._last_event_id = latest.event_id


def json_value(value: object) -> Any:
    """Convert lab values into deterministic JSON-compatible structures."""
    if is_dataclass(value) and not isinstance(value, type):
        return json_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if hasattr(value, "value") and isinstance(value.value, str):
        return value.value
    return value
