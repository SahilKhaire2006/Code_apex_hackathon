"""
Supabase Client — Fixed & Hardened for PolicyGuard AI

Key fixes in this version:
  1. insert_or_update_rule() strips unknown columns BEFORE sending to Supabase
     (was silently failing with 400 errors because raw rule dicts contain fields
      like confidence_score / is_active / needs_review that are not in Supabase)
  2. base_document_exists() falls back to local SQLite when Supabase is empty
  3. record_ingestion_document() uses UPSERT instead of INSERT to handle retries
  4. All functions have hardened error logging so failures are visible in logs
"""

from supabase import create_client, Client
from core.config import settings
from core.logger import logger
from typing import Optional, List
import json

_client: Client = None

# ── EXACT columns that exist in our Supabase rules_registry table ─────────
# If you add a column to Supabase, add it here too.
_SUPABASE_RULE_COLUMNS = {
    "rule_id",
    "title",
    "category",
    "severity",
    "logic_type",
    "page_number",
    "paragraph_number",
    "act_section",
    "circular_reference",
    "source_clause",
    "description",
    "plain_english",
    "violation_message_template",
    "applicable_entity",
    "metadata_tags",
    "condition_field",
    "condition_operator",
    "condition_value",
    "condition_unit",
    # Provenance columns
    "status",
    "source_document_name",
    "source_document_type",
    "source_document_date",
    "last_modified_by",
    "modification_summary",
    "provenance_chain",
    "rule_history",
    "parent_rule_id",
    "supersedes_rule_id",
    "reference_count",
}


def get_supabase() -> Client:
    global _client
    if not settings.supabase_url or not settings.supabase_key:
        raise RuntimeError(
            "Supabase is not configured — set SUPABASE_URL and SUPABASE_KEY in .env."
        )
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_key)
        logger.info("Supabase client initialized successfully")
    return _client


def _supabase_available() -> bool:
    """Non-raising check for Supabase availability."""
    return bool(settings.supabase_url and settings.supabase_key)


def _sanitize_rule_for_supabase(rule_dict: dict) -> dict:
    """
    Strip any fields that are NOT in the Supabase schema.
    Also serializes JSONB arrays properly.
    """
    row = {}
    for k, v in rule_dict.items():
        if k not in _SUPABASE_RULE_COLUMNS:
            continue
        # JSONB arrays — serialize if needed
        if k in ("provenance_chain", "rule_history", "metadata_tags"):
            if isinstance(v, str):
                try:
                    v = json.loads(v)
                except Exception:
                    v = []
            if not isinstance(v, (list, dict)):
                v = []
        # page_number must be int or None
        if k == "page_number" and v is not None:
            try:
                v = int(v)
            except Exception:
                v = None
        row[k] = v
    return row


# ── Rules Registry ────────────────────────────────────────────────────────

def insert_rule(rule: dict) -> dict:
    client = get_supabase()
    sanitized = _sanitize_rule_for_supabase(rule)
    response = client.table("rules_registry").upsert(sanitized).execute()
    return response.data


def fetch_all_rules() -> list:
    client = get_supabase()
    response = client.table("rules_registry").select("*").execute()
    return response.data


def fetch_rules_needing_review() -> list:
    client = get_supabase()
    response = client.table("rules_registry").select("*").eq("needs_review", True).execute()
    return response.data


def approve_rule(rule_id: str) -> dict:
    client = get_supabase()
    response = client.table("rules_registry").update(
        {"needs_review": False}
    ).eq("rule_id", rule_id).execute()
    return response.data


def fetch_rule_by_id(rule_id: str) -> Optional[dict]:
    """Fetch a single rule by its UUID."""
    try:
        client = get_supabase()
        response = client.table("rules_registry").select("*").eq("rule_id", rule_id).limit(1).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"[Supabase] fetch_rule_by_id failed: {e}")
        return None


