"""
Contract tests for the triage side of the memory integration: the
precedent section of the triage prompt, the Gemini client, and the
runner's two seams.

Offline. No API key, no network, no embedding model: the LLM call is
mocked and the memory layer is either "off" or a stand-in that records
calls.

    python -m unittest tests.test_triage_memory -v
"""

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))

from memsoc.memory import Case, open_memory
from memsoc.triage import config, llm_client, triage_prompt, triage_runner

from test_memory import FIXTURE_FLOW, FIXTURE_RECORD, FIXTURE_VERDICT


# SHA-256 of triage_prompt.render(FIXTURE_RECORD, FIXTURE_FLOW), taken
# BEFORE the precedent section was added on 2026-10-14. The same check
# was run over all 215 real alerts of the stream-v2 25,000-flow stream,
# and every prompt was byte-identical.
ARM_A_PROMPT_SHA256 = "fd33c7835b5f905af12f42765e63b328f16e802bd05ea80ec6aa80cbd5c2b351"


def _case(case_id, similarity, verdict="true_positive", category="Exploits"):

    return Case(
        case_id=case_id,
        similarity=similarity,
        distance=1.0 - similarity,
        document="TCP to port 80 (http)\nKey features: L4_DST_PORT, MIN_TTL, IN_BYTES",
        metadata={
            "verdict": verdict,
            "attack_category": category,
            "confidence": 0.9,
            "rationale_summary": "Repeated HTTP probing.",
            "src_ip": "SHOULD-NOT-RENDER",
        },
    )


class _Response:
    """The parts of requests.Response the Gemini client reads."""

    def __init__(self, status, body):

        self.status_code = status
        self._body = body
        self.text = json.dumps(body)
        self.headers = {}

    def json(self):

        return self._body

    def raise_for_status(self):

        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code}")


def _answer(text, finish="STOP"):

    return _Response(200, {
        "candidates": [{
            "finishReason": finish,
            "content": {"parts": [{"text": text}]},
        }],
    })


VERDICT_JSON = json.dumps(FIXTURE_VERDICT)


class PrecedentSectionTests(unittest.TestCase):

    def test_no_precedent_is_the_arm_a_prompt_byte_for_byte(self):

        for precedents in ((), []):
            prompt = triage_prompt.render(FIXTURE_RECORD, FIXTURE_FLOW, precedents)
            self.assertEqual(
                hashlib.sha256(prompt.encode()).hexdigest(), ARM_A_PROMPT_SHA256
            )

    def test_precedent_shows_ids_and_similarity_most_similar_first(self):

        prompt = triage_prompt.render(
            FIXTURE_RECORD, FIXTURE_FLOW,
            [_case("r:000002", 0.81), _case("r:000001", 0.97, "false_positive", "none")],
        )

        self.assertIn("Relevant past cases from this SOC's records:", prompt)
        self.assertLess(
            prompt.index("[Case r:000001 -- similarity 0.97]"),
            prompt.index("[Case r:000002 -- similarity 0.81]"),
        )
        self.assertIn("Verdict: false_positive (confidence 0.90)", prompt)
        self.assertIn("Attack category: none", prompt)
        self.assertLess(prompt.index("Relevant past cases"), prompt.index("TASK"))

    def test_precedent_renders_whitelisted_fields_only(self):

        prompt = triage_prompt.render(FIXTURE_RECORD, FIXTURE_FLOW, [_case("r:000001", 0.9)])

        self.assertNotIn("SHOULD-NOT-RENDER", prompt)


