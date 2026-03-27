"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

type Status = "running" | "complete" | "pending" | "error" | "idle";

interface StatusBadgeProps {
  status: Status;
  className?: string;
}

const map = {
  running: { text: "RUNNING", dot: "bg-[var(--accent-amber)]", textColor: "text-[var(--accent-amber)]" },
  complete: { text: "COMPLETED", dot: "bg-[var(--accent-green)]", textColor: "text-[var(--accent-green)]" },
  pending: { text: "PENDING", dot: "bg-[var(--accent-teal-dim)]", textColor: "text-[var(--text-secondary)]" },
  error: { text: "ERROR", dot: "bg-[var(--accent-red)]", textColor: "text-[var(--accent-red)]" },
  idle: { text: "IDLE", dot: "bg-[var(--accent-teal-dim)]", textColor: "text-[var(--text-secondary)]" },
};

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = map[status];

  return (
    <span
      className={cn(
        "ui-panel-muted inline-flex items-center gap-2 rounded-full px-2.5 py-1 font-mono text-[11px] tracking-[0.15em]",
        config.textColor,
        className,
      )}
    >
      <motion.span
        className={cn("size-1.5 rounded-full", config.dot)}
        animate={status === "running" ? { opacity: [1, 0.25, 1] } : { opacity: 1 }}
        transition={status === "running" ? { duration: 1.1, repeat: Infinity, ease: "easeInOut" } : undefined}
      />
      {config.text}
    </span>
  );
}
