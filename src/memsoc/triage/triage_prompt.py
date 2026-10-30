"""
Prompt construction and response parsing for Phase 1 per-alert triage
(Arm A -- the memoryless baseline).

One alert in, one structured verdict out. This is deliberately NOT the
aggregate report in report_prompt.py: that module asks the LLM to write
narrative prose over pre-computed statistics for a whole run, and emits
no per-alert verdict. The memory layer stores *cases* -- one alert plus
the verdict and rationale it received (PROJECT_BRIEF.md section 4,
Layer 3) -- so Phase 2 needs exactly what this module produces.

What the prompt shows
---------------------
The detector's own output (predicted family, confidence, SHAP
attributions) plus the flow's actual NetFlow v3 feature values, joined
from the raw stream by triage_runner.py.

The feature values are not optional detail. An earlier revision showed
only SHAP attributions -- "MIN_TTL contributed +0.61" without ever
saying MIN_TTL was 31 -- and the model returned "inconclusive" on every
alert it saw, correctly, because an attribution without the value it
attributes to is not evidence. The layout follows the template in
docs/memory-layer/02-case-schema.md so that what Phase 2 embeds and what
Phase 1 reasons over describe the same flow the same way.

Two constraints are enforced structurally rather than by prompt wording
-------------------------------------------------------------------
1. No ground-truth label can reach the prompt. This module reads only
   detector output and flow features. It never opens ground_truth.csv,
   imports no CSV reader, and does not know that file exists.

2. No IP address reaches the prompt. Both live_results.jsonl and the raw
   stream carry addresses, but source IP predicts the attack label with
   100% accuracy on this dataset -- the same reason the detector's alert
   omits it and stats_engine.py refuses to report a source-IP statistic.
   Rendering one would hand the LLM an oracle and, in Phase 2, write
   that oracle into the memory store. build_alert_view() is the only
   path into the prompt and copies fields by explicit whitelist, so an
   address cannot arrive by accident.

The verdict vocabulary is fixed by docs/memory-layer/02-case-schema.md
("Triage output (Layer 4)") and is not invented here.
"""

import json

# ---------------------------------------------------------------------
# Closed vocabularies. Both come from existing project artifacts, not
# from this module: VERDICTS from the case schema doc, CATEGORIES from
# the frozen detector's own label set.
# ---------------------------------------------------------------------
VERDICTS = ("true_positive", "false_positive", "inconclusive")

DETECTOR_CATEGORIES = (
    "Analysis",
    "Backdoor",
    "DoS",
    "Exploits",
    "Fuzzers",
    "Generic",
    "Reconnaissance",
    "Shellcode",
)

# "none" for a flow the analyst judges benign, "unknown" when the
# evidence does not support naming a family. Both are required by the
# case schema.
ATTACK_CATEGORIES = DETECTOR_CATEGORIES + ("none", "unknown")

REQUIRED_RESPONSE_KEYS = (
    "verdict",
    "attack_category",
    "confidence",
    "rationale_summary",
)

RATIONALE_MAX_CHARS = 500

PROTOCOL_NAMES = {1: "ICMP", 6: "TCP", 17: "UDP"}

# Well-known ports only. Anything else renders as the bare number --
# inventing a service name for an ephemeral port would be noise.
PORT_NAMES = {
    20: "ftp-data", 21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp",
    53: "dns", 80: "http", 110: "pop3", 111: "rpcbind", 123: "ntp",
    143: "imap", 179: "bgp", 443: "https", 445: "smb", 993: "imaps",
    995: "pop3s", 1433: "mssql", 3306: "mysql", 3389: "rdp", 5432: "postgres",
}

# Standard TCP flag bits. The NF-* v3 schema stores TCP_FLAGS as a
# bitmask; "24" means nothing to a reader, "PSH,ACK" means a great deal.
TCP_FLAG_BITS = (
    (0x01, "FIN"), (0x02, "SYN"), (0x04, "RST"), (0x08, "PSH"),
    (0x10, "ACK"), (0x20, "URG"), (0x40, "ECE"), (0x80, "CWR"),
)

