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

import requests

from memsoc.memory import Case, open_memory
from memsoc.triage import config, llm_client, triage_prompt, triage_runner

from test_memory import FIXTURE_FLOW, FIXTURE_RECORD, FIXTURE_VERDICT


# SHA-256 of triage_prompt.render(FIXTURE_RECORD, FIXTURE_FLOW), taken
# BEFORE the precedent section was added on 2026-10-14. The same check
# was run over all 215 real alerts of the stream-v2 25,000-flow stream,
# and every prompt was byte-identical.
ARM_A_PROMPT_SHA256 = "fd33c7835b5f905af12f42765e63b328f16e802bd05ea80ec6aa80cbd5c2b351"

# Every prompt wording ever used, by the config.PROMPT_VARIANT name it
# was run under. A prompt change adds a NEW entry and bumps the variant;
# an existing entry is never edited, or verdicts already labelled with
# that name would stop meaning what they say.
PROMPT_VARIANT_SHA256 = {
    "label-hypothesis-v1": ARM_A_PROMPT_SHA256,
}


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

    def test_prompt_variant_names_the_current_wording(self):
        """A prompt edit without a PROMPT_VARIANT bump fails here."""

        self.assertIn(
            config.PROMPT_VARIANT, PROMPT_VARIANT_SHA256,
            "PROMPT_VARIANT has no recorded hash; add one for the new wording",
        )

        prompt = triage_prompt.render(FIXTURE_RECORD, FIXTURE_FLOW)

        self.assertEqual(
            hashlib.sha256(prompt.encode()).hexdigest(),
            PROMPT_VARIANT_SHA256[config.PROMPT_VARIANT],
            "the triage prompt changed but config.PROMPT_VARIANT did not",
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

    def test_a_case_with_family_and_reasoning_renders_as_before_byte_for_byte(self):

        # The block exactly as the p3 runs rendered it (BL-170 must not
        # change any existing condition's prompt).
        case = _case("r:000001", 0.9)

        self.assertEqual(
            triage_prompt._render_precedents([case]),
            "Relevant past cases from this SOC's records:\n\n"
            f"[Case r:000001 -- similarity 0.90]\n{case.document}\n"
            "Verdict: true_positive (confidence 0.90)\n"
            "Attack category: Exploits\n"
            "Reasoning: Repeated HTTP probing.\n\n",
        )

        oracle = Case("r:000002", 0.8, 0.2, case.document,
                      {"verdict": "true_positive", "attack_category": "DoS",
                       "confidence": 1.0, "rationale_summary": ""})

        self.assertIn("Attack category: DoS\nReasoning: (none recorded)",
                      triage_prompt._render_precedents([oracle]))

    def test_a_label_free_case_shows_no_family_and_no_reasoning(self):

        case = Case("r:000003", 0.85, 0.15, "TCP to port 80 (http)",
                    {"verdict": "true_positive", "confidence": 0.8, "label_source": "llm"})

        block = triage_prompt._render_precedents([case])

        self.assertIn("Verdict: true_positive (confidence 0.80)\n\n", block)
        self.assertNotIn("Attack category", block)
        self.assertNotIn("Reasoning", block)


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

    def test_gemini_retries_the_same_server_errors_as_groq(self):
        """
        502 was missing from the Gemini set while Groq retried it, so a
        single bad gateway ended a Gemma run (BL-126).
        """

        for status in (500, 502, 503):
            with self.subTest(status=status):
                busy = _Response(status, {"error": {"message": "upstream"}})
                with mock.patch("requests.post", side_effect=[busy, _answer(VERDICT_JSON)]):
                    with mock.patch("time.sleep"):
                        text, _ = llm_client.call_gemini("prompt", model="gemma-4-26b-a4b-it")
                self.assertEqual(json.loads(text), FIXTURE_VERDICT)

    def test_an_empty_answer_is_an_http_error_so_the_driver_can_retry(self):

        empty = _answer("")

        with mock.patch("requests.post", return_value=empty):
            with self.assertRaises(requests.HTTPError):
                llm_client.call_gemini("prompt", model="gemma-4-26b-a4b-it")

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
        self.assertEqual(payload["max_tokens"], 6000)
        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertNotIn("reasoning_effort", payload)
        self.assertEqual(llm_client.triage_model_id(), "qwen/qwen3.8-27b")
        self.assertEqual(llm_client.LAST_USAGE["total_tokens"], 2000)

    def test_gemini_triage_uses_its_own_cap_and_the_model_url(self):

        self._select("gemini", "gemma-4-26b-a4b-it")

        with mock.patch("requests.post", return_value=_answer(VERDICT_JSON)) as post:
            llm_client.call_triage_llm("prompt")

        self.assertIn("/gemma-4-26b-a4b-it:generateContent", post.call_args.args[0])
        generation = post.call_args.kwargs["json"]["generationConfig"]
        self.assertEqual(
            generation["maxOutputTokens"],
            config.max_response_tokens("gemma-4-26b-a4b-it"),
        )
        self.assertEqual(generation["maxOutputTokens"], 16384)
        self.assertEqual(generation["responseMimeType"], "application/json")

    def test_the_output_cap_is_per_model_with_a_shared_default(self):
        """
        BL-126: Gemma gets its own cap; everyone else keeps the Groq-sized
        default. A model nobody has listed must fall back, not raise.
        """

        self.assertEqual(config.max_response_tokens("gemma-4-26b-a4b-it"), 16384)

        for model in ("openai/gpt-oss-20b", "qwen/qwen3.8-27b", "a-model-nobody-listed"):
            with self.subTest(model=model):
                self.assertEqual(
                    config.max_response_tokens(model),
                    config.TRIAGE_MAX_RESPONSE_TOKENS,
                )

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


class ProtocolV4Tests(unittest.TestCase):
    """Protocol v4: one arm per experiment, its own run ids, the pre-registration gate."""

    def setUp(self):

        from memsoc.triage import protocol_v4

        self.v4 = protocol_v4
        self.tmp = tempfile.TemporaryDirectory()
        self.calls = []

        alerts = [dict(FIXTURE_RECORD, uid=f"u{i}") for i in range(4)]
        flows = {a["uid"]: FIXTURE_FLOW for a in alerts}
        self.loaded = {"alerts": alerts, "flows": flows, "first": alerts[:3]}

        test = self

        test.seeded = 0

        class Recorder:
            skipped_writes = 0

            def __init__(self, run_id, condition):
                self.condition = condition
                self.writes = 0
                self.collection = mock.Mock(count=lambda: test.seeded + self.writes)

            def retrieve(self, record, flow):
                return []

            def write(self, *args, **kwargs):
                self.writes += 1

        def fake_triage(record, flow, seq, mem, run_id=""):
            test.calls.append((seq, mem.condition, run_id))
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
            mock.patch("memsoc.triage.protocol_run._run_config", return_value={"protocol": "p3"}),
            mock.patch("memsoc.memory.open_memory", side_effect=Recorder),
            mock.patch.object(triage_runner, "triage_alert", side_effect=fake_triage),
            mock.patch("time.sleep"),
        ):
            patch.start()
            self.addCleanup(patch.stop)

        self.log = self.v4.protocol_run.Log(Path(self.tmp.name) / "runs" / "protocol.log")

    def tearDown(self):

        self.tmp.cleanup()

    def _checks(self, failing=()):
        """The p3 checks all passing, except the names in `failing`."""

        names = ("Python 3.13", "no local changes to src/, tests/, requirements/",
                 "git checkout is the protocol tag", "data file generated_logs.jsonl")

        return mock.patch(
            "memsoc.triage.protocol_run._checks",
            return_value=([(n, "FAIL" if n in failing else "PASS", "") for n in names], self.loaded),
        )

    def _git(self, tagged=True, note=True, listed=True):
        """HEAD is or is not the v4 tag; the note and the benign list are or are not committed."""

        def fake(*args):
            if args[0] == "rev-parse":
                return "abc"
            if args[0] == "rev-list":
                return "abc" if tagged else None
            if args[0] == "ls-files":
                if args[-1] == self.v4.PREREGISTRATION:
                    return args[-1] if note else None
                return args[-1] if listed else None
            if args[0] == "status":
                return ""
            if args[0] == "log":
                return "abc 2026-10-30T00:00:00+00:00" if note else None
            return None

        return mock.patch("memsoc.triage.protocol_run._git", side_effect=fake)

    def _verdicts(self, run_id):

        path = Path(self.tmp.name) / "runs" / run_id / "triage_verdicts.jsonl"

        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def test_reversed_runs_the_same_alerts_in_exactly_reverse_order(self):

        with self._checks(), self._git():
            self.v4.run(self.log, "reversed", wait_on_quota=False)

        run_id = "bself-rev-gemma4-26b-p4"
        rows = self._verdicts(run_id)

        self.assertEqual([r["uid"] for r in rows], ["u2", "u1", "u0"])
        self.assertEqual([seq for seq, _, _ in self.calls], [0, 1, 2])
        self.assertEqual({c for _, c, _ in self.calls}, {"self"})

        config = json.loads((Path(self.tmp.name) / "runs" / run_id / "run_config.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(config["alert_order_sha256"],
                         self.v4._alert_order_sha256(self.loaded["first"][::-1]))

    def test_nolabel_runs_the_p3_alerts_under_its_own_condition(self):

        with self._checks(), self._git():
            self.v4.run(self.log, "nolabel", wait_on_quota=False)

        self.assertEqual(self.calls, [(s, "nolabel", "bnolabel-gemma4-26b-p4") for s in range(3)])

    def test_v4_run_ids_never_collide_with_v3(self):

        from memsoc.triage import protocol_run

        run_id = self.v4._run_id("shuffled")
        v3 = {f"{prefix}-gemma4-26b-{protocol_run.PROTOCOL}" for _, prefix in protocol_run.ARMS}

        self.assertEqual(run_id, "bshuf-gemma4-26b-p4")
        self.assertEqual(self.v4._run_id("shuffled", dry_run=True), "bshuf-gemma4-26b-p4-dryrun")
        self.assertNotIn(run_id, v3)

    def test_one_arm_over_the_alerts_rows_marked_p4(self):

        with self._checks(), self._git():
            self.v4.run(self.log, "shuffled", wait_on_quota=False)

        self.assertEqual(self.calls, [(s, "shuffled", "bshuf-gemma4-26b-p4") for s in range(3)])

        rows = self._verdicts("bshuf-gemma4-26b-p4")
        self.assertEqual([r["protocol"] for r in rows], ["p4"] * 3)
        self.assertEqual([r["experiment"] for r in rows], ["shuffled"] * 3)

        config = json.loads((Path(self.tmp.name) / "runs" / "bshuf-gemma4-26b-p4"
                             / "run_config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["protocol"], "p4")
        self.assertEqual(config["protocol_tag"], "memsoc-protocol-v4")
        self.assertEqual(config["alert_order_sha256"], self.v4._alert_order_sha256(self.loaded["first"]))

    def test_no_real_run_without_the_tag_or_the_committed_note(self):

        for tagged, note in ((False, True), (True, False)):

            with self.subTest(tagged=tagged, note=note):
                with self._checks(), self._git(tagged=tagged, note=note):
                    with self.assertRaises(SystemExit) as stopped:
                        self.v4.run(self.log, "shuffled", wait_on_quota=False)

                self.assertEqual(stopped.exception.code, 1)
                self.assertEqual(self.calls, [])

    def test_dry_run_tolerates_only_tag_note_and_clean_tree(self):

        with self._checks(failing=("no local changes to src/, tests/, requirements/",)), \
                self._git(tagged=False, note=False):
            self.v4.run(self.log, "shuffled", wait_on_quota=False, dry_run=True)

        self.assertEqual(self.calls, [(s, "shuffled", "bshuf-gemma4-26b-p4-dryrun")
                                      for s in range(self.v4.DRY_RUN_ALERTS)])

        self.calls.clear()

        with self._checks(failing=("data file generated_logs.jsonl",)), self._git(tagged=False, note=False):
            with self.assertRaises(SystemExit):
                self.v4.run(self.log, "shuffled", wait_on_quota=False, dry_run=True)

        self.assertEqual(self.calls, [])

    def test_a_rerun_resumes_without_repeating_any_verdict(self):

        self.fail_at = 2

        with self._checks(), self._git():
            with self.assertRaises(SystemExit) as stopped:
                self.v4.run(self.log, "shuffled", wait_on_quota=False)

        self.assertEqual(stopped.exception.code, 2)

        self.fail_at = None
        self.calls.clear()

        with self._checks(), self._git():
            self.v4.run(self.log, "shuffled", wait_on_quota=False)

        self.assertEqual([seq for seq, _, _ in self.calls], [1, 2])
        self.assertEqual(len(self._verdicts("bshuf-gemma4-26b-p4")), 3)

    def _benign(self, ok=True):
        """A three-flow benign set, its files matching (or not) the committed list."""

        from memsoc.triage import protocol_v4_benign

        records = [dict(FIXTURE_RECORD, uid=f"b{i}", v4_benign={"set": "hard"}) for i in range(3)]
        flows = {r["uid"]: FIXTURE_FLOW for r in records}

        return (
            mock.patch.object(protocol_v4_benign, "load", return_value=(records, flows)),
            mock.patch.object(protocol_v4_benign, "check", return_value=(ok, "test")),
        )

    def _seed_source(self, content=b"p3 store"):
        """A stand-in p3 B-self store, and SEED_STORES pinned to its hash."""

        root = Path(self.tmp.name) / "shared"
        store = root / "memory" / "bself-gemma4-26b-p3"
        store.mkdir(parents=True)
        (store / "chroma.sqlite3").write_bytes(b"p3 store")
        self.seeded = 165

        return (
            mock.patch("memsoc.paths.P3_GEMMA_RESULTS", str(root)),
            mock.patch.dict(self.v4.SEED_STORES,
                            {"bself-gemma4-26b-p3": (165, hashlib.sha256(content).hexdigest())}),
        )

    def test_benign_arm_numbers_on_from_the_attacks_and_keeps_the_real_score(self):

        load, check = self._benign()

        with self._checks(), self._git(), load, check:
            self.v4.run(self.log, "benign-armA", wait_on_quota=False)

        self.assertEqual(self.calls, [(s, "off", "armA-benign-gemma4-26b-p4") for s in (165, 166, 167)])
        rows = self._verdicts("armA-benign-gemma4-26b-p4")
        self.assertEqual([r["v4_benign"] for r in rows], [{"set": "hard"}] * 3)

    def test_no_benign_run_without_the_committed_list_or_matching_files(self):

        for listed, files_ok in ((False, True), (True, False)):

            with self.subTest(listed=listed, files_ok=files_ok):
                load, check = self._benign(ok=files_ok)

                with self._checks(), self._git(listed=listed), load, check:
                    with self.assertRaises(SystemExit):
                        self.v4.run(self.log, "benign-armA", wait_on_quota=False)

                self.assertEqual(self.calls, [])

    def test_seeded_arm_copies_the_verified_store_and_checks_its_size(self):

        load, check = self._benign()
        source, pinned = self._seed_source()

        with self._checks(), self._git(), load, check, source, pinned:
            self.v4.run(self.log, "benign-bself", wait_on_quota=False)

        copy = Path(self.tmp.name) / "memory" / "bself-benign-gemma4-26b-p4" / "chroma.sqlite3"
        self.assertEqual(copy.read_bytes(), b"p3 store")
        self.assertEqual([seq for seq, _, _ in self.calls], [165, 166, 167])

        config = json.loads((Path(self.tmp.name) / "runs" / "bself-benign-gemma4-26b-p4"
                             / "run_config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["seed_store"], "bself-gemma4-26b-p3")

    def test_seeded_arm_refuses_a_store_that_is_not_the_verified_one(self):

        load, check = self._benign()
        source, pinned = self._seed_source(content=b"some other store")

        with self._checks(), self._git(), load, check, source, pinned:
            with self.assertRaises(SystemExit) as stopped:
                self.v4.run(self.log, "benign-bself", wait_on_quota=False)

        self.assertEqual(stopped.exception.code, 1)
        self.assertEqual(self.calls, [])
        self.assertFalse((Path(self.tmp.name) / "memory" / "bself-benign-gemma4-26b-p4").exists())

    def test_seeded_arm_refuses_a_store_of_the_wrong_size(self):

        load, check = self._benign()
        source, pinned = self._seed_source()

        with self._checks(), self._git(), load, check, source, pinned:
            self.seeded = 164
            with self.assertRaises(SystemExit):
                self.v4.run(self.log, "benign-bself", wait_on_quota=False)

        self.assertEqual(self.calls, [])


class ApiErrorRetryTests(unittest.TestCase):
    """
    BL-126: requests.HTTPError is a sibling of ConnectionError and
    Timeout, not a subclass, so before protocol v3 every API error --
    an exhausted 5xx budget, an exhausted 429 budget, a truncation, an
    empty answer -- stopped the run with no retry at all. Two Gemma runs
    died that way. A 4xx that will never succeed must still stop at once.
    """

    def setUp(self):

        from memsoc.triage import protocol_run

        self.protocol_run = protocol_run
        self.logged = []
        self.log = lambda message="", error=False: self.logged.append(str(message))

        patch = mock.patch("time.sleep")
        patch.start()
        self.addCleanup(patch.stop)

    def _run(self, side_effect):

        with mock.patch.object(triage_runner, "triage_alert", side_effect=side_effect):
            with mock.patch.object(llm_client, "LAST_USAGE", {}):
                return self.protocol_run._triage_with_retries(
                    self.log, FIXTURE_RECORD, FIXTURE_FLOW, 0, None, "run-id"
                )

    @staticmethod
    def _http_error(status=None):

        error = requests.HTTPError(f"status {status}")

        if status is not None:
            response = requests.Response()
            response.status_code = status
            error.response = response

        return error

    def test_an_error_with_no_response_is_retried_then_succeeds(self):
        """A truncation or empty answer raised by the client itself."""

        row = self._run([self._http_error(), self._http_error(), {"ok": True}])

        self.assertEqual(row["ok"], True)
        self.assertEqual(row["attempts"], 3)
        self.assertEqual(sum("API error" in m for m in self.logged), 2)

    def test_server_errors_and_429_are_retried(self):

        for status in (500, 502, 503, 429):
            with self.subTest(status=status):
                self.logged.clear()
                row = self._run([self._http_error(status), {"ok": True}])
                self.assertEqual(row["attempts"], 2)

    def test_a_401_stops_at_once_without_burning_retries(self):

        calls = []

        def once(*args, **kwargs):
            calls.append(1)
            raise self._http_error(401)

        with self.assertRaises(requests.HTTPError):
            self._run(once)

        self.assertEqual(len(calls), 1, "a bad key must not be retried")

    def test_retries_are_bounded(self):

        with self.assertRaises(requests.HTTPError):
            self._run([self._http_error()] * 20)

        self.assertEqual(
            sum("API error" in m for m in self.logged),
            self.protocol_run.API_ERROR_MAX_RETRIES,
        )


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
            self.assertEqual(row["prompt_variant"], config.PROMPT_VARIANT)
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

    def test_resume_refuses_a_run_started_under_other_settings(self):

        model = llm_client.triage_model_id()

        def row(**overrides):
            base = {
                "memory_condition": "self",
                "model_id": model,
                "prompt_variant": config.PROMPT_VARIANT,
            }
            base.update(overrides)
            return base

        check = triage_runner.resume_mismatches

        self.assertEqual(check({}, "self"), [])
        self.assertEqual(check({"a": row()}, "self"), [])

        # Rows from before prompt_variant existed read as the first wording.
        legacy = row()
        del legacy["prompt_variant"]
        self.assertEqual(check({"a": legacy}, "self"), [])

        self.assertEqual(len(check({"a": row()}, "off")), 1)
        self.assertEqual(len(check({"a": row(model_id="some-other-model")}, "self")), 1)
        self.assertEqual(len(check({"a": row(prompt_variant="other-v9")}, "self")), 1)


if __name__ == "__main__":
    unittest.main()
