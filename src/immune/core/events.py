"""Immutable domain representation of an execution event."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping, TypeAlias

JsonPrimitive: TypeAlias = None | bool | int | float | str


class EventType(StrEnum):
    """Kinds of events that can occur during an execution run."""

    TASK_STARTED = "TASK_STARTED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    DECISION = "DECISION"
    TOOL_CALL = "TOOL_CALL"
    TOOL_RESULT = "TOOL_RESULT"
    STATE_CHANGE = "STATE_CHANGE"
    VERIFICATION = "VERIFICATION"
    RECOVERY_STARTED = "RECOVERY_STARTED"
    RECOVERY_COMPLETED = "RECOVERY_COMPLETED"
    FAULT_INJECTED = "FAULT_INJECTED"


class EventStatus(StrEnum):
    """Outcome status recorded for an execution event."""

    OK = "OK"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    """An immutable, validated event in an agent execution history."""

    event_id: str
    run_id: str
    step: int
    timestamp: datetime
    event_type: EventType
    actor_id: str
    operation: str
    tool_name: str | None
    status: EventStatus
    parent_event_id: str | None
    dependency_event_ids: tuple[str, ...]
    input_hash: str | None
    output_hash: str | None
    state_before_hash: str | None
    state_after_hash: str | None
    latency_ms: float | None
    metadata: Mapping[str, JsonPrimitive]
    checkpoint_id: str | None

    def __post_init__(self) -> None:
        """Validate invariants and freeze mutable constructor inputs."""
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise ValueError("event_id cannot be blank")
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise ValueError("run_id cannot be blank")
        if not isinstance(self.actor_id, str) or not self.actor_id.strip():
            raise ValueError("actor_id cannot be blank")
        if not isinstance(self.operation, str) or not self.operation.strip():
            raise ValueError("operation cannot be blank")
        if self.step < 0:
            raise ValueError("step must be greater than or equal to zero")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.latency_ms is not None and (
            not math.isfinite(self.latency_ms) or self.latency_ms < 0
        ):
            raise ValueError("latency_ms must be finite and non-negative")
        if self.event_id == self.parent_event_id:
            raise ValueError("parent_event_id cannot equal event_id")
        for dependency_id in self.dependency_event_ids:
            if not isinstance(dependency_id, str) or not dependency_id.strip():
                raise ValueError("dependency IDs must be nonblank strings")
        if len(set(self.dependency_event_ids)) != len(self.dependency_event_ids):
            raise ValueError("dependency_event_ids must be unique")
        if self.event_id in self.dependency_event_ids:
            raise ValueError("an event cannot depend on itself")

        _validate_metadata(self.metadata)
        object.__setattr__(
            self, "dependency_event_ids", tuple(self.dependency_event_ids)
        )
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


def _validate_metadata(metadata: Mapping[str, JsonPrimitive]) -> None:
    """Reject metadata keys or values that are not JSON-compatible primitives."""
    for key, value in metadata.items():
        if not isinstance(key, str):
            raise TypeError("metadata keys must be strings")
        if value is not None and not isinstance(value, (bool, int, float, str)):
            raise TypeError("metadata values must be JSON-compatible primitives")
