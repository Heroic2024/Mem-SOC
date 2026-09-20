# Tests

| Path | What it is | How to run |
|---|---|---|
| `test_pipeline.py` | Contract tests for the log-generation -> detection pipeline. Three tiers: static (always run), artifact (needs `artifacts/generated_logs.jsonl`), live (needs the detection API up, else skipped). | `docker compose -f deploy/docker-compose.yml --profile tools run --rm tests` |
| `manual/` | Standalone smoke scripts, **not** unittest tests. They need the full dataset and take minutes. They live outside the `test_*.py` discovery pattern on purpose -- `unittest discover` would otherwise collect them and fail at import. | `PYTHONPATH=src python tests/manual/api_smoke.py` |
| `fixtures/` | Static sample payloads. | — |

Run the suite natively instead of in Docker with:

```bash
PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py" -v
```

The live tier reports `skipped` rather than failing when no API is
reachable, so a green run without Docker still means something.
