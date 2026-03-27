"""
storage.py — Stage 3: DataStoragePipeline
Saves cleaned data to:
  • SQLite  → output/transactions.db  (indexed table)
  • Pickle  → output/batch.pkl        (ML-ready format)
No external API calls. No cloud storage.
"""

import os
import pickle
import sqlite3

import pandas as pd
from config import DATABASE_PATH, PICKLE_PATH, TABLE_NAME


class DataStoragePipeline:
    """Stage 3 — Storage."""

    def __init__(self, df: pd.DataFrame):
        self.df = df

    # ── Public entry point ────────────────────────────────────────────────────
    def run(self) -> dict:
        """
        Persist the DataFrame to SQLite and Pickle.
        Returns a dict with file paths and sizes.
        """
        print("[Stage 3] Starting storage …")

        self._save_sqlite()
        self._save_pickle()

        db_size = os.path.getsize(DATABASE_PATH)
        pkl_size = os.path.getsize(PICKLE_PATH)

        result = {
            "db_path": DATABASE_PATH,
            "db_size_bytes": db_size,
            "pkl_path": PICKLE_PATH,
            "pkl_size_bytes": pkl_size,
            "rows_stored": len(self.df),
        }

        print(f"[Stage 3] Storage complete.\n")
        return result

    # ── SQLite ────────────────────────────────────────────────────────────────
    def _save_sqlite(self):
        """Write DataFrame to SQLite with indexed columns."""
        conn = sqlite3.connect(DATABASE_PATH)
        try:
            # Write data (replace table if exists from previous run)
            self.df.to_sql(
                name=TABLE_NAME,
                con=conn,
                if_exists="replace",
                index=False,
                chunksize=10_000,
            )

            # Create indexes on all columns that look like IDs or dates
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({TABLE_NAME})")
            columns = [row[1] for row in cursor.fetchall()]

            index_candidates = [
                c for c in columns
                if any(
                    kw in c.lower()
                    for kw in ["id", "date", "time", "key", "ref", "num", "code"]
                )
            ]
            for col in index_candidates[:10]:  # cap at 10 indexes
                safe_col = col.replace(" ", "_").replace("-", "_")
                idx_name = f"idx_{TABLE_NAME}_{safe_col}"
                try:
                    cursor.execute(
                        f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON "{TABLE_NAME}" ("{col}")'
                    )
                except sqlite3.OperationalError:
                    pass  # skip if column name causes issues

            conn.commit()
            print(f"[Stage 3] SQLite  → {DATABASE_PATH}")
            print(f"          Table   : {TABLE_NAME}")
            print(f"          Indexes : {index_candidates or 'none (no ID/date columns detected)'}")
        finally:
            conn.close()

    # ── Pickle ────────────────────────────────────────────────────────────────
    def _save_pickle(self):
        """Serialize DataFrame as a Pickle file for ML pipelines."""
        with open(PICKLE_PATH, "wb") as f:
            pickle.dump(self.df, f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"[Stage 3] Pickle   → {PICKLE_PATH}")