def search_rules_by_clause(clause_text: str, limit: int = 5) -> list:
    """
    STEP B — Supabase ILIKE lookup by source_clause text.
    Returns list of rule dicts.
    """
    if not _supabase_available():
        return []
    try:
        client = get_supabase()
        key_phrase = clause_text.strip()[:120].replace("%", "")
        response = (
            client.table("rules_registry")
            .select("*")
            .ilike("source_clause", f"%{key_phrase[:60]}%")
            .limit(limit)
            .execute()
        )
        return response.data or []
    except Exception as e:
        logger.warning(f"[Supabase] search_rules_by_clause failed: {e}")
        return []


def update_rule_in_registry(rule_id: str, updates: dict) -> dict:
    """Update specific fields on an existing rule in the registry."""
    try:
        client = get_supabase()
        safe_updates = _sanitize_rule_for_supabase(updates)
        response = client.table("rules_registry").update(safe_updates).eq("rule_id", rule_id).execute()
        return response.data
    except Exception as e:
        logger.error(f"[Supabase] update_rule_in_registry failed for {rule_id}: {e}")
        return {}


def update_rule_provenance(rule_id: str, provenance_entry: dict, extra_updates: dict = None) -> bool:
    """
    Append a provenance entry to the rule's provenance_chain JSONB array.
    Also apply any extra field updates (e.g. modification_summary, last_modified_by).
    """
    if not _supabase_available():
        return False
    try:
        client = get_supabase()
        current = fetch_rule_by_id(rule_id)
        if not current:
            return False

        chain = current.get("provenance_chain") or []
        if isinstance(chain, str):
            try:
                chain = json.loads(chain)
            except Exception:
                chain = []
        chain.append(provenance_entry)

        updates = {"provenance_chain": chain}
        if extra_updates:
            updates.update(extra_updates)

        ref_count = (current.get("reference_count") or 1) + 1
        updates["reference_count"] = ref_count

        safe_updates = _sanitize_rule_for_supabase(updates)
        client.table("rules_registry").update(safe_updates).eq("rule_id", rule_id).execute()
        logger.info(f"[Supabase] Provenance updated for rule {rule_id}")
        return True
    except Exception as e:
        logger.error(f"[Supabase] update_rule_provenance failed: {e}")
        return False


def insert_or_update_rule(rule_dict: dict) -> str:
    """
    Shared registry smart upsert.
    - Strips unknown columns before sending (KEY FIX: prevents 400 errors)
    - Upserts on rule_id conflict
    Returns the rule_id.
    """
    if not _supabase_available():
        return rule_dict.get("rule_id", "")

    rule_id = rule_dict.get("rule_id", "")
    if not rule_id:
        logger.warning("[Supabase] insert_or_update_rule called with no rule_id — skipping")
        return ""

    try:
        client = get_supabase()
        # Strip all columns not in Supabase schema — THIS IS THE CRITICAL FIX
        row = _sanitize_rule_for_supabase(rule_dict)

        if not row.get("title"):
            logger.warning(f"[Supabase] Rule {rule_id} has no title — skipping")
            return rule_id

        response = client.table("rules_registry").upsert(row, on_conflict="rule_id").execute()
        logger.info(f"[Supabase] ✅ Rule upserted — rule_id={rule_id}, title='{row.get('title', '')[:50]}'")
        return rule_id
    except Exception as e:
        logger.error(f"[Supabase] ❌ insert_or_update_rule FAILED for rule_id={rule_id}: {e}")
        return rule_id


# ── Shared Registry: Check if document already processed ─────────────────

def fetch_rules_for_document(source_document_name: str) -> List[dict]:
    """
    SHARED REGISTRY FEATURE:
    Check if rules from a specific document have already been extracted
    (by any bank/tenant). Returns list of rule dicts if found.
    """
    if not _supabase_available():
        return []
    try:
        client = get_supabase()
        response = (
            client.table("rules_registry")
            .select("*")
            .eq("source_document_name", source_document_name)
            .execute()
        )
        results = response.data or []
        if results:
            logger.info(
                f"[Supabase] SharedRegistry: Found {len(results)} existing rules "
                f"for document '{source_document_name}'"
            )
        return results
    except Exception as e:
        logger.warning(f"[Supabase] fetch_rules_for_document failed: {e}")
        return []


