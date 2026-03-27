"""
preprocessor.py — Stage 2: DataPreprocessingPipeline + RBI Compliance
Steps:
  1. Remove banned columns (e.g. 'country') — RBI requirement
  2. Drop rows with any NULL values
  3. Remove duplicate rows
  4. Normalize string fields (strip whitespace)
  5. Validate schema completeness
  6. Run RBI compliance gate
"""

import pandas as pd
from transactions.config import BANNED_COLUMNS


# ── Compliance Result Container ───────────────────────────────────────────────
class ComplianceReport:
    def __init__(self):
        self.passed: bool = True
        self.checks: list[dict] = []

    def add_check(self, name: str, passed: bool, detail: str = ""):
        status = "PASS" if passed else "FAIL"
        self.checks.append({"name": name, "status": status, "detail": detail})
        if not passed:
            self.passed = False

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks": self.checks,
        }

    def print_report(self):
        print("\n" + "=" * 60)
        print("  RBI COMPLIANCE REPORT")
        print("=" * 60)
        for chk in self.checks:
            icon = "✅" if chk["status"] == "PASS" else "❌"
            print(f"  {icon} [{chk['status']}] {chk['name']}")
            if chk["detail"]:
                print(f"          → {chk['detail']}")
        print("-" * 60)
        overall = "✅ OVERALL: PASS" if self.passed else "❌ OVERALL: FAIL"
        print(f"  {overall}")
        print("=" * 60 + "\n")


# ── Main Pipeline Class ───────────────────────────────────────────────────────
class DataPreprocessingPipeline:
    """Stage 2 — Preprocessing + RBI Compliance."""

    def __init__(self, df: pd.DataFrame):
        self.original_count = len(df)
        # Reuse the incoming frame to avoid doubling memory for large files.
        self.df = df
        self.drop_log: list[dict] = []
        self.compliance = ComplianceReport()

    def run(self) -> tuple[pd.DataFrame, ComplianceReport]:
        print("[Stage 2] Starting preprocessing …")

        self._remove_banned_columns()
        self._drop_null_rows()
        self._remove_duplicates()
        self._normalize_strings()
        self._validate_schema()
        self._run_rbi_compliance()

        cleaned_count = len(self.df)
        dropped_count = self.original_count - cleaned_count
        print(
            f"[Stage 2] Complete. "
            f"{self.original_count:,} → {cleaned_count:,} rows "
            f"({dropped_count:,} dropped)\n"
        )
        return self.df, self.compliance

    def _remove_banned_columns(self):
        cols_to_drop = [c for c in BANNED_COLUMNS if c in self.df.columns]
        if cols_to_drop:
            self.df.drop(columns=cols_to_drop, inplace=True)
            print(f"[Stage 2] Removed banned columns: {cols_to_drop}")
        else:
            ci_hits = [
                c for c in self.df.columns
                if c.lower() in [b.lower() for b in BANNED_COLUMNS]
            ]
            if ci_hits:
                self.df.drop(columns=ci_hits, inplace=True)
                print(f"[Stage 2] Removed banned columns (case-insensitive): {ci_hits}")

    def _drop_null_rows(self):
        before = len(self.df)
        null_mask = self.df.isnull().any(axis=1)
        null_rows = self.df[null_mask].head(25)
        for idx, row in null_rows.iterrows():
            null_cols = row.index[row.isnull()].tolist()
            self.drop_log.append({
                "original_index": idx,
                "reason": f"NULL values in column(s): {null_cols}",
            })
        self.df = self.df[~null_mask].reset_index(drop=True)
        dropped = before - len(self.df)
        if dropped:
            print(f"[Stage 2] Dropped {dropped:,} rows with NULL values.")

    def _remove_duplicates(self):
        before = len(self.df)
        dup_mask = self.df.duplicated(keep="first")
        for idx, _ in self.df[dup_mask].head(25).iterrows():
            self.drop_log.append({"original_index": idx, "reason": "Duplicate row"})
        self.df = self.df[~dup_mask].reset_index(drop=True)
        dropped = before - len(self.df)
        if dropped:
            print(f"[Stage 2] Dropped {dropped:,} duplicate rows.")

    def _normalize_strings(self):
        str_cols = self.df.select_dtypes(include=["object"]).columns
        for col in str_cols:
            self.df[col] = self.df[col].astype(str).str.strip()
        if len(str_cols):
            print(f"[Stage 2] Normalized whitespace in {len(str_cols)} string column(s).")

    def _validate_schema(self):
        if self.df.empty or len(self.df.columns) == 0:
            raise ValueError("[Stage 2] FATAL: No columns remain after preprocessing.")
        if len(self.df) == 0:
            raise ValueError("[Stage 2] FATAL: All rows were dropped.")
        print(f"[Stage 2] Schema valid: {len(self.df.columns)} columns, {len(self.df):,} rows.")

    def _run_rbi_compliance(self):
        print("[Stage 2] Running RBI compliance checks …")

        lower_cols = [c.lower() for c in self.df.columns]
        country_absent = "country" not in lower_cols
        self.compliance.add_check(
            "Country column removed", country_absent,
            "" if country_absent else "Column 'country' still present — RBI violation.",
        )

        null_total = self.df.isnull().sum().sum()
        no_nulls = null_total == 0
        self.compliance.add_check(
            "No NULL values", no_nulls,
            "" if no_nulls else f"{null_total} NULL(s) still present.",
        )

        dup_count = self.df.duplicated().sum()
        no_dups = dup_count == 0
        self.compliance.add_check(
            "No duplicate rows", no_dups,
            "" if no_dups else f"{dup_count} duplicate(s) still present.",
        )

        not_empty = len(self.df) > 0
        self.compliance.add_check(
            "Dataset not empty after cleaning", not_empty,
            "" if not_empty else "All rows were dropped during preprocessing.",
        )

        has_columns = len(self.df.columns) >= 1
        self.compliance.add_check(
            "At least one column present", has_columns,
            "" if has_columns else "No columns remain in dataset.",
        )

    def print_drop_log(self):
        if not self.drop_log:
            print("[Stage 2] No rows were dropped.")
            return
        print(f"\n[Stage 2] Dropped Rows Log (showing up to {len(self.drop_log)} samples):")
