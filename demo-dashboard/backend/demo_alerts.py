"""
Curated shortlist of alerts for the Dynamic section's live-demo picker.

Each entry is deliberately chosen to tell a clear, specific story when run
live, rather than exposing all 165 alerts (most of which are not
illustrative on their own). `uid` must exist in both
artifacts/model_outputs/live_results.jsonl and artifacts/generated_logs.jsonl
so the real alert + flow can be reconstructed and rendered exactly as the
evaluated pipeline rendered it.

Every `outcome` below is the actual recorded result for that alert (not a
prediction of what the live call will show) -- the live call may differ
slightly from run to run since the models aren't perfectly deterministic,
and the Dynamic section's own "does this match the recorded result?" check
is what makes that visible rather than hiding it.
"""

GEMMA_RUN_ID = "bself-gemma4-26b-p3"
GPTOSS_RUN_ID = "bself-gptoss20b-p1"

DEMO_ALERTS = {
    "gemma": [
        {
            "uid": "C1424223317312-51709-285",
            "seq": 3,
            "label": "The report's worked example",
            "outcome": "harm — wrong family, still escalated",
            "note": (
                "Arm A correctly names this Exploits. B-self's most similar "
                "retrieved precedent (0.99 similarity) was stored as Fuzzers, "
                "and B-self copies it — still catches the attack, but "
                "names it wrong. This is the exact copying mechanism Section "
                "4.4.4 documents, reproduced live on the alert the report "
                "itself uses as its worked example."
            ),
        },
        {
            "uid": "C1424256835752-64848-703",
            "seq": 8,
            "label": "The same harm, a second alert",
            "outcome": "harm — wrong family, still escalated",
            "note": (
                "Arm A again correctly names Exploits; B-self again copies a "
                "retrieved Fuzzers label and gets the family wrong — run "
                "this one to show the pattern from alert 4 isn't a one-off."
            ),
        },
        {
            "uid": "C1421928595670-59362-768",
            "seq": 9,
            "label": "Where memory fixes a miss",
            "outcome": "help — Arm A misses it, B-self catches it",
            "note": (
                "Arm A dismisses this alert outright (a missed attack). "
                "B-self's retrieved precedents are correctly labelled "
                "Fuzzers, and B-self follows them to the right answer — "
                "one of only 5 alerts in the whole run where memory fixed an "
                "Arm A mistake rather than causing one."
            ),
        },
        {
            "uid": "C1421928105613-16373-3693",
            "seq": 32,
            "label": "Memory fixing a miss, again",
            "outcome": "help — Arm A misses it, B-self catches it",
            "note": (
                "Same pattern as the alert above, a different case: Arm A "
                "misses it, B-self catches it via a correctly-labelled "
                "retrieved precedent. Run both to show it's a repeatable "
                "effect, not a single lucky draw."
            ),
        },
    ],
    "gptoss": [
        {
            "uid": "C1424251826140-57260-6430",
            "seq": 60,
            "label": "Where memory helps gpt-oss-20b",
            "outcome": "help — Arm A misses it, B-self catches it",
            "note": (
                "Arm A dismisses this alert outright (a missed attack). "
                "B-self's retrieved precedents are correctly labelled "
                "Fuzzers, and B-self follows them to the right answer — "
                "memory fixing an Arm A mistake isn't unique to Gemma."
            ),
        },
        {
            "uid": "C1421932755522-62628-7493",
            "seq": 75,
            "label": "The same help, a second case",
            "outcome": "help — Arm A misses it, B-self catches it",
            "note": (
                "Same pattern as the alert above, a different case: Arm A "
                "misses it, B-self catches it via a correctly-labelled "
                "retrieved precedent — run both to show it's repeatable on "
                "this model too."
            ),
        },
        {
            "uid": "C1424223317312-51709-285",
            "seq": 3,
            "label": "Same alert as Gemma, for contrast",
            "outcome": "neutral — both arms miss it on this model",
            "note": (
                "The exact alert used in the Gemma examples above, run "
                "through gpt-oss-20b instead. Here neither arm catches it "
                "(both come back false_positive) — memory doesn't help or "
                "hurt on this specific alert for this model, which is its "
                "own useful contrast with Gemma's result on the same alert."
            ),
        },
        {
            "uid": "C1424245219449-21814-1570",
            "seq": 17,
            "label": "Memory causing a miss, not just a wrong name",
            "outcome": "harm — Arm A catches it, B-self dismisses it",
            "note": (
                "Arm A correctly escalates this as Exploits. B-self doesn't "
                "just mis-name it — it dismisses the alert entirely "
                "(false_positive), missing a real attack Arm A caught. This "
                "is the sharper failure mode behind gpt-oss-20b's recall "
                "drop (40.2% → 26.1%), distinct from Gemma's "
                "right-verdict-wrong-name pattern above."
            ),
        },
        {
            "uid": "C1424237451380-43315-1802",
            "seq": 19,
            "label": "The same miss pattern, a second case",
            "outcome": "harm — Arm A catches it, B-self dismisses it",
            "note": (
                "Arm A correctly escalates this as Reconnaissance; B-self "
                "dismisses it outright — run this alongside the alert "
                "above to show gpt-oss-20b's harm from memory is repeatable, "
                "not a single bad draw."
            ),
        },
        {
            "uid": "C1424249486851-13691-1532",
            "seq": 16,
            "label": "Where memory helps gpt-oss-20b too",
            "outcome": "help — Arm A misses it, B-self catches it",
            "note": (
                "Arm A dismisses this alert (a missed attack). B-self's "
                "retrieved precedents are correctly labelled Fuzzers, and "
                "B-self follows them to the right answer — one of the "
                "10 alerts where memory helped gpt-oss-20b, proving the "
                "effect isn't purely negative on this model either."
            ),
        },
    ],
}
