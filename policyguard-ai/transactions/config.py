"""
transactions/config.py — Configuration for the transaction processing pipeline.
Paths are relative to the policyguard-ai project root.
"""

import os

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # policyguard-ai/
OUTPUT_DIR = os.path.join(BASE_DIR, "data", "transactions", "output")

DATABASE_PATH = os.path.join(OUTPUT_DIR, "transactions.db")
PICKLE_PATH = os.path.join(OUTPUT_DIR, "batch.pkl")

# ─── Processing ───────────────────────────────────────────────────────────────
CHUNK_SIZE = 10_000          # rows per chunk for large files
SMALL_FILE_THRESHOLD = 10_000  # files with fewer rows → direct load
LARGE_CSV_STREAM_THRESHOLD_BYTES = 100 * 1024 * 1024  # 100 MB
SQLITE_WRITE_CHUNK_SIZE = 10_000

# ─── RBI Compliance ───────────────────────────────────────────────────────────
BANNED_COLUMNS = ["country"]   # columns that must be fully removed

# ─── Supported Formats ────────────────────────────────────────────────────────
SUPPORTED_EXTENSIONS = [".csv", ".xls", ".xlsx"]

# ─── SQLite ───────────────────────────────────────────────────────────────────
TABLE_NAME = "transactions"

# ─── Ensure output directory exists ──────────────────────────────────────────
os.makedirs(OUTPUT_DIR, exist_ok=True)