# The flow feature values rendered into the prompt, by explicit
# whitelist. Addresses are absent by construction -- see the module
# docstring. Anything not named here never reaches the LLM.
FLOW_FEATURES = (
    "L7_PROTO",
    "IN_BYTES", "IN_PKTS", "OUT_BYTES", "OUT_PKTS",
    "TCP_FLAGS", "CLIENT_TCP_FLAGS", "SERVER_TCP_FLAGS",
    "FLOW_DURATION_MILLISECONDS", "DURATION_IN", "DURATION_OUT",
    "MIN_TTL", "MAX_TTL",
    "LONGEST_FLOW_PKT", "SHORTEST_FLOW_PKT",
    "MIN_IP_PKT_LEN", "MAX_IP_PKT_LEN",
    "SRC_TO_DST_SECOND_BYTES", "DST_TO_SRC_SECOND_BYTES",
    "RETRANSMITTED_IN_BYTES", "RETRANSMITTED_IN_PKTS",
    "RETRANSMITTED_OUT_BYTES", "RETRANSMITTED_OUT_PKTS",
    "SRC_TO_DST_AVG_THROUGHPUT", "DST_TO_SRC_AVG_THROUGHPUT",
    "NUM_PKTS_UP_TO_128_BYTES", "NUM_PKTS_128_TO_256_BYTES",
    "NUM_PKTS_256_TO_512_BYTES", "NUM_PKTS_512_TO_1024_BYTES",
    "NUM_PKTS_1024_TO_1514_BYTES",
    "TCP_WIN_MAX_IN", "TCP_WIN_MAX_OUT",
    "ICMP_TYPE", "ICMP_IPV4_TYPE",
    "DNS_QUERY_TYPE", "DNS_TTL_ANSWER", "FTP_COMMAND_RET_CODE",
    "SRC_TO_DST_IAT_MIN", "SRC_TO_DST_IAT_MAX",
    "SRC_TO_DST_IAT_AVG", "SRC_TO_DST_IAT_STDDEV",
    "DST_TO_SRC_IAT_MIN", "DST_TO_SRC_IAT_MAX",
    "DST_TO_SRC_IAT_AVG", "DST_TO_SRC_IAT_STDDEV",
)

SHAP_IN_PROMPT = 8


def _num(value, precision=0):
    """
    Format one feature value for the prompt.

    Missing and non-finite values render as the literal "n/a" -- the
    NF-* v3 rate and throughput columns are null or infinite for
    zero-duration flows, and neither "inf" nor a formatter crash belongs
    in a prompt. Fixed precision per call site, per the rendering rules
    in docs/memory-layer/02-case-schema.md.
    """

    if value is None:
        return "n/a"

    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)

    if f != f or f in (float("inf"), float("-inf")):
        return "n/a"

    return f"{f:,.{precision}f}"


def _flags(mask):
    """Decode a TCP flag bitmask into names, e.g. 24 -> 'PSH,ACK (24)'."""

    if mask is None:
        return "n/a"

    try:
        bits = int(mask)
    except (TypeError, ValueError):
        return str(mask)

    names = [name for bit, name in TCP_FLAG_BITS if bits & bit]

    return f"{','.join(names) if names else 'none'} ({bits})"


def build_alert_view(record: dict, flow: dict = None) -> dict:
    """
    Reduce one captured detector record, plus its raw flow, to exactly
    the fields the prompt is allowed to see.

    This is the security boundary of the triage path. Fields present in
    either input but absent from the returned dict -- src_ip, dst_ip,
    id.orig_h, id.resp_h -- are excluded deliberately. Copying by
    whitelist rather than filtering at render time means the exclusion
    is testable and cannot be bypassed by a later edit to the template.

    `flow` may be None, in which case the feature block renders as
    unavailable rather than raising. That path is a degraded prompt, not
    a normal one; triage_runner.py refuses to run if the join fails.
    """

    alert = record.get("alert") or {}
    multiclass = record.get("multiclass") or {}
    flow = flow or {}

    protocol = alert.get("protocol")
    dst_port = alert.get("dst_port")

    return {
        "uid": record.get("uid"),
        "detector_label": multiclass.get("prediction"),
        "detector_score": multiclass.get("confidence"),
        "binary_confidence": record.get("binary_confidence"),
        "src_port": alert.get("src_port"),
        "dst_port": dst_port,
        "dst_port_name": PORT_NAMES.get(dst_port, str(dst_port)),
        "protocol": protocol,
        "protocol_name": PROTOCOL_NAMES.get(protocol, str(protocol)),
        "shap_explanation": (alert.get("shap_explanation") or [])[:SHAP_IN_PROMPT],
        "features": {k: flow.get(k) for k in FLOW_FEATURES},
        "has_flow": bool(flow),
    }


