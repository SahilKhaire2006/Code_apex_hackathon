import sqlite3
import json
from pathlib import Path
from core.logger import logger


class RuleRegistrySQLite:
    """Local SQLite registry for structured rule storage — extended with provenance fields."""

    def __init__(self, db_path: str = "registry/rules.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._migrate_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rules (
                    rule_id TEXT PRIMARY KEY,

                    -- Core Identity
                    title TEXT NOT NULL,
                    category TEXT,
                    severity TEXT,
                    logic_type TEXT,

                    -- Legal Reference
                    page_number INTEGER,
                    paragraph_number TEXT,
                    act_section TEXT,
                    circular_reference TEXT,

                    -- Text Fields
                    source_clause TEXT,
                    description TEXT,
                    plain_english TEXT,
                    violation_message_template TEXT,

                    -- Applicability
                    applicable_entity TEXT DEFAULT 'ALL',

                    -- Tagging
                    metadata_tags TEXT,

                    -- Condition Engine
                    condition_field TEXT,
                    condition_operator TEXT,
                    condition_value TEXT,
                    condition_unit TEXT,

                    -- Quality & Review
                    confidence_score REAL DEFAULT 1.0,
                    is_active INTEGER DEFAULT 1,
                    needs_review INTEGER DEFAULT 1,

                    -- Status (FIX 2)
                    status TEXT DEFAULT 'NEW',

                    -- Provenance Fields (FIX 1)
                    source_document_name TEXT,
                    source_document_type TEXT,
                    source_document_date TEXT,
                    last_modified_by TEXT,
                    modification_summary TEXT,
                    provenance_chain TEXT DEFAULT '[]',
                    rule_history TEXT DEFAULT '[]',
                    parent_rule_id TEXT,
                    supersedes_rule_id TEXT,
                    reference_count INTEGER DEFAULT 1,

                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Ingestion documents tracker
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ingestion_documents (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    document_type TEXT NOT NULL,
                    document_date TEXT,
                    total_rules_extracted INTEGER DEFAULT 0,
                    new_rules INTEGER DEFAULT 0,
                    modified_rules INTEGER DEFAULT 0,
                    existing_rules INTEGER DEFAULT 0,
                    superseded_rules INTEGER DEFAULT 0,
                    clarification_rules INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
        logger.info(f"SQLite Rule Registry initialized at {self.db_path}")

    def _migrate_db(self):
        """Add provenance columns to existing databases (non-destructive migration)."""
        new_columns = [
            ("status", "TEXT DEFAULT 'NEW'"),
            ("source_document_name", "TEXT"),
            ("source_document_type", "TEXT"),
            ("source_document_date", "TEXT"),
            ("last_modified_by", "TEXT"),
            ("modification_summary", "TEXT"),
            ("provenance_chain", "TEXT DEFAULT '[]'"),
            ("rule_history", "TEXT DEFAULT '[]'"),
            ("parent_rule_id", "TEXT"),
            ("supersedes_rule_id", "TEXT"),
            ("reference_count", "INTEGER DEFAULT 1"),
        ]
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(rules)")
            existing_cols = {row[1] for row in cursor.fetchall()}
            for col_name, col_def in new_columns:
                if col_name not in existing_cols:
                    try:
                        cursor.execute(f"ALTER TABLE rules ADD COLUMN {col_name} {col_def}")
                        logger.info(f"[SQLite] Migration: added column '{col_name}'")
                    except Exception as e:
                        logger.warning(f"[SQLite] Migration skipped '{col_name}': {e}")
            conn.commit()

    # ── ALLOWED COLUMNS (full set) ────────────────────────────────────────

    _ALLOWED_COLUMNS = {
        "rule_id", "title", "category", "severity", "logic_type",
        "page_number", "paragraph_number", "act_section", "circular_reference",
        "source_clause", "description", "plain_english", "violation_message_template",
        "applicable_entity", "metadata_tags",
        "condition_field", "condition_operator", "condition_value", "condition_unit",
        "confidence_score", "is_active", "needs_review",
        # Provenance fields
        "status", "source_document_name", "source_document_type", "source_document_date",
        "last_modified_by", "modification_summary", "provenance_chain", "rule_history",
        "parent_rule_id", "supersedes_rule_id", "reference_count",
    }

    def upsert_rule(self, rule_dict: dict):
        rule_copy = rule_dict.copy()

        # Serialize list/dict fields to JSON strings
        for field in ("metadata_tags", "provenance_chain", "rule_history"):
            if field in rule_copy and isinstance(rule_copy[field], (list, dict)):
                rule_copy[field] = json.dumps(rule_copy[field])

        # Convert bool → int for SQLite
        rule_copy["is_active"] = 1 if rule_copy.get("is_active", True) else 0
        rule_copy["needs_review"] = 1 if rule_copy.get("needs_review", True) else 0

        # Filter to allowed schema columns
        rule_copy = {k: v for k, v in rule_copy.items() if k in self._ALLOWED_COLUMNS}

        columns = ", ".join(rule_copy.keys())
        placeholders = ", ".join(["?" for _ in rule_copy])
        update_clauses = ", ".join([
            f"{k}=excluded.{k}"
            for k in rule_copy.keys()
            if k != "rule_id"
        ])

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            query = f"""
                INSERT INTO rules ({columns})
                VALUES ({placeholders})
                ON CONFLICT(rule_id) DO UPDATE SET {update_clauses}
            """
            cursor.execute(query, list(rule_copy.values()))
            conn.commit()

    def upsert_ingestion_document(self, doc: dict):
        """Record a processed document in the ingestion_documents table."""
        cols = ", ".join(doc.keys())
        placeholders = ", ".join(["?" for _ in doc])
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO ingestion_documents ({cols}) VALUES ({placeholders})",
                list(doc.values()),
            )
            conn.commit()

    def fetch_all(self) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rules")
            rows = [dict(row) for row in cursor.fetchall()]
            for row in rows:
                for field in ("metadata_tags", "provenance_chain", "rule_history"):
                    if row.get(field):
                        try:
                            row[field] = json.loads(row[field])
                        except Exception:
                            row[field] = []
            return rows

    def fetch_by_category(self, category: str) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rules WHERE category = ?", (category,))
            return [dict(row) for row in cursor.fetchall()]

    def fetch_pending_review(self) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rules WHERE needs_review = 1")
            return [dict(row) for row in cursor.fetchall()]

    def fetch_by_status(self, status: str) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rules WHERE status = ?", (status,))
            return [dict(row) for row in cursor.fetchall()]

    def fetch_by_source_document(self, source_document_name: str) -> list:
        """Check if rules from this document already exist locally."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM rules WHERE source_document_name = ?",
                (source_document_name,)
            )
            rows = [dict(row) for row in cursor.fetchall()]
            for row in rows:
                for field in ("metadata_tags", "provenance_chain", "rule_history"):
                    if row.get(field):
                        try:
                            row[field] = json.loads(row[field])
                        except Exception:
                            row[field] = []
            return rows

    def approve_rule(self, rule_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE rules SET needs_review = 0 WHERE rule_id = ?",
                (rule_id,)
            )
            conn.commit()

    def get_status_summary(self) -> dict:
        """Count rules by status — useful for the API response."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT status, COUNT(*) as cnt FROM rules GROUP BY status"
            )
            return {row[0]: row[1] for row in cursor.fetchall()}
