"""Tests for deterministic simulated logical time."""

from immune.core.events import EventStatus, EventType, ExecutionEvent
from immune.telemetry.lab_events import LabClock


def test_logical_clock_is_deterministic_monotonic_and_not_latency() -> None:
    first = LabClock()
    second = LabClock()
    first_timestamps = [first.timestamp_for_step(step) for step in range(4)]
    second_timestamps = [second.timestamp_for_step(step) for step in range(4)]

    assert first_timestamps == second_timestamps
    assert first_timestamps == sorted(first_timestamps)
    assert (first_timestamps[1] - first_timestamps[0]).total_seconds() == 0.001
    event = ExecutionEvent(
        event_id="event",
        run_id="run",
        step=0,
        timestamp=first_timestamps[0],
        event_type=EventType.TOOL_RESULT,
        actor_id="actor",
        operation="operation",
        tool_name=None,
        status=EventStatus.OK,
        parent_event_id=None,
        dependency_event_ids=(),
        input_hash=None,
        output_hash=None,
        state_before_hash=None,
        state_after_hash=None,
        latency_ms=25.0,
        metadata={},
        checkpoint_id=None,
    )
    assert event.latency_ms == 25.0
    assert event.timestamp == first_timestamps[0]
