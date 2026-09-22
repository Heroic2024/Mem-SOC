"""
Contract tests for the gateway prefixes (backlog BL-071).

The strings `/services/detection` and `/services/report` are typed out by
hand in four files, in three languages, none of which imports the value
from the others:

    deploy/nginx.conf              the location blocks that route traffic
    src/memsoc/api/routes_docs.py  the paths written into the merged spec
    dashboard/src/api.js           where the dashboard fetches its data
    dashboard/vite.config.js       the dev-server proxy (key + rewrite)

Change one and the others keep pointing at the old name. Nothing else in
the suite notices: the pipeline tests talk to the detection service
directly on port 8000 and never pass through the gateway, so all of them
pass while the dashboard shows an empty page.

Two tiers, the same shape as test_pipeline.py:

    static   always runs -- reads the four files and compares the
             literals. Catches drift without Docker running.
    live     needs the gateway up -- asks it to serve every path the
             merged spec advertises. Catches the case where the files
             agree with each other but not with what nginx actually does.

Usage:
    python -m unittest test_gateway_contract -v
    python -m unittest discover -s tests -v
"""

import ast
import os
import re
import unittest

import requests

from memsoc import paths

# The gateway is the dashboard container. Its published port is the one
# thing here that is genuinely environment-specific.
GATEWAY_BASE = os.environ.get("MEMSOC_GATEWAY_BASE", "http://127.0.0.1:8080")

MERGED_SPEC_URL = f"{GATEWAY_BASE}/api-docs/openapi.json"

REPO_ROOT = paths.ROOT

ROUTES_DOCS = os.path.join(
    REPO_ROOT, "src", "memsoc", "api", "routes_docs.py"
)
NGINX_CONF = os.path.join(REPO_ROOT, "deploy", "nginx.conf")
DASHBOARD_API_JS = os.path.join(REPO_ROOT, "dashboard", "src", "api.js")
VITE_CONFIG = os.path.join(REPO_ROOT, "dashboard", "vite.config.js")

TIMEOUT = 15

# A path parameter has to be filled in before the path can be requested.
# The value does not need to be valid -- a 400 still proves the gateway
# routed it, which is all this test is about.
PATH_PARAM_PLACEHOLDER = "contract-test"


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def prefix_from_routes_docs(name):
    """
    Read one prefix constant out of routes_docs.py without importing it.

    Importing would drag in fastapi and pydantic, which the lightweight
    tests image does not install -- and this test has no business needing
    the web stack to compare two strings. test_pipeline.py parses
    feature_engineering.py the same way, for the same reason.

    The constants look like:

        DETECTION_PREFIX = os.environ.get(
            "MEMSOC_GATEWAY_DETECTION_PREFIX", "/services/detection"
        )

    so the env override is honoured exactly as it is at runtime.
    """

    tree = ast.parse(read(ROUTES_DOCS))

    for node in tree.body:

        if not isinstance(node, ast.Assign):
            continue

        if not any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            continue

        call = node.value

        if not isinstance(call, ast.Call) or len(call.args) != 2:
            raise AssertionError(
                f"{name} in routes_docs.py is no longer an "
                f"os.environ.get(var, default) call -- update this test"
            )

        env_name, default = (ast.literal_eval(a) for a in call.args)

        return os.environ.get(env_name, default)

    raise AssertionError(f"{name} not found in {ROUTES_DOCS}")


# Resolved at import so every test shares one answer. If the source is
# not present (running outside a checkout), stay None and let the tiers
# skip rather than failing to collect.
if os.path.exists(ROUTES_DOCS):
    DETECTION_PREFIX = prefix_from_routes_docs("DETECTION_PREFIX")
    REPORT_PREFIX = prefix_from_routes_docs("REPORT_PREFIX")
else:
    DETECTION_PREFIX = REPORT_PREFIX = None


def gateway_is_up():
    try:
        return requests.get(MERGED_SPEC_URL, timeout=TIMEOUT).ok
    except requests.RequestException:
        return False


