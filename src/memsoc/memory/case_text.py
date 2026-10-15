"""
The embedding text for one alert -- what decides "similar" in memory.

render() is the only implementation. The read path renders the incoming
alert with it and the write path renders the stored case with it, so
query and document are the same shape by construction (the symmetry
requirement, docs/memory-layer/02-case-schema.md).

Template 1.0 -- alert-only text plus the detector's top-3 SHAP feature
names, raw numbers. Chosen 2026-10-13 from the measurements in
docs/memory-layer/retrieval-precision-investigation.md section 3, where
it was the best of four variants on the detector's own errors.

What is deliberately NOT in the text
------------------------------------
- The detector's label and score. Adding them raised the overall match
  rate and collapsed it on the alerts the detector got wrong -- the
  population memory exists to help with (decisions.md C1).
- The LLM's verdict or rationale. A new alert has none yet, so query
  and document would be different shapes (investigation section 4.3).
  Verdicts are stored as metadata and shown to the LLM; they do not
  decide the match.
- IP addresses. Source IP predicts the attack label perfectly on this
  dataset (triage_prompt.py module docstring); embedding it would make
  retrieval an oracle.
- Timestamps. Attack families cluster in capture windows, so time
  leaks the label too (02-case-schema.md, Network context).
- Any ground-truth field. This module never reads ground_truth.csv.

Rendering rules
---------------
Fixed field order, fixed labels, every line always present, fixed
precision, non-finite values as "n/a". Any change to this template --
a field, a label, a rounding -- is a SCHEMA_VERSION bump and a new
store (02-case-schema.md, Schema versioning).

The protocol, port and flag tables are copied here on purpose rather
than imported from triage. The case text must not change because
another layer's prompt code changed.
"""

import math


SCHEMA_VERSION = "1.0"

SHAP_FEATURES_IN_TEXT = 3

PROTOCOL_NAMES = {1: "ICMP", 6: "TCP", 17: "UDP"}

PORT_NAMES = {
    20: "ftp-data", 21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp",
    53: "dns", 80: "http", 110: "pop3", 111: "rpcbind", 123: "ntp",
    143: "imap", 179: "bgp", 443: "https", 445: "smb", 993: "imaps",
    995: "pop3s", 1433: "mssql", 3306: "mysql", 3389: "rdp", 5432: "postgres",
}

TCP_FLAG_BITS = (
    (0x01, "FIN"), (0x02, "SYN"), (0x04, "RST"), (0x08, "PSH"),
    (0x10, "ACK"), (0x20, "URG"), (0x40, "ECE"), (0x80, "CWR"),
)


def _num(value, precision=0) -> str:
    """One number, fixed precision, no thousands separator."""

    if value is None:
        return "n/a"

    try:
        f = float(value)
    except (TypeError, ValueError):
        return "n/a"

    if not math.isfinite(f):
        return "n/a"

    return f"{f:.{precision}f}"


def _flags(mask) -> str:
    """A TCP flag bitmask as names, e.g. 24 -> 'PSH ACK'."""

    if mask is None:
        return "n/a"

    try:
        bits = int(mask)
    except (TypeError, ValueError):
        return "n/a"

    names = [name for bit, name in TCP_FLAG_BITS if bits & bit]

    return " ".join(names) if names else "none"


def top_shap_features(alert: dict) -> list:
    """
    The detector's top SHAP feature names, strongest first.

    Sorted by absolute contribution, ties kept in the detector's own
    order, so the result does not depend on how the list arrived.
    """

    explanation = alert.get("shap_explanation") or []

    ranked = sorted(
        enumerate(explanation),
        key=lambda pair: (-abs(pair[1]["shap_value"]), pair[0]),
    )

    return [item["feature"] for _, item in ranked[:SHAP_FEATURES_IN_TEXT]]


def render(record: dict, flow: dict) -> str:
    """
    The embedding text for one detector-flagged alert.

    `record` is one line of live_results.jsonl; `flow` is the matching
    line of generated_logs.jsonl, joined on uid. A missing alert block or
    missing flow raises: embedding a degraded text would put a case in
    memory that matches nothing it should.
    """

    alert = record.get("alert")

    if not alert:
        raise ValueError(
            f"record {record.get('uid')} has no alert block; only "
            f"detector-flagged alerts become cases"
        )

    if not flow:
        raise ValueError(
            f"record {record.get('uid')} has no joined flow; refusing to "
            f"render a case without its measurements"
        )

    protocol = alert.get("protocol")
    dst_port = alert.get("dst_port")

    transport = PROTOCOL_NAMES.get(protocol, _num(protocol))
    service = PORT_NAMES.get(dst_port, "unnamed")
    key_features = ", ".join(top_shap_features(alert)) or "none"

    f = flow

    lines = [
        f"{transport} to port {_num(dst_port)} ({service}), L7 protocol {_num(f.get('L7_PROTO'), 1)}",
        f"Volume: {_num(f.get('IN_PKTS'))} in / {_num(f.get('OUT_PKTS'))} out packets, {_num(f.get('IN_BYTES'))} / {_num(f.get('OUT_BYTES'))} bytes",
        f"Duration: {_num(f.get('FLOW_DURATION_MILLISECONDS'))} ms",
        f"Throughput: {_num(f.get('SRC_TO_DST_AVG_THROUGHPUT'))} src to dst, {_num(f.get('DST_TO_SRC_AVG_THROUGHPUT'))} dst to src",
        f"Packet size: shortest {_num(f.get('SHORTEST_FLOW_PKT'))}, longest {_num(f.get('LONGEST_FLOW_PKT'))}",
        f"Retransmitted: {_num(f.get('RETRANSMITTED_IN_PKTS'))} in / {_num(f.get('RETRANSMITTED_OUT_PKTS'))} out packets",
        f"TTL: min {_num(f.get('MIN_TTL'))}, max {_num(f.get('MAX_TTL'))}",
        f"TCP flags: client {_flags(f.get('CLIENT_TCP_FLAGS'))}, server {_flags(f.get('SERVER_TCP_FLAGS'))}",
        f"Key features: {key_features}",
    ]

    return "\n".join(lines)
