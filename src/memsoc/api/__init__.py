"""
Every HTTP endpoint in MemSOC lives in this package.

Previously the two APIs sat in unrelated trees -- the detection API in
final_ml_model_v1/src/api/server.py and the report API in
LLMTriage/report_server.py -- so there was no single place to look when a
route misbehaved. They are now two routers and two thin app objects here.

    Route table
    -----------
    detection  (app_detection:app, default port 8000)
        GET   /                    liveness banner
        GET   /health              health probe
        POST  /api/logs            one NetFlow record -> verdict + SHAP + alert

    reports    (app_reports:app, default port 8001)
        GET   /health              health probe
        GET   /api/reports         summaries of retained reports, newest first
        GET   /api/reports/{name}  one full report, exactly as written to disk

They remain two separate ASGI apps on two ports on purpose: the detection
app loads LightGBM, SHAP and the 37MB multiclass pickle, while the report
app is read-only and holds the LLM credentials. Merging them would couple
those two very different runtimes into one image. Shared request/response
shapes live in `schemas.py` so the contract is declared once.
"""

from memsoc.api import schemas

__all__ = ["schemas"]
