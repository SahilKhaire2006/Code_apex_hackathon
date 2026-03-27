"""
storage.py — Stage 3: DataStoragePipeline
Saves cleaned data to:
  • SQLite  → data/transactions/output/transactions.db
  • Pickle  → data/transactions/output/batch.pkl
"""

import os
import pickle
import sqlite3

import pandas as pd
from transactions.config import DATABASE_PATH, PICKLE_PATH, TABLE_NAME


class DataStoragePipeline:
    """Stage 3 — Storage."""

    def __init__(self, df: pd.DataFrame):
        self.df = df

    def run(self) -> dict:
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
        print("[Stage 3] Storage complete.\n")
        return result

    def _save_sqlite(self):
        conn = sqlite3.connect(DATABASE_PATH)
        try:
            self.df.to_sql(
                name=TABLE_NAME,
                con=conn,
                if_exists="replace",
                index=False,
                chunksize=10_000,
            )
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
            conn.commit()
            print(f"[Stage 3] SQLite  → {DATABASE_PATH}")
        finally:
            conn.close()

    def _save_pickle(self):
        with open(PICKLE_PATH, "wb") as f:
            pickle.dump(self.df, f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"[Stage 3] Pickle   → {PICKLE_PATH}")
