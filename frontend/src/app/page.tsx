"use client";

import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Navbar } from "@/components/layout/Navbar";
import { HeroSection } from "@/components/home/HeroSection";
import { HowItWorks } from "@/components/home/HowItWorks";
import { ComplianceSimulation } from "@/components/home/ComplianceSimulation";

export default function HomePage() {
  const [activeTab, setActiveTab] = useState("new");

  const tabMap = useMemo(
    () => ({
      recent: "recent",
      guidelines: "guidelines",
      new: "new",
    }),
    [],
  );

  return (
    <motion.main
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="min-h-screen"
    >
      <Navbar
        activeTab={activeTab}
        onTabClick={(id) => {
          setActiveTab(id);
          const section = document.getElementById(tabMap[id as keyof typeof tabMap]);
          section?.scrollIntoView({ behavior: "smooth", block: "start" });
        }}
      />

      <HeroSection />

      <section id="recent" className="mx-auto max-w-7xl px-6 py-16">
        <h2 className="text-3xl font-bold text-[var(--text-primary)]">Recent Analysis Sessions</h2>
        <p className="mt-2 text-[var(--text-secondary)]">No previous sessions yet. Your latest compliance runs will appear here.</p>
        <div className="mt-6 grid gap-4 md:grid-cols-3">
          {Array.from({ length: 3 }).map((_, idx) => (
            <div key={idx} className="glass-card rounded-2xl p-4">
              <div className="h-3 w-28 rounded bg-white/10" />
              <div className="mt-3 h-20 rounded bg-white/5" />
            </div>
          ))}
        </div>
      </section>

      <HowItWorks />
      <ComplianceSimulation />
    </motion.main>
  );
}
