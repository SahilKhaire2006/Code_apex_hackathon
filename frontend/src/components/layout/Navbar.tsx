"use client";

import { ExternalLink, Menu, X } from "lucide-react";
import { AnimatePresence, motion, useMotionValueEvent, useScroll } from "framer-motion";
import { useState } from "react";
import { cn } from "@/lib/utils";

const tabs = [
  { id: "recent", label: "RECENT" },
  { id: "guidelines", label: "GUIDELINES" },
  { id: "new", label: "NEW" },
] as const;

interface NavbarProps {
  activeTab: string;
  onTabClick: (id: string) => void;
}

export function Navbar({ activeTab, onTabClick }: NavbarProps) {
  const { scrollY } = useScroll();
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useMotionValueEvent(scrollY, "change", (latest) => {
    setScrolled(latest > 20);
  });

  return (
    <>
      <motion.nav
        className={cn(
          "fixed top-6 left-1/2 z-50 flex w-[calc(100%-1.5rem)] max-w-[700px] -translate-x-1/2 items-center justify-between rounded-full border px-4 py-3 md:px-7",
          "transition-colors duration-200",
          scrolled
            ? "border-[rgba(0,212,255,0.25)] bg-[rgba(2,11,24,0.94)]"
            : "border-[rgba(0,212,255,0.15)] bg-[rgba(2,11,24,0.85)]",
        )}
        animate={{ backdropFilter: scrolled ? "blur(20px)" : "blur(16px)" }}
      >
        <div className="text-sm font-bold tracking-[0.1em] text-[var(--accent-teal)]">POLICYGUARD.AI</div>

        <div className="hidden items-center gap-2 md:flex">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => onTabClick(tab.id)}
              className={cn(
                "relative rounded-full px-4 py-2 text-sm font-medium transition-colors",
                activeTab === tab.id ? "text-[var(--accent-teal)]" : "text-[var(--text-secondary)] hover:text-[var(--accent-teal)]",
              )}
            >
              {activeTab === tab.id && (
                <motion.span
                  layoutId="nav-pill"
                  className="absolute inset-0 rounded-full bg-[rgba(0,212,255,0.12)]"
                  transition={{ type: "spring", stiffness: 400, damping: 30 }}
                />
              )}
              <span className="relative z-10">{tab.label}</span>
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <a
            href="https://github.com"
            target="_blank"
            rel="noreferrer"
            className="hidden rounded-full border border-[rgba(0,212,255,0.2)] p-2 text-[var(--text-secondary)] transition hover:shadow-[0_0_20px_rgba(0,212,255,0.35)] hover:text-[var(--accent-teal)] md:inline-flex"
          >
            <ExternalLink className="size-4" />
          </a>
          <button
            className="inline-flex rounded-full border border-[rgba(0,212,255,0.2)] p-2 text-[var(--text-secondary)] md:hidden"
            onClick={() => setOpen((prev) => !prev)}
          >
            {open ? <X className="size-4" /> : <Menu className="size-4" />}
          </button>
        </div>
      </motion.nav>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            className="fixed top-24 left-3 right-3 z-40 rounded-2xl border border-[rgba(0,212,255,0.2)] bg-[rgba(2,11,24,0.92)] p-3 backdrop-blur-xl md:hidden"
          >
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => {
                  onTabClick(tab.id);
                  setOpen(false);
                }}
                className={cn(
                  "mb-1 block w-full rounded-xl px-4 py-3 text-left text-sm",
                  activeTab === tab.id ? "bg-[rgba(0,212,255,0.12)] text-[var(--accent-teal)]" : "text-[var(--text-secondary)]",
                )}
              >
                {tab.label}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
