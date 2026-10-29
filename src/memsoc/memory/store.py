"""
The memory store: one read path, one write path, one switch.

    mem = open_memory(run_id, condition)        # "off" | "self" | "oracle"
    cases = mem.retrieve(record, flow)          # before the prompt is built
    mem.write(record, flow, verdict, seq, precedent_used)   # after the verdict is logged

The three conditions (decisions.md A3, work-split.md)
-----------------------------------------------------
- "off"    -- Arm A. NullMemoryLayer: retrieve() returns [] and write()
              returns. Neither touches disk or loads the embedding model,
              so the baseline cannot write to memory by construction.
- "self"   -- Arm B-self, the headline. Stores the LLM's own verdicts,
              right or wrong.
- "oracle" -- Arm B-oracle, a declared ceiling, never the headline.
              Identical to "self" except that write() replaces the
              verdict fields with the dataset's true label.
- "shuffled" -- protocol v4, supplementary. Writes exactly as "oracle".
              On read, each retrieved case's label is replaced with a
              true label sampled from every case stored so far, seeded
              by the querying alert's uid. The same cases come back;
              only their label content is destroyed. Every replacement
              is logged to shuffles.jsonl.

"self", "oracle" and "shuffled" are the same class. _verdict_fields()
changes metadata only: the embedding text is rendered by the same
case_text.render() in every condition, so no condition can change which
cases come back -- only what they say. _shuffle_labels() runs after the
cases are chosen, for the same reason. Ground truth is read nowhere
else in the memory layer.

Retrieval follows decisions.md C8: top 3, no similarity cut-off.
Writes follow C5: every case is written (write_all).

What lands in the run directory, paths.memory_store(run_id)
-----------------------------------------------------------
- the ChromaDB files            PersistentClient, cosine space
- cases.jsonl                   sidecar: one full row per write attempt
- writes.jsonl                  one outcome row per write attempt
- retrievals.jsonl              every candidate with distance and similarity
- shuffles.jsonl                "shuffled" only: every label replacement
"""

import csv
import hashlib
import json
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from memsoc import paths
from memsoc.memory import case_text


CONDITIONS = ("off", "self", "oracle", "shuffled")

TOP_K = 3

WRITE_POLICY = "write_all"

COLLECTION_NAME = "cases"

RATIONALE_MAX_CHARS = 500

# Layer 2 emits no version identifier yet (BL-075). A sentinel rather
# than an omitted key: Chroma metadata may not hold None, and a key
# present on some cases and absent on others breaks `where` filters.
DETECTOR_VERSION = "unknown"


class SchemaMismatch(RuntimeError):
    """The store was written under a different template, model or condition."""


@dataclass(frozen=True)
class Case:
    """One retrieved precedent. Ordered by descending similarity in a result."""

    case_id: str
    similarity: float
    distance: float
    document: str
    metadata: dict


def open_memory(run_id: str, condition: str):
    """The single switch. Returns the layer for this run's condition."""

    if condition not in CONDITIONS:
        raise ValueError(
            f"condition must be one of {CONDITIONS}, got {condition!r}"
        )

    if condition == "off":
        return NullMemoryLayer(run_id)

    return MemoryLayer(run_id, condition)


class NullMemoryLayer:
    """
    Arm A. Retrieves nothing, writes nothing, opens nothing.

    It does not import chromadb or the embedding module, and it does not
    create the run directory -- the tests assert all three.
    """

    condition = "off"

    def __init__(self, run_id: str):

        self.run_id = run_id
        self.skipped_writes = 0

    def retrieve(self, record: dict, flow: dict) -> list:

        return []

    def write(self, record, flow, verdict, seq, precedent_used=()) -> None:

        return None


