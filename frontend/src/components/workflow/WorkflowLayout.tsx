"use client";

import { motion } from "framer-motion";
import { Phase1Panel } from "@/components/workflow/Phase1Panel";
import { Phase2Panel } from "@/components/workflow/Phase2Panel";
import { usePipelineStore } from "@/store/pipelineStore";

export function WorkflowLayout() {
  const phase1Status = usePipelineStore((s) => s.phase1Status);
  const phase2Ready = phase1Status === "complete";

  return (
    <div className="relative grid min-h-[calc(100vh-88px)] grid-cols-1 bg-(--bg-primary) md:grid-cols-[1fr_auto_1fr]">
      <div className="min-h-[50vh] md:h-[calc(100vh-88px)] md:overflow-y-auto lg:h-[calc(100vh-96px)]">
        <Phase1Panel />
      </div>

      <div className="relative mx-auto hidden w-px bg-(--border-default) md:block" />

      {phase2Ready && (
        <motion.div
          className="pointer-events-none absolute top-4 right-0 hidden h-12 w-0.5 bg-(--accent-saffron) md:block"
          initial={{ opacity: 0, x: 8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.3, ease: "easeOut" }}
        />
      )}

      <div className="min-h-[50vh] md:h-[calc(100vh-88px)] md:overflow-y-auto lg:h-[calc(100vh-96px)]">
        <Phase2Panel />
      </div>
    </div>
  );
}