def _render_flow(f: dict) -> str:
    """
    The flow's own numbers, grouped the way an analyst reads them:
    volume, rate, packet shape, retransmission, timing, flags, then the
    protocol-specific fields.
    """

    return f"""  Volume        : {_num(f['IN_PKTS'])} in / {_num(f['OUT_PKTS'])} out packets, {_num(f['IN_BYTES'])} / {_num(f['OUT_BYTES'])} bytes
  Duration      : {_num(f['FLOW_DURATION_MILLISECONDS'])} ms total, {_num(f['DURATION_IN'])} in / {_num(f['DURATION_OUT'])} out
  Throughput    : {_num(f['SRC_TO_DST_AVG_THROUGHPUT'])} src->dst, {_num(f['DST_TO_SRC_AVG_THROUGHPUT'])} dst->src
  Bytes/sec     : {_num(f['SRC_TO_DST_SECOND_BYTES'], 1)} src->dst, {_num(f['DST_TO_SRC_SECOND_BYTES'], 1)} dst->src
  Packet size   : shortest {_num(f['SHORTEST_FLOW_PKT'])}, longest {_num(f['LONGEST_FLOW_PKT'])}, IP len {_num(f['MIN_IP_PKT_LEN'])}-{_num(f['MAX_IP_PKT_LEN'])}
  Size buckets  : <=128B {_num(f['NUM_PKTS_UP_TO_128_BYTES'])}, 128-256B {_num(f['NUM_PKTS_128_TO_256_BYTES'])}, 256-512B {_num(f['NUM_PKTS_256_TO_512_BYTES'])}, 512-1024B {_num(f['NUM_PKTS_512_TO_1024_BYTES'])}, 1024-1514B {_num(f['NUM_PKTS_1024_TO_1514_BYTES'])}
  Retransmitted : {_num(f['RETRANSMITTED_IN_PKTS'])} in / {_num(f['RETRANSMITTED_OUT_PKTS'])} out packets, {_num(f['RETRANSMITTED_IN_BYTES'])} / {_num(f['RETRANSMITTED_OUT_BYTES'])} bytes
  TTL           : min {_num(f['MIN_TTL'])}, max {_num(f['MAX_TTL'])}
  TCP flags     : combined {_flags(f['TCP_FLAGS'])}, client {_flags(f['CLIENT_TCP_FLAGS'])}, server {_flags(f['SERVER_TCP_FLAGS'])}
  TCP window    : max in {_num(f['TCP_WIN_MAX_IN'])}, max out {_num(f['TCP_WIN_MAX_OUT'])}
  IAT src->dst  : min {_num(f['SRC_TO_DST_IAT_MIN'])}, max {_num(f['SRC_TO_DST_IAT_MAX'])}, avg {_num(f['SRC_TO_DST_IAT_AVG'])}, stddev {_num(f['SRC_TO_DST_IAT_STDDEV'])}
  IAT dst->src  : min {_num(f['DST_TO_SRC_IAT_MIN'])}, max {_num(f['DST_TO_SRC_IAT_MAX'])}, avg {_num(f['DST_TO_SRC_IAT_AVG'])}, stddev {_num(f['DST_TO_SRC_IAT_STDDEV'])}
  L7 protocol   : {_num(f['L7_PROTO'], 1)}
  DNS / ICMP    : query type {_num(f['DNS_QUERY_TYPE'])}, TTL answer {_num(f['DNS_TTL_ANSWER'])}, ICMP type {_num(f['ICMP_TYPE'])}, ICMP IPv4 type {_num(f['ICMP_IPV4_TYPE'])}
  FTP return    : {_num(f['FTP_COMMAND_RET_CODE'])}"""


