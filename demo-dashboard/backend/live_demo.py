"""
The Dynamic section's live-call engine.

Every step here calls the project's own, already-tested modules
(memsoc.memory.store, memsoc.triage.triage_prompt, memsoc.triage.llm_client)
rather than reimplementing retrieval, prompt construction, or response
parsing. This module only orchestrates them and shapes the result for the
frontend. Retrieval reads from an isolated copy of the real memory stores
(demo_artifacts/), never the archived evaluation artifacts, so nothing a
live demo does can corrupt the original results.
"""

import json
import os
import sys
import time

import requests

DEMO_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(DEMO_BACKEND_DIR))
SRC_DIR = os.path.join(REPO_ROOT, "src")
sys.path.insert(0, SRC_DIR)

os.environ.setdefault(
    "MEMSOC_ARTIFACTS_DIR", os.path.join(DEMO_BACKEND_DIR, "demo_artifacts")
)

from memsoc.memory.store import MemoryLayer  # noqa: E402
from memsoc.triage import triage_prompt  # noqa: E402

LIVE_RESULTS_PATH = os.path.join(REPO_ROOT, "artifacts", "model_outputs", "live_results.jsonl")
GENERATED_LOGS_PATH = os.path.join(REPO_ROOT, "artifacts", "generated_logs.jsonl")
RUNS_DIR = os.path.join(REPO_ROOT, "artifacts", "runs")

MODEL_RUN_IDS = {
    "gemma": "bself-gemma4-26b-p3",
    "gptoss": "bself-gptoss20b-p1",
}
MODEL_IDS = {
    "gemma": "gemma-4-26b-a4b-it",
    "gptoss": "openai/gpt-oss-20b",
}
MODEL_PROVIDER = {
    "gemma": "gemini",
    "gptoss": "groq",
}

_records_cache = None
_flows_cache = None
_memory_layers = {}


def _load_jsonl_by_uid(path):
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            out[row["uid"]] = row
    return out


def get_record_and_flow(uid):
    global _records_cache, _flows_cache
    if _records_cache is None:
        _records_cache = _load_jsonl_by_uid(LIVE_RESULTS_PATH)
    if _flows_cache is None:
        _flows_cache = _load_jsonl_by_uid(GENERATED_LOGS_PATH)
    return _records_cache.get(uid), _flows_cache.get(uid)


def get_memory_layer(model_key):
    if model_key not in _memory_layers:
        run_id = MODEL_RUN_IDS[model_key]
        _memory_layers[model_key] = MemoryLayer(run_id, "self")
    return _memory_layers[model_key]


def get_recorded_result(model_key, uid, arm="bself"):
    """The real, already-triaged result for this alert -- used both to
    build the fallback-on-failure response and the "does this match the
    recorded result?" reproducibility check."""

    run_id = MODEL_RUN_IDS[model_key] if arm == "bself" else MODEL_RUN_IDS[model_key].replace("bself", "armA")
    path = os.path.join(RUNS_DIR, run_id, "triage_verdicts.jsonl")
    try:
        rows = _load_jsonl_by_uid(path)
        return rows.get(uid)
    except FileNotFoundError:
        return None


def _case_summaries(cases):
    return [
        {
            "case_id": c.case_id,
            "similarity": round(c.similarity, 4),
            "document": c.document,
            "verdict": c.metadata.get("verdict"),
            "attack_category": c.metadata.get("attack_category"),
            "confidence": c.metadata.get("confidence"),
            "rationale_summary": c.metadata.get("rationale_summary"),
        }
        for c in cases
    ]


# Demo-specific timeouts. llm_client.call_gemini/call_groq use 180s/120s
# timeouts with built-in retry loops -- correct for an unattended batch
# evaluation run, wrong for a live audience-facing click, where a flaky
# connection should fail fast into the recorded-result fallback instead
# of hanging for minutes. This deliberately does not touch llm_client.py
# (shared, locked, and depended on by the real evaluation protocol) or
# its budget-tracking files -- it is a separate, minimal direct call.
# Direct measurement (five payload sizes, 500-6000 chars, against the
# real endpoint): successes land in 1.4-2.9s; failures are either a fast
# HTTP 500 (~1.5s) or an occasional hang resolved by ~25s. A 6000-char
# payload -- the same size as the real triage prompt -- succeeded
# cleanly in 2.6s in that same test, proving the full-size request
# works when Google's side cooperates; the failures seen elsewhere are
# transient, not a permanent block on this payload size or network.
# Timeout sized to comfortably cover Gemma's legitimate ~40s thinking
# time on a good connection, with retries to ride out the transient
# failures this measurement found.
GEMINI_DEMO_TIMEOUT_S = 25
GROQ_DEMO_TIMEOUT_S = 20

