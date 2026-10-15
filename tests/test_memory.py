"""
Contract tests for Layer 3, the memory layer (src/memsoc/memory/).

Every invariant here fails SILENTLY in production rather than raising,
which is why each one is asserted instead of assumed:

- the same text embeds to the same vector, every time;
- the store really is cosine space -- asserted on distances, not on the
  config string;
- an over-long case text raises instead of being truncated (BL-013);
- condition "off" touches nothing: no directory, no model, no write;
- "self" and "oracle" embed byte-identical text -- the oracle changes
  what a case says, never which cases come back;
- writes are idempotent, memory is append-only, and a store written
  under another schema is refused.

Needs the memory virtualenv (requirements/memory.txt). The `tests`
Docker image does not install it, so there the whole module skips:

    PYTHONPATH=src <memory-venv>/python -m unittest tests.test_memory -v

Stores are created in a temporary directory, never under artifacts/.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from importlib.util import find_spec

HAVE_MEMORY_DEPS = bool(find_spec("chromadb")) and bool(find_spec("sentence_transformers"))

FIXTURE_RECORD = {
    "uid": "C-test-1",
    "status": "attack",
    "binary_confidence": 1.0,
    "multiclass": {"prediction": "Exploits", "confidence": 0.7989},
    "alert": {
        "attack": "Exploits", "confidence": 0.7989,
        "src_port": 11056, "dst_port": 21, "protocol": 6,
        "shap_explanation": [
            {"feature": "CLIENT_TCP_FLAGS", "shap_value": 0.6297, "impact": "positive"},
            {"feature": "MIN_TTL", "shap_value": 0.6137, "impact": "positive"},
            {"feature": "DNS_QUERY_TYPE", "shap_value": 0.4769, "impact": "positive"},
            {"feature": "L7_PROTO", "shap_value": 0.2415, "impact": "positive"},
        ],
    },
}

FIXTURE_FLOW = {
    "uid": "C-test-1", "L7_PROTO": 1.0,
    "IN_PKTS": 13, "OUT_PKTS": 11, "IN_BYTES": 721, "OUT_BYTES": 891,
    "FLOW_DURATION_MILLISECONDS": 860,
    "SRC_TO_DST_AVG_THROUGHPUT": 6699, "DST_TO_SRC_AVG_THROUGHPUT": 8278,
    "SHORTEST_FLOW_PKT": 40, "LONGEST_FLOW_PKT": 145,
    "RETRANSMITTED_IN_PKTS": 5, "RETRANSMITTED_OUT_PKTS": 5,
    "MIN_TTL": 62, "MAX_TTL": 63,
    "CLIENT_TCP_FLAGS": 24, "SERVER_TCP_FLAGS": 16,
}

FIXTURE_VERDICT = {
    "verdict": "true_positive",
    "attack_category": "Exploits",
    "confidence": 0.8,
    "rationale_summary": "FTP control session with PSH/ACK and retransmits.",
}


def _variant(uid, dst_port, in_pkts):
    """A second, different alert built from the fixture."""

    record = json.loads(json.dumps(FIXTURE_RECORD))
    flow = dict(FIXTURE_FLOW)

    record["uid"] = flow["uid"] = uid
    record["alert"]["dst_port"] = dst_port
    flow["IN_PKTS"] = in_pkts

    return record, flow


class CaseTextTests(unittest.TestCase):
    """Pure rendering. No model, no store -- runs in any environment."""

    def test_no_ip_no_detector_label_in_text(self):

        from memsoc.memory import case_text

        record = json.loads(json.dumps(FIXTURE_RECORD))
        record["src_ip"] = "175.45.176.2"
        record["dst_ip"] = "149.171.126.12"

        text = case_text.render(record, FIXTURE_FLOW)

        self.assertNotIn("175.45", text)
        self.assertNotIn("149.171", text)
        self.assertNotIn("Exploits", text)
        self.assertNotIn("0.79", text)

    def test_top_three_shap_names_by_magnitude(self):

        from memsoc.memory import case_text

        record = json.loads(json.dumps(FIXTURE_RECORD))
        record["alert"]["shap_explanation"].append(
            {"feature": "TCP_FLAGS", "shap_value": -0.9, "impact": "negative"}
        )

        self.assertEqual(
            case_text.top_shap_features(record["alert"]),
            ["TCP_FLAGS", "CLIENT_TCP_FLAGS", "MIN_TTL"],
        )

    def test_non_finite_renders_as_na(self):

        from memsoc.memory import case_text

        flow = dict(FIXTURE_FLOW, SRC_TO_DST_AVG_THROUGHPUT=float("inf"))

        self.assertIn("n/a src to dst", case_text.render(FIXTURE_RECORD, flow))

    def test_missing_flow_raises(self):

        from memsoc.memory import case_text

        with self.assertRaises(ValueError):
            case_text.render(FIXTURE_RECORD, None)


class NullLayerTests(unittest.TestCase):
    """Arm A must touch nothing. Runs in any environment."""

    def test_off_creates_nothing_and_loads_nothing(self):

        from memsoc import paths
        from memsoc.memory import open_memory

        with tempfile.TemporaryDirectory() as tmp:

            original = paths.MEMORY_STORE_DIR
            paths.MEMORY_STORE_DIR = tmp

            try:
                mem = open_memory("baseline-run", "off")

                self.assertEqual(mem.retrieve(FIXTURE_RECORD, FIXTURE_FLOW), [])
                self.assertIsNone(
                    mem.write(FIXTURE_RECORD, FIXTURE_FLOW, FIXTURE_VERDICT, 1, [])
                )
                self.assertEqual(os.listdir(tmp), [])
            finally:
                paths.MEMORY_STORE_DIR = original

    def test_off_imports_no_model_and_no_store(self):

        # A fresh interpreter: other tests in this process load the model,
        # so sys.modules here would prove nothing.
        probe = (
            "import sys\n"
            "from memsoc.memory import open_memory\n"
            "mem = open_memory('baseline-run', 'off')\n"
            "mem.retrieve({}, {})\n"
            "mem.write({}, {}, {}, 1, [])\n"
            "loaded = [m for m in ('memsoc.memory.embedding', 'chromadb', 'torch') if m in sys.modules]\n"
            "sys.exit(1 if loaded else 0)\n"
        )

        env = dict(os.environ, PYTHONPATH=os.pathsep.join(
            p for p in (os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"),
                        os.environ.get("PYTHONPATH")) if p
        ))

        result = subprocess.run([sys.executable, "-c", probe], env=env)

        self.assertEqual(result.returncode, 0, "condition 'off' loaded the model or the store")

    def test_unknown_condition_raises(self):

        from memsoc.memory import open_memory

        with self.assertRaises(ValueError):
            open_memory("r", "baseline")


@unittest.skipUnless(HAVE_MEMORY_DEPS, "memory venv not installed (requirements/memory.txt)")
class EmbeddingTests(unittest.TestCase):

    def test_same_text_same_vector(self):

        from memsoc.memory import embedding

        a = embedding.embed("TCP to port 21 (ftp)")
        b = embedding.embed("TCP to port 21 (ftp)")

        self.assertEqual(a, b)
        self.assertEqual(len(a), embedding.EMBEDDING_DIM)

    def test_over_long_text_raises(self):

        from memsoc.memory import embedding

        with self.assertRaises(embedding.CaseTextTooLong):
            embedding.embed("retransmitted " * 400)


@unittest.skipUnless(HAVE_MEMORY_DEPS, "memory venv not installed (requirements/memory.txt)")
class StoreTests(unittest.TestCase):

    def setUp(self):

        from memsoc import paths

        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self._original = paths.MEMORY_STORE_DIR
        paths.MEMORY_STORE_DIR = self._tmp.name

    def tearDown(self):

        from memsoc import paths

        paths.MEMORY_STORE_DIR = self._original
        self._tmp.cleanup()

    def test_cosine_space_on_distances(self):

        from memsoc.memory import open_memory

        mem = open_memory("cosine", "self")

        unit = [1.0] + [0.0] * 383
        mem.collection.add(ids=["a"], embeddings=[unit], documents=["a"], metadatas=[{"k": 1}])

        self_hit = mem.collection.query(query_embeddings=[unit], n_results=1)
        opposite = mem.collection.query(query_embeddings=[[-1.0] + [0.0] * 383], n_results=1)

        # Cosine: 0 and 2. Chroma's L2 default would give 0 and 4.
        self.assertAlmostEqual(self_hit["distances"][0][0], 0.0, places=5)
        self.assertAlmostEqual(opposite["distances"][0][0], 2.0, places=5)

    def test_empty_store_returns_nothing(self):

        from memsoc.memory import open_memory

        mem = open_memory("empty", "self")

        self.assertEqual(mem.retrieve(FIXTURE_RECORD, FIXTURE_FLOW), [])

    def test_top_three_most_similar_first(self):

        from memsoc.memory import open_memory

        mem = open_memory("topk", "self")

        for seq in range(5):
            record, flow = _variant(f"C-{seq}", 21 + seq, 10 + seq * 50)
            mem.write(record, flow, FIXTURE_VERDICT, seq, [])

        cases = mem.retrieve(FIXTURE_RECORD, FIXTURE_FLOW)

        self.assertEqual(len(cases), 3)
        self.assertEqual(
            [c.similarity for c in cases],
            sorted((c.similarity for c in cases), reverse=True),
        )
        for case in cases:
            self.assertAlmostEqual(case.similarity, 1.0 - case.distance)

    def test_write_is_idempotent_and_append_only(self):

        from memsoc.memory import open_memory

        mem = open_memory("idem", "self")

        mem.write(FIXTURE_RECORD, FIXTURE_FLOW, FIXTURE_VERDICT, 7, [])
        mem.write(FIXTURE_RECORD, FIXTURE_FLOW, FIXTURE_VERDICT, 7, [])

        self.assertEqual(mem.collection.count(), 1)

        changed = dict(FIXTURE_VERDICT, verdict="false_positive")

        with self.assertRaises(ValueError):
            mem.write(FIXTURE_RECORD, FIXTURE_FLOW, changed, 7, [])

    def test_store_survives_reopen(self):

        from memsoc.memory import open_memory

        mem = open_memory("reopen", "self")
        mem.write(FIXTURE_RECORD, FIXTURE_FLOW, FIXTURE_VERDICT, 1, [])
        del mem

        again = open_memory("reopen", "self")

        self.assertEqual(again.collection.count(), 1)
        self.assertEqual(len(again.retrieve(FIXTURE_RECORD, FIXTURE_FLOW)), 1)

    def test_other_schema_or_condition_refused(self):

        import chromadb

        from memsoc import paths
        from memsoc.memory import SchemaMismatch, open_memory

        open_memory("cond", "self")

        with self.assertRaises(SchemaMismatch):
            open_memory("cond", "oracle")

        client = chromadb.PersistentClient(path=paths.memory_store("old"))
        client.create_collection(
            name="cases",
            metadata={"hnsw:space": "cosine", "schema_version": "0.9"},
            embedding_function=None,
        )

        with self.assertRaises(SchemaMismatch):
            open_memory("old", "self")

    def test_oracle_changes_metadata_never_text(self):

        from unittest import mock

        from memsoc.memory import open_memory

        own = open_memory("own", "self")
        oracle = open_memory("oracle", "oracle")

        # The LLM said true_positive / Exploits; the oracle says Fuzzers.
        with mock.patch.object(oracle, "_true_label", return_value=(1, "Fuzzers")):
            oracle.write(FIXTURE_RECORD, FIXTURE_FLOW, FIXTURE_VERDICT, 1, [])

        own.write(FIXTURE_RECORD, FIXTURE_FLOW, FIXTURE_VERDICT, 1, [])

        a = own.collection.get(include=["documents", "metadatas"])
        b = oracle.collection.get(include=["documents", "metadatas"])

        self.assertEqual(a["documents"], b["documents"])
        self.assertEqual(a["metadatas"][0]["attack_category"], "Exploits")
        self.assertEqual(b["metadatas"][0]["attack_category"], "Fuzzers")
        self.assertEqual(b["metadatas"][0]["label_source"], "oracle")
        self.assertEqual(b["metadatas"][0]["rationale_summary"], "")


if __name__ == "__main__":
    unittest.main()
