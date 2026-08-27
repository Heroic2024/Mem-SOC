"""
Stage 4 statistics engine.

This module contains every quantitative computation that appears in the
final security report. It makes NO network calls of any kind -- it does
not talk to the detection API and does not read
log_generation/generated_logs.jsonl. Running the model is live_capture.py's
job exclusively; this module only reads whatever live_capture.py has
already written to model_outputs/live_results.jsonl and does plain
Python aggregation over it.

No LLM is involved anywhere in this file either. Every count,
percentage, and score the report presents as a "verified statistic" is
produced here. The LLM (see report_prompt.py) only ever receives the
dictionaries this module returns -- it never computes them.
"""

import json
from collections import Counter, defaultdict

PROTOCOL_NAMES = {6: "TCP", 17: "UDP", 1: "ICMP"}

# ---------------------------------------------------------------------
# Risk scoring
# ---------------------------------------------------------------------
#
# This is a fixed, documented heuristic -- not a measured ground-truth
# statistic and not something the LLM is asked to invent. It follows
# standard NIDS severity convention: categories implying persistence or
# code execution outweigh reconnaissance/probing categories. Anyone
# auditing the report can see exactly how a risk_score was produced from
# risk_score(confidence, category) below, and adjust the weights here if
# the project wants a different convention -- it is a single, visible
# table, not logic buried in a prompt.
SEVERITY_WEIGHTS = {
    "Worms": 1.00,
    "Backdoor": 1.00,
    "Shellcode": 0.95,
    "Exploits": 0.90,
    "DoS": 0.80,
    "Fuzzers": 0.55,
    "Reconnaissance": 0.50,
    "Analysis": 0.50,
    "Generic": 0.40,
}
DEFAULT_SEVERITY_WEIGHT = 0.50

RISK_THRESHOLDS = (
    (0.70, "Critical"),
    (0.50, "High"),
    (0.30, "Medium"),
    (0.00, "Low"),
)


def risk_score(confidence: float, category: str) -> float:
    weight = SEVERITY_WEIGHTS.get(category, DEFAULT_SEVERITY_WEIGHT)
    return round(confidence * weight, 4)


def risk_level(score: float) -> str:
    for threshold, label in RISK_THRESHOLDS:
        if score >= threshold:
            return label
    return "Low"


# ---------------------------------------------------------------------
# Step 1 -- read whatever live_capture.py has already written. This is
# the ONLY way results reach this module: no API call, no file replay.
# ---------------------------------------------------------------------
def read_live_results(path, limit=None):
    """
    Read every valid line from live_results.jsonl.

    A line that fails to parse is skipped rather than raised on -- the
    only realistic cause is live_capture.py being mid-write on the very
    last line while this runs concurrently with it, and a report
    snapshot should not crash because of a single in-flight write.

    `limit`, if given, keeps only the `limit` most recently captured
    flows (the file is append-only in capture order, so this is a tail).
    """

    results = []

    with open(path, "r", encoding="utf-8") as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if limit is not None:
        results = results[-limit:]

    return results


