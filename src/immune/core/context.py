"""Explicit execution actor context."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """Identifies the run and actor responsible for an operation."""

    run_id: str
    actor_id: str

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id cannot be blank")
        if not self.actor_id.strip():
            raise ValueError("actor_id cannot be blank")
