#!/usr/bin/env python3
# ==============================================================================
# recursive_ml_orchestrator.py -- Autonomous 24/7 ML pipeline loop.
#
# This script creates a powerful feedback loop for the system:
# 1. RUN: Executes the main arbitrage pipeline for a set number of cycles.
# 2. COLLECT: Gathers performance data from the execution traces.
# 3. TRAIN: Retrains the ML Alpha model on the newly collected data.
# 4. DEPLOY: The next pipeline run uses the improved model.
# 5. REPEAT.
# ==============================================================================

import argparse
import subprocess
import sys
import time
from decimal import Decimal

from .paths import repo_path


def run_command(command: list[str], description: str) -> bool:
    print(f"\n--- [ORCHESTRATOR] Running: {description} ---")
    print(f"Executing: {' '.join(command)}")
    try:
        proc = subprocess.run(
            command,
            cwd=str(repo_path()),
            check=True,
            text=True,
            capture_output=True,
        )
        print(proc.stdout)
        if proc.stderr:
            print("--- STDERR ---")
            print(proc.stderr)
        print(f"--- [SUCCESS] {description} ---")
        return True
    except subprocess.CalledProcessError as e:
        print(f"--- [FAILED] {description} ---")
        print(f"Return code: {e.returncode}")
        print("--- STDOUT ---")
        print(e.stdout)
        print("--- STDERR ---")
        print(e.stderr)
        return False
    except Exception as e:
        print(f"--- [FAILED] An unexpected error occurred: {e} ---")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the autonomous ML orchestrator loop.")
    parser.add_argument("--loops", type=int, default=1, help="Number of full Run-Collect-Train loops to execute. 0 for infinite.")
    parser.add_argument("--cycles", type=int, default=25, help="Number of pipeline cycles to run per loop.")
    parser.add_argument("--principal", type=float, default=50000, help="Flash loan principal in USD.")
    args = parser.parse_args()

    loop_count = 0
    while args.loops == 0 or loop_count < args.loops:
        loop_count += 1
        print(f"\n============================================================")
        print(f"  ORCHESTRATOR LOOP {loop_count} / {args.loops or '∞'} STARTING")
        print(f"============================================================")

        # 1. RUN: Execute the main pipeline
        pipeline_command = [
            sys.executable,
            "-m", "omega_v5.main",
            "--ticks", str(args.cycles),
            "--principal", str(args.principal),
        ]
        if not run_command(pipeline_command, f"{args.cycles}-Cycle Arbitrage Pipeline"):
            print("[FATAL] Pipeline execution failed. Halting orchestrator.")
            return 1

        # 2. COLLECT: Gather training data
        collector_command = [sys.executable, "-m", "omega_v5.ml_data_collector"]
        if not run_command(collector_command, "ML Data Collection"):
            print("[WARNING] ML data collection failed. Skipping training for this loop.")
            time.sleep(60)
            continue

        # 3. TRAIN: Retrain the model
        trainer_command = [sys.executable, "scripts/ml/train_vqc_ranker.py"]
        if not run_command(trainer_command, "ML Model Training"):
            print("[WARNING] ML model training failed. The system will continue with the previous model.")
            time.sleep(60)
            continue

        print(f"\n[SUCCESS] Orchestrator loop {loop_count} complete.")
        if args.loops != 0 and loop_count < args.loops:
            print("Pausing before next loop...")
            time.sleep(10)

    print("\nAll orchestrator loops complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())