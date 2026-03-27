import { create } from "zustand";
import type { ExplanationItem, RuleItem, ViolationItem } from "@/lib/api";

export type Status = "idle" | "running" | "complete" | "error";

export interface LayerProgress {
  policyParsing: number;
  ruleExtraction: number;
  txnProcessing: number;
}

export interface EngineProgress {
  complianceValidation: number;
  explainability: number;
}

interface PipelineStore {
  uploadedPolicyFile: File | null;
  uploadedTransactionFile: File | null;
  phase1Status: Status;
  phase2Status: Status;
  phase1Progress: LayerProgress;
  phase2Progress: EngineProgress;
  logs: string[];
  error: string | null;
  results: {
    rules: RuleItem[];
    violations: ViolationItem[];
    explanations: ExplanationItem[];
  };
  setPolicyFile: (file: File | null) => void;
  setTransactionFile: (file: File | null) => void;
  setPhase1Status: (status: Status) => void;
  setPhase2Status: (status: Status) => void;
  setPhase1Progress: (progress: Partial<LayerProgress>) => void;
  setPhase2Progress: (progress: Partial<EngineProgress>) => void;
  appendLog: (log: string) => void;
  setError: (error: string | null) => void;
  setResults: (data: {
    rules: RuleItem[];
    violations: ViolationItem[];
    explanations: ExplanationItem[];
  }) => void;
  reset: () => void;
}

const initialPhase1: LayerProgress = {
  policyParsing: 0,
  ruleExtraction: 0,
  txnProcessing: 0,
};

const initialPhase2: EngineProgress = {
  complianceValidation: 0,
  explainability: 0,
};

export const usePipelineStore = create<PipelineStore>((set) => ({
  uploadedPolicyFile: null,
  uploadedTransactionFile: null,
  phase1Status: "idle",
  phase2Status: "idle",
  phase1Progress: initialPhase1,
  phase2Progress: initialPhase2,
  logs: [],
  error: null,
  results: {
    rules: [],
    violations: [],
    explanations: [],
  },
  setPolicyFile: (file) => set({ uploadedPolicyFile: file }),
  setTransactionFile: (file) => set({ uploadedTransactionFile: file }),
  setPhase1Status: (status) => set({ phase1Status: status }),
  setPhase2Status: (status) => set({ phase2Status: status }),
  setPhase1Progress: (progress) =>
    set((state) => ({ phase1Progress: { ...state.phase1Progress, ...progress } })),
  setPhase2Progress: (progress) =>
    set((state) => ({ phase2Progress: { ...state.phase2Progress, ...progress } })),
  appendLog: (log) => set((state) => ({ logs: [...state.logs.slice(-49), log] })),
  setError: (error) => set({ error }),
  setResults: (data) => set({ results: data }),
  reset: () =>
    set({
      uploadedPolicyFile: null,
      uploadedTransactionFile: null,
      phase1Status: "idle",
      phase2Status: "idle",
      phase1Progress: initialPhase1,
      phase2Progress: initialPhase2,
      logs: [],
      error: null,
      results: { rules: [], violations: [], explanations: [] },
    }),
}));
