"use client";

import { motion } from "framer-motion";
import { CheckCircle2, Cpu, Database, FileText } from "lucide-react";
import { LayerCard } from "@/components/workflow/LayerCard";
import { AnimatedCounter } from "@/components/ui/AnimatedCounter";
import { LogStream } from "@/components/ui/LogStream";
import { DocumentScanner } from "@/components/workflow/DocumentScanner";
import { RuleExtractionFeed } from "@/components/workflow/RuleExtractionFeed";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { usePipelineStore } from "@/store/pipelineStore";

export function Phase1Panel() {
  const phase1Status = usePipelineStore((s) => s.phase1Status);
  const phase1Progress = usePipelineStore((s) => s.phase1Progress);
  const pipelineStats = usePipelineStore((s) => s.pipelineStats);
  const logs = usePipelineStore((s) => s.logs);
  const rules = usePipelineStore((s) => s.results.rules);

  // Use real counts from SSE when available, fall back to progress-derived estimates
  const totalPages = pipelineStats.pages > 0 ? pipelineStats.pages : 24;
  const totalChunks = pipelineStats.chunks > 0 ? pipelineStats.chunks : 187;
  const txnTotalBaseline = pipelineStats.transactionsInput > 0 ? pipelineStats.transactionsInput : 180000;
  const transactionsLoaded =
    pipelineStats.transactionsStored > 0
      ? pipelineStats.transactionsStored
      : Math.round((phase1Progress.txnProcessing / 100) * txnTotalBaseline);
  const totalRules = rules.length;
  const extractedRules = totalRules > 0
    ? Math.min(totalRules, Math.round((phase1Progress.ruleExtraction / 100) * totalRules))
    : 0;
  const severityCounts = rules.reduce(
    (acc, rule) => {
      if (rule.severity === "LOW") acc.low += 1;
      if (rule.severity === "MEDIUM") acc.med += 1;
      if (rule.severity === "HIGH") acc.high += 1;
      if (rule.severity === "CRITICAL") acc.crit += 1;
      return acc;
    },
    { low: 0, med: 0, high: 0, crit: 0 },
  );
  const maxSeverityCount = Math.max(
    severityCounts.low,
    severityCounts.med,
    severityCounts.high,
    severityCounts.crit,
    1,
  );

  const overall = (phase1Progress.policyParsing + phase1Progress.ruleExtraction + phase1Progress.txnProcessing) / 3;

  return (
    <div className="space-y-4 p-4 md:p-6">
      <div className="rounded-md border border-(--border-default) bg-white p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="border-l-4 border-l-(--accent-saffron) bg-(--bg-dark) px-3 py-2 text-xl font-semibold text-white!">Phase 1 - Data Ingestion</h2>
          <StatusBadge
            status={phase1Status === "idle" ? "pending" : phase1Status}
          />
        </div>
        <ProgressBar value={overall} />
      </div>

      <LayerCard
        title="Policy PDF Parsing"
        status={phase1Progress.policyParsing >= 100 ? "complete" : phase1Progress.policyParsing > 0 ? "running" : "pending"}
        progress={phase1Progress.policyParsing}
      >
        <div className="space-y-3">
          <div className="inline-flex items-center gap-2 text-sm text-(--text-secondary)">
            <FileText className="size-4 text-(--accent-saffron)" />
            Live parsing telemetry
          </div>
          <DocumentScanner
            currentPage={Math.max(1, Math.ceil((phase1Progress.policyParsing / 100) * totalPages))}
            totalPages={totalPages}
          />
          <div className="grid grid-cols-3 gap-3 text-sm">
            <div className="ui-panel-muted rounded-xl p-3">
              <div className="text-xs text-(--text-secondary)">Pages Processed</div>
              <AnimatedCounter value={Math.round((phase1Progress.policyParsing / 100) * totalPages)} />
            </div>
            <div className="ui-panel-muted rounded-xl p-3">
              <div className="text-xs text-(--text-secondary)">Chunks Created</div>
              <AnimatedCounter value={Math.round((phase1Progress.policyParsing / 100) * totalChunks)} />
            </div>
            <div className="ui-panel-muted rounded-xl p-3">
              <div className="text-xs text-(--text-secondary)">Indexing</div>
              <AnimatedCounter value={phase1Progress.policyParsing} suffix="%" />
            </div>
          </div>
          <LogStream entries={logs.length ? logs : ["Extracting text from page 1...", "Section detected: Monitoring", "Chunk created"]} />
        </div>
      </LayerCard>

      <LayerCard
        title="Rule Extraction"
        status={phase1Progress.ruleExtraction >= 100 ? "complete" : phase1Progress.ruleExtraction > 0 ? "running" : "pending"}
        progress={phase1Progress.ruleExtraction}
      >
        <div className="space-y-3">
          <div className="inline-flex items-center gap-2 text-sm text-(--text-secondary)">
            <Cpu className="size-4 text-(--accent-saffron)" />
            Meta-Llama 3 analyzing clauses
          </div>
          <div className="ui-panel-muted rounded-xl p-3 text-sm text-(--text-secondary)">
            Clause <AnimatedCounter value={extractedRules} /> / <AnimatedCounter value={totalRules} />
          </div>
          <div className="ui-panel-muted rounded-xl p-3">
            <div className="mb-2 text-xs text-(--text-secondary)">Latest extracted rule</div>
            <RuleExtractionFeed rules={rules} />
          </div>
          <div className="grid grid-cols-4 gap-2 text-xs">
            {[
              ["LOW", severityCounts.low],
              ["MED", severityCounts.med],
              ["HIGH", severityCounts.high],
              ["CRIT", severityCounts.crit],
            ].map(([label, count]) => (
              <div key={label} className="ui-panel-muted rounded-lg p-2">
                <div className="mb-1 flex items-center justify-between text-(--text-secondary)">
                  <span>{label}</span>
                  <AnimatedCounter value={Number(count)} />
                </div>
                <div className="h-1.5 rounded bg-white/10">
                  <motion.div
                    className="h-full rounded bg-(--accent-saffron)"
                    animate={{ scaleX: phase1Progress.ruleExtraction > 0 ? 1 : 0 }}
                    style={{ transformOrigin: "0 50%", width: `${(Number(count) / maxSeverityCount) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
          <div className="text-xs text-(--accent-amber)">
            <AnimatedCounter value={severityCounts.high + severityCounts.crit} /> rules flagged for review
          </div>
        </div>
      </LayerCard>

      <LayerCard
        title="Transaction Processing"
        status={phase1Progress.txnProcessing >= 100 ? "complete" : phase1Progress.txnProcessing > 0 ? "running" : "pending"}
        progress={phase1Progress.txnProcessing}
      >
        <div className="space-y-3 text-sm text-(--text-secondary)">
          <div className="inline-flex items-center gap-2">
            <Database className="size-4 text-(--accent-saffron)" />
            Loading IBM AML Dataset
          </div>
          <div className="ui-panel-muted rounded-xl p-3">
            Transactions loaded: <AnimatedCounter value={transactionsLoaded} />
          </div>
          <div className="ui-panel-muted space-y-1 rounded-xl p-3 text-xs">
            <div className={phase1Progress.txnProcessing >= 20 ? "text-(--accent-green)" : "text-(--text-secondary)"}>
              {phase1Progress.txnProcessing >= 20 ? "✅ " : "○ "}Stage 1: Multi-format File Parsing
            </div>
            <div className={phase1Progress.txnProcessing >= 50 ? "text-(--accent-green)" : "text-(--text-secondary)"}>
              {phase1Progress.txnProcessing >= 50 ? "✅ " : "○ "}Stage 2: RBI Compliance Pre-filtering
            </div>
            <div className={phase1Progress.txnProcessing >= 80 ? "text-(--accent-green)" : "text-(--text-secondary)"}>
              {phase1Progress.txnProcessing >= 80 ? "✅ " : "○ "}Stage 3: SQLite & Pickle Persistence
            </div>
            <div className={phase1Progress.txnProcessing >= 100 ? "text-(--accent-green)" : "text-(--text-secondary)"}>
              {phase1Progress.txnProcessing >= 100 ? "✅ " : "○ "}Pipeline validation complete
            </div>
          </div>
          {phase1Progress.txnProcessing > 0 && phase1Progress.txnProcessing < 100 && (
            <LogStream entries={logs.filter(l => l.includes("Stage") || l.includes("transaction")).slice(-3)} />
          )}
        </div>
      </LayerCard>

      {phase1Progress.policyParsing >= 100 && phase1Progress.ruleExtraction >= 100 && phase1Progress.txnProcessing >= 100 && (
        <motion.div
          initial={{ x: -16, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          className="inline-flex w-full items-center gap-2 rounded-md border border-(--accent-green) bg-[rgba(19,136,8,0.08)] px-4 py-3 text-sm text-(--accent-green)"
        >
          <CheckCircle2 className="size-4" />
          Phase 1 Complete - Handoff to Compliance Engine
        </motion.div>
      )}
    </div>
  );
}
