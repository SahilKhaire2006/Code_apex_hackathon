"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  CheckCircle2, FileText, Cpu, Database, ChevronDown, ChevronUp,
  Layers, Zap, Clock, Hash,
} from "lucide-react";
import { AnimatedCounter } from "@/components/ui/AnimatedCounter";
import { usePipelineStore } from "@/store/pipelineStore";

// ── Theme tokens (Indian Tricolor light) ─────────────────────────────────────
const C = {
  saffron:    "#FF6600",
  saffronBg:  "#FFF3E6",
  saffronBdr: "#FFD0A0",
  green:      "#138808",
  greenBg:    "#F0FFF4",
  greenBdr:   "#A8E6B0",
  navy:       "#000080",
  navyBg:     "#EEF0FF",
  navyBdr:    "#BACAFB",
  card:       "#FFFFFF",
  cardBdr:    "#E8D5B0",
  pageBg:     "#FFFDF5",
  text:       "#1A1A1A",
  textSub:    "#6B5B3E",
  textMuted:  "#9C8060",
  red:        "#CC0000",
  redBg:      "#FFF1F0",
  redBdr:     "#FFCCC0",
  amber:      "#D97706",
  amberBg:    "#FFFBEB",
};

// ── Shared sub-components ─────────────────────────────────────────────────────

