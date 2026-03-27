"""
file_parser.py — Stage 1: FileParsingPipeline
Accepts CSV, XLS, XLSX files of any size.
Auto-detects schema, infers types.
Routes small files (<10K rows) to direct load,
large files (>=10K rows) to chunked processing.
"""

import os
import pandas as pd
from transactions.config import CHUNK_SIZE, SMALL_FILE_THRESHOLD, SUPPORTED_EXTENSIONS


class FileParsingPipeline:
    """Stage 1 — File Parsing."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.ext = os.path.splitext(filepath)[1].lower()
        self.schema: dict = {}
        self.row_count: int = 0
        self.is_chunked: bool = False

    # ── Public entry point ────────────────────────────────────────────────────
    def parse(self) -> pd.DataFrame:
        """
        Parse the file and return a DataFrame.
        Automatically chooses direct-load or chunked processing.
        """
        self._validate_extension()

        print(f"\n[Stage 1] Parsing file: {os.path.basename(self.filepath)}")
        print(f"          Format      : {self.ext.upper()}")

        estimated_rows = self._estimate_row_count()

        if estimated_rows is not None and estimated_rows < SMALL_FILE_THRESHOLD:
            df = self._direct_load()
        else:
            df = self._chunked_load()

        self.row_count = len(df)
        self.schema = self._infer_schema(df)
        self._print_schema()

        print(f"[Stage 1] Loaded {self.row_count:,} rows, {len(df.columns)} columns.\n")
        return df

    # ── Private helpers ───────────────────────────────────────────────────────
    def _validate_extension(self):
        if self.ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type '{self.ext}'. "
                f"Supported: {SUPPORTED_EXTENSIONS}"
            )

    def _estimate_row_count(self) -> int | None:
        if self.ext == ".csv":
            with open(self.filepath, "r", encoding="utf-8", errors="replace") as f:
                count = sum(1 for _ in f) - 1
            return max(count, 0)
        return None

    def _direct_load(self) -> pd.DataFrame:
        print(f"[Stage 1] Strategy  : Direct load (< {SMALL_FILE_THRESHOLD:,} rows)")
        self.is_chunked = False
        return self._read_file()

    def _chunked_load(self) -> pd.DataFrame:
        print(f"[Stage 1] Strategy  : Chunked load (chunk size = {CHUNK_SIZE:,})")
        self.is_chunked = True

        if self.ext == ".csv":
            chunks = []
            chunk_num = 0
            for chunk in pd.read_csv(
                self.filepath,
                chunksize=CHUNK_SIZE,
                encoding="utf-8",
                encoding_errors="replace",
                low_memory=False,
            ):
                chunk_num += 1
                print(f"            Chunk {chunk_num}: {len(chunk):,} rows")
                chunks.append(chunk)
            return pd.concat(chunks, ignore_index=True)
        else:
            df = self._read_file()
            n = len(df)
            if n >= SMALL_FILE_THRESHOLD:
                print(f"            Excel file with {n:,} rows — loaded in one pass.")
            return df

    def _read_file(self) -> pd.DataFrame:
        if self.ext == ".csv":
            return pd.read_csv(
                self.filepath,
                encoding="utf-8",
                encoding_errors="replace",
                low_memory=False,
            )
        elif self.ext == ".xlsx":
            return pd.read_excel(self.filepath, engine="openpyxl")
        elif self.ext == ".xls":
            return pd.read_excel(self.filepath, engine="xlrd")
        else:
            raise ValueError(f"Unsupported extension: {self.ext}")

    def _infer_schema(self, df: pd.DataFrame) -> dict:
        schema = {}
        for col in df.columns:
            dtype = df[col].dtype
            if pd.api.types.is_integer_dtype(dtype):
                schema[col] = "integer"
            elif pd.api.types.is_float_dtype(dtype):
                schema[col] = "float"
            elif pd.api.types.is_bool_dtype(dtype):
                schema[col] = "boolean"
            elif pd.api.types.is_datetime64_any_dtype(dtype):
                schema[col] = "datetime"
            else:
                sample = df[col].dropna().head(100)
                try:
                    # infer_datetime_format removed — deprecated in pandas 2.x
                    pd.to_datetime(sample)
                    schema[col] = "datetime (inferred)"
                except Exception:
                    schema[col] = "string"
        return schema

    def _print_schema(self):
        print("[Stage 1] Auto-detected schema:")
        for col, dtype in self.schema.items():
            print(f"            {col:<30} → {dtype}")
