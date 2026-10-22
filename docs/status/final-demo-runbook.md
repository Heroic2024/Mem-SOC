# Final Demonstration — Runbook

> **Format:** live system demo to an academic panel, 15–20 minutes, on this laptop with internet.
> **Result being presented:** [`gemma-p3-results.md`](./gemma-p3-results.md) — 165 alerts × 3 arms,
> Gemma 4 26B, commit `d08233c`, tag `memsoc-protocol-v3`.
> **Status of this document:** written 2026-10-21. Two blockers in §1 are **not yet cleared** —
> the demo cannot be given until they are.

---

## 0. The one-paragraph version

Three Docker services are already running. Detection is live and answers in under a
second. The dashboard is the reporting layer and shows both the technical and the
non-technical view. The memory layer is the research variable; it has no UI, so it is
shown from the terminal and from the run artifacts. The results are four committed
figures. The integrity of the experiment is proved on stage by a command that makes no
API calls. One live LLM verdict is called during beat 4 — everything else is offline.

---

## 1. Blockers — clear these before the demo

### B1 + B2 — the dashboard is empty, and the thing that fills it is broken

`artifacts/reports/` does not exist. `GET http://localhost:8001/api/reports` returns
`{"reports":[],"retention_limit":10}`, so `http://localhost:8080/` renders
"No reports found yet" instead of the charts.

The fix is to generate a report, but `src/memsoc/triage/generate_report.py:364` calls
`llm_client.call_groq()` and `:252` hard-fails without a working key. The key in `.env`
returns **HTTP 401** (confirmed 2026-10-21; this is backlog **BL-120**).

**Do this:**

1. Get a new free Groq key.
2. Replace `GROQ_API_KEY` in `.env`. That file only — never `.env.developer`, never
   committed, and do not touch `.gitignore`.
3. Restart the report service so it picks up the new environment:

   ```powershell
   docker compose -f .\deploy\docker-compose.yml restart report
   ```

4. Generate two reports from the capture already on disk. **No new capture.**

   ```powershell
   docker exec memsoc-report python -m memsoc.triage.generate_report
   docker exec memsoc-report python -m memsoc.triage.generate_report
   ```

   Two, because the dashboard's Trends tab needs at least two reports to render.

5. Confirm:

   ```powershell
   Invoke-RestMethod http://localhost:8001/api/reports
   ```

   It must come back non-empty. **This is the gate.** If it is still empty, the demo
   loses beat 3b.

If no Groq key can be obtained, the alternative is to add a Gemini branch to the report
path — `llm_client.call_gemini` and the `call_triage_llm` switch already exist, so it is
a small change. It is still a code change to Layer 4 and should be raised before it is
made. It does **not** touch a protected component: the frozen prompt is the *triage*
prompt shared by both arms, not `report_prompt.py`.

### B3 — a live Arm B call must not touch the p3 artifacts

The obvious command would be
`triage_runner --memory self --run-id bself-gemma4-26b-p3 --limit 1`.

**Do not run it.** It appends a 166th verdict row and a 166th case to the Chroma store.
`protocol_run --verify` asserts exactly 165 per arm, so it would flip **PASS → FAIL**,
and the packaged results zip would stop matching.

A fresh `--run-id` avoids the contamination but opens an *empty* store, so the model
retrieves nothing and the beat demonstrates nothing.

**Do this instead — demo against a copy.** Before the demo:

```powershell
Copy-Item -Recurse .\artifacts\runs\bself-gemma4-26b-p3   .\artifacts\runs\demo-bself
Copy-Item -Recurse .\artifacts\memory\bself-gemma4-26b-p3 .\artifacts\memory\demo-bself
```

The copy carries all 165 cases, so retrieval returns three real precedents. The case IDs
inside still read `bself-gemma4-26b-p3:…` — cosmetic, and worth mentioning only if
someone asks.

Afterwards, re-run `--verify` (§6, beat 6) to prove the originals are untouched.

---

## 2. Never do these on stage

1. **Never run the controller** —
   `docker compose -f deploy/docker-compose.yml --profile workflow run --rm controller`.
   It regenerates flows, which truncates `artifacts/generated_logs.jsonl` (172 MB) and
   `artifacts/ground_truth.csv` — they are opened in mode `"w"` (backlog **BL-022**) —
   and then runs `live_capture --reset`, which deletes
   `artifacts/model_outputs/live_results.jsonl` (30 MB). All three currently hash-match
   the protocol bundle pinned in `protocol_run.DATA_SHA256`. Destroying them breaks
   `--preflight`, `--verify`, and the ability to reproduce or extend any run.
