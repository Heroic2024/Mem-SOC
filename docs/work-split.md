# Work split — three people, the memory layer and the experiment

**Written 2026-10-10. Paper due 2026-10-14.**

Who owns what, what each person can start right now, and the one interface
the three of us have to agree on before anybody writes code.

Read [`decisions.md`](./decisions.md) first — this file says *who does it*,
not *what we decided*.

---

## The rule this file exists to protect

**Split the work by layer. Never by experimental condition.**

We considered giving each person one memory variant to build — one stores the
LLM's verdicts, one stores a mix, one stores the true labels. It is the wrong
shape, for three reasons, and the first is fatal.

**1. Three people building three memory layers gives three codepaths, and three
codepaths destroy the comparison.** The whole credibility of this project is
the claim that *the only difference between conditions is the memory*. If each
variant is separately written, a difference in results could just as easily come
from a different case rendering, a different retrieval ordering, or a different
tokenizer call. There would be no way to attribute the result to memory at all.
[`../CLAUDE.md`](../CLAUDE.md) states the rule directly: *"Arm B is Arm A plus a
toggleable memory module. Never implement the two arms as parallel codepaths."*
[`decisions.md`](./decisions.md) A3 already said the same thing — *"one switch on
the memory module, not two separate sets of code"* — so this was settled before
the question came up again.

**2. It is three times the work for one module.** The variants differ in *what
goes into a stored case's metadata*. That is one function and a flag. Everything
else — the embedding, the store, the read path, the token check, the lifecycle —
is identical. Three people would each build the whole layer in order to vary
about twenty lines, and then have to reconcile three codebases in four days.

**3. Two of the three variants measure nearly the same thing.** A case holding
both the LLM's verdict and the true label will be read by the LLM as the true
label. So "a mix" collapses onto "the true labels" with extra text, and a third
of the effort and a third of the API budget would go on a near-duplicate.

**So: one module, one switch, and the conditions become runs.** Nobody is idle
as a result — there is more than enough non-memory work, and two of the three
roles below start with no dependencies at all.

---

## Owners

### Person 1 — the memory layer

**Owns `src/memsoc/memory/` alone. Nobody else edits that directory.**

This is the critical path and the research variable. It is serial work that
cannot be sped up by adding people, which is exactly why it gets a sole owner.

| Build | Notes |
|---|---|
| The embedding function | **One shared model instance for the write path and the read path.** A mismatch does not raise — retrieval just returns plausible nonsense forever. This is the single most dangerous line in the layer. |
| The write path | Per [`memory-layer/03-write-path.md`](./memory-layer/03-write-path.md). `schema_version` on every case (C10, BL-006). |
| The read path | Per [`memory-layer/04-read-path.md`](./memory-layer/04-read-path.md). top-k = 3, no similarity cut-off (C8). |
| The token check | Must use MiniLM's **real tokenizer** and **raise**. `case_ranker/token_estimator.py:30-41` is a heuristic — do not use it for this. See the warning below. |
| The memory-content switch | One switch, per A3 and BL-015. Never a second codepath. |
| Store lifecycle | `paths.memory_store(run_id)`, `PersistentClient` only, **cosine space set explicitly**. |

**Already done for you:** `requirements/memory.txt`, the isolated virtualenv
(BL-107 — read the requirements header, and do **not** install next to the
detector), `paths.MEMORY_STORE_DIR`, `paths.memory_store(run_id)`, and the store
location corrected across the docs.

**The environment is verified.** Model loads on CPU at 384 dimensions; the same
text embeds bit-identically twice; the collection really is cosine space,
asserted on the distances (self 0, opposite 2) rather than on the metadata
string — under Chroma's L2 default those would be 0 and 4 and nothing would have
errored.

> **Silent truncation, confirmed live on 2026-10-10.** MiniLM truncates at 256
> tokens without raising. A 1,321-token input returned a normal-looking 384-dim
> unit vector, and **two different over-long texts embedded to bit-identical
> vectors.** 179 of our 211 sandbox cases were in that state. Length-check with
> `model.tokenizer.encode()` and fail loudly. See **BL-013**.

