"use client";

import { useMemo, useState } from "react";
import { ArrowRight, Database, FileText, Loader2 } from "lucide-react";
import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { UploadButton } from "@/components/home/UploadButton";
import { ParticleBackground } from "@/components/ui/ParticleBackground";
import { usePipelineStore } from "@/store/pipelineStore";

export function HeroSection() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  const policyFile = usePipelineStore((s) => s.uploadedPolicyFile);
  const transactionFile = usePipelineStore((s) => s.uploadedTransactionFile);
  const setPolicyFile = usePipelineStore((s) => s.setPolicyFile);
  const setTransactionFile = usePipelineStore((s) => s.setTransactionFile);

  const ready = useMemo(() => Boolean(policyFile && transactionFile), [policyFile, transactionFile]);

  return (
    <section id="new" className="relative flex min-h-screen items-center justify-center overflow-hidden px-6 pt-36 pb-20">
      <div className="pointer-events-none absolute -top-40 -left-20 h-[420px] w-[420px] rounded-full bg-[radial-gradient(circle,rgba(0,212,255,0.06),transparent_70%)]" />
      <div className="pointer-events-none absolute -right-20 -bottom-20 h-[420px] w-[420px] rounded-full bg-[radial-gradient(circle,rgba(0,120,255,0.06),transparent_70%)]" />
      <ParticleBackground />

      <div className="relative z-10 mx-auto flex max-w-5xl flex-col items-center text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6 rounded-full border border-[var(--accent-teal)] px-4 py-1 text-[11px] font-semibold tracking-[0.15em] text-[var(--accent-teal)]"
        >
          AGENTIC AI COMPLIANCE SYSTEM
        </motion.div>

        <h1 className="mb-6 max-w-4xl text-4xl font-bold leading-[1.1] tracking-tight text-[var(--text-primary)] md:text-6xl">
          <span className="inline-block">Compliance That Thinks.</span>
          <br />
          <span className="inline-block bg-[linear-gradient(90deg,#00D4FF,#00FF88)] bg-clip-text text-transparent">
            Decisions That Explain Themselves.
          </span>
        </h1>

        <motion.p
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="mb-10 max-w-2xl text-lg text-[var(--text-secondary)]"
        >
          Upload your compliance policy and transaction dataset. PolicyGuard AI will extract every rule,
          validate every transaction, and explain every decision automatically.
        </motion.p>

        <div className="mb-8 flex flex-col gap-5 md:flex-row">
          <UploadButton
            title="Upload Policy PDF"
            subtitle="Drop .pdf"
            accent="teal"
            accept=".pdf"
            fileName={policyFile?.name ?? null}
            icon={<FileText className="size-5" />}
            onSelect={(file) => setPolicyFile(file)}
          />

          <UploadButton
            title="Upload Transaction Data"
            subtitle="Drop .csv or .xlsx"
            accent="green"
            mirror
            accept=".csv,.xlsx"
            fileName={transactionFile?.name ?? null}
            icon={<Database className="size-5" />}
            onSelect={(file) => setTransactionFile(file)}
          />
        </div>

        <motion.button
          disabled={!ready || loading}
          whileHover={ready ? { scale: 1.01 } : undefined}
          whileTap={ready ? { scale: 0.98 } : undefined}
          onClick={async () => {
            setLoading(true);
            await new Promise((r) => setTimeout(r, 300));
            router.push("/agent-workflow");
          }}
          className="flex h-14 w-full max-w-[460px] items-center justify-center gap-2 rounded-full bg-[linear-gradient(135deg,#00D4FF,#0099BB)] px-6 font-semibold text-white shadow-[0_8px_30px_rgba(0,212,255,0.35)] transition disabled:cursor-not-allowed disabled:opacity-40"
        >
          {loading ? <Loader2 className="size-5 animate-spin" /> : "Analyze Compliance"}
          {!loading && <ArrowRight className="size-4" />}
        </motion.button>
      </div>
    </section>
  );
}
