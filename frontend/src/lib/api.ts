export type PhaseStatus = "idle" | "running" | "complete" | "error";

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

export async function ingestPolicy(payload: FormData) {
  return request<{ status: PhaseStatus; progress?: number; message?: string }>("/ingest", {
    method: "POST",
    body: payload,
  });
}

export async function extractRules(payload: FormData) {
  return request<{ status: PhaseStatus; progress?: number; message?: string }>("/extract-rules", {
    method: "POST",
    body: payload,
  });
}

export async function validateTransactions(payload: FormData) {
  return request<{ status: PhaseStatus; progress?: number; message?: string }>("/validate", {
    method: "POST",
    body: payload,
  });
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
