# Protocol v4: execution plan

> **Status as of 2026-10-29:** Person 1's code is done and pushed (`cd0be63`). The Gemma p3 results are received and verified (`3440251`, BL-171). Everything below is what remains, in order.
> **Branch:** `protocol-v4`. Who does what and how long it takes: [`protocol-v4-work-split.md`](./protocol-v4-work-split.md), [`protocol-v4-time-estimate.md`](./protocol-v4-time-estimate.md).

The frozen p3 results stay the main experiment. Every v4 run is **supplementary**.

---

## Already done

| What | Where |
|---|---|
| Shuffled-label memory (`"shuffled"` condition) | `src/memsoc/memory/store.py` |
| v4 runner: own tag, `-p4` run ids, pre-registration gate, `--dry-run` | `src/memsoc/triage/protocol_v4.py` |
| Tests: 88/88 memory, triage and scoring tests pass | `tests/test_memory.py`, `tests/test_triage_memory.py` |
| Preflight and a 2-call dry run against real data and the Gemini API: PASS | `bshuf-gemma4-26b-p4-dryrun` |
| Gemma p3 results verified: 23/23 checksums, 165 verdicts per arm, scores match the write-up | `artifacts/shared/memsoc-p3-gemma4-26b-results/` |

---

## Step 1: start now, in parallel

| Who | Task | Done when |
|---|---|---|
| **Aadit → supervisor** | Ask: may label-free memory edit `triage_prompt.py` (**BL-170**)? Is a family-only shuffle intended (**BL-172**)? | Both answers written down |
| **Person 2** | Put the full NF-v3 dataset in `data/`; run `python -m memsoc.detection.training.heldout_split` | It writes `artifacts/heldout_rows.npy`. **If it fails, tell the team at once:** the benign test is blocked |
| **Person 2** | Fix the benign selection rule: ranking, seed, near-duplicate method | Sent to Person 3 |
| **Person 3** | Start the pre-registration note | Draft shared |
| **Person 3** | Recompute the nearest-neighbour baseline (3-neighbour vote, text-embedding retrieval, earlier alerts only, true labels, same 165 alerts) | One table |

## Step 2: build

| Who | Task | Done when |
|---|---|---|
| **Person 3** | Finish the note: definitions, hypotheses (what result supports or contradicts each), metrics, the benign rule, a promise to report all results | **Committed** at `docs/status/protocol-v4-preregistration.md` (the runner checks this exact path) |
| **Person 3** | Label-free memory: a new condition in `src/memsoc/memory/`, plus the `triage_prompt.py` change **only if approved** | Tests pass; Arm A prompt unchanged |
| **Person 3** | Reversed order: exact reverse of the 165 alerts, B-self, fresh store | Reversed-order hash recorded |
| **Person 2** | Pick the 100 hard-benign flows; build them into alerts | List hash **committed** before any benign run |
| **Person 2** | Mixed stream: copy the p3 B-self store to a new v4 run id, check 165 cases and the hash (`chroma.sqlite3` = `fd5ba38c3143d7918d4685aba762b1b1fccee070c0ea4386b3ebe67c1de31d55`); Arm A on the same 100 flows | The runner logs count and hash |

**Rule for all new code:** add each experiment to `EXPERIMENTS` in `protocol_v4.py`. Each memory condition goes inside `src/memsoc/memory/`, never as an `if arm == ...` branch elsewhere.

## Step 3: checks (Person 1)

1. Merge everyone's work into `protocol-v4`.
2. Run the tests in the pinned venv.
3. Run `--preflight --dry-run` and `--dry-run` for **every** experiment, then `--verify --dry-run`.
4. Confirm Arm A writes no memory, and the Arm A prompt hash is unchanged.
5. Create and push the tag: `git tag memsoc-protocol-v4 && git push origin memsoc-protocol-v4`.

## Step 4: the runs

Run each from the tag, each person on **their own** Gemini key.

| Run | Calls | Who | When |
|---|---|---|---|
| Shuffled-label | 165 | Person 1 | Overnight |
| Label-free | 165 | Person 3 | Overnight |
| Reversed order (B-self) | 165 | Person 3 | Overnight, after label-free or on a second key |
| Benign: Arm A + B-self | 200 | Person 2 | Next day |
| *Optional: 50 random benign* | 100 | Person 2 | Only if time is left |

**If time runs short:** drop the reversed order first, then the random benign set.

## Step 5: finish

| Who | Task |
|---|---|
| Everyone | `--verify` on their runs; write their results section |
| Person 1 | Shuffled-label vs B-oracle, B-self, Arm A |
| Person 2 | False-escalation rate on benign flows, Arm A vs B-self ("hard-benign", "attack-primed memory") |
| Person 3 | Label-free and reversed order; the nearest-neighbour baseline row; combine everything into one supplementary doc |
| Everyone | Report every result against the pre-registered hypotheses, **including unfavourable ones**; update the backlog (BL-159 and others); commit and push |

---

## How to run

```powershell
# One-time: the pinned environment (docs/status/testing-protocol-v3.md §3.3)
py -3.13 -m venv "$env:USERPROFILE\.venvs\memsoc-memory-p4"
& "$env:USERPROFILE\.venvs\memsoc-memory-p4\Scripts\python.exe" -m pip install -r requirements\memory.txt -c requirements\memory-protocol-v1-constraints.txt

# Each time
$py = "$env:USERPROFILE\.venvs\memsoc-memory-p4\Scripts\python.exe"
$env:PYTHONPATH = "src"
& $py -m memsoc.triage.protocol_v4 --experiment shuffled --preflight
& $py -m memsoc.triage.protocol_v4 --experiment shuffled            # start or resume
& $py -m memsoc.triage.protocol_v4 --experiment shuffled --status
& $py -m memsoc.triage.protocol_v4 --experiment shuffled --verify
```

Put the key in `.env` as `GEMINI_API_KEY=...`. Don't install into, or upgrade, the pinned venv.

## Stopping and resuming

Press **Ctrl-C** at any time. Every verdict already written is kept. Run the **same command** again and it continues from the next alert, with no repeated API calls.

## Run safely

- Only one runner process per experiment. Don't use a restart wrapper.
- Don't use the same API key for anything else during a run.
- Never write into `artifacts/shared/memsoc-p3-gemma4-26b-results/`. It is the reference copy.
- Back up `artifacts/generated_logs.jsonl` and `artifacts/ground_truth.csv` before anything that could regenerate them. They are a matched pair (BL-022).
- Never commit anything under `artifacts/`.

## Open items

| Backlog | What | Owner |
|---|---|---|
| BL-170 | Approval for the label-free edit to `triage_prompt.py` | Supervisor |
| BL-172 | Confirm the family-only shuffle | Supervisor |
| BL-173 | The old `memsoc-memory` venv is off-pin; use `memsoc-memory-p4` | Info |
| BL-159 | Control arms: in progress, closes when the v4 runs are reported | All |
