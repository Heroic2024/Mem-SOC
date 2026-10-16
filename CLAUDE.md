# CLAUDE.md — Agent Operating Instructions

Design context lives in `PROJECT_BRIEF.md`. Read it once at session start. **This file is the rules.**

---

## Product Backlog — MANDATORY

`docs/PRODUCT_BACKLOG.md` is the central register of open work: bugs, missed or partial requirements, planned features, test gaps worth tracking, and tech debt.

**Every agent must use it. This is not optional.**

### When to add a row

Add one whenever something is **not done**, **not specified clearly enough**, or **known to be wrong** — *even if it is already noted somewhere else* (a plan, the FRD, the test matrix, a code comment, a commit message). Duplication with those is expected. The backlog is the one place all of it is visible at once.

Concretely, add a row when you:

- find a bug you are not fixing in this task,
- leave a requirement partially implemented,
- skip, stub, or weaken a test,
- hit an ambiguity you had to flag rather than resolve,
- take a shortcut, leave a TODO, or knowingly add debt,
- notice a doc that is now wrong,
- decide something is out of scope (see *Working Method* — "report it, do not fix it" means **report it here**).

"I will mention it in my summary" is not sufficient. Summaries are lost when the session ends; the backlog is not.

### Rules

1. **Never invent an ID.** Read the file, take the next free number in the right block, and keep the table sorted by **ID**.
2. **IDs are permanent.** Never renumber, never reuse, never delete a row. A finished item stays in place with `Status: done` and a filled-in `Resolution`.
3. **Fill every column.** `Resolution` is the only one that may be empty, and only while the row is open.
4. **Priority is for triage only.** It never changes sort order.
5. **Close rows you actually finish.** If your change resolves an open row, set `Status: done`, write what closed it, and cite the commit.
6. **Ground every row in something you verified.** Cite the file, the command, or the observed behaviour in `Related`. Do not file speculative rows.
7. **Check the backlog before declaring anything complete.** If an open row covers the thing you are about to call finished, it is not finished.

### Fields

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

---

## Repository Map — Where Things Go

The repo holds **one** source tree. There are no second copies of anything. If you find yourself creating a parallel copy of a module, a Dockerfile, or a model file, stop — that is the exact problem the 2026-09-20 restructure removed.

```text
src/memsoc/            the entire application, one importable package
├── paths.py           single source of truth for every path
├── api/               EVERY HTTP endpoint in the system
├── logstream/         Layer 1 — deterministic NetFlow replay
├── detection/         Layer 2 — frozen LightGBM + SHAP
├── memory/            Layer 3 — the memory layer (THE research variable)
├── triage/            Layer 4 — LLM triage and report generation
└── controller.py      interactive end-to-end workflow driver

models/                the two LightGBM pickles — ONE copy
dashboard/             React app (Vite)
deploy/                Dockerfiles + docker-compose.yml, NO application code
requirements/          one file per deployable
artifacts/             ALL runtime output — gitignored
tests/                 contract tests; manual/ holds non-unittest smoke scripts
notebooks/             analysis notebooks, committed with outputs cleared; figures → artifacts/figures/
docs/                  see docs/README.md
data/                  the dataset — gitignored, bind-mounted into containers
```

The `src/memsoc/` subpackages map one-to-one onto the four layers in `PROJECT_BRIEF.md` §4, and onto the directories in `docs/`. Keep that correspondence.

### Hard rules

- **All HTTP endpoints live in `src/memsoc/api/`.** Never define a route anywhere else. Adding an endpoint means editing a router there and updating the route table in `api/__init__.py`. The two ASGI apps stay separate on separate ports — the detection app loads the model pickles, the report app holds the LLM credentials. Do not merge them.
- **All paths come from `src/memsoc/paths.py`.** Never hardcode a path, never re-derive one from `__file__`, never read `MEMSOC_*` environment variables directly outside `paths.py`. If you need a new location, add it there.
- **All runtime output goes to `artifacts/`.** Nothing writes into the source tree.
- **Every published port is declared once**, in `deploy/docker-compose.yml`, and overridable from `.env`. A port must never be hardcoded in application code, in a Dockerfile, or in the dashboard bundle. Two things that must agree on a port take it from the same variable.
- **Anything that runs in the browser needs a host-facing URL** (`localhost:<published port>`), never a Docker-internal hostname. Anything that runs inside the network uses the service name. Do not confuse the two.
- **Every image builds from the repository root** against `src/`, with `PYTHONPATH=/app/src`. Do not add a per-service copy of the code to make a build context smaller.
- **`deploy/` contains no application code.** If a Dockerfile needs a script, the script belongs in `src/memsoc/` and is invoked as `python -m memsoc.<module>`.

---

## Scope Discipline

- Work on **one feature or phase at a time**. Do not begin the next phase because the current one looks finished.
- Touch **only the files required by the current task**. Do not refactor, rename, reformat, or "clean up" adjacent code you were not asked to change.
- If a task requires modifying a file outside the stated scope, **stop and say so** before editing it. Name the file and the reason.
- If you discover a genuine dependency that blocks the current task, you may follow it — but state explicitly that you are crossing scope, name the dependency, and keep the diversion minimal.
- Do not add features, abstractions, config options, or error handling that were not requested. Speculative generality is a defect in this repo.
- Do not create new files when an existing one is the right home. Do not split a module into many files without being asked.

---

## Protected Components — Do Not Modify Without Explicit Approval

These are frozen by experimental design. Changing any of them silently invalidates the research.

