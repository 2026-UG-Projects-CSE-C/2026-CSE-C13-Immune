"""Deterministic reference agent for the IMMUNE-Lab order scenario."""

from __future__ import annotations

from immune.agents.order_lab import OrderManagementEnvironment
from immune.core.context import ExecutionContext
from immune.core.events import EventStatus, EventType
from immune.telemetry.lab_events import LabEventRecorder, json_value


class ReferenceOrderAgent:
    """Complete the fixed order-address task using only public environment tools."""

    def __init__(
        self, environment: OrderManagementEnvironment, recorder: LabEventRecorder
    ) -> None:
        self._environment = environment
        self._recorder = recorder
        self._context = ExecutionContext(recorder.run_id, "reference-order-agent")

    def run(self) -> bool:
        """Run the healthy C001/O001 benchmark trajectory."""
        self._recorder.record(
            EventType.TASK_STARTED,
            "update_order_shipping_address_task",
            context=self._context,
            status=EventStatus.OK,
            metadata={"customer_id": "C001", "order_id": "O001"},
        )

        customer_result = self._environment.get_customer("C001", context=self._context)
        if not customer_result.ok or customer_result.value is None:
            return self._fail("customer lookup failed")

        addresses_result = self._environment.get_addresses(
            customer_result.value.customer_id, context=self._context
        )
        if not addresses_result.ok or addresses_result.value is None:
            return self._fail("address lookup failed")
        current_addresses = [
            address for address in addresses_result.value if address.is_current
        ]
        if len(current_addresses) != 1:
            return self._fail("current address was not uniquely identified")
        current_address = current_addresses[0]
        self._recorder.record(
            EventType.DECISION,
            "identify_current_shipping_address",
            context=self._context,
            status=EventStatus.OK,
            input_value=json_value(addresses_result.value),
            output_value=json_value(current_address),
            metadata={"selected_address_id": current_address.address_id},
        )

        order_result = self._environment.get_order("O001", context=self._context)
        if not order_result.ok or order_result.value is None:
            return self._fail("order lookup failed")
        permitted = order_result.value.status.value in ("DRAFT", "CONFIRMED")
        self._recorder.record(
            EventType.DECISION,
            "check_order_status_for_mutation",
            context=self._context,
            status=EventStatus.OK if permitted else EventStatus.ERROR,
            input_value=json_value(order_result.value),
            output_value=permitted,
            metadata={"status_permitted": permitted},
        )
        if not permitted:
            return self._fail("order status does not permit mutation")

        update_result = self._environment.update_order_shipping_address(
            "O001", current_address.address_id, context=self._context
        )
        if not update_result.ok:
            return self._fail(update_result.message)

        self._recorder.record(
            EventType.TASK_COMPLETED,
            "update_order_shipping_address_task",
            context=self._context,
            status=EventStatus.OK,
            output_value=json_value(update_result.value),
        )
        return True

    def _fail(self, message: str) -> bool:
        self._recorder.record(
            EventType.TASK_FAILED,
            "update_order_shipping_address_task",
            context=self._context,
            status=EventStatus.ERROR,
            metadata={"message": message},
        )
        return False
