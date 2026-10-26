"""Immutable run-level identity and safety context."""

from __future__ import annotations

from dataclasses import dataclass

from immune.core.modes import ExecutionMode


@dataclass(frozen=True, slots=True)
class RunContext:
    experiment_id: str
    run_id: str
    mode: ExecutionMode = ExecutionMode.DEMO_DEBUG
    scenario_id: str = "IMMUNE-Lab"
    scenario_version: str = "V0"
    random_seed: int = 0

    def __post_init__(self) -> None:
        for name in ("experiment_id", "run_id", "scenario_id", "scenario_version"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} cannot be blank")
        if not isinstance(self.mode, ExecutionMode):
            raise ValueError("mode must be an ExecutionMode")

    def require_same_run(self, run_id: str) -> None:
        if run_id != self.run_id:
            raise ValueError("run_id does not match RunContext")
