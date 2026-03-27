from supabase import create_client, Client
from core.config import settings
from core.logger import logger

_client: Client = None

def get_supabase() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_key)
        logger.info("Supabase client initialized successfully")
    return _client


# ── Rules Registry ────────────────────────────────────────────────

def insert_rule(rule: dict) -> dict:
    client = get_supabase()
    response = client.table("rules_registry").upsert(rule).execute()
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


# ── Compliance Results ────────────────────────────────────────────

def insert_compliance_result(result: dict) -> dict:
    client = get_supabase()
    response = client.table("compliance_results").insert(result).execute()
    return response.data

def fetch_violations() -> list:
    client = get_supabase()
    response = client.table("compliance_results").select("*").eq("verdict", "VIOLATION").execute()
    return response.data


# ── Violation Explanations ────────────────────────────────────────

def insert_explanation(explanation: dict) -> dict:
    client = get_supabase()
    response = client.table("violation_explanations").insert(explanation).execute()
    return response.data


# ── Ingestion Sessions ────────────────────────────────────────────

def create_ingestion_session(filename: str) -> str:
    client = get_supabase()
    response = client.table("ingestion_sessions").insert({
        "filename": filename,
        "status": "PROCESSING"
    }).execute()
    return response.data[0]["id"]

def update_ingestion_session(session_id: str, updates: dict) -> dict:
    client = get_supabase()
    response = client.table("ingestion_sessions").update(updates).eq("id", session_id).execute()
    return response.data