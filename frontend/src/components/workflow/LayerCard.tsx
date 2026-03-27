"use client";

import { ChevronDown } from "lucide-react";
import { motion } from "framer-motion";
import { ReactNode, useState } from "react";
import { cn } from "@/lib/utils";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ProgressBar } from "@/components/ui/ProgressBar";

interface LayerCardProps {
  title: string;
  status: "running" | "complete" | "pending" | "error" | "idle";
  progress: number;
  children: ReactNode;
}

export function LayerCard({ title, status, progress, children }: LayerCardProps) {
  const [open, setOpen] = useState(true);

  return (
    <motion.section
      className={cn(
        "glass-card rounded-2xl border-l-4 p-4",
        status === "complete"
          ? "border-l-[var(--accent-green)]"
          : status === "running"
            ? "border-l-[var(--accent-teal)]"
            : status === "error"
              ? "border-l-[var(--accent-red)]"
              : "border-l-[var(--surface-border)]",
      )}
      animate={{ borderColor: status === "running" ? "rgba(0,212,255,0.8)" : undefined }}
    >
      <button className="mb-3 flex w-full items-center justify-between gap-3" onClick={() => setOpen((v) => !v)}>
        <div>
          <h4 className="text-left text-lg font-semibold text-[var(--text-primary)]">{title}</h4>
          <div className="mt-2"><ProgressBar value={progress} /></div>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={status} />
          <ChevronDown className={cn("size-4 text-[var(--text-secondary)] transition", open && "rotate-180")} />
        </div>
      </button>
      {open && <div>{children}</div>}
    </motion.section>
  );
}
