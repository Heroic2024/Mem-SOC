"""
CICIDS2017/2018 (NetFlow-format) -> Zeek conn.log-style text logs
Vectorized + chunked version -- scales to millions of rows.

Key differences from the simple version:
  - Reads the CSV in chunks (never loads the whole file into memory)
  - Uses vectorized pandas operations instead of a Python row loop
    (this is the main speed fix -- df.iterrows() is ~50-100x slower
    than vectorized column operations on large files)
  - Prints progress after every chunk so it never looks "hung"

Usage:
    python3 template_convert_fast.py
"""

import pandas as pd
import time

INPUT_CSV = "full_dataset.csv"        # point this at your full CICIDS file
OUTPUT_LOG = "generated_conn.log"
CHUNK_SIZE = 200_000                   # rows per chunk; lower if RAM constrained

PROTO_MAP = {6: "tcp", 17: "udp", 1: "icmp"}


def chunk_to_lines(df: pd.DataFrame) -> pd.Series:
    df.columns = [c.strip() for c in df.columns]

    proto = df["PROTOCOL"].astype(int).map(PROTO_MAP).fillna(
        df["PROTOCOL"].astype(str)
    )
    ts = (df["FLOW_START_MILLISECONDS"] / 1000).round(6)
    duration = (df["FLOW_DURATION_MILLISECONDS"] / 1000).round(6)
    uid = (
        "C"
        + df["FLOW_START_MILLISECONDS"].astype(int).astype(str)
        + df["L4_SRC_PORT"].astype(int).astype(str)
    )
    # Build each line via vectorized string concatenation
    # (label/attack columns intentionally excluded -- see README)
    lines = (
        ts.astype(str) + " "
        + uid + " "
        + df["IPV4_SRC_ADDR"].astype(str) + " "
        + df["L4_SRC_PORT"].astype(int).astype(str) + " "
        + df["IPV4_DST_ADDR"].astype(str) + " "
        + df["L4_DST_PORT"].astype(int).astype(str) + " "
        + proto + " "
        + duration.astype(str) + " "
        + df["IN_BYTES"].astype(int).astype(str) + " "
        + df["OUT_BYTES"].astype(int).astype(str) + " "
        + df["IN_PKTS"].astype(int).astype(str) + " "
        + df["OUT_PKTS"].astype(int).astype(str) + " "
        + df["TCP_FLAGS"].astype(int).astype(str) + " "
        + df["MIN_TTL"].astype(int).astype(str) + " "
        + df["MAX_TTL"].astype(int).astype(str)
    )
    return lines


def main():
    start = time.time()
    total_rows = 0

    with open(OUTPUT_LOG, "w") as out_f:
        for chunk_num, chunk in enumerate(
            pd.read_csv(INPUT_CSV, chunksize=CHUNK_SIZE), start=1
        ):
            lines = chunk_to_lines(chunk)
            out_f.write("\n".join(lines) + "\n")

            total_rows += len(chunk)
            elapsed = time.time() - start
            print(
                f"[chunk {chunk_num}] {total_rows:,} rows processed "
                f"({elapsed:.1f}s elapsed, {total_rows / elapsed:,.0f} rows/sec)"
            )

    print(f"\nDone. {total_rows:,} rows -> {OUTPUT_LOG} in {time.time() - start:.1f}s")


if __name__ == "__main__":
    main()
