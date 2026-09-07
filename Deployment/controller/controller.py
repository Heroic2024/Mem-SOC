import os
import subprocess
import sys


def run_command(command, cwd=None, env=None):
    print(f"\n$ {' '.join(command)}\n")

    result = subprocess.run(
        command,
        cwd=cwd,
        env=env
    )

    if result.returncode != 0:
        print(f"\n✗ Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)

    return result


def main():
    print("=" * 55)
    print("                 MemSOC SYSTEM")
    print("=" * 55)

    # ---------------------------------------------------------
    # 1. Ask how many logs
    # ---------------------------------------------------------
    while True:
        try:
            flows = int(input("\nHow many logs do you want to generate? "))

            if flows > 0:
                break

            print("Please enter a number greater than 0.")

        except ValueError:
            print("Please enter a valid number.")

    # ---------------------------------------------------------
    # 2. Generate logs
    # ---------------------------------------------------------
    print(f"\nGenerating {flows} logs...")

    env = os.environ.copy()
    env["MEMSOC_SAMPLE_SIZE"] = str(flows)

    run_command(
        [
            "python",
            "/app/log_generation/log_generation/nfv3_log_generator.py",
        ],
        env=env
    )

    print(f"\n✓ {flows} logs generated successfully.")

    # ---------------------------------------------------------
    # 3. Ask whether to start live capture
    # ---------------------------------------------------------
    while True:
        choice = input("\nStart live capture? (Y/N): ").strip().lower()

        if choice in ("y", "n"):
            break

        print("Please enter Y or N.")

    if choice == "n":
        print("\nLive capture cancelled.")
        print("MemSOC workflow stopped.")
        return

    # ---------------------------------------------------------
    # 4. Live capture
    # ---------------------------------------------------------
    print("\nStarting live capture...")

    run_command(
        [
            "python",
            "/app/LLMTriage/live_capture.py",
            "--reset",
        ]
    )

    print("\n✓ Live capture completed.")

    # ---------------------------------------------------------
    # 5. Wait for ENTER
    # ---------------------------------------------------------
    print("\nPress ENTER to generate the security report...")
    input()

    # ---------------------------------------------------------
    # 6. Generate report
    # ---------------------------------------------------------
    print("\nGenerating security report...")

    run_command(
        [
            "python",
            "/app/LLMTriage/generate_report.py",
            "--limit",
            str(flows),
        ]
    )

    # ---------------------------------------------------------
    # 7. Complete
    # ---------------------------------------------------------
    print("\n" + "=" * 55)
    print("              MemSOC WORKFLOW COMPLETE")
    print("=" * 55)
    print("\nDashboard: http://localhost:8081")
    print("Report API: http://localhost:8001")
    print("=" * 55)


if __name__ == "__main__":
    main()