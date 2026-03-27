"""
transactions/pipeline.py — Orchestrator for the 3-stage transaction pipeline.
Wraps FileParsingPipeline → DataPreprocessingPipeline → DataStoragePipeline
and returns a structured dict suitable for the FastAPI /validate endpoint.
"""

import os
import asyncio
import sqlite3
from pathlib import Path
from typing import Optional

import pandas as pd

from core.logger import logger
from transactions.file_parser import FileParsingPipeline
from transactions.preprocessor import DataPreprocessingPipeline
from transactions.storage import DataStoragePipeline
from transactions.config import (
    DATABASE_PATH,
    TABLE_NAME,
    CHUNK_SIZE,
    LARGE_CSV_STREAM_THRESHOLD_BYTES,
    SQLITE_WRITE_CHUNK_SIZE,
)


def _summarize_failed_checks(checks: list[dict], sink: dict[str, int]) -> None:
    for check in checks:
        if check.get("status") == "FAIL":
            name = str(check.get("name", "Unknown compliance check"))
            sink[name] = sink.get(name, 0) + 1


def _create_indexes(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({TABLE_NAME})")
    columns = [row[1] for row in cursor.fetchall()]
    index_candidates = [
        c for c in columns
        if any(kw in c.lower() for kw in ["id", "date", "time", "key", "ref", "num", "code"])
    ]
    for col in index_candidates[:10]:
        safe_col = col.replace(" ", "_").replace("-", "_")
        idx_name = f"idx_{TABLE_NAME}_{safe_col}"
        try:
            cursor.execute(
                f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON "{TABLE_NAME}" ("{col}")'
            )
        except sqlite3.OperationalError:
            pass


def _run_large_csv_streaming_pipeline(filepath: str, sid: str, filename: str) -> dict:
    logger.info(
        f"[TxnPipeline:{sid}] Using streaming mode for large CSV "
        f"({os.path.getsize(filepath):,} bytes)"
    )

    input_rows = 0
    rows_stored = 0
    dropped_rows = 0
    failed_checks: dict[str, int] = {}
    compliance_passed = True
    first_write = True

    conn = sqlite3.connect(DATABASE_PATH)
    try:
        for chunk_num, chunk in enumerate(
            pd.read_csv(
                filepath,
                chunksize=CHUNK_SIZE,
                encoding="utf-8",
                encoding_errors="replace",
                low_memory=True,
            ),
            start=1,
        ):
            chunk_rows = len(chunk)
            input_rows += chunk_rows
            logger.info(
                f"[TxnPipeline:{sid}] Streaming chunk {chunk_num}: {chunk_rows:,} rows"
            )

            preprocessor = DataPreprocessingPipeline(chunk)
            df_clean, compliance = preprocessor.run()

            cleaned_rows = len(df_clean)
            rows_stored += cleaned_rows
            dropped_rows += chunk_rows - cleaned_rows
            compliance_passed = compliance_passed and compliance.passed
            _summarize_failed_checks(compliance.checks, failed_checks)

            if cleaned_rows > 0:
                df_clean.to_sql(
                    name=TABLE_NAME,
                    con=conn,
                    if_exists="replace" if first_write else "append",
                    index=False,
                    chunksize=SQLITE_WRITE_CHUNK_SIZE,
                )
                first_write = False

        if not first_write:
            _create_indexes(conn)
            conn.commit()

    finally:
        conn.close()

    violations = [
        {
            "rule": name,
            "detail": f"Failed in {count} chunk(s)",
            "severity": "HIGH",
            "verdict": "VIOLATION",
        }
        for name, count in failed_checks.items()
    ]

    if dropped_rows > 0:
        violations.append({
            "rule": "Data Quality: Null/Duplicate Rows",
            "detail": f"{dropped_rows:,} rows dropped during preprocessing",
            "severity": "MEDIUM",
            "verdict": "WARNING",
        })

    return {
        "status": "complete",
        "filename": filename,
        "rows_input": input_rows,
        "rows_stored": rows_stored,
        "rows_dropped": dropped_rows,
        "compliance_passed": compliance_passed,
        "compliance_checks": [],
        "violations_count": len(violations),
        "violations": violations,
        "db_path": DATABASE_PATH,
        "error": None,
    }


def run_transaction_pipeline(filepath: str, session_id: Optional[str] = None) -> dict:
    """
    Run the full 3-stage transaction processing pipeline synchronously.

    Args:
        filepath: Absolute path to the uploaded CSV/XLS/XLSX file.
        session_id: Optional session ID for correlation logging.

    Returns:
        {
          "status": "complete" | "failed",
          "filename": str,
          "rows_input": int,
          "rows_stored": int,
          "rows_dropped": int,
          "compliance_passed": bool,
          "compliance_checks": list[dict],
          "violations_count": int,
          "violations": list[dict],   # rows that failed RBI compliance checks
          "db_path": str,
          "error": str | None,
        }
    """
    filename = Path(filepath).name
    sid = session_id or "N/A"
    logger.info(f"[TxnPipeline:{sid}] Starting — {filename}")

    try:
        if (
            str(filepath).lower().endswith(".csv")
            and os.path.getsize(filepath) >= LARGE_CSV_STREAM_THRESHOLD_BYTES
        ):
            return _run_large_csv_streaming_pipeline(filepath, sid, filename)

        # ── Stage 1: Parse ────────────────────────────────────────────────────
        parser = FileParsingPipeline(filepath)
        df_raw = parser.parse()
        input_rows = len(df_raw)
        logger.info(f"[TxnPipeline:{sid}] Stage 1 complete — {input_rows:,} rows parsed")

        # ── Stage 2: Preprocess + RBI Compliance ─────────────────────────────
        preprocessor = DataPreprocessingPipeline(df_raw)
        df_clean, compliance = preprocessor.run()
        preprocessor.print_drop_log()
        compliance.print_report()
        cleaned_rows = len(df_clean)
        dropped_rows = input_rows - cleaned_rows
        logger.info(
            f"[TxnPipeline:{sid}] Stage 2 complete — "
            f"{cleaned_rows:,} clean rows, {dropped_rows:,} dropped, "
            f"compliance={'PASS' if compliance.passed else 'FAIL'}"
        )

        # Collect violation rows (failed RBI checks as "violation" items)
        violations = []
        if not compliance.passed:
            for check in compliance.checks:
                if check["status"] == "FAIL":
                    violations.append({
                        "rule": check["name"],
                        "detail": check.get("detail", ""),
                        "severity": "HIGH",
                        "verdict": "VIOLATION",
                    })

        # Also log dropped row count as a violation metric
        if dropped_rows > 0:
            violations.append({
                "rule": "Data Quality: Null/Duplicate Rows",
                "detail": f"{dropped_rows:,} rows dropped during preprocessing",
                "severity": "MEDIUM",
                "verdict": "WARNING",
            })

        # ── Quality Gate (non-fatal in API mode — we still store clean data) ─
        if compliance.passed:
            # ── Stage 3: Store ────────────────────────────────────────────────
            storage = DataStoragePipeline(df_clean)
            storage_info = storage.run()
            logger.info(
                f"[TxnPipeline:{sid}] Stage 3 complete — "
                f"{storage_info['rows_stored']:,} rows stored to SQLite"
            )
        else:
            storage_info = {"rows_stored": 0, "db_path": "", "db_size_bytes": 0}
            logger.warning(f"[TxnPipeline:{sid}] Skipping storage — compliance FAILED")

        return {
            "status": "complete",
            "filename": filename,
            "rows_input": input_rows,
            "rows_stored": storage_info["rows_stored"],
            "rows_dropped": dropped_rows,
            "compliance_passed": compliance.passed,
            "compliance_checks": compliance.checks,
            "violations_count": len(violations),
            "violations": violations,
            "db_path": storage_info.get("db_path", ""),
            "error": None,
        }

    except Exception as exc:
        logger.error(f"[TxnPipeline:{sid}] FAILED — {exc}")
        return {
            "status": "failed",
            "filename": filename,
            "rows_input": 0,
            "rows_stored": 0,
            "rows_dropped": 0,
            "compliance_passed": False,
            "compliance_checks": [],
            "violations_count": 1,
            "violations": [{"rule": "Pipeline Error", "detail": str(exc), "severity": "CRITICAL", "verdict": "ERROR"}],
            "db_path": "",
            "error": str(exc),
        }


async def run_transaction_pipeline_async(filepath: str, session_id: Optional[str] = None) -> dict:
    """Async wrapper — runs the synchronous pipeline in a thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, run_transaction_pipeline, filepath, session_id)
