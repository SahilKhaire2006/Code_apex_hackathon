import uuid
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


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
    applicable_entity: Optional[str] = "ALL"  # NBFC, RNBC, ALL

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