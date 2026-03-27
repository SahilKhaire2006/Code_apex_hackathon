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
      <header className="fixed inset-x-0 top-1 z-50">
        <motion.div
          initial={false}
          animate={{ height: scrolled ? 0 : 36, opacity: scrolled ? 0 : 1 }}
          className="overflow-hidden"
        >
          <div className="h-9 border-b border-white/15 bg-(--bg-dark)">
            <div className="mx-auto flex h-full max-w-7xl items-center justify-between px-4 md:px-6">
              <div className="inline-flex items-center gap-2 text-[11px] text-(--text-on-dark)">
                <svg viewBox="0 0 24 24" className="size-4" fill="currentColor" aria-hidden>
                  <path d="M12 2l3 3h-1v4h2l2 2v2h-2v6h-2v-6h-4v6H8v-6H6v-2l2-2h2V5H9l3-3z" />
                </svg>
                <span className="tracking-[0.06em]">Government of India</span>
              </div>
              <a href="#main-content" className="text-[11px] text-(--text-on-dark)">Skip to main content</a>
            </div>
          </div>
        </motion.div>

        <motion.nav
          className="border-b bg-(--bg-primary)"
          style={{ borderColor: "var(--border-default)" }}
          animate={{ boxShadow: scrolled ? "0 2px 8px rgba(0,0,0,0.1)" : "0 0 0 rgba(0,0,0,0)" }}
        >
          <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 md:px-6">
            <div className="min-w-0">
              <div className="truncate text-sm font-bold tracking-[0.03em] text-(--accent-navy)">PolicyGuard AI</div>
              <div className="truncate text-[11px] text-(--text-secondary)">Data Policy Compliance System</div>
            </div>

            <div className="hidden items-center gap-7 md:flex">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => onTabClick(tab.id)}
                  className={cn(
                    "relative pb-1 text-sm font-semibold tracking-[0.08em] text-(--accent-navy)",
                    "hover:underline",
                  )}
                >
                  {tab.label}
                  {activeTab === tab.id && (
                    <span className="absolute inset-x-0 -bottom-2 h-[3px] bg-(--accent-saffron)" />
                  )}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2">
              <a
                href="https://github.com/SahilKhaire2006/Code_apex_hackathon.git"
                target="_blank"
                rel="noreferrer"
                className="hidden items-center gap-2 rounded-md bg-(--accent-saffron) px-3 py-2 text-xs font-semibold text-white md:inline-flex"
              >
                External Link
                <ExternalLink className="size-3.5" />
              </a>
              <button
                className="inline-flex rounded-md border p-2 text-(--accent-navy) md:hidden"
                style={{ borderColor: "var(--border-default)" }}
                onClick={() => setOpen((prev) => !prev)}
                aria-label="Toggle menu"
              >
                {open ? <X className="size-4" /> : <Menu className="size-4" />}
              </button>
            </div>
          </div>
        </motion.nav>
      </header>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            className="fixed top-[101px] left-0 right-0 z-40 border-b bg-(--bg-primary) p-3 md:hidden"
            style={{ borderColor: "var(--border-default)" }}
          >
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => {
                  onTabClick(tab.id);
                  setOpen(false);
                }}
                className={cn(
                  "mb-1 block w-full border-l-2 px-4 py-3 text-left text-sm",
                  activeTab === tab.id
                    ? "border-l-(--accent-saffron) bg-(--bg-secondary) text-(--accent-navy)"
                    : "border-l-transparent text-(--text-secondary)",
                )}
              >
                {tab.label}
              </button>
            ))}

            <a
              href="https://github.com/SahilKhaire2006/Code_apex_hackathon.git"
              target="_blank"
              rel="noreferrer"
              className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-md bg-(--accent-saffron) px-4 py-2 text-sm font-semibold text-white"
            >
              External Link
              <ExternalLink className="size-3.5" />
            </a>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
