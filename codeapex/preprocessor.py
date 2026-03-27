"""
preprocessor.py — Stage 2: DataPreprocessingPipeline + RBI Compliance
Steps:
  1. Remove banned columns (e.g. 'country') — RBI requirement
  2. Drop rows with any NULL values
  3. Remove duplicate rows
  4. Normalize string fields (strip whitespace, lowercase where sensible)
  5. Validate schema completeness
  6. Run RBI compliance gate
"""

import pandas as pd
from config import BANNED_COLUMNS


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
        self.df = df.copy()
        self.drop_log: list[dict] = []   # records of dropped rows
        self.compliance = ComplianceReport()

    # ── Public entry point ────────────────────────────────────────────────────
    def run(self) -> tuple[pd.DataFrame, ComplianceReport]:
        """Execute all preprocessing steps and return cleaned DataFrame + report."""
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

    # ── Step 1 — Remove banned columns ───────────────────────────────────────
    def _remove_banned_columns(self):
        cols_to_drop = [c for c in BANNED_COLUMNS if c in self.df.columns]
        if cols_to_drop:
            self.df.drop(columns=cols_to_drop, inplace=True)
            print(f"[Stage 2] Removed banned columns: {cols_to_drop}")
        else:
            # Check case-insensitive
            ci_hits = [
                c for c in self.df.columns
                if c.lower() in [b.lower() for b in BANNED_COLUMNS]
            ]
            if ci_hits:
                self.df.drop(columns=ci_hits, inplace=True)
                print(f"[Stage 2] Removed banned columns (case-insensitive): {ci_hits}")
            else:
                print(f"[Stage 2] No banned columns found in dataset.")

    # ── Step 2 — NULL removal ─────────────────────────────────────────────────
    def _drop_null_rows(self):
        before = len(self.df)
        null_mask = self.df.isnull().any(axis=1)
        null_rows = self.df[null_mask]

        for idx, row in null_rows.iterrows():
            null_cols = row.index[row.isnull()].tolist()
            self.drop_log.append({
                "original_index": idx,
                "reason": f"NULL values in column(s): {null_cols}",
                "row_preview": row.fillna("<NULL>").to_dict(),
            })

        self.df = self.df[~null_mask].reset_index(drop=True)
        dropped = before - len(self.df)
        if dropped:
            print(f"[Stage 2] Dropped {dropped:,} rows with NULL values.")

    # ── Step 3 — Duplicate removal ────────────────────────────────────────────
    def _remove_duplicates(self):
        before = len(self.df)
        dup_mask = self.df.duplicated(keep="first")
        dup_rows = self.df[dup_mask]

        for idx, row in dup_rows.iterrows():
            self.drop_log.append({
                "original_index": idx,
                "reason": "Duplicate row",
                "row_preview": row.to_dict(),
            })

        self.df = self.df[~dup_mask].reset_index(drop=True)
        dropped = before - len(self.df)
        if dropped:
            print(f"[Stage 2] Dropped {dropped:,} duplicate rows.")

    # ── Step 4 — Normalize strings ────────────────────────────────────────────
    def _normalize_strings(self):
        """Strip leading/trailing whitespace from all string columns."""
        str_cols = self.df.select_dtypes(include=["object"]).columns
        for col in str_cols:
            self.df[col] = self.df[col].astype(str).str.strip()
        if len(str_cols):
            print(f"[Stage 2] Normalized whitespace in {len(str_cols)} string column(s).")

    # ── Step 5 — Schema validation ────────────────────────────────────────────
    def _validate_schema(self):
        """Ensure dataset still has columns after all drops."""
        if self.df.empty or len(self.df.columns) == 0:
            raise ValueError(
                "[Stage 2] FATAL: No columns remain after preprocessing. "
                "Cannot proceed to storage."
            )
        if len(self.df) == 0:
            raise ValueError(
                "[Stage 2] FATAL: All rows were dropped. "
                "Cannot proceed to storage."
            )
        print(f"[Stage 2] Schema valid: {len(self.df.columns)} columns, {len(self.df):,} rows.")

    # ── Step 6 — RBI Compliance gate ─────────────────────────────────────────
    def _run_rbi_compliance(self):
        print("[Stage 2] Running RBI compliance checks …")

        # Check 1: Country column absent
        lower_cols = [c.lower() for c in self.df.columns]
        country_absent = "country" not in lower_cols
        self.compliance.add_check(
            "Country column removed",
            country_absent,
            "" if country_absent else "Column 'country' still present — RBI violation.",
        )

        # Check 2: No NULLs remain
        null_total = self.df.isnull().sum().sum()
        no_nulls = null_total == 0
        self.compliance.add_check(
            "No NULL values",
            no_nulls,
            "" if no_nulls else f"{null_total} NULL(s) still present.",
        )

        # Check 3: No duplicates remain
        dup_count = self.df.duplicated().sum()
        no_dups = dup_count == 0
        self.compliance.add_check(
            "No duplicate rows",
            no_dups,
            "" if no_dups else f"{dup_count} duplicate(s) still present.",
        )

        # Check 4: Dataset not empty
        not_empty = len(self.df) > 0
        self.compliance.add_check(
            "Dataset not empty after cleaning",
            not_empty,
            "" if not_empty else "All rows were dropped during preprocessing.",
        )

        # Check 5: Column count reasonable (at least 1)
        has_columns = len(self.df.columns) >= 1
        self.compliance.add_check(
            "At least one column present",
            has_columns,
            "" if has_columns else "No columns remain in dataset.",
        )

    # ── Drop log printer ─────────────────────────────────────────────────────
    def print_drop_log(self):
        if not self.drop_log:
            print("[Stage 2] No rows were dropped.")
            return
        print(f"\n[Stage 2] Dropped Rows Log ({len(self.drop_log)} total):")
        print("-" * 60)
        for i, entry in enumerate(self.drop_log, 1):
            print(f"  [{i}] Index: {entry['original_index']}")
            print(f"       Reason : {entry['reason']}")
            # Print a short preview (first 3 fields)
            preview_items = list(entry["row_preview"].items())[:3]
            preview_str = ", ".join(f"{k}={v}" for k, v in preview_items)
            print(f"       Preview: {preview_str} …")
        print("-" * 60)
