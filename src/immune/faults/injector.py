"""One-shot stale-address response transformation for the academic lab."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from immune.core.context import ExecutionContext
from immune.core.events import EventStatus, EventType
from immune.core.modes import ExecutionMode
from immune.faults.specifications import FaultSpecification
from immune.models.order_lab import Address
from immune.telemetry.lab_events import LabEventRecorder

if TYPE_CHECKING:
    from immune.agents.order_lab import ToolResult


class FaultInjector:
    def __init__(
        self,
        specification: FaultSpecification,
        recorder: LabEventRecorder,
        *,
        mode: ExecutionMode = ExecutionMode.DEMO_DEBUG,
    ) -> None:
        if mode is not ExecutionMode.DEMO_DEBUG:
            raise ValueError("only academic debug visibility is included")
        self._specification = specification
        self._recorder = recorder
        self._triggered = False

    def intercept(
        self, operation: str, result: ToolResult[Any], *, ground_truth_step: int
    ) -> ToolResult[Any]:
        fault = self._specification
        if (
            self._triggered
            or operation != fault.target_operation
            or self._recorder.operation_occurrence(operation)
            != fault.inject_at_occurrence
            or not result.ok
            or not isinstance(result.value, list)
        ):
            return result
        from immune.agents.order_lab import ToolResult

        observed = [
            replace(address, is_current=address.address_id == "A001")
            if isinstance(address, Address)
            else address
            for address in result.value
        ]
        self._triggered = True
        self._recorder.record(
            EventType.FAULT_INJECTED,
            "fault_injected_debug_marker",
            context=ExecutionContext(self._recorder.run_id, "fault-injector"),
            status=EventStatus.OK,
            tool_name=operation,
            metadata={
                "fault_id": fault.fault_id,
                "fault_type": fault.fault_type.value,
                "target_operation": operation,
                "ground_truth_step": ground_truth_step,
                "visibility": "DEMO_DEBUG",
            },
        )
        return ToolResult(True, observed, None, result.message)
