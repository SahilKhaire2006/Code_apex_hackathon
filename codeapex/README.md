# Production-Ready Python Data Pipeline

A 3-stage data pipeline with RBI compliance checks.

---

## Architecture

```
Input File (CSV / XLS / XLSX)
        │
        ▼
┌─────────────────────────┐
│  Stage 1 — File Parsing │  Auto-schema detection, type inference,
│  (FileParsingPipeline)  │  chunked processing for large files
└────────────┬────────────┘
             │
             ▼
┌──────────────────────────────────┐
│  Stage 2 — Preprocessing         │  Remove 'country' col, drop NULLs,
│  (DataPreprocessingPipeline)     │  remove duplicates, normalize,
│  + RBI Compliance Gate           │  run 5-point RBI compliance check
└────────────┬─────────────────────┘
             │  ← Quality gate: ALL checks must PASS
             ▼
┌─────────────────────────┐
│  Stage 3 — Storage      │  SQLite → output/transactions.db
│  (DataStoragePipeline)  │  Pickle  → output/batch.pkl
└─────────────────────────┘
```

---

## Setup

### Step 1 — Create virtual environment

```bash
python -m venv .venv
```

### Step 2 — Activate it

**Windows:**
```bash
.venv\Scripts\activate
```

**Mac / Linux:**
```bash
source .venv/bin/activate
```

### Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

### Step 4 — Run the pipeline

```bash
python main.py --file your_data_file.csv
```

---

## Supported File Formats

| Format | Extension | Engine  |
|--------|-----------|---------|
| CSV    | `.csv`    | built-in |
| Excel  | `.xlsx`   | openpyxl |
| Excel  | `.xls`    | xlrd     |

---

## Output Files

All outputs are written to the `output/` directory (created automatically).

| File                       | Description                          |
|----------------------------|--------------------------------------|
| `output/transactions.db`   | SQLite database with indexed table   |
| `output/batch.pkl`         | Pickle file for ML pipelines         |

---

## Pipeline Rules

### Data Quality Gates (hard blocks)

| Gate                    | Action on Failure       |
|-------------------------|-------------------------|
| NULL values detected    | Rows dropped + logged   |
| Duplicate rows detected | Rows dropped + logged   |
| `country` column found  | Column removed (RBI)    |

All 3 gates must pass before Stage 3 runs.

### File Size Routing

| File Size    | Strategy               |
|--------------|------------------------|
| < 10,000 rows | Direct load into memory |
| ≥ 10,000 rows | Chunked (10K rows/chunk) |

---

## RBI Compliance Report

After Stage 2, the pipeline prints a full compliance report:

```
============================================================
  RBI COMPLIANCE REPORT
============================================================
  ✅ [PASS] Country column removed
  ✅ [PASS] No NULL values
  ✅ [PASS] No duplicate rows
  ✅ [PASS] Dataset not empty after cleaning
  ✅ [PASS] At least one column present
------------------------------------------------------------
  ✅ OVERALL: PASS
============================================================
```

---

## Project Files

```
codeapex/
├── main.py           # Entry point — runs full pipeline
├── file_parser.py    # Stage 1 — file parsing & schema detection
├── preprocessor.py   # Stage 2 — preprocessing & RBI compliance
├── storage.py        # Stage 3 — SQLite + Pickle storage
├── config.py         # Central configuration (paths, chunk size)
├── requirements.txt  # Python dependencies
├── README.md         # This file
└── output/           # Auto-created; holds transactions.db & batch.pkl
```

> **Note:** `.venv/` is excluded from any zip archive.  
> All pipeline testing uses only your provided data files — no synthetic data is generated.