### Person 2 — the experiment harness

**Owns `src/memsoc/triage/`. Consumes the memory module's two functions and
never touches its internals.**

**Can start immediately** — the seams already exist and are marked.

| Build | Notes |
|---|---|
| The arm / condition toggle | **Done** (`8816b7d`). `--memory off/self/oracle`; seam 1 `mem.retrieve` in `triage_alert()`, seam 2 `write_back()` after the verdict is logged. The hardcoded `"arm": "baseline"` is gone. |
| Run identity | **Done.** `--run-id` gives each run its own directory, so a fresh run is a new ID (3 runs per arm = 3 IDs); restarting the same ID still resumes. `run_id`, `seq` and `prompt_variant` (2026-10-16, BL-120) are on every record. Resuming an ID under a different memory condition, model or prompt variant is refused. |
| The `priority` field | **Blocked on BL-106 sign-off.** The prompt template is a protected component and is declared LOCKED at `triage_prompt.py:255-262`. Do not edit it before approval. When approved: applied to both arms in one commit, and versioned. |

**No `if arm == "baseline"` branch anywhere outside the memory module.** If you
find yourself writing one, the design is wrong — raise it.

**The baseline arm must perform zero writes to memory.** Assert it, do not
assume it.

### Person 3 — measurement and the paper

**Owns `src/memsoc/triage/score_verdicts.py` and `docs/research-paper/`.**

**Can start right now with zero dependencies** — the scorer is developed against
synthetic verdict files long before a real run exists.

| Build / write | Notes |
|---|---|
| Escalation precision + must-escalate recall | The new primary metric (B1). Both halves, always — a system that escalates nothing would otherwise score perfectly. |
| Wilson intervals on every proportion | `statistics.NormalDist().inv_cdf`. **No new dependency.** |
| Exact McNemar, paired on `uid` | `math.comb`. **No new dependency.** `scipy` and `statsmodels` are the rejected alternatives. |
| A real confusion matrix | There is only a flat `cat_errors` counter today at `:146,155`. |
| Agreement rate with the detector | Reported *alongside* accuracy, so the LLM merely echoing the detector's label is visible rather than hidden inside a good-looking score. |
| Declare the tier split | **BL-105.** Decides our headline number. Confirm or change it in writing. |
| Write Part C's answers down | **BL-108.** All ten still read `Status: open` though we agreed most of them. ~20 minutes, and it is the likeliest way three people build to different unwritten answers. |
| Paper sections | D1–D4. Results, Discussion, Limitations, Threats to validity, Conclusion. |

**Extend the scorer additively only.** The evaluation harness is a protected
component — no existing metric definition changes, and nothing is adjusted after
seeing results.

---

## The one interface to agree on, day one, in writing

Person 1 and Person 2 agree these two signatures before either writes code.
Everything else is independent.

**Agreed and built** (BL-110, reviewed by Person 2 on 2026-10-16). The
original sketch was `retrieve(alert)` / `write(alert, verdict)`; the real
interface carries what the sketch left out:

```python
mem = open_memory(run_id, condition)       # "off" | "self" | "oracle"

mem.retrieve(record, flow) -> list[Case]   # read path;  [] when "off"
mem.write(record, flow, verdict, seq, precedent_used) -> None
                                           # write path; no-op when "off"
```

- `record, flow` — triage already holds an alert as the detector's
  `live_results` record plus its joined flow.
- `seq` — the alert's position in the stream; the case ID is
  `{run_id}:{seq:06d}`.
- `precedent_used` — the case IDs `retrieve` returned for this alert, so a
  wrong verdict can be traced back to the precedent that caused it.
- `Case` carries `case_id`, `similarity`, `distance`, `document`, `metadata`.

**Call order** (`triage_runner.py`): `retrieve` before the prompt is built;
`write` only after the verdict is appended to the run's verdict file, and
replayed from that file on resume.

