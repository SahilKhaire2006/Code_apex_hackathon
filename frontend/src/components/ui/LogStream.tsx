"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useRef } from "react";

interface LogStreamProps {
  entries: string[];
  maxVisible?: number;
}

export function LogStream({ entries, maxVisible = 7 }: LogStreamProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const visibleEntries = useMemo(() => entries.slice(-maxVisible), [entries, maxVisible]);

  useEffect(() => {
    if (!containerRef.current) return;
    containerRef.current.scrollTop = containerRef.current.scrollHeight;
  }, [visibleEntries]);

  return (
    <div
      ref={containerRef}
      className="max-h-44 overflow-y-auto rounded-xl border border-white/10 bg-(--bg-dark) p-3 font-mono text-xs text-white"
    >
      <AnimatePresence initial={false}>
        {visibleEntries.map((entry, index) => (
          <motion.div
            key={`${entry}-${index}`}
            className="mb-2 flex gap-2 last:mb-0"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <span className="text-[10px] text-(--accent-saffron)">LOG</span>
            <span className="text-white/90">{entry}</span>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