2. **Never run `live_capture.py --reset`**, for the same reason.
3. **Never write to any `*-p3` run or memory store.** Use the `demo-*` copies.
4. **Never open `http://localhost:8080/services/detection/docs`.** Neither app sets
   `root_path`, so that Swagger shell loads empty and looks broken. Use
   `http://localhost:8080/api-docs/` (trailing slash) or `http://localhost:8000/docs`.
5. **Never trigger a live Arm A verdict.** Median 39 s, tail 171 s. Arm A is shown with
   `--dry-run`, which makes no API call at all.

---

## 3. Morning-of preflight

Run this list about an hour before, not five minutes before. Tick every line.

| # | Check | Command / URL | Expected |
|---|---|---|---|
| 1 | Docker up | `docker compose -f .\deploy\docker-compose.yml ps` | detection, report, dashboard all `Up` |
| 2 | Detection alive | `Invoke-RestMethod http://localhost:8000/health` | `healthy` |
| 3 | Report alive | `Invoke-RestMethod http://localhost:8001/health` | `ok` |
| 4 | **Reports exist** | `Invoke-RestMethod http://localhost:8001/api/reports` | **non-empty** |
| 5 | Dashboard renders | `http://localhost:8080/` in the browser | charts, not the empty state; console clean |
| 6 | Swagger renders | `http://localhost:8080/api-docs/` | two tag groups, `detection` and `reports` |
| 7 | Demo copies exist | `ls .\artifacts\runs\demo-bself, .\artifacts\memory\demo-bself` | both present |
| 8 | Gemini key live | see §4 beat 4 env block, then `--dry-run` | prompt prints, no error |
| 9 | Integrity passes | `--verify` (beat 6) | all `PASS` |
| 10 | Payload ready | the NetFlow record for beat 3a is in the clipboard or a scratch file | — |

**Pre-warm before you walk on.** `triage_runner` spends 20–30 s loading 172 MB of flows
before it makes any API call, plus 5–10 s loading torch and MiniLM on a memory arm. Run
the `--dry-run` once beforehand so the OS file cache is warm.

Also open every tab you will use, in order, ahead of time. Do not type URLs on stage.

---

## 4. The demo — 17 minutes, six beats

17 minutes leaves slack in a 20-minute slot. If the slot is 15, cut beat 3b.

| # | Beat | Min | Mode |
|---|---|---:|---|
| 1 | The problem and the research question | 2 | slide |
| 2 | Architecture — the four layers | 2 | slide |
| 3a | Detection, live: one flow → verdict + SHAP | 2 | live, sub-second |
| 3b | Reporting, live: the dashboard | 3 | live |
| 4 | The research variable: one script, two arms | 4 | live LLM, one call |
| 5 | Results: the three findings | 4 | figures |
| 6 | Integrity, then limits | 2 | live, offline |

---

### Beat 1 — the problem (2 min, slide)

SOC analysts re-investigate alerts that have already been resolved, because the
institutional knowledge lives in individual analysts' heads. When someone rotates off
shift or leaves, it goes with them.

The research question is deliberately narrow: **what does a memory layer contribute when
bolted onto LLM-based alert triage?** Not a better detector, not a novel retrieval
algorithm. Everything else in the system exists to make the memory layer measurable.

---

### Beat 2 — architecture (2 min, slide)

Four layers:

```
[1] DATA STREAM  →  [2] DETECTION (ML)  →  [3] MEMORY (Vector DB)  →  [4] LLM TRIAGE + REPORTING
                                                    ↑______________________________|
                                                          (write-back loop)
```

1. **Data stream** — NF-UNSW-NB15-v3 replayed deterministically, seed 42.
2. **Detection** — a frozen LightGBM multiclass classifier with SHAP. Never retuned,
   identical in all three arms.
3. **Memory** — ChromaDB, persistent on disk, MiniLM embeddings, **top-3, no similarity
   cut-off, every verdict stored**. This is the research variable.
4. **Triage and reporting** — one fixed LLM, one fixed prompt, producing a verdict and
   an explainable report in a technical and a non-technical view.

