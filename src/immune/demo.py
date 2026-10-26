"""Minimal deterministic command-line demonstration for IMMUNE V0."""

from __future__ import annotations

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Sequence

from immune.agents.order_lab import OrderManagementEnvironment
from immune.agents.reference_order_agent import ReferenceOrderAgent
from immune.core.events import ExecutionEvent
from immune.core.modes import ExecutionMode
from immune.faults import FaultInjector, FaultSpecification, FaultType
from immune.recovery import (
    OrderTaskRecovery,
    RecoveryAction,
    RecoveryRequest,
    RecoveryResult,
)
from immune.telemetry.event_store import EventStore
from immune.telemetry.lab_events import LabEventRecorder
from immune.verification import (
    OrderTaskVerifier,
    VerificationResult,
    VerificationStatus,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    if arguments.recover and arguments.command != "stale-retrieval":
        parser.error("--recover is only valid with stale-retrieval")

    run_id = (
        "demo-healthy"
        if arguments.command == "healthy"
        else "demo-stale-retrieval-recovered"
        if arguments.recover
        else "demo-stale-retrieval"
    )
    with TemporaryDirectory(prefix="immune-demo-") as directory:
        database_url = f"sqlite:///{Path(directory) / 'run.sqlite'}"
        event_store = EventStore(database_url)
        event_store.initialize()
        recorder = LabEventRecorder(event_store, run_id)
        injector = None
        if arguments.command == "stale-retrieval":
            injector = FaultInjector(
                FaultSpecification(
                    "demo-stale-retrieval",
                    FaultType.STALE_RETRIEVAL,
                    "get_addresses",
                    1,
                    {},
                ),
                recorder,
                mode=ExecutionMode.DEMO_DEBUG,
            )
        environment = OrderManagementEnvironment(
            database_url, recorder, injector, event_store
        )
        agent_completed = ReferenceOrderAgent(environment, recorder).run()
        with environment.verification_view() as verification_view:
            verification = OrderTaskVerifier(verification_view, recorder).verify()
        initial_verification = verification
        recovery_result = None
        if arguments.recover:
            recovery_result = OrderTaskRecovery(environment, recorder).recover(
                RecoveryRequest(RecoveryAction.REFRESH, run_id, verification)
            )
            verification = recovery_result.verification or verification

        with environment.verification_view() as final_view:
            final_order = final_view.read_order("O001")
        final_address = None if final_order is None else final_order.shipping_address_id
        events = event_store.events_for_run(run_id)
        _print_summary(
            arguments.command,
            arguments.recover,
            run_id,
            len(events),
            agent_completed,
            verification,
            recovery_result,
            events,
            arguments.show_events,
            initial_verification,
            final_address,
        )
        environment.close()
        event_store.close()
    expected = (
        VerificationStatus.FAIL
        if arguments.command == "stale-retrieval" and not arguments.recover
        else VerificationStatus.PASS
    )
    return 0 if agent_completed and verification.status is expected else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a deterministic IMMUNE-Lab demo.")
    parser.add_argument("command", choices=("healthy", "stale-retrieval"))
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--show-events", action="store_true")
    return parser


def _print_summary(
    command: str,
    recovering: bool,
    run_id: str,
    event_count: int,
    agent_completed: bool,
    verification: VerificationResult,
    recovery_result: RecoveryResult | None,
    events: Sequence[ExecutionEvent],
    show_events: bool,
    initial_verification: VerificationResult,
    final_address: str | None,
) -> None:
    print("IMMUNE-Lab Run")
    print("--------------")
    print("Task: Update O001 to current customer address")
    print()
    print(f"Execution status: {'COMPLETED' if agent_completed else 'FAILED'}")

    if command == "stale-retrieval":
        print("Injected fault: STALE_RETRIEVAL")
    if recovering:
        initial_status = initial_verification.status.value
        print(f"Initial verification: {initial_status}")
        print("Recovery: REFRESH")
        recovered_address = final_address or "UNKNOWN"
        print(
            f"Recovered address: {recovered_address}"
            if recovery_result is not None and recovery_result.success
            else f"Final address: {recovered_address}"
        )
        print(
            f"Recovery success: {recovery_result.success if recovery_result else False}"
        )
        print(f"Final verification: {verification.status.value}")
    else:
        print(f"Verification: {verification.status.value}")
        if verification.status is VerificationStatus.FAIL:
            print(f"Reason: {verification.reason}")
        else:
            print(f"Final address: {final_address or 'UNAVAILABLE'}")
    print(f"Run ID: {run_id}")
    print(f"Event count: {event_count}")
    if show_events:
        print()
        print("step | event_type | actor | operation | status")
        print("-----|------------|-------|-----------|-------")
        for event in events:
            print(
                f"{event.step} | {event.event_type.value} | {event.actor_id} | "
                f"{event.operation} | {event.status.value}"
            )


if __name__ == "__main__":
    raise SystemExit(main())
