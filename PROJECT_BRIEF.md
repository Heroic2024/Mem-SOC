# Project Brief — Agentic SOC Capstone Project

> Authoritative design context for this repository. Everything below reflects decisions already made by the project team. Operating rules for the coding agent live in `CLAUDE.md`.

---

## 1. What This Project Is

An **Agentic SOC (Security Operations Center) triage system** built around a persistent **memory layer**.

The research contribution is **not** a better detection model and **not** a novel retrieval algorithm. It is the isolation and measurement of what a memory layer contributes when bolted onto LLM-based alert triage.

**Core thesis:** SOC analysts repeatedly re-investigate alerts that have already been resolved, because institutional knowledge lives in individual analysts' heads rather than in tooling. When an analyst rotates off shift or leaves, that knowledge disappears. A vector-DB-backed memory layer should reduce redundant investigation and false-positive volume by surfacing relevant precedent at triage time.

**The memory layer is the crux of the research.** Every other component exists to make the memory layer measurable.

---

## 2. Objectives

1. **Reduce false-positive volume** via similarity-based case retrieval.
2. **Enable memory retention & detailed reporting** — every decision stored with context and rationale, retrievable and citable later.
3. **Give the SOC institutional memory beyond one shift/analyst** — knowledge persists across shifts, analysts, and time, decoupled from any single person.

---

## 3. Scope & Experimental Control

This is a **controlled comparison**, and the control is the credibility backbone of the whole project. Preserve it in every design decision.

| Aspect | Status |
|---|---|
| Data stream | **Fixed** — same alert sequence replayed through both arms |
| Detection layer (ML model) | **Fixed / frozen** — identical weights and thresholds in both arms |
| LLM | **Fixed** — same model in both arms |
| Prompts | **Fixed** — same base prompt template in both arms |
| **Memory layer** | **THE VARIABLE** — present in one arm, absent in the other |

**Two arms:**
- **Arm A — Memoryless baseline:** alert → LLM triage → verdict + rationale. No retrieval, no persistence.
- **Arm B — Memory-augmented:** alert → embed → similarity retrieval from vector DB → inject precedent into the same base prompt → LLM triage → verdict + rationale → write case back to memory.

If any measured difference between arms could be attributed to something other than the memory layer, the experiment is invalid. Guard this aggressively.

---

## 4. System Architecture — Four Layers

```
[1] DATA STREAM  →  [2] DETECTION (ML)  →  [3] MEMORY (Vector DB)  →  [4] LLM TRIAGE + REPORTING
                                                    ↑______________________________|
                                                          (write-back loop)
```

### Layer 1 — Data Stream
- Source dataset: **NF-UNSW-NB15-v3** (current — what the detector is trained on today) → **NF-CICIDS2018-v3** (target for model training). Both use the NetFlow v3 schema, so the feature set is stable across the switch; the **attack label vocabulary is not**.
- CICIDS2017 was the original choice and has been **dropped as outdated**.
- Replayed as a sequential alert stream to simulate live SOC ingest.
- The **identical sequence** must be replayable deterministically through both arms. Seed and order must be reproducible.

### Layer 2 — Detection (Open-Source ML Model)
- An open-source ML classifier (LightGBM multiclass, `final_ml_model_v1/`) trained on the NF-* v3 dataset produces the alerts/scores that enter triage.
- **Frozen after training.** It is a fixed input, not a subject of evaluation. Do not tune it per-arm.
- Produces the raw signal; it does **not** produce the final verdict.

### Layer 3 — Memory Layer (ChromaDB) — *the research crux*
- **Write path:** after each triage, embed the case (alert features + context + verdict + rationale) and store the vector plus metadata (verdict, timestamp, attack category, protocol, source/dest, case ID) and original text.
- **Read path:** embed the incoming alert with the *same* embedding model → top-k similarity search → optional metadata filter → similarity threshold cutoff → inject retrieved cases into the LLM prompt.
- **Non-negotiable:** the same embedding model on both paths. Mismatched models make similarity meaningless.
- Persistent/on-disk mode from day one. In-memory mode would make "memory persists across shifts" false.

### Layer 4 — LLM Triage & Reporting
- Consumes the alert plus (in Arm B only) retrieved precedent.
- Emits: a **verdict** and an **explainable report** — not a raw score.
- Report must state: what the alert was, which past case(s) it matched, why that precedent was or wasn't relevant, and the reasoning behind the final call.
- **Dual-audience output:**
  - *Technical view* — feature-level context, matched case IDs, confidence, full rationale.
  - *Non-technical view* — plain-language summary of what happened, why it was triaged this way, and what it means.

---

## 5. Ground Truth Handling — Read Carefully

The dataset's ground-truth labels (the `Attack` column) function as **simulated analyst verdicts** for evaluation purposes.

**Working assumption to implement:** ground-truth labels are held out as the **evaluation oracle only**. The ML detector produces alerts; the LLM produces verdicts; ground truth scores those verdicts after the fact.

**Flag this explicitly in the docs you generate.** There is a design ambiguity here worth surfacing to the team: if ground-truth labels also feed the memory store as confirmed verdicts, memory becomes an oracle rather than a realistic analyst record, which would inflate results. Recommend an explicit decision on this and document whichever choice is made. Do not silently pick one.

