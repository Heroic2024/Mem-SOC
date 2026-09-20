"""
Interactive driver for the complete MemSOC workflow.

Asks how many flows to generate, generates them, runs live capture against
the detection API, then generates the security report. Nothing here
reimplements a stage -- each step is the same module the rest of the
system uses, invoked as `python -m memsoc.<module>` so it resolves through
the installed package rather than a hardcoded container path.

    python -m memsoc.controller
"""

import os
import subprocess
import sys

from memsoc import paths

# Where the workflow ends up. Printed at the end so the operator does not
# have to go looking in docker-compose.yml for the published ports.
#
# These are HOST-facing URLs for a human to click, not the in-network
# addresses this process uses. paths.REPORT_BASE resolves to
# http://report:8001 inside the Docker network, which is useless in a
# browser, so compose passes the published localhost URLs instead.
DASHBOARD_URL = os.environ.get("MEMSOC_DASHBOARD_URL", "http://localhost:8080")
REPORT_URL = os.environ.get("MEMSOC_REPORT_URL", "http://localhost:8001")


def run_module(module, args=None, env=None):
    """Run one MemSOC module as a subprocess, failing loudly."""

    command = [sys.executable, "-u", "-m", module] + list(args or [])

    print(f"\n$ {' '.join(command)}\n")

    result = subprocess.run(command, env=env)

    if result.returncode != 0:
        print(f"\n[FAIL] {module} exited with code {result.returncode}")
        sys.exit(result.returncode)

    return result


def ask_flow_count():
    while True:
        try:
            flows = int(input("\nHow many logs do you want to generate? "))

            if flows > 0:
                return flows

            print("Please enter a number greater than 0.")

        except ValueError:
            print("Please enter a valid number.")


def ask_yes_no(question):
    while True:
        choice = input(f"\n{question} (Y/N): ").strip().lower()

        if choice in ("y", "n"):
            return choice == "y"

        print("Please enter Y or N.")


def main():
    print("=" * 55)
    print("                 MemSOC SYSTEM")
    print("=" * 55)

    paths.ensure_dirs()

    # ---------------------------------------------------------
    # 1. Generate logs
    # ---------------------------------------------------------
    flows = ask_flow_count()

    print(f"\nGenerating {flows} logs...")

    env = os.environ.copy()
    env["MEMSOC_SAMPLE_SIZE"] = str(flows)

    run_module("memsoc.logstream.nfv3_log_generator", env=env)

    print(f"\n[OK] {flows} logs generated.")

    # ---------------------------------------------------------
    # 2. Live capture
    # ---------------------------------------------------------
    if not ask_yes_no("Start live capture?"):
        print("\nLive capture cancelled. MemSOC workflow stopped.")
        return

    print("\nStarting live capture...")

    run_module("memsoc.triage.live_capture", ["--reset"])

    print("\n[OK] Live capture completed.")

    # ---------------------------------------------------------
    # 3. Report
    # ---------------------------------------------------------
    print("\nPress ENTER to generate the security report...")
    input()

    print("\nGenerating security report...")

    run_module("memsoc.triage.generate_report", ["--limit", str(flows)])

    # ---------------------------------------------------------
    # 4. Done
    # ---------------------------------------------------------
    print("\n" + "=" * 55)
    print("              MemSOC WORKFLOW COMPLETE")
    print("=" * 55)
    print(f"\nDashboard : {DASHBOARD_URL}")
    print(f"Report API: {REPORT_URL}")
    print("=" * 55)


if __name__ == "__main__":
    main()
