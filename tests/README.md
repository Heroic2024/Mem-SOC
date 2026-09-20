# Tests

| Path | What it is | How to run |
|---|---|---|
| `test_pipeline.py` | Contract tests for the log-generation -> detection pipeline. Three tiers: static (always run), artifact (needs `artifacts/generated_logs.jsonl`), live (needs the detection API up, else skipped). | `docker compose -f deploy/docker-compose.yml --profile tools run --rm tests` |
| `test_gateway_contract.py` | Guards the gateway prefixes (**BL-071**). The string `/services/report` is hand-written in four files across three languages; this catches them drifting apart. Two tiers: static (compares the four files, no Docker) and live (asks the running gateway to serve every path the API docs page advertises, else skipped). | same command |
| `manual/` | Standalone smoke scripts, **not** unittest tests. They need the full dataset and take minutes. They live outside the `test_*.py` discovery pattern on purpose -- `unittest discover` would otherwise collect them and fail at import. | `PYTHONPATH=src python tests/manual/api_smoke.py` |
| `fixtures/` | Static sample payloads. | — |

Run the suite natively instead of in Docker with:

```bash
PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py" -v
```

A full run is **19 tests**: 13 from `test_pipeline.py`, 6 from
`test_gateway_contract.py`.

Live tiers report `skipped` rather than failing when nothing is
reachable, so a green run without Docker still means something. Read the
skip count: `OK (skipped=2)` means a whole tier did not run.

**The `tests` service reuses the `logstream` image.** If you add a test
dependency, or a file a test reads, rebuild it -- otherwise the suite
runs against a stale copy and silently skips:

```bash
docker compose -f deploy/docker-compose.yml --profile tools build logstream
```
