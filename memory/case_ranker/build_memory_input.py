"""
Builds a compact, metrics-only, <=256-token digest of the most
critical/severe attacks -- from the existing detection model's own
captured outputs, never from the raw log stream.

Input:  LLMTriage/model_outputs/live_results.jsonl
        (written by LLMTriage/live_capture.py; the model's real
        status/binary/multiclass/alert response per flow)

Output: memory/case_ranker/outputs/memory_input_<timestamp>.json
        Full structured record: every ranked candidate, which ones
        were included vs dropped for budget, and the exact compact
        text with its estimated token count.

        memory/case_ranker/outputs/memory_input_<timestamp>.txt
        Just the compact text -- the literal string meant to be handed
        to the embedding step later.

This script does NOT call an embedding model, does NOT touch ChromaDB,
and does NOT write to any memory store -- those remain future work per
docs/memory-layer/. Its only job is: read model output, rank by
severity, select the highest-ranking cases, and compress them into an
embedding-ready, metrics-only string within the token budget.

Usage:
    python build_memory_input.py                 # rank everything captured so far
    python build_memory_input.py --limit 500      # only the 500 most recently captured flows
"""

import argparse
import json
import sys
from datetime import datetime, timezone

import config
import risk
from token_estimator import estimate_tokens


def read_live_results(path, limit=None):
    """
    Same read-only, skip-malformed-lines approach as
    LLMTriage/stats_engine.py's read_live_results() -- duplicated
    rather than imported to keep this component self-contained (see
    risk.py's module docstring for why).
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


def rank_attacks(results):
    """
    Every DISTINCT attack flow (deduplicated by uid), scored and sorted
    highest-risk first. Uses the exact same risk_score formula as
    LLMTriage/stats_engine.py's build_findings(), so "critical" is
    consistent project-wide.

    Deduplication matters specifically here: live_capture.py --loop
    wraps and re-replays the same stream, so the same uid can appear
    more than once in live_results.jsonl. Without deduplication, a
    repeated flow would occupy multiple ranked slots and crowd out a
    genuinely different case within the token budget -- the same
    near-duplicate-saturation risk already documented in
    docs/memory-layer/04-read-path.md. First occurrence wins; later
    repeats of the same uid carry identical data anyway.
    """

    seen = {}

    for r in results:

        if r.get("status") != "attack" or not r.get("alert") or not r.get("multiclass"):
            continue

        uid = r["uid"]

        if uid in seen:
            continue

        category = r["multiclass"]["prediction"]
        confidence = r["multiclass"]["confidence"]
        score = risk.risk_score(confidence, category)

        shap = [
            (item["feature"], item["shap_value"])
            for item in (r["alert"].get("shap_explanation") or [])[: config.SHAP_TOP_K]
        ]

        seen[uid] = {
            "uid": uid,
            "category": category,
            "confidence": confidence,
            "risk_score": score,
            "risk_level": risk.risk_level(score),
            "dst_port": r["alert"]["dst_port"],
            "protocol": risk.PROTOCOL_NAMES.get(
                r["alert"]["protocol"], str(r["alert"]["protocol"])
            ),
            "shap": shap,
        }

    ranked = list(seen.values())
    ranked.sort(key=lambda f: f["risk_score"], reverse=True)

    return ranked


def build_header(results, ranked):
    """
    One compact line of pure aggregate numbers -- flows considered,
    attack count/rate, overall risk level, and the severity
    distribution across every ranked attack (not just the ones that
    end up fitting the token budget below).
    """

    total = len(results)
    attack_count = len(ranked)
    attack_rate = round((attack_count / total) * 100, 2) if total else 0.0

    severity_counts = {level: 0 for level in risk.SEVERITY_ORDER}
    for case in ranked:
        severity_counts[case["risk_level"]] += 1

    overall_risk = "None"
    for level in risk.SEVERITY_ORDER:
        if severity_counts[level] > 0:
            overall_risk = level
            break

    sev_str = "/".join(
        f"{level[0]}{severity_counts[level]}" for level in risk.SEVERITY_ORDER
    )

    header_line = (
        f"FLOWS={total} ATTACKS={attack_count} RATE={attack_rate}% "
        f"RISK={overall_risk} SEV={sev_str}"
    )

    summary = {
        "total_flows": total,
        "attack_count": attack_count,
        "attack_rate_pct": attack_rate,
        "overall_risk_level": overall_risk,
        "severity_distribution": severity_counts,
    }

    return header_line, summary


def format_case_line(rank_num, case):
    """
    One dense line per selected case: identifier, category, severity,
    scores, network context, and top SHAP features -- numbers and
    closed-vocabulary labels only, no prose.
    """

    shap_str = ",".join(f"{feature}:{value:.4f}" for feature, value in case["shap"])

    return (
        f"#{rank_num} id={case['uid']} cat={case['category']} "
        f"sev={case['risk_level']} risk={case['risk_score']} "
        f"conf={case['confidence']} port={case['dst_port']} "
        f"proto={case['protocol']} shap=[{shap_str}]"
    )


def pack_within_budget(header_line, ranked, effective_budget):
    """
    Greedily add ranked cases, highest risk first, stopping the moment
    the next case would push the digest over budget. A case is either
    fully included or fully dropped -- never truncated mid-line -- so
    the output is always syntactically complete.
    """

    lines = [header_line]
    included = []

    for i, case in enumerate(ranked, start=1):

        line = format_case_line(i, case)
        candidate = "\n".join(lines + [line])

        if estimate_tokens(candidate) > effective_budget:
            break

        lines.append(line)
        included.append(case)

    dropped = len(ranked) - len(included)

    return "\n".join(lines), included, dropped


def main():

    parser = argparse.ArgumentParser(
        description="Rank the most critical attacks from the model's own "
                    "captured output and compact them into a <=256-token, "
                    "metrics-only digest for the memory layer's eventual "
                    "embedding step."
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Only use the N most recently captured flows "
             "(default: everything captured so far)"
    )
    args = parser.parse_args()

    if not config.LIVE_RESULTS_PATH.exists():
        print(
            f"No captured model outputs found at {config.LIVE_RESULTS_PATH}.\n"
            "Run LLMTriage/live_capture.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    results = read_live_results(config.LIVE_RESULTS_PATH, args.limit)

    if not results:
        print(
            f"{config.LIVE_RESULTS_PATH} exists but has no usable records yet.",
            file=sys.stderr,
        )
        sys.exit(1)

    ranked = rank_attacks(results)
    header_line, summary = build_header(results, ranked)

    effective_budget = config.TOKEN_BUDGET - config.SAFETY_MARGIN

    digest_text, included, dropped = pack_within_budget(
        header_line, ranked, effective_budget
    )
    token_count = estimate_tokens(digest_text)

    print(
        f"Ranked {len(ranked)} attacks from {len(results)} flows; "
        f"included {len(included)}, dropped {dropped} to stay within the "
        f"{config.TOKEN_BUDGET}-token budget "
        f"(estimated {token_count} tokens, effective budget {effective_budget})."
    )

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(config.LIVE_RESULTS_PATH),
        "flows_considered": len(results),
        "token_budget": config.TOKEN_BUDGET,
        "safety_margin": config.SAFETY_MARGIN,
        "estimated_tokens": token_count,
        "summary": summary,
        "candidates_ranked": len(ranked),
        "candidates_included": len(included),
        "candidates_dropped_for_budget": dropped,
        "included_case_ids": [c["uid"] for c in included],
        "embedding_input_text": digest_text,
    }

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    json_path = config.OUTPUT_DIR / f"memory_input_{timestamp}.json"
    txt_path = config.OUTPUT_DIR / f"memory_input_{timestamp}.txt"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(digest_text)

    print(f"\nWrote {json_path}")
    print(f"Wrote {txt_path}")


if __name__ == "__main__":
    main()
