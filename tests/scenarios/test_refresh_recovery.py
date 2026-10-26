"""Scenario tests for bounded REFRESH recovery."""

from pathlib import Path

import pytest
from sqlalchemy import insert

from immune.agents.order_lab import OrderManagementEnvironment
from immune.agents.reference_order_agent import ReferenceOrderAgent
from immune.core.events import EventType
from immune.core.modes import ExecutionMode
from immune.faults import FaultInjector, FaultSpecification, FaultType
from immune.recovery import (
    OrderTaskRecovery,
    RecoveryAction,
    RecoveryRequest,
)
from immune.telemetry.event_store import EventStore
from immune.telemetry.lab_events import LabEventRecorder
from immune.verification import OrderTaskVerifier, VerificationStatus


def build_faulty_run(
    tmp_path: Path,
) -> tuple[OrderManagementEnvironment, EventStore, LabEventRecorder]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    database_url = f"sqlite:///{tmp_path / 'lab.sqlite'}"
    event_store = EventStore(database_url)
    event_store.initialize()
    recorder = LabEventRecorder(event_store, "recovery-run-001")
    injector = FaultInjector(
        FaultSpecification(
            "stale-001", FaultType.STALE_RETRIEVAL, "get_addresses", 1, {}
        ),
        recorder,
        mode=ExecutionMode.DEMO_DEBUG,
    )
    environment = OrderManagementEnvironment(
        database_url, recorder, injector, event_store
    )
    assert ReferenceOrderAgent(environment, recorder).run() is True
    return environment, event_store, recorder


def test_refresh_preserves_fault_history_and_verifies_correct_state(
    tmp_path: Path,
) -> None:
    environment, event_store, recorder = build_faulty_run(tmp_path)
    before = event_store.events_for_run(recorder.run_id)
    failed = OrderTaskVerifier(environment.verification_view(), recorder).verify()
    assert failed.status is VerificationStatus.FAIL
    before_recovery = event_store.events_for_run(recorder.run_id)

    recovery = OrderTaskRecovery(environment, recorder).recover(
        RecoveryRequest(RecoveryAction.REFRESH, recorder.run_id, failed)
    )

    assert recovery.success is True
    assert recovery.verification is not None
    assert recovery.verification.status is VerificationStatus.PASS
    assert event_store.get(before[0].event_id) == before[0]
    after = event_store.events_for_run(recorder.run_id)
    assert after[: len(before_recovery)] == before_recovery
    assert any(event.event_type is EventType.RECOVERY_STARTED for event in after)
    assert any(event.event_type is EventType.RECOVERY_COMPLETED for event in after)
    start = next(
        i
        for i, event in enumerate(after)
        if event.event_type is EventType.RECOVERY_STARTED
    )
    end = next(
        i
        for i, event in enumerate(after)
        if event.event_type is EventType.RECOVERY_COMPLETED
    )
    assert all(
        event.actor_id == "recovery-controller"
        for event in after[start : end + 1]
        if event.event_type is not EventType.VERIFICATION
    )
    final_order = environment.verification_view().read_order("O001")
    assert final_order is not None
    assert final_order.shipping_address_id == "A002"


def test_refresh_is_single_attempt_and_idempotent_after_success(tmp_path: Path) -> None:
    environment, event_store, recorder = build_faulty_run(tmp_path)
    failed = OrderTaskVerifier(environment.verification_view(), recorder).verify()
    recovery = OrderTaskRecovery(environment, recorder)

    first = recovery.recover(
        RecoveryRequest(RecoveryAction.REFRESH, recorder.run_id, failed)
    )
    count_after_first = event_store.count(recorder.run_id)
    second = recovery.recover(
        RecoveryRequest(RecoveryAction.REFRESH, recorder.run_id, first.verification)
    )

    assert first.success is True
    assert second == first
    assert event_store.count(recorder.run_id) == count_after_first
    assert (
        len(
            [
                event
                for event in event_store.events_for_run(recorder.run_id)
                if event.event_type is EventType.RECOVERY_STARTED
            ]
        )
        == 1
    )


def test_recovery_action_outside_enum_cannot_execute(tmp_path: Path) -> None:
    environment, _, recorder = build_faulty_run(tmp_path)
    recovery = OrderTaskRecovery(environment, recorder)

    with pytest.raises(ValueError):
        recovery.recover(  # type: ignore[arg-type]
            RecoveryRequest("DELETE_DATABASE", recorder.run_id, None)  # type: ignore[arg-type]
        )


def test_recovery_retry_detects_intervening_legitimate_mutation(tmp_path: Path) -> None:
    environment, event_store, recorder = build_faulty_run(tmp_path)
    failed = OrderTaskVerifier(environment.verification_view(), recorder).verify()
    recovery = OrderTaskRecovery(environment, recorder)
    request = RecoveryRequest(RecoveryAction.REFRESH, recorder.run_id, failed)
    recovery.recover(request)

    with event_store.transaction() as connection:
        connection.execute(
            insert(environment._tables[1]).values(
                address_id="A003",
                customer_id="C001",
                street="3 New Street",
                city="London",
                version=1,
                is_current=0,
            )
        )
    changed = environment.update_order_shipping_address("O001", "A003")
    assert changed.ok is True
    count_before_retry = event_store.count(recorder.run_id)

    retry = recovery.recover(request)
    assert retry.attempted is False
    assert retry.success is False
    assert "Intervening state change" in retry.message
    assert event_store.count(recorder.run_id) == count_before_retry
    with environment.verification_view() as view:
        order = view.read_order("O001")
    assert order is not None and order.shipping_address_id == "A003"
