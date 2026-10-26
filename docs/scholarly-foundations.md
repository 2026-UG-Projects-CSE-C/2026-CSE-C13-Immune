# Scholarly Foundations and Scope of Adoption

## Academic Positioning

The October 2026 IMMUNE Phase I presentation cites the following **ten** research publications. The entries are organized by presentation citation number rather than claiming historical priority or novel methods. Seven are published conference/journal papers; **[3], [4] and [5] are 2026 arXiv preprints** and must not be presented as peer reviewed. The technical relationship to the academic code is described narrowly.

| Ref. | Source (bibliographic record) | Established contribution and relevance | Implemented in Phase I? |
|---|---|---|---|
| [1] | C. Lee et al., “Implementing Linearizability at Large Scale and Low Latency,” *ACM SOSP*, 2015, pp. 71–86. [DOI](https://doi.org/10.1145/2815400.2815416) | RIFL supplies identity/completion-based RPC retry semantics; motivates guarding against duplicate effects. | **No** RIFL or exactly-once RPC contract |
| [2] | E. Yel et al., “Assured Runtime Monitoring and Planning: Toward Verification of Neural Networks for Safe Autonomous Operations,” *IEEE Robotics & Automation Magazine*, 27(2), 102–116, 2020. [DOI](https://doi.org/10.1109/MRA.2020.2981114) | Motivates separation of execution and runtime monitoring/assurance. | **No** neural verification, reachable-set proof, or autonomous safety guarantee |
| [3] | B. Mohammadi et al., “Atomix: Timely, Transactional Tool Use for Reliable Agentic Workflows,” **arXiv preprint**, 2026. [arXiv:2602.14849](https://arxiv.org/abs/2602.14849) | Transactional settlement of agent tool effects; relevant to possible future multi-tool effect coordination. | **No** Atomix protocol |
| [4] | D. Sah, T. Sah, H. Jain and T. Sah, “UndoBench: Separating Task Competence from Recovery Capability in Tool-Using AI Agents,” **arXiv preprint**, 2026. [arXiv:2610.05622](https://arxiv.org/abs/2610.05622) | Distinguishes nominal success from failure recovery using controlled intervention and external-state/effect evidence. | **No** UndoBench experiments or benchmark measurements |
| [5] | J. Li, “Where Does Exactly-Once Live? Model, Harness, and Tool-Contract Effects on Duplicate Side Effects in LLM Agents,” **arXiv preprint**, 2026. [arXiv:2609.29095](https://arxiv.org/abs/2609.29095) | Analyzes duplicate write effects under ambiguous responses and varying agent/tool contracts. | **No** late-commit, distributed exactly-once, or LIMBO benchmark guarantee |
| [6] | H. Garcia-Molina and K. Salem, “Sagas,” *ACM SIGMOD International Conference on Management of Data*, 1987, pp. 249–259. [DOI](https://doi.org/10.1145/38713.38742) | Long-lived transactions and compensating actions. | **No** general Saga compensation; REFRESH is task-specific correction |
| [7] | J. H. Saltzer, D. P. Reed and D. D. Clark, “End-to-End Arguments in System Design,” *ACM Transactions on Computer Systems*, 2(4), 277–288, 1984. [DOI](https://doi.org/10.1145/357401.357402) | End-to-end correctness principle; motivates outcome checking at a suitable task boundary. | A **limited application of the principle** through task-specific persisted-state checks |
| [8] | S. Yao et al., “ReAct: Synergizing Reasoning and Acting in Language Models,” *ICLR*, 2023. [Source](https://arxiv.org/abs/2210.03629) | Reasoning-and-acting language-model paradigm motivating agent/tool interactions. | **No** ReAct model, chain-of-thought planner, or LLM execution |
| [9] | S. Yao, N. Shinn, P. Razavi and K. Narasimhan, “τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains,” *ICLR*, 2025. [Proceedings](https://proceedings.iclr.cc/paper_files/paper/2025/hash/1b126cc38b8638e07bef37e7b2bb72bf-Abstract-Conference.html) | Evaluates agents by comparing final database state with annotated task goals. | **No** τ-bench benchmark; similar restricted outcome-checking concept |
| [10] | J. Lu et al., “ToolSandbox: A Stateful, Conversational, Interactive Evaluation Benchmark for LLM Tool Use Capabilities,” *Findings of NAACL*, 2025, pp. 1160–1183. [DOI](https://doi.org/10.18653/v1/2025.findings-naacl.65) | Evaluates tool use with state dependencies and intermediate/final milestones. | **No** ToolSandbox environment or benchmark results |

## Relation to the Phase I Demonstration

The implemented system does **not** claim a novel distributed transaction algorithm, formal safety proof, or advances over the cited benchmarks. It demonstrates a controlled, locally reproducible engineering separation between (i) what an agent observed, (ii) what persisted in an SQLite order record, and (iii) whether an explicitly requested single REFRESH correction brought the task state into agreement with fixed predicates.

The most direct methodological parallel is to **final-state evaluation** in [9], with the limitations of a single synthetic task and trusted local schema. Reference [7] supplies general system-design motivation. References [1], [3], [5] and [6] primarily motivate **out-of-scope** questions concerning ambiguous writes, global effect contracts and compensation. Reference [2] is a runtime-assurance precedent; the project does not implement its monitoring algorithms. References [4] and [10] illustrate evaluation practices not reproduced by this project.

## Boundaries of Evidence

- A **literature reference** is evidence of prior work, not evidence that the referenced method is implemented here.
- The order-task verifier has six known predicates for C001/O001 and uses a separate read-only SQLite connection. It is not a cryptographic guarantee, remote oracle, or single atomic database snapshot across all reads.
- Bounded REFRESH is admitted after a supplied FAIL and limited in memory to one attempt per controller instance. It does not provide general exactly-once effect semantics.
- The executable examples are **fixed deterministic scenarios**, not a statistical benchmark against [4], [9] or [10].
- Preprint dates and metadata correspond to the cited October 2026 versions; they remain explicitly identified as preprints.

## Source of the Citation Set

This bibliography matches presentation slides 5–8 and 23–25. Project source [S1] and official UN goals [U1]–[U3] on slide 26 are **supporting sources** rather than members of the ten-paper research bibliography.
