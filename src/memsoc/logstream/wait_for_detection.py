"""
Block until the `detection` service reports healthy, then hand off to
run_pipeline.py.

run_pipeline.py's own readiness check is a single probe -- correct when it
just started its own uvicorn subprocess and polled it in a loop first, but
this container runs with --no-api against a *separate* container whose
model load (the 37MB multiclass pickle) can take a while after `docker
compose up` starts it. Without a retry loop here, log_generation would
race detection and fail before it ever finishes loading.
"""

import os
import sys
import time
import urllib.request

from memsoc import paths

TIMEOUT = int(os.environ.get("MEMSOC_WAIT_TIMEOUT", "180"))
POLL_INTERVAL = 2.0


def wait() -> None:
    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(paths.API_HEALTH, timeout=5) as resp:
                if resp.status == 200:
                    print(f"  detection API healthy at {paths.API_HEALTH}")
                    return
        except OSError:
            pass
        print(f"  waiting for {paths.API_HEALTH} ...")
        time.sleep(POLL_INTERVAL)
    print(f"  FAIL: {paths.API_HEALTH} not healthy after {TIMEOUT}s")
    sys.exit(1)


if __name__ == "__main__":
    wait()
