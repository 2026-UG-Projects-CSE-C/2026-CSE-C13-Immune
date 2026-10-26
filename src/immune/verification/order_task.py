"""Independent verification of the IMMUNE-Lab order task."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from immune.agents.order_lab import OrderVerificationView
from immune.core.context import ExecutionContext
from immune.core.errors import VerificationReadError
from immune.core.events import EventStatus, EventType
from immune.models.order_lab import Address, Customer, Order, OrderStatus
from immune.telemetry.hashing import sha256_json
from immune.telemetry.lab_events import LabEventRecorder, json_value


class VerificationStatus(StrEnum):
    """Overall result of independent task verification."""

    PASS = "PASS"
    FAIL = "FAIL"
    INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True, slots=True)
class VerificationCheck:
    """Structured result for one deterministic verification check."""

    name: str
    passed: bool | None
    reason: str


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Auditable aggregate of independent verification checks."""

    status: VerificationStatus
    checks: tuple[VerificationCheck, ...]
    reason: str
    diagnostic_code: str
    observed_state_hash: str | None


class ReadOnlyOrderState(Protocol):
    """Protocol implemented by the verifier's state-only query interface."""

    def read_customer(self, customer_id: str) -> Customer | None: ...

    def read_addresses(self, customer_id: str) -> list[Address]: ...

    def read_order(self, order_id: str) -> Order | None: ...

    def order_update_count(self, order_id: str) -> int: ...


class OrderTaskVerifier:
    """Verify the order task from persisted state, independently of the agent."""

    def __init__(
        self,
        state: ReadOnlyOrderState | OrderVerificationView,
        recorder: LabEventRecorder,
        expected_order_update_count: int = 1,
    ) -> None:
        self._state = state
        self._recorder = recorder
        self._expected_order_update_count = expected_order_update_count
        self._context = ExecutionContext(recorder.run_id, "order-task-verifier")

    def verify(self) -> VerificationResult:
        """Run all checks and append one auditable VERIFICATION event."""
        observed: dict[str, object] = {}
        try:
            customer = self._state.read_customer("C001")
            order = self._state.read_order("O001")
            addresses = self._state.read_addresses("C001")
            update_count = self._state.order_update_count("O001")
            observed = {
                "customer": json_value(customer),
                "order": json_value(order),
                "addresses": json_value(addresses),
                "order_update_count": update_count,
            }
            checks = self._checks(
                customer,
                order,
                addresses,
                update_count,
                self._expected_order_update_count,
            )
            state_hash = sha256_json(observed)
        except VerificationReadError as error:
            checks = (
                VerificationCheck(
                    "state_readable",
                    None,
                    str(error),
                ),
            )
            state_hash = None

        result = self._result(checks, state_hash)
        self._record_verification(result, observed)
        return result

    @staticmethod
    def _checks(
        customer: Customer | None,
        order: Order | None,
        addresses: list[Address],
        update_count: int,
        expected_update_count: int,
    ) -> tuple[VerificationCheck, ...]:
        current_addresses = [address for address in addresses if address.is_current]
        current_id = (
            current_addresses[0].address_id if len(current_addresses) == 1 else None
        )
        return (
            VerificationCheck("order_exists", order is not None, "O001 exists."),
            VerificationCheck("customer_exists", customer is not None, "C001 exists."),
            VerificationCheck(
                "exactly_one_current_address",
                len(current_addresses) == 1,
                f"Found {len(current_addresses)} current addresses for C001.",
            ),
            VerificationCheck(
                "order_uses_current_address",
                None
                if order is None or current_id is None
                else order.shipping_address_id == current_id,
                "Order shipping address matches the current address."
                if order is not None
                and current_id is not None
                and order.shipping_address_id == current_id
                else "Order or unique current address is unavailable.",
            ),
            VerificationCheck(
                "status_permits_reached_state",
                None
                if order is None
                else order.status in (OrderStatus.DRAFT, OrderStatus.CONFIRMED),
                "Reached order status permits the address state."
                if order is not None
                and order.status in (OrderStatus.DRAFT, OrderStatus.CONFIRMED)
                else "Order status does not permit the reached state.",
            ),
            VerificationCheck(
                "no_unintended_second_order_update",
                update_count == expected_update_count,
                f"Observed {update_count} order updates; expected {expected_update_count}.",
            ),
        )

    @staticmethod
    def _result(
        checks: tuple[VerificationCheck, ...], state_hash: str | None
    ) -> VerificationResult:
        if any(check.passed is False for check in checks):
            status = VerificationStatus.FAIL
            reason = "One or more verification checks failed."
        elif any(check.passed is None for check in checks):
            status = VerificationStatus.INDETERMINATE
            reason = "One or more verification checks could not be determined."
        else:
            status = VerificationStatus.PASS
            reason = "All verification checks passed."
        diagnostic_code = {
            VerificationStatus.PASS: "VERIFICATION_PASSED",
            VerificationStatus.FAIL: "VERIFICATION_CHECK_FAILED",
            VerificationStatus.INDETERMINATE: "VERIFICATION_STATE_UNAVAILABLE",
        }[status]
        return VerificationResult(status, checks, reason, diagnostic_code, state_hash)

    def _record_verification(
        self, result: VerificationResult, observed: dict[str, object]
    ) -> None:
        checks_json = json.dumps(
            json_value(result.checks), sort_keys=True, separators=(",", ":")
        )
        self._recorder.record(
            EventType.VERIFICATION,
            "verify_order_task",
            context=self._context,
            status={
                VerificationStatus.PASS: EventStatus.OK,
                VerificationStatus.FAIL: EventStatus.ERROR,
                VerificationStatus.INDETERMINATE: EventStatus.UNKNOWN,
            }[result.status],
            input_value=observed,
            output_value=json_value(result),
            metadata={
                "verification_status": result.status.value,
                "reason": result.reason,
                "diagnostic_code": result.diagnostic_code,
                "checks_json": checks_json,
            },
        )
