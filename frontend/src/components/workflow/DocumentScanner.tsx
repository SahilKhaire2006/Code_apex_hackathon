"use client";

import { motion } from "framer-motion";

interface DocumentScannerProps {
  currentPage: number;
  totalPages: number;
}

export function DocumentScanner({ currentPage, totalPages }: DocumentScannerProps) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/30 p-3">
      <div className="mb-2 text-xs text-(--text-secondary)">Processing page {currentPage} of {totalPages}</div>
      <div className="relative h-28 overflow-hidden rounded-lg border border-white/10 bg-[#061226] p-2">
        {Array.from({ length: 10 }).map((_, idx) => (
          <div key={idx} className="mb-2 h-1.5 rounded bg-white/15" />
        ))}
        <motion.div
          className="absolute left-0 right-0 h-0.5 bg-(--accent-teal)"
          animate={{ y: [0, 100] }}
          transition={{ duration: 2.5, repeat: Infinity, ease: "linear" }}
        />
      </div>
    </div>
  );
}
