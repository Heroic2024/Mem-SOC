"""
Curated shortlist of alerts for the Dynamic section's live-demo picker.

Each entry is deliberately chosen to tell a clear story when run live,
rather than exposing all 165 alerts (most of which are not illustrative
on their own). `uid` must exist in both artifacts/model_outputs/live_results.jsonl
and artifacts/generated_logs.jsonl so the real alert + flow can be
reconstructed and rendered exactly as the evaluated pipeline rendered it.
"""

GEMMA_RUN_ID = "bself-gemma4-26b-p3"
GPTOSS_RUN_ID = "bself-gptoss20b-p1"

DEMO_ALERTS = {
    "gemma": [
        {
            "uid": "C1424223317312-51709-285",
            "seq": 3,
            "label": "Alert 4 — the report's own worked example",
            "note": (
                "Arm A names this correctly as Exploits. B-self's most similar "
                "precedent (0.99 similarity) was stored as Fuzzers, and the "
                "model follows it — this is the exact copying mechanism "
                "Section 4.4.4 documents, reproduced live."
            ),
        },
        {
            "uid": "C1424256835752-64848-703",
            "seq": 8,
            "label": "The harm, repeated",
            "note": (
                "Arm A correctly names Exploits; B-self again copies a "
                "retrieved Fuzzers label and gets it wrong — shows the "
                "pattern is not a one-off."
            ),
        },
        {
            "uid": "C1421928595670-59362-768",
            "seq": 9,
            "label": "Where memory actually helps",
            "note": (
                "Arm A dismisses this alert entirely (wrong); B-self's "
                "retrieved precedents correctly flag it as Fuzzers — one "
                "of only 5 alerts in the whole run where memory fixed an "
                "Arm A mistake."
            ),
        },
        {
            "uid": "C1421928105613-16373-3693",
            "seq": 32,
            "label": "Memory helping, a second case",
            "note": "Same pattern as above: Arm A misses it, B-self catches it via a correctly-labelled precedent.",
        },
    ],
    "gptoss": [
        {
            "uid": "C1424223317312-51709-285",
            "seq": 3,
            "label": "Same alert, different model",
            "note": (
                "The same alert run through gpt-oss-20b, for direct contrast "
                "with Gemma above — memory does not affect every model the "
                "same way."
            ),
        },
    ],
}
