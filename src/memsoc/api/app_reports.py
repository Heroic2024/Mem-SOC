"""
Report ASGI app -- Layer 4, default port 8001.

    python -m uvicorn memsoc.api.app_reports:app --host 0.0.0.0 --port 8001

Separate from the detection app on purpose: this one is read-only and
holds the LLM credentials, while the detection app loads the model
pickles. See memsoc/api/__init__.py for the full route table.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from memsoc.api.routes_reports import router

app = FastAPI(
    title="MemSOC Report API",
    description="Read-only access to generated security reports (Layer 4)",
    version="1.0.0",
)

# Local development only: the React dev server runs on a different port
# (Vite default 5173) than this API, so the browser needs CORS allowed to
# fetch across ports. This API is read-only, local-only, and serves no
# secret data -- there is nothing here to protect with a stricter origin
# policy for a capstone project running on localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(router)
