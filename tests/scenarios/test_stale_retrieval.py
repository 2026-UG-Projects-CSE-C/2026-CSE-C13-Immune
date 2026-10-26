"""Scenario tests for deterministic silent stale-retrieval failure."""

from pathlib import Path

from immune.agents.order_lab import OrderManagementEnvironment
from immune.agents.reference_order_agent import ReferenceOrderAgent
from immune.core.events import EventType
from immune.core.modes import ExecutionMode
from immune.faults import FaultInjector, FaultSpecification, FaultType
from immune.telemetry.event_store import EventStore
from immune.telemetry.lab_events import LabEventRecorder


def run_faulty_scenario(
    tmp_path: Path, run_id: str
) -> tuple[OrderManagementEnvironment, EventStore]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    database_url = f"sqlite:///{tmp_path / f'{run_id}.sqlite'}"
    event_store = EventStore(database_url)
    event_store.initialize()
    recorder = LabEventRecorder(event_store, run_id)
    specification = FaultSpecification(
        fault_id="fault-stale-address-001",
        fault_type=FaultType.STALE_RETRIEVAL,
        target_operation="get_addresses",
        inject_at_occurrence=1,
        metadata={"scenario": "order-current-address"},
    )
    injector = FaultInjector(specification, recorder, mode=ExecutionMode.DEMO_DEBUG)
    environment = OrderManagementEnvironment(
        database_url, recorder, injector, event_store
    )
    assert ReferenceOrderAgent(environment, recorder).run() is True
    return environment, event_store


def test_stale_retrieval_is_a_silent_business_failure(tmp_path: Path) -> None:
    environment, event_store = run_faulty_scenario(tmp_path, "run-faulty-001")

    events = event_store.events_for_run("run-faulty-001")
    final_order = environment.get_order("O001")
    assert final_order.ok
    assert final_order.value is not None
    assert final_order.value.shipping_address_id == "A001"
    fault_events = [
        event for event in events if event.event_type is EventType.FAULT_INJECTED
    ]
    assert len(fault_events) == 1
    fault_event = fault_events[0]
    assert fault_event.metadata["fault_id"] == "fault-stale-address-001"
    assert fault_event.metadata["fault_type"] == "STALE_RETRIEVAL"
    assert fault_event.metadata["target_operation"] == "get_addresses"
    assert fault_event.metadata["ground_truth_step"] == fault_event.step + 1
    addresses_result_events = [
        event
        for event in events
        if event.event_type is EventType.TOOL_RESULT
        and event.tool_name == "get_addresses"
    ]
    assert len(addresses_result_events) == 1
    assert addresses_result_events[0].metadata["ok"] is True
    assert events[-1].event_type is EventType.TASK_COMPLETED


def test_repeated_faulty_execution_has_same_trajectory_structure(
    tmp_path: Path,
) -> None:
    _, first_store = run_faulty_scenario(tmp_path / "first", "run-one")
    _, second_store = run_faulty_scenario(tmp_path / "second", "run-two")

    def structure(store: EventStore, run_id: str) -> list[tuple[object, ...]]:
        return [
            (
                event.step,
                event.event_type,
                event.operation,
                event.tool_name,
                event.status,
                dict(event.metadata),
                event.input_hash,
                event.output_hash,
                event.state_before_hash,
                event.state_after_hash,
            )
            for event in store.events_for_run(run_id)
        ]

    assert structure(first_store, "run-one") == structure(second_store, "run-two")
