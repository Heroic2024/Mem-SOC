"""
Protocol v4 -- build the benign alerts for the hard-benign test.

    # 1. detection venv (requirements/detection.txt): score and explain
    python -m memsoc.triage.protocol_v4_benign --score
    # 2. memory venv (protocol constraints): de-duplicate, order, write
    python -m memsoc.triage.protocol_v4_benign --select
    # either venv: check the built files against the committed manifest
    python -m memsoc.triage.protocol_v4_benign --check

Two steps because they need two pinned environments: scoring and SHAP
need the detector's own packages, near-duplicate removal needs the
embedding model. Neither venv has the other's pins.

The selection rule (fixed 2026-10-29, before any benign run)
-------------------------------------------------------------
Pool      Held-out rows only (paths.HELD_OUT_ROWS, verified against the
          detector's published fingerprint), every feature finite, true
          label benign, and NOT one of the 120,000 flows already in the
          stream (generated_logs.jsonl row_id). So nothing was trained
          on, and nothing overlaps the alerts already triaged.
Hard set  Ranked by the frozen binary detector's attack probability,
          highest first. Ties are broken by a seeded random key, not by
          row number: from about rank 70 the pool shares one floor
          score, so row order would take the tied flows from one
          stretch of the capture (BL-180). Walking that ranking, a
          flow is skipped if its 48 features equal an already chosen
          flow's, or if its case text embeds at cosine >= NEAR_DUP_COSINE
          to an already chosen flow's. The first HARD_COUNT kept are
          the set; they are then shuffled once with ORDER_SEED.
Random    RANDOM_COUNT flows drawn uniformly from the same pool,
          skipping any in the hard set. Optional second set.

Seeds     SEED is split by numpy's SeedSequence into two independent
          streams, one for the tie-break key and one for the random
          draw. One shared stream would order both identically, and the
          random set would then just continue the hard set's ties.

What the LLM sees
-----------------
Each flow is passed through the detector's own code (InferencePipeline's
multiclass prediction, SHAP explainer and AlertGenerator), so the family
guess and the SHAP block are exactly what any alert would carry. The one
deliberate departure is the "Attack/benign score" line: the binary model
called these flows benign, and its real score would be the only value
below 1.0 among all 1,135 real alerts (every one shows 1.0 or 0.9999).
Showing it would hand the LLM the answer, so the record carries
SHOWN_BINARY_CONFIDENCE instead, and the real figures are kept beside it
under "v4_benign" for the audit. Both arms see the same record.

Outputs: PROTOCOL_V4_DIR (gitignored) holds the records, flows and the
ground truth; protocol_v4_benign.json beside this module is committed,
and its hashes are what the runner checks before every benign run.
"""

import argparse
import contextlib
import csv
import hashlib
import io
import json
import os
import sys
from pathlib import Path

from memsoc import paths

HARD_COUNT = 100
RANDOM_COUNT = 50

# Ranked candidates explained in --score. More than HARD_COUNT because
# near-duplicates are removed in --select; --select fails rather than
# returning fewer than HARD_COUNT.
HARD_CANDIDATES = 1000
RANDOM_CANDIDATES = 200

NEAR_DUP_COSINE = 0.98

# Split into (tie-break, random draw) streams; see the module docstring.
SEED = 42
ORDER_SEED = 42

# See the module docstring: what every real alert shows.
SHOWN_BINARY_CONFIDENCE = 1.0

# Benign uids continue the stream's numbering (C<start>-<port>-<seq>, seq
# 1..120,000), so they cannot collide with a stream uid and look like any
# other alert id in the prompt.
UID_SEQ_START = 120_001

CHUNK_SIZE = 200_000

CANDIDATES = Path(paths.PROTOCOL_V4_DIR) / "benign_candidates.jsonl"
MANIFEST = Path(__file__).with_name("protocol_v4_benign.json")

SETS = ("hard", "random")


def set_paths(name):
    """records, flows and ground truth for one set, in PROTOCOL_V4_DIR."""

    base = Path(paths.PROTOCOL_V4_DIR)

    return {
        "records": base / f"{name}_benign_records.jsonl",
        "flows": base / f"{name}_benign_flows.jsonl",
        "ground_truth": base / f"{name}_benign_ground_truth.csv",
    }


def _sha256(path):

    digest = hashlib.sha256()

    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)

    return digest.hexdigest()


