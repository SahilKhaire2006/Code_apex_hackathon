"use client";

import { ExternalLink, Menu, Moon, Sun, X } from "lucide-react";
import { AnimatePresence, motion, useMotionValueEvent, useScroll } from "framer-motion";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { useTheme } from "next-themes";

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
  const { theme, setTheme, resolvedTheme } = useTheme();

  const activeTheme = theme === "system" ? resolvedTheme : theme;
  const isDark = activeTheme ? activeTheme !== "light" : true;

  useMotionValueEvent(scrollY, "change", (latest) => {
    setScrolled(latest > 20);
  });

  return (
    <>
      <motion.nav
        className={cn(
          "fixed top-4 left-1/2 z-50 flex w-[calc(100%-1rem)] max-w-[760px] -translate-x-1/2 items-center justify-between rounded-full border px-3 py-2.5 sm:top-6 sm:w-[calc(100%-1.5rem)] sm:px-4 sm:py-3 md:px-6 lg:px-7",
          "transition-colors duration-200",
        )}
        style={{
          borderColor: "var(--nav-border)",
          backgroundColor: scrolled ? "var(--nav-bg-scrolled)" : "var(--nav-bg)",
        }}
        animate={{ backdropFilter: scrolled ? "blur(20px)" : "blur(16px)" }}
      >
        <div className="text-[11px] font-bold tracking-[0.1em] text-[var(--accent-teal)] sm:text-sm">POLICYGUARD.AI</div>

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
          <button
            aria-label="Toggle theme"
            className="inline-flex rounded-full border p-2 text-[var(--text-secondary)] transition hover:text-[var(--accent-teal)]"
            style={{ borderColor: "var(--surface-border)", backgroundColor: "var(--surface-soft)" }}
            onClick={() => {
              setTheme(isDark ? "light" : "dark");
            }}
          >
            {isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </button>
          <a
            href="https://github.com/SahilKhaire2006/Code_apex_hackathon.git"
            target="_blank"
            rel="noreferrer"
            className="hidden rounded-full border p-2 text-[var(--text-secondary)] transition hover:shadow-[0_0_20px_rgba(0,212,255,0.35)] hover:text-[var(--accent-teal)] md:inline-flex"
            style={{ borderColor: "var(--surface-border)", backgroundColor: "var(--surface-soft)" }}
          >
            <ExternalLink className="size-4" />
          </a>
          <button
            className="inline-flex rounded-full border p-2 text-[var(--text-secondary)] md:hidden"
            style={{ borderColor: "var(--surface-border)", backgroundColor: "var(--surface-soft)" }}
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
            className="fixed top-24 left-3 right-3 z-40 rounded-2xl border p-3 backdrop-blur-xl md:hidden"
            style={{ borderColor: "var(--nav-border)", backgroundColor: "var(--nav-bg-scrolled)" }}
          >
            <button
              className="mb-2 inline-flex w-full items-center justify-center gap-2 rounded-xl border px-4 py-3 text-sm text-[var(--text-secondary)]"
              style={{ borderColor: "var(--surface-border)", backgroundColor: "var(--surface-soft)" }}
              onClick={() => setTheme(isDark ? "light" : "dark")}
            >
              {isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}
              {isDark ? "Switch to Light" : "Switch to Dark"}
            </button>
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
