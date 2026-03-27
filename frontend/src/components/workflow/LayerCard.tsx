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
        "rounded-md border border-(--border-default) border-l-4 bg-white p-4",
        status === "complete"
          ? "border-l-(--accent-green) bg-[rgba(19,136,8,0.05)]"
          : status === "running"
            ? "border-l-(--accent-saffron) bg-[rgba(255,102,0,0.04)]"
            : status === "error"
              ? "border-l-(--violation) bg-[rgba(204,0,0,0.04)]"
              : "border-l-(--border-default)",
      )}
      animate={{ opacity: 1 }}
    >
      <button className="mb-3 flex w-full items-center justify-between gap-3" onClick={() => setOpen((v) => !v)}>
        <div>
          <h4 className="text-left text-lg font-semibold text-(--accent-navy)">{title}</h4>
          <div className="mt-2"><ProgressBar value={progress} /></div>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={status} />
          <ChevronDown className={cn("size-4 text-(--text-secondary) transition", open && "rotate-180")} />
        </div>
      </button>
      {open && <div>{children}</div>}
    </motion.section>
  );
}