def _render_shap(shap_explanation, features) -> str:
    """
    SHAP attributions with each feature's actual value alongside.

    The value is the point. "MIN_TTL +0.6073" says the model leaned on
    the field; "MIN_TTL = 31 (+0.6073)" lets the reader judge whether it
    was right to.
    """

    if not shap_explanation:
        return "  (none reported)"

    lines = []

    for item in shap_explanation:
        name = item["feature"]
        value = _num(features.get(name), 1) if name in features else "n/a"
        lines.append(
            f"  {name:<28} = {value:>14}   contribution {item['shap_value']:+.4f}"
        )

    return "\n".join(lines)


def _render_precedents(precedents) -> str:
    """
    The retrieved past cases, as records rather than instructions.

    Format from docs/memory-layer/04-read-path.md, "Prompt injection
    format": most similar first, case ID and similarity shown, the
    stored verdict and its short rationale. Nothing here says whether
    the stored verdicts were right -- in the self condition they are the
    LLM's own unchecked conclusions, and whether they mislead is what
    the experiment measures.

    No precedents renders as the empty string, so the prompt is
    byte-identical to the Arm A prompt: silence, not a stated absence.

    One approved edit, 2026-10-30 (BL-170, protocol v4 pre-registration
    §8.2): the Attack category and Reasoning lines are printed only for
    a case that stores those fields. The label-free condition stores
    neither, so its cases show the alert, the verdict and the
    confidence. Every other condition stores both, so its prompt is
    unchanged byte for byte.
    """

    if not precedents:
        return ""

    blocks = []

    for case in sorted(precedents, key=lambda c: -c.similarity):

        m = case.metadata

        lines = [
            f"[Case {case.case_id} -- similarity {case.similarity:.2f}]",
            case.document,
            f"Verdict: {m.get('verdict')} (confidence {float(m.get('confidence', 0.0)):.2f})",
        ]

        if "attack_category" in m:
            lines.append(f"Attack category: {m.get('attack_category')}")

        if "rationale_summary" in m:
            lines.append(f"Reasoning: {m.get('rationale_summary') or '(none recorded)'}")

        blocks.append("\n".join(lines))

    return (
        "Relevant past cases from this SOC's records:\n\n"
        + "\n\n".join(blocks)
        + "\n\n"
    )


def render(record: dict, flow: dict = None, precedents=()) -> str:
    """
    Build the triage prompt for a single alert.

    LOCKED. Treat any edit as a schema change: verdicts produced under
    different wording are not comparable, and mixing them within or
    between arms puts an uncontrolled variable into the experiment.

    One approved edit, 2026-10-14 (BL-109): `precedents`, the memory
    layer's retrieved cases, render as a section before TASK. With none
    -- Arm A, and the first alert of every Arm B run -- the section is
    empty and the prompt is byte-identical to the pre-edit one;
    tests/test_triage_memory.py pins that with a hash.

    The wording is deliberately neutral about the detector's reliability.
    An earlier revision characterised it as strong on attack/benign and
    weaker on family -- accurate, but both halves of that claim were
    derived from measuring the detector against ground_truth.csv, which
    made the prompt a channel for oracle information (PROJECT_BRIEF.md
    section 5). Stating only what the detector itself outputs keeps the
    evaluation honest.

    For the same reason the prompt neither encourages nor discourages
    agreement with the detector. Whether the LLM merely echoes the
    detector's label is a property to be *measured* -- score_verdicts.py
    reports the agreement rate -- not one to be steered from here.
    """

    view = build_alert_view(record, flow)

    flow_block = (
        _render_flow(view["features"])
        if view["has_flow"]
        else "  (flow features unavailable for this alert)"
    )

    return f"""You are a SOC analyst triaging one alert raised by an automated network-intrusion detection model. Decide whether the alert is a genuine detection or a false alarm, and name the attack family if there is one.

The detector is an ML classifier. Its predicted family and confidence are its own output, reported below alongside the flow's measurements. Form your own assessment from the evidence; your conclusion may agree or disagree with it.

Base the decision on the measurements. Use "inconclusive" and "unknown" where the evidence genuinely does not support a call, rather than as a default.

ALERT {view['uid']}

Detector hypothesis : {view['detector_label']} (multiclass confidence {view['detector_score']})
Attack/benign score : {view['binary_confidence']}

Connection
  Destination port  : {view['dst_port']} ({view['dst_port_name']})
  Source port       : {view['src_port']}
  Transport         : {view['protocol_name']}

Flow measurements
{flow_block}

Model explanation (SHAP -- which features drove the prediction, with their values)
{_render_shap(view['shap_explanation'], view['features'])}

A positive contribution pushed the model toward its predicted family; a negative one pushed against it. These indicate which fields the model attended to; weigh the measurements themselves as well.

{_render_precedents(precedents)}TASK
Respond with ONLY a single valid JSON object -- no markdown code fences, no prose before or after it -- with exactly these keys:

{{
  "verdict": "<one of: true_positive | false_positive | inconclusive. true_positive = this is genuinely malicious traffic and the alert was warranted. false_positive = this is benign traffic and the alert was a false alarm. inconclusive = the measurements genuinely conflict.>",
  "attack_category": "<the attack family YOU conclude, one of: {' | '.join(DETECTOR_CATEGORIES)} | none | unknown. Use 'none' if you judged the flow benign. Use 'unknown' only if it is malicious but the family truly cannot be determined. This need not match the detector's hypothesis.>",
  "confidence": <a number between 0.0 and 1.0 -- your own confidence in this verdict, not the detector's>,
  "rationale_summary": "<at most 400 characters. State the measurements that decided it: the service and port, the specific flow numbers you weighted, and -- if you departed from the detector's hypothesis -- why.>"
}}
"""


