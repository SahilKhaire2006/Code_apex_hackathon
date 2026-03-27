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
  const logs = usePipelineStore((s) => s.logs);
  const rules = usePipelineStore((s) => s.results.rules);

  const overall = (phase1Progress.policyParsing + phase1Progress.ruleExtraction + phase1Progress.txnProcessing) / 3;

  return (
    <div className="space-y-4 p-4 md:p-6">
      <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-[var(--text-primary)]">Phase 1 - Data Ingestion</h2>
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
          <div className="inline-flex items-center gap-2 text-sm text-[var(--text-secondary)]">
            <FileText className="size-4 text-[var(--accent-teal)]" />
            Live parsing telemetry
          </div>
          <DocumentScanner
            currentPage={Math.max(1, Math.ceil((phase1Progress.policyParsing / 100) * 24))}
            totalPages={24}
          />
          <div className="grid grid-cols-3 gap-3 text-sm">
            <div className="rounded-xl border border-white/10 bg-black/20 p-3">
              <div className="text-xs text-[var(--text-secondary)]">Pages Processed</div>
              <AnimatedCounter value={Math.round((phase1Progress.policyParsing / 100) * 24)} />
            </div>
            <div className="rounded-xl border border-white/10 bg-black/20 p-3">
              <div className="text-xs text-[var(--text-secondary)]">Chunks Created</div>
              <AnimatedCounter value={Math.round((phase1Progress.policyParsing / 100) * 187)} />
            </div>
            <div className="rounded-xl border border-white/10 bg-black/20 p-3">
              <div className="text-xs text-[var(--text-secondary)]">Indexing</div>
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
          <div className="inline-flex items-center gap-2 text-sm text-[var(--text-secondary)]">
            <Cpu className="size-4 text-[var(--accent-teal)]" />
            Meta-Llama 3 analyzing clauses
          </div>
          <div className="rounded-xl border border-white/10 bg-black/20 p-3 text-sm text-[var(--text-secondary)]">
            Clause {Math.max(1, Math.ceil((phase1Progress.ruleExtraction / 100) * 34))} / 34
          </div>
          <div className="rounded-xl border border-white/10 bg-black/20 p-3">
            <div className="mb-2 text-xs text-[var(--text-secondary)]">Latest extracted rule</div>
            <RuleExtractionFeed rules={rules} />
          </div>
          <div className="grid grid-cols-4 gap-2 text-xs">
            {[
              ["LOW", 8],
              ["MED", 5],
              ["HIGH", 3],
              ["CRIT", 2],
            ].map(([label, weight]) => (
              <div key={label} className="rounded-lg border border-white/10 bg-black/25 p-2">
                <div className="mb-1 text-[var(--text-secondary)]">{label}</div>
                <div className="h-1.5 rounded bg-white/10">
                  <motion.div
                    className="h-full rounded bg-[var(--accent-teal)]"
                    animate={{ scaleX: phase1Progress.ruleExtraction > 0 ? 1 : 0 }}
                    style={{ transformOrigin: "0 50%", width: `${Number(weight) * 10}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
          <div className="text-xs text-[var(--accent-amber)]">3 rules flagged for review</div>
        </div>
      </LayerCard>

      <LayerCard
        title="Transaction Processing"
        status={phase1Progress.txnProcessing >= 100 ? "complete" : phase1Progress.txnProcessing > 0 ? "running" : "pending"}
        progress={phase1Progress.txnProcessing}
      >
        <div className="space-y-3 text-sm text-[var(--text-secondary)]">
          <div className="inline-flex items-center gap-2">
            <Database className="size-4 text-[var(--accent-teal)]" />
            Loading IBM AML Dataset
          </div>
          <div className="rounded-xl border border-white/10 bg-black/25 p-3">
            Transactions loaded: <AnimatedCounter value={Math.round((phase1Progress.txnProcessing / 100) * 180000)} />
          </div>
          <div className="space-y-1 rounded-xl border border-white/10 bg-black/25 p-3 text-xs">
            <div className="text-[var(--accent-green)]">Check transaction_id - valid</div>
            <div className="text-[var(--accent-green)]">Check amount - valid</div>
            <div className="text-[var(--accent-green)]">Check timestamp - valid</div>
            <div>Pandera schema validation passed</div>
            <div>Building transaction graph with NetworkX</div>
          </div>
        </div>
      </LayerCard>

      {phase1Progress.policyParsing >= 100 && phase1Progress.ruleExtraction >= 100 && phase1Progress.txnProcessing >= 100 && (
        <motion.div
          initial={{ x: -20, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          className="inline-flex w-full items-center gap-2 rounded-xl bg-[rgba(0,255,136,0.2)] px-4 py-3 text-sm text-[var(--accent-green)]"
        >
          <CheckCircle2 className="size-4" />
          Phase 1 Complete - Handoff to Compliance Engine
        </motion.div>
      )}
    </div>
  );
}
