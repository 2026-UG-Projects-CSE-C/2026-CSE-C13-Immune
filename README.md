# IMMUNE: Early Failure Forecasting and Verified Recovery for Autonomous AI Agents

Phase I academic edition: evidence-grounded state verification and bounded REFRESH recovery.

## Academic Context

B.Tech Computer Science and Engineering, Department of Computer Science and Engineering, Vidya Academy of Science & Technology, APJ Abdul Kalam Technological University (KTU), 2019 Scheme. This repository presents the CSD415 Project Phase I implementation, with further development proposed for Phase II.

The title preserves continuity with the original project proposal. The implemented Phase I scope is narrower: it focuses on independent state verification and bounded recovery. Operational early failure forecasting remains planned work and is not represented as an implemented capability. See the [implementation status](docs/implementation-status.md).

## Project Overview

IMMUNE demonstrates a reliability boundary between a deterministic order agent's execution and the correctness of its persisted result. An injected stale address response can make the agent complete normally while leaving an order linked to an outdated address. A separate read-only database interface verifies the task state. A requested, bounded REFRESH continuation re-reads the relevant information, attempts the update and verifies the resulting state.

The repository contains a local educational prototype. It uses synthetic customer and order records and requires no API credentials or model service.

## Problem Statement

Successful tool execution does not establish successful task completion. If an agent acts on stale observations, its workflow may complete without satisfying the intended state conditions. Recovery therefore requires explicit task predicates, independent state checks and a bounded continuation whose outcome is verified.

## Objectives

- Reproduce a deterministic order-address workflow and a stale-information failure.
- Verify persisted state independently of agent-visible tool responses.
- Permit a task-scoped REFRESH attempt only after failed verification.
- Record execution, injected faults, verification and recovery events.
- Provide an independently installable implementation and reproducible tests.

## Implemented Functionality

The reference agent retrieves customer C001, selects the unique current address in the returned data, reads order O001 and requests an address update. The fault injector can mark old address A001 as current in the first address response without changing the address table. The verifier checks persisted customer and order existence, a unique current address, address agreement, an allowed order status and exactly one actual address change.

REFRESH is explicitly requested through `--recover`. It requires FAIL, re-reads addresses and order, updates only when needed and verifies again. Repeated requests on the same controller instance reuse its result when the order hash is unchanged; intervening order changes prevent re-execution. See [system design](docs/architecture.md) for the exact admission and verification boundaries.

## Technical Foundations

IMMUNE draws on established systems and agent-evaluation research while limiting its implementation claims to the submitted Phase I source:

- **Idempotency and external effects [1].** RIFL motivates explicit request identity and completion evidence when retries could duplicate effects. IMMUNE does not implement RIFL or provider-enforced exactly-once RPCs.
- **Runtime assurance [2].** Independent monitoring and assurance motivate a distinction between agent control flow and task-state correctness. IMMUNE does not implement the cited neural-network verification methods or safety guarantees.
- **Transactional recovery [6].** Sagas provide a foundational model of compensating long-lived transactions. IMMUNE's bounded REFRESH is a task-specific corrective continuation, not a general Saga protocol.
- **End-to-end correctness [7].** The end-to-end argument motivates evaluating the final task outcome at the appropriate boundary, without implying a formal correctness proof.
- **State-based agent evaluation [9].** τ-bench motivates independent comparison of persisted state with task goals. IMMUNE does not execute the benchmark or claim its results.

The contribution documented here is a reproducible engineering demonstration that combines selected ideas within one fixed order-management task. For the complete, consistently numbered ten-paper literature review, publication statuses, and non-adoption limitations, see [Scholarly Foundations and Scope of Adoption](docs/scholarly-foundations.md).

## System Architecture

```mermaid
flowchart TB
    CLI["CLI: demo.py"] --> AG["ReferenceOrderAgent"]
    AG --> ENV["OrderManagementEnvironment"]
    FI["FaultInjector"] -->|response transformation| ENV
    ENV --> DB[("SQLite state and events")]
    DB --> RO["OrderVerificationView"]
    RO --> V["OrderTaskVerifier"]
    CLI -->|explicit request| REC["OrderTaskRecovery"]
    V -->|verification result| REC
    REC --> ENV
```

