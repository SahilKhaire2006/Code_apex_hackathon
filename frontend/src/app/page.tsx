"use client";

import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { ShieldCheck, Database, Search } from "lucide-react";
import { Navbar } from "@/components/layout/Navbar";
import { GovernmentFooter } from "@/components/layout/GovernmentFooter";
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
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="min-h-screen bg-(--bg-primary)"
    >
      <Navbar
        activeTab={activeTab}
        onTabClick={(id) => {
          setActiveTab(id);
          const section = document.getElementById(tabMap[id as keyof typeof tabMap]);
          section?.scrollIntoView({ behavior: "smooth", block: "start" });
        }}
      />

      <div id="main-content" className="pt-2">
        <HeroSection />
      </div>

      {/* Enterprise Features */}
      <section id="features" className="mx-auto max-w-7xl px-6 py-20 pb-10">
        <div className="mb-12 text-center">
          <h2 className="text-3xl font-bold text-[#000080]">Enterprise-Grade Compliance</h2>
          <p className="mx-auto mt-3 max-w-2xl text-sm text-[#6B5B3E]">
            PolicyGuard transforms complex regulatory documents into actionable, automated rule sets with complete transparency.
          </p>
        </div>
        <div className="grid gap-6 md:grid-cols-3">
          {[
            {
              title: "Automated Rule Ingestion",
              desc: "Extract structured standard rules directly from unstructured RBI Master Directions and circular PDFs using a specialized LLM pipeline.",
              icon: <ShieldCheck className="size-6 text-[#FF6600]" />
            },
            {
              title: "High-Throughput Validation",
              desc: "Process millions of transaction records against dynamically generated condition matrices in seconds, reducing auditor backlog.",
              icon: <Database className="size-6 text-[#138808]" />
            },
            {
              title: "Complete Explainability",
              desc: "Our verification layer maps every flagged transaction back to the exact source clause, ensuring full regulatory audibility.",
              icon: <Search className="size-6 text-[#000080]" />
            }
          ].map((feature, idx) => (
            <motion.div key={idx} initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: idx * 0.1 }}
              className="rounded-2xl border border-[#E8D5B0] bg-white p-6 shadow-[0_4px_20px_rgba(139,90,0,0.06)] transition-all hover:scale-[1.02] hover:shadow-[0_8px_30px_rgba(139,90,0,0.12)]">
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl border border-[#E8DCCA] bg-[#FFFDF5]">
                {feature.icon}
              </div>
              <h3 className="mb-2 text-lg font-bold text-[#1A1A1A]">{feature.title}</h3>
              <p className="text-sm leading-relaxed text-[#6B5B3E]">{feature.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      <HowItWorks />
      <ComplianceSimulation />
      <GovernmentFooter />
    </motion.main>
  );
}
