-- ═══════════════════════════════════════════════════════════════════════
-- PolicyGuard AI — Supabase Schema Migration (Safe / Idempotent)
-- Run this in the Supabase SQL Editor.
-- Safe to run multiple times — uses IF NOT EXISTS everywhere.
-- ═══════════════════════════════════════════════════════════════════════

-- ── STEP 0: Enable pg_trgm extension FIRST (needed for GIN index) ─────

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ── STEP 1: Create ingestion_sessions table if it doesn't exist ────────

CREATE TABLE IF NOT EXISTS ingestion_sessions (
    id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    filename      TEXT NOT NULL,
    status        TEXT DEFAULT 'PROCESSING',
    document_type TEXT DEFAULT 'circular',
    base_document_ready BOOLEAN DEFAULT FALSE,
    total_pages   INTEGER,
    total_chunks  INTEGER,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ── STEP 2: Create rules_registry table if it doesn't exist ───────────
-- This creates the FULL schema from scratch if the table is missing.

CREATE TABLE IF NOT EXISTS rules_registry (
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

    -- Quality & Review
    confidence_score         REAL DEFAULT 1.0,
    is_active                BOOLEAN DEFAULT TRUE,
    needs_review             BOOLEAN DEFAULT TRUE,

    -- Status (NEW/EXISTING/MODIFIED/SUPERSEDED/CLARIFICATION)
    status                   TEXT DEFAULT 'NEW'
        CHECK (status IN ('NEW','EXISTING','MODIFIED','SUPERSEDED','CLARIFICATION')),

    -- Provenance Fields
    source_document_name     TEXT,
    source_document_type     TEXT
        CHECK (source_document_type IN (
            'master_direction','circular','amendment','gazette','notification'
        )),
    source_document_date     DATE,
    last_modified_by         TEXT,
    modification_summary     TEXT,
    provenance_chain         JSONB DEFAULT '[]'::jsonb,
    rule_history             JSONB DEFAULT '[]'::jsonb,
    parent_rule_id           TEXT,
    supersedes_rule_id       TEXT,
    reference_count          INTEGER DEFAULT 1,

    created_at               TIMESTAMPTZ DEFAULT NOW()
);

-- ── STEP 3: Add any missing columns to rules_registry ─────────────────
-- (Safe for existing tables — each ALTER is independent)

ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS source_clause            TEXT;
ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS description              TEXT;
ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS plain_english            TEXT;
ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS violation_message_template TEXT;
ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS applicable_entity        TEXT DEFAULT 'ALL';
ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS metadata_tags            JSONB DEFAULT '[]'::jsonb;
ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS condition_field          TEXT;
ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS condition_operator       TEXT;
ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS condition_value          TEXT;
ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS condition_unit           TEXT;
ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS confidence_score         REAL DEFAULT 1.0;
ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS is_active                BOOLEAN DEFAULT TRUE;
ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS needs_review             BOOLEAN DEFAULT TRUE;
ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS status                   TEXT DEFAULT 'NEW';
ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS source_document_name     TEXT;
ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS source_document_type     TEXT;
ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS source_document_date     DATE;
ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS last_modified_by         TEXT;
ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS modification_summary     TEXT;
ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS provenance_chain         JSONB DEFAULT '[]'::jsonb;
ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS rule_history             JSONB DEFAULT '[]'::jsonb;
ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS parent_rule_id           TEXT;
ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS supersedes_rule_id       TEXT;
ALTER TABLE rules_registry ADD COLUMN IF NOT EXISTS reference_count          INTEGER DEFAULT 1;

-- ── STEP 4: Add missing columns to ingestion_sessions ─────────────────

ALTER TABLE ingestion_sessions ADD COLUMN IF NOT EXISTS document_type        TEXT DEFAULT 'circular';
ALTER TABLE ingestion_sessions ADD COLUMN IF NOT EXISTS base_document_ready  BOOLEAN DEFAULT FALSE;
ALTER TABLE ingestion_sessions ADD COLUMN IF NOT EXISTS total_pages          INTEGER;
ALTER TABLE ingestion_sessions ADD COLUMN IF NOT EXISTS total_chunks         INTEGER;

-- ── STEP 5: Create ingestion_documents table ──────────────────────────

CREATE TABLE IF NOT EXISTS ingestion_documents (
    id                    UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    filename              TEXT NOT NULL,
    document_type         TEXT NOT NULL,
    document_date         DATE,
    total_rules_extracted INTEGER DEFAULT 0,
    new_rules             INTEGER DEFAULT 0,
    modified_rules        INTEGER DEFAULT 0,
    existing_rules        INTEGER DEFAULT 0,
    superseded_rules      INTEGER DEFAULT 0,
    clarification_rules   INTEGER DEFAULT 0,
    session_id            UUID REFERENCES ingestion_sessions(id),
    processed_by_bank     TEXT,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- ── STEP 6: Create compliance_results table if missing ────────────────

CREATE TABLE IF NOT EXISTS compliance_results (
    id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    rule_id          TEXT,
    transaction_id   TEXT,
    verdict          TEXT,
    explanation      TEXT,
    severity         TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ── STEP 7: Create violation_explanations table if missing ────────────

CREATE TABLE IF NOT EXISTS violation_explanations (
    id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    rule_id          TEXT,
    transaction_id   TEXT,
    clause           TEXT,
    explanation      TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ── STEP 8: Performance Indexes ───────────────────────────────────────

-- Index for fast shared-registry document lookup
CREATE INDEX IF NOT EXISTS idx_rules_registry_source_doc
    ON rules_registry(source_document_name);

-- Index for status-based filtering
CREATE INDEX IF NOT EXISTS idx_rules_registry_status
    ON rules_registry(status);

-- Index for document type filtering
CREATE INDEX IF NOT EXISTS idx_rules_registry_doc_type
    ON rules_registry(source_document_type);

-- Index for ingestion_documents filename lookup
CREATE INDEX IF NOT EXISTS idx_ingestion_documents_filename
    ON ingestion_documents(filename);

-- ── STEP 9: GIN index for fuzzy clause matching (pg_trgm) ─────────────
-- Using a DO block so this only runs if source_clause column exists.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'rules_registry'
          AND column_name = 'source_clause'
    ) THEN
        IF NOT EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE tablename = 'rules_registry'
              AND indexname = 'idx_rules_source_clause_trgm'
        ) THEN
            EXECUTE 'CREATE INDEX idx_rules_source_clause_trgm
                     ON rules_registry
                     USING GIN (source_clause gin_trgm_ops)';
            RAISE NOTICE 'Created GIN index idx_rules_source_clause_trgm';
        ELSE
            RAISE NOTICE 'GIN index idx_rules_source_clause_trgm already exists, skipping.';
        END IF;
    ELSE
        RAISE NOTICE 'Column source_clause not found — skipping GIN index.';
    END IF;
END
$$;

-- ── STEP 10: Verify migration ─────────────────────────────────────────
-- Run this SELECT to confirm all tables and columns are present.

SELECT
    table_name,
    COUNT(*) AS column_count
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN (
      'rules_registry',
      'ingestion_sessions',
      'ingestion_documents',
      'compliance_results',
      'violation_explanations'
  )
GROUP BY table_name
ORDER BY table_name;