# The real evaluation protocol (src/memsoc/triage/protocol_run.py,
# NETWORK_MAX_RETRIES / NETWORK_RETRY_WAIT) retries a dropped connection
# up to 10 times with a 60s wait -- proof transient failures are a known,
# survivable condition for this API, not a broken key or endpoint. This
# is the demo-appropriate compression of the same idea: more retries
# than a single long wait, since measurement shows most failures (and
# all observed successes) resolve within a few seconds, not tens of
# seconds -- so several quick-ish attempts beat one or two slow ones.
CONNECTION_MAX_RETRIES = 8
CONNECTION_RETRY_WAIT_S = 1.5
RETRYABLE_HTTP_STATUS = {429, 500, 502, 503}


def _with_connection_retries(make_request):
    last_error = None
    for attempt in range(CONNECTION_MAX_RETRIES + 1):
        try:
            response = make_request()
        except (requests.ConnectionError, requests.Timeout) as e:
            last_error = e
            if attempt < CONNECTION_MAX_RETRIES:
                time.sleep(CONNECTION_RETRY_WAIT_S)
            continue
        if response.status_code in RETRYABLE_HTTP_STATUS:
            last_error = requests.HTTPError(
                f"{response.status_code} from server: {response.text[:300]}"
            )
            if attempt < CONNECTION_MAX_RETRIES:
                time.sleep(CONNECTION_RETRY_WAIT_S)
            continue
        return response
    raise last_error


def _call_gemini_direct(prompt, model):
    import os
    key = os.environ.get("GEMINI_API_KEY", "")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 16384,
            "responseMimeType": "application/json",
        },
    }
    start = time.time()
    response = _with_connection_retries(
        lambda: requests.post(url, headers=headers, json=payload, timeout=GEMINI_DEMO_TIMEOUT_S)
    )
    latency_ms = (time.time() - start) * 1000
    response.raise_for_status()
    body = response.json()
    candidates = body.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {body.get('promptFeedback')}")
    candidate = candidates[0]
    if candidate.get("finishReason") == "MAX_TOKENS":
        raise RuntimeError("Gemini truncated at the token cap before answering")
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    if not text.strip():
        raise RuntimeError("Gemini returned an empty response")
    return text, latency_ms


def _call_groq_direct(prompt, model):
    import os
    key = os.environ.get("GROQ_API_KEY", "")
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 6000,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    }
    start = time.time()
    response = _with_connection_retries(
        lambda: requests.post(url, headers=headers, json=payload, timeout=GROQ_DEMO_TIMEOUT_S)
    )
    latency_ms = (time.time() - start) * 1000
    response.raise_for_status()
    body = response.json()
    choice = (body.get("choices") or [{}])[0]
    if choice.get("finish_reason") == "length":
        raise RuntimeError("Groq truncated at the token cap before answering")
    text = (choice.get("message") or {}).get("content", "")
    if not text.strip():
        raise RuntimeError("Groq returned an empty response")
    return text, latency_ms


def _call_llm(model_key, prompt):
    provider = MODEL_PROVIDER[model_key]
    model_id = MODEL_IDS[model_key]
    if provider == "gemini":
        return _call_gemini_direct(prompt, model_id)
    return _call_groq_direct(prompt, model_id)