---

## 6. Technology Choices

- **Vector DB:** ChromaDB. Apache 2.0 licensed, open source, no vendor lock-in. Purpose-built for RAG; acts as long-term memory in a RAG pipeline. Persists to disk by default. Supports per-entry metadata for filtering. Uses HNSW graphs for top-k similarity search. Fast to stand up for a research prototype.
- **Embedding model:** a local sentence-transformers model (e.g. `all-MiniLM-L6-v2`) — lightweight, runs locally, no API dependency.
- **Detection model:** open-source ML classifier (LightGBM multiclass) trained on the NF-* v3 dataset.
- **LLM:** single fixed model, identical across both arms.

**Documented ChromaDB limitations (must appear in the limitations section):** high memory usage at scale due to reliance on in-memory operations; limited scalability for workloads with millions of vectors, where Pinecone/Weaviate/Milvus perform better. Neither blocks this project — a controlled comparison on a fixed dataset — but both would warrant re-evaluation at production traffic volumes.

---

## 7. Build Phases

**Phase 0 — Setup & data prep**
Install ChromaDB and embedding model. Persistent mode from the start. Preprocess the NF-* v3 dataset. Find the right OS ML model and define the output format. Complete data consistency should be maintained between layers. Define the **case schema**: which features become the embedded text representation vs. which become filterable metadata.

**Phase 1 — Baseline (Arm A) first**
Fixed-prompt LLM triage, no retrieval, no storage. Log verdicts against ground truth. Build this before the memory arm so there is something to beat.

**Phase 2 — Memory-augmented (Arm B)**
Lock the embedding function. Implement write path, then read path. Keep everything else byte-identical to Arm A.

**Phase 3 — Tuning**
Sweep top-k and similarity threshold. Verify retrieved cases are genuinely relevant, not noise. Decide the **write policy** (store every case / only high-confidence / only confirmed) — this directly controls error-propagation risk. Address **cold start**: memory begins empty, so early alerts get no benefit; either warm-start with a seed set or report cold-start and steady-state separately.

**Phase 4 — Evaluation**
Replay the identical alert sequence through both arms. Compare on:
- False-positive volume (**primary metric**)
- Precision / recall / F1
- Verdict consistency across similar or near-duplicate alerts
- Latency and token cost overhead introduced by retrieval
- Qualitative rationale quality — does it cite relevant precedent, or noisy matches?

**Phase 5 — Reporting layer**
Explainable per-decision reports in both technical and non-technical views.

---

## 8. Known Risks & Failure Modes

These must be documented, not buried. They are part of the honest contribution.

- **Error propagation** — a mis-triaged case stored in memory can cause the same error to repeat across all future similar alerts. This is the single most important failure mode. It must be explicitly *tested*, not just mentioned: identify or inject a mis-stored case and measure downstream corruption.
- **Cold start** — an empty memory store means early alerts receive no benefit, likely understating steady-state performance.
- **Retrieval noise** — a poorly chosen top-k or absent threshold injects irrelevant "precedent" and could make Arm B *worse* than Arm A.
- **Dataset realism** — NF-UNSW-NB15-v3 and NF-CICIDS2018-v3 are synthetic testbed captures, not production traffic; their attack mix and volumes may not reflect real SOC alert distributions. Newer than CICIDS2017, but still simulated.
- **Dataset switch mid-project** — the detector is trained on NF-UNSW-NB15-v3 today and targeted at NF-CICIDS2018-v3. The two share the NetFlow v3 feature schema but have **disjoint attack label vocabularies**, so a retrain changes `detector_label` and invalidates every stored case. Any switch requires a `schema_version` bump and a new store; results across the two are not comparable.
- **Ground-truth oversimplification** — real analyst verdicts involve ambiguity that binary labels do not capture.
- **Frozen detector** — the study says nothing about how memory-augmented triage behaves with a noisy or imperfect detector, which is the real-world case.

A negative or null result is a legitimate outcome. Do not design the evaluation to guarantee that Arm B wins.

---

## 9. Critical Engineering Constraint

**Arms A and B must share as much code as possible** — same prompt template object, same LLM call wrapper, same logging, same scoring harness. The only divergence should be the retrieval-and-inject step and the write-back step.

If the two arms are implemented as separate codepaths, incidental implementation differences will contaminate the results and the experiment cannot support its own conclusion. Structure the repo so that Arm B is Arm A plus a toggleable memory module, not a parallel reimplementation.

---

## 10. Final Deliverables

1. **Memory Retention** — vector DB storing past incidents as embeddings, retrieved by similarity.
2. **Reporting & Analysis** — explainable LLM-generated reports, not just raw scores.
3. **Dual-audience output** — usable by both technical and non-technical stakeholders.

Plus, as academic output: the controlled comparison results, the error-propagation analysis, and the documented limitations.

---

## 11. Documentation To Be Produced

- **Architecture doc** — the four layers in §4.
- **Data & case schema doc** — resolving the open questions in §5 and Phase 0.
- **Experiment protocol doc** — §3 and Phase 4, including how reproducibility of the alert sequence is guaranteed.
- **Risks & limitations doc** — §8.
- **Per-phase implementation plans** — §7.