# Agentic SOC — Memory-Augmented LLM Alert Triage

> Capstone project. Status: **Phase 0 — project initialization.**

A SOC alert triage system built around a persistent memory layer, evaluated against a memoryless baseline under strict experimental control.

---

## The Problem

SOC analysts drown in alerts, most of which are false positives. Worse, they repeatedly re-investigate alerts that have *already been resolved* — because the knowledge that resolved them lives in one analyst's head, or a Slack thread, rather than in the tooling.

When that analyst rotates off shift or leaves the team, the knowledge goes with them. The next person starts from zero.

## The Idea

Give the SOC a memory.

Every triaged case — the alert, its context, the verdict, and the reasoning — is embedded and stored in a vector database. When a new alert arrives, the system retrieves the most similar past cases and hands them to the LLM as precedent, so it reasons *with* institutional history instead of from scratch.

The result should be fewer false positives, more consistent verdicts, and knowledge that persists across shifts, analysts, and time — decoupled from any single person.

## The Research Question

**What does a memory layer actually contribute to LLM-based alert triage?**

The memory layer is the crux of this research. Everything else in the system is held fixed so that its contribution can be isolated and measured.

---

## Architecture

```
[1] DATA STREAM  →  [2] DETECTION (ML)  →  [3] MEMORY (Vector DB)  →  [4] LLM TRIAGE + REPORTING
                                                    ↑______________________________|
                                                          (write-back loop)
```

| Layer | Component | Role |
|---|---|---|
| 1 | NF-* v3 flow replay | Sequential alert stream simulating live SOC ingest |
| 2 | LightGBM multiclass classifier | Produces alerts/scores. **Frozen** — not under evaluation |
| 3 | ChromaDB + sentence-transformers | **The research crux.** Stores and retrieves past cases by similarity |
| 4 | LLM | Produces verdicts and explainable reports |

## Experimental Design

Two arms, one variable.

- **Arm A — Memoryless baseline:** alert → LLM triage → verdict. No retrieval, no persistence.
- **Arm B — Memory-augmented:** alert → similarity retrieval → precedent injected into the same prompt → LLM triage → verdict → case written back to memory.

**Held constant across both arms:** the alert stream, the detection model, the LLM, and the prompts. The presence or absence of the memory layer is the *only* difference.

---

## Objectives

1. Reduce false-positive volume via similarity-based case retrieval.
2. Enable memory retention and detailed, explainable reporting.
3. Give the SOC institutional memory beyond a single shift or analyst.

## Deliverables

- **Memory retention** — vector DB storing past incidents as embeddings, retrieved by similarity.
- **Reporting & analysis** — explainable LLM-generated reports, not raw scores.
- **Dual-audience output** — a technical view for analysts and engineers, a plain-language view for management and compliance.

---

## Evaluation

Both arms replay the identical alert sequence. Compared on:

- **False-positive volume** (primary metric)
- Precision / recall / F1 against dataset ground truth
- Verdict consistency across similar alerts
- Latency and token-cost overhead from retrieval
- Qualitative quality of cited precedent

**A null or negative result is a legitimate outcome.** The evaluation is not designed to guarantee that memory wins.

## Known Risks

- **Error propagation** — a mis-triaged case in memory can repeat its error across every future similar alert. The most important failure mode; explicitly tested, not just noted.
- **Cold start** — memory begins empty, likely understating steady-state performance.
- **Retrieval noise** — a bad top-k or missing threshold could make the memory arm *worse* than baseline.
- **Dataset realism** — NF-UNSW-NB15-v3 / NF-CICIDS2018-v3 are synthetic testbed captures, not production traffic.
- **Frozen detector** — says nothing about behaviour with a noisy, real-world detection layer.

---

## Running it

> **Setting up, or pulling after the restructure?** Read
> **[`docs/deployment/operations.md` §2 — Before You Test](./docs/deployment/operations.md)**
> first. It covers first-time setup, migrating off the old `Deployment/`
> layout (order matters — stop the old stack *before* pulling), which
> images to rebuild, and a four-step pre-test checklist.

Three services start by default — detection (`:8000`), report (`:8001`)
and the dashboard (`:8080`):

```bash
docker compose -f deploy/docker-compose.yml build
docker compose -f deploy/docker-compose.yml up -d
```

Then open <http://localhost:8080> for the dashboard, or
<http://localhost:8080/api-docs> for **one page documenting every endpoint
in both services**, with working "Try it out" buttons. Each service also
keeps its own `/docs` on its own port.

Drive the full workflow interactively — generate flows, classify them,
produce a report:

```bash
docker compose -f deploy/docker-compose.yml --profile workflow run --rm controller
```

Useful one-shots:

```bash
# what resolved where, and what is missing
docker compose -f deploy/docker-compose.yml --profile tools run --rm paths

# contract tests
docker compose -f deploy/docker-compose.yml --profile tools run --rm tests
```

Every published port is defined once in `deploy/docker-compose.yml` and
can be overridden from `.env` (`MEMSOC_DETECTION_PORT`,
`MEMSOC_REPORT_PORT`, `MEMSOC_DASHBOARD_PORT`).

Full instructions, including the native (non-Docker) path:
**[`docs/deployment/operations.md`](./docs/deployment/operations.md)**.

---

## Layout

One source tree. `deploy/` holds build and orchestration files only.

```text
src/memsoc/        the application
├── paths.py       single source of truth for every path
├── api/           EVERY HTTP endpoint in the system
├── logstream/     Layer 1 — deterministic NetFlow replay
├── detection/     Layer 2 — frozen LightGBM + SHAP
├── memory/        Layer 3 — the memory layer (the research variable)
├── triage/        Layer 4 — LLM triage and reporting
└── controller.py  interactive end-to-end workflow driver

models/            the two LightGBM pickles
dashboard/         React app
deploy/            Dockerfiles + compose
requirements/      one file per deployable
artifacts/         all runtime output (gitignored)
tests/  docs/  data/
```

---

## Repository

- [`PROJECT_BRIEF.md`](./PROJECT_BRIEF.md) — authoritative design context. **Read this first.**
- [`CLAUDE.md`](./CLAUDE.md) — operating rules for anyone, human or AI, working in this repo.
- [`docs/README.md`](./docs/README.md) — documentation index.
- [`docs/PRODUCT_BACKLOG.md`](./docs/PRODUCT_BACKLOG.md) — **every known bug, gap and piece of tech debt.** Check here before assuming something is finished.
- [`docs/memory-layer/`](./docs/memory-layer/) — the memory layer (Layer 3): architecture, case schema, read/write paths, configuration, risks, open questions.

## Roadmap

- [ ] **Phase 0** — Setup, data prep, case schema definition
- [ ] **Phase 1** — Memoryless baseline (Arm A)
- [ ] **Phase 2** — Memory-augmented arm (Arm B)
- [ ] **Phase 3** — Tuning: top-k, threshold, write policy, cold start
- [ ] **Phase 4** — Evaluation and error-propagation analysis
- [ ] **Phase 5** — Reporting layer

## Stack

ChromaDB (Apache 2.0) · sentence-transformers · LightGBM multiclass classifier · NF-UNSW-NB15-v3 / NF-CICIDS2018-v3
