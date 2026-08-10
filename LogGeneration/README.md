# CICIDS2017 -> Zeek-style Log Generator

Converts the CICIDS2017 (NetFlow-format) dataset into realistic,
Zeek `conn.log`-style logs for training a memory-based intrusion
detection model.

## Pipeline

```
full CICIDS CSV
      |
      v   template_convert_fast.py
generated_conn.log     (Zeek-style, space-separated text)
      |
      v   log_to_jsonl.py
generated_logs.jsonl   (JSON Lines -- final output)
```

## Scripts

### `template_convert_fast.py`
Reads the source CSV in chunks (default 200,000 rows at a time) and
converts each row into one Zeek `conn.log`-style text line, using
vectorized pandas operations (not a row-by-row loop) so it stays fast
on large files. Prints progress after every chunk.

- **Input:** `full_dataset.csv` (edit `INPUT_CSV` to point at your file)
- **Output:** `generated_conn.log`

Field mapping applied:
| CICIDS column | Log field | Notes |
|---|---|---|
| `FLOW_START_MILLISECONDS` | `ts` | converted ms -> seconds |
| `FLOW_START_MILLISECONDS` + `L4_SRC_PORT` | `uid` | synthetic connection ID, Zeek-style prefix |
| `IPV4_SRC_ADDR` | `id.orig_h` | |
| `L4_SRC_PORT` | `id.orig_p` | |
| `IPV4_DST_ADDR` | `id.resp_h` | |
| `L4_DST_PORT` | `id.resp_p` | |
| `PROTOCOL` | `proto` | numeric -> name (`6`->`tcp`, `17`->`udp`, `1`->`icmp`) |
| `FLOW_DURATION_MILLISECONDS` | `duration` | converted ms -> seconds |
| `IN_BYTES` / `OUT_BYTES` | `orig_bytes` / `resp_bytes` | |
| `IN_PKTS` / `OUT_PKTS` | `orig_pkts` / `resp_pkts` | |
| `TCP_FLAGS` | `tcp_flags` | |
| `MIN_TTL` / `MAX_TTL` | `min_ttl` / `max_ttl` | |

### `log_to_jsonl.py`
Re-parses `generated_conn.log` (does **not** touch the original CSV)
and rewrites each line as one JSON object per line (JSONL), casting
each field to the correct type (int/float/string).

- **Input:** `generated_conn.log`
- **Output:** `generated_logs.jsonl`

Example output line:
```json
{"ts": 1518611287.705, "uid": "C151861128770553", "id.orig_h": "172.31.0.2", "id.orig_p": 53, "id.resp_h": "172.31.66.58", "id.resp_p": 63593, "proto": "udp", "duration": 0.001, "orig_bytes": 156, "resp_bytes": 0, "orig_pkts": 1, "resp_pkts": 0, "tcp_flags": 0, "min_ttl": 0, "max_ttl": 0}
```

## Why no `label` / `attack` fields

The original CICIDS columns `Label` (0/1) and `Attack` (e.g. `Benign`,
`DDoS`, `PortScan`) are intentionally **excluded** from the generated
logs. A real network sensor (Zeek, NetFlow exporter, etc.) has no way
of knowing in advance whether a connection is malicious -- it only
records what it observes. Keeping ground-truth labels inside the logs
themselves would leak the answer into the model's input and make
results look better than they'd be on real traffic.

If you need the ground truth for evaluation (measuring precision/
recall once your model flags anomalies), keep it as a **separate**
file, joined by `uid`, rather than embedding it in the logs:

```python
import pandas as pd

df = pd.read_csv("full_dataset.csv")
df.columns = [c.strip() for c in df.columns]

ground_truth = pd.DataFrame({
    "uid": (
        "C"
        + df["FLOW_START_MILLISECONDS"].astype(int).astype(str)
        + df["L4_SRC_PORT"].astype(int).astype(str)
    ),
    "label": df["Label"],
    "attack": df["Attack"],
})
ground_truth.to_csv("ground_truth.csv", index=False)
```

This keeps your training logs "unlabeled" (as a real deployment would
see them) while still letting you score your model's detections
against ground truth afterward.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install pandas
```

No API keys needed -- both scripts are pure Python/pandas, no LLM calls.

## Usage

```bash
# 1. Edit INPUT_CSV in template_convert_fast.py to point at your dataset
python3 template_convert_fast.py

# 2. Convert the resulting log to JSONL
python3 log_to_jsonl.py
```

## Notes

- Both scripts are deterministic -- same input always produces the
  same output, byte for byte.
- `template_convert_fast.py` prints progress per chunk so it never
  looks "hung" on large files.
- If `log_to_jsonl.py` reports `[SKIP] line N: expected 15 fields,
  got X`, it means a field in that line unexpectedly contained a
  space -- check that row in the source CSV.