def parse_llm_response(raw_text: str) -> dict:
    """
    Parse and validate the LLM's response into a verdict dict.

    Strips markdown fences an LLM might add despite instructions, then
    validates every field against its closed vocabulary. Anything that
    does not validate raises ValueError.

    Nothing here repairs, coerces to a default, or guesses. A fabricated
    verdict would be indistinguishable from a real one downstream, would
    be scored as if the LLM had produced it, and in Phase 2 would be
    embedded into the memory store and retrieved as precedent for later
    alerts. Failing loudly is the only safe behaviour.
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

    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):

        # Some models put the one verdict inside an array despite JSON
        # mode. The object inside is the model's own answer, field for
        # field; unwrapping it repairs nothing and guesses nothing, and
        # every validation below still applies to it. A list of any
        # other shape -- empty, several verdicts, or not objects -- is
        # still an answer we cannot attribute, and still fails.
        data = data[0]

    if not isinstance(data, dict):
        raise ValueError(
            f"LLM response was not a JSON object, got {type(data).__name__}.\n"
            f"Raw response:\n{raw_text}"
        )

    missing = [key for key in REQUIRED_RESPONSE_KEYS if key not in data]

    if missing:
        raise ValueError(
            f"LLM response missing required keys: {missing}\n"
            f"Raw response:\n{raw_text}"
        )

    verdict = data["verdict"]

    if verdict not in VERDICTS:
        raise ValueError(
            f"verdict {verdict!r} is not one of {VERDICTS}.\n"
            f"Raw response:\n{raw_text}"
        )

    category = data["attack_category"]

    if category not in ATTACK_CATEGORIES:
        raise ValueError(
            f"attack_category {category!r} is not one of {ATTACK_CATEGORIES}.\n"
            f"Raw response:\n{raw_text}"
        )

    try:
        confidence = float(data["confidence"])
    except (TypeError, ValueError):
        raise ValueError(
            f"confidence {data['confidence']!r} is not a number.\n"
            f"Raw response:\n{raw_text}"
        )

    if not 0.0 <= confidence <= 1.0:
        raise ValueError(
            f"confidence {confidence} is outside 0.0-1.0.\n"
            f"Raw response:\n{raw_text}"
        )

    rationale = data["rationale_summary"]

    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError(
            f"rationale_summary must be a non-empty string, got "
            f"{rationale!r}.\nRaw response:\n{raw_text}"
        )

    return {
        "verdict": verdict,
        "attack_category": category,
        "confidence": confidence,
        # Truncated to the case-schema limit. The full text would live in
        # the Phase 2 sidecar record; Phase 1 has no sidecar, so an
        # over-long rationale is cut here rather than rejected -- length
        # is a formatting matter, not a correctness one.
        "rationale_summary": rationale.strip()[:RATIONALE_MAX_CHARS],
    }
