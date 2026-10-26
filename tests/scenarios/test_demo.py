"""End-to-end tests for the IMMUNE V0 command-line demo."""

import subprocess
import sys


def run_demo(*arguments: str) -> str:
    completed = subprocess.run(
        [sys.executable, "-m", "immune.demo", *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def test_healthy_command() -> None:
    output = run_demo("healthy")

    assert "Execution status: COMPLETED" in output
    assert "Verification: PASS" in output
    assert "Final address: A002" in output
    assert "Run ID: demo-healthy" in output
    assert "Event count: " in output


def test_stale_retrieval_command() -> None:
    output = run_demo("stale-retrieval")

    assert "Execution status: COMPLETED" in output
    assert "Injected fault: STALE_RETRIEVAL" in output
    assert "Verification: FAIL" in output
    assert "Reason: One or more verification checks failed." in output
    assert "Run ID: demo-stale-retrieval" in output


def test_stale_retrieval_recovery_command_with_event_table() -> None:
    output = run_demo("stale-retrieval", "--recover", "--show-events")

    assert "Execution status: COMPLETED" in output
    assert "Injected fault: STALE_RETRIEVAL" in output
    assert "Initial verification: FAIL" in output
    assert "Recovery: REFRESH" in output
    assert "Recovered address: A002" in output
    assert "Final verification: PASS" in output
    assert "step | event_type | actor | operation | status" in output
    assert "RECOVERY_STARTED" in output
    assert "RECOVERY_COMPLETED" in output
