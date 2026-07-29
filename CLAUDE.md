# CLAUDE.md — Agent Operating Instructions

Design context lives in `PROJECT_BRIEF.md`. Read it once at session start. **This file is the rules.**

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
- The ground-truth handling question in `PROJECT_BRIEF.md` §5 is **open**. Do not implement either interpretation without confirmation.
- If a requested change would compromise experimental control, say so before implementing — even if asked directly.
- Never invent dataset fields, metric definitions, or schema entries. If something is undefined, ask.

---

## Code & Repo Rules

- No new dependencies without stating what, why, and the lighter alternative you rejected. Prefer the standard library.
- Persistent/on-disk mode for the vector store, always. Never in-memory.
- Every run must be reproducible: fixed seeds, logged config, recorded model versions.
- Log enough per decision to reconstruct it later — alert ID, retrieved case IDs, similarity scores, verdict, rationale.
- Do not commit data files, model weights, `.env` files, API keys, or the vector store directory.
- Do not run destructive commands (`rm -rf`, force-push, history rewrite, DB drops) without explicit instruction.
- Do not modify `.gitignore`, CI config, or dependency lockfiles as a side effect of a feature task.

---

## Working Method

1. Restate the task and its scope boundary before starting.
2. State which files you will touch. Wait if the list exceeds the obvious scope.
3. Implement the minimum that satisfies the task.
4. Report what changed, what you deliberately left alone, and any open question you hit.

- Do not report a phase complete until its evaluation criteria in `PROJECT_BRIEF.md` §7 are met.
- Do not mark checkboxes in `README.md` on your own initiative.
- If something is broken but out of scope, report it — do not fix it.
- Prefer asking one precise question over making three assumptions.