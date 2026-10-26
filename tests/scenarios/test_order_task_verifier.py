"""Scenario tests for independent order-task verification."""

from pathlib import Path

from immune.agents.order_lab import OrderManagementEnvironment
from immune.agents.reference_order_agent import ReferenceOrderAgent
from immune.core.errors import VerificationReadError
from immune.core.events import EventType
from immune.core.modes import ExecutionMode
from immune.faults import FaultInjector, FaultSpecification, FaultType
from immune.telemetry.event_store import EventStore
from immune.telemetry.lab_events import LabEventRecorder
from immune.verification import OrderTaskVerifier, VerificationStatus


def build_run(
    tmp_path: Path, run_id: str, fault: bool = False
) -> tuple[OrderManagementEnvironment, EventStore, LabEventRecorder]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    database_url = f"sqlite:///{tmp_path / 'lab.sqlite'}"
    event_store = EventStore(database_url)
    event_store.initialize()
    recorder = LabEventRecorder(event_store, run_id)
    injector = None
    if fault:
        injector = FaultInjector(
            FaultSpecification(
                "fault-stale-001", FaultType.STALE_RETRIEVAL, "get_addresses", 1, {}
            ),
            recorder,
            mode=ExecutionMode.DEMO_DEBUG,
        )
    environment = OrderManagementEnvironment(
        database_url, recorder, injector, event_store
    )
    assert ReferenceOrderAgent(environment, recorder).run() is True
    return environment, event_store, recorder


def test_verifier_passes_healthy_run(tmp_path: Path) -> None:
    environment, event_store, recorder = build_run(tmp_path, "verify-healthy")

    result = OrderTaskVerifier(environment.verification_view(), recorder).verify()

    assert result.status is VerificationStatus.PASS
    assert result.observed_state_hash is not None
    assert (
        event_store.latest_event("verify-healthy").event_type is EventType.VERIFICATION
    )  # type: ignore[union-attr]


def test_verifier_fails_stale_retrieval_run(tmp_path: Path) -> None:
    environment, event_store, recorder = build_run(
        tmp_path, "verify-faulty", fault=True
    )

    result = OrderTaskVerifier(environment.verification_view(), recorder).verify()

    assert result.status is VerificationStatus.FAIL
    assert any(
        check.name == "order_uses_current_address" and check.passed is False
        for check in result.checks
    )
    verification_event = event_store.latest_event("verify-faulty")
    assert verification_event is not None
    assert verification_event.event_type is EventType.VERIFICATION
    assert verification_event.metadata["verification_status"] == "FAIL"
    assert "order_uses_current_address" in str(
        verification_event.metadata["checks_json"]
    )


class UnreadableState:
    def read_customer(self, customer_id: str) -> None:
        raise VerificationReadError("state unavailable")

    def read_addresses(self, customer_id: str) -> list[object]:
        raise VerificationReadError("state unavailable")

    def read_order(self, order_id: str) -> None:
        raise VerificationReadError("state unavailable")

    def order_update_count(self, order_id: str) -> int:
        raise VerificationReadError("state unavailable")


def test_verifier_can_be_indeterminate(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'indeterminate.sqlite'}"
    event_store = EventStore(database_url)
    event_store.initialize()
    recorder = LabEventRecorder(event_store, "verify-indeterminate")

    result = OrderTaskVerifier(UnreadableState(), recorder).verify()

    assert result.status is VerificationStatus.INDETERMINATE
    assert result.checks[0].passed is None
    assert result.diagnostic_code == "VERIFICATION_STATE_UNAVAILABLE"
    assert (
        event_store.latest_event("verify-indeterminate").event_type
        is EventType.VERIFICATION
    )  # type: ignore[union-attr]


def test_unexpected_verifier_programming_error_surfaces(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'unexpected.sqlite'}"
    event_store = EventStore(database_url)
    event_store.initialize()
    recorder = LabEventRecorder(event_store, "verify-unexpected")

    class BrokenState(UnreadableState):
        def read_customer(self, customer_id: str) -> None:
            raise RuntimeError("programming defect")

    import pytest

    with pytest.raises(RuntimeError, match="programming defect"):
        OrderTaskVerifier(BrokenState(), recorder).verify()
