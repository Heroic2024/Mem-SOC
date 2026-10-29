# Protocol v4: work split for three people

**Goal:** finish the approved supplementary experiments on Gemma 4 26B.
**Time:** about **8–11 hours of work per person**, everyone under 12 hours. **About 2 working days** in all.
Gemma runs are unattended (left running overnight) and are not counted in anyone's hours.

---

## Person 1: memory conditions and setup (8–11 h)

| Task | Hours |
|---|---|
| Set up protocol v4: new code tag, new run IDs, startup checks, hash recording. **Do this first; everyone builds on it.** | 2–3 |
| Build shuffled-label memory: same retrieved cases, each label replaced by a true label sampled from stored cases (seed from the alert ID), every replacement logged | 3–4 |
| Checks before the runs: contract tests, a one-alert dry run of each new condition, confirm Arm A writes no memory | 1.5–2 |
| Run shuffled-label overnight (165 calls) | unattended |
| Write the shuffled-label results section | 1–1.5 |
| Coordination and code review | 0.5 |

## Person 2: benign test (7.5–11 h)

| Task | Hours |
|---|---|
| Select the 100 hard-benign flows: held-out rows only, top 100 by detector score, remove near-duplicates, record the rule, hash the list. **Commit the hash before any benign run.** | 4–6.5 |
| Build the attack-primed mixed stream: copy the B-self memory, check its case count and hash; run B-self (with write-back) and Arm A on the same 100 flows | 2–2.5 |
| Run the benign flows (200 calls) | unattended |
| Write the benign results section (false-escalation rate) | 1–1.5 |
| Coordination and code review | 0.5 |
| *Optional, only if time is left: 50 random benign flows as a second set (about 2.5 h)* | — |

## Person 3: note, label-free memory, baselines (8–11 h)

| Task | Hours |
|---|---|
| Write and commit the pre-registration note: definitions, hypotheses, metrics, a promise to report all results. **Commit before the first run.** | 1–1.5 |
| Build label-free memory: B-self without the attack family; prompt and schema unchanged | 2–3 |
| Set up the reversed-order run: exact reverse of the 165 alerts, B-self only | 1 |
| Run label-free and reversed order overnight (330 calls) | unattended |
| Recompute the nearest-neighbour baseline on the same 165 alerts | 1–2 |
| Combine everyone's sections into one write-up; update the backlog and docs | 2.5–3 |
| Coordination and code review | 0.5 |

---

## Order

1. **Person 1** finishes the v4 setup. **Person 3** commits the pre-registration note.
2. Everyone builds their parts at the same time.
3. **Day 1 overnight:** shuffled-label, label-free and reversed-order runs.
4. **Day 2:** Person 2 commits the benign-list hash, then runs the benign flows.
5. When all runs are done: everyone writes their section, and Person 3 combines them.

## Rules

- Each person runs on **their own API key**, with the same environment checks passing.
- Do not touch the original (p3) results. All new results are labelled **supplementary**.
- The detector, prompt, embedding model and seeds stay unchanged.
- All results are reported, whether or not they are favourable.
- **If time runs short:** drop the reversed order first, then the random benign set.

## Known risk

The full dataset and the held-out index aren't on our machines yet. Person 2 should check this **first**. If the held-out split can't be recovered, tell the team straight away: the benign test is blocked until we decide what to do.
