"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertCircle, CheckCircle, RotateCcw, XCircle } from "lucide-react";
import { motion } from "framer-motion";
import { AnimatedCounter } from "@/components/ui/AnimatedCounter";
import { JSONHighlight } from "@/components/ui/JSONHighlight";
import { formatCurrency } from "@/lib/utils";

type Verdict = "COMPLIANT" | "VIOLATION" | "NEEDS_REVIEW";

const severities = ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;

function makeRule(step: number) {
  return {
    field: ["amount", "origin_country", "velocity", "counterparty"][step % 4],
    operator: [">", "in", "<", "contains"][step % 4],
    threshold: [10000, "high-risk", 3, "shell"][step % 4],
    severity: severities[step % severities.length],
  };
}

function makeTxn(step: number): { id: string; amount: number; verdict: Verdict } {
  const cycle = step % 10;
  const verdict: Verdict = cycle > 7 ? "VIOLATION" : cycle > 5 ? "NEEDS_REVIEW" : "COMPLIANT";
  return {
    id: `TXN-${(780000 + step).toString()}`,
    amount: Math.round(2000 + Math.random() * 25000),
    verdict,
  };
}

export function ComplianceSimulation() {
  const [running, setRunning] = useState(true);
  const [cursor, setCursor] = useState(0);
  const [page, setPage] = useState(1);
  const [chunks, setChunks] = useState(0);
  const [rules, setRules] = useState<ReturnType<typeof makeRule>[]>([]);
  const [txns, setTxns] = useState<ReturnType<typeof makeTxn>[]>([]);

  useEffect(() => {
    if (!running) return;

    const timer = setInterval(() => {
      setCursor((v) => (v + 1) % 16);
      setPage((p) => (p % 18) + 1);
      setChunks((c) => c + 3);
      setRules((prev) => [...prev.slice(-6), makeRule(prev.length + 1)]);
      setTxns((prev) => [...prev.slice(-9), makeTxn(prev.length + 1)]);
    }, 900);

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
    <section className="mx-auto max-w-7xl px-6 py-20">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold text-(--text-primary)">Live Compliance Simulation</h2>
          <p className="mt-2 text-(--text-secondary)">Watch PolicyGuard AI process a sample AML policy in real time.</p>
        </div>
        <button
          className="inline-flex items-center gap-2 rounded-md border border-(--border-default) bg-white px-4 py-2 text-sm text-(--accent-navy)"
          onClick={() => {
            setRules([]);
            setTxns([]);
            setChunks(0);
            setRunning(false);
            requestAnimationFrame(() => setRunning(true));
          }}
        >
          <RotateCcw className="size-4" />
          Replay Simulation
        </button>
      </div>

      <div className="rounded-xl border border-(--border-default) bg-(--bg-tertiary) p-6 lg:p-10">
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="ui-panel rounded-2xl p-4">
            <div className="mb-3 flex items-center justify-between text-xs text-(--text-secondary)">
              <span>Document Feed</span>
              <span>Page {page} of 18</span>
            </div>
            <div className="ui-panel-muted relative h-72 overflow-hidden rounded-xl p-3">
              {Array.from({ length: 16 }).map((_, line) => (
                <div
                  key={line}
                  className="mb-2 h-2 rounded"
                  style={{
                    background: line === cursor ? "rgba(255,102,0,0.45)" : "rgba(74,85,104,0.2)",
                  }}
                />
              ))}
              <motion.div
                className="pointer-events-none absolute left-0 right-0 h-0.5 bg-(--accent-saffron)"
                animate={{ y: [0, 270] }}
                transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
              />
            </div>
            <div className="mt-3 text-sm text-(--text-secondary)">
              Chunks Extracted: <AnimatedCounter value={chunks} />
            </div>
          </div>

          <div className="rounded-2xl border border-(--border-default) bg-(--bg-dark) p-4">
            <div className="mb-3 text-xs text-white/70">Rule Extraction Feed</div>
            <div className="h-72 space-y-2 overflow-y-auto">
              {rules.map((rule, idx) => (
                <motion.div
                  key={`${rule.field}-${idx}`}
                  initial={{ opacity: 0, y: 14 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="rounded-xl border border-white/10 bg-(--bg-dark-mid) p-2"
                >
                  <JSONHighlight data={rule} />
                </motion.div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-(--border-default) bg-(--bg-dark) p-4">
            <div className="mb-3 text-xs text-white/70">Compliance Verdict Stream</div>
            <div className="h-72 space-y-2 overflow-y-auto">
              {txns.map((txn, idx) => (
                <motion.div
                  key={`${txn.id}-${idx}`}
                  initial={{ opacity: 0, y: 14 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`rounded-lg border p-2 text-sm ${
                    txn.verdict === "VIOLATION"
                      ? "border-[rgba(204,0,0,0.4)] bg-[rgba(204,0,0,0.22)] text-white"
                      : txn.verdict === "NEEDS_REVIEW"
                        ? "border-[rgba(255,102,0,0.45)] bg-[rgba(255,102,0,0.2)] text-white"
                        : "border-[rgba(19,136,8,0.45)] bg-[rgba(19,136,8,0.2)] text-white"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs text-white">{txn.id}</span>
                    <span className="font-mono text-xs text-white/80">{formatCurrency(txn.amount)}</span>
                  </div>
                  <div className="mt-1 inline-flex items-center gap-1 text-xs">
                    {txn.verdict === "COMPLIANT" && <CheckCircle className="size-3 text-white" />}
                    {txn.verdict === "VIOLATION" && <XCircle className="size-3 text-white" />}
                    {txn.verdict === "NEEDS_REVIEW" && <AlertCircle className="size-3 text-white" />}
                    {txn.verdict}
                  </div>
                </motion.div>
              ))}
            </div>

            <div className="mt-4 rounded-xl border border-white/10 bg-(--bg-dark-mid) p-3 text-sm text-white">
              <span className="mr-3 text-[#9df5a2]">✓ <AnimatedCounter value={totals.compliant} /></span>
              <span className="mr-3 text-[#ff9b9b]">✗ <AnimatedCounter value={totals.violations} /></span>
              <span className="text-[#ffd38f]">⚠ <AnimatedCounter value={totals.review} /></span>
            </div>
          </div>
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          {[
            "AML/KYC",
            "FATF",
            "GDPR",
            "Basel III",
          ].map((label, idx) => (
            <motion.div
              key={label}
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: idx * 0.08 }}
              className="inline-flex items-center gap-2 rounded-full border border-(--accent-navy) px-3 py-1 text-xs text-(--accent-navy)"
            >
              <CheckCircle className="size-3 text-(--accent-gold)" />
              {label} ✓
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
