"""Integration tests for the SQLite-backed event store."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from immune.core.events import EventStatus, EventType, ExecutionEvent
from immune.telemetry.event_store import EventStore, EventStoreError


def make_event(
    event_id: str = "event-1",
    run_id: str = "run-1",
    step: int = 0,
    **overrides: object,
) -> ExecutionEvent:
    values: dict[str, object] = {
        "event_id": event_id,
        "run_id": run_id,
        "step": step,
        "timestamp": datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        "event_type": EventType.TOOL_RESULT,
        "actor_id": "agent-1",
        "operation": "invoke",
        "tool_name": "calculator",
        "status": EventStatus.OK,
        "parent_event_id": None,
        "dependency_event_ids": (),
        "input_hash": "input-hash",
        "output_hash": "output-hash",
        "state_before_hash": "before-hash",
        "state_after_hash": "after-hash",
        "latency_ms": 12.5,
        "metadata": {"attempt": 1, "successful": True},
        "checkpoint_id": "checkpoint-1",
    }
    values.update(overrides)
    return ExecutionEvent(**values)  # type: ignore[arg-type]


@pytest.fixture
def store(tmp_path: Path) -> EventStore:
    event_store = EventStore(f"sqlite:///{tmp_path / 'events.sqlite'}")
    event_store.initialize()
    return event_store


def test_append_one_event_and_get(store: EventStore) -> None:
    event = make_event()

    store.append(event)

    assert store.get(event.event_id) == event
    assert store.count(event.run_id) == 1


def test_duplicate_id_is_rejected(store: EventStore) -> None:
    event = make_event()
    store.append(event)

    with pytest.raises(EventStoreError):
        store.append(make_event(run_id="run-2"))


def test_duplicate_run_step_is_rejected(store: EventStore) -> None:
    store.append(make_event())

    with pytest.raises(EventStoreError):
        store.append(make_event(event_id="event-2"))


def test_invalid_parent_is_rejected(store: EventStore) -> None:
    with pytest.raises(EventStoreError, match="parent_event_id"):
        store.append(make_event(parent_event_id="missing"))


def test_cross_run_parent_is_rejected(store: EventStore) -> None:
    store.append(make_event())

    with pytest.raises(EventStoreError, match="same run"):
        store.append(
            make_event(
                event_id="event-2",
                run_id="run-2",
                parent_event_id="event-1",
            )
        )


def test_invalid_dependency_is_rejected(store: EventStore) -> None:
    with pytest.raises(EventStoreError, match="dependency_event_ids"):
        store.append(make_event(dependency_event_ids=("missing",)))


def test_failed_append_leaves_count_unchanged(store: EventStore) -> None:
    store.append(make_event())

    with pytest.raises(EventStoreError):
        store.append(
            make_event(
                event_id="event-2",
                step=1,
                dependency_event_ids=("missing",),
            )
        )

    assert store.count("run-1") == 1
    assert store.get("event-2") is None


def test_events_are_ordered_by_step_and_latest_is_returned(store: EventStore) -> None:
    store.append(make_event(event_id="event-1", step=1))
    store.append(make_event(event_id="event-0", step=0))

    assert [event.step for event in store.events_for_run("run-1")] == [0, 1]
    assert store.latest_event("run-1") == store.get("event-1")


def test_serialization_round_trip_preserves_event(store: EventStore) -> None:
    parent = make_event(event_id="event-1", step=0)
    event = make_event(
        event_id="event-2",
        step=1,
        parent_event_id=parent.event_id,
        dependency_event_ids=(parent.event_id,),
        metadata={"unicode": "✓", "attempt": 2, "ratio": 0.5},
    )
    store.append(parent)
    store.append(event)

    assert store.get(event.event_id) == event
