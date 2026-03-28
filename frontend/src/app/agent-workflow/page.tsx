"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Bell, ChevronRight, RotateCcw, AlertTriangle, Activity, Wifi, Zap } from "lucide-react";
import {
  extractFromCircularCode, extractFromPolicyLink, uploadAndExtract,
  getViolations, validateTransactions, ruleOutputToRuleItem,
  type ViolationItem,
} from "@/lib/api";
import { usePipelineStore } from "@/store/pipelineStore";
import { Phase1Panel } from "@/components/workflow/Phase1Panel";
import { Phase2Panel } from "@/components/workflow/Phase2Panel";

// ── Indian National Emblem – Satyameva Jayate (simplified SVG) ───────────────
function SatyamevaJayate({ size = 36 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" aria-label="Satyameva Jayate – National Emblem of India">
      {/* Circular base */}
      <circle cx="32" cy="32" r="30" fill="#FF6600" opacity="0.12" />
      <circle cx="32" cy="32" r="30" fill="none" stroke="#FF6600" strokeWidth="1.5" />
      {/* Ashoka Chakra (24 spokes wheel) */}
      <circle cx="32" cy="37" r="8" fill="none" stroke="#000080" strokeWidth="1.2" />
      <circle cx="32" cy="37" r="2" fill="#000080" />
      {[...Array(24)].map((_, i) => {
        const angle = (i * 360) / 24;
        const rad = (angle * Math.PI) / 180;
        const x1 = 32 + 2 * Math.cos(rad);
        const y1 = 37 + 2 * Math.sin(rad);
        const x2 = 32 + 7.5 * Math.cos(rad);
        const y2 = 37 + 7.5 * Math.sin(rad);
        return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#000080" strokeWidth="0.7" />;
      })}
      {/* Stylized lion silhouette (simplified) */}
      <ellipse cx="32" cy="22" rx="5" ry="4" fill="#FF6600" />
      <ellipse cx="32" cy="25" rx="7" ry="5" fill="#FF6600" />
      {/* Three lions hint */}
      <ellipse cx="24" cy="23" rx="3" ry="3" fill="#FF6600" opacity="0.6" />
      <ellipse cx="40" cy="23" rx="3" ry="3" fill="#FF6600" opacity="0.6" />
      {/* Base platform */}
      <rect x="22" y="28" width="20" height="2.5" rx="1" fill="#FF6600" />
      {/* Devanagari-style text hint */}
      <text x="32" y="60" textAnchor="middle" fontSize="4.5" fill="#138808" fontWeight="bold" fontFamily="serif">सत्यमेव जयते</text>
    </svg>
  );
}

