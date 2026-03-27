"use client";

import { useMemo } from "react";
import { AlertTriangle, Lock, TrendingUp } from "lucide-react";
import { PieChart, Pie, ResponsiveContainer, Cell, Tooltip } from "recharts";
import { LayerCard } from "@/components/workflow/LayerCard";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { AnimatedCounter } from "@/components/ui/AnimatedCounter";
import { ViolationStream } from "@/components/workflow/ViolationStream";
import { OutputPanel } from "@/components/workflow/OutputPanel";
import { usePipelineStore } from "@/store/pipelineStore";

export function Phase2Panel() {
  const phase1Status = usePipelineStore((s) => s.phase1Status);
  const phase2Status = usePipelineStore((s) => s.phase2Status);
  const phase2Progress = usePipelineStore((s) => s.phase2Progress);
  const results = usePipelineStore((s) => s.results);

  const unlocked = phase1Status === "complete";
  const overall = (phase2Progress.complianceValidation + phase2Progress.explainability) / 2;

  const donutData = useMemo(() => {
    const compliant = Math.max(0, 180000 - results.violations.length);
    const violation = results.violations.filter((v) => v.status === "VIOLATION").length;
    const review = results.violations.filter((v) => v.status === "NEEDS_REVIEW").length;

    return [
      { name: "Compliant", value: compliant, color: "#00FF88" },
      { name: "Violation", value: violation, color: "#FF3B5C" },
      { name: "Needs Review", value: review, color: "#FFB800" },
    ];
  }, [results.violations]);

  return (
    <div className="relative space-y-4 p-4 md:p-6">
      <div
        className={
          unlocked
            ? "space-y-4"
            : "pointer-events-none space-y-4 opacity-30 blur-[8px]"
        }
      >
        <div className="ui-panel rounded-2xl p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-xl font-semibold text-[var(--text-primary)]">Phase 2 - Compliance Engine</h2>
            <StatusBadge status={phase2Status === "idle" ? "pending" : phase2Status} />
          </div>
          <ProgressBar value={overall} />
        </div>

        <LayerCard
          title="Compliance Validation"
          status={phase2Progress.complianceValidation >= 100 ? "complete" : phase2Progress.complianceValidation > 0 ? "running" : "pending"}
          progress={phase2Progress.complianceValidation}
        >
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-2 text-xs">
              {["Threshold Engine", "Temporal Engine", "Graph Engine"].map((engine) => (
                <div key={engine} className="ui-panel-muted rounded-lg px-3 py-2 text-[var(--text-secondary)]">
                  {engine} <span className="text-[var(--accent-green)]">●</span>
                </div>
              ))}
            </div>

            <div className="ui-panel-muted rounded-xl p-3 text-sm text-[var(--text-secondary)]">
              Processing: <AnimatedCounter value={Math.round((phase2Progress.complianceValidation / 100) * 180000)} /> / 180000
            </div>

            <div className="ui-panel-muted inline-flex items-center gap-2 rounded-xl p-3 text-sm text-[var(--text-secondary)]">
              <TrendingUp className="size-4 text-[var(--accent-teal)]" />
              Throughput: <AnimatedCounter value={8247} suffix=" txns/sec" />
            </div>

            <div className="ui-panel-muted h-44 rounded-xl p-3">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={donutData} dataKey="value" innerRadius={44} outerRadius={68}>
                    {donutData.map((entry) => (
                      <Cell key={entry.name} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>

            <ViolationStream violations={results.violations} />
          </div>
        </LayerCard>

        <LayerCard
          title="Explainability and Report"
          status={phase2Progress.explainability >= 100 ? "complete" : phase2Progress.explainability > 0 ? "running" : "pending"}
          progress={phase2Progress.explainability}
        >
          <div className="space-y-3 text-sm text-[var(--text-secondary)]">
            <div>Generating explanations for <AnimatedCounter value={results.violations.length} /> violations</div>
            <div>Compiling PDF audit report with WeasyPrint</div>
            <div className="ui-panel-muted rounded-xl p-3 text-xs">
              Latest explanation preview
              <div className="mt-2 text-[var(--text-primary)]">
                {results.explanations.at(-1)?.explanation ?? "Awaiting explainability output..."}
              </div>
            </div>
            {phase2Progress.explainability >= 100 && (
              <OutputPanel
                totalTransactions={180000}
                rulesCount={results.rules.length}
                violations={results.violations}
              />
            )}
          </div>
        </LayerCard>
      </div>

      {!unlocked && (
        <div className="absolute inset-0 z-10 grid place-items-center rounded-2xl border border-white/10 bg-[rgba(2,11,24,0.45)]">
          <div className="text-center">
            <Lock className="mx-auto mb-2 size-8 animate-pulse text-[var(--accent-teal)]" />
            <div className="text-sm text-[var(--text-primary)]">Awaiting Phase 1 Completion</div>
          </div>
        </div>
      )}

      {phase2Status === "error" && (
        <div className="rounded-xl border border-[rgba(255,59,92,0.5)] bg-[rgba(255,59,92,0.08)] p-3 text-sm text-[var(--accent-red)] inline-flex items-center gap-2">
          <AlertTriangle className="size-4" />
          Phase 2 encountered an error. Retry from New Analysis.
        </div>
      )}
    </div>
  );
}
