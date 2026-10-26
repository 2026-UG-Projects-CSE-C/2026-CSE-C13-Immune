"""Scenario test for the healthy IMMUNE-Lab order trajectory."""

from pathlib import Path

from immune.agents.order_lab import OrderManagementEnvironment
from immune.agents.reference_order_agent import ReferenceOrderAgent
from immune.core.events import EventType
from immune.telemetry.event_store import EventStore
from immune.telemetry.lab_events import LabEventRecorder


def test_healthy_order_address_update_completes(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'lab.sqlite'}"
    event_store = EventStore(database_url)
    event_store.initialize()
    recorder = LabEventRecorder(event_store, "run-healthy-001")
    environment = OrderManagementEnvironment(
        database_url, recorder, event_store=event_store
    )
    agent = ReferenceOrderAgent(environment, recorder)

    assert agent.run() is True
    events = event_store.events_for_run("run-healthy-001")
    final_order = environment.get_order("O001")
    assert final_order.ok
    assert final_order.value is not None
    assert final_order.value.shipping_address_id == "A002"

    event_types = [event.event_type for event in events]
    assert event_types[0] is EventType.TASK_STARTED
    assert event_types[-1] is EventType.TASK_COMPLETED
    assert EventType.DECISION in event_types
    assert event_types.count(EventType.TOOL_CALL) == 4
    assert event_types.count(EventType.TOOL_RESULT) == 4
    assert all(
        event_types[index : index + 2]
        in ([EventType.TOOL_CALL, EventType.TOOL_RESULT],)
        for index in range(len(event_types) - 1)
        if event_types[index] is EventType.TOOL_CALL
    )

    mutation_results = [
        event
        for event in events
        if event.event_type is EventType.TOOL_RESULT
        and event.tool_name == "update_order_shipping_address"
    ]
    assert len(mutation_results) == 1
    assert mutation_results[0].state_before_hash is not None
    assert mutation_results[0].state_after_hash is not None
    assert mutation_results[0].state_before_hash != mutation_results[0].state_after_hash