export default function AgentWorkflowPage() {
  const router = useRouter();
  const hasRun = useRef(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(new Date());

  const policyFile      = usePipelineStore((s) => s.uploadedPolicyFile);
  const policyLink      = usePipelineStore((s) => s.policyLink);
  const documentType    = usePipelineStore((s) => s.documentType);
  const transactionFile = usePipelineStore((s) => s.uploadedTransactionFile);
  const phase1Status    = usePipelineStore((s) => s.phase1Status);
  const phase2Status    = usePipelineStore((s) => s.phase2Status);

  const setPhase1Status   = usePipelineStore((s) => s.setPhase1Status);
  const setPhase2Status   = usePipelineStore((s) => s.setPhase2Status);
  const setPhase1Progress = usePipelineStore((s) => s.setPhase1Progress);
  const setPhase2Progress = usePipelineStore((s) => s.setPhase2Progress);
  const setPipelineStats  = usePipelineStore((s) => s.setPipelineStats);
  const setResults        = usePipelineStore((s) => s.setResults);
  const appendLog         = usePipelineStore((s) => s.appendLog);
  const setSessionId      = usePipelineStore((s) => s.setSessionId);

  useEffect(() => {
    const t = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const mapTxnViolations = (raw: Array<Record<string, unknown>>): ViolationItem[] =>
    raw.map((v, i) => {
      const severity = String(v?.severity ?? "MEDIUM").toUpperCase();
      const normalizedSeverity: ViolationItem["severity"] =
        severity === "LOW" || severity === "MEDIUM" || severity === "HIGH" || severity === "CRITICAL"
          ? severity : "MEDIUM";
      const verdictRaw = String(v?.verdict ?? v?.status ?? "VIOLATION").toUpperCase();
      const normalizedStatus: ViolationItem["status"] =
        verdictRaw === "COMPLIANT" ? "COMPLIANT" : verdictRaw === "NEEDS_REVIEW" ? "NEEDS_REVIEW" : "VIOLATION";
      const txId = v?.transactionId ? String(v.transactionId)
        : v?.id ? String(v.id)
        : `TXN-${String(i + 1).padStart(4, "0")}`;
      return {
        id: String(v?.id ?? `VIO-${i + 1}`),
        transactionId: txId,
        amount: typeof v?.amount === "number" ? v.amount : null,
        rule: String(v?.rule ?? "Compliance Rule"),
        severity: normalizedSeverity,
        page: undefined,
        status: normalizedStatus,
        detail: v?.detail ? String(v.detail) : undefined,
        rule_id: v?.rule_id ? String(v.rule_id) : undefined,
        source_document: v?.source_document ? String(v.source_document) : undefined,
        source_document_type: v?.source_document_type ? String(v.source_document_type) : undefined,
      };
    });

  const policySourceName = policyFile?.name ?? policyLink.trim();

  useEffect(() => {
    if (!policyFile && !policyLink.trim()) router.replace("/");
  }, [policyFile, policyLink, router]);

  useEffect(() => {
    const normalizedPolicyLink = policyLink.trim();
    if ((!policyFile && !normalizedPolicyLink) || hasRun.current) return;
    hasRun.current = true;
    let isMounted = true;
    const wait = (ms: number) => new Promise((res) => setTimeout(res, ms));

    const run = async () => {
      try {
        setErrorMessage(null);
        setPhase1Status("running");
        setPipelineStats({ transactionsInput: 0, transactionsStored: 0, transactionsDropped: 0 });
        appendLog(
          policyFile
            ? `Starting PolicyGuard AI pipeline for "${policyFile.name}" (${documentType})…`
            : normalizedPolicyLink.startsWith("[CIRCULAR]")
            ? `Searching for RBI circular: ${normalizedPolicyLink.slice(10)}…`
            : `Starting PolicyGuard AI pipeline for policy link: ${normalizedPolicyLink}`,
        );

        const extractPromise = policyFile
          ? uploadAndExtract(policyFile, documentType)
          : normalizedPolicyLink.startsWith("[CIRCULAR]")
          ? extractFromCircularCode(normalizedPolicyLink.slice(10))
          : extractFromPolicyLink(normalizedPolicyLink);

        let animationCancelled = false;
        const animateWaiting = async () => {
          for (let i = 0; i <= 65; i += 1) {
            if (animationCancelled) break;
            setPhase1Progress({ policyParsing: i });
            appendLog(
              i < 30 ? `Classifying and extracting text… (page ${Math.ceil((i / 30) * 5)} of ~30)`
              : i < 50 ? `Chunking and filtering content… (${Math.ceil(((i - 30) / 20) * 180)} chunks)`
              : `Batching for LLM router… (batch ${Math.ceil(((i - 50) / 15) * 12)} of ~12)`,
            );
            await wait(300);
          }
        };

        const animationPromise = animateWaiting();
        const response = await extractPromise;
        animationCancelled = true;

        setSessionId(response.session_id);
        const ruleCount = response.total_rules;
        const ruleItems = response.rules.map(ruleOutputToRuleItem);
        setPhase1Progress({ policyParsing: 100, ruleExtraction: 100 });

        if (response.from_cache) {
          appendLog(`⚡ Cache hit — ${ruleCount} rules served instantly (session ${response.session_id})`);
          appendLog(`   Document: ${response.pdf_name}`);
          for (let i = 0; i <= 100; i += 5) { setPhase1Progress({ policyParsing: i, ruleExtraction: i }); await wait(10); }
          setResults({ rules: ruleItems, violations: [], explanations: [] });
        } else {
          appendLog(`Pipeline complete — ${ruleCount} rules extracted in ${(response.processing_time_seconds ?? 0).toFixed(1)}s`);
          setResults({ rules: ruleItems, violations: [], explanations: [] });
        }

        let txnViolations: ViolationItem[] = [];
        if (transactionFile) {
          appendLog(`Starting transaction validation for "${transactionFile.name}"…`);
          setPhase1Progress({ txnProcessing: 0 });
          const validatePromise = validateTransactions(transactionFile);
          let txnAnimationCancelled = false;
          const animateTxn = async () => {
            for (let i = 0; i <= 90; i += 2) {
              if (txnAnimationCancelled) break;
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

          const checkedRows = txnResponse.rows_checked ?? txnResponse.rows_stored ?? 0;
          setPipelineStats({
            transactionsInput: txnResponse.rows_input ?? txnResponse.rows_stored ?? 0,
            transactionsStored: checkedRows,
            transactionsDropped: txnResponse.rows_dropped ?? 0,
          });

          if (txnResponse.status === "complete") {
            appendLog(`✅ Stage 1-3 complete: ${txnResponse.rows_stored} rows stored, ${txnResponse.rows_dropped} dropped.`);
            if (txnResponse.rule_check_enabled) {
              appendLog(`✅ Stage 4: Loaded ${txnResponse.rules_applied ?? 0} rules from Supabase registry.`);
              appendLog(
                `✅ Stage 5: Checked ${checkedRows} rows — ` +
                `${txnResponse.violation_count ?? 0} violations, ` +
                `${txnResponse.compliant_count ?? 0} compliant. ` +
                `Compliance Rate: ${txnResponse.compliance_rate ?? 100}%`
              );
              const summary = txnResponse.rule_violation_summary as Record<string, { violations: number }> | undefined;
              if (summary) {
                Object.entries(summary).slice(0, 5).forEach(([rule, info]) => {
                  appendLog(`   ↳ ${rule}: ${info.violations} violations`);
                });
              }
            } else if (txnResponse.rule_check_warning) {
              appendLog(`⚠️ ${txnResponse.rule_check_warning}`);
            }
            if (!txnResponse.compliance_passed) appendLog(`⚠️ Data Quality: ${txnResponse.violations_count} checks failed.`);
          } else {
            appendLog(`❌ Transaction pipeline failed: ${txnResponse.error}`);
          }

          txnViolations = mapTxnViolations(txnResponse.violations ?? []);
          setPhase1Progress({ txnProcessing: 100 });
          setResults({ rules: ruleItems, violations: txnViolations, explanations: [] });
          void txnAnimPromise;
        } else {
          appendLog("No transaction file provided — skipping validation stage.");
          setPipelineStats({ transactionsInput: 0, transactionsStored: 0, transactionsDropped: 0 });
          setPhase1Progress({ txnProcessing: 100 });
        }

        setPhase1Status("complete");
        setPhase2Status("running");

        // Animate Phase 2 engine tracking
        const validationSpeed = response.from_cache ? 15 : 40;
        const explainSpeed = response.from_cache ? 15 : 60;
        
        for (let i = 0; i <= 100; i += 4) { setPhase2Progress({ complianceValidation: i }); await wait(validationSpeed); }
        for (let i = 0; i <= 100; i += 5) { setPhase2Progress({ explainability: i }); await wait(explainSpeed); }

        try {
          const violationsData = await getViolations();
          setResults({
            rules: violationsData.rules.length > 0 ? violationsData.rules : ruleItems,
            violations: violationsData.violations.length > 0 ? violationsData.violations : txnViolations,
            explanations: violationsData.explanations,
          });
        } catch { /* non-fatal */ }

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
    return () => { isMounted = false; };
  }, [appendLog, policyFile, policyLink, transactionFile, setPhase1Progress, setPhase1Status, setPhase2Progress, setPhase2Status, setPipelineStats, setResults, setSessionId]);

  const systemStatus =
    phase1Status === "error" || phase2Status === "error" ? "error"
    : phase2Status === "complete" ? "complete"
    : phase1Status === "running" || phase2Status === "running" ? "running"
    : "idle";

  const statusColor = systemStatus === "complete" ? "#138808" : systemStatus === "error" ? "#CC0000" : systemStatus === "running" ? "#FF6600" : "#9CA3AF";

  return (
    <div className="min-h-screen font-dashboard" style={{ background: "linear-gradient(160deg, #FFFDF5 0%, #FFF8EC 50%, #F0FFF4 100%)" }}>

      {/* ── Indian Tricolor top stripe ─────────────────────────────────────── */}
      <div className="h-1 w-full" style={{ background: "linear-gradient(to right, #FF6600 33.33%, #ffffff 33.33%, #ffffff 66.66%, #138808 66.66%)" }} />

      {/* ── Navigation Bar ──────────────────────────────────────────────────── */}
      <nav className="sticky top-0 z-50 border-b" style={{ background: "rgba(255,253,245,0.95)", borderColor: "#E8D5B0", backdropFilter: "blur(12px)" }}>
        <div className="mx-auto flex max-w-[1600px] items-center justify-between px-6 py-2.5">

          {/* Logo + Emblem */}
          <div className="flex items-center gap-4">
            {/* Satyameva Jayate emblem */}
            <SatyamevaJayate size={48} />

            {/* Brand text */}
            <div className="border-l-2 pl-4" style={{ borderColor: "#FF6600" }}>
              <div className="text-base font-black tracking-widest" style={{ color: "#FF6600" }}>POLICYGUARD.AI</div>
              <div className="text-[10px] font-semibold tracking-[0.18em]" style={{ color: "#138808" }}>RBI · AML · KYC COMPLIANCE MONITORING</div>
            </div>
          </div>

          {/* Center — workspace */}
          <div className="hidden items-center gap-2 md:flex">
            <div className="flex items-center gap-2 rounded-full px-4 py-1.5" style={{ background: "#FFF8EC", border: "1px solid #FFD580" }}>
              <div className="h-1.5 w-1.5 rounded-full" style={{
                background: statusColor,
                boxShadow: systemStatus === "running" ? `0 0 6px ${statusColor}` : "none",
              }} />
              <span className="max-w-64 truncate text-xs font-medium" style={{ color: "#7C5C1E" }} title={policySourceName || "Analysis Workspace"}>
                {policySourceName || "Analysis Workspace"}
              </span>
            </div>
            <ChevronRight className="size-3" style={{ color: "#D4A840" }} />
            <span className="font-mono text-xs" style={{ color: "#9CA3AF" }}>
              {currentTime.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
            </span>
          </div>

          {/* Right */}
          <div className="flex items-center gap-2">
            {/* Status pill */}
            <div className="hidden items-center gap-1.5 rounded-full px-3 py-1.5 text-[10px] font-bold tracking-wider sm:flex"
              style={{ background: `${statusColor}15`, border: `1px solid ${statusColor}40`, color: statusColor }}>
              <Activity className="size-3" />
              {systemStatus === "complete" ? "ANALYSIS DONE" : systemStatus === "running" ? "PROCESSING..." : systemStatus === "error" ? "ERROR" : "INITIALIZING"}
            </div>

            <div className="flex items-center gap-1 text-[9px] font-medium" style={{ color: "#138808" }}>
              <Wifi className="size-3" />
              <span className="hidden sm:inline">Supabase</span>
            </div>
            <div className="flex items-center gap-1 text-[9px] font-medium" style={{ color: "#FF6600" }}>
              <Zap className="size-3" />
              <span className="hidden sm:inline">LLM Live</span>
            </div>

            <button className="relative flex h-8 w-8 items-center justify-center rounded-full transition-all hover:bg-orange-50"
              style={{ border: "1px solid #E8D5B0", color: "#9CA3AF" }}>
              <Bell className="size-4" />
              <div className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full" style={{ background: "#FF6600" }} />
            </button>

            <button
              onClick={() => router.push("/")}
              className="flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-bold text-white transition-all hover:scale-105 active:scale-95"
              style={{ background: "linear-gradient(135deg, #FF6600, #E55A00)", boxShadow: "0 4px 14px rgba(255,102,0,0.35)" }}
            >
              <RotateCcw className="size-3.5" />
              New Analysis
            </button>
          </div>
        </div>
      </nav>

      {/* ── Error Banner ───────────────────────────────────────────────────── */}
      <AnimatePresence>
        {errorMessage && (
          <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
            className="mx-auto mt-4 max-w-[1600px] px-6">
            <div className="flex items-center gap-3 rounded-xl px-4 py-3 text-sm"
              style={{ background: "#FFF1F0", border: "1px solid #FFCCC0", color: "#CC0000" }}>
              <AlertTriangle className="size-4 shrink-0" />
              <span className="flex-1">{errorMessage}</span>
              <button onClick={() => window.location.reload()}
                className="rounded-lg px-3 py-1 text-xs font-semibold transition-all hover:bg-red-100"
                style={{ border: "1px solid #FFCCC0", color: "#CC0000" }}>
                Retry
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Page header ────────────────────────────────────────────────────── */}
      <div className="mx-auto max-w-[1600px] px-6 pt-5">
        <div className="mb-5 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-black" style={{ color: "#1A1A1A" }}>
              Compliance Analysis Pipeline
            </h1>
            <p className="mt-0.5 text-xs font-medium" style={{ color: "#7C5C1E" }}>
              AML · KYC · RBI Policy Violation Detection &amp; Reporting
            </p>
          </div>
          {/* Tricolor decorative stripe */}
          <div className="hidden items-center sm:flex" style={{ gap: 6 }}>
            {["#FF6600", "#138808", "#000080"].map((c) => (
              <div key={c} className="h-6 w-1.5 rounded-full" style={{ background: c }} />
            ))}
          </div>
        </div>

        {/* ── Two-column grid ───────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
          <Phase1Panel />
          <Phase2Panel />
        </div>

        {/* Footer */}
        <div className="mt-8 flex items-center justify-between border-t py-4 text-[10px]"
          style={{ borderColor: "#E8D5B0", color: "#B8A080" }}>
          <span>PolicyGuard.AI — Ministry of Finance · RBI AML/KYC Compliance System</span>
          <span style={{ color: "#138808", fontWeight: 600 }}>सत्यमेव जयते · Code Apex Hackathon 2026</span>
        </div>
      </div>
    </div>
  );
}