def _features_hash(flow, feature_names):

    return hashlib.sha256(
        json.dumps([flow[k] for k in feature_names]).encode()
    ).hexdigest()


def _uid_list_sha256(uids):

    return hashlib.sha256("\n".join(uids).encode()).hexdigest()


# ----------------------------------------------------------------------
# Step 1 -- detection venv
# ----------------------------------------------------------------------

def score():

    import numpy as np
    import pandas as pd

    from memsoc.detection.inference.inference_pipeline import InferencePipeline
    from memsoc.detection.utils.logger import alert_logger, inference_logger
    from memsoc.logstream import nfv3_log_generator as generator

    # These flows are not detections. AlertGenerator would otherwise write
    # an "Attack detected" line to alerts.log for every candidate.
    alert_logger.disabled = True
    inference_logger.disabled = True

    held_out = np.load(paths.HELD_OUT_ROWS)

    with open(paths.GENERATED_LOGS, "r", encoding="utf-8") as f:
        in_stream = {json.loads(line)["row_id"] for line in f if line.strip()}

    print(f"Held-out rows {len(held_out):,}; stream rows excluded {len(in_stream):,}")

    with contextlib.redirect_stdout(io.StringIO()):
        pipeline = InferencePipeline()

    feature_columns = generator.read_feature_columns(paths.DATASET_CSV)

    if feature_columns != pipeline.feature_names:
        raise SystemExit("Dataset feature order differs from the detector's; refusing to score.")

    pool_rows, pool_scores = [], []

    for chunk in pd.read_csv(paths.DATASET_CSV, chunksize=CHUNK_SIZE):

        chunk.columns = [c.strip() for c in chunk.columns]

        mask = (
            generator.pool_mask(chunk, feature_columns, held_out)
            & (chunk["Label"] == 0)
            & ~chunk.index.isin(in_stream)
        )
        chunk = chunk[mask]

        if len(chunk):
            sample = chunk[feature_columns].apply(pd.to_numeric)
            attack = list(pipeline.binary_model.classes_).index(1)
            pool_rows.extend(chunk.index.tolist())
            pool_scores.extend(pipeline.binary_model.predict_proba(sample)[:, attack].tolist())

        print(f"  scanned to row {chunk.index.max() if len(chunk) else '-'}: pool {len(pool_rows):,}")

    pool_rows = np.asarray(pool_rows)
    pool_scores = np.asarray(pool_scores)

    tie_stream, draw_stream = np.random.SeedSequence(SEED).spawn(2)

    # One random key per row, assigned in row-number order so the key a
    # row gets does not depend on chunking.
    by_row_order = np.argsort(pool_rows)
    tie_key = np.empty(len(pool_rows))
    tie_key[by_row_order] = np.random.default_rng(tie_stream).random(len(pool_rows))

    # Highest attack probability first; ties by the seeded key.
    ranked = np.lexsort((tie_key, -pool_scores))
    hard = pool_rows[ranked[:HARD_CANDIDATES]]

    rng = np.random.default_rng(draw_stream)
    random_rows = np.sort(pool_rows)[rng.permutation(len(pool_rows))[:RANDOM_CANDIDATES]]

    wanted = {int(r): ("hard", i) for i, r in enumerate(hard)}
    for i, r in enumerate(random_rows):
        wanted.setdefault(int(r), ("random", i))

    rows = {}

    for chunk in pd.read_csv(paths.DATASET_CSV, chunksize=CHUNK_SIZE):
        chunk.columns = [c.strip() for c in chunk.columns]
        for row_id in chunk.index.intersection(list(wanted)):
            rows[int(row_id)] = chunk.loc[row_id]

    by_row = dict(zip(pool_rows.tolist(), pool_scores.tolist()))

    os.makedirs(paths.PROTOCOL_V4_DIR, exist_ok=True)

    with open(CANDIDATES, "w", encoding="utf-8") as out:

        for kind, order in (("hard", [int(r) for r in hard]), ("random", [int(r) for r in random_rows])):

            for rank, row_id in enumerate(order):

                row = rows[row_id]
                flow = generator.build_record(row, 0, feature_columns)
                sample = pipeline.prepare_dataframe(flow)

                with contextlib.redirect_stdout(io.StringIO()):
                    prediction, label, confidence = pipeline.binary_prediction(sample)
                    attack, attack_confidence = pipeline.multiclass_prediction(sample)
                    shap_explanation = pipeline.shap_explainer.explain(sample, top_k=10)
                    alert = pipeline.alert_generator.generate(
                        attack=attack,
                        confidence=attack_confidence,
                        flow=flow,
                        top_features=[item["feature"] for item in shap_explanation],
                        shap_explanation=shap_explanation,
                    )

                out.write(json.dumps({
                    "kind": kind,
                    "rank": rank,
                    "row_id": row_id,
                    "attack_probability": by_row[row_id],
                    "binary_prediction": label,
                    "binary_confidence": round(confidence, 4),
                    "multiclass": {"prediction": attack, "confidence": round(attack_confidence, 4)},
                    "alert": alert,
                    "flow": flow,
                }, default=generator.to_native) + "\n")

    print(f"Pool {len(pool_rows):,} benign rows; top attack probability {pool_scores.max():.4f}")
    print(f"Wrote {CANDIDATES}")


