export type PhaseStatus = "idle" | "running" | "complete" | "error";

// ── Backend response shapes ────────────────────────────────────────────────

export interface RuleOutput {
  id: string;
  title: string;
  description: string;
  severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  source_clause?: string;
  page_number?: number;
  rule_type?: string;
  category?: string;
  confidence_score?: number;
  is_approved?: boolean;
  approval_status?: string;
}

export interface ExtractionResponse {
  session_id: string;
  pdf_name: string;
  total_rules: number;
  rules: RuleOutput[];
  from_cache: boolean;
  processing_time_seconds?: number;
}

export interface LinkExtractionRequest {
  url: string;
}

export interface CircularExtractionRequest {
  circular_code: string;
}

// ── Frontend display shapes ────────────────────────────────────────────────

export interface RuleItem {
  id: string;
  field: string;
  operator: string;
  threshold: string | number;
  severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  page?: number;
}

export interface ViolationItem {
  id: string;
  transactionId: string;
  amount: number;
  rule: string;
  severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  page?: number;
  status: "COMPLIANT" | "VIOLATION" | "NEEDS_REVIEW";
}

export interface ExplanationItem {
  id: string;
  transactionId: string;
  ruleId: string;
  clause: string;
  explanation: string;
}

export interface PipelineResults {
  rules: RuleItem[];
  violations: ViolationItem[];
  explanations: ExplanationItem[];
}

export interface ComplianceCheck {
  name?: string;
  status?: string;
  detail?: string;
  [key: string]: unknown;
}

export interface TransactionViolationRaw {
  rule?: string;
  severity?: string;
  verdict?: string;
  detail?: string;
  [key: string]: unknown;
}

export interface TransactionResponse {
  status: "complete" | "failed";
  filename: string;
  rows_input: number;
  rows_stored: number;
  rows_dropped: number;
  compliance_passed: boolean;
  compliance_checks: ComplianceCheck[];
  violations_count: number;
  violations: TransactionViolationRaw[];
  db_path: string;
  error?: string;
}

// ── SSE event types from backend /progress/{session_id} ───────────────────

export interface ProgressEvent {
  stage:
    | "classification"
    | "extraction"
    | "chunking"
    | "filtering"
    | "batching"
    | "llm_complete"
    | "verification"
    | "deduplication"
    | "validation"
    | "error";
  // classification
  pdf_type?: string;
  text_pages?: number;
  image_pages?: number;
  // extraction / chunking / filtering / batching
  pages_extracted?: number;
  chunks_created?: number;
  chunks_remaining?: number;
  chunks_skipped?: number;
  batches_created?: number;
  // LLM
  rules_extracted?: number;
  provider?: string;
  completed?: number;
  total?: number;
  percent?: number;
  // verification
  rules_verified?: number;
  // dedup / validation
  rules_final?: number;
  duplicates_removed?: number;
  valid_rules?: number;
  auto_approved?: number;
  // error
  error?: string;
}

// ── API client helpers ─────────────────────────────────────────────────────

interface ApiErrorPayload {
  detail?: string;
  message?: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    cache: "no-store",
  });

  if (!response.ok) {
    let payload: ApiErrorPayload | undefined;
    try {
      payload = (await response.json()) as ApiErrorPayload;
    } catch {
      payload = undefined;
    }

    throw new Error(payload?.detail ?? payload?.message ?? `Request failed: ${response.status}`);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return (await response.json()) as T;
}

// ── Mapping helper ─────────────────────────────────────────────────────────

export function ruleOutputToRuleItem(r: RuleOutput): RuleItem {
  return {
    id: r.id,
    field: r.rule_type ?? r.category ?? "compliance",
    operator: "must comply",
    threshold: r.source_clause ?? r.description.slice(0, 80),
    severity: r.severity,
    page: r.page_number,
  };
}

// ── Endpoints ──────────────────────────────────────────────────────────────

/** Upload PDF and extract compliance rules (main 8-layer pipeline). */
export async function uploadAndExtract(file: File): Promise<ExtractionResponse> {
  const body = new FormData();
  body.append("file", file);
  return request<ExtractionResponse>("/extract", { method: "POST", body });
}

/** Extract compliance rules from a public policy URL using backend retrieval + pipeline. */
export async function extractFromPolicyLink(url: string): Promise<ExtractionResponse> {
  return request<ExtractionResponse>("/extract-from-link", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url } satisfies LinkExtractionRequest),
  });
}

/** Extract compliance rules from RBI circular code using Serper search. */
export async function extractFromCircularCode(circularCode: string): Promise<ExtractionResponse> {
  return request<ExtractionResponse>("/extract-from-circular", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ circular_code: circularCode } satisfies CircularExtractionRequest),
  });
}

/** Open an SSE connection for real-time pipeline progress. */
export function streamProgress(
  sessionId: string,
  onEvent: (event: ProgressEvent) => void,
  onDone?: () => void,
): EventSource {
  const es = new EventSource(`${API_BASE}/progress/${sessionId}`);
  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data) as ProgressEvent;
      onEvent(data);
      if (data.stage === "validation" || data.stage === "error") {
        es.close();
        onDone?.();
      }
    } catch {
      // ignore non-JSON keep-alive pings
    }
  };
  es.onerror = () => {
    es.close();
    onDone?.();
  };
  return es;
}

// ── Legacy stubs (kept so existing imports don't break) ───────────────────

export async function ingestPolicy(payload: FormData) {
  return request<{ status: PhaseStatus; progress?: number; message?: string }>("/ingest", {
    method: "POST",
    body: payload,
  });
}

export async function extractRules(payload: FormData) {
  return request<{ status: PhaseStatus; progress?: number; message?: string; session_id?: string }>(
    "/extract-rules",
    { method: "POST", body: payload },
  );
}

/** Upload transactions and run the 3-stage Parse→Preprocess→Store pipeline. */
export async function validateTransactions(file: File): Promise<TransactionResponse> {
  const body = new FormData();
  body.append("file", file);
  return request<TransactionResponse>("/validate", { method: "POST", body });
}

export async function getViolations() {
  return request<PipelineResults>("/violations");
}

export async function downloadReportBlob() {
  const response = await fetch(`${API_BASE}/report`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to download report: ${response.status}`);
  }
  return response.blob();
}
