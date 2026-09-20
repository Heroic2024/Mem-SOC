# Product Backlog

Central register of open work: bugs, missed or partial requirements,
planned features, test gaps worth tracking, and tech debt.

**Use this whenever something is not done, not specified clearly enough, or
known to be wrong — even if it is already noted somewhere else** (a plan,
the FRD, the test matrix, a code comment). Duplication with those documents
is expected and fine; this file is the one place you can see all of it at
once.

This register is **mandatory** for every contributor, human or AI. See
[`../CLAUDE.md`](../CLAUDE.md) § *Product Backlog* for the rules.

---

## Fields

| Column | Meaning |
|--------|---------|
| **ID** | Stable key `BL-###` |
| **Type** | `feature` · `bug` · `requirement` · `test` · `tech-debt` · `docs` |
| **Summary** | One line — what is wrong or missing |
| **Related** | FR IDs, plans, files, matrix rows |
| **Created by** | Who added the backlog row |
| **Created** | Date (YYYY-MM-DD) |
| **Status** | `open` · `in_progress` · `blocked` · `done` · `wont_fix` |
| **Resolution** | How it was closed (empty while open) |
| **Priority** | `P1` (critical) · `P2` (high) · `P3` (medium) · `P4` (low) · `P5` (deferred / test-only / known limitation) |

Tables are sorted by **ID**. Use Priority for triage only — never re-sort
or renumber rows. IDs are permanent: a closed row stays in place with
`Status: done`, it is not deleted.

---

## Open — research & requirements

| ID | Type | Summary | Related | Created by | Created | Status | Resolution | Priority |
|---|---|---|---|---|---|---|---|---|
| BL-001 | requirement | Ground-truth handling is undecided: are dataset labels the evaluation oracle only, or do they also seed memory as confirmed verdicts? Must not be silently picked — seeding memory turns it into an oracle and inflates results. | `PROJECT_BRIEF.md` §5; `CLAUDE.md` § When Requirements Are Unclear | Claude (restructure) | 2026-09-20 | open | | P1 |
| BL-002 | feature | Layer 3, the memory layer, does not exist yet. No ChromaDB, no embedding model, no write path, no read path. Only `memory/case_ranker/` (case compaction) is built. This is the research crux — everything else exists to measure it. | `PROJECT_BRIEF.md` §4 Layer 3, Phase 2; `docs/memory-layer/` | Claude (restructure) | 2026-09-20 | open | | P1 |
| BL-003 | feature | No two-arm experiment harness. There is no arm toggle, no A/B runner, and no scoring harness, so the controlled comparison the project is built around cannot be run. Arm B must be Arm A plus a toggleable module, never a parallel codepath. | `PROJECT_BRIEF.md` §3, §9, Phase 4; `CLAUDE.md` § Experimental Integrity | Claude (restructure) | 2026-09-20 | open | | P1 |
| BL-004 | test | Error propagation is named as the single most important failure mode and is required to be **explicitly tested** — inject a mis-stored case, measure downstream corruption. No such test exists. | `PROJECT_BRIEF.md` §8 | Claude (restructure) | 2026-09-20 | open | | P1 |
| BL-005 | requirement | Phase 3 decisions all still open: top-k, similarity threshold, write policy (every case / high-confidence only / confirmed only), and cold-start handling (warm-start seed vs. report cold and steady state separately). | `PROJECT_BRIEF.md` Phase 3; `docs/memory-layer/07-open-questions.md` | Claude (restructure) | 2026-09-20 | open | | P2 |
| BL-006 | requirement | No `schema_version` on stored cases. The brief requires a version bump and a new store if the detector is retrained on NF-CICIDS2018-v3, because the attack label vocabulary is disjoint and every stored case is invalidated. | `PROJECT_BRIEF.md` §8 | Claude (restructure) | 2026-09-20 | open | | P2 |
| BL-007 | requirement | Evaluation metrics are defined in prose only. False-positive volume (primary), precision/recall/F1, verdict consistency, latency and token-cost overhead all need concrete definitions and a frozen harness before results are produced. | `PROJECT_BRIEF.md` Phase 4 | Claude (restructure) | 2026-09-20 | open | | P2 |
| BL-008 | feature | Dual-audience reporting is only half delivered. The report has a technical view; the plain-language non-technical view is a named deliverable and is not separately produced. | `PROJECT_BRIEF.md` §4 Layer 4, §10 | Claude (restructure) | 2026-09-20 | open | | P3 |

## Open — bugs & correctness

