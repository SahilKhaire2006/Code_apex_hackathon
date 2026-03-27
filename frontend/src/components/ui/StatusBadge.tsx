"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

type Status = "running" | "complete" | "pending" | "error" | "idle";

interface StatusBadgeProps {
  status: Status;
  className?: string;
}

const map = {
  running: { text: "RUNNING", bg: "bg-(--accent-saffron)" },
  complete: { text: "COMPLETED", bg: "bg-(--accent-green)" },
  pending: { text: "PENDING", bg: "bg-[#718096]" },
  error: { text: "ERROR", bg: "bg-(--violation)" },
  idle: { text: "IDLE", bg: "bg-[#718096]" },
};

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = map[status];

  return (
    <motion.span
      className={cn(
        "inline-flex items-center rounded-md px-2.5 py-1 font-mono text-[11px] tracking-[0.12em] text-white",
        config.bg,
        className,
      )}
      style={{ fontFamily: "Courier New, monospace" }}
      animate={status === "running" ? { opacity: [1, 0.86, 1] } : { opacity: 1 }}
      transition={status === "running" ? { duration: 1.1, repeat: Infinity, ease: "easeInOut" } : undefined}
    >
      {config.text}
    </motion.span>
  );
}
