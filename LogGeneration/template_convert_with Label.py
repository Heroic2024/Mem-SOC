"""
CICIDS2017 (NetFlow-format) -> Zeek conn.log-style text logs
Pure template-based conversion -- no LLM, no API calls, no drift risk.

Since every field in the log line comes directly from the dataset,
this is a mechanical formatting task, not a generation task -- a
template is faster, free, and guaranteed exact.

Usage:
    python3 template_convert.py
"""

import pandas as pd

INPUT_CSV = "first_10_rows.csv"     # your source file (swap for full dataset)
OUTPUT_LOG = "generated_conn.log"

PROTO_MAP = {6: "tcp", 17: "udp", 1: "icmp"}


def row_to_log_line(row: pd.Series) -> str:
    proto_num = int(row["PROTOCOL"])
    proto = PROTO_MAP.get(proto_num, str(proto_num))

    ts = round(row["FLOW_START_MILLISECONDS"] / 1000, 6)
    uid = f"C{int(row['FLOW_START_MILLISECONDS'])}{int(row['L4_SRC_PORT'])}"
    duration = round(row["FLOW_DURATION_MILLISECONDS"] / 1000, 6)
    label = str(row["Label"]).replace(" ", "_")
    attack = str(row["Attack"]).replace(" ", "_")

    fields = [
        ts,
        uid,
        row["IPV4_SRC_ADDR"],
        int(row["L4_SRC_PORT"]),
        row["IPV4_DST_ADDR"],
        int(row["L4_DST_PORT"]),
        proto,
        duration,
        int(row["IN_BYTES"]),
        int(row["OUT_BYTES"]),
        int(row["IN_PKTS"]),
        int(row["OUT_PKTS"]),
        int(row["TCP_FLAGS"]),
        int(row["MIN_TTL"]),
        int(row["MAX_TTL"]),
        label,
        attack,
    ]
    return " ".join(str(f) for f in fields)


def main():
    df = pd.read_csv(INPUT_CSV)
    df.columns = [c.strip() for c in df.columns]  # CICIDS columns often have stray whitespace

    lines = [row_to_log_line(row) for _, row in df.iterrows()]

    with open(OUTPUT_LOG, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Converted {len(lines)} rows -> {OUTPUT_LOG}")


if __name__ == "__main__":
    main()
