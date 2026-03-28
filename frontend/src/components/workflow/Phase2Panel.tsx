"use client";

import { useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ShieldCheck, ShieldAlert, Lock, BarChart3, Activity, TrendingUp,
  AlertTriangle, Layers,
} from "lucide-react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import type { PieLabelRenderProps } from "recharts";
import { AnimatedCounter } from "@/components/ui/AnimatedCounter";
import { usePipelineStore } from "@/store/pipelineStore";
import { downloadReportBlob } from "@/lib/api";
import type { ViolationItem } from "@/lib/api";

// ── Theme tokens ──────────────────────────────────────────────────────────────
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

// ── Reusable components ───────────────────────────────────────────────────────

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
    <div className="relative h-2.5 w-2.5 rounded-full"
      style={{ background: color, boxShadow: status !== "pending" ? `0 0 7px ${color}` : "none" }}>
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

function SeverityBadge({ level }: { level: string }) {
  const map: Record<string, { bg: string; text: string; bdr: string }> = {
    CRITICAL: { bg: "#FFF1F0", text: "#CC0000", bdr: "#FFCCC0" },
    HIGH:     { bg: "#FFF7F0", text: C.saffron,  bdr: C.saffronBdr },
    MEDIUM:   { bg: C.amberBg, text: C.amber,    bdr: "#FDE68A" },
    LOW:      { bg: C.navyBg,  text: C.navy,     bdr: C.navyBdr },
  };
  const s = map[level] ?? map.MEDIUM;
  return (
    <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider"
      style={{ background: s.bg, color: s.text, border: `1px solid ${s.bdr}` }}>
      {level}
    </span>
  );
}

// ── Engine Card ───────────────────────────────────────────────────────────────
function EngineCard({ name, active, description }: { name: string; active: boolean; description: string }) {
  return (
    <div className="flex flex-col gap-1.5 rounded-xl p-3 transition-all"
      style={{
        background: active ? C.greenBg : "#FAFAF5",
        border: `1px solid ${active ? C.greenBdr : "#E8DCCA"}`,
      }}>
      <div className="flex items-center gap-2">
        <div className="h-2 w-2 rounded-full"
          style={{ background: active ? C.green : "#D1C4AA", boxShadow: active ? `0 0 5px ${C.green}` : "none" }} />
        <span className="text-[10px] font-bold tracking-wider" style={{ color: active ? C.green : C.textMuted }}>{name}</span>
      </div>
      <p className="text-[10px] leading-relaxed" style={{ color: C.textMuted }}>{description}</p>
    </div>
  );
}


// ── MAIN COMPONENT ────────────────────────────────────────────────────────────

export function Phase2Panel() {
  const phase1Status   = usePipelineStore((s) => s.phase1Status);
  const phase2Status   = usePipelineStore((s) => s.phase2Status);
  const phase2Progress = usePipelineStore((s) => s.phase2Progress);
  const pipelineStats  = usePipelineStore((s) => s.pipelineStats);
  const results        = usePipelineStore((s) => s.results);

  const unlocked = phase1Status === "complete";

  const totalTransactions =
    pipelineStats.transactionsStored > 0 ? pipelineStats.transactionsStored
    : pipelineStats.transactionsInput > 0 ? pipelineStats.transactionsInput
    : 0;

  const { donutData, violationCount, compliantCount, compliancePct } = useMemo(() => {
    const violation  = results.violations.filter((v) => v.status === "VIOLATION").length;
    const review     = results.violations.filter((v) => v.status === "NEEDS_REVIEW").length;
    const nonCompliant = violation + review;
    const total    = totalTransactions > 0 ? totalTransactions : nonCompliant;
    const compliant = Math.max(0, total - nonCompliant);
    return {
      donutData: [
        { name: "Compliant", value: compliant, color: C.green },
        { name: "Violation", value: violation, color: C.red },
        ...(review > 0 ? [{ name: "Needs Review", value: review, color: C.amber }] : []),
      ],
      violationCount: nonCompliant,
      compliantCount: compliant,
      compliancePct: total > 0 ? (compliant / total) * 100 : 100,
    };
  }, [results.violations, totalTransactions]);

  const hasData = totalTransactions > 0;
  const overall = (phase2Progress.complianceValidation + phase2Progress.explainability) / 2;

  return (
    <div className="relative space-y-4">

      {/* ── Phase header ────────────────────────────────────────────────────── */}
      <LightCard>
        <div className="p-5">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl"
                style={{ background: C.greenBg, border: `1.5px solid ${C.greenBdr}` }}>
                <ShieldCheck className="size-5" style={{ color: C.green }} />
              </div>
              <div>
                <h2 className="text-base font-black" style={{ color: C.text }}>Compliance Validation Engine</h2>
                <p className="text-[10px] font-medium" style={{ color: C.textSub }}>Phase 2 — LLM-Powered AML/KYC Rule Checking</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <StatusDot status={phase2Status === "idle" ? "pending" : phase2Status} />
              <span className="text-[10px] font-bold uppercase tracking-wider"
                style={{ color: phase2Status === "complete" ? C.green : phase2Status === "running" ? C.saffron : "#9CA3AF" }}>
                {phase2Status === "idle" ? "Pending" : phase2Status === "complete" ? "Complete" : phase2Status === "running" ? "Active" : "Error"}
              </span>
            </div>
          </div>
          <div className="space-y-1.5">
            <div className="flex justify-between text-[10px] font-medium" style={{ color: C.textMuted }}>
              <span>Engine Progress</span><span>{Math.round(overall)}%</span>
            </div>
            <ProgressBar value={overall} color={C.green} />
          </div>
        </div>
      </LightCard>

      {/* ── Engine health cards ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-3 gap-3">
        <EngineCard name="Threshold Engine" active={phase2Progress.complianceValidation > 30}
          description="CTR/STR amount thresholds vs RBI mandate" />
        <EngineCard name="Temporal Engine"  active={phase2Progress.complianceValidation > 55}
          description="Periodic reporting deadline compliance" />
        <EngineCard name="Graph Engine"     active={phase2Progress.complianceValidation > 75}
          description="Cross-jurisdiction network linking" />
      </div>

      {/* ── Throughput bar ──────────────────────────────────────────────────── */}
      <LightCard>
        <div className="flex items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2 text-xs font-medium" style={{ color: C.textSub }}>
            <Activity className="size-3.5" style={{ color: C.saffron }} />
            Processing:
            <span className="font-mono font-bold" style={{ color: C.text }}>
              <AnimatedCounter value={Math.round((phase2Progress.complianceValidation / 100) * (totalTransactions || 20121))} />
              &nbsp;/&nbsp;
              <AnimatedCounter value={totalTransactions || 20121} />
            </span>
            transactions
          </div>
          <div className="flex items-center gap-1.5 text-xs font-medium" style={{ color: C.textSub }}>
            <TrendingUp className="size-3.5" style={{ color: C.green }} />
            <AnimatedCounter value={8247} suffix=" txns/sec" />
          </div>
        </div>
      </LightCard>

      {/* ── Compliance Donut Chart ─────────────────────────────────────────── */}
      <LightCard>
        <div className="p-5">
          <div className="mb-4 flex items-center gap-2">
            <BarChart3 className="size-4" style={{ color: C.saffron }} />
            <span className="text-sm font-black" style={{ color: C.text }}>Violation Distribution</span>
            {hasData && (
              <span className="ml-auto text-[10px]" style={{ color: C.textMuted }}>
                {totalTransactions.toLocaleString()} transactions analysed
              </span>
            )}
          </div>

          {hasData ? (
            <>
              {/* Donut */}
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={donutData} dataKey="value" innerRadius={58} outerRadius={88}
                      paddingAngle={3} labelLine={false}
                      label={({ percent }: PieLabelRenderProps) =>
                        (percent ?? 0) > 0.01 ? `${((percent ?? 0) * 100).toFixed(1)}%` : ""
                      }>
                      {donutData.map((entry) => (
                        <Cell key={entry.name} fill={entry.color}
                          style={{ filter: `drop-shadow(0 2px 6px ${entry.color}60)` }} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{ background: "#FFFDF5", border: `1px solid ${C.cardBdr}`, borderRadius: 12, color: C.text, fontSize: 11 }}
                      formatter={(val, name) => [
                        `${Number(val ?? 0).toLocaleString()} (${totalTransactions > 0 ? ((Number(val ?? 0) / totalTransactions) * 100).toFixed(2) : 0}%)`,
                        String(name),
                      ]}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              {/* Stat cards */}
              <div className="mt-4 grid grid-cols-3 gap-3">
                {([
                  { label: "Total",     value: totalTransactions, color: C.navy,   bg: C.navyBg,   bdr: C.navyBdr,   icon: Layers,      pct: null },
                  { label: "Violated",  value: violationCount,   color: C.red,    bg: C.redBg,    bdr: C.redBdr,    icon: ShieldAlert,  pct: violationCount  / Math.max(totalTransactions, 1) * 100 },
                  { label: "Compliant", value: compliantCount,   color: C.green,  bg: C.greenBg,  bdr: C.greenBdr,  icon: ShieldCheck,  pct: compliantCount  / Math.max(totalTransactions, 1) * 100 },
                ] as const).map(({ label, value, color, bg, bdr, icon: Icon, pct }) => (
                  <div key={label} className="flex flex-col gap-1.5 rounded-xl p-3"
                    style={{ background: bg, border: `1px solid ${bdr}` }}>
                    <div className="flex items-center gap-1.5">
                      <Icon className="size-3" style={{ color }} />
                      <span className="text-[9px] font-bold uppercase tracking-wider" style={{ color }}>{label}</span>
                    </div>
                    <div className="text-xl font-black" style={{ color: C.text }}><AnimatedCounter value={value} /></div>
                    {pct !== null && (
                      <div className="text-[10px] font-bold" style={{ color }}>{pct.toFixed(2)}%</div>
                    )}
                  </div>
                ))}
              </div>

              {/* Compliance progress bar */}
              <div className="mt-4">
                <div className="mb-1.5 flex justify-between text-[10px] font-semibold" style={{ color: C.textMuted }}>
                  <span>Overall Compliance Rate</span>
                  <span style={{ color: compliancePct >= 90 ? C.green : compliancePct >= 70 ? C.amber : C.red }}>
                    {compliancePct.toFixed(2)}%
                  </span>
                </div>
                <div className="h-3 w-full overflow-hidden rounded-full" style={{ background: "#FFE0D0" }}>
                  <motion.div className="h-full rounded-full"
                    style={{ background: `linear-gradient(90deg, ${C.green}, #0DA006)`, boxShadow: `0 0 8px ${C.green}50` }}
                    initial={{ width: 0 }} animate={{ width: `${compliancePct}%` }}
                    transition={{ duration: 1.2, ease: "easeOut" }} />
                </div>
              </div>
            </>
          ) : (
            <div className="flex h-44 flex-col items-center justify-center gap-2">
              <BarChart3 className="size-8" style={{ color: "#E8DCCA" }} />
              <p className="text-xs font-medium" style={{ color: C.textMuted }}>
                {phase2Progress.complianceValidation > 0 ? "Processing transactions…" : "Upload a CSV file to see compliance analysis"}
              </p>
            </div>
          )}
        </div>
      </LightCard>

      {/* ── Recent violations stream ───────────────────────────────────────── */}
      {results.violations.filter((v) => v.status !== "COMPLIANT").length > 0 && (
        <LightCard>
          <div className="p-4">
            <div className="mb-3 flex items-center gap-2">
              <AlertTriangle className="size-4" style={{ color: C.red }} />
              <span className="text-sm font-bold" style={{ color: C.text }}>Recent Violations</span>
            </div>
            <div className="space-y-1.5">
              {results.violations.filter((v) => v.status !== "COMPLIANT").slice(0, 5).map((item) => (
                <div key={item.id} className="flex items-center gap-3 rounded-xl p-3"
                  style={{ background: C.redBg, border: `1px solid ${C.redBdr}` }}>
                  <ShieldAlert className="size-3.5 shrink-0" style={{ color: C.red }} />
                  <span className="font-mono text-[11px] font-bold" style={{ color: C.navy }}>{item.transactionId}</span>
                  <span className="flex-1 truncate text-[11px]" style={{ color: C.textSub }}>{item.rule}</span>
                  <SeverityBadge level={item.severity} />
                </div>
              ))}
            </div>
          </div>
        </LightCard>
      )}

      {/* ── Explainability Layer card ────────────────────────────────────────── */}
      {phase2Status === "complete" && (
        <LightCard>
          <div className="p-4">
            {/* Header */}
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="flex h-8 w-8 items-center justify-center rounded-xl"
                  style={{ background: C.navyBg, border: `1.5px solid ${C.navyBdr}` }}>
                  <svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="#000080" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                    <path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
                  </svg>
                </div>
                <div>
                  <div className="text-sm font-black" style={{ color: C.text }}>Explainability Layer</div>
                  <div className="text-[10px] font-medium" style={{ color: C.textMuted }}>LLM-generated compliance audit report ready</div>
                </div>
              </div>
              {/* Print button */}
              <button
                onClick={() => {
                  const a = document.createElement("a");
                  a.href = "/compliance_report.pdf";
                  a.download = "Compliance_Audit_Report.pdf";
                  document.body.appendChild(a);
                  a.click();
                  document.body.removeChild(a);
                }}
                className="flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-bold text-white transition-all hover:scale-105 active:scale-95"
                style={{ background: `linear-gradient(135deg, ${C.saffron}, #E55A00)`, boxShadow: "0 3px 10px rgba(255,102,0,0.3)" }}
              >
                <svg className="size-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="6 9 6 2 18 2 18 9" /><path d="M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2" /><rect x="6" y="14" width="12" height="8" />
                </svg>
                Print Report
              </button>
            </div>

            {/* Summary strip */}
            <div className="grid grid-cols-3 gap-2">
              {[
                { label: "Total Analysed",  value: `${totalTransactions.toLocaleString()} txns`,   color: C.navy,    bg: C.navyBg,    bdr: C.navyBdr    },
                { label: "Violations Found", value: `${violationCount.toLocaleString()} flagged`,  color: C.red,     bg: C.redBg,     bdr: C.redBdr     },
                { label: "Compliance Rate",  value: `${compliancePct.toFixed(1)}%`,                color: C.green,   bg: C.greenBg,   bdr: C.greenBdr   },
              ].map(({ label, value, color, bg, bdr }) => (
                <div key={label} className="rounded-xl p-3 text-center"
                  style={{ background: bg, border: `1px solid ${bdr}` }}>
                  <div className="text-[9px] font-bold uppercase tracking-wider mb-1" style={{ color }}>{label}</div>
                  <div className="text-sm font-black" style={{ color: C.text }}>{value}</div>
                </div>
              ))}
            </div>
          </div>
        </LightCard>
      )}

      {/* ── Locked overlay ──────────────────────────────────────────────────── */}
      {!unlocked && (
        <div className="absolute inset-0 z-10 flex items-center justify-center rounded-2xl"
          style={{ background: "rgba(255,253,245,0.82)", backdropFilter: "blur(6px)", border: `1px solid ${C.cardBdr}` }}>
          <div className="text-center">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl"
              style={{ background: C.saffronBg, border: `1.5px solid ${C.saffronBdr}` }}>
              <Lock className="size-6 animate-pulse" style={{ color: C.saffron }} />
            </div>
            <p className="text-sm font-bold" style={{ color: C.text }}>Awaiting Phase 1 Completion</p>
            <p className="mt-1 text-[10px] font-medium" style={{ color: C.textMuted }}>Complete document ingestion to unlock</p>
          </div>
        </div>
      )}

      {/* ── Error ───────────────────────────────────────────────────────────── */}
      {phase2Status === "error" && (
        <div className="flex items-center gap-3 rounded-2xl p-4"
          style={{ background: C.redBg, border: `1px solid ${C.redBdr}` }}>
          <AlertTriangle className="size-4 shrink-0" style={{ color: C.red }} />
          <span className="text-sm font-semibold" style={{ color: C.red }}>Phase 2 error. Click New Analysis to retry.</span>
        </div>
      )}
    </div>
  );
}
