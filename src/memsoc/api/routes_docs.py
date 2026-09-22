"""
The unified API catalogue -- GET /api/openapi/merged.

MemSOC runs two ASGI apps on two ports, so FastAPI generates two separate
Swagger pages. This route builds ONE OpenAPI document describing both, so
`/api-docs` on the gateway can render a single list instead of making
somebody remember which port a route lives on.

Why this lives in the report app rather than a service of its own: the
detection app cannot host it (importing the detection routes pulls in
LightGBM and SHAP, and the report image installs neither), and a third
container just to concatenate two JSON documents is not worth the moving
part. The report app is the light one, it already depends on `requests`,
and it is the service the gateway fronts.

The detection half is fetched over HTTP at request time rather than
imported. That keeps the heavy dependency out of this image and has a
useful side effect: the document always describes what is actually
running, not what was importable at build time.

Path prefixes here MUST match the proxy locations in deploy/nginx.conf.
They are what makes the merged document honest: every path in it is a
real, callable path on the gateway, which is not true of a merge that
simply concatenates two specs (both apps serve GET /health, so a naive
merge silently drops one).
"""

import copy
import os

import requests
from fastapi import APIRouter, Request

from memsoc import paths

router = APIRouter()

# Must match the `location` blocks in deploy/nginx.conf.
DETECTION_PREFIX = os.environ.get(
    "MEMSOC_GATEWAY_DETECTION_PREFIX", "/services/detection"
)
REPORT_PREFIX = os.environ.get(
    "MEMSOC_GATEWAY_REPORT_PREFIX", "/services/report"
)

# Resolved from paths.py, so it is http://detection:8000 inside the
# compose network and http://127.0.0.1:8000 when run natively.
DETECTION_OPENAPI_URL = os.environ.get(
    "MEMSOC_DETECTION_OPENAPI_URL", f"{paths.API_BASE}/openapi.json"
)

FETCH_TIMEOUT = float(os.environ.get("MEMSOC_DOCS_FETCH_TIMEOUT", "10"))

DETECTION_TAG = "detection"
REPORT_TAG = "reports"


def _prefix_paths(spec: dict, prefix: str, tag: str) -> dict:
    """
    Re-key one spec's paths under `prefix` and tag every operation.

    operationIds are namespaced too: both apps generate
    `health_health_get` for their own GET /health, and duplicate
    operationIds break client generators and Swagger UI deep links.
    """

    out = {}

    for path, operations in spec.get("paths", {}).items():

        # "/" would otherwise become "/services/detection" with no
        # trailing slash, which is a different nginx location.
        new_path = prefix + "/" if path == "/" else prefix + path

        new_operations = {}

        for method, operation in operations.items():

            if not isinstance(operation, dict):
                new_operations[method] = operation
                continue

            operation = copy.deepcopy(operation)
            operation["tags"] = [tag]

            if "operationId" in operation:
                operation["operationId"] = f"{tag}_{operation['operationId']}"

            new_operations[method] = operation

        out[new_path] = new_operations

    return out


def _merge_schemas(target: dict, spec: dict, tag: str) -> dict:
    """
    Fold one spec's component schemas into `target`.

    Both specs are generated from the same `api/schemas.py`, so shared
    names (HTTPValidationError, ValidationError) are byte-identical and
    collapse harmlessly. A name that collides with a DIFFERENT definition
    is namespaced instead of silently overwritten; the returned mapping
    says which names moved so their $refs can be rewritten.
    """

    source = spec.get("components", {}).get("schemas", {})

    destination = target.setdefault("components", {}).setdefault("schemas", {})

    renames = {}

    for name, schema in source.items():

        if name in destination and destination[name] != schema:
            renamed = f"{tag}__{name}"
            renames[name] = renamed
            destination[renamed] = schema
        else:
            destination[name] = schema

    return renames


def _rewrite_refs(node, renames: dict) -> None:
    """Point $refs at renamed schemas, in place."""

    if not renames:
        return

    if isinstance(node, dict):

        for key, value in node.items():

            if (
                key == "$ref"
                and isinstance(value, str)
                and value.startswith("#/components/schemas/")
            ):
                name = value.rsplit("/", 1)[1]

                if name in renames:
                    node[key] = f"#/components/schemas/{renames[name]}"

            else:
                _rewrite_refs(value, renames)

    elif isinstance(node, list):

        for item in node:
            _rewrite_refs(item, renames)


def _fetch_detection_spec():
    """The detection app's live spec, or None if it is not reachable."""

    try:
        response = requests.get(DETECTION_OPENAPI_URL, timeout=FETCH_TIMEOUT)
        response.raise_for_status()
        return response.json()

    except (requests.RequestException, ValueError):
        return None


@router.get("/api/openapi/merged", include_in_schema=False)
def merged_openapi(request: Request):
    """
    One OpenAPI document covering both MemSOC services.

    Served to the Swagger UI page at /api-docs on the gateway. Every path
    is prefixed to match the gateway's proxy locations, so operations are
    callable straight from the page.
    """

    merged = {
        "openapi": "3.1.0",
        "info": {
            "title": "MemSOC API",
            "version": "1.0.0",
            "description": (
                "Every HTTP endpoint in MemSOC, across both services.\n\n"
                "Paths are shown as the gateway exposes them "
                f"(`{DETECTION_PREFIX}/...`, `{REPORT_PREFIX}/...`), so "
                "they are callable directly from this page. Each service "
                "also serves its own `/docs` on its own port."
            ),
        },
        # Same origin as this page: the gateway proxies both services.
        "servers": [{"url": "/"}],
        "tags": [
            {
                "name": DETECTION_TAG,
                "description": (
                    "Layer 2 -- frozen LightGBM classifier with SHAP. "
                    "Proxied to the detection service."
                ),
            },
            {
                "name": REPORT_TAG,
                "description": (
                    "Layer 4 -- read-only access to generated security "
                    "reports. Proxied to the report service."
                ),
            },
        ],
        "paths": {},
    }

    # --- this app's own spec, in process -----------------------------
    report_spec = request.app.openapi()

    renames = _merge_schemas(merged, report_spec, REPORT_TAG)
    report_paths = _prefix_paths(report_spec, REPORT_PREFIX, REPORT_TAG)
    _rewrite_refs(report_paths, renames)
    merged["paths"].update(report_paths)

    # --- the detection app's spec, over HTTP -------------------------
    detection_spec = _fetch_detection_spec()

    if detection_spec is None:

        # Still serve what we have. A docs page that renders half the
        # API beats one that 500s because a sibling is restarting.
        merged["info"]["description"] += (
            "\n\n> **Warning:** the detection service was unreachable at "
            f"`{DETECTION_OPENAPI_URL}`, so its endpoints are missing "
            "from this page. Reload once it is healthy."
        )
        merged["x-memsoc-detection-unavailable"] = True

    else:
        renames = _merge_schemas(merged, detection_spec, DETECTION_TAG)
        detection_paths = _prefix_paths(
            detection_spec, DETECTION_PREFIX, DETECTION_TAG
        )
        _rewrite_refs(detection_paths, renames)
        merged["paths"].update(detection_paths)

    return merged