| ID | Type | Summary | Related | Created by | Created | Status | Resolution | Priority |
|---|---|---|---|---|---|---|---|---|
| BL-020 | bug | `GITHUB_PAT` is injected into the `report` and `controller` containers. Both use `env_file: ../.env`, which passes the whole file, but only `GROQ_API_KEY` is needed. Verified by `docker exec memsoc-report env`. Fix needs a decision on where `GITHUB_PAT` should live. | `deploy/docker-compose.yml`; `.env` | Claude (restructure) | 2026-09-20 | open | | P2 |
| BL-021 | bug | `live_results.jsonl` is append-only across runs by default (`--reset` is opt-in), so one report can mix flows from two unrelated generation runs. `generate_report --limit` only slices the tail; it does not scope to a run. No run ID ties captures to the generation that produced them. | `src/memsoc/triage/live_capture.py`; `src/memsoc/triage/generate_report.py` | Claude (restructure) | 2026-09-20 | open | | P3 |
| BL-022 | bug | `nfv3_log_generator.py` opens its outputs with mode `w`, so any run silently destroys the previous `generated_logs.jsonl` and `ground_truth.csv`. With `MEMSOC_SAMPLE_SIZE` now settable from the controller, a small demo run wipes a large generated corpus with no warning. | `src/memsoc/logstream/nfv3_log_generator.py` | Claude (restructure) | 2026-09-20 | open | | P3 |
| BL-023 | bug | Report retention (`REPORTS_TO_KEEP = 10`) deletes older `security_report_*.json/.md` pairs automatically. Combined with BL-021 this can discard a report that is the only record of a particular run. | `src/memsoc/triage/config.py`; `src/memsoc/triage/generate_report.py` | Claude (restructure) | 2026-09-20 | open | | P4 |

## Open — tests

| ID | Type | Summary | Related | Created by | Created | Status | Resolution | Priority |
|---|---|---|---|---|---|---|---|---|
| BL-040 | test | No automated tests for the triage layer or the report API. `stats_engine`, `report_prompt`, `generate_report` and both `api/routes_reports.py` endpoints are untested; only the detection path has contract tests. | `tests/test_pipeline.py`; `src/memsoc/api/routes_reports.py` | Claude (restructure) | 2026-09-20 | open | | P2 |
| BL-041 | test | Stream mode (`run_pipeline --mode stream`, `stream_to_api.py`) was not exercised after the restructure. Its imports compile and it is covered by no test; the resumable cursor path in particular is unverified. | `src/memsoc/logstream/stream_to_api.py` | Claude (restructure) | 2026-09-20 | open | | P3 |
| BL-042 | test | No CI. Tests run only when somebody remembers to run them, so the contract tests cannot catch a regression at push time. | — | Claude (restructure) | 2026-09-20 | open | | P3 |
| BL-043 | test | `tests/manual/` smoke scripts need the full multi-GB dataset and take minutes, so they are never run. They are also not asserted — they print and exit 0. | `tests/manual/` | Claude (restructure) | 2026-09-20 | open | | P4 |
| BL-044 | test | The dashboard has no tests and no lint step. A broken render is only caught by opening a browser. | `dashboard/` | Claude (restructure) | 2026-09-20 | open | | P4 |

## Open — tech debt & docs

| ID | Type | Summary | Related | Created by | Created | Status | Resolution | Priority |
|---|---|---|---|---|---|---|---|---|
| BL-060 | tech-debt | No `pyproject.toml`. The `memsoc` package is importable only because every entry point sets `PYTHONPATH=src`. It should be a properly declared, installable package. | `src/memsoc/` | Claude (restructure) | 2026-09-20 | open | | P3 |
| BL-061 | docs | `docs/design-assets/generate_diagrams.py` and `content_data.py` still label components with pre-restructure names (`final_ml_model_v1`, `LLMTriage`), so the rendered PNGs in `design-assets/` and the design document built from them are stale. Not regenerated during the restructure because that churns binary assets without review. | `docs/design-assets/` | Claude (restructure) | 2026-09-20 | open | | P3 |
| BL-062 | docs | Two overlapping operations guides. `docs/deployment/operations.md` (1181 lines) is authoritative; `docs/archive/operations-legacy.md` (418 lines) duplicates much of it and is banner-marked but not yet merged or deleted. | `docs/deployment/operations.md`; `docs/archive/operations-legacy.md` | Claude (restructure) | 2026-09-20 | open | | P3 |
| BL-063 | docs | `docs/deployment/operations.md` had its commands and paths mechanically rewritten for the new layout. The commands were corrected, but its 1181 lines of surrounding prose have not been read end to end against the current system. | `docs/deployment/operations.md` | Claude (restructure) | 2026-09-20 | open | | P3 |
| BL-064 | docs | `docs/detection/progress.md` and `docs/detection/demo.md` overlap substantially and both read as point-in-time status rather than reference documentation. | `docs/detection/` | Claude (restructure) | 2026-09-20 | open | | P4 |
| BL-065 | tech-debt | `requirements/research-lock.txt` is a UTF-16-encoded 121-package `pip freeze` of a Jupyter environment. It is kept only as a record of the training environment and is not installable as-is. | `requirements/research-lock.txt` | Claude (restructure) | 2026-09-20 | open | | P4 |
| BL-066 | tech-debt | Application logs are written to `/app/logs` inside each container and are not mounted out, so they vanish when a container is recreated. | `deploy/*.Dockerfile`; `src/memsoc/paths.py` | Claude (restructure) | 2026-09-20 | open | | P4 |
| BL-067 | tech-debt | `artifacts/reports/sample-fuzzers_report.json` is a stale report in an earlier, incompatible single-alert format. The API already filters it out by name pattern, but it remains on disk as a trap. | `artifacts/reports/`; `src/memsoc/api/routes_reports.py` | Claude (restructure) | 2026-09-20 | open | | P5 |
| BL-068 | tech-debt | The report API sets `allow_origins=["*"]` and neither API has authentication or rate limiting. Acceptable for a localhost capstone; documented here so it is a known limitation rather than an oversight. | `src/memsoc/api/app_reports.py` | Claude (restructure) | 2026-09-20 | open | | P5 |
| BL-069 | tech-debt | ChromaDB's documented limits — high memory use at scale, weak scalability past millions of vectors — must appear in the limitations write-up. Not a blocker for a fixed-dataset comparison. | `PROJECT_BRIEF.md` §6; `docs/memory-layer/06-risks-and-limitations.md` | Claude (restructure) | 2026-09-20 | open | | P5 |

