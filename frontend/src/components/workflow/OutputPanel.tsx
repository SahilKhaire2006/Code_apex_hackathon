"use client";

import { useMemo, useState } from "react";
import { ArrowDownUp, Download, Loader2, CheckCircle2, ShieldAlert, ShieldCheck } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import type { ViolationItem } from "@/lib/api";
import { downloadReportBlob } from "@/lib/api";
import { AnimatedCounter } from "@/components/ui/AnimatedCounter";

interface OutputPanelProps {
  totalTransactions: number;
  rulesCount: number;
  violations: ViolationItem[];
}

type Tab = "violations" | "compliant";
type SortKey = "transactionId" | "rule" | "severity" | "status";

const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: "bg-red-600",
  HIGH: "bg-orange-500",
  MEDIUM: "bg-yellow-500",
  LOW: "bg-blue-500",
};

export function OutputPanel({ totalTransactions, rulesCount, violations }: OutputPanelProps) {
  const [tab, setTab] = useState<Tab>("violations");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [sortKey, setSortKey] = useState<SortKey>("severity");
  const [asc, setAsc] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloaded, setDownloaded] = useState(false);

  // Separate violations (non-compliant) from compliant transactions
  const violationRows = useMemo(
    () => violations.filter((v) => v.status !== "COMPLIANT"),
    [violations]
  );
  const compliantRows = useMemo(
    () => violations.filter((v) => v.status === "COMPLIANT"),
    [violations]
  );

  const activeRows = tab === "violations" ? violationRows : compliantRows;

  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    return activeRows.filter(
      (v) =>
        v.transactionId.toLowerCase().includes(q) ||
        v.rule.toLowerCase().includes(q)
    );
  }, [query, activeRows]);

  const sorted = useMemo(() => {
    const SEVERITY_RANK: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
    return [...filtered].sort((a, b) => {
      const dir = asc ? 1 : -1;
      if (sortKey === "severity") {
        return ((SEVERITY_RANK[a.severity] ?? 4) - (SEVERITY_RANK[b.severity] ?? 4)) * dir;
      }
      const av = a[sortKey as keyof ViolationItem];
      const bv = b[sortKey as keyof ViolationItem];
      return String(av).localeCompare(String(bv)) * dir;
    });
  }, [filtered, sortKey, asc]);

  const pageSize = 15;
  const pages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const visible = sorted.slice((page - 1) * pageSize, page * pageSize);

  const complianceRate =
    totalTransactions > 0
      ? Math.round(((totalTransactions - violationRows.length) / totalTransactions) * 100)
      : 100;

  const stats = [
    { label: "Total Checked", value: totalTransactions, icon: null },
    { label: "Violations", value: violationRows.length, icon: null },
    { label: "Compliant", value: compliantRows.length, icon: null },
    { label: "Rules Applied", value: rulesCount, icon: null },
    { label: "Compliance %", value: complianceRate, suffix: "%", icon: null },
  ];

  return (
    <div className="space-y-4 rounded-md border border-(--border-default) bg-white p-4">

      {/* ── Summary Stats ─────────────────────────────────────────────────── */}
      <div className="grid gap-3 md:grid-cols-5">
        {stats.map(({ label, value, suffix }) => (
          <div key={label} className="rounded-md border border-(--border-default) bg-(--bg-secondary) p-3">
            <div className="text-[11px] tracking-[0.15em] text-(--text-secondary)">{label}</div>
            <div className="mt-2 text-2xl font-semibold">
              <AnimatedCounter value={value} />
              {suffix && <span className="ml-0.5 text-sm">{suffix}</span>}
            </div>
          </div>
        ))}
      </div>

      {/* ── Compliance Rate Bar ────────────────────────────────────────────── */}
      <div className="rounded-md border border-(--border-default) bg-(--bg-secondary) p-3">
        <div className="mb-1 flex items-center justify-between text-xs">
          <span className="text-(--text-secondary) font-medium">Overall Compliance Rate</span>
          <span
            className={`font-bold ${
              complianceRate >= 80 ? "text-emerald-600" : complianceRate >= 50 ? "text-amber-500" : "text-red-500"
            }`}
          >
            {complianceRate}%
          </span>
        </div>
        <div className="h-2 rounded-full bg-white/20 overflow-hidden border border-(--border-default)">
          <motion.div
            className={`h-full rounded-full ${
              complianceRate >= 80 ? "bg-emerald-500" : complianceRate >= 50 ? "bg-amber-500" : "bg-red-500"
            }`}
            initial={{ width: 0 }}
            animate={{ width: `${complianceRate}%` }}
            transition={{ duration: 1, ease: "easeOut" }}
          />
        </div>
      </div>

      {/* ── Tabs ──────────────────────────────────────────────────────────── */}
      <div className="flex gap-2 border-b border-(--border-default)">
        <button
          onClick={() => { setTab("violations"); setPage(1); }}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-semibold border-b-2 -mb-px transition-colors ${
            tab === "violations"
              ? "border-red-500 text-red-600"
              : "border-transparent text-(--text-secondary) hover:text-(--text-primary)"
          }`}
        >
          <ShieldAlert className="size-4" />
          Violations ({violationRows.length})
        </button>
        <button
          onClick={() => { setTab("compliant"); setPage(1); }}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-semibold border-b-2 -mb-px transition-colors ${
            tab === "compliant"
              ? "border-emerald-500 text-emerald-600"
              : "border-transparent text-(--text-secondary) hover:text-(--text-primary)"
          }`}
        >
          <ShieldCheck className="size-4" />
          Compliant ({compliantRows.length})
        </button>
      </div>

      {/* ── Table ─────────────────────────────────────────────────────────── */}
      <div className="rounded-md border border-(--border-default) bg-white">
        <div className="mb-3 flex flex-col gap-3 p-3 md:flex-row md:items-center md:justify-between">
          <input
            value={query}
            onChange={(e) => { setPage(1); setQuery(e.target.value); }}
            className="h-10 rounded-md border border-(--border-default) bg-white px-3 text-sm text-(--text-primary) outline-none focus:border-(--accent-navy) w-full md:w-64"
            placeholder="Filter by transaction ID or rule…"
          />
          <button
            className="inline-flex items-center gap-2 rounded-md border border-(--border-default) px-3 py-2 text-xs text-(--text-secondary)"
            onClick={() => setAsc((v) => !v)}
          >
            <ArrowDownUp className="size-3" />
            Toggle Sort Direction
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[780px] text-left text-xs">
            <thead className="bg-(--bg-dark) text-white">
              <tr>
                {(["transactionId", "rule", "severity", "status"] as SortKey[]).map((key) => (
                  <th
                    key={key}
                    className="cursor-pointer px-3 py-2 capitalize hover:bg-white/5"
                    onClick={() => setSortKey(key)}
                  >
                    {key === "transactionId" ? "Transaction ID" : key}
                  </th>
                ))}
                <th className="px-3 py-2">Detail</th>
              </tr>
            </thead>
            <tbody>
              <AnimatePresence mode="sync">
                {visible.map((row) => (
                  <motion.tr
                    key={`${row.id}-${row.transactionId}`}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    className={`border-t border-(--border-default) ${
                      row.status === "COMPLIANT"
                        ? "hover:bg-emerald-50"
                        : "hover:bg-red-50"
                    }`}
                  >
                    <td className="px-3 py-2 font-mono text-[11px]">{row.transactionId}</td>
                    <td className="px-3 py-2 max-w-[220px] truncate" title={row.rule}>{row.rule}</td>
                    <td className="px-3 py-2">
                      {row.status !== "COMPLIANT" ? (
                        <span
                          className={`inline-flex rounded-sm px-2 py-0.5 text-[10px] font-semibold text-white ${SEVERITY_COLOR[row.severity] ?? "bg-gray-500"}`}
                        >
                          {row.severity}
                        </span>
                      ) : (
                        <span className="inline-flex rounded-sm px-2 py-0.5 text-[10px] font-semibold bg-emerald-100 text-emerald-700">
                          LOW
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <span
                        className={`inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-[10px] font-semibold ${
                          row.status === "COMPLIANT"
                            ? "bg-emerald-100 text-emerald-700"
                            : row.status === "VIOLATION"
                            ? "bg-red-100 text-red-700"
                            : "bg-amber-100 text-amber-700"
                        }`}
                      >
                        {row.status === "COMPLIANT" ? <CheckCircle2 className="size-3" /> : <ShieldAlert className="size-3" />}
                        {row.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-[10px] text-(--text-secondary) max-w-[280px]">
                      {/* Show detail from the raw violation if available */}
                      {(row as unknown as Record<string, unknown>)["detail"] as string ?? "—"}
                    </td>
                  </motion.tr>
                ))}
              </AnimatePresence>
              {visible.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-(--text-secondary) text-sm">
                    {tab === "violations" ? "✅ No violations found" : "No compliant transactions recorded yet"}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between p-3">
          <button
            disabled={page <= 1}
            className="rounded px-2 py-1 text-xs disabled:opacity-30"
            onClick={() => setPage((p) => p - 1)}
          >
            Prev
          </button>
          <span className="text-xs text-(--text-secondary)">Page {page} / {pages}</span>
          <button
            disabled={page >= pages}
            className="rounded px-2 py-1 text-xs disabled:opacity-30"
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </button>
        </div>
      </div>

      {/* ── Export Button ──────────────────────────────────────────────────── */}
      <div className="flex justify-end">
        <button
          onClick={async () => {
            setDownloading(true);
            try {
              const blob = await downloadReportBlob();
              const url = URL.createObjectURL(blob);
              const anchor = document.createElement("a");
              anchor.href = url;
              anchor.download = "policyguard-compliance-report.pdf";
              anchor.click();
              URL.revokeObjectURL(url);
              setDownloaded(true);
              setTimeout(() => setDownloaded(false), 1200);
            } finally {
              setDownloading(false);
            }
          }}
          className="inline-flex h-12 w-[220px] items-center justify-center gap-2 rounded-md border-r-4 border-r-(--accent-saffron) bg-(--bg-dark) px-4 text-sm font-semibold text-white hover:bg-(--bg-dark-mid) hover:shadow-[0_4px_16px_rgba(11,37,69,0.3)]"
        >
          {downloading ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" />}
          {downloading ? "Generating PDF..." : downloaded ? "Downloaded ✓" : "Export Compliance Report"}
        </button>
      </div>
    </div>
  );
}
