"""
main.py — Entry point for the 3-Stage Data Pipeline
Usage:
    python main.py --file path/to/your_data.csv
"""

import argparse
import os
import sys

from config import DATABASE_PATH, PICKLE_PATH
from file_parser import FileParsingPipeline
from preprocessor import DataPreprocessingPipeline
from storage import DataStoragePipeline


# ─── Helpers ─────────────────────────────────────────────────────────────────
def human_size(num_bytes: int) -> str:
    """Convert bytes to a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"


def print_banner():
    print("=" * 62)
    print("   Production-Ready Python Data Pipeline")
    print("   3-Stage Architecture: Parse → Preprocess → Store")
    print("=" * 62)


def print_summary(
    input_rows: int,
    cleaned_rows: int,
    storage_info: dict,
    drop_count: int,
):
    print("\n" + "=" * 62)
    print("  PIPELINE SUMMARY")
    print("=" * 62)
    print(f"  Rows input          : {input_rows:,}")
    print(f"  Rows after cleaning : {cleaned_rows:,}")
    print(f"  Rows dropped        : {drop_count:,}")
    print(f"  Rows stored         : {storage_info['rows_stored']:,}")
    print("-" * 62)
    print(f"  STORAGE")
    print(f"  transactions.db     : {human_size(storage_info['db_size_bytes'])}")
    print(f"                        {storage_info['db_path']}")
    print(f"  batch.pkl           : {human_size(storage_info['pkl_size_bytes'])}")
    print(f"                        {storage_info['pkl_path']}")
    print("=" * 62 + "\n")


# ─── Main Orchestrator ────────────────────────────────────────────────────────
def run_pipeline(filepath: str):
    print_banner()

    if not os.path.exists(filepath):
        print(f"[ERROR] File not found: {filepath}")
        sys.exit(1)

    # ── Stage 1: Parse ───────────────────────────────────────────────────────
    parser = FileParsingPipeline(filepath)
    df_raw = parser.parse()
    input_rows = len(df_raw)

    # ── Stage 2: Preprocess + RBI Compliance ─────────────────────────────────
    preprocessor = DataPreprocessingPipeline(df_raw)
    df_clean, compliance = preprocessor.run()
    cleaned_rows = len(df_clean)

    # Print what was dropped and why
    preprocessor.print_drop_log()

    # Print RBI compliance report
    compliance.print_report()

    # ── Quality Gate ─────────────────────────────────────────────────────────
    if not compliance.passed:
        print("[GATE] ❌ RBI compliance FAILED. Aborting storage stage.")
        print("       Fix the issues listed above and re-run the pipeline.\n")
        sys.exit(2)

    print("[GATE] ✅ All quality gates passed. Proceeding to storage …\n")

    # ── Stage 3: Store ───────────────────────────────────────────────────────
    storage = DataStoragePipeline(df_clean)
    storage_info = storage.run()

    # ── Final Summary ─────────────────────────────────────────────────────────
    drop_count = input_rows - cleaned_rows
    print_summary(input_rows, cleaned_rows, storage_info, drop_count)

    print("✅ Pipeline completed successfully.\n")


# ─── CLI ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description="3-Stage Data Pipeline: Parse → Preprocess → Store"
    )
    ap.add_argument(
        "--file",
        required=True,
        help="Path to the input file (CSV, XLS, or XLSX)",
    )
    args = ap.parse_args()
    run_pipeline(args.file)


if __name__ == "__main__":
    main()
