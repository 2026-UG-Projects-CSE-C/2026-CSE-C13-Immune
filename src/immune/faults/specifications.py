"""The single response fault used by the academic demonstration."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping


class FaultType(StrEnum):
    STALE_RETRIEVAL = "STALE_RETRIEVAL"


@dataclass(frozen=True, slots=True)
class FaultSpecification:
    fault_id: str
    fault_type: FaultType
    target_operation: str
    inject_at_occurrence: int
    metadata: Mapping[str, str]

    def __post_init__(self) -> None:
        if not self.fault_id.strip():
            raise ValueError("fault_id cannot be blank")
        if self.fault_type is not FaultType.STALE_RETRIEVAL:
            raise ValueError("only stale retrieval is included")
        if self.target_operation != "get_addresses":
            raise ValueError("stale retrieval targets get_addresses")
        if self.inject_at_occurrence < 1:
            raise ValueError("occurrence must be positive")
