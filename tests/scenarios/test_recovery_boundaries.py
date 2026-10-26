"""Recovery refusal and durable-state checks for the academic scope."""

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from immune.agents.order_lab import OrderManagementEnvironment, ToolResult
from immune.agents.reference_order_agent import ReferenceOrderAgent
from immune.core.events import EventType
from immune.faults import FaultInjector, FaultSpecification, FaultType
from immune.recovery import OrderTaskRecovery, RecoveryAction, RecoveryRequest
from immune.telemetry.event_store import EventStore, EventStoreUnavailableError
from immune.telemetry.lab_events import LabEventRecorder
from immune.verification import (
    OrderTaskVerifier,
    VerificationResult,
    VerificationStatus,
)


@pytest.fixture
def run(tmp_path: Path):
    store = EventStore(f"sqlite:///{tmp_path / 'case.sqlite'}")
    store.initialize()
    recorder = LabEventRecorder(store, "boundary-run")
    injector = FaultInjector(
        FaultSpecification("stale", FaultType.STALE_RETRIEVAL, "get_addresses", 1, {}),
        recorder,
    )
    environment = OrderManagementEnvironment(
        store.database_url, recorder, injector, store
    )
    try:
        yield environment, store, recorder
    finally:
        environment.close()
        store.close()


def failed_run(run):
    environment, store, recorder = run
    assert ReferenceOrderAgent(environment, recorder).run()
    with environment.verification_view() as view:
        result = OrderTaskVerifier(view, recorder).verify()
    assert result.status is VerificationStatus.FAIL
    return environment, store, recorder, result


@pytest.mark.parametrize(
    "status", [None, VerificationStatus.INDETERMINATE, VerificationStatus.PASS]
)
def test_refresh_admission_does_not_mutate_without_failure(run, status):
    environment, store, recorder = run
    verification = (
        None if status is None else VerificationResult(status, (), "test", "test", None)
    )
    result = OrderTaskRecovery(environment, recorder).recover(
        RecoveryRequest(RecoveryAction.REFRESH, recorder.run_id, verification)
    )
    assert not result.attempted
    assert result.success == (status is VerificationStatus.PASS)
    with environment.verification_view() as view:
        assert view.read_order("O001").shipping_address_id == "A001"
        assert view.order_update_count("O001") == 0
    assert store.count(recorder.run_id) == 0


@pytest.mark.parametrize(
    "field,value", [("run_id", "other"), ("customer_id", "C002"), ("order_id", "O002")]
)
def test_request_must_match_the_fixed_task_scope(run, field, value):
    environment, store, recorder = run
    request = replace(
        RecoveryRequest(RecoveryAction.REFRESH, recorder.run_id, None), **{field: value}
    )
    with pytest.raises(ValueError):
        OrderTaskRecovery(environment, recorder).recover(request)
    assert store.count(recorder.run_id) == 0


@pytest.mark.parametrize(
    "operation", ["get_addresses", "update_order_shipping_address"]
)
def test_failed_recovery_tool_is_not_reported_as_success(run, monkeypatch, operation):
    environment, store, recorder, failed = failed_run(run)
    monkeypatch.setattr(
        environment,
        operation,
        lambda *args, **kwargs: ToolResult(
            False, None, "UNAVAILABLE", "Injected unavailable tool"
        ),
    )
    controller = OrderTaskRecovery(environment, recorder)
    request = RecoveryRequest(RecoveryAction.REFRESH, recorder.run_id, failed)
    first = controller.recover(request)
    assert first.attempted and not first.success
    assert first.verification.status is VerificationStatus.FAIL
    with environment.verification_view() as view:
        assert view.read_order("O001").shipping_address_id == "A001"
        assert view.order_update_count("O001") == 0
    count = store.count(recorder.run_id)
    assert controller.recover(request) == first
    assert store.count(recorder.run_id) == count
    assert store.events_for_run(recorder.run_id)[-1].status.value == "ERROR"


def test_read_only_handle_rejects_writes(run):
    environment, _, _ = run
    with environment.verification_view() as view:
        with pytest.raises(sqlite3.OperationalError):
            view._connection.execute("UPDATE orders SET shipping_address_id='A002'")
        assert view.read_order("O001").shipping_address_id == "A001"


def test_event_persistence_failure_rolls_back_business_mutation(run):
    environment, store, recorder = run
    store.fail_next_append_for_test()
    with pytest.raises(EventStoreUnavailableError):
        environment.update_order_shipping_address("O001", "A002")
    with environment.verification_view() as view:
        assert view.read_order("O001").shipping_address_id == "A001"
        assert view.order_update_count("O001") == 0
    assert not any(
        event.event_type is EventType.TOOL_RESULT
        for event in store.events_for_run(recorder.run_id)
    )
    assert environment.update_order_shipping_address("O001", "A002").ok
    with environment.verification_view() as view:
        assert view.read_order("O001").shipping_address_id == "A002"
        assert view.order_update_count("O001") == 1
