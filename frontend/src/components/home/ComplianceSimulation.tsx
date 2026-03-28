"use client";

import { useEffect, useMemo, useState, useRef } from "react";
import { AlertCircle, CheckCircle2, RotateCcw, ShieldAlert, FileText, Activity } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { AnimatedCounter } from "@/components/ui/AnimatedCounter";
import { formatCurrency } from "@/lib/utils";

// Theme constants matching Phase2Panel
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
  amberBdr:   "#FDE68A",
};

type Verdict = "COMPLIANT" | "VIOLATION" | "NEEDS_REVIEW";
const severities = ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;

function makeRule(step: number) {
  const fields = ["transaction_amount", "origin_country", "velocity_30d", "counterparty_risk"];
  const ops = [">", "in", "<", "=="];
  const thresholds = [100000, "FATF-Blacklist", 12, "High"];
  return {
    id: `R-${Math.floor(1000 + Math.random() * 9000)}`,
    field: fields[step % 4],
    operator: ops[step % 4],
    threshold: thresholds[step % 4],
    severity: severities[step % severities.length],
  };
}

function makeTxn(step: number): { id: string; amount: number; verdict: Verdict; ruleViolated?: string } {
  const cycle = step % 10;
  const verdict: Verdict = cycle > 7 ? "VIOLATION" : cycle > 5 ? "NEEDS_REVIEW" : "COMPLIANT";
  return {
    id: `TXN-${(780000 + step).toString()}`,
    amount: Math.round(2000 + Math.random() * 150000),
    verdict,
    ruleViolated: verdict !== "COMPLIANT" ? `R-${Math.floor(1000 + Math.random() * 9000)}` : undefined
  };
}