# ---------------------------------------------------------------------
# Static tier -- the four declarations agree with each other
# ---------------------------------------------------------------------
class TestPrefixDeclarations(unittest.TestCase):
    """No Docker required. Compares the literals in the four files."""

    @classmethod
    def setUpClass(cls):
        missing = [
            p for p in (ROUTES_DOCS, NGINX_CONF, DASHBOARD_API_JS, VITE_CONFIG)
            if not os.path.exists(p)
        ]

        if missing:
            raise unittest.SkipTest(
                "source files not present (running outside a checkout?): "
                + ", ".join(missing)
            )

    def test_nginx_routes_both_prefixes(self):
        """nginx is the thing that actually moves the traffic."""

        conf = read(NGINX_CONF)

        for prefix in (DETECTION_PREFIX, REPORT_PREFIX):
            self.assertIn(
                f"location {prefix}/ {{",
                conf,
                f"deploy/nginx.conf has no location block for {prefix}/ -- "
                f"routes_docs.py writes that prefix into the merged spec, "
                f"so every path it advertises would 404",
            )

    def test_dashboard_fetches_the_report_prefix(self):
        """
        The dashboard's fetch base is the third copy of the prefix. If it
        drifts, the page loads and then stays empty.
        """

        source = read(DASHBOARD_API_JS)

        match = re.search(
            r'VITE_API_URL\s*\|\|\s*["\']([^"\']+)["\']', source
        )

        self.assertIsNotNone(
            match, "could not find the API_URL fallback in dashboard/src/api.js"
        )

        self.assertEqual(
            match.group(1),
            REPORT_PREFIX,
            "dashboard/src/api.js fetches a different prefix than the one "
            "routes_docs.py and nginx use",
        )

    def test_dev_proxy_matches_the_same_prefix(self):
        """
        The Vite dev proxy is the fourth copy, and the easiest to forget
        because production keeps working when it drifts.
        """

        source = read(VITE_CONFIG)

        self.assertIn(
            f"'{REPORT_PREFIX}'",
            source,
            "dashboard/vite.config.js proxies a different prefix, so "
            "`npm run dev` will 404 where the deployed stack works",
        )

        # The rewrite strips the prefix before forwarding. If it strips a
        # different string, the dev server forwards the wrong path.
        escaped = REPORT_PREFIX.replace("/", r"\/")

        self.assertIn(
            escaped,
            source,
            "the rewrite regex in dashboard/vite.config.js strips a "
            "different prefix than the one it proxies",
        )


# ---------------------------------------------------------------------
# Live tier -- the gateway serves what the merged spec advertises
# ---------------------------------------------------------------------
class TestGatewayServesTheMergedSpec(unittest.TestCase):
    """
    The static tier proves the files agree. This proves they agree with
    reality: every path in the merged document is routed by the gateway.
    """

    @classmethod
    def setUpClass(cls):
        if REPORT_PREFIX is None:
            raise unittest.SkipTest(f"{ROUTES_DOCS} not present")

        if not gateway_is_up():
            raise unittest.SkipTest(
                f"gateway not reachable at {MERGED_SPEC_URL} -- "
                f"start it with `docker compose -f deploy/docker-compose.yml up -d`"
            )

        cls.spec = requests.get(MERGED_SPEC_URL, timeout=TIMEOUT).json()

    def test_spec_advertises_both_services(self):
        """A half-built document would make the next test vacuous."""

        self.assertFalse(
            self.spec.get("x-memsoc-detection-unavailable", False),
            "the merged spec was built while the detection service was "
            "unreachable, so it only describes half the API",
        )

        prefixes = {
            DETECTION_PREFIX: 0,
            REPORT_PREFIX: 0,
        }

        for path in self.spec["paths"]:
            for prefix in prefixes:
                if path.startswith(prefix):
                    prefixes[prefix] += 1

        for prefix, count in prefixes.items():
            self.assertGreater(
                count, 0, f"no path in the merged spec starts with {prefix}"
            )

    def test_every_advertised_path_is_routed(self):
        """
        The actual drift check. A 404 means the gateway does not know a
        path the documentation tells people to call.
        """

        unrouted = []

        for path, operations in self.spec["paths"].items():

            request_path = re.sub(
                r"\{[^}]+\}", PATH_PARAM_PLACEHOLDER, path
            )

            for method in operations:

                url = f"{GATEWAY_BASE}{request_path}"

                try:
                    response = requests.request(
                        method.upper(),
                        url,
                        json={} if method.lower() in ("post", "put") else None,
                        timeout=TIMEOUT,
                    )
                except requests.RequestException as e:
                    unrouted.append(f"{method.upper()} {path} -> {e}")
                    continue

                # 404 is the signal: nginx has no location for this path.
                # Anything else (200, 400, 422, 500) means it routed and
                # the service answered, which is all we are testing.
                if response.status_code == 404:
                    unrouted.append(
                        f"{method.upper()} {path} -> 404 at {url}"
                    )

        self.assertEqual(
            [],
            unrouted,
            "the merged spec advertises paths the gateway does not serve. "
            "The prefixes in deploy/nginx.conf and "
            "src/memsoc/api/routes_docs.py have drifted:\n  "
            + "\n  ".join(unrouted),
        )

    def test_dashboard_data_path_is_routed(self):
        """
        Guards the dashboard's own prefix end to end, not just as a
        string comparison: this is the exact request the page makes.
        """

        url = f"{GATEWAY_BASE}{REPORT_PREFIX}/api/reports"

        response = requests.get(url, timeout=TIMEOUT)

        self.assertEqual(
            200,
            response.status_code,
            f"the dashboard's report list is not served at {url}",
        )

        self.assertIn("reports", response.json())


if __name__ == "__main__":
    unittest.main(verbosity=2)