> **Draw this slide fresh.** Do not reuse anything from `docs/design-assets/`. Those
> figures still carry pre-restructure component names (backlog **BL-061**), and
> `fig13_memory_layer_architecture.png` in particular shows a similarity threshold, a
> diversity filter and a `WritePolicy` — **none of which the system as run uses.** Showing
> it would misdescribe the system to the panel.

---

### Beat 3a — detection is real (2 min, live)

Open **`http://localhost:8080/api-docs/`** — note the trailing slash; `/api-docs` 301s.

One Swagger page covers both services, which is worth a sentence: the dashboard
container is also the gateway, so a single origin fronts both APIs.

Expand `detection → POST /services/detection/api/logs`, click **Try it out**, paste the
prepared NetFlow record, **Execute**.

What comes back:

- binary verdict (Attack / Benign) with confidence,
- the attack family with confidence,
- **the top-10 SHAP feature contributions**,
- the alert object that flows on to the next layer.

Sub-second, no API cost, no mutation.

**Prepare the record in advance** from `artifacts/generated_logs.jsonl`. Pick one the
detector classifies correctly and whose SHAP output is interesting. Do not go looking
for a good example on stage.

---

### Beat 3b — the reporting layer, both audiences (3 min, live)

Open **`http://localhost:8080/`**.

Walk it in this order:

1. **Sidebar** — pick the newest report.
2. **KPI row** — total flows, attacks detected, attack rate, overall risk level.
3. **Overview tab** — the LLM executive summary and risk analysis. *This is the
   non-technical view.*
4. **Technical Findings tab** — category chart and table, frequency-vs-risk scatter,
   confidence distribution, protocol distribution, top targeted ports, top SHAP
   indicators, ranked findings table. *This is the technical view.*
5. **Recommendations tab** — prioritised action plan.
6. **Trends tab** — only if two or more reports exist.

Say explicitly that this is the **dual-audience output** the project committed to in
`PROJECT_BRIEF.md` §10. It is a deliverable being demonstrated, not a nice-to-have.

---

### Beat 4 — the controlled comparison, live (4 min)

This is the strongest beat, because it *shows* the experimental control rather than
asserting it.

**The point to make first.** `src/memsoc/triage/triage_runner.py` is **one script for
both arms**. `--memory off` is Arm A; `--memory self` is Arm B. Under `off`, retrieval
and write-back are no-ops inside `NullMemoryLayer` — they are not `if arm == …`
branches. Put the two commands side by side and say: this is why no measured difference
between the arms can be an implementation artefact.

Set up the shell **before** you go on:

```powershell
cd $env:USERPROFILE\Mem-SOC
$env:PYTHONPATH      = "src"
$env:TRIAGE_PROVIDER = "gemini"
$env:TRIAGE_MODEL    = "gemma-4-26b-a4b-it"
$env:GEMINI_API_KEY  = "<paste from .env>"   # triage_runner does NOT read .env itself
$py = "$env:USERPROFILE\.venvs\memsoc-memory\Scripts\python.exe"
```

The memory layer is **not in any container** — `sentence-transformers` pulls torch,
which would let pip re-resolve numpy and scipy underneath the frozen detector. It runs
from the host venv at `C:\Users\Aryan Mhatre\.venvs\memsoc-memory`. Worth one sentence
if anyone asks why this beat is in a terminal.

**Arm A — no API call, no store opened:**

```powershell
& $py -m memsoc.triage.triage_runner --dry-run
```

Prints the exact Arm A prompt. Show that it contains the alert and nothing else.

**Arm B-self — one live verdict, against the copy:**

```powershell
& $py -m memsoc.triage.triage_runner --memory self --run-id demo-bself --limit 1
```

Expect roughly 22 s of model time on top of the startup cost. **Narrate the wait** —
what the prompt now contains, which three past cases were retrieved and why. The printed
line shows `precedent=3`, against `precedent=0` for Arm A.

**Then show what retrieval actually did**, from
`artifacts/memory/bself-gemma4-26b-p3/retrievals.jsonl`. Each line carries the candidate
case IDs, their distances and similarities, and the timings:

```json
{"uid":"…","collection_count":19,
 "candidates":[{"case_id":"bself-gemma4-26b-p3:000009","distance":0.1786,"similarity":0.8214}, …],
 "embed_ms":19.89,"query_ms":2.79,"total_retrieval_ms":22.68}
```