| Component | Rule |
|---|---|
| Detection model weights & thresholds | Frozen after training. Never retune, never per-arm. |
| Embedding model | Never swap or change versions. Same model on write and read paths, always. |
| Base prompt template | Identical across both arms. No per-arm wording. |
| Alert stream order & seeds | Deterministic and reproducible. Never reshuffle, resample, or reseed. |
| Evaluation harness & metric definitions | Do not edit while implementing features. Do not adjust metrics after seeing results. |
| Stored vector DB / case store | Never delete, wipe, or regenerate without explicit instruction. |

If a task appears to require changing one of these, that is a signal to **ask, not proceed**.

`SEED = 42` in `src/memsoc/logstream/nfv3_log_generator.py` is frozen. `SAMPLE_SIZE` is overridable via `MEMSOC_SAMPLE_SIZE` because the controller sets it per run — the seed is not, so a given sample size always yields the same sequence. Do not make the seed configurable.

---

## Experimental Integrity

- **Arm B is Arm A plus a toggleable memory module.** Never implement the two arms as parallel codepaths.
- Shared by construction: prompt template object, LLM call wrapper, logging, scoring harness, data loader.
- The **only** permitted divergence: the retrieval-and-inject step and the write-back step.
- If you find yourself writing an `if arm == "baseline"` branch anywhere outside the memory module, stop — the design is wrong. Raise it.
- The baseline arm must **never** write to the memory store. Verify this before any baseline run.
- Do not tune parameters, thresholds, or prompts to improve Arm B's results. A null or negative result is a valid outcome and must be reported as-is.
- Any change affecting both arms must be applied to both in the same commit.

---

## When Requirements Are Unclear

- **Surface ambiguity; do not resolve it silently.** Guessing on a settled-looking question is worse than pausing.
- Flag any instruction that conflicts with `PROJECT_BRIEF.md`, and name the conflict.
- The ground-truth handling question in `PROJECT_BRIEF.md` §5 is **open** (backlog **BL-001**). Do not implement either interpretation without confirmation.
- If a requested change would compromise experimental control, say so before implementing — even if asked directly.
- Never invent dataset fields, metric definitions, or schema entries. If something is undefined, ask.
- When you flag an ambiguity, **also add a backlog row for it.** A flag in a chat message disappears; a backlog row does not.

---

## Code & Repo Rules

- No new dependencies without stating what, why, and the lighter alternative you rejected. Prefer the standard library.
- Add a dependency to the **one** `requirements/*.txt` for the deployable that needs it, not to all of them. `requirements/research-lock.txt` is a historical record of the training environment — never edit it, never install from it.
- Persistent/on-disk mode for the vector store, always. Never in-memory.
- Every run must be reproducible: fixed seeds, logged config, recorded model versions.
- Log enough per decision to reconstruct it later — alert ID, retrieved case IDs, similarity scores, verdict, rationale.
- Do not commit data files, model weights other than the two frozen pickles already in `models/`, `.env` files, API keys, or the vector store directory.
- Do not commit anything under `artifacts/`. It is generated output and is gitignored.
- Do not run destructive commands (`rm -rf`, force-push, history rewrite, DB drops) without explicit instruction.
- Do not modify `.gitignore`, `.dockerignore`, CI config, or dependency lockfiles as a side effect of a feature task.
- Match the surrounding code's style. This repo uses generous vertical spacing and explicit names; do not reformat existing code to a different style while editing it.

---

## Docs Rules

- Documentation lives in `docs/`. The index is `docs/README.md`; update it when you add or move a file.
- **Naming is lower-kebab-case** for directories and files. Numbered prefixes (`01-`, `02-`…) only where a reading order genuinely exists. `README.md` is the index of its own directory. The only shouty filename is `PRODUCT_BACKLOG.md`.
- `docs/` subdirectories mirror the packages under `src/memsoc/`. Keep them aligned.
- If you move or rename code, **fix the references to it in `docs/`** in the same change. If you cannot fix them all, file a backlog row naming what is left.
- Superseded documents go to `docs/archive/` with a banner saying what replaced them, plus a row in `docs/archive/README.md`. Do not silently delete a doc, and do not leave a stale one where it will be mistaken for current.
- Do not mark checkboxes in `README.md` on your own initiative.

---

## Verification

Do not report something as working because it compiles or imports.

- Changed a route, a Dockerfile, or compose? Rebuild and bring the stack up, then hit the endpoints.
- Changed the pipeline? Run the contract tests: `docker compose -f deploy/docker-compose.yml --profile tools run --rm tests`. 13 tests, and the live tier needs `detection` running or it skips.
- Changed paths? `docker compose -f deploy/docker-compose.yml --profile tools run --rm paths` shows what resolved and what is missing.
- Changed the dashboard? Load it in a browser and check the console. A 200 from nginx says nothing about whether the app rendered.
- **Anything that destroys a generated artifact — regenerating flows, `live_capture --reset`, report retention — back it up first.** `artifacts/generated_logs.jsonl` and `artifacts/ground_truth.csv` are a matched pair; the generator overwrites both (backlog **BL-022**).

State plainly what you ran and what the result was. If you did not verify something, say so rather than implying you did.

---

## Working Method

1. Restate the task and its scope boundary before starting.
2. State which files you will touch. Wait if the list exceeds the obvious scope.
3. Implement the minimum that satisfies the task.
4. Verify it (see above).
5. **Update `docs/PRODUCT_BACKLOG.md`** — close what you finished, open rows for what you found and did not do.
6. Report what changed, what you deliberately left alone, and any open question you hit.

- Do not report a phase complete until its evaluation criteria in `PROJECT_BRIEF.md` §7 are met.
- If something is broken but out of scope, report it — do not fix it. "Report it" means **file a backlog row**, not just mention it.
- Prefer asking one precise question over making three assumptions.