class MemoryLayer:
    """Arm B. Shared by "self", "oracle" and "shuffled"; see the module docstring."""

    def __init__(self, run_id: str, condition: str):

        import chromadb

        from memsoc.memory import embedding

        self._embedding = embedding

        self.run_id = run_id
        self.condition = condition
        self.skipped_writes = 0

        self.store_dir = paths.memory_store(run_id)
        os.makedirs(self.store_dir, exist_ok=True)

        expected = {
            "hnsw:space": "cosine",
            "schema_version": case_text.SCHEMA_VERSION,
            "embedding_model": embedding.MODEL_NAME,
            "embedding_revision": embedding.MODEL_REVISION,
            "condition": condition,
        }

        client = chromadb.PersistentClient(path=self.store_dir)

        # Embeddings are always computed by memsoc.memory.embedding and
        # passed in. Chroma is never given an embedding function, so the
        # one-model invariant is visible here rather than buried in
        # collection config (03-write-path.md).
        self.collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata=expected,
            embedding_function=None,
        )

        # get_or_create ignores `metadata` for an existing collection, so
        # a reopened store is checked against what this code would have
        # written. A mixed store is silently corrupt; refuse it.
        found = self.collection.metadata or {}

        for key, value in expected.items():

            if found.get(key) != value:
                raise SchemaMismatch(
                    f"store {self.store_dir} has {key}={found.get(key)!r}, "
                    f"this code expects {value!r}. Use a new run_id; never "
                    f"clear or migrate a store in place."
                )

        self._truth = None

    # -----------------------------------------------------------------
    # Read path
    # -----------------------------------------------------------------
    def retrieve(self, record: dict, flow: dict) -> list:
        """
        Up to TOP_K most similar past cases, most similar first.

        An empty store returns [] -- a normal state at the start of every
        run, not an error. Failures raise rather than degrade to [],
        because a silent [] would turn an Arm B alert into an Arm A one
        with nothing in the log to show it.
        """

        started = time.perf_counter()

        text = case_text.render(record, flow)
        vector = self._embedding.embed(text)

        embedded = time.perf_counter()

        count = self.collection.count()

        cases = []

        if count:

            result = self.collection.query(
                query_embeddings=[vector],
                n_results=min(TOP_K, count),
                include=["documents", "metadatas", "distances"],
            )

            for case_id, document, metadata, distance in zip(
                result["ids"][0],
                result["documents"][0],
                result["metadatas"][0],
                result["distances"][0],
            ):
                cases.append(Case(
                    case_id=case_id,
                    # Cosine space: the one place distance becomes
                    # similarity (04-read-path.md).
                    similarity=1.0 - float(distance),
                    distance=float(distance),
                    document=document,
                    metadata=dict(metadata),
                ))

            cases.sort(key=lambda case: case.distance)

        if self.condition == "shuffled":
            cases = self._shuffle_labels(record, cases)

        finished = time.perf_counter()

        self._append("retrievals.jsonl", {
            "uid": record.get("uid"),
            "collection_count": count,
            "candidates": [
                {
                    "case_id": case.case_id,
                    "distance": case.distance,
                    "similarity": case.similarity,
                }
                for case in cases
            ],
            "embed_ms": round((embedded - started) * 1000, 2),
            "query_ms": round((finished - embedded) * 1000, 2),
            "total_retrieval_ms": round((finished - started) * 1000, 2),
        })

        return cases

    def _shuffle_labels(self, record, cases) -> list:
        """
        "shuffled" only. Replace each retrieved case's label with a true
        label drawn, with replacement, from every case stored so far.

        Drawing from the stored labels keeps the class mix of what the
        LLM sees the same as the store's own. The pool is ordered by seq
        and the generator is seeded from the querying alert's uid, so the
        same alert against the same store always gets the same labels --
        a resumed run reproduces them exactly. Only verdict and
        attack_category change; confidence and rationale are the
        oracle's constant 1.0 and "" in every case already.
        """

        if not cases:
            return cases

        stored = self.collection.get(include=["metadatas"])["metadatas"]
        pool = [
            (m["verdict"], m["attack_category"])
            for m in sorted(stored, key=lambda m: int(m["seq"]))
        ]

        seed = shuffle_seed(record["uid"])
        rng = random.Random(seed)

        shuffled = []
        replacements = []

        for case in cases:

            verdict, attack_category = rng.choice(pool)

            replacements.append({
                "case_id": case.case_id,
                "from_verdict": case.metadata.get("verdict"),
                "from_attack_category": case.metadata.get("attack_category"),
                "to_verdict": verdict,
                "to_attack_category": attack_category,
            })

            shuffled.append(Case(
                case_id=case.case_id,
                similarity=case.similarity,
                distance=case.distance,
                document=case.document,
                metadata=dict(case.metadata, verdict=verdict, attack_category=attack_category),
            ))

        self._append("shuffles.jsonl", {
            "uid": record.get("uid"),
            "seed": seed,
            "pool_size": len(pool),
            "replacements": replacements,
        })

        return shuffled

    # -----------------------------------------------------------------
    # Write path
    # -----------------------------------------------------------------
    def write(self, record, flow, verdict, seq, precedent_used=()) -> None:
        """
        Store one triaged alert as a case. Call only after the verdict
        has been written to the scoring log (03-write-path.md, ordering).

        `verdict` is the dict triage_prompt.parse_llm_response() returns.
        `precedent_used` is the case IDs retrieve() returned for this
        alert -- what makes error propagation traceable.

        Rendering and schema errors raise. A failure to embed or to add
        is logged, counted in skipped_writes, and does not abort the run:
        the verdict is already scored.
        """

        case_id = f"{self.run_id}:{seq:06d}"

        document = case_text.render(record, flow)
        metadata = self._metadata(record, verdict, seq, case_id, precedent_used)

        _check_metadata(metadata)

        if self._is_duplicate(case_id, document, metadata):

            self._log_write(seq, case_id, record, False, "duplicate", 0.0, 0.0)
            return

        self._append("cases.jsonl", {
            "case_id": case_id,
            "document": document,
            "metadata": metadata,
            "llm_verdict": verdict,
            "flow": flow,
            "shap_explanation": (record.get("alert") or {}).get("shap_explanation"),
        })

        started = time.perf_counter()

        try:
            vector = self._embedding.embed(document)
        except Exception as e:
            self.skipped_writes += 1
            self._log_write(seq, case_id, record, False, f"embed failed: {e!r}", 0.0, 0.0)
            return

        embedded = time.perf_counter()

        try:
            self.collection.add(
                ids=[case_id],
                documents=[document],
                embeddings=[vector],
                metadatas=[metadata],
            )
        except Exception as e:
            self.skipped_writes += 1
            self._log_write(
                seq, case_id, record, False, f"add failed: {e!r}",
                (embedded - started) * 1000, 0.0,
            )
            return

        finished = time.perf_counter()

        self._log_write(
            seq, case_id, record, True, WRITE_POLICY,
            (embedded - started) * 1000, (finished - embedded) * 1000,
        )

    def _metadata(self, record, verdict, seq, case_id, precedent_used) -> dict:

        alert = record.get("alert") or {}
        multiclass = record.get("multiclass") or {}

        protocol = alert.get("protocol")
        precedent = list(precedent_used or ())

        # No src_ip / dst_ip, even though 02-case-schema.md lists them:
        # metadata is shown to the LLM with every retrieved case, and
        # source IP predicts the label on this dataset.
        metadata = {
            "case_id": case_id,
            "run_id": self.run_id,
            "seq": int(seq),
            "alert_id": record.get("uid"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "schema_version": case_text.SCHEMA_VERSION,
            "condition": self.condition,
            "write_policy": WRITE_POLICY,
            "src_port": alert.get("src_port"),
            "dst_port": alert.get("dst_port"),
            "protocol": protocol,
            "protocol_name": case_text.PROTOCOL_NAMES.get(protocol, str(protocol)),
            "detector_label": multiclass.get("prediction"),
            "detector_score": multiclass.get("confidence"),
            "detector_version": DETECTOR_VERSION,
            "precedent_used": ",".join(precedent),
            "precedent_count": len(precedent),
        }

        metadata.update(self._verdict_fields(record, verdict))

        return metadata

    def _verdict_fields(self, record, verdict) -> dict:
        """
        The ONLY place the conditions diverge.

        "self" stores the LLM's verdict. "oracle" stores the true label
        in its place and no rationale: the LLM's rationale argues for the
        LLM's verdict, and pairing it with a different label would be the
        "mix" condition decisions.md A3 dropped. "shuffled" stores what
        "oracle" stores; its labels are replaced on read, never on disk.
        """

        if self.condition == "self":

            return {
                "label_source": "llm",
                "verdict": verdict["verdict"],
                "attack_category": verdict["attack_category"],
                "confidence": float(verdict["confidence"]),
                "rationale_summary": str(verdict["rationale_summary"])[:RATIONALE_MAX_CHARS],
            }

        label, attack = self._true_label(record["uid"])

        return {
            "label_source": "oracle",
            "verdict": "true_positive" if label == 1 else "false_positive",
            "attack_category": attack if label == 1 else "none",
            "confidence": 1.0,
            "rationale_summary": "",
        }

    def _true_label(self, uid: str) -> tuple:
        """Oracle condition only. Read lazily, so "self" never opens the file."""

        if self._truth is None:

            with open(paths.GROUND_TRUTH, "r", encoding="utf-8", newline="") as f:
                self._truth = {
                    row["uid"]: (int(row["label"]), row["attack"])
                    for row in csv.DictReader(f)
                }

        if uid not in self._truth:
            raise KeyError(
                f"uid {uid} is not in {paths.GROUND_TRUTH}; the oracle "
                f"condition cannot write a case without its true label"
            )

        return self._truth[uid]

    def _is_duplicate(self, case_id, document, metadata) -> bool:
        """
        True if this exact case is already stored. Writes are idempotent
        by case_id; a same-ID write with different content would mutate
        memory, which is append-only, so it raises.
        """

        existing = self.collection.get(ids=[case_id], include=["documents", "metadatas"])

        if not existing["ids"]:
            return False

        stored = dict(existing["metadatas"][0])
        stored.pop("created_at", None)

        incoming = dict(metadata)
        incoming.pop("created_at", None)

        if existing["documents"][0] != document or stored != incoming:
            raise ValueError(
                f"case {case_id} is already stored with different content; "
                f"memory is append-only"
            )

        return True

    def _log_write(self, seq, case_id, record, written, reason, embed_ms, add_ms):

        self._append("writes.jsonl", {
            "seq": int(seq),
            "case_id": case_id,
            "uid": record.get("uid"),
            "written": written,
            "policy": WRITE_POLICY,
            "reason": reason,
            "embed_ms": round(embed_ms, 2),
            "add_ms": round(add_ms, 2),
            "collection_count_after": self.collection.count(),
            "skipped_writes": self.skipped_writes,
        })

    def _append(self, filename: str, row: dict) -> None:

        with open(os.path.join(self.store_dir, filename), "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")


def shuffle_seed(uid: str) -> int:
    """The "shuffled" condition's per-alert seed: the first 64 bits of SHA-256(uid)."""

    return int(hashlib.sha256(uid.encode("utf-8")).hexdigest()[:16], 16)


def _check_metadata(metadata: dict) -> None:
    """Chroma takes str/int/float/bool only. A None is a schema bug: raise."""

    for key, value in metadata.items():

        if value is None or not isinstance(value, (str, int, float, bool)):
            raise TypeError(
                f"metadata {key}={value!r} is not a str/int/float/bool; "
                f"fix the record, do not coerce it (03-write-path.md)"
            )
