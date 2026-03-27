"use client";

import { useMemo, useState } from "react";
import { ArrowDownUp, Download, Loader2 } from "lucide-react";
import { motion } from "framer-motion";
import type { ViolationItem } from "@/lib/api";
import { downloadReportBlob } from "@/lib/api";
import { AnimatedCounter } from "@/components/ui/AnimatedCounter";
import { formatCurrency } from "@/lib/utils";

interface OutputPanelProps {
  totalTransactions: number;
  rulesCount: number;
  violations: ViolationItem[];
}

type SortKey = "transactionId" | "amount" | "rule" | "severity";

export function OutputPanel({ totalTransactions, rulesCount, violations }: OutputPanelProps) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [sortKey, setSortKey] = useState<SortKey>("amount");
  const [asc, setAsc] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloaded, setDownloaded] = useState(false);

  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    return violations.filter((v) => v.transactionId.toLowerCase().includes(q) || v.rule.toLowerCase().includes(q));
  }, [query, violations]);

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      const dir = asc ? 1 : -1;
      const av = a[sortKey];
      const bv = b[sortKey];
      if (typeof av === "number" && typeof bv === "number") {
        return (av - bv) * dir;
      }
      return String(av).localeCompare(String(bv)) * dir;
    });
  }, [filtered, sortKey, asc]);

  const pageSize = 10;
  const pages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const visible = sorted.slice((page - 1) * pageSize, page * pageSize);

  const complianceRate = totalTransactions > 0 ? ((totalTransactions - violations.length) / totalTransactions) * 100 : 0;

  return (
    <div className="space-y-4 rounded-md border border-(--border-default) bg-white p-4">
      <div className="grid gap-3 md:grid-cols-4">
        {[
          ["Total Transactions", totalTransactions],
          ["Violations Found", violations.length],
          ["Rules Extracted", rulesCount],
          ["Compliance %", Number(complianceRate.toFixed(2))],
        ].map(([label, value]) => (
          <div key={label as string} className="rounded-md border border-(--border-default) bg-(--bg-secondary) p-3">
            <div className="text-[11px] tracking-[0.15em] text-(--text-secondary)">{label as string}</div>
            <div className="mt-2 text-2xl font-semibold"><AnimatedCounter value={value as number} /></div>
          </div>
        ))}
      </div>

      <div className="rounded-md border border-(--border-default) bg-white p-3">
        <div className="mb-3 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <input
            value={query}
            onChange={(e) => {
              setPage(1);
              setQuery(e.target.value);
            }}
            className="h-10 rounded-md border border-(--border-default) bg-white px-3 text-sm text-(--text-primary) outline-none focus:border-(--accent-navy)"
            placeholder="Filter by transaction ID or rule"
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
          <table className="w-full min-w-[760px] text-left text-xs">
            <thead className="bg-(--bg-dark) text-white">
              <tr>
                {(["transactionId", "amount", "rule", "severity"] as SortKey[]).map((key) => (
                  <th key={key} className="cursor-pointer px-2 py-2" onClick={() => setSortKey(key)}>
                    {key}
                  </th>
                ))}
                <th className="px-2 py-2">page</th>
                <th className="px-2 py-2">status</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <motion.tr
                  key={row.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="border-t border-(--border-default) hover:bg-[rgba(255,102,0,0.06)]"
                >
                  <td className="px-2 py-2 font-mono">{row.transactionId}</td>
                  <td className="px-2 py-2">{formatCurrency(row.amount)}</td>
                  <td className="px-2 py-2">{row.rule}</td>
                  <td className="px-2 py-2">
                    <span
                      className={`inline-flex rounded-sm px-2 py-0.5 text-[10px] font-semibold text-white ${
                        row.severity === "CRITICAL"
                          ? "bg-(--violation)"
                          : row.severity === "HIGH"
                            ? "bg-(--warning)"
                            : row.severity === "MEDIUM"
                              ? "bg-(--accent-navy)"
                              : "bg-(--compliant)"
                      }`}
                    >
                      {row.severity}
                    </span>
                  </td>
                  <td className="px-2 py-2">{row.page ?? "-"}</td>
                  <td className="px-2 py-2">
                    <span
                      className={`inline-flex rounded-sm px-2 py-0.5 text-[10px] font-semibold text-white ${
                        row.status === "COMPLIANT"
                          ? "bg-(--compliant)"
                          : row.status === "VIOLATION"
                            ? "bg-(--violation)"
                            : "bg-(--warning)"
                      }`}
                    >
                      {row.status}
                    </span>
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-3 flex items-center justify-between">
          <button disabled={page <= 1} className="rounded px-2 py-1 text-xs disabled:opacity-30" onClick={() => setPage((p) => p - 1)}>
            Prev
          </button>
          <span className="text-xs text-[var(--text-secondary)]">Page {page} / {pages}</span>
          <button disabled={page >= pages} className="rounded px-2 py-1 text-xs disabled:opacity-30" onClick={() => setPage((p) => p + 1)}>
            Next
          </button>
        </div>
      </div>

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
          {downloading ? "Generating PDF..." : downloaded ? "Downloaded" : "Export Compliance Report"}
        </button>
      </div>
    </div>
  );
}