Every implemented component is mapped to source in [architecture and system design](docs/architecture.md). Planned Phase II work is documented separately in the [implementation status and roadmap](docs/implementation-status.md).

## Repository Structure

```text
README.md
pyproject.toml
requirements-lock.txt
docs/
|-- architecture.md
|-- implementation-status.md
`-- reproducibility.md
src/immune/
|-- demo.py
|-- agents/          # Reference agent and SQLite order environment
|-- core/            # Execution context and event types
|-- faults/          # Deterministic response fault injection
|-- models/          # Order-management domain models
|-- recovery/        # Bounded REFRESH recovery
|-- telemetry/       # Event storage and hashing
`-- verification/    # Independent persisted-state verification
tests/
|-- integration/
|-- scenarios/
`-- unit/
```

See the [architecture and system design](docs/architecture.md) and [implementation status and roadmap](docs/implementation-status.md) documents for component responsibilities and the Phase I/Phase II boundary.

## Technology Stack

Python 3.12, SQLite through Python's `sqlite3`, SQLAlchemy Core 2.0.48, and pytest 9.0.2. Runtime code uses the Python standard library and SQLAlchemy; pytest is a test dependency. There is no web framework, LLM SDK, forecasting model or external database server in this edition.

## Installation and Configuration

Validated environment: Windows 11 x64, CPython 3.12.14 and PowerShell. Python 3.12 must be available as `python` in PATH, with the standard `venv`, `ensurepip` and `sqlite3` modules. Network access is required to obtain build and Python dependencies. Other operating systems and Python versions have not been validated.

From the repository root:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check --no-cache-dir -c requirements-lock.txt ".[test]"
.\.venv\Scripts\python.exe -m pip check
```

`pyproject.toml` declares direct dependencies and the build backend. `requirements-lock.txt` constrains the dependency set validated on Windows Python 3.12. No environment file, database preparation or API key is required. Explicit interpreter paths avoid shell activation-policy changes.

## Execution and Demonstration

```powershell
.\.venv\Scripts\python.exe -m immune.demo healthy
.\.venv\Scripts\python.exe -m immune.demo stale-retrieval
.\.venv\Scripts\python.exe -m immune.demo stale-retrieval --recover --show-events
```

| Scenario | Agent execution | Independent verification | Result |
|---|---|---|---|
| Healthy | COMPLETED | PASS | Order uses A002 |
| Stale retrieval | COMPLETED | FAIL | Order remains at A001 |
| Stale retrieval with REFRESH | COMPLETED | FAIL, then PASS | Order changes to A002 |

Exit code 0 means the specified demonstration produced its expected verification outcome. The stale scenario intentionally expects FAIL. Unexpected outcomes return 1; invalid arguments return 2. Exit code 0 is therefore not a general task-success signal.

Each command creates a fresh temporary SQLite database, reads real persisted local state and removes that database on exit. `--show-events` prints the event sequence. The CLI does not retain durable session history. Logical timestamps are deterministic simulated time; they are not measured latency.

## Testing and Validation

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

The complete included suite covers healthy and faulty execution, verification, bounded recovery, refusal conditions, failed recovery tools, event integrity, hashing and read-only database behavior. The [reproducibility report](docs/reproducibility.md) records the exact environment, commands, exit codes, test totals and representative outputs. Passing tests establish only the behavior exercised by those tests.

## Presentation Traceability and Academic Evidence

The October 2026 [Project Phase I final-review presentation](docs/presentation-evidence-map.md) is supported by an explicit slide-to-source and slide-to-test evidence map. The source contains the **deterministic Phase I implementation only**; literature precedents and proposed Phase II integrations are distinguished from executable functionality.

- [Presentation-to-implementation traceability](docs/presentation-evidence-map.md): key claims, their source and test evidence, and implementation boundaries.
- [Scholarly foundations](docs/scholarly-foundations.md): ten cited research publications, publication status, technical relevance, and non-adoption caveats.
- [SDG alignment and evidence limitations](docs/sdg-alignment.md): qualitative mapping to SDGs 9, 8, and 4 without unsupported impact claims.
- [Continuous validation workflow](.github/workflows/phase-i-validation.yml): Windows Python 3.12 tests, static checks and demonstration outcomes, subject to GitHub Actions being enabled by the repository owner.
- [Software citation metadata](CITATION.cff): machine-readable citation for the institutional academic edition, not a research-publication DOI.

