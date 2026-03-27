"use client";

import { motion } from "framer-motion";
import { Cpu, FileOutput, FileSearch, ShieldCheck } from "lucide-react";

const steps = [
  {
    id: "01",
    title: "Policy Ingestion",
    icon: FileSearch,
    description:
      "Your PDF is parsed page by page, chunked into semantic segments, embedded, and stored with clause metadata.",
  },
  {
    id: "02",
    title: "Rule Extraction",
    icon: Cpu,
    description:
      "Meta-Llama 3 converts policy clauses into structured JSON rules with field, operator, threshold, severity, and source.",
  },
  {
    id: "03",
    title: "Transaction Validation",
    icon: ShieldCheck,
    description:
      "Transactions run through threshold, temporal, and graph engines simultaneously for deep compliance checks.",
  },
  {
    id: "04",
    title: "Explainable Output",
    icon: FileOutput,
    description:
      "Every violation is linked to exact page and clause references, then compiled into an audit-ready report.",
  },
];

export function HowItWorks() {
  return (
    <section id="guidelines" className="gov-section-alt mx-auto max-w-7xl px-6 py-20">
      <h2 className="text-center text-3xl font-bold text-(--text-primary)">How PolicyGuard AI Works</h2>
      <p className="mx-auto mt-4 max-w-2xl text-center text-(--text-secondary)">
        From raw policy document to explainable compliance verdict, fully automated and fully traceable.
      </p>

      <div className="relative mt-12 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {steps.map((step, idx) => {
          const Icon = step.icon;
          return (
            <motion.article
              key={step.id}
              className="relative rounded-lg border border-(--border-default) border-l-4 border-l-(--accent-saffron) bg-white p-5"
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-50px" }}
              transition={{ duration: 0.5, delay: idx * 0.08, ease: "easeOut" }}
            >
              <div className="mb-4 inline-flex rounded-md bg-(--bg-dark) px-2 py-1 text-xs font-semibold tracking-[0.12em] text-white">{step.id}</div>
              <Icon className="mb-4 size-5 text-(--accent-saffron)" />
              <h3 className="mb-2 text-lg font-semibold text-(--text-primary)">{step.title}</h3>
              <p className="text-sm text-(--text-secondary)">{step.description}</p>
            </motion.article>
          );
        })}
      </div>

      <div className="mx-auto mt-6 max-w-4xl border-t border-dashed border-(--accent-saffron)" />
    </section>
  );
}