# ---------------------------------------------------------------------
# Step 2 -- aggregate statistics. Every value below is derived directly
# from `results`; nothing is estimated or assumed.
# ---------------------------------------------------------------------
def compute_statistics(results):

    total = len(results)
    attacks = [r for r in results if r["status"] == "attack"]
    benign = [r for r in results if r["status"] == "benign"]

    attack_count = len(attacks)
    benign_count = len(benign)
    attack_rate_pct = round((attack_count / total) * 100, 2) if total else 0.0

    category_counter = Counter(
        a["multiclass"]["prediction"] for a in attacks if a.get("multiclass")
    )

    category_confidences = defaultdict(list)
    for a in attacks:
        if a.get("multiclass"):
            category_confidences[a["multiclass"]["prediction"]].append(
                a["multiclass"]["confidence"]
            )

    category_breakdown = []
    for category, count in category_counter.most_common():
        confidences = category_confidences[category]
        avg_conf = round(sum(confidences) / len(confidences), 4)
        score = risk_score(avg_conf, category)
        category_breakdown.append({
            "category": category,
            "count": count,
            "pct_of_attacks": round((count / attack_count) * 100, 2) if attack_count else 0.0,
            "avg_confidence": avg_conf,
            "severity_weight": SEVERITY_WEIGHTS.get(category, DEFAULT_SEVERITY_WEIGHT),
            "risk_score": score,
            "risk_level": risk_level(score),
        })

    category_breakdown.sort(key=lambda c: c["risk_score"], reverse=True)

    # Protocol distribution is read from the model's own alert output
    # (alert.protocol), not from the raw log envelope's "proto" string --
    # the model does emit protocol, so there's no reason to fall back to
    # the log for it.
    protocol_counter = Counter(
        PROTOCOL_NAMES.get(a["alert"]["protocol"], str(a["alert"]["protocol"]))
        for a in attacks if a.get("alert")
    )

    dst_port_counter = Counter(
        a["alert"]["dst_port"] for a in attacks if a.get("alert")
    )

    # No top_source_ips statistic: the model's alert never includes an IP
    # address by deliberate design (memory/SCHEMA_DESIGN.md B9 -- source
    # IP predicts the attack label with 100% accuracy on this dataset, so
    # it is excluded from the alert to avoid leaking an oracle). Since
    # the model itself never outputs an IP, no "source IP" statistic can
    # legitimately be presented as a model-derived finding here.

    # Aggregate SHAP indicator frequency across every attack alert -- how
    # often each feature appears in an alert's own top-5 explanation.
    shap_counter = Counter()
    for a in attacks:
        alert = a.get("alert") or {}
        for item in (alert.get("shap_explanation") or [])[:5]:
            shap_counter[item["feature"]] += 1

    confidence_buckets = Counter()
    for a in attacks:
        conf = (a.get("multiclass") or {}).get("confidence")
        if conf is None:
            continue
        if conf >= 0.9:
            confidence_buckets["0.9-1.0"] += 1
        elif conf >= 0.7:
            confidence_buckets["0.7-0.9"] += 1
        elif conf >= 0.5:
            confidence_buckets["0.5-0.7"] += 1
        else:
            confidence_buckets["<0.5"] += 1

    return {
        "total_flows_processed": total,
        "benign_count": benign_count,
        "attack_count": attack_count,
        "attack_rate_pct": attack_rate_pct,
        "distinct_attack_categories": len(category_counter),
        "category_breakdown": category_breakdown,
        "protocol_distribution": dict(protocol_counter),
        "top_targeted_ports": dst_port_counter.most_common(10),
        "top_shap_indicators": shap_counter.most_common(10),
        "confidence_distribution": dict(confidence_buckets),
        "overall_risk_level": (
            category_breakdown[0]["risk_level"] if category_breakdown else "None"
        ),
    }


# ---------------------------------------------------------------------
# Step 3 -- detailed, per-alert findings, ranked by risk. Every field is
# copied straight from the detector's own response.
# ---------------------------------------------------------------------
def build_findings(results, max_findings):

    findings = []

    for r in results:

        if r["status"] != "attack" or not r.get("alert") or not r.get("multiclass"):
            continue

        category = r["multiclass"]["prediction"]
        confidence = r["multiclass"]["confidence"]
        score = risk_score(confidence, category)

        findings.append({
            "uid": r["uid"],
            "dst_port": r["alert"]["dst_port"],
            "protocol": PROTOCOL_NAMES.get(
                r["alert"]["protocol"], str(r["alert"]["protocol"])
            ),
            "category": category,
            "confidence": confidence,
            "risk_score": score,
            "risk_level": risk_level(score),
            "top_indicators": [
                item["feature"]
                for item in (r["alert"].get("shap_explanation") or [])[:3]
            ],
        })

    findings.sort(key=lambda f: f["risk_score"], reverse=True)

    return findings[:max_findings]
