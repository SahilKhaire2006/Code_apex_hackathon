"use client";

import { motion } from "framer-motion";

interface ProgressBarProps {
  value: number;
}

export function ProgressBar({ value }: ProgressBarProps) {
  const safe = Math.max(0, Math.min(100, value));
  const fillColor = safe >= 100 ? "var(--accent-green)" : "var(--accent-saffron)";

  return (
    <div className="w-full">
      <div className="mb-1 flex items-center justify-end font-mono text-[11px] tracking-[0.15em] text-(--text-secondary)">
        {safe.toFixed(0)}%
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-[#E2E8F0]">
        <motion.div
          className="h-full origin-left"
          animate={{ scaleX: safe / 100, backgroundColor: fillColor }}
          initial={{ scaleX: 0 }}
          transition={{ type: "spring", stiffness: 130, damping: 20 }}
          style={{ transformOrigin: "0% 50%" }}
        />
      </div>
    </div>
  );
}