The final presentation's supporting-source entry [S1] identifies commit `79d6ade89d1908d9af6bc87b4e785578061b110a`, the **frozen original Phase I implementation snapshot**. These subsequent documentation and validation additions do not change its executable source. If the institution requires the presentation to cite the latest documentation commit, update the supporting-source reference explicitly rather than silently rewriting historical evidence.

## Static Analysis and Formatting

Ruff 0.17.2 was used for lint rules `E4`, `E7`, `E9`, `F` and `I`, together with a formatting check, consistent with the [reproducibility report](docs/reproducibility.md). From the repository root, after completing the installation above, run:

```powershell
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check "ruff==0.17.2"
.\.venv\Scripts\python.exe -m ruff check --select E4,E7,E9,F,I src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
```

Both checks are non-mutating. Ruff is an optional development validation tool and is not a runtime dependency.

## Limitations

- The agent is deterministic; no real LLM controls execution or recovery.
- Operational early failure forecasting, calibrated runtime confidence and automatic fault localization are not implemented.
- The verifier is fixed to C001 and O001 and trusts the local schema and database. Its reads are not one atomic cross-table snapshot.
- The recovery bound is per controller instance in one process. It is not a persistent global admission service, universal enforcement layer or arbitrary rollback mechanism.
- Recovery checks use supplied verification results; they are not cryptographically bound to invocation arguments or fresh state. Concurrent changes outside the tested order-hash checks require further work.
- The web and MCP demonstrations are excluded. No dashboard, network service or production deployment is provided.

## Future Work

Phase II work will prioritize configured workflows, task-bound verification, persistent recovery budgets and session evidence, additional controlled faults, and invocation-correct integration. Any future LLM integration or forecasting capability will require its own implementation and evaluation before being described as delivered. See the [Phase II roadmap](docs/implementation-status.md).

## Alignment with Sustainable Development Goals

The following alignments are qualitative interpretations of the implemented Phase I prototype, not evidence of progress against official United Nations indicators:

