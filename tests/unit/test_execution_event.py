"""Unit tests for the immutable execution event domain model."""

from datetime import datetime, timezone
from types import MappingProxyType

import pytest

from immune.core.events import EventStatus, EventType, ExecutionEvent


def make_event(**overrides: object) -> ExecutionEvent:
    values: dict[str, object] = {
        "event_id": "event-1",
        "run_id": "run-1",
        "step": 0,
        "timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "event_type": EventType.TASK_STARTED,
        "actor_id": "agent-1",
        "operation": "start",
        "tool_name": None,
        "status": EventStatus.OK,
        "parent_event_id": None,
        "dependency_event_ids": ["event-0"],
        "input_hash": None,
        "output_hash": None,
        "state_before_hash": None,
        "state_after_hash": None,
        "latency_ms": None,
        "metadata": {"attempt": 1, "cached": False, "label": "first"},
        "checkpoint_id": None,
    }
    values.update(overrides)
    return ExecutionEvent(**values)  # type: ignore[arg-type]


def test_event_has_expected_values_and_immutable_containers() -> None:
    event = make_event()

    assert event.event_type is EventType.TASK_STARTED
    assert event.status is EventStatus.OK
    assert event.dependency_event_ids == ("event-0",)
    assert isinstance(event.metadata, MappingProxyType)


def test_event_is_immutable_after_construction() -> None:
    event = make_event()

    with pytest.raises((AttributeError, TypeError)):
        event.step = 1  # type: ignore[misc]
    with pytest.raises(TypeError):
        event.metadata["new"] = "value"  # type: ignore[index]


@pytest.mark.parametrize("field, value", [("event_id", ""), ("run_id", "   ")])
def test_blank_identifiers_are_rejected(field: str, value: str) -> None:
    with pytest.raises(ValueError, match="cannot be blank"):
        make_event(**{field: value})


def test_step_must_not_be_negative() -> None:
    with pytest.raises(ValueError, match="step"):
        make_event(step=-1)


def test_latency_must_not_be_negative() -> None:
    with pytest.raises(ValueError, match="latency_ms"):
        make_event(latency_ms=-0.1)


def test_timestamp_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        make_event(timestamp=datetime(2026, 1, 1))


def test_self_parent_and_self_dependency_are_rejected() -> None:
    with pytest.raises(ValueError, match="parent_event_id"):
        make_event(parent_event_id="event-1")
    with pytest.raises(ValueError, match="depend on itself"):
        make_event(dependency_event_ids=["event-1"])


def test_mutable_constructor_inputs_are_copied() -> None:
    dependencies = ["event-0"]
    metadata = {"attempt": 1}
    event = make_event(dependency_event_ids=dependencies, metadata=metadata)

    dependencies.append("event-2")
    metadata["attempt"] = 2

    assert event.dependency_event_ids == ("event-0",)
    assert event.metadata["attempt"] == 1


def test_metadata_rejects_non_primitive_values() -> None:
    with pytest.raises(TypeError, match="primitives"):
        make_event(metadata={"nested": {"not": "allowed"}})


@pytest.mark.parametrize("field", ["actor_id", "operation"])
def test_blank_actor_and_operation_are_rejected(field: str) -> None:
    with pytest.raises(ValueError, match="blank"):
        make_event(**{field: "   "})


def test_dependency_ids_must_be_unique_nonblank_strings() -> None:
    with pytest.raises(ValueError, match="unique"):
        make_event(dependency_event_ids=("event-0", "event-0"))
    with pytest.raises(ValueError, match="nonblank strings"):
        make_event(dependency_event_ids=("event-0", ""))
    with pytest.raises(ValueError, match="nonblank strings"):
        make_event(dependency_event_ids=("event-0", 3))


@pytest.mark.parametrize("latency", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_latency_is_rejected(latency: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        make_event(latency_ms=latency)