export function ComplianceSimulation() {
  const [running, setRunning] = useState(true);
  const [cursor, setCursor] = useState(0);
  const [page, setPage] = useState(1);
  const [chunks, setChunks] = useState(0);
  const [rules, setRules] = useState<ReturnType<typeof makeRule>[]>([]);
  const [txns, setTxns] = useState<ReturnType<typeof makeTxn>[]>([]);
  const txnStepRef = useRef(0);

  useEffect(() => {
    if (!running) return;

    const timer = setInterval(() => {
      setCursor((v) => (v + 1) % 18);
      setPage((p) => (p % 12) + 1);
      setChunks((c) => c + Math.floor(Math.random() * 4) + 1);
      
      // Add a rule every other step
      if (Math.random() > 0.4) {
        setRules((prev) => [...prev.slice(-4), makeRule(Date.now() + prev.length)]);
      }
      
      // Add 1-2 txns every step
      setTxns((prev) => {
        txnStepRef.current += 1;
        const t1 = makeTxn(txnStepRef.current);
        let t2 = null;
        if (Math.random() > 0.5) {
          txnStepRef.current += 1;
          t2 = makeTxn(txnStepRef.current);
        }
        const newTxns = t2 ? [t1, t2] : [t1];
        return [...prev, ...newTxns].slice(-7);
      });
    }, 800);

    return () => clearInterval(timer);
  }, [running]);

  const totals = useMemo(() => {
    return txns.reduce(
      (acc, txn) => {
        if (txn.verdict === "COMPLIANT") acc.compliant += 1;
        if (txn.verdict === "VIOLATION") acc.violations += 1;
        if (txn.verdict === "NEEDS_REVIEW") acc.review += 1;
        return acc;
      },
      { compliant: 0, violations: 0, review: 0 },
    );
  }, [txns]);

  return (
    <section className="mx-auto max-w-7xl px-6 py-10 pb-24">
      <div className="mb-8 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h2 className="text-3xl font-black" style={{ color: C.text }}>Live Compliance Simulation</h2>
          <p className="mt-2 text-sm font-medium" style={{ color: C.textSub }}>Watch PolicyGuard's LLM pipeline process an RBI circular and evaluate streaming transactions in real time.</p>
        </div>
        <button
          className="inline-flex items-center gap-2 rounded-xl border px-4 py-2.5 text-xs font-bold transition-all hover:scale-105 active:scale-95"
          style={{ background: C.card, borderColor: C.cardBdr, color: C.navy, boxShadow: "0 2px 10px rgba(139,90,0,0.06)" }}
          onClick={() => {
            setRules([]);
            setTxns([]);
            setChunks(0);
            txnStepRef.current = 0;
            setRunning(false);
            requestAnimationFrame(() => setRunning(true));
          }}
        >
          <RotateCcw className="size-3.5" />
          Restart Engine
        </button>
      </div>

      <div className="rounded-2xl border p-4 sm:p-6 lg:p-8" style={{ background: C.pageBg, borderColor: C.cardBdr, boxShadow: "inset 0 2px 14px rgba(139,90,0,0.03)" }}>
        <div className="grid gap-6 lg:grid-cols-3">
          
          {/* 1. Document Ingestion */}
          <div className="flex h-[440px] w-full flex-col rounded-2xl border p-4" style={{ background: C.card, borderColor: "#E8DCCA", boxShadow: "0 4px 20px rgba(139,90,0,0.05)" }}>
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg" style={{ background: C.navyBg, border: `1px solid ${C.navyBdr}` }}>
                  <FileText className="size-4" style={{ color: C.navy }} />
                </div>
                <span className="text-sm font-black tracking-tight" style={{ color: C.text }}>Document Ingestion</span>
              </div>
              <span className="text-[10px] font-bold" style={{ color: C.textMuted }}>Page {page} / 12</span>
            </div>
            
            {/* Fake PDF Lines */}
            <div className="relative h-64 w-full overflow-hidden rounded-xl border p-4" style={{ background: "#FAFAF5", borderColor: "#E8DCCA" }}>
              <div className="absolute inset-0 z-10 bg-gradient-to-b from-[#FAFAF5]/10 via-transparent to-[#FAFAF5]" />
              {Array.from({ length: 18 }).map((_, line) => (
                <div
                  key={line}
                  className="mb-2 h-1.5 rounded-full transition-colors duration-300"
                  style={{
                    width: `${40 + Math.random() * 50}%`,
                    background: line === cursor ? C.saffron : "#E8DCCA",
                    boxShadow: line === cursor ? `0 0 8px ${C.saffron}` : "none",
                  }}
                />
              ))}
              <motion.div
                className="pointer-events-none absolute left-0 right-0 z-20 h-[100px] bg-gradient-to-b from-transparent via-[#FF6600]/10 to-transparent"
                animate={{ y: [-100, 300] }}
                transition={{ duration: 2.5, repeat: Infinity, ease: "linear" }}
              />
            </div>
            {/* Metrics */}
            <div className="mt-4 flex items-center justify-between rounded-xl px-3 py-2.5" style={{ background: C.saffronBg, border: `1px solid ${C.saffronBdr}` }}>
              <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: C.saffron }}>Chunks Extracted</span>
              <span className="font-mono text-sm font-black" style={{ color: C.saffron }}><AnimatedCounter value={chunks} /></span>
            </div>
          </div>

          {/* 2. Structured Rules Generator */}
          <div className="flex h-[440px] w-full flex-col rounded-2xl border p-4" style={{ background: C.card, borderColor: "#E8DCCA", boxShadow: "0 4px 20px rgba(139,90,0,0.05)" }}>
            <div className="mb-4 flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg" style={{ background: C.saffronBg, border: `1px solid ${C.saffronBdr}` }}>
                <Activity className="size-4" style={{ color: C.saffron }} />
              </div>
              <span className="text-sm font-black tracking-tight" style={{ color: C.text }}>Extracted Rules Stream</span>
            </div>
            
            <div className="flex-1 space-y-2.5 overflow-hidden">
              <AnimatePresence mode="popLayout">
                {rules.map((rule) => (
                  <motion.div
                    key={rule.id}
                    layout
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    transition={{ type: "spring", stiffness: 400, damping: 25 }}
                    className="rounded-xl border p-3"
                    style={{ background: "#FAFAF5", borderColor: "#E8DCCA" }}
                  >
                    <div className="mb-2 flex items-center justify-between">
                      <span className="font-mono text-[10px] font-bold" style={{ color: C.navy }}>{rule.id}</span>
                      <span className="rounded-full px-1.5 py-0.5 text-[8px] font-black uppercase tracking-wider" style={{ background: C.amberBg, color: C.amber, border: `1px solid ${C.amberBdr || "#FDE68A"}` }}>{rule.severity}</span>
                    </div>
                    <div className="font-mono text-[10px] space-y-1">
                      <div className="flex justify-between"><span style={{ color: C.textMuted }}>field</span><span style={{ color: C.text }}>"{rule.field}"</span></div>
                      <div className="flex justify-between"><span style={{ color: C.textMuted }}>condition</span><span className="font-bold" style={{ color: C.green }}>{rule.operator} {rule.threshold}</span></div>
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          </div>

          {/* 3. Transaction Validation */}
          <div className="flex h-[440px] w-full flex-col rounded-2xl border p-4" style={{ background: C.card, borderColor: "#E8DCCA", boxShadow: "0 4px 20px rgba(139,90,0,0.05)" }}>
            <div className="mb-4 flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg" style={{ background: C.greenBg, border: `1px solid ${C.greenBdr}` }}>
                <ShieldAlert className="size-4" style={{ color: C.green }} />
              </div>
              <span className="text-sm font-black tracking-tight" style={{ color: C.text }}>Live Validation Engine</span>
            </div>

            <div className="flex-1 space-y-2 overflow-hidden">
              <AnimatePresence mode="popLayout">
                {txns.map((txn) => {
                  const isViol = txn.verdict === "VIOLATION";
                  const isRev = txn.verdict === "NEEDS_REVIEW";
                  const color = isViol ? C.red : isRev ? C.saffron : C.green;
                  const bg = isViol ? C.redBg : isRev ? C.saffronBg : C.greenBg;
                  const bdr = isViol ? C.redBdr : isRev ? C.saffronBdr : C.greenBdr;
                  
                  return (
                    <motion.div
                      key={txn.id}
                      layout
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, scale: 0.9 }}
                      transition={{ type: "spring", stiffness: 450, damping: 25 }}
                      className="flex items-center justify-between rounded-xl border p-3"
                      style={{ background: bg, borderColor: bdr }}
                    >
                      <div className="flex flex-col gap-1">
                        <span className="font-mono text-[11px] font-bold" style={{ color: C.text }}>{txn.id}</span>
                        <div className="flex items-center gap-1.5">
                          {isViol ? <ShieldAlert className="size-3" style={{ color }} /> : 
                           isRev ? <AlertCircle className="size-3" style={{ color }} /> : 
                           <CheckCircle2 className="size-3" style={{ color }} />}
                          <span className="text-[9px] font-black uppercase tracking-wider" style={{ color }}>{txn.verdict.replace("_", " ")}</span>
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        <span className="font-mono text-[11px] font-semibold" style={{ color: C.textSub }}>{formatCurrency(txn.amount)}</span>
                        {txn.ruleViolated && <span className="text-[9px] font-medium" style={{ color }}>Failed: {txn.ruleViolated}</span>}
                      </div>
                    </motion.div>
                  )
                })}
              </AnimatePresence>
            </div>
            
            {/* Totals strip */}
            <div className="mt-4 flex items-center justify-between rounded-xl px-3 py-2" style={{ background: "#FAFAF5", border: "1px solid #E8DCCA" }}>
              <span className="font-mono text-[10px] font-bold" style={{ color: C.green }}>✓ <AnimatedCounter value={totals.compliant} /></span>
              <span className="font-mono text-[10px] font-bold" style={{ color: C.saffron }}>⚠ <AnimatedCounter value={totals.review} /></span>
              <span className="font-mono text-[10px] font-bold" style={{ color: C.red }}>✗ <AnimatedCounter value={totals.violations} /></span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
