import uuid
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime, date
from enum import Enum


# ── Enums ─────────────────────────────────────────────────────────────────

class RuleStatus(str, Enum):
    """
    Status of a rule relative to the Master Direction base.
    NEW        = first appearance ever in the registry
    EXISTING   = semantically identical rule already exists in the registry
    MODIFIED   = same rule but threshold/scope/deadline changed
    SUPERSEDED = prior rule explicitly replaced/withdrawn by this document
    CLARIFICATION = interpretive guidance on an existing rule — no obligation change
    """
    NEW = "NEW"
    EXISTING = "EXISTING"
    MODIFIED = "MODIFIED"
    SUPERSEDED = "SUPERSEDED"
    CLARIFICATION = "CLARIFICATION"


class DocumentType(str, Enum):
    """RBI document types for provenance tracking."""
    MASTER_DIRECTION = "master_direction"
    CIRCULAR = "circular"
    AMENDMENT = "amendment"
    GAZETTE = "gazette"
    NOTIFICATION = "notification"


# ── Core Schemas ──────────────────────────────────────────────────────────

class PolicyChunk(BaseModel):
    chunk_id: str
    text: str
    page_number: int
    section_title: Optional[str] = None
    char_start: int
    char_end: int
    source_filename: str
    chunk_index: int


class IngestionResult(BaseModel):
    session_id: str
    filename: str
    total_pages: int
    total_chunks: int
    status: str
    document_type: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class Rule(BaseModel):
    rule_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # ── Core Identity ─────────────────────────────────────────────
    title: str
    category: str           # KYC, AML, REPORTING, PEP, CFT, PMLA, FATF,
                            # RECORD_KEEPING, TRANSACTION_THRESHOLD, EMPLOYEE_CONDUCT
    severity: str           # CRITICAL, HIGH, MEDIUM, LOW
    logic_type: str         # REQUIRED, PROHIBITED, CONDITIONAL, THRESHOLD

    # ── Legal Reference ───────────────────────────────────────────
    page_number: Optional[int] = None
    paragraph_number: Optional[str] = None
    act_section: Optional[str] = None
    circular_reference: Optional[str] = None

    # ── Text Fields ───────────────────────────────────────────────
    source_clause: str
    description: str
    plain_english: Optional[str] = None
    violation_message_template: Optional[str] = None

    # ── Applicability ─────────────────────────────────────────────
    applicable_entity: Optional[str] = "ALL"   # NBFC, RNBC, ALL

    # ── Tagging ───────────────────────────────────────────────────
    metadata_tags: List[str] = []

    # ── Automated Condition Engine ────────────────────────────────
    condition_field: Optional[str] = None
    condition_operator: Optional[str] = None
    condition_value: Optional[str] = None
    condition_unit: Optional[str] = None

    # ── Quality ───────────────────────────────────────────────────
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)

    # ── Review Gate ───────────────────────────────────────────────
    is_active: bool = True
    needs_review: bool = True

    # ══ PROVENANCE FIELDS (FIX 1 & FIX 2) ═══════════════════════════════

    # Status — now a proper enum (default NEW for backward compat)
    status: str = RuleStatus.NEW

    # Source document that first introduced this rule
    source_document_name: Optional[str] = None
    source_document_type: Optional[str] = None    # DocumentType value
    source_document_date: Optional[str] = None    # ISO date string "YYYY-MM-DD"

    # Most recent document that modified this rule
    last_modified_by: Optional[str] = None
    modification_summary: Optional[str] = None

    # Ordered list of all documents that touched this rule
    # Each entry: {document, type, date, action}
    provenance_chain: List[Any] = Field(default_factory=list)

    # Previous versions of the rule (appended before overwrite)
    rule_history: List[Any] = Field(default_factory=list)

    # For SUPERSEDED / CLARIFICATION linking
    supersedes_rule_id: Optional[str] = None
    parent_rule_id: Optional[str] = None

    # How many documents have referenced this rule
    reference_count: int = 1


class ProvenanceEntry(BaseModel):
    """A single entry in a rule's provenance_chain."""
    document: str
    type: str                             # DocumentType value
    date: Optional[str] = None            # ISO date string
    action: str                           # introduced | referenced | modified | superseded | clarified


class DeltaJudgment(BaseModel):
    """LLM comparison judgment output (FIX 6)."""
    matched_rule_id: Optional[str] = None
    status: str                            # RuleStatus value
    confidence: float = Field(ge=0.0, le=1.0)
    modification_summary: Optional[str] = None
    key_delta: Optional[str] = None
    provenance_action: str = "introduced"  # introduced | referenced | modified | superseded | clarified