function LightCard({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-2xl ${className}`}
      style={{ background: C.card, border: `1px solid ${C.cardBdr}`, boxShadow: "0 2px 12px rgba(139,90,0,0.06)" }}>
      {children}
    </div>
  );
}

function StatusDot({ status }: { status: "pending" | "running" | "complete" | "error" }) {
  const colors = { pending: "#9CA3AF", running: C.saffron, complete: C.green, error: C.red };
  const color = colors[status];
  return (
    <div className="relative h-2.5 w-2.5 rounded-full" style={{ background: color, boxShadow: status !== "pending" ? `0 0 7px ${color}` : "none" }}>
      {status === "running" && <div className="absolute inset-0 rounded-full animate-ping" style={{ background: color, opacity: 0.35 }} />}
    </div>
  );
}

function ProgressBar({ value, color = C.saffron }: { value: number; color?: string }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full" style={{ background: "#F0E8D8" }}>
      <motion.div className="h-full rounded-full"
        style={{ background: `linear-gradient(90deg, ${color}, ${color}CC)`, boxShadow: `0 0 5px ${color}50` }}
        initial={{ width: 0 }} animate={{ width: `${Math.min(100, value)}%` }}
        transition={{ duration: 0.6, ease: "easeOut" }} />
    </div>
  );
}

function StepCard({
  icon: Icon, title, status, progress, children, stepNumber,
}: {
  icon: React.ElementType; title: string;
  status: "pending" | "running" | "complete" | "error";
  progress: number; children: React.ReactNode; stepNumber: number;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const barColor = status === "complete" ? C.green : status === "running" ? C.saffron : "#D1C4AA";
  const iconBg   = status === "complete" ? C.greenBg : status === "running" ? C.saffronBg : "#F5F0E8";
  const iconClr  = status === "complete" ? C.green  : status === "running" ? C.saffron  : "#9C8060";

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: stepNumber * 0.07 }}>
      <LightCard>
        <button onClick={() => setCollapsed((c) => !c)} className="flex w-full items-center gap-3 p-4 text-left">
          {/* Icon circle */}
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl"
            style={{ background: iconBg, border: `1.5px solid ${status === "complete" ? C.greenBdr : status === "running" ? C.saffronBdr : "#E2D5BE"}` }}>
            {status === "complete"
              ? <CheckCircle2 className="size-4.5" style={{ color: C.green }} />
              : <Icon className="size-4.5" style={{ color: iconClr }} />}
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-bold" style={{ color: C.text }}>{title}</span>
              <div className="flex items-center gap-2">
                <span className="rounded-full px-2.5 py-0.5 text-[9px] font-bold uppercase tracking-wider"
                  style={{
                    background: status === "complete" ? C.greenBg : status === "running" ? C.saffronBg : "#F5F0E8",
                    color:      status === "complete" ? C.green   : status === "running" ? C.saffron  : "#9C8060",
                    border:     `1px solid ${status === "complete" ? C.greenBdr : status === "running" ? C.saffronBdr : "#D5C5A8"}`,
                  }}>
                  {status === "complete" ? "DONE" : status === "running" ? `${Math.round(progress)}%` : "PENDING"}
                </span>
                {collapsed
                  ? <ChevronDown className="size-3.5" style={{ color: C.textMuted }} />
                  : <ChevronUp   className="size-3.5" style={{ color: C.textMuted }} />}
              </div>
            </div>
            <div className="mt-2">
              <ProgressBar value={progress} color={barColor} />
            </div>
          </div>
        </button>

        <AnimatePresence>
          {!collapsed && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.22 }} className="overflow-hidden">
              <div className="px-4 pb-4 pt-0">{children}</div>
            </motion.div>
          )}
        </AnimatePresence>
      </LightCard>
    </motion.div>
  );
}

function MetricTile({ label, value, suffix = "", icon: Icon, color = C.saffron }: {
  label: string; value: number; suffix?: string; icon?: React.ElementType; color?: string;
}) {
  return (
    <div className="flex flex-col gap-1.5 rounded-xl p-3"
      style={{ background: "#FFFBF5", border: "1px solid #EDE0C8" }}>
      <div className="flex items-center gap-1.5">
        {Icon && <Icon className="size-3" style={{ color }} />}
        <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: C.textMuted }}>{label}</span>
      </div>
      <div className="text-lg font-black" style={{ color: C.text }}>
        <AnimatedCounter value={value} />{suffix}
      </div>
    </div>
  );
}

function LogPanel({ logs }: { logs: string[] }) {
  return (
    <div className="h-28 overflow-y-auto rounded-xl p-3 font-mono text-[10px] leading-relaxed"
      style={{ background: "#FAFAF2", border: "1px solid #E8DCCA" }}>
      {logs.length === 0
        ? <span style={{ color: "#C4B8A0" }}>Awaiting pipeline start…</span>
        : logs.map((log, i) => (
          <div key={i} style={{
            color: log.includes("✅") ? C.green : log.includes("❌") ? C.red : log.includes("⚠") ? C.amber : "#7C5C3E"
          }}>
            <span style={{ color: "#D4C4A8", marginRight: 8 }}>›</span>
            {log}
          </div>
        ))}
    </div>
  );
}

// ── MAIN COMPONENT ────────────────────────────────────────────────────────────

export function Phase1Panel() {
  const phase1Status   = usePipelineStore((s) => s.phase1Status);
  const phase1Progress = usePipelineStore((s) => s.phase1Progress);
  const pipelineStats  = usePipelineStore((s) => s.pipelineStats);
  const logs           = usePipelineStore((s) => s.logs);
  const rules          = usePipelineStore((s) => s.results.rules);

  const totalPages  = pipelineStats.pages  > 0 ? pipelineStats.pages  : 24;
  const totalChunks = pipelineStats.chunks > 0 ? pipelineStats.chunks : 187;
  const txnTotal    = pipelineStats.transactionsInput > 0 ? pipelineStats.transactionsInput : 20121;
  const txnLoaded   =
    pipelineStats.transactionsStored > 0
      ? pipelineStats.transactionsStored
      : Math.round((phase1Progress.txnProcessing / 100) * txnTotal);

  const totalRules = rules.length;
  const sev = rules.reduce(
    (acc, r) => {
      if (r.severity === "LOW")      acc.low++;
      if (r.severity === "MEDIUM")   acc.med++;
      if (r.severity === "HIGH")     acc.high++;
      if (r.severity === "CRITICAL") acc.crit++;
      return acc;
    },
    { low: 0, med: 0, high: 0, crit: 0 },
  );

  const overall     = (phase1Progress.policyParsing + phase1Progress.ruleExtraction + phase1Progress.txnProcessing) / 3;
  const parseStatus = phase1Progress.policyParsing  >= 100 ? "complete" : phase1Progress.policyParsing  > 0 ? "running" : "pending";
  const ruleStatus  = phase1Progress.ruleExtraction >= 100 ? "complete" : phase1Progress.ruleExtraction > 0 ? "running" : "pending";
  const txnStatus   = phase1Progress.txnProcessing  >= 100 ? "complete" : phase1Progress.txnProcessing  > 0 ? "running" : "pending";

  return (
    <div className="space-y-4">

      {/* ── Phase header ───────────────────────────────────────────────────── */}
      <LightCard>
        <div className="p-5">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl"
                style={{ background: C.saffronBg, border: `1.5px solid ${C.saffronBdr}` }}>
                <Layers className="size-5" style={{ color: C.saffron }} />
              </div>
              <div>
                <h2 className="text-base font-black" style={{ color: C.text }}>Data Ingestion Pipeline</h2>
                <p className="text-[10px] font-medium" style={{ color: C.textSub }}>Phase 1 — Document Processing &amp; Rule Extraction</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <StatusDot status={phase1Status === "idle" ? "pending" : phase1Status} />
              <span className="text-[10px] font-bold uppercase tracking-wider"
                style={{ color: phase1Status === "complete" ? C.green : phase1Status === "running" ? C.saffron : "#9CA3AF" }}>
                {phase1Status === "idle" ? "Pending" : phase1Status === "complete" ? "Complete" : phase1Status === "running" ? "Active" : "Error"}
              </span>
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="flex justify-between text-[10px] font-medium" style={{ color: C.textMuted }}>
              <span>Overall Progress</span><span>{Math.round(overall)}%</span>
            </div>
            <ProgressBar value={overall} color={C.saffron} />
          </div>
        </div>
      </LightCard>

      {/* ── Step 1: PDF Parsing ────────────────────────────────────────────── */}
      <StepCard icon={FileText} title="Policy PDF Parsing" status={parseStatus}
        progress={phase1Progress.policyParsing} stepNumber={0}>
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2">
            <MetricTile label="Pages"   value={Math.round((phase1Progress.policyParsing / 100) * totalPages)}  icon={Hash}         color={C.navy} />
            <MetricTile label="Chunks"  value={Math.round((phase1Progress.policyParsing / 100) * totalChunks)} icon={Layers}       color={C.saffron} />
            <MetricTile label="Indexed" value={phase1Progress.policyParsing} suffix="%" icon={CheckCircle2}   color={C.green} />
          </div>
          <LogPanel logs={logs.slice(-12)} />
        </div>
      </StepCard>

      {/* ── Step 2: Rule Extraction ─────────────────────────────────────────── */}
      <StepCard icon={Cpu} title="AI Rule Extraction" status={ruleStatus}
        progress={phase1Progress.ruleExtraction} stepNumber={1}>
        <div className="space-y-3">
          {/* LLM label */}
          <div className="flex items-center gap-2 rounded-xl p-3 text-xs font-medium"
            style={{ background: C.amberBg, border: "1px solid #FDE68A", color: C.amber }}>
            <Zap className="size-3.5" />
            Meta-Llama 3 analyzing policy clauses
            <span className="ml-auto font-bold" style={{ color: C.text }}>{totalRules} rules</span>
          </div>

          {/* Severity bars */}
          <div className="grid grid-cols-4 gap-2">
            {([
              ["LOW",  sev.low,  "#6B7280", "#F3F4F6", "#D1D5DB"],
              ["MED",  sev.med,  C.amber,   C.amberBg, "#FDE68A"],
              ["HIGH", sev.high, C.red,     C.redBg,   C.redBdr],
              ["CRIT", sev.crit, "#7C1D6F", "#FDF4FF", "#E9D5FF"],
            ] as [string, number, string, string, string][]).map(([label, count, color, bg, bdr]) => (
              <div key={label} className="flex flex-col gap-1.5 rounded-xl p-2.5"
                style={{ background: bg, border: `1px solid ${bdr}` }}>
                <div className="flex items-center justify-between">
                  <span className="text-[9px] font-bold tracking-wider" style={{ color }}>{label}</span>
                  <span className="text-sm font-black" style={{ color: C.text }}>{count}</span>
                </div>
                <div className="h-1 rounded-full overflow-hidden" style={{ background: "#E8E0D0" }}>
                  <div className="h-full rounded-full transition-all duration-700"
                    style={{ width: `${totalRules > 0 ? (count / totalRules) * 100 : 0}%`, background: color }} />
                </div>
              </div>
            ))}
          </div>

          {totalRules > 0 && (
            <div className="rounded-xl p-3" style={{ background: C.saffronBg, border: `1px solid ${C.saffronBdr}` }}>
              <div className="text-[10px] font-semibold mb-1" style={{ color: C.textMuted }}>Latest extracted rule</div>
              <div className="text-xs font-semibold truncate" style={{ color: C.text }}>
                {rules[rules.length - 1]?.title ?? "Awaiting extraction…"}
              </div>
            </div>
          )}
        </div>
      </StepCard>

      {/* ── Step 3: Transaction Processing ─────────────────────────────────── */}
      <StepCard icon={Database} title="Transaction Processing" status={txnStatus}
        progress={phase1Progress.txnProcessing} stepNumber={2}>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <MetricTile label="Loaded" value={txnLoaded} icon={Database} color={C.green} />
            <MetricTile label="Total"  value={txnTotal}  icon={Clock}    color={C.navy}  />
          </div>

          <div className="space-y-1.5">
            {[
              { label: "Multi-format file parsing & schema detection", threshold: 20  },
              { label: "RBI compliance pre-filtering & null removal",  threshold: 50  },
              { label: "SQLite persistence & pickle registry",         threshold: 80  },
              { label: "LLM violation matrix generation complete",     threshold: 100 },
            ].map(({ label, threshold }) => {
              const done = phase1Progress.txnProcessing >= threshold;
              return (
                <div key={label} className="flex items-center gap-2.5 rounded-lg px-3 py-2 transition-all"
                  style={{
                    background: done ? C.greenBg  : "#FAFAF5",
                    border:     `1px solid ${done ? C.greenBdr : "#E8DCCA"}`,
                  }}>
                  <div className="h-1.5 w-1.5 shrink-0 rounded-full"
                    style={{ background: done ? C.green : "#D1C4AA", boxShadow: done ? `0 0 5px ${C.green}` : "none" }} />
                  <span className="text-[11px] font-medium" style={{ color: done ? C.green : C.textMuted }}>{label}</span>
                </div>
              );
            })}
          </div>
        </div>
      </StepCard>

      {/* ── Phase complete banner ───────────────────────────────────────────── */}
      <AnimatePresence>
        {phase1Status === "complete" && (
          <motion.div initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}
            className="flex items-center gap-3 rounded-2xl p-4"
            style={{ background: C.greenBg, border: `1.5px solid ${C.greenBdr}` }}>
            <div className="flex h-9 w-9 items-center justify-center rounded-xl"
              style={{ background: "#D1FAE5" }}>
              <CheckCircle2 className="size-5" style={{ color: C.green }} />
            </div>
            <div>
              <div className="text-sm font-bold" style={{ color: C.green }}>Phase 1 Complete</div>
              <div className="text-[10px] font-medium" style={{ color: "#2D8C3F" }}>Handing off to Compliance Validation Engine →</div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