# ----------------------------------------------------------------------
# Step 2 -- memory venv
# ----------------------------------------------------------------------

def select():

    import numpy as np

    from memsoc.memory import case_text, embedding

    with open(CANDIDATES, "r", encoding="utf-8") as f:
        candidates = [json.loads(line) for line in f if line.strip()]

    feature_names = [k for k in candidates[0]["flow"]
                     if k not in ("uid", "ts", "id.orig_h", "id.orig_p", "id.resp_h", "id.resp_p", "proto")]

    def as_record(c):
        record = {
            "uid": None,
            "status": "attack",
            "binary_confidence": SHOWN_BINARY_CONFIDENCE,
            "multiclass": c["multiclass"],
            "alert": c["alert"],
        }
        return record

    # -- hard set: walk the ranking, drop near-duplicates --
    hard, seen_hashes, vectors = [], set(), []
    skipped = {"identical_features": 0, "near_duplicate_text": 0}

    for c in sorted((c for c in candidates if c["kind"] == "hard"), key=lambda c: c["rank"]):

        h = _features_hash(c["flow"], feature_names)

        if h in seen_hashes:
            skipped["identical_features"] += 1
            continue

        vector = np.asarray(embedding.embed(case_text.render(as_record(c), c["flow"])))
        vector = vector / np.linalg.norm(vector)

        if vectors and float(np.max(np.stack(vectors) @ vector)) >= NEAR_DUP_COSINE:
            skipped["near_duplicate_text"] += 1
            continue

        seen_hashes.add(h)
        vectors.append(vector)
        hard.append(c)

        if len(hard) == HARD_COUNT:
            break

    if len(hard) < HARD_COUNT:
        raise SystemExit(f"Only {len(hard)} distinct hard-benign flows among {HARD_CANDIDATES} "
                         f"candidates; raise HARD_CANDIDATES and re-run --score.")

    order = np.random.default_rng(ORDER_SEED).permutation(HARD_COUNT)
    hard = [hard[i] for i in order]

    # -- random set: the draw order, skipping the hard set --
    taken = {c["row_id"] for c in hard}
    random_set = [c for c in sorted((c for c in candidates if c["kind"] == "random"), key=lambda c: c["rank"])
                  if c["row_id"] not in taken][:RANDOM_COUNT]

    manifest = {
        "rule": {
            "pool": "held-out rows (paths.HELD_OUT_ROWS), all features finite, Label == 0, "
                    "not in generated_logs.jsonl (row_id)",
            "hard_ranking": f"binary detector attack probability, descending; ties by a random key "
                            f"from numpy SeedSequence({SEED}).spawn(2)[0], assigned in row-number order",
            "near_duplicates": f"skip identical 48-feature vectors, and case text cosine >= {NEAR_DUP_COSINE} "
                               f"to an already chosen flow (embedding {embedding.MODEL_NAME} @ {embedding.MODEL_REVISION})",
            "hard_count": HARD_COUNT,
            "hard_candidates_scored": HARD_CANDIDATES,
            "hard_order": f"numpy default_rng({ORDER_SEED}).permutation of the kept flows",
            "random_count": RANDOM_COUNT,
            "random_draw": f"numpy default_rng(SeedSequence({SEED}).spawn(2)[1]).permutation of the pool "
                           f"sorted by row number, skipping the hard set",
            "shown_binary_confidence": SHOWN_BINARY_CONFIDENCE,
            "uid_format": f"C<FLOW_START_MILLISECONDS>-<L4_SRC_PORT>-<seq>, seq from {UID_SEQ_START}",
        },
        "skipped_as_duplicates": skipped,
        "inputs_sha256": {
            "dataset": _sha256(paths.DATASET_CSV),
            "heldout_rows": _sha256(paths.HELD_OUT_ROWS),
            "generated_logs": _sha256(paths.GENERATED_LOGS),
        },
        "sets": {},
    }

    seq = UID_SEQ_START

    for name, chosen in (("hard", hard), ("random", random_set)):

        out = set_paths(name)
        listing = []

        with open(out["records"], "w", encoding="utf-8") as fr, \
                open(out["flows"], "w", encoding="utf-8") as ff, \
                open(out["ground_truth"], "w", encoding="utf-8", newline="") as fg:

            truth = csv.writer(fg)
            truth.writerow(["uid", "label", "attack"])

            for c in chosen:

                flow = dict(c["flow"])
                uid = f"C{int(round(flow['ts'] * 1000))}-{flow['id.orig_p']}-{seq}"
                seq += 1
                flow["uid"] = uid

                record = as_record(c)
                record["uid"] = uid
                record["row_id"] = c["row_id"]
                record["v4_benign"] = {
                    "set": name,
                    "rank": c["rank"],
                    "real_attack_probability": c["attack_probability"],
                    "real_binary_prediction": c["binary_prediction"],
                    "real_binary_confidence": c["binary_confidence"],
                    "shown_binary_confidence": SHOWN_BINARY_CONFIDENCE,
                }

                fr.write(json.dumps(record) + "\n")
                ff.write(json.dumps(flow) + "\n")
                truth.writerow([uid, 0, "Benign"])

                listing.append({"uid": uid, "row_id": c["row_id"], "rank": c["rank"],
                                "attack_probability": c["attack_probability"]})

        manifest["sets"][name] = {
            "count": len(listing),
            "uid_list_sha256": _uid_list_sha256([x["uid"] for x in listing]),
            "records_sha256": _sha256(out["records"]),
            "flows_sha256": _sha256(out["flows"]),
            "ground_truth_sha256": _sha256(out["ground_truth"]),
            "flows_in_run_order": listing,
        }

    MANIFEST.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")

    print(f"hard {len(hard)} (skipped {skipped}), random {len(random_set)}")
    print(f"Wrote {MANIFEST} -- commit it before any benign run.")


