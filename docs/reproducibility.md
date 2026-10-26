# Reproducibility and Test Report

## Validation Scope

The academic package was installed into a newly created virtual environment from its own `pyproject.toml`. The validation environment contained no copied database, API credential or external source path. The installed package resolved from the validation environment's `site-packages` directory.

Validation date: 26 October 2026. Validated platform: Windows 11 x64, CPython 3.12.14, SQLite 3.53.1. Package versions were SQLAlchemy 2.0.48 and pytest 9.0.2 with the transitive constraints in `requirements-lock.txt`. The operating-system and runtime versions describe this execution; they are not a claim of support for every Windows installation.

## Installation and Configuration

From the repository root, use the following commands:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check --no-cache-dir -c requirements-lock.txt ".[test]"
.\.venv\Scripts\python.exe -m pip check
```

The clean installation built `immune-academic` 0.1.0 and installed the declared dependency set. The installation command exited 0. `pip check` exited 0 with `No broken requirements found.` Network access was used only to download packages and the isolated build dependency. No credential was supplied.

## Demonstration Execution

```powershell
.\.venv\Scripts\python.exe -m immune.demo healthy
.\.venv\Scripts\python.exe -m immune.demo stale-retrieval
.\.venv\Scripts\python.exe -m immune.demo stale-retrieval --recover --show-events
```

| Scenario | Exit code | Agent | Verification | Persisted final address | Events |
|---|---:|---|---|---|---:|
| Healthy | 0 | COMPLETED | PASS | A002 | 13 |
| Stale retrieval | 0 | COMPLETED | FAIL | A001 | 14 |
| Stale retrieval and REFRESH | 0 | COMPLETED | initial FAIL, final PASS | A002 | 25 |

The stale scenario intentionally returns exit code 0 when it reproduces the expected independently detected failure. The text `Execution status: COMPLETED` records agent control flow; it does not assert task correctness. The recovered scenario recorded `RECOVERY_STARTED`, a new address read, an order read, one address update, post-attempt verification and `RECOVERY_COMPLETED`.

These runs created disposable SQLite files and removed them on normal CLI exit. The outputs above demonstrate the fixed local scenario only. They do not measure latency, reliability rates or general agent performance.

## Automated Testing

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Result: exit code 0; **60 passed in 3.84 seconds**. The suite covered:

- healthy and stale response trajectories;
- task verification PASS, FAIL and INDETERMINATE;
- read-only verification-handle enforcement;
- explicit recovery admission and refusal conditions;
- one-attempt behavior, repeat-result behavior and intervening state change;
- failed recovery reads and writes without false success;
- rollback when canonical event persistence fails during a business mutation;
- event identity, ordering, references and serialization;
- deterministic hashing and logical time.

Test success is evidence for the specified inputs and invariants. It is not proof of general reliability, complete concurrency safety or real-model behavior.

## Static and Structural Checks

The selected source and tests passed Ruff 0.17.2 lint rules `E4`, `E7`, `E9`, `F` and `I`, and the formatter check. The Mermaid diagrams parsed and rendered with Mermaid 11.12.0 in a headless browser. Diagram parsing supplements source review; it does not establish the runtime behavior of the components shown.

## Architecture-to-Source Consistency

Every implemented node in the architecture diagram maps to one of `demo.py`, `reference_order_agent.py`, `order_lab.py`, `injector.py`, `order_task.py`, `lab_events.py` or `event_store.py`. The proposed Phase II diagram is labeled as future work and has no implied source implementation. The public architecture does not depict omitted firewall, certifier, MCP or browser components.

## Reproduction Boundaries

The repository does not include pip caches, temporary databases or validation virtual environments. Re-running package installation at a later date depends on the availability of compatible packages from the configured Python package index.