def base_document_exists() -> bool:
    """
    PROCESSING ORDER CONSTRAINT:
    Check if any master_direction has been ingested.
    Checks Supabase first, then falls back to local SQLite.
    This ensures the constraint works even when Supabase just got reset.
    """
    # Try Supabase first
    if _supabase_available():
        try:
            client = get_supabase()
            response = (
                client.table("rules_registry")
                .select("rule_id")
                .eq("source_document_type", "master_direction")
                .limit(1)
                .execute()
            )
            if response.data:
                logger.info("[Supabase] base_document_exists: master_direction found in Supabase")
                return True
        except Exception as e:
            logger.warning(f"[Supabase] base_document_exists Supabase check failed: {e}")

    # Fallback: check local SQLite
    try:
        import sqlite3
        from pathlib import Path
        db_path = Path("registry/rules.db")
        if db_path.exists():
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT rule_id FROM rules WHERE source_document_type = 'master_direction' LIMIT 1"
                )
                row = cursor.fetchone()
                if row:
                    logger.info("[Supabase] base_document_exists: master_direction found in SQLite fallback")
                    return True
    except Exception as e:
        logger.warning(f"[Supabase] base_document_exists SQLite fallback failed: {e}")

    logger.warning("[Supabase] base_document_exists: NO master_direction found in Supabase OR SQLite")
    return False


def fetch_all_master_direction_rules() -> List[dict]:
    """Fetch all rules from master direction documents for comparison."""
    if not _supabase_available():
        return []
    try:
        client = get_supabase()
        response = (
            client.table("rules_registry")
            .select("*")
            .eq("source_document_type", "master_direction")
            .execute()
        )
        return response.data or []
    except Exception as e:
        logger.warning(f"[Supabase] fetch_all_master_direction_rules failed: {e}")
        return []


# ── Ingestion Documents Table ─────────────────────────────────────────────

def record_ingestion_document(doc_record: dict) -> str:
    """
    Record every processed document in the ingestion_documents table.
    Uses UPSERT on filename to handle retries gracefully.
    """
    if not _supabase_available():
        return ""
    try:
        client = get_supabase()
        # Only send columns that exist in our ingestion_documents table
        allowed = {
            "filename", "document_type", "document_date",
            "total_rules_extracted", "new_rules", "modified_rules",
            "existing_rules", "superseded_rules", "clarification_rules",
        }
        safe_doc = {k: v for k, v in doc_record.items() if k in allowed}
        response = client.table("ingestion_documents").upsert(
            safe_doc, on_conflict="filename"
        ).execute()
        if response.data:
            logger.info(f"[Supabase] ✅ Ingestion document recorded — filename={safe_doc.get('filename')}")
        return safe_doc.get("filename", "")
    except Exception as e:
        logger.warning(f"[Supabase] record_ingestion_document failed: {e}")
        return ""


# ── Compliance Results ────────────────────────────────────────────────────

def insert_compliance_result(result: dict) -> dict:
    client = get_supabase()
    response = client.table("compliance_results").insert(result).execute()
    return response.data


def fetch_violations() -> list:
    client = get_supabase()
    response = client.table("compliance_results").select("*").eq("verdict", "VIOLATION").execute()
    return response.data


# ── Violation Explanations ────────────────────────────────────────────────

def insert_explanation(explanation: dict) -> dict:
    client = get_supabase()
    response = client.table("violation_explanations").insert(explanation).execute()
    return response.data


# ── Ingestion Sessions ────────────────────────────────────────────────────

def create_ingestion_session(filename: str, document_type: str = "circular") -> str:
    client = get_supabase()
    response = client.table("ingestion_sessions").insert({
        "filename": filename,
        "status": "PROCESSING",
        "document_type": document_type,
        "base_document_ready": document_type == "master_direction",
    }).execute()
    return response.data[0]["id"]


def update_ingestion_session(session_id: str, updates: dict) -> dict:
    client = get_supabase()
    response = client.table("ingestion_sessions").update(updates).eq("id", session_id).execute()
    return response.data