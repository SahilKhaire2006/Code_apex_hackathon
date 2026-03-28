"use client";

import { CheckCircle2, UploadCloud } from "lucide-react";
import { motion, useMotionTemplate, useMotionValue } from "framer-motion";
import { useRef, useState } from "react";
import { clamp, cn } from "@/lib/utils";

interface UploadButtonProps {
  title: string;
  subtitle: string;
  accent: "saffron" | "green";
  accept: string;
  fileName: string | null;
  icon: React.ReactNode;
  onSelect: (file: File | null) => void;
  mirror?: boolean;
}

export function UploadButton({
  title,
  subtitle,
  accent,
  accept,
  fileName,
  icon,
  onSelect,
  mirror,
}: UploadButtonProps) {
  const ref = useRef<HTMLLabelElement | null>(null);
  const [dragging, setDragging] = useState(false);
  const rotateX = useMotionValue(0);
  const rotateY = useMotionValue(0);
  const glow = useMotionTemplate`${accent === "saffron" ? "rgba(255,102,0,0.16)" : "rgba(19,136,8,0.14)"}`;

  const onMove: React.MouseEventHandler<HTMLLabelElement> = (event) => {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;

    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;

    const nextRotateY = clamp(((x / rect.width) * 2 - 1) * 4 * (mirror ? -1 : 1), -4, 4);
    const nextRotateX = clamp(((y / rect.height) * 2 - 1) * -4, -4, 4);

    rotateX.set(nextRotateX);
    rotateY.set(nextRotateY);
  };

  return (
    <motion.label
      ref={ref}
      onMouseMove={onMove}
      onMouseLeave={() => {
        rotateX.set(0);
        rotateY.set(0);
      }}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        onSelect(e.dataTransfer.files?.[0] ?? null);
      }}
      whileHover={{ scale: 1.02, rotateX: -3, rotateY: mirror ? -3 : 3 }}
      whileTap={{ scale: 0.97 }}
      transition={{ type: "spring", stiffness: 240, damping: 20 }}
      className={cn(
        "group relative flex h-[170px] w-full cursor-pointer select-none flex-col justify-between rounded-lg border-2 border-dashed bg-white/40 backdrop-blur-md p-4 transition-colors hover:bg-white/60 sm:h-[180px] md:h-[190px] md:max-w-[260px]",
        fileName ? "border-(--accent-green) bg-[rgba(19,136,8,0.05)]" : "border-(--border-default)",
        dragging && "border-(--accent-saffron)",
      )}
      style={{
        transformStyle: "preserve-3d",
        perspective: "1000px",
        rotateX,
        rotateY,
        boxShadow: dragging
          ? "0 4px 16px rgba(255,102,0,0.15)"
          : fileName
            ? "0 4px 14px rgba(19,136,8,0.12)"
            : "0 2px 8px rgba(11,37,69,0.06)",
      }}
    >
      <div
        className="absolute inset-x-0 top-0 h-1.5 rounded-t-md"
        style={{ background: fileName ? "var(--accent-green)" : "var(--accent-saffron)" }}
      />

      <input
        className="hidden"
        type="file"
        accept={accept}
        onChange={(e) => onSelect(e.target.files?.[0] ?? null)}
      />

      <motion.div className="pointer-events-none absolute inset-0 rounded-lg" style={{ background: `radial-gradient(circle at top left, ${glow}, transparent 70%)` }} />

      <div className="relative z-10 flex items-center gap-2 text-(--accent-navy)">
        <motion.span animate={{ scale: [1, 1.08, 1] }} transition={{ duration: 2, repeat: Infinity }}>
          {icon}
        </motion.span>
        <span className="text-sm font-medium sm:text-base">{title}</span>
      </div>

      <div
        className="relative z-10 rounded-md border border-(--border-default) bg-white/50 px-3 py-4 text-center text-xs text-(--text-secondary) sm:text-sm"
      >
        {fileName ? (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center justify-center gap-2 text-(--accent-green)">
            <CheckCircle2 className="size-4" />
            <span className="max-w-[160px] truncate">{fileName}</span>
          </motion.div>
        ) : (
          <>
            <UploadCloud className="mx-auto mb-2 size-4" />
            {subtitle}
          </>
        )}
      </div>
    </motion.label>
  );
}
