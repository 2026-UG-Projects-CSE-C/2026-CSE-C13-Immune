# Phase I Presentation-to-Implementation Traceability

## Purpose and Scope

This document provides an auditable correspondence between the October 2026 IMMUNE Project Phase I final-review presentation (`Immune(2).pdf`, 27 pages) and the **published academic edition**. It is an evidence index, not a claim that literature methods, proposed Phase II components, or unpublished research subsystems are implemented. The current presentation cites the academic-edition snapshot `79d6ade89d1908d9af6bc87b4e785578061b110a`; the documentation added after that snapshot does not change the existing implementation.

The assignment retains the original proposal title, *IMMUNE: Early Failure Forecasting and Verified Recovery for Autonomous AI Agents*. The reproducible Phase I implementation covers **independent task-state verification and explicitly requested, task-scoped REFRESH** in one deterministic order-management workflow. Early failure forecasting remains unimplemented.

## Slide-to-Evidence Index

| PDF page | Presentation content | Evidence in this repository | Status / interpretation |
|---:|---|---|---|
| 1 | Title, team and institutional attribution | `README.md` — Academic Context; Project Team and Supervision | Academic identification; title includes planned scope |
| 2 | Contents | Presentation itself | Navigation, not implementation evidence |
| 3 | Execution completion versus task correctness | `src/immune/agents/reference_order_agent.py`; `src/immune/verification/order_task.py`; `tests/scenarios/test_stale_retrieval.py` | Demonstrated in the fixed task |
| 4 | Stale tool observations; broader ambiguous external writes | `src/immune/faults/injector.py`; `tests/scenarios/test_stale_retrieval.py`; literature [1], [5] | Stale response demonstrated; late-commit ambiguity not implemented |
| 5 | Literature [1]–[3] | [Scholarly foundations](scholarly-foundations.md) | Prior art, not algorithms implemented here |
| 6 | Literature [4]–[5] | [Scholarly foundations](scholarly-foundations.md) | 2026 preprints, contextual evidence |
| 7 | Literature [6]–[8] | [Scholarly foundations](scholarly-foundations.md) | Prior art and motivating principles |
| 8 | Literature [9]–[10] | [Scholarly foundations](scholarly-foundations.md) | Stateful evaluation precedents; no reproduced benchmarks |
| 9 | Project-specific integration gap | `docs/architecture.md`; `src/immune/demo.py` | A project engineering objective, not a literature-wide novelty claim |
| 10 | Five Phase I objectives | `docs/implementation-status.md`; `tests/` | Four objectives implemented in scope; configurable workflows planned |
| 11 | Existing retry/idempotency/recovery approaches | [Scholarly foundations](scholarly-foundations.md) | Comparative literature, not IMMUNE functionality claims |
| 12 | Observe → verify → decide → recover/withhold → reverify | `src/immune/demo.py`; `src/immune/recovery/order_task.py` | Integrated local scenario; process-local bounds |
| 13 | Source-mapped Phase I execution architecture | `docs/architecture.md`; `src/immune/agents/order_lab.py`; `src/immune/telemetry/event_store.py` | Same local SQLite file; verifier uses separate read-only connection |
| 14 | Six verification predicates and recovery boundary | `src/immune/verification/order_task.py`; `src/immune/recovery/order_task.py`; `tests/scenarios/test_order_task_verifier.py`; `tests/scenarios/test_recovery_boundaries.py` | Fixed C001/O001 task; neither global snapshot nor universal firewall |
| 15 | Developer/evaluator CLI interactions | `src/immune/demo.py`; `tests/scenarios/test_demo.py` | Command line only, not a browser interface |
| 16 | PASS / FAIL / INDETERMINATE and REFRESH decision flow | `src/immune/verification/order_task.py`; `src/immune/recovery/order_task.py`; `tests/scenarios/test_recovery_boundaries.py` | Explicit recovery after supplied FAIL; not proof of authoritative request authentication |
| 17 | Six module interface descriptions | `docs/architecture.md`; code under `src/immune/` | Architectural interfaces are task-specific |
| 18 | Requirements and implementation status | `docs/implementation-status.md`; `tests/` | Completed work distinguished from S8 intentions |
| 19 | Three scenarios and 60 tests | `src/immune/demo.py`; `tests/scenarios/test_demo.py`; `docs/reproducibility.md` | Synthetic task; documented deterministic outputs |
| 20 | Technology stack, S8 roadmap and repository source | `pyproject.toml`; `requirements-lock.txt`; `docs/implementation-status.md`; `docs/reproducibility.md` | Python 3.12; SQLite; SQLAlchemy 2.0.48; pytest 9.0.2; Ruff 0.17.2 |
| 21 | Conclusion | `README.md` — Implemented Functionality; Limitations | Proof of concept only; no measured production outcome |
| 22 | SDGs 9, 8 and 4 | [SDG alignment](sdg-alignment.md) | Qualitative primary, prospective and educational alignments |
| 23–25 | Ten scholarly references | [Scholarly foundations](scholarly-foundations.md) | Seven peer-reviewed publications and three arXiv preprints |
| 26 | Repository and official UN sources | `README.md`; `docs/`; [SDG alignment](sdg-alignment.md) | Supporting sources; not counted as scholarly references |
| 27 | Thank You | Presentation itself | Closing slide, no technical claim |

## Direct Reproduction of Demonstration Evidence

From the repository root, follow the [documented Windows Python 3.12 installation](../README.md#installation-and-configuration), then execute:

```powershell
.\.venv\Scripts\python.exe -m immune.demo healthy
.\.venv\Scripts\python.exe -m immune.demo stale-retrieval
.\.venv\Scripts\python.exe -m immune.demo stale-retrieval --recover --show-events
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

| Scenario | Expected agent result | Independent verification | Final persisted address | Event count |
|---|---|---|---|---:|
| Healthy | COMPLETED | PASS | A002 | 13 |
| Stale retrieval | COMPLETED | FAIL | A001 | 14 |
| Stale retrieval + REFRESH | COMPLETED | initial FAIL, final PASS | A002 | 25 |

**Important:** The stale-retrieval command intentionally exits successfully when it reproduces the expected verification FAIL. A successful command return code does not mean the underlying task passed its verification predicates. The recorded test total of **60 passed** refers to the October 2026 validated source and tests; it is not a measure of agent recovery success rate.

## Explicit Exclusions

No Phase I evidence in this repository establishes LLM-controlled execution, operational early failure forecasting, automated fault localization, persistent recovery quotas, universal effect certification, MCP tool dispatch, a web user interface, industrial deployment, or measurable SDG outcomes. The controls apply to the defined local order task and must not be generalized without further implementation and testing.
