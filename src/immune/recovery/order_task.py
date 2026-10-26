"""Bounded REFRESH recovery for the IMMUNE-Lab order task."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from immune.core.context import ExecutionContext
from immune.core.events import EventStatus, EventType
from immune.recovery.interfaces import OrderTaskRuntime, RuntimeToolResponse
from immune.telemetry.hashing import sha256_json
from immune.telemetry.lab_events import LabEventRecorder, json_value
from immune.verification.order_task import (
    OrderTaskVerifier,
    ReadOnlyOrderState,
    VerificationResult,
    VerificationStatus,
)


class RecoveryAction(StrEnum):
    """Bounded recovery actions supported by IMMUNE V0."""

    CONTINUE = "CONTINUE"
    REFRESH = "REFRESH"


@dataclass(frozen=True, slots=True)
class RecoveryRequest:
    """A task-scoped request for one approved recovery action."""

    action: RecoveryAction
    run_id: str
    verification: VerificationResult | None
    customer_id: str = "C001"
    order_id: str = "O001"
    recovery_id: str = "refresh-order-task"

    def __post_init__(self) -> None:
        if not isinstance(self.action, RecoveryAction):
            raise ValueError("recovery action must be a RecoveryAction")
        if not self.run_id.strip():
            raise ValueError("run_id cannot be blank")


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    """Auditable result of a bounded recovery attempt."""

    action: RecoveryAction
    attempted: bool
    success: bool
    message: str
    verification: VerificationResult | None
    event_ids: tuple[str, ...]
    recovery_id: str = "refresh-order-task"
    precondition_state_hash: str | None = None
    resulting_state_hash: str | None = None
    resulting_version: int | None = None


class OrderTaskRecovery:
    """Execute at most one policy-approved REFRESH continuation."""

    def __init__(
        self, environment: OrderTaskRuntime, recorder: LabEventRecorder
    ) -> None:
        self._environment = environment
        self._recorder = recorder
        self._context = ExecutionContext(recorder.run_id, "recovery-controller")
        self._attempted = False
        self._last_result: RecoveryResult | None = None

    def recover(self, request: RecoveryRequest) -> RecoveryResult:
        """Execute a bounded recovery request or return an idempotent result."""
        if not isinstance(request.action, RecoveryAction):
            raise ValueError("recovery action must be a RecoveryAction")
        if (request.customer_id, request.order_id) != ("C001", "O001"):
            raise ValueError("academic recovery is scoped to C001 and O001")
        if request.run_id != self._recorder.run_id:
            raise ValueError("recovery request run_id does not match telemetry run")
        if request.action is RecoveryAction.CONTINUE:
            return RecoveryResult(
                request.action,
                attempted=False,
                success=request.verification is not None
                and request.verification.status is VerificationStatus.PASS,
                message="CONTINUE performs no recovery action.",
                verification=request.verification,
                event_ids=(),
            )
        if self._attempted and self._last_result is not None:
            if request.recovery_id != self._last_result.recovery_id:
                return RecoveryResult(
                    request.action,
                    False,
                    False,
                    "Only one recovery operation is permitted for this run.",
                    request.verification,
                    (),
                    request.recovery_id,
                )
            with self._environment.verification_view() as view:
                current = view.read_order(request.order_id)
            current_hash = None if current is None else sha256_json(json_value(current))
            if current_hash == self._last_result.resulting_state_hash:
                return self._last_result
            return RecoveryResult(
                request.action,
                False,
                False,
                "Intervening state change detected; recovery will not roll back state.",
                request.verification,
                (),
                request.recovery_id,
            )
        if (
            request.verification is not None
            and request.verification.status is VerificationStatus.PASS
        ):
            return RecoveryResult(
                request.action,
                attempted=False,
                success=True,
                message="Recovery is not needed after verified success.",
                verification=request.verification,
                event_ids=(),
            )
        if (
            request.verification is None
            or request.verification.status is not VerificationStatus.FAIL
        ):
            return RecoveryResult(
                request.action,
                attempted=False,
                success=False,
                message="REFRESH requires a failed verification result.",
                verification=request.verification,
                event_ids=(),
            )

        self._attempted = True
        with self._environment.verification_view() as view:
            before_order = view.read_order(request.order_id)
        precondition_hash = (
            None if before_order is None else sha256_json(json_value(before_order))
        )
        started = self._recorder.record(
            EventType.RECOVERY_STARTED,
            "refresh_order_task",
            context=self._context,
            status=EventStatus.OK,
            metadata={
                "recovery_action": RecoveryAction.REFRESH.value,
                "target_operation": "get_addresses",
                "order_id": request.order_id,
            },
        )
        self._recorder.record(
            EventType.DECISION,
            "invalidate_observed_get_addresses",
            context=self._context,
            status=EventStatus.OK,
            tool_name="get_addresses",
            metadata={"recovery_action": RecoveryAction.REFRESH.value},
        )

        addresses_result = cast(
            RuntimeToolResponse,
            self._environment.get_addresses(request.customer_id, context=self._context),
        )
        if addresses_result.ok and addresses_result.value is not None:
            values = cast(list[object], addresses_result.value)
            current_addresses = [
                address for address in values if getattr(address, "is_current", False)
            ]
        else:
            current_addresses = []

        if len(current_addresses) == 1:
            current_address = current_addresses[0]
            current_address_id = str(getattr(current_address, "address_id"))
            self._recorder.record(
                EventType.DECISION,
                "identify_refreshed_current_shipping_address",
                context=self._context,
                status=EventStatus.OK,
                output_value=json_value(current_address),
                metadata={
                    "recovery_action": RecoveryAction.REFRESH.value,
                    "selected_address_id": current_address_id,
                },
            )
            order_result = cast(
                RuntimeToolResponse,
                self._environment.get_order(request.order_id, context=self._context),
            )
            if order_result.ok and order_result.value is not None:
                order = order_result.value
                if getattr(order, "shipping_address_id", None) != current_address_id:
                    self._environment.update_order_shipping_address(
                        request.order_id,
                        current_address_id,
                        context=self._context,
                    )

        with self._environment.verification_view() as verification_view:
            verification = OrderTaskVerifier(
                cast(ReadOnlyOrderState, verification_view),
                self._recorder,
                expected_order_update_count=1,
            ).verify()
        success = verification.status is VerificationStatus.PASS
        with self._environment.verification_view() as view:
            resulting_order = view.read_order(request.order_id)
        resulting_hash = (
            None
            if resulting_order is None
            else sha256_json(json_value(resulting_order))
        )
        completed = self._recorder.record(
            EventType.RECOVERY_COMPLETED,
            "refresh_order_task",
            context=self._context,
            status=EventStatus.OK if success else EventStatus.ERROR,
            output_value=json_value(verification),
            metadata={
                "recovery_action": RecoveryAction.REFRESH.value,
                "verification_status": verification.status.value,
            },
        )
        result = RecoveryResult(
            RecoveryAction.REFRESH,
            attempted=True,
            success=success,
            message=(
                "REFRESH completed with verified success."
                if success
                else "REFRESH completed but verification failed."
            ),
            verification=verification,
            event_ids=(started.event_id, completed.event_id),
            recovery_id=request.recovery_id,
            precondition_state_hash=precondition_hash,
            resulting_state_hash=resulting_hash,
            resulting_version=None
            if resulting_order is None
            else int(getattr(resulting_order, "version")),
        )
        self._last_result = result
        return result
