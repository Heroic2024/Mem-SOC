# Requirements

One file per deployable. Versions are pinned to the ones the models were
trained and validated against -- `joblib` unpickles LightGBM/scikit-learn
objects, so version drift here is a silent correctness risk, not just a
compatibility one.

| File | Used by | Why it differs |
|---|---|---|
| `detection.txt` | `deploy/detection.Dockerfile` | The only image that loads the model pickles, so the only one needing lightgbm/scikit-learn/shap. |
| `logstream.txt` | `deploy/logstream.Dockerfile` | Runs `--no-api`: POSTs flows over HTTP, never loads a model. |
| `triage.txt` | `deploy/report.Dockerfile` | Read-only report API plus the Groq HTTP client. No ML, no dataset. |
| `controller.txt` | `deploy/controller.Dockerfile` | Drives generation + capture + report generation, so it needs the data stack and an HTTP client, but not the model. |
| `research-lock.txt` | nothing at runtime | A full `pip freeze` of the Jupyter research environment (121 packages, UTF-16 encoded). Kept as a record of what the models were trained under. Never installed by an image. |

`research-lock.txt` is deliberately left byte-for-byte untouched.
