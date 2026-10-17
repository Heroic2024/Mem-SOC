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


class VerdictParsingTests(unittest.TestCase):
    """
    A verdict the model wrapped in an array is still that verdict.
    BL-125: gemma-4-26b-a4b-it did this on 1 alert in 128 and, at
    temperature 0, on all three attempts, which stopped a protocol run.
    """

    def test_a_single_verdict_in_an_array_is_unwrapped(self):
        parsed = triage_prompt.parse_llm_response(json.dumps([FIXTURE_VERDICT]))
        self.assertEqual(parsed["verdict"], FIXTURE_VERDICT["verdict"])
        self.assertEqual(parsed["attack_category"], FIXTURE_VERDICT["attack_category"])

    def test_unwrapping_changes_nothing_a_bare_object_would_give(self):
        self.assertEqual(
            triage_prompt.parse_llm_response(json.dumps([FIXTURE_VERDICT])),
            triage_prompt.parse_llm_response(VERDICT_JSON),
        )

    def test_a_wrapped_verdict_is_still_validated(self):
        bad = dict(FIXTURE_VERDICT, verdict="probably_bad")
        with self.assertRaises(ValueError):
            triage_prompt.parse_llm_response(json.dumps([bad]))

    def test_an_array_that_is_not_one_verdict_still_fails(self):
        for raw in ("[]", json.dumps([FIXTURE_VERDICT, FIXTURE_VERDICT]), '["true_positive"]'):
            with self.subTest(raw=raw[:40]), self.assertRaises(ValueError):
                triage_prompt.parse_llm_response(raw)


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
        self.budget_dir = Path(self.tmp.name)

        for patch in (
            mock.patch("memsoc.paths.MODEL_OUTPUTS_DIR", self.tmp.name),
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

    def test_count_survives_a_busy_budget_file(self):

        # Windows refuses the swap while another arm is reading the file.
        real_replace = os.replace
        refusals = iter([PermissionError(5, "Access is denied")] * 3)

        def flaky_replace(src, dst):
            error = next(refusals, None)
            if error:
                raise error
            real_replace(src, dst)

        with mock.patch("os.replace", side_effect=flaky_replace), \
                mock.patch("requests.post", return_value=_answer(VERDICT_JSON)):
            llm_client.call_gemini("prompt")

        self.assertEqual(llm_client._budget_state("gemini")["count"], 1)
        self.assertEqual(list(self.budget_dir.glob("*.tmp")), [])

    def test_missing_key_raises_before_any_request(self):

        with mock.patch.object(config, "GEMINI_API_KEY", ""), \
                mock.patch("requests.post") as post:
            with self.assertRaises(llm_client.GeminiAPIKeyMissing):
                llm_client.call_gemini("prompt")

        post.assert_not_called()


def _groq_answer(text):

    return _Response(200, {
        "choices": [{"finish_reason": "stop", "message": {"content": text}}],
        "usage": {"prompt_tokens": 1200, "completion_tokens": 800, "total_tokens": 2000},
    })


class TriageModelSelectionTests(unittest.TestCase):
    """Protocol v1: one output cap, JSON mode and a per-model budget for every model."""

    def setUp(self):

        self.tmp = tempfile.TemporaryDirectory()

        for patch in (
            mock.patch("memsoc.paths.MODEL_OUTPUTS_DIR", self.tmp.name),
            mock.patch.object(config, "GEMINI_API_KEY", "test-key"),
            mock.patch.object(config, "GROQ_API_KEY", "test-key"),
            mock.patch("time.sleep"),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def tearDown(self):

        self.tmp.cleanup()

    def _select(self, provider, model):

        for patch in (
            mock.patch.object(config, "TRIAGE_PROVIDER", provider),
            mock.patch.object(config, "TRIAGE_MODEL", model),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def test_groq_triage_sends_the_triage_model_cap_and_json_mode(self):

        self._select("groq", "qwen/qwen3.8-27b")

        with mock.patch("requests.post", return_value=_groq_answer(VERDICT_JSON)) as post:
            llm_client.call_triage_llm("prompt")

        payload = post.call_args.kwargs["json"]

        self.assertEqual(payload["model"], "qwen/qwen3.8-27b")
        self.assertEqual(payload["max_tokens"], config.TRIAGE_MAX_RESPONSE_TOKENS)
        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertNotIn("reasoning_effort", payload)
        self.assertEqual(llm_client.triage_model_id(), "qwen/qwen3.8-27b")
        self.assertEqual(llm_client.LAST_USAGE["total_tokens"], 2000)

    def test_gemini_triage_uses_the_same_cap_and_the_model_url(self):

        self._select("gemini", "gemma-4-26b-a4b-it")

        with mock.patch("requests.post", return_value=_answer(VERDICT_JSON)) as post:
            llm_client.call_triage_llm("prompt")

        self.assertIn("/gemma-4-26b-a4b-it:generateContent", post.call_args.args[0])
        generation = post.call_args.kwargs["json"]["generationConfig"]
        self.assertEqual(generation["maxOutputTokens"], config.TRIAGE_MAX_RESPONSE_TOKENS)
        self.assertEqual(generation["responseMimeType"], "application/json")

    def test_budgets_are_counted_per_model(self):

        self._select("gemini", "gemma-4-26b-a4b-it")

        with mock.patch("requests.post", return_value=_answer(VERDICT_JSON)):
            llm_client.call_gemini("prompt", model="gemma-4-26b-a4b-it")
            llm_client.call_gemini("prompt", model="gemma-4-26b-a4b-it")
            llm_client.call_gemini("prompt", model="gemini-3.1-flash-lite")

        self.assertEqual(llm_client._budget_state("gemini", "gemma-4-26b-a4b-it")["count"], 2)
        self.assertEqual(llm_client._budget_state("gemini", "gemini-3.1-flash-lite")["count"], 1)
        self.assertEqual(llm_client.budget_remaining("gemini", "gemma-4-26b-a4b-it"), 14400 - 20 - 2)

    def test_a_small_allowance_is_not_swallowed_by_the_reserve(self):

        self.assertGreater(llm_client.budget_remaining("gemini", "gemini-3.8-flash"), 0)

    def test_groq_per_day_limit_stops_with_the_quoted_wait(self):

        self._select("groq", "openai/gpt-oss-20b")

        exhausted = _Response(429, {"error": {
            "message": "Rate limit reached for model `openai/gpt-oss-20b` in organization `o` "
                       "on tokens per day (TPD): Limit 200000, Used 199000, Requested 7400. "
                       "Please try again in 48m10.08s.",
            "code": "rate_limit_exceeded",
        }})

        with mock.patch("requests.post", return_value=exhausted) as post:
            with self.assertRaises(llm_client.DailyBudgetExhausted) as caught:
                llm_client.call_triage_llm("prompt")

        self.assertEqual(post.call_count, 1)
        self.assertAlmostEqual(caught.exception.retry_after, 48 * 60 + 10.08)

    def test_groq_server_errors_are_retried(self):

        self._select("groq", "openai/gpt-oss-20b")

        busy = _Response(503, {"error": {"message": "over capacity"}})

        with mock.patch("requests.post", side_effect=[busy, _groq_answer(VERDICT_JSON)]):
            text, _ = llm_client.call_triage_llm("prompt")

        self.assertEqual(json.loads(text), FIXTURE_VERDICT)

    def test_quoted_waits_in_every_unit(self):

        for text, seconds in (
            ("Please try again in 20.22s.", 20.22),
            ("Please try again in 48m10.08s.", 2890.08),
            ("Please try again in 1h2m3s.", 3723.0),
            ("Please try again in 250ms.", 0.25),
            ("no wait quoted", None),
        ):
            wait = llm_client._quoted_wait(text)
            if seconds is None:
                self.assertIsNone(wait)
            else:
                self.assertAlmostEqual(wait, seconds)


class ProtocolRunTests(unittest.TestCase):
    """The protocol's scheduler: scope, arm order, resume, quota stop."""

    def setUp(self):

        from memsoc.triage import protocol_run

        self.protocol_run = protocol_run
        self.tmp = tempfile.TemporaryDirectory()
        self.calls = []

        alerts = [dict(FIXTURE_RECORD, uid=f"u{i}") for i in range(3)]
        flows = {a["uid"]: FIXTURE_FLOW for a in alerts}
        loaded = {"alerts": alerts, "flows": flows, "first": alerts[:2]}

        test = self

        class Recorder:
            skipped_writes = 0

            def __init__(self, run_id, condition):
                self.condition = condition

            def retrieve(self, record, flow):
                return []

            def write(self, *args, **kwargs):
                pass

        def fake_triage(record, flow, seq, mem, run_id=""):
            test.calls.append((seq, mem.condition))
            if test.fail_at == len(test.calls):
                raise llm_client.DailyBudgetExhausted("quota", retry_after=None)
            return {
                "uid": record["uid"], "seq": seq, "run_id": run_id, "memory_condition": mem.condition,
                "verdict": "true_positive", "attack_category": "Exploits", "confidence": 0.9,
                "rationale_summary": "r", "precedent_used": "", "precedent_count": 0,
                "latency_ms": 1.0, "model_id": "gemma-4-26b-a4b-it",
            }

        self.fail_at = None

        for patch in (
            mock.patch("memsoc.paths.RUNS_DIR", os.path.join(self.tmp.name, "runs")),
            mock.patch("memsoc.paths.MEMORY_STORE_DIR", os.path.join(self.tmp.name, "memory")),
            mock.patch.object(protocol_run, "_checks", return_value=([], loaded)),
            mock.patch.object(protocol_run, "_run_config", return_value={"protocol": "p1"}),
            mock.patch("memsoc.memory.open_memory", side_effect=Recorder),
            mock.patch.object(triage_runner, "triage_alert", side_effect=fake_triage),
            mock.patch("time.sleep"),
        ):
            patch.start()
            self.addCleanup(patch.stop)

        self.log = protocol_run.Log(Path(self.tmp.name) / "runs" / "protocol.log")

    def tearDown(self):

        self.tmp.cleanup()

    def test_each_alert_goes_through_all_three_arms_before_the_next(self):

        self.protocol_run.run(self.log, "gemma-4-26b", wait_on_quota=False)

        self.assertEqual(self.calls, [
            (0, "off"), (0, "self"), (0, "oracle"),
            (1, "off"), (1, "self"), (1, "oracle"),
        ])

        for prefix in ("armA", "bself", "boracle"):
            run_id = f"{prefix}-gemma4-26b-{self.protocol_run.PROTOCOL}"
            path = Path(self.tmp.name) / "runs" / run_id / "triage_verdicts.jsonl"
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 2)

    def test_a_rerun_resumes_without_repeating_any_verdict(self):

        self.fail_at = 4

        with self.assertRaises(SystemExit) as stopped:
            self.protocol_run.run(self.log, "gemma-4-26b", wait_on_quota=False)

        self.assertEqual(stopped.exception.code, 2)

        self.fail_at = None
        self.calls.clear()
        self.protocol_run.run(self.log, "gemma-4-26b", wait_on_quota=False)

        self.assertEqual(self.calls, [(1, "off"), (1, "self"), (1, "oracle")])

    def test_the_pinned_scope_and_retrieval_reference_agree(self):

        expected = self.protocol_run._load_expected_retrieval()

        self.assertEqual(self.protocol_run.PROTOCOL_ALERTS, 165)
        self.assertEqual(len(expected), 165)
        self.assertEqual(expected[0], [])
        self.assertTrue(all(len(seqs) <= 3 and all(s < i for s in seqs)
                            for i, seqs in enumerate(expected)))


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
