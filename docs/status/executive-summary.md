# MemSOC Executive Summary

## Introduction and problem statement

Security Operations Center (SOC) analysts often re-investigate alerts that have already been resolved, because that knowledge sits with individuals and leaves when they do. MemSOC tests whether giving an LLM triage system a persistent memory of past cases measurably changes its decisions, and if so, how and why. The contribution is the measurement of memory itself, not a new detector or retrieval method.

## Methodology

MemSOC is a controlled comparison. The alert stream, frozen LightGBM detector, LLM and base prompt are the same in every arm, so memory is the only variable.

- **Arm A:** no memory.
- **Arm B-self:** retrieves similar past cases and stores the model's own verdicts, as a live system would.
- **Arm B-oracle:** uses the same retrieval, but past cases carry correct labels. This shows the best case for memory.

Memory is a ChromaDB vector store of NetFlow-based alerts from NF-UNSW-NB15-v3. Gemma 4 26B and gpt-oss-20b were scored on the same 165 alerts, under protocols v3 and v1 respectively. Qwen 3.8 27B was scored on 250 alerts, comparing Arm A with Arm B-self only. Results were tested with McNemar paired tests and with a stricter cluster bootstrap that resamples 43 groups of near-duplicate alerts.

## Key findings and results

**Memory's effect depends on the model and on what is stored in it.**

| Measure | Gemma: A / B-self / B-oracle | gpt-oss-20b: A / B-self / B-oracle |
|---|---|---|
| Attacks caught (recall) | 74.5% / 86.7% / 98.8% | 40.2% / 26.1% / 87.3% |
| Attack family named correctly | 54.5% / 23.6% / 69.1% | 32.7% / 18.8% / 64.8% |
| Mean time per alert | 40.4 s / 21.5 s / 27.1 s | 3.0 s / 2.3 s / 2.6 s |

- **Gemma caught more attacks.** Missed attacks fell from 42 to 22, and the gain held under the stricter test (+5.7 to +22.2 points).
- **Gemma's naming got worse.** Family accuracy fell by 30.9 points (-53.2 to -10.1), and all 143 attacks it caught in B-self were labelled Fuzzers.
- **Models copied their memories.** Gemma's family followed the most common family among retrieved cases 97.6% of the time, against 40.9% for the same comparison without memory. For gpt-oss-20b the figures were 93.9% and 65.9%.
- **The stored labels are the cause.** With identical retrieval, correct labels raised recall and family accuracy above Arm A for both models.
- **gpt-oss-20b lost recall, but the result is not robust.** The 14.2-point drop was significant per alert (p = 0.0018), but not under the stricter test (-37.4 to +4.5).
- **Qwen gave no usable signal.** Recall was 2% without memory and 0% with it, a floor effect (p = 0.0625).

## Project value and impact

- **Practical guidance:** memory is not automatically safe. What gets stored decides whether it helps, so verified labels matter more than retrieval alone.
- **Error propagation measured:** the project puts numbers on how a system can repeat its own mistakes, instead of treating that as a theoretical risk.
- **Operational benefit:** near-duplicate alert groups given a consistent verdict rose from 10 to 17 of 17 for Gemma, and from 5 to 14 of 17 for gpt-oss-20b, though copying drives part of this consistency.
- **Reusable method:** the design and working dashboard let other teams test memory on other models.

**Limitations:** every scored alert was a real attack, so reduced false positives, the project's original primary metric, was not measured here. Protocol v4 is pre-registered to address benign alerts, and its results are not included. The data is a synthetic testbed, and the oracle arm is an upper bound rather than a deployable system.