class GeminiClientTests(unittest.TestCase):

    def setUp(self):

        self.tmp = tempfile.TemporaryDirectory()
        budget = Path(self.tmp.name) / "budget.json"

        for patch in (
            mock.patch.object(config, "GEMINI_REQUEST_BUDGET_PATH", budget),
            mock.patch.object(config, "GEMINI_API_KEY", "test-key"),
            mock.patch("time.sleep"),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def tearDown(self):

        self.tmp.cleanup()

    def test_answer_is_returned_and_charged(self):

        with mock.patch("requests.post", return_value=_answer(VERDICT_JSON)) as post:
            text, _ = llm_client.call_gemini("prompt")

        self.assertEqual(json.loads(text), FIXTURE_VERDICT)
        self.assertEqual(post.call_args.kwargs["json"]["generationConfig"]["temperature"], 0)
        self.assertEqual(llm_client._budget_state("gemini")["count"], 1)

    def test_truncation_retries_then_raises(self):

        import requests

        responses = [_answer("", "MAX_TOKENS")] * (config.TRUNCATION_MAX_RETRIES + 1)

        with mock.patch("requests.post", side_effect=responses) as post:
            with self.assertRaises(requests.HTTPError):
                llm_client.call_gemini("prompt")

        self.assertEqual(post.call_count, config.TRUNCATION_MAX_RETRIES + 1)

    def test_per_minute_429_waits_and_retries(self):

        limited = _Response(429, {"error": {"details": [
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "7s"},
            {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
             "violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]},
        ]}})

        with mock.patch("requests.post", side_effect=[limited, _answer(VERDICT_JSON)]):
            text, _ = llm_client.call_gemini("prompt")

        self.assertEqual(json.loads(text), FIXTURE_VERDICT)

    def test_per_day_429_stops_the_run(self):

        exhausted = _Response(429, {"error": {"details": [
            {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
             "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
        ]}})

        with mock.patch("requests.post", return_value=exhausted) as post:
            with self.assertRaises(llm_client.DailyBudgetExhausted):
                llm_client.call_gemini("prompt")

        self.assertEqual(post.call_count, 1)

    def test_missing_key_raises_before_any_request(self):

        with mock.patch.object(config, "GEMINI_API_KEY", ""), \
                mock.patch("requests.post") as post:
            with self.assertRaises(llm_client.GeminiAPIKeyMissing):
                llm_client.call_gemini("prompt")

        post.assert_not_called()


class RunnerSeamTests(unittest.TestCase):

    def test_off_sends_the_arm_a_prompt_and_stores_nothing(self):

        with tempfile.TemporaryDirectory() as tmp:

            store_root = os.path.join(tmp, "memory")

            with mock.patch("memsoc.paths.MEMORY_STORE_DIR", store_root), \
                    mock.patch.object(llm_client, "call_triage_llm",
                                      return_value=(VERDICT_JSON, 1.0)) as call:

                mem = open_memory("arm-a", "off")
                row = triage_runner.triage_alert(FIXTURE_RECORD, FIXTURE_FLOW, 0, mem)
                triage_runner.write_back(mem, FIXTURE_RECORD, FIXTURE_FLOW, row)

            prompt = call.call_args.args[0]

            self.assertEqual(hashlib.sha256(prompt.encode()).hexdigest(), ARM_A_PROMPT_SHA256)
            self.assertEqual(row["arm"], "baseline")
            self.assertEqual(row["precedent_used"], "")
            self.assertEqual(row["precedent_count"], 0)
            self.assertEqual(row["precedent_chars"], 0)
            self.assertFalse(os.path.exists(store_root))

    def test_memory_cases_reach_the_prompt_and_the_row(self):

        class Recorder:
            condition = "self"
            skipped_writes = 0

            def __init__(self):
                self.writes = []

            def retrieve(self, record, flow):
                return [_case("run:000001", 0.95)]

            def write(self, record, flow, verdict, seq, precedent_used=()):
                self.writes.append((verdict, seq, list(precedent_used)))

        mem = Recorder()

        with mock.patch.object(llm_client, "call_triage_llm",
                               return_value=(VERDICT_JSON, 1.0)) as call:
            row = triage_runner.triage_alert(FIXTURE_RECORD, FIXTURE_FLOW, 4, mem, "run")

        triage_runner.write_back(mem, FIXTURE_RECORD, FIXTURE_FLOW, row)

        self.assertIn("[Case run:000001 -- similarity 0.95]", call.call_args.args[0])
        self.assertEqual(row["arm"], "memory-self")
        self.assertEqual(row["precedent_used"], "run:000001")
        self.assertGreater(row["precedent_chars"], 0)
        self.assertEqual(mem.writes, [(
            {k: FIXTURE_VERDICT[k] for k in ("verdict", "attack_category", "confidence", "rationale_summary")},
            4,
            ["run:000001"],
        )])


if __name__ == "__main__":
    unittest.main()
