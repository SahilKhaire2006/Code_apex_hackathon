import sqlite3
import json
from pathlib import Path
from core.logger import logger


class RuleRegistrySQLite:
    """Local SQLite registry for structured rule storage with full 19-field schema."""

    def __init__(self, db_path: str = "registry/rules.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

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

                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
        logger.info(f"SQLite Rule Registry initialized at {self.db_path}")

    def upsert_rule(self, rule_dict: dict):
        rule_copy = rule_dict.copy()

        # Serialize lists to JSON strings
        if "metadata_tags" in rule_copy:
            rule_copy["metadata_tags"] = json.dumps(rule_copy.get("metadata_tags", []))

        # Convert bool to int for SQLite
        rule_copy["is_active"] = 1 if rule_copy.get("is_active", True) else 0
        rule_copy["needs_review"] = 1 if rule_copy.get("needs_review", True) else 0

        # Remove any fields not in the schema (future-proofing)
        allowed_columns = {
            "rule_id", "title", "category", "severity", "logic_type",
            "page_number", "paragraph_number", "act_section", "circular_reference",
            "source_clause", "description", "plain_english", "violation_message_template",
            "applicable_entity", "metadata_tags",
            "condition_field", "condition_operator", "condition_value", "condition_unit",
            "confidence_score", "is_active", "needs_review"
        }
        rule_copy = {k: v for k, v in rule_copy.items() if k in allowed_columns}

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

    def fetch_all(self) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rules")
            rows = [dict(row) for row in cursor.fetchall()]
            # Deserialize metadata_tags JSON
            for row in rows:
                if row.get("metadata_tags"):
                    try:
                        row["metadata_tags"] = json.loads(row["metadata_tags"])
                    except Exception:
                        row["metadata_tags"] = []
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

    def approve_rule(self, rule_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE rules SET needs_review = 0 WHERE rule_id = ?",
                (rule_id,)
            )
            conn.commit()