## Closed

| ID | Type | Summary | Related | Created by | Created | Status | Resolution | Priority |
|---|---|---|---|---|---|---|---|---|
| BL-080 | tech-debt | The repo carried two copies of the application (`Deployment/` duplicated the root tree) and they had drifted in opposite directions, so neither was canonical. | `Deployment/`; `LLMTriage/`; `final_ml_model_v1/`; `log_generation/` | Claude (restructure) | 2026-09-20 | done | Collapsed to one tree under `src/memsoc/`. Both divergent behaviours preserved: `MEMSOC_SAMPLE_SIZE` from the Deployment generator, artifacts-dir resolution from the root `live_capture.py`. Commit `2f35cb8`. | P1 |
| BL-081 | tech-debt | Three byte-identical copies of the LightGBM pickles were committed (~108MB total). | `models/` | Claude (restructure) | 2026-09-20 | done | md5-verified identical, collapsed to a single `models/` directory; ~72MB reclaimed. Commit `2f35cb8`. | P2 |
| BL-082 | tech-debt | HTTP endpoints were split across unrelated trees (`final_ml_model_v1/src/api/server.py`, `LLMTriage/report_server.py`), so there was no single place to look when a route misbehaved. | `src/memsoc/api/` | Claude (restructure) | 2026-09-20 | done | All routes consolidated into `src/memsoc/api/`, route table documented in `api/__init__.py`, shared shapes in `api/schemas.py`. Still two ASGI apps on two ports by design. Commit `2f35cb8`. | P2 |
| BL-083 | bug | `controller.py` printed `Dashboard: http://localhost:8081` while compose published the dashboard on `8080`. | `src/memsoc/controller.py` | Claude (restructure) | 2026-09-20 | done | The controller now prints host-facing URLs passed in by compose from the same variables that publish the ports. Commit `5bbd2de`. | P2 |
| BL-084 | bug | The dashboard bundle hardcoded `http://127.0.0.1:8001` at build time, so changing the published report port silently broke it. | `deploy/dashboard.Dockerfile`; `dashboard/src/api.js` | Claude (restructure) | 2026-09-20 | done | `VITE_API_URL` is now a build arg driven by `MEMSOC_REPORT_PORT`, the same variable that publishes the port. Commit `5bbd2de`. | P2 |
| BL-085 | bug | Dependents raced the detection container: it reported "up" while still unpickling ~37MB, so `log_generation` could fail before models finished loading. | `deploy/docker-compose.yml`; `src/memsoc/api/app_detection.py` | Claude (restructure) | 2026-09-20 | done | The pipeline is warmed by the app's lifespan hook, making `/health` a true readiness signal; dependents use `condition: service_healthy`. Commit `5bbd2de`. | P2 |
| BL-086 | tech-debt | Generated runtime artifacts were committed to git (`generated_logs.jsonl`, `stream_index.npy`, case-ranker outputs, generated reports). | `.gitignore`; `artifacts/` | Claude (restructure) | 2026-09-20 | done | Moved to `artifacts/` and untracked; they are reproducible from a seeded run. Files left untouched on disk. Commit `2f35cb8`. | P3 |
| BL-087 | tech-debt | Two rival Docker stacks existed: a root single-image `Dockerfile`/`docker-compose.yml` and the five-service `Deployment/docker-compose.yml` that was actually running. | `deploy/docker-compose.yml` | Claude (restructure) | 2026-09-20 | done | Root stack deleted; its useful one-shots (`paths`, `generate`, `tests`) folded into `deploy/docker-compose.yml` behind `--profile tools`. Old guide archived. Commit `5bbd2de`. | P2 |
| BL-088 | bug | Two standalone smoke scripts were named `test_*.py` and broke `unittest discover` once they landed in `tests/`; both also referenced a `data/raw/` dataset path that no longer exists. | `tests/manual/` | Claude (restructure) | 2026-09-20 | done | Moved to `tests/manual/` outside the discovery pattern and repointed at `paths.DATASET_CSV`. 13/13 contract tests pass. Commit `5bbd2de`. | P3 |