**~23 ms.** Retrieval is not the slow part — and that sets up the latency finding in
beat 5.

---

### Beat 5 — the results (4 min, figures)

Use the four committed figures in `docs/status-assets/` as they are. Regenerate only if
needed:

```powershell
python docs\status-assets\build_p3_figures.py
```

numpy and matplotlib only, about two seconds, no embedding model, no network.

**Finding 1 — memory halved the attacks that were missed.**
42 → 22 of 165. Recall 0.745 → 0.867. It fixed 21 alerts the baseline got wrong and
broke exactly one. Paired exact McNemar, **p = 1.1 × 10⁻⁵**. The gap opens around the
20th alert and keeps widening, so it is not a lucky patch at the end.
*(figure `p3-01-attacks-missed.png`, `p3-02-misses-over-time.png`)*

**Finding 2 — and it made the attack labels much worse.**
Family accuracy 54.5% → 23.6%. Fifty-six alerts the baseline labelled correctly went
wrong once the model could see its own past answers, against five fixed.
**p = 5.7 × 10⁻¹².**
*(figure `p3-03-catching-vs-naming.png`)*

**Finding 3 — the mechanism, with its own control.**
On the 17 groups of near-identical alerts, B-self gave one consistent answer **17 times
out of 17** — perfect consistency — *while* its accuracy collapsed. That is the
mechanism in one number: **memory does not make the model think harder, it makes the
model agree with itself.** Whatever family it assigned first gets retrieved and repeated.
Right first guess → free accuracy. Wrong first guess → the error is copied forward
indefinitely.

B-oracle is the control that proves it. Same retrieval, same prompt, same model — only
the stored labels are correct — and accuracy recovers to 69.1%. **Memory is not the
problem. Unchecked memory is.**
*(figure `p3-04-consistency.png`)*

**Secondary, and unexpected:** latency fell from 40.4 s to 21.5 s per alert. Retrieval
normally costs time; here it halved it, because a relevant past case gives the model a
starting point instead of reasoning from scratch.

**The framing to land.** Error propagation through self-memory is named in
`PROJECT_BRIEF.md` §8 as the single most important failure mode of this design. It was
predicted up front, then measured, then causally isolated by the oracle contrast. It is
a finding to report, not a bug to tune away — and per `CLAUDE.md` the prompt must not be
adjusted to make it disappear. A null or negative result is a valid outcome.

---

### Beat 6 — integrity, then limits (2 min)

**Prove the experiment, live.** No API calls, fully offline:

```powershell
& $py -m memsoc.triage.protocol_run --model gemma-4-26b --verify
```

It prints every integrity check as `PASS` — including *"Arm A retrieved nothing"*,
*"Arm A created no memory store"*, and *"retrieval matches the reference machine
(0 of 165 alerts differ)"* — then three score reports produced by the unchanged
`memsoc.triage.score_verdicts`. One to two minutes, most of it hashing.

This is also the check that proves the beat-4 demo copy left the protocol artifacts
intact.

**Then state the limits yourself, before the panel finds them.**

1. **There is no benign traffic in the stream.** Every alert that reaches the LLM is a
   real attack, so false positives and true negatives are structurally zero and the
   `precision 1.000` in the raw output is an artefact. The project's original primary
   metric was false-positive volume — **this run cannot speak to it.** Any claim that
   memory reduces false alarms is unsupported. The honest headline is recall.
2. **No arm beat the frozen detector at naming families.** The best, B-oracle at 69.1%,
   is still 13 points below the detector's 82.4% on the same alerts.
3. **B-oracle is a declared ceiling**, fed the answer key. It exists to separate
   "retrieval found the right neighbours" from "the model used them well". It is never
   system performance.
4. **One model, one run, one ordering**, 165 of 1,135 alerts in stream order — not a
   random sample. The McNemar tests are paired and robust to that, but they test this
   ordering of these alerts.

---

## 5. Fallbacks

Capture these during rehearsal into `artifacts/demo-fallback/` (gitignored, as all of
`artifacts/` is). If a live beat stalls, switch to the capture — and say plainly that
that is what you are doing. Do not let it look live.