- **[SDG 9 — Industry, Innovation and Infrastructure](https://sdgs.un.org/goals/goal9) [U1] — Primary thematic alignment (Targets 9.5 and 9.b).** Controlled fault injection, independent persisted-state verification, and bounded correction constitute a reproducible technical study of dependable digital engineering. No industrial deployment, infrastructure reliability measurement, or innovation-policy effect is claimed.
- **[SDG 8 — Decent Work and Economic Growth](https://sdgs.un.org/goals/goal8) [U3] — Prospective application (Target 8.2).** A verification-and-recovery approach might inform more dependable business-process automation. The synthetic order workflow does not establish increased productivity, employment, or economic impact.
- **[SDG 4 — Quality Education](https://sdgs.un.org/goals/goal4) [U2] — Secondary educational relevance (Target 4.4).** The available code, architecture, demonstration procedures, and tests may support the study of software dependability. No formal educational intervention or measured learning benefit is claimed.

For target-specific evidence and explicit limitations, consult [Sustainable Development Goal Alignment: Scope and Evidence](docs/sdg-alignment.md). The project makes no claim of UN endorsement or certified SDG impact.

## Project Team and Supervision

Team members: Adhil Naseem, Nithin C, Sath Sree Hari K. Project guide: Neethu George.

## References

### Scholarly Literature

The numbering below is identical to the ten scholarly works cited in the Phase I final-review presentation. The 2026 arXiv entries **[3]–[5] are preprints**, not peer-reviewed publications. A comparison of their methods with the implemented prototype is provided in [Scholarly Foundations and Scope of Adoption](docs/scholarly-foundations.md).

- **[1]** C. Lee, S. J. Park, A. Kejriwal, S. Matsushita, and J. K. Ousterhout, “Implementing Linearizability at Large Scale and Low Latency,” *Proceedings of the 25th ACM Symposium on Operating Systems Principles (SOSP)*, pp. 71–86, 2015. [DOI: 10.1145/2815400.2815416](https://doi.org/10.1145/2815400.2815416).
- **[2]** E. Yel *et al.*, “Assured Runtime Monitoring and Planning: Toward Verification of Neural Networks for Safe Autonomous Operations,” *IEEE Robotics & Automation Magazine*, vol. 27, no. 2, pp. 102–116, 2020. [DOI: 10.1109/MRA.2020.2981114](https://doi.org/10.1109/MRA.2020.2981114).
- **[3]** B. Mohammadi *et al.*, “Atomix: Timely, Transactional Tool Use for Reliable Agentic Workflows,” *arXiv preprint* arXiv:2602.14849, 2026. [arXiv](https://arxiv.org/abs/2602.14849).
- **[4]** D. Sah *et al.*, “UndoBench: Separating Task Competence from Recovery Capability in Tool-Using AI Agents,” *arXiv preprint* arXiv:2610.05622, 2026. [arXiv](https://arxiv.org/abs/2610.05622).
- **[5]** J. Li, “Where Does Exactly-Once Live? Model, Harness, and Tool-Contract Effects on Duplicate Side Effects in LLM Agents,” *arXiv preprint* arXiv:2609.29095, 2026. [arXiv](https://arxiv.org/abs/2609.29095).
- **[6]** H. Garcia-Molina and K. Salem, “Sagas,” *Proceedings of the 1987 ACM SIGMOD International Conference on Management of Data*, pp. 249–259, 1987. [DOI: 10.1145/38713.38742](https://doi.org/10.1145/38713.38742).
- **[7]** J. H. Saltzer, D. P. Reed, and D. D. Clark, “End-to-End Arguments in System Design,” *ACM Transactions on Computer Systems*, vol. 2, no. 4, pp. 277–288, 1984. [DOI: 10.1145/357401.357402](https://doi.org/10.1145/357401.357402).
- **[8]** S. Yao *et al.*, “ReAct: Synergizing Reasoning and Acting in Language Models,” *International Conference on Learning Representations (ICLR)*, 2023. [arXiv:2210.03629](https://arxiv.org/abs/2210.03629).
- **[9]** S. Yao, N. Shinn, P. Razavi, and K. Narasimhan, “τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains,” *International Conference on Learning Representations (ICLR)*, 2025. [Proceedings](https://proceedings.iclr.cc/paper_files/paper/2025/hash/1b126cc38b8638e07bef37e7b2bb72bf-Abstract-Conference.html).
- **[10]** J. Lu *et al.*, “ToolSandbox: A Stateful, Conversational, Interactive Evaluation Benchmark for LLM Tool Use Capabilities,” *Findings of the Association for Computational Linguistics: NAACL 2025*, pp. 1160–1183, 2025. [DOI: 10.18653/v1/2025.findings-naacl.65](https://doi.org/10.18653/v1/2025.findings-naacl.65).

### Supporting Sources and Technical Documentation

- **[S1]** IMMUNE Project Team, *IMMUNE — Phase I Academic Edition*, [institutional implementation repository](https://github.com/VAST-CSE/2023-27-MAIN-C13-ADHIL-NASEEM), 2026. The presentation cites the [frozen implementation snapshot](https://github.com/VAST-CSE/2023-27-MAIN-C13-ADHIL-NASEEM/commit/79d6ade89d1908d9af6bc87b4e785578061b110a); later documentation updates do not change that implementation.
- **[U1]** United Nations, “[Goal 9: Industry, Innovation and Infrastructure](https://sdgs.un.org/goals/goal9).”
- **[U2]** United Nations, “[Goal 4: Quality Education](https://sdgs.un.org/goals/goal4).”
- **[U3]** United Nations, “[Goal 8: Decent Work and Economic Growth](https://sdgs.un.org/goals/goal8).”
- [Python 3.12 documentation](https://docs.python.org/3.12/); [SQLite read-only URI mode](https://www.sqlite.org/uri.html); [SQLAlchemy 2.0 transaction interfaces](https://docs.sqlalchemy.org/en/20/core/connections.html).

No project license is included. Public availability alone does not grant permission to copy, modify or redistribute the project source.
