"""
Demo dashboard backend. Run locally only:

    uvicorn main:app --reload --port 8090

Serves two kinds of endpoint:
  - /static/*  pre-computed JSON bundles (built once by static_export.py)
  - /live/*    genuine live calls for the Dynamic section (live_demo.py)

No public exposure: CORS is restricted to the local Vite dev server.
"""

import json
import os

# Must be set before sentence-transformers is imported anywhere (it's
# imported lazily by memsoc.memory.embedding on first use). Without
# this, loading the embedding model makes a network round-trip to the
# Hugging Face Hub to verify the cached revision is current -- normally
# fast, but observed to intermittently take 40-50s on this network,
# which is the actual cause of what looks like a slow/hung LLM call.
# The model files are already cached locally, so offline loading is
# correct, not a degraded fallback.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(BACKEND_DIR))
load_dotenv(os.path.join(REPO_ROOT, ".env"))

import live_demo  # noqa: E402  -- imported after env vars are loaded
from demo_alerts import DEMO_ALERTS  # noqa: E402

STATIC_DIR = os.path.join(BACKEND_DIR, "static_data")

app = FastAPI(title="MemSOC Demo Dashboard")


@app.on_event("startup")
def warm_up():
    """
    Forces the embedding model to actually load, at startup, instead of
    on the presenter's first live click. Opening the memory store alone
    does NOT load it -- embedding.get_model() is lazy, loaded only on
    first .retrieve() call -- so the first click used to pay a one-time
    ~35-50s cost that has nothing to do with the LLM call itself (it's
    local model initialization, confirmed by direct testing; unaffected
    by HF_HUB_OFFLINE). Running one real retrieve(), not just opening
    the collection, is what actually pays this cost here instead of
    during the demo.
    """
    print("warming up: loading embedding model and opening memory stores...")
    for model_key in ("gemma", "gptoss"):
        try:
            layer = live_demo.get_memory_layer(model_key)
            sample_uid = DEMO_ALERTS[model_key][0]["uid"]
            record, flow = live_demo.get_record_and_flow(sample_uid)
            if record is not None and flow is not None:
                layer.retrieve(record, flow)  # forces embedding.get_model() to load
            print(f"  {model_key}: warm")
        except Exception as e:  # noqa: BLE001 -- warm-up failure shouldn't block startup
            print(f"  {model_key}: warm-up failed: {e}")
    print("warm-up complete")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _load_static(name):
    path = os.path.join(STATIC_DIR, f"{name}.json")
    if not os.path.exists(path):
        raise HTTPException(
            status_code=404,
            detail=f"{name}.json not found -- run static_export.py first",
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@app.get("/static/{name}")
def get_static(name: str):
    return _load_static(name)


@app.get("/live/demo-alerts")
def get_demo_alerts():
    return DEMO_ALERTS


@app.post("/live/triage")
def live_triage(model: str, uid: str):
    if model not in ("gemma", "gptoss"):
        raise HTTPException(400, "model must be 'gemma' or 'gptoss'")
    try:
        return live_demo.run_live_triage(model, uid)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.get("/health")
def health():
    return {"status": "ok"}