# ----------------------------------------------------------------------
# Used by protocol_v4
# ----------------------------------------------------------------------

def check(name):
    """
    (ok, detail) -- the built files for one set match the committed
    manifest. The runner refuses a benign run unless this passes.
    """

    if not MANIFEST.exists():
        return False, f"{MANIFEST.name} not found"

    wanted = json.loads(MANIFEST.read_text(encoding="utf-8"))["sets"].get(name)

    if not wanted:
        return False, f"set {name!r} not in {MANIFEST.name}"

    files = set_paths(name)
    bad = [kind for kind in ("records", "flows", "ground_truth")
           if not files[kind].exists() or _sha256(files[kind]) != wanted[f"{kind}_sha256"]]

    return not bad, ("matches the manifest" if not bad else f"differs or missing: {', '.join(bad)}")


def load(name):
    """(records in run order, flows keyed by uid) for one set."""

    files = set_paths(name)

    with open(files["records"], "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    with open(files["flows"], "r", encoding="utf-8") as f:
        flows = {row["uid"]: row for row in map(json.loads, f) if row}

    return records, flows


def main():

    parser = argparse.ArgumentParser(description="Protocol v4 -- build the benign alerts")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--score", action="store_true", help="step 1, detection venv")
    mode.add_argument("--select", action="store_true", help="step 2, memory venv")
    mode.add_argument("--check", action="store_true", help="built files match the committed manifest")
    args = parser.parse_args()

    if args.score:
        score()
    elif args.select:
        select()
    else:
        results = {name: check(name) for name in SETS}
        for name, (ok, detail) in results.items():
            print(f"  {'PASS' if ok else 'FAIL'}  {name}: {detail}")
        sys.exit(0 if all(ok for ok, _ in results.values()) else 1)


if __name__ == "__main__":
    main()
