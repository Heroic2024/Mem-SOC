"""
Severity/risk scoring.

Intentionally MIRRORS LLMTriage/stats_engine.py's SEVERITY_WEIGHTS and
risk_score()/risk_level() methodology exactly, so "critical" means the
same thing everywhere in this project. Duplicated here rather than
cross-imported so this component stays self-contained and independent
of LLMTriage's internals -- the same pattern already used elsewhere in
this repo (log_generation/nfv3_log_generator.py's eligibility check is
a documented independent re-implementation of the same finiteness rule
final_ml_model_v1's inference pipeline enforces, not a shared import;
see log_generation/README.md).

If SEVERITY_WEIGHTS or RISK_THRESHOLDS ever change, update both this
file and LLMTriage/stats_engine.py together.
"""

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

SEVERITY_ORDER = ["Critical", "High", "Medium", "Low"]

PROTOCOL_NAMES = {6: "TCP", 17: "UDP", 1: "ICMP"}


def risk_score(confidence: float, category: str) -> float:
    weight = SEVERITY_WEIGHTS.get(category, DEFAULT_SEVERITY_WEIGHT)
    return round(confidence * weight, 4)


def risk_level(score: float) -> str:
    for threshold, label in RISK_THRESHOLDS:
        if score >= threshold:
            return label
    return "Low"
