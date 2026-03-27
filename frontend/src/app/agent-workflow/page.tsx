"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Shield } from "lucide-react";
import { motion } from "framer-motion";
import {
  extractFromCircularCode,
  extractFromPolicyLink,
  uploadAndExtract,
  getViolations,
  validateTransactions,
  ruleOutputToRuleItem,
  type ViolationItem,
} from "@/lib/api";
import { usePipelineStore } from "@/store/pipelineStore";
import { WorkflowLayout } from "@/components/workflow/WorkflowLayout";
import { GovernmentFooter } from "@/components/layout/GovernmentFooter";

export default function AgentWorkflowPage() {
  const router = useRouter();
  const hasRun = useRef(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const policyFile = usePipelineStore((s) => s.uploadedPolicyFile);
  const policyLink = usePipelineStore((s) => s.policyLink);
  const transactionFile = usePipelineStore((s) => s.uploadedTransactionFile);

  const setPhase1Status = usePipelineStore((s) => s.setPhase1Status);
  const setPhase2Status = usePipelineStore((s) => s.setPhase2Status);
  const setPhase1Progress = usePipelineStore((s) => s.setPhase1Progress);
  const setPhase2Progress = usePipelineStore((s) => s.setPhase2Progress);
  const setPipelineStats = usePipelineStore((s) => s.setPipelineStats);
  const setResults = usePipelineStore((s) => s.setResults);
  const appendLog = usePipelineStore((s) => s.appendLog);
  const setSessionId = usePipelineStore((s) => s.setSessionId);

  const mapTxnViolations = (raw: Array<Record<string, unknown>>): ViolationItem[] =>
    raw.map((v, i) => {
      const severity = String(v?.severity ?? "MEDIUM").toUpperCase();
      const normalizedSeverity: ViolationItem["severity"] =
        severity === "LOW" || severity === "MEDIUM" || severity === "HIGH" || severity === "CRITICAL"
          ? severity
          : "MEDIUM";

      const verdict = String(v?.verdict ?? "VIOLATION").toUpperCase();
      const normalizedStatus: ViolationItem["status"] =
        verdict === "COMPLIANT" || verdict === "NEEDS_REVIEW" ? verdict : "VIOLATION";

      return {
        id: `VIO-${i + 1}`,
        transactionId: `TXN-${String(i + 1).padStart(4, "0")}`,
        amount: 0,
        rule: String(v?.rule ?? "Compliance Rule"),
        severity: normalizedSeverity,
        page: undefined,
        status: normalizedStatus,
      };
    });

  const policySourceName = policyFile?.name ?? policyLink.trim();

  // Redirect to home if no policy source is loaded
  useEffect(() => {
    if (!policyFile && !policyLink.trim()) {
      router.replace("/");
    }
  }, [policyFile, policyLink, router]);

  useEffect(() => {
    const normalizedPolicyLink = policyLink.trim();
    if ((!policyFile && !normalizedPolicyLink) || hasRun.current) return;
    hasRun.current = true;

    let isMounted = true;
    const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

    const run = async () => {
      try {
        setErrorMessage(null);
        setPhase1Status("running");
        setPipelineStats({ transactionsInput: 0, transactionsStored: 0, transactionsDropped: 0 });
        appendLog(
          policyFile
            ? `Starting PolicyGuard AI pipeline for "${policyFile.name}"…`
            : normalizedPolicyLink.startsWith("[CIRCULAR]")
            ? `Searching for RBI circular: ${normalizedPolicyLink.slice(10)}…`
            : `Starting PolicyGuard AI pipeline for policy link: ${normalizedPolicyLink}`,
        );

        const extractPromise = policyFile
          ? uploadAndExtract(policyFile)
          : normalizedPolicyLink.startsWith("[CIRCULAR]")
          ? extractFromCircularCode(normalizedPolicyLink.slice(10))
          : extractFromPolicyLink(normalizedPolicyLink);

        // Cancellable waiting animation — stops the moment the response arrives
        let animationCancelled = false;
        const animateWaiting = async () => {
          for (let i = 0; i <= 65; i += 1) {
            if (!isMounted || animationCancelled) break;
            setPhase1Progress({ policyParsing: i });
            appendLog(
              i < 30
                ? `Classifying and extracting text… (page ${Math.ceil((i / 30) * 5)} of ~30)`
                : i < 50
                ? `Chunking and filtering content… (${Math.ceil(((i - 30) / 20) * 180)} chunks)`
                : `Batching for LLM router… (batch ${Math.ceil(((i - 50) / 15) * 12)} of ~12)`,
            );
            await wait(300);
          }
        };

        const animationPromise = animateWaiting();

        // Await the response — cancel the waiting animation immediately
        const response = await extractPromise;
        animationCancelled = true;

        // ── DO NOT check isMounted here — StrictMode cleanup sets it false   ──
        // ── before the response arrives, but hasRun.current blocks a re-run. ──
        // ── Always process the response so the store is updated.             ──

        setSessionId(response.session_id);
        const ruleCount = response.total_rules;
        const ruleItems = response.rules.map(ruleOutputToRuleItem);

        // Mark extraction layers as completed from backend truth first.
        // This avoids stale "pending" UI when StrictMode interrupts local animations.
        setPhase1Progress({ policyParsing: 100, ruleExtraction: 100 });

        if (response.from_cache) {
          // ── Cache hit: fast sweep to 100% (~500ms) ──────────────────────────
          appendLog(`⚡ Cache hit — ${ruleCount} rules served instantly (session ${response.session_id})`);
          appendLog(`   Document: ${response.pdf_name}`);

          for (let i = 0; i <= 100; i += 5) {
            if (!isMounted) break; // break, not return — setResults still runs below
            setPhase1Progress({ policyParsing: i, ruleExtraction: i });
            await wait(10);
          }

          setResults({ rules: ruleItems, violations: [], explanations: [] });
          setPhase1Status("complete");
          setPhase2Status("running");

          for (let i = 0; i <= 100; i += 5) {
            if (!isMounted) break;
            setPhase2Progress({ complianceValidation: i });
            await wait(30);
          }
          for (let i = 0; i <= 100; i += 5) {
            if (!isMounted) break;
            setPhase2Progress({ explainability: i });
            await wait(25);
          }

        } else {
          // ── Fresh extraction: paced completion ──────────────────────────────
          appendLog(
            `Pipeline complete — ${ruleCount} rules extracted in ${(response.processing_time_seconds ?? 0).toFixed(1)}s`,
          );
          setResults({ rules: ruleItems, violations: [], explanations: [] });
          setPhase1Status("complete");
          setPhase2Status("running");

          for (let i = 0; i <= 100; i += 3) {
            if (!isMounted) break;
            setPhase2Progress({ complianceValidation: i });
            await wait(80);
          }
          for (let i = 0; i <= 100; i += 4) {
            if (!isMounted) break;
            setPhase2Progress({ explainability: i });
            await wait(60);
          }
        }

        // ── Step 2: Transaction Processing ───────────────────────────────────
        let txnViolations: ViolationItem[] = [];

        if (transactionFile) {
          appendLog(`Starting transaction validation for "${transactionFile.name}"…`);
          setPhase1Progress({ txnProcessing: 0 });
          
          const validatePromise = validateTransactions(transactionFile);
          
          // Animate txnProcessing bar while waiting for the 3-stage pipeline
          let txnAnimationCancelled = false;
          const animateTxn = async () => {
            for (let i = 0; i <= 90; i += 2) {
              if (!isMounted || txnAnimationCancelled) break;
              setPhase1Progress({ txnProcessing: i });
              if (i === 10) appendLog("Stage 1: Parsing file and detecting schema…");
              if (i === 40) appendLog("Stage 2: Preprocessing and running RBI compliance checks…");
              if (i === 70) appendLog("Stage 3: Persisting cleaned data to SQLite registry…");
              await wait(150);
            }
          };

          const txnAnimPromise = animateTxn();
          const txnResponse = await validatePromise;
          txnAnimationCancelled = true;

          setPipelineStats({
            transactionsInput: txnResponse.rows_input,
            transactionsStored: txnResponse.rows_stored,
            transactionsDropped: txnResponse.rows_dropped,
          });

          txnViolations = mapTxnViolations(txnResponse.violations ?? []);

          if (txnResponse.status === "complete") {
            appendLog(`✅ Transaction pipeline complete: ${txnResponse.rows_stored} rows stored, ${txnResponse.rows_dropped} dropped.`);
            if (!txnResponse.compliance_passed) {
              appendLog(`⚠️ RBI Compliance FAILED: ${txnResponse.violations_count} checks failed.`);
            } else {
              appendLog("✅ RBI Compliance PASSED.");
            }
          } else {
            appendLog(`❌ Transaction pipeline failed: ${txnResponse.error}`);
          }

          setPhase1Progress({ txnProcessing: 100 });
          setResults({ rules: ruleItems, violations: txnViolations, explanations: [] });
          void txnAnimPromise;
        } else {
          appendLog("No transaction file provided — skipping validation stage.");
          setPipelineStats({ transactionsInput: 0, transactionsStored: 0, transactionsDropped: 0 });
          setPhase1Progress({ txnProcessing: 100 });
        }

        // Enrich results with violations from /violations
        try {
          const violationsData = await getViolations();
          setResults({
            rules: violationsData.rules.length > 0 ? violationsData.rules : ruleItems,
            violations: violationsData.violations.length > 0 ? violationsData.violations : txnViolations,
            explanations: violationsData.explanations,
          });
        } catch {
          // Non-fatal — keep locally mapped violations from /validate response
        }

        setPhase2Status("complete");
        void animationPromise;

      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to run pipeline";
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
    policyLink,
    transactionFile,
    setPhase1Progress,
    setPhase1Status,
    setPhase2Progress,
    setPhase2Status,
    setPipelineStats,
    setResults,
    setSessionId,
  ]);

  return (
    <motion.main
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="min-h-screen bg-(--bg-primary) pt-1"
    >
      <div
        className="sticky top-1 z-30 border-b bg-(--bg-primary) px-4 py-3 md:px-6 md:py-4"
        style={{ borderColor: "var(--border-default)" }}
      >
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Shield className="size-5 text-(--accent-navy)" />
            <div>
              <div className="border-l-4 border-l-(--accent-saffron) bg-(--bg-dark) px-3 py-1 text-sm font-bold tracking-[0.08em] text-white">POLICYGUARD.AI</div>
              <div className="max-w-[56vw] truncate text-xs text-(--text-secondary) sm:max-w-[420px]">
                Analysis Workspace - {policySourceName || "Policy source"}
              </div>
            </div>
          </div>
          <button
            className="inline-flex items-center gap-2 rounded-md border border-(--border-default) bg-white px-3 py-2 text-xs font-medium text-(--accent-navy) shadow-sm sm:px-4 sm:text-sm"
            onClick={() => router.push("/")}
          >
            <ArrowLeft className="size-4" />
            New Analysis
          </button>
        </div>
      </div>

      {errorMessage && (
        <div className="mx-auto mt-4 max-w-7xl rounded-md border border-[rgba(204,0,0,0.45)] bg-[rgba(204,0,0,0.08)] px-4 py-3 text-sm text-(--violation)">
          API error: {errorMessage}
          <button
            onClick={() => window.location.reload()}
            className="ml-3 rounded border border-[rgba(204,0,0,0.35)] px-2 py-1 text-xs"
          >
            Retry
          </button>
        </div>
      )}

      <WorkflowLayout />
      <GovernmentFooter />
    </motion.main>
  );
}
