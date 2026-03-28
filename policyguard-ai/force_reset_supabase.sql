-- ═══════════════════════════════════════════════════════════════════════
-- PolicyGuard AI — Supabase Schema Force Reset
-- RUN THIS IN THE SUPABASE SQL EDITOR to fix the schema mismatch.
-- ═══════════════════════════════════════════════════════════════════════

-- 1. CLEAN UP LEGACY TABLES (which have old columns like uploaded_by_session)
DROP TABLE IF EXISTS rules_registry CASCADE;
DROP TABLE IF EXISTS ingestion_documents CASCADE;

-- 2. ENABLE EXTENSION
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 3. CREATE NEW CORRECT SCHEMA
CREATE TABLE rules_registry (
    rule_id                  TEXT PRIMARY KEY,

    -- Core Identity
    title                    TEXT NOT NULL,
    category                 TEXT,
    severity                 TEXT,
    logic_type               TEXT,

    -- Legal Reference
    page_number              INTEGER,
    paragraph_number         TEXT,
    act_section              TEXT,
    circular_reference       TEXT,

    -- Text Fields
    source_clause            TEXT,
    description              TEXT,
    plain_english            TEXT,
    violation_message_template TEXT,

    -- Applicability
    applicable_entity        TEXT DEFAULT 'ALL',

    -- Tagging
    metadata_tags            JSONB DEFAULT '[]'::jsonb,

    -- Condition Engine
    condition_field          TEXT,
    condition_operator       TEXT,
    condition_value          TEXT,
    condition_unit           TEXT,

    -- RULE STATUS DETECTION & PROVENANCE TRACKING (New Columns)
    status                   TEXT DEFAULT 'NEW',  -- NEW, EXISTING, MODIFIED, SUPERSEDED, CLARIFICATION
    source_document_name     TEXT,
    source_document_type     TEXT,
    source_document_date     TEXT,
    last_modified_by         TEXT,
    modification_summary     TEXT,
    provenance_chain         JSONB DEFAULT '[]'::jsonb,
    rule_history             JSONB DEFAULT '[]'::jsonb,
    parent_rule_id           TEXT,
    supersedes_rule_id       TEXT,
    reference_count          INTEGER DEFAULT 0,
    
    -- Timestamps
    created_at               TIMESTAMPTZ DEFAULT NOW(),
    updated_at               TIMESTAMPTZ DEFAULT NOW()
);

-- 4. CREATE INGESTION TRACKING TABLE
CREATE TABLE ingestion_documents (
    filename                 TEXT PRIMARY KEY,
    document_type            TEXT,
    document_date            TEXT,
    total_rules_extracted    INTEGER DEFAULT 0,
    new_rules                INTEGER DEFAULT 0,
    modified_rules           INTEGER DEFAULT 0,
    existing_rules           INTEGER DEFAULT 0,
    superseded_rules         INTEGER DEFAULT 0,
    clarification_rules      INTEGER DEFAULT 0,
    processed_at             TIMESTAMPTZ DEFAULT NOW()
);

-- 5. CREATE INDEXES
CREATE INDEX idx_rules_registry_source_doc ON rules_registry(source_document_name);
CREATE INDEX idx_rules_registry_status ON rules_registry(status);
CREATE INDEX idx_rules_registry_doc_type ON rules_registry(source_document_type);
CREATE INDEX idx_ingestion_documents_filename ON ingestion_documents(filename);

-- 6. GIN INDEX
CREATE INDEX idx_rules_source_clause_trgm ON rules_registry USING GIN (source_clause gin_trgm_ops);

SELECT 'SCHEMA RESET COMPLETE. READY FOR TESTING.' AS status;
