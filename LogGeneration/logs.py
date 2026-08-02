"""
CICIDS2017 (NetFlow-format) -> realistic Zeek conn.log-style text logs
using Groq for the text-rendering step.

Pipeline:
  1. Read CSV rows.
  2. Deterministically map each row to a clean structured dict
     (no LLM involved here -- this guarantees no value is invented).
  3. Send batches of these dicts to Groq, asking it ONLY to render
     them into Zeek conn.log-style lines using a fixed template.
     The model is not allowed to alter, invent, or drop any value.
  4. Re-parse the generated lines and diff them against the source
     dicts to catch any drift introduced by the LLM.

Install deps:
    pip install pandas groq

Set your API key:
    export GROQ_API_KEY="your_key_here"
"""

import os
import json
import time
import pandas as pd
from groq import Groq

# ---------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------
INPUT_CSV = "first_10_rows.csv"          # your source file
OUTPUT_LOG = "generated_conn.log"         # final raw-text log output
OUTPUT_JSONL = "structured_intermediate.jsonl"  # intermediate JSON (for validation)
BATCH_SIZE = 10                            # rows per LLM call
MODEL = "llama-3.3-70b-versatile"          # fast + capable on Groq

PROTO_MAP = {6: "tcp", 17: "udp", 1: "icmp"}

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))


# ---------------------------------------------------------------------
# STEP 1: Deterministic mapping (dataset row -> structured dict)
# No LLM here -- this is the ground truth the LLM must not alter.
# ---------------------------------------------------------------------
def row_to_struct(row: pd.Series) -> dict:
    proto_num = int(row["PROTOCOL"])
    return {
        "ts": round(row["FLOW_START_MILLISECONDS"] / 1000, 6),
        "uid": f"C{int(row['FLOW_START_MILLISECONDS'])}{int(row['L4_SRC_PORT'])}",
        "id.orig_h": row["IPV4_SRC_ADDR"],
        "id.orig_p": int(row["L4_SRC_PORT"]),
        "id.resp_h": row["IPV4_DST_ADDR"],
        "id.resp_p": int(row["L4_DST_PORT"]),
        "proto": PROTO_MAP.get(proto_num, str(proto_num)),
        "duration": round(row["FLOW_DURATION_MILLISECONDS"] / 1000, 6),
        "orig_bytes": int(row["IN_BYTES"]),
        "resp_bytes": int(row["OUT_BYTES"]),
        "orig_pkts": int(row["IN_PKTS"]),
        "resp_pkts": int(row["OUT_PKTS"]),
        "tcp_flags": int(row["TCP_FLAGS"]),
        "min_ttl": int(row["MIN_TTL"]),
        "max_ttl": int(row["MAX_TTL"]),
        "label": row["Label"],
        "attack": row["Attack"],
    }


# ---------------------------------------------------------------------
# STEP 2: Groq call -- render structured dicts as raw text log lines
# ---------------------------------------------------------------------
LOG_TEMPLATE_INSTRUCTIONS = """You are a strict log-formatting engine.
You will receive a JSON array of flow records. For EACH record, output exactly
one line in this Zeek conn.log-style format (space-separated, in this order):

<ts> <uid> <id.orig_h> <id.orig_p> <id.resp_h> <id.resp_p> <proto> <duration> \
<orig_bytes> <resp_bytes> <orig_pkts> <resp_pkts> <tcp_flags> <min_ttl> <max_ttl> \
<label> <attack>

STRICT RULES:
- Do NOT invent, alter, round, or omit any value. Use the values exactly as given.
- Do NOT add commentary, headers, markdown, or explanations.
- Output ONLY the log lines, one per input record, in the same order as input.
- If a string field contains spaces, replace spaces with underscores.
"""


def render_batch(records: list[dict]) -> list[str]:
    user_payload = json.dumps(records)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": LOG_TEMPLATE_INSTRUCTIONS},
            {"role": "user", "content": user_payload},
        ],
        temperature=0,  # deterministic formatting, no creative variation needed here
    )
    text = response.choices[0].message.content.strip()
    lines = [l for l in text.splitlines() if l.strip()]
    return lines


# ---------------------------------------------------------------------
# STEP 3: Validation -- re-parse generated lines, diff against source
# ---------------------------------------------------------------------
FIELD_ORDER = [
    "ts", "uid", "id.orig_h", "id.orig_p", "id.resp_h", "id.resp_p",
    "proto", "duration", "orig_bytes", "resp_bytes", "orig_pkts",
    "resp_pkts", "tcp_flags", "min_ttl", "max_ttl", "label", "attack",
]


def validate_line(struct: dict, line: str) -> list[str]:
    parts = line.strip().split()
    mismatches = []
    if len(parts) != len(FIELD_ORDER):
        return [f"field count mismatch: expected {len(FIELD_ORDER)}, got {len(parts)}"]
    for field, parsed_val in zip(FIELD_ORDER, parts):
        expected = str(struct[field]).replace(" ", "_")
        if str(parsed_val) != expected:
            mismatches.append(f"{field}: expected={expected} got={parsed_val}")
    return mismatches


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------
def main():
    df = pd.read_csv(INPUT_CSV)
    df.columns = [c.strip() for c in df.columns]  # CICIDS columns often have stray whitespace

    structs = [row_to_struct(row) for _, row in df.iterrows()]

    # save intermediate JSON (ground truth for validation / reproducibility)
    with open(OUTPUT_JSONL, "w") as f:
        for s in structs:
            f.write(json.dumps(s) + "\n")

    all_lines = []
    total_mismatches = 0

    for i in range(0, len(structs), BATCH_SIZE):
        batch = structs[i:i + BATCH_SIZE]
        lines = render_batch(batch)

        if len(lines) != len(batch):
            print(f"[WARN] batch {i}: expected {len(batch)} lines, got {len(lines)} -- "
                  f"skipping validation for this batch, keeping raw output")
            all_lines.extend(lines)
            continue

        for struct, line in zip(batch, lines):
            mismatches = validate_line(struct, line)
            if mismatches:
                total_mismatches += 1
                print(f"[DRIFT] uid={struct['uid']} -> {mismatches}")
            all_lines.append(line)

        time.sleep(0.2)  # light throttling; Groq is fast but be polite in bulk runs

    with open(OUTPUT_LOG, "w") as f:
        f.write("\n".join(all_lines) + "\n")

    print(f"\nDone. {len(all_lines)} log lines written to {OUTPUT_LOG}")
    print(f"Intermediate structured JSON: {OUTPUT_JSONL}")
    print(f"Rows with drift/mismatch: {total_mismatches} / {len(structs)}")


if __name__ == "__main__":
    main()