Get this wrong and the two of you block each other for a day. Get it right and
you never need to talk again until integration.

---

## Conditions are runs, not codebases

| Condition | Memory holds | Status |
|---|---|---|
| **Arm A** | nothing | Baseline. Required. |
| **Arm B-self** | the LLM's own past verdicts, right or wrong | **The headline. The deployable system.** |
| **Arm B-oracle** | the true labels | A declared **ceiling**, never the headline. Run only if budget allows. |

Running a condition is a config change, done by whoever has API budget when the
module lands. It is not a build task and it is not owned by anyone.

**Dropped: the "LLM verdict plus ground truth" mix.** A case containing both is
read as the true label, so it collapses onto Arm B-oracle. See A3.

**If you want a third variant, vary the write policy instead** — write every
case, versus only high-confidence ones. That tests **memory poisoning**, and we
already have evidence it is a live risk: BL-014 measured nearest-neighbour
retrieval as *worse than random* on exactly the alerts the detector got wrong,
carrying the wrong attack family 70.8% of the time. "Does memory poison itself
with its own mistakes?" is a real question with a real chance of a real answer,
and it is a stronger contribution than measuring the oracle twice.

**Both oracle conditions leak the answer key** — memory would let the LLM read
the correct family for a *similar past* alert, and this dataset has many
near-duplicate flows. Legitimate as a declared ceiling; never as the result. It
also breaks an invariant asserted in three docstrings
(`score_verdicts.py:4-9`, `triage/config.py:75-78`, `triage_runner.py:13-14`),
so it needs deliberate containment: read ground truth only inside the memory
module's `write()`, gated on the condition, and let the oracle label reach
precedent metadata only — never the embedding text, never the current alert's
prompt.

---

## What blocks what

```
Person 3  ──────────────────────────────────  nothing blocks this. start now.
Person 2  ──────────────────────────┐
                                    └── priority field waits on BL-106 sign-off
Person 1  ──────────────────────────────────  nothing blocks this. start now.

Scored runs ───────────────────────────────── wait on the rate limits (BL-098/099)
```

**Not blocked by anything:** the memory layer, the harness seams, the whole
scorer, the tier split, the Part C write-up, every paper section.

**Blocked:** the `priority` field (BL-106 sign-off), and *running* the scored
comparison (rate limits — read them off the provider dashboard, not the docs).

Note that no build task waits on the API budget. Everything in this file is
developed and tested offline against the 215 alerts that already exist.

---

## Rules that protect the experiment

Short list, all from [`../CLAUDE.md`](../CLAUDE.md). Breaking any one of them
silently invalidates the result rather than producing an error.

1. **Arm B is Arm A plus a toggle.** Never parallel codepaths.
2. **The baseline never writes to memory.** Verify before every baseline run.
3. **Same embedding model on the write and read paths, always.** Never swapped,
   never re-versioned.
4. **One prompt template, identical across arms.** No per-arm wording.
5. **Never reshuffle, resample, or reseed the stream.** `SEED = 42` is frozen.
6. **Never delete or regenerate the case store.** A fresh store is a *new
   directory*, never a cleared one.
7. **Do not tune anything to improve Arm B.** A null or negative result is a
   valid outcome and is reported as-is.

---

## If four days is not enough

Decide the order now, not at 3am on the 13th. Protect in this order:

1. **Keep:** a held-out detector measurement (done), Arm A vs Arm B-self, 3 runs
   each, the paired test, confidence intervals — on a reduced sample if needed.
   Cutting the sample is the right lever; cutting the arms or the runs is not.
2. **Drop first:** Arm B-oracle. It costs one research question, which should
   then be *removed* from the paper rather than left claimed and unmeasured.
3. **Drop second:** the benign-flow pass (B2). Costs the LLM false-positive rate,
   and the limitation has to be stated explicitly.

A null result on Arm B is a live possibility — see the BL-014 retrieval figure
above. Structure the paper so that outcome is still publishable.
