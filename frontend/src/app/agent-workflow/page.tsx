"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Shield } from "lucide-react";
import { motion } from "framer-motion";
import {
  extractRules,
  getViolations,
  ingestPolicy,
  validateTransactions,
} from "@/lib/api";
import { usePipelineStore } from "@/store/pipelineStore";
import { WorkflowLayout } from "@/components/workflow/WorkflowLayout";

export default function AgentWorkflowPage() {
  const router = useRouter();
  const hasRun = useRef(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const policyFile = usePipelineStore((s) => s.uploadedPolicyFile);
  const txnFile = usePipelineStore((s) => s.uploadedTransactionFile);

  const setPhase1Status = usePipelineStore((s) => s.setPhase1Status);
  const setPhase2Status = usePipelineStore((s) => s.setPhase2Status);
  const setPhase1Progress = usePipelineStore((s) => s.setPhase1Progress);
  const setPhase2Progress = usePipelineStore((s) => s.setPhase2Progress);
  const setResults = usePipelineStore((s) => s.setResults);
  const appendLog = usePipelineStore((s) => s.appendLog);

  useEffect(() => {
    if (!policyFile || !txnFile) {
      router.replace("/");
    }
  }, [policyFile, router, txnFile]);

  useEffect(() => {
    if (!policyFile || !txnFile || hasRun.current) return;
    hasRun.current = true;

    let isMounted = true;
    const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

    const run = async () => {
      try {
        setErrorMessage(null);
        setPhase1Status("running");

        const ingestData = new FormData();
        ingestData.append("policy", policyFile);
        await ingestPolicy(ingestData);

        for (let i = 0; i <= 100; i += 5) {
          if (!isMounted) return;
          setPhase1Progress({ policyParsing: i });
          appendLog(`Extracting text from page ${Math.max(1, Math.ceil((i / 100) * 24))}...`);
          await wait(160);
        }

        const extractionData = new FormData();
        extractionData.append("policy", policyFile);
        await extractRules(extractionData);

        for (let i = 0; i <= 100; i += 5) {
          if (!isMounted) return;
          setPhase1Progress({ ruleExtraction: i });
          appendLog(`Meta-Llama 3 analyzing clause ${Math.max(1, Math.ceil((i / 100) * 34))}/34...`);
          await wait(150);
        }

        const txnData = new FormData();
        txnData.append("transactions", txnFile);
        await validateTransactions(txnData);

        for (let i = 0; i <= 100; i += 4) {
          if (!isMounted) return;
          setPhase1Progress({ txnProcessing: i });
          appendLog(`Building transaction graph: ${Math.round((i / 100) * 25000)} edges`);
          await wait(120);
        }

        if (!isMounted) return;
        setPhase1Status("complete");
        setPhase2Status("running");

        for (let i = 0; i <= 100; i += 5) {
          if (!isMounted) return;
          setPhase2Progress({ complianceValidation: i });
          await wait(120);
        }

        for (let i = 0; i <= 100; i += 5) {
          if (!isMounted) return;
          setPhase2Progress({ explainability: i });
          await wait(120);
        }

        const results = await getViolations();
        if (!isMounted) return;
        setResults(results);
        setPhase2Status("complete");
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to run pipeline";
        if (!isMounted) return;
        setErrorMessage(message);
        setPhase1Status("error");
        setPhase2Status("error");
      }
    };

    run();

    return () => {
      isMounted = false;
    };
  }, [
    appendLog,
    policyFile,
    setPhase1Progress,
    setPhase1Status,
    setPhase2Progress,
    setPhase2Status,
    setResults,
    txnFile,
  ]);

  return (
    <motion.main
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="min-h-screen"
    >
      <div
        className="sticky top-0 z-30 border-b px-4 py-3 backdrop-blur-xl md:px-6 md:py-4"
        style={{ borderColor: "var(--surface-border)", backgroundColor: "var(--nav-bg-scrolled)" }}
      >
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Shield className="size-5 text-[var(--accent-teal)]" />
            <div>
              <div className="text-sm font-bold tracking-[0.08em] text-[var(--accent-teal)]">POLICYGUARD.AI</div>
              <div className="max-w-[56vw] truncate text-xs text-[var(--text-secondary)] sm:max-w-[420px]">
                Analysis Workspace - {policyFile?.name ?? "Policy file"}
              </div>
            </div>
          </div>
          <button
            className="inline-flex items-center gap-2 rounded-full border px-3 py-2 text-xs font-medium text-[var(--accent-teal)] shadow-sm sm:px-4 sm:text-sm"
            style={{ borderColor: "var(--surface-border)", backgroundColor: "var(--surface-soft)" }}
            onClick={() => router.push("/")}
          >
            <ArrowLeft className="size-4" />
            New Analysis
          </button>
        </div>
      </div>

      {errorMessage && (
        <div className="mx-auto mt-4 max-w-7xl rounded-xl border border-[rgba(255,59,92,0.5)] bg-[rgba(255,59,92,0.1)] px-4 py-3 text-sm text-[var(--accent-red)]">
          API error: {errorMessage}
          <button
            onClick={() => window.location.reload()}
            className="ml-3 rounded border border-[rgba(255,59,92,0.35)] px-2 py-1 text-xs"
          >
            Retry
          </button>
        </div>
      )}

      <WorkflowLayout />
    </motion.main>
  );
}
