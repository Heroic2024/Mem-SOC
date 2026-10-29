# MemSOC Documentation

Start here. Design context is in [`../PROJECT_BRIEF.md`](../PROJECT_BRIEF.md);
agent operating rules are in [`../CLAUDE.md`](../CLAUDE.md).

Every question the project still has to answer, and the answers already
settled, are in **[`decisions.md`](./decisions.md)**. Read that before
starting work.

Open work — bugs, gaps, tech debt — is tracked in
**[`PRODUCT_BACKLOG.md`](./PRODUCT_BACKLOG.md)**. Anything not done, not
specified clearly enough, or known to be wrong belongs there.

---

## Naming convention

Directories and files are **lower-kebab-case**. Numbered prefixes
(`01-`, `02-`…) mean there is a reading order. `README.md` is the index
of its own directory. Nothing else is capitalised except
`PRODUCT_BACKLOG.md`, which is deliberately loud.

---

## By layer

The system is four layers (see `PROJECT_BRIEF.md` §4). Each maps to one
package under `src/memsoc/` and one directory here.

| Layer | Code | Docs |
|---|---|---|
| 1 — Data stream | `src/memsoc/logstream/` | [`log-generation/`](./log-generation/) |
| 2 — Detection (frozen ML) | `src/memsoc/detection/` | [`detection/`](./detection/) |
| 3 — Memory (**the research crux**) | `src/memsoc/memory/` | [`memory-layer/`](./memory-layer/) |
| 4 — LLM triage & reporting | `src/memsoc/triage/` | [`llm-triage/`](./llm-triage/) |
| — HTTP surface | `src/memsoc/api/` | [`detection/api-architecture.md`](./detection/api-architecture.md) |

## By task

| I want to… | Read |
|---|---|
| **Know what still needs deciding, and what was already decided** | [`decisions.md`](./decisions.md) |
| **Know what I am supposed to be building** | [`work-split.md`](./work-split/work-split.md) |
| **Set up, or pull after the restructure** | [`deployment/operations.md`](./deployment/operations.md) **§2 — Before You Test** |
| Run the stack | [`deployment/operations.md`](./deployment/operations.md) |
| Browse every API endpoint in one place | `http://localhost:8080/api-docs` — see [`deployment/architecture.md`](./deployment/architecture.md) |
| Understand the container topology and ports | [`deployment/architecture.md`](./deployment/architecture.md) |
| See the end-to-end flow | [`architecture/end-to-end-pipeline.md`](./architecture/end-to-end-pipeline.md) |
| Understand the memory layer design | [`memory-layer/README.md`](./memory-layer/README.md) |
| See the retrieval-quality charts (token fit, family match, thresholds) | [`../notebooks/retrieval-quality.ipynb`](../notebooks/retrieval-quality.ipynb) — run in the memory venv; PNGs land in `artifacts/figures/` |
| Know what is broken or missing | [`PRODUCT_BACKLOG.md`](./PRODUCT_BACKLOG.md) |
| See where the project stands | [`status/phase0.md`](./status/phase0.md) |
| **See every test result so far (Arm A and B together) and the options for the next run** | [`status/testing-results-to-date.md`](./status/testing-results-to-date.md) |
| **Read the first complete three-arm result (Gemma 4 26B, 165 alerts, with figures)** | [`status/gemma-p3-results.md`](./status/gemma-p3-results.md) |
| See the Qwen 3.8 27B A vs B-self result and figures | [`status/qwen-results.md`](./status/qwen-results.md) |
| See the Groq gpt-oss-20b three-arm result on protocol v1 and figures | [`status/groq-gptoss20b-p1-results.md`](./status/groq-gptoss20b-p1-results.md) |
| **Run the three-model memory test as a tester (step-by-step, for you and your AI agent)** | [`status/testing-protocol-v3.md`](./status/testing-protocol-v3.md) |
| **Run the live demo for the final presentation** | [`status/final-demo-runbook.md`](./status/final-demo-runbook.md) |
| See the new experiments the 2026-10-28 paper review asks for, and the order to run them | [`status/paper-review-experiments.md`](./status/paper-review-experiments.md) |

---

## Directory map

```text
docs/
├── README.md                  this file
├── decisions.md               open questions, settled decisions, and what was run
├── work-split/                who owns what, and the interfaces between us
│   ├── work-split.md          ownership by layer and the one memory interface
│   └── protocol-v4-work-split.md   protocol v4 supplementary experiments, split three ways
├── PRODUCT_BACKLOG.md         central register of open work
├── architecture/              system-wide views
│   ├── end-to-end-pipeline.md
│   └── diagrams/              rendered activity/flow/sequence/state diagrams
├── deployment/
│   ├── operations.md          authoritative run guide
│   └── architecture.md        container topology, ports, repo layout
├── detection/                 Layer 2 — the frozen classifier
│   ├── api-architecture.md
│   ├── model-overview.md
│   ├── model-justification.md
│   ├── demo.md
│   ├── progress.md
│   └── assets/
├── log-generation/            Layer 1
│   └── overview.md
├── llm-triage/                Layer 4
│   ├── report-generation.md
│   └── attack-categories.md
├── memory-layer/              Layer 3 — the research variable
│   ├── README.md
│   ├── 01-architecture.md … 09-setup-plan.md
│   ├── alert-to-case.md
│   ├── chromadb-setup.md
│   └── retrieval-precision-investigation.md
├── design-assets/             scripts + figures for the design document
├── status-assets/             scripts + figures for the status write-ups
├── status/
│   ├── phase0.md
│   ├── testing-results-to-date.md
│   ├── testing-protocol-v3.md
│   ├── gemma-p3-results.md
│   ├── qwen-results.md
│   ├── groq-gptoss20b-p1-results.md
│   ├── final-demo-runbook.md
│   └── paper-review-experiments.md
└── archive/                   superseded, banner-marked, do not follow
```

---

## Known documentation debt

The figure-generation scripts in `design-assets/` still label components
with pre-restructure names (`final_ml_model_v1`, `LLMTriage`). The
rendered PNGs are stale in the same way. Tracked as **BL-061** — the
figures were not regenerated as part of the restructure because that
would churn binary assets without review.
