"""
Report ASGI app -- Layer 4, default port 8001.

    python -m uvicorn memsoc.api.app_reports:app --host 0.0.0.0 --port 8001

Separate from the detection app on purpose: this one is read-only and
holds the LLM credentials, while the detection app loads the model
pickles. See memsoc/api/__init__.py for the full route table.
"""

from fastapi import FastAPI

from memsoc.api.routes_docs import router as docs_router
from memsoc.api.routes_reports import router

app = FastAPI(
    title="MemSOC Report API",
    description="Read-only access to generated security reports (Layer 4)",
    version="1.0.0",
)

# No CORS middleware, deliberately. Every browser client reaches this API
# through the gateway on its own origin -- nginx proxies /services/report/
# in the deployed stack, and Vite proxies the same prefix in `npm run dev`
# -- so these requests are same-origin and need no CORS headers. This used
# to carry allow_origins=["*"] purely to work around the dashboard calling
# a different port; that call is gone, so the wildcard goes with it.

app.include_router(router)

# The unified API catalogue that /api-docs on the gateway renders. It
# describes BOTH services; it is hosted here because this is the light
# service (see routes_docs.py). Excluded from this app's own /docs.
app.include_router(docs_router)
