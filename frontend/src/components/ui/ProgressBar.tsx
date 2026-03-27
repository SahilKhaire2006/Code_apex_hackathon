"use client";

import { motion } from "framer-motion";

interface ProgressBarProps {
  value: number;
}

export function ProgressBar({ value }: ProgressBarProps) {
  const safe = Math.max(0, Math.min(100, value));

  return (
    <div className="w-full">
      <div className="mb-1 flex items-center justify-end font-mono text-[11px] tracking-[0.15em] text-(--text-secondary)">
        {safe.toFixed(0)}%
      </div>
      <div className="h-1 w-full overflow-hidden rounded-full bg-[rgba(0,212,255,0.1)]">
        <motion.div
          className="h-full origin-left bg-[linear-gradient(90deg,#00D4FF,#00FF88)]"
          animate={{ scaleX: safe / 100 }}
          initial={{ scaleX: 0 }}
          transition={{ type: "spring", stiffness: 130, damping: 20 }}
          style={{ transformOrigin: "0% 50%" }}
        />
      </div>
    </div>
  );
}