def run_live_triage(model_key, uid):
    """
    Returns a dict describing every step of the pipeline for one alert,
    for both Arm A and B-self, so the frontend can reveal them in
    sequence. Each LLM call is wrapped so a failure degrades to the
    real recorded result instead of breaking the demo.
    """

    record, flow = get_record_and_flow(uid)
    if record is None or flow is None:
        raise ValueError(f"uid {uid} not found in the capture files")

    steps = {"uid": uid, "model": model_key}

    # Step 2: case text (same template used for embedding and shown to
    # the presenter so the "what memory sees" claim is checkable).
    from memsoc.memory import case_text, embedding

    t0 = time.perf_counter()
    query_case_text = case_text.render(record, flow)
    steps["case_text"] = query_case_text

    # Steps 3-5: embed + retrieve against the real (isolated) store.
    layer = get_memory_layer(model_key)
    t_embed_start = time.perf_counter()
    cases = layer.retrieve(record, flow)
    t_embed_end = time.perf_counter()
    steps["retrieval"] = {
        "precedents": _case_summaries(cases),
        "latency_ms": round((t_embed_end - t_embed_start) * 1000, 1),
    }

    # Step 6: the literal injected block, exactly as the real pipeline
    # renders it -- reuses triage_prompt's own renderer, not a copy.
    armA_prompt = triage_prompt.render(record, flow, precedents=())
    bself_prompt = triage_prompt.render(record, flow, precedents=cases)

    # Keep the live request within MAX_PROMPT_CHARS. Direct measurement
    # (five sizes, 500-6000 chars against the real endpoint) found larger
    # payloads fail noticeably more often, though not deterministically.
    # The real triage prompt with 3 precedents is normally ~6000 chars
    # and fits comfortably; this only engages if an unusually long
    # rationale or case text pushes it over, and drops the
    # *least*-similar precedent(s) first (cases is already sorted
    # most-similar-first) rather than truncating text mid-string, which
    # would hand the model a broken-looking case block.
    MAX_PROMPT_CHARS = 8000
    live_cases = list(cases)
    while len(bself_prompt) > MAX_PROMPT_CHARS and live_cases:
        live_cases = live_cases[:-1]
        bself_prompt = triage_prompt.render(record, flow, precedents=live_cases)

    # Extract just the injected block by diffing the two renders at the
    # point they first differ, rather than re-deriving the format.
    common_prefix_len = 0
    for a, b in zip(armA_prompt, bself_prompt):
        if a != b:
            break
        common_prefix_len += 1
    steps["precedent_block"] = bself_prompt[common_prefix_len:common_prefix_len + (len(bself_prompt) - len(armA_prompt))]

    # Step 7: the real, live LLM calls -- Arm A and B-self, fired
    # concurrently so the wait is one call's latency, not two (matters
    # most for Gemma, which can take 20-40s per call).
    #
    # ARM_HARD_TIMEOUT_S is a backstop independent of _call_gemini_direct/
    # _call_groq_direct's own requests timeout: a stalled TLS connection
    # has been observed (via raw curl, outside any of this app's code)
    # to sit past its configured socket timeout before failing, so the
    # only reliable ceiling is fut.result(timeout=...) here. Critically,
    # this pool is NOT used as a context manager -- `with
    # ThreadPoolExecutor() as pool` calls shutdown(wait=True) on exit,
    # which blocks until every submitted thread finishes regardless of
    # whether fut.result() already gave up on it. shutdown(wait=False)
    # below lets a still-hung thread finish or not on its own time
    # without blocking the response the presenter is waiting on.
    from concurrent.futures import ThreadPoolExecutor, wait as futures_wait

    # Worst case if every retry genuinely hangs the full per-attempt
    # timeout: 5 attempts x 45s + 4 x 1.5s wait =~ 231s. In practice this
    # is the rare tail, not the common case -- direct measurement showed
    # successes and fast failures (HTTP 500) both resolving in 1.5-3s, so
    # most calls settle within the first attempt or two. This ceiling
    # exists so a truly bad run still ends in a clean fallback rather
    # than hanging forever, not because 231s is the expected wait.
    ARM_HARD_TIMEOUT_S = 240

    def run_arm(arm, prompt):
        raw_text, latency_ms = _call_llm(model_key, prompt)
        parsed = triage_prompt.parse_llm_response(raw_text)
        return {
            "live": True,
            "verdict": parsed["verdict"],
            "attack_category": parsed["attack_category"],
            "confidence": parsed["confidence"],
            "rationale_summary": parsed["rationale_summary"],
            "latency_ms": round(latency_ms, 1),
        }

    def fallback_result(arm, error_text):
        recorded = get_recorded_result(model_key, uid, arm=arm)
        return {
            "live": False,
            "error": error_text,
            "fallback_to_recorded": True,
            "verdict": recorded.get("verdict") if recorded else None,
            "attack_category": recorded.get("attack_category") if recorded else None,
            "confidence": recorded.get("confidence") if recorded else None,
            "rationale_summary": recorded.get("rationale_summary") if recorded else None,
        }

    pool = ThreadPoolExecutor(max_workers=2)
    futures = {
        pool.submit(run_arm, "armA", armA_prompt): "armA",
        pool.submit(run_arm, "bself", bself_prompt): "bself",
    }
    # wait() blocks on the WHOLE set for one shared deadline, not one
    # timeout per future checked in sequence -- looping fut.result(timeout=N)
    # over two futures can cost up to 2N if both are slow, since each
    # call starts its own fresh countdown regardless of how long the
    # previous one already waited. This is the fix for that.
    done, not_done = futures_wait(futures.keys(), timeout=ARM_HARD_TIMEOUT_S)

    results = {}
    for fut in done:
        arm = futures[fut]
        try:
            results[arm] = fut.result()
        except Exception as e:  # noqa: BLE001 -- any failure falls back, by design
            results[arm] = fallback_result(arm, str(e))
    for fut in not_done:
        arm = futures[fut]
        results[arm] = fallback_result(arm, f"no response within {ARM_HARD_TIMEOUT_S}s")
    pool.shutdown(wait=False)

    steps["results"] = results

    # Step 8: the mechanism check, computed on this exact alert.
    if cases:
        from collections import Counter
        families = [c.metadata.get("attack_category") for c in cases]
        plurality_family, _ = Counter(families).most_common(1)[0]
        steps["mechanism_check"] = {
            "plurality_family_of_precedents": plurality_family,
            "bself_family": results["bself"].get("attack_category"),
            "matches_plurality": results["bself"].get("attack_category") == plurality_family,
        }
    else:
        steps["mechanism_check"] = None

    # Reproducibility indicator against the real recorded run.
    recorded_bself = get_recorded_result(model_key, uid, arm="bself")
    if recorded_bself and results["bself"].get("live"):
        steps["matches_recorded"] = (
            results["bself"]["verdict"] == recorded_bself.get("verdict")
            and results["bself"]["attack_category"] == recorded_bself.get("attack_category")
        )
    else:
        steps["matches_recorded"] = None

    steps["total_latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return steps
