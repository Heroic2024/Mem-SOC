"""
Prompt construction and response parsing for the Stage 4 aggregate
security report.

The LLM is given ONLY the pre-computed statistics and ranked findings
produced by stats_engine.py -- it never sees the raw stream and never
computes a number itself. Its job is interpretation, prioritization, and
natural-language writing over numbers that are already verified. This is
enforced structurally: this module cannot add a statistic to the prompt
that stats_engine.py did not compute, and parse_llm_response() below
extracts only free-text/narrative fields from the response, never a
number that would need to match a stat -- the numeric tables in the
final report are rendered directly from stats_engine.py's output in
generate_report.py, not from anything the LLM returns.
"""

import json

REQUIRED_RESPONSE_KEYS = (
    "executive_summary",
    "security_overview",
    "risk_analysis",
    "threat_analysis",
    "recommendations",
    "prioritized_action_plan",
    "conclusion",
)


def render(stats: dict, findings_sample: list) -> str:
    """
    Build the report-writing prompt from verified statistics and a
    ranked sample of the highest-risk findings (both from
    stats_engine.py). `findings_sample` is deliberately a subset -- the
    full findings list still appears in the final report, rendered
    directly from data, not through the LLM.
    """

    stats_json = json.dumps(stats, indent=2)
    findings_json = json.dumps(findings_sample, indent=2)

    return f"""You are a senior SOC (Security Operations Center) analyst writing a security report for one network-intrusion-detection run. You are given VERIFIED, PROGRAMMATICALLY-COMPUTED statistics and a ranked sample of the highest-risk findings from this run. These numbers were computed directly from the detection model's outputs before you saw them -- they are ground truth, not something you produce.

CRITICAL RULE: Use ONLY the numbers given below. Do not invent, estimate, recompute, round differently, or introduce any count, percentage, or score that is not explicitly present in the data below. Every figure you cite must come from this data. Your job is interpretation, prioritization, and clear writing -- not arithmetic.

VERIFIED STATISTICS
{stats_json}

TOP-RISK FINDINGS (sample, ranked by computed risk_score; risk_score = detector_confidence x a fixed severity weight per attack category)
{findings_json}

TASK
Respond with ONLY a single valid JSON object -- no markdown code fences, no prose before or after it -- with exactly these keys:

{{
  "executive_summary": "<3-5 sentences, non-technical, for leadership: what happened in this run and how serious it is. Must cite attack_rate_pct and overall_risk_level from the data above.>",
  "security_overview": "<a paragraph describing the traffic processed and the attack/benign split, protocol distribution, and confidence distribution, citing the real figures above>",
  "risk_analysis": "<a paragraph interpreting category_breakdown -- which attack categories carry the most risk and why, referencing their risk_score and risk_level fields>",
  "threat_analysis": "<a paragraph analyzing attack patterns: what top_targeted_ports and top_shap_indicators suggest about attacker behaviour, and how the findings sample illustrates this>",
  "recommendations": ["<specific, actionable recommendation grounded in the data above>", "..."],
  "prioritized_action_plan": ["<step 1 -- highest priority first, tied to a specific category or finding above>", "<step 2>", "..."],
  "conclusion": "<2-3 sentence closing summary>"
}}
"""


def parse_llm_response(raw_text: str) -> dict:
    """
    Parse the LLM's response into the expected narrative dict.

    Strips common wrapping (markdown code fences) an LLM might add
    despite instructions, then requires all REQUIRED_RESPONSE_KEYS to be
    present. Raises ValueError on anything else -- a malformed response
    is rejected, not silently repaired or guessed at.
    """

    text = raw_text.strip()

    if text.startswith("```"):

        text = text.strip("`")

        if text.lower().startswith("json"):
            text = text[4:]

        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM response was not valid JSON: {e}\nRaw response:\n{raw_text}"
        )

    missing = [key for key in REQUIRED_RESPONSE_KEYS if key not in data]

    if missing:
        raise ValueError(
            f"LLM response missing required keys: {missing}\n"
            f"Raw response:\n{raw_text}"
        )

    return data
