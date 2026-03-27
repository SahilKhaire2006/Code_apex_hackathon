"use client";

import { motion } from "framer-motion";

interface DocumentScannerProps {
  currentPage: number;
  totalPages: number;
}

export function DocumentScanner({ currentPage, totalPages }: DocumentScannerProps) {
  return (
    <div className="ui-panel-muted rounded-xl p-3">
      <div className="mb-2 text-xs text-(--text-secondary)">Processing page {currentPage} of {totalPages}</div>
      <div className="ui-panel relative h-28 overflow-hidden rounded-lg p-2">
        {Array.from({ length: 10 }).map((_, idx) => (
          <div key={idx} className="mb-2 h-1.5 rounded bg-[rgba(74,85,104,0.2)]" />
        ))}
        <motion.div
          className="absolute left-0 right-0 h-0.5 bg-(--accent-saffron)"
          animate={{ y: [0, 100] }}
          transition={{ duration: 2.5, repeat: Infinity, ease: "linear" }}
        />
      </div>
    </div>
  );
}