| Beat | Risk | Fallback |
|---|---|---|
| 3a | detection container restarting, browser cache | screenshot of the Swagger response with SHAP expanded |
| 3b | no report generated (B1/B2 unresolved) | screenshots of all four dashboard tabs |
| 4 | API stall, quota, slow verdict, network | recorded terminal output of both commands, plus the `retrievals.jsonl` excerpt |
| 6 | nothing realistic — it is offline | recorded `--verify` output |

Quota is not a realistic risk: the Gemma free tier is 14,400 requests/day and the
counter was last touched on 2026-10-17. Wall-clock latency is the real risk.

---

## 6. Questions the panel will probably ask

**"How do you know the difference is the memory layer and not the code?"**
One script runs both arms. `--memory off` returns a `NullMemoryLayer` whose `retrieve`
returns `[]` and whose `write` does nothing — the same call sites, not a parallel
codepath. `--verify` asserts that Arm A retrieved nothing and created no store, and that
retrieval on the memory arms matches a reference machine on all 165 alerts.

**"Why is precision exactly 1.000?"**
Because the evaluation population contains only detector-flagged flows, and in this
dataset all of them are real attacks. With no benign traffic present, a false positive
is not expressible. It is an artefact, not a result — which is why recall is the
headline and false-positive volume is explicitly not claimed. Tracked as **BL-016**.

**"Isn't B-oracle cheating?"**
Yes, deliberately. It is fed ground truth and is reported as a ceiling, never as system
performance. Its only job is to separate two explanations for B-self's label collapse:
bad retrieval, or good retrieval with bad stored content. Same retrieval, correct labels,
accuracy recovers — so it is the content.

**"Why only 165 alerts, and only one run?"**
Free-tier limits. The full run took 5 h 18 m for 495 verdicts, and the three-arm design
triples every call. 165 is the first 165 in stream order, per protocol v3 §2 — never a
random sample, because the memory arms must run in stream order. Repeats are an
acknowledged gap, tracked as **BL-017**.

**"Could you fix the label regression?"**
Probably, and deliberately not. The data points at a specific follow-up: B-self's failure
is concentrated in the *label* it copies, not the *verdict*. Storing the verdict without
the family label might keep the recall gain and drop the label harm. That changes the
case schema, so it needs approval rather than initiative — and tuning the prompt until
the regression disappears would be exactly the kind of result-chasing the project's own
rules forbid.

**"What would you need to measure the thing you actually set out to measure?"**
Benign traffic in the stream. Until the evaluation population contains flows that are not
attacks, alert fatigue — the thing a real SOC cares about most — cannot be measured at
all.

---

## 7. Quick command reference

```powershell
# --- stack ---
docker compose -f .\deploy\docker-compose.yml ps
docker compose -f .\deploy\docker-compose.yml restart report
Invoke-RestMethod http://localhost:8000/health        # -> healthy
Invoke-RestMethod http://localhost:8001/health        # -> ok
Invoke-RestMethod http://localhost:8001/api/reports   # -> must be non-empty

# --- reports (needs a working GROQ_API_KEY) ---
docker exec memsoc-report python -m memsoc.triage.generate_report

# --- host venv ---
$env:PYTHONPATH      = "src"
$env:TRIAGE_PROVIDER = "gemini"
$env:TRIAGE_MODEL    = "gemma-4-26b-a4b-it"
$env:GEMINI_API_KEY  = "<paste from .env>"
$py = "$env:USERPROFILE\.venvs\memsoc-memory\Scripts\python.exe"

# --- the demo beats ---
& $py -m memsoc.triage.triage_runner --dry-run
& $py -m memsoc.triage.triage_runner --memory self --run-id demo-bself --limit 1
& $py -m memsoc.triage.protocol_run  --model gemma-4-26b --verify

# --- figures ---
python docs\status-assets\build_p3_figures.py
```

**URLs, in the order they are used:**

```
http://localhost:8080/api-docs/     Swagger, both services   (trailing slash)
http://localhost:8080/              the dashboard
http://localhost:8000/health        detection liveness
http://localhost:8001/health        report liveness
http://localhost:8001/api/reports   the report index
```

---

*Companion documents: [`gemma-p3-results.md`](./gemma-p3-results.md) for the result being
presented, [`testing-protocol-v3.md`](./testing-protocol-v3.md) for how the run was
produced, and [`../deployment/operations.md`](../deployment/operations.md) for the
authoritative run guide.*
