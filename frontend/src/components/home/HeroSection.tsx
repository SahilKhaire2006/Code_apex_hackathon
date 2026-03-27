"use client";

import { useMemo, useState } from "react";
import { ArrowRight, Database, FileText, Link2, Loader2, X } from "lucide-react";
import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { UploadButton } from "@/components/home/UploadButton";
import { usePipelineStore } from "@/store/pipelineStore";

export function HeroSection() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [rulesModalOpen, setRulesModalOpen] = useState(false);
  const [modalLink, setModalLink] = useState("");
  const [modalPolicyFile, setModalPolicyFile] = useState<File | null>(null);
  const [modalCircularCode, setModalCircularCode] = useState("");
  const [rulesInputError, setRulesInputError] = useState<string | null>(null);

  const policyFile = usePipelineStore((s) => s.uploadedPolicyFile);
  const policyLink = usePipelineStore((s) => s.policyLink);
  const transactionFile = usePipelineStore((s) => s.uploadedTransactionFile);
  const setPolicyFile = usePipelineStore((s) => s.setPolicyFile);
  const setPolicyLink = usePipelineStore((s) => s.setPolicyLink);
  const setTransactionFile = usePipelineStore((s) => s.setTransactionFile);

  const ready = useMemo(() => Boolean(policyFile) || Boolean(policyLink.trim()), [policyFile, policyLink]);

  const selectedRulesLabel = useMemo(() => {
    if (policyFile) {
      return `PDF selected: ${policyFile.name}`;
    }
    if (policyLink.trim()) {
      return `Link selected: ${policyLink}`;
    }
    return "Add RBI circular/master direction link or upload .pdf";
  }, [policyFile, policyLink]);

  const openRulesModal = () => {
    setModalLink(policyLink);
    setModalPolicyFile(policyFile);
    setModalCircularCode("");
    setRulesInputError(null);
    setRulesModalOpen(true);
  };

  const saveRulesInput = () => {
    const trimmedLink = modalLink.trim();
    const trimmedCode = modalCircularCode.trim();
    if (!trimmedLink && !modalPolicyFile && !trimmedCode) {
      setRulesInputError("Provide a policy link, a circular code, or a policy PDF.");
      return;
    }

    if (trimmedLink) {
      setPolicyLink(trimmedLink);
    } else if (trimmedCode) {
      setPolicyLink(`[CIRCULAR]${trimmedCode}`);
    } else {
      setPolicyLink("");
    }

    if (modalPolicyFile) {
      setPolicyFile(modalPolicyFile);
    } else {
      setPolicyFile(null);
    }

    setRulesModalOpen(false);
  };

  return (
    <section id="new" className="relative flex min-h-screen items-center justify-center overflow-hidden bg-(--bg-primary) px-4 pt-32 pb-16 sm:px-6 sm:pt-36 md:pt-40 md:pb-20">
      <motion.div
        aria-hidden
        className="pointer-events-none absolute inset-0 m-auto h-[560px] w-[560px] opacity-[0.04]"
        initial={{ rotate: 0 }}
        animate={{ rotate: 360 }}
        transition={{ duration: 45, ease: "linear", repeat: Infinity }}
        style={{
          backgroundImage: "url('/ashoka-chakra.svg')",
          backgroundPosition: "center",
          backgroundRepeat: "no-repeat",
          backgroundSize: "contain",
        }}
      />

      <div className="relative z-10 mx-auto flex w-full max-w-5xl flex-col items-center text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6 rounded-full border border-(--border-saffron) bg-white px-4 py-1 text-[11px] font-semibold tracking-[0.15em] text-(--accent-saffron)"
        >
          GOVERNMENT COMPLIANCE SYSTEM
        </motion.div>

        <h1 className="mb-6 max-w-4xl text-3xl font-bold leading-[1.1] tracking-tight text-(--text-primary) sm:text-4xl md:text-5xl lg:text-6xl">
          <span className="inline-block text-(--accent-navy)">Compliance That Thinks.</span>
          <br />
          <span className="inline-block bg-[linear-gradient(90deg,#FF6600,#0B2545)] bg-clip-text text-transparent">
            Decisions That Explain Themselves.
          </span>
        </h1>

        <motion.p
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="mb-8 max-w-2xl px-2 text-base text-(--text-secondary) sm:text-lg"
        >
          Add your policy rules from an official circular link or a policy PDF. PolicyGuard AI will extract every rule,
          validate transactions, and explain every decision automatically.
        </motion.p>

        <div className="mb-8 flex w-full max-w-[620px] flex-col items-center gap-4 sm:gap-5 md:max-w-[720px] md:flex-row md:justify-center">
          <button
            type="button"
            onClick={openRulesModal}
            className="group relative flex h-[170px] w-full select-none flex-col justify-between rounded-lg border-2 border-dashed border-(--border-default) bg-white p-4 text-left shadow-[0_2px_8px_rgba(11,37,69,0.06)] transition hover:scale-[1.01] hover:border-(--accent-saffron) hover:shadow-[0_4px_16px_rgba(255,102,0,0.12)] sm:h-[180px] md:h-[190px] md:max-w-[260px]"
          >
            <div className="absolute inset-x-0 top-0 h-1.5 rounded-t-md bg-(--accent-saffron)" />
            <div className="relative z-10 flex items-center gap-2 text-(--accent-navy)">
              <FileText className="size-5" />
              <span className="text-sm font-medium sm:text-base">Add Rules</span>
            </div>
            <div className="relative z-10 rounded-md border border-(--border-default) bg-(--bg-secondary) px-3 py-3 text-xs text-(--text-secondary) sm:text-sm">
              <div className="line-clamp-3">{selectedRulesLabel}</div>
            </div>
          </button>

          <UploadButton
            title="Upload Transaction Data"
            subtitle="Drop .csv or .xlsx"
            accent="saffron"
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
          className="flex h-12 w-full max-w-[460px] items-center justify-center gap-2 rounded-md bg-(--accent-saffron) px-6 text-sm font-semibold text-white transition hover:bg-(--accent-saffron-hover) hover:shadow-[0_4px_20px_rgba(255,102,0,0.3)] sm:h-14 sm:text-base disabled:cursor-not-allowed disabled:opacity-40"
        >
          {loading ? <Loader2 className="size-5 animate-spin" /> : "Analyze Compliance"}
          {!loading && <ArrowRight className="size-4" />}
        </motion.button>
      </div>

      {rulesModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(11,37,69,0.42)] px-4">
          <div className="w-full max-w-xl rounded-lg border border-(--border-default) bg-white shadow-[0_14px_40px_rgba(11,37,69,0.2)]">
            <div className="flex items-center justify-between border-b border-(--border-default) px-4 py-3">
              <h3 className="text-sm font-semibold tracking-[0.08em] text-(--accent-navy) sm:text-base">ADD RULES</h3>
              <button
                type="button"
                className="rounded-md p-1 text-(--text-secondary) hover:bg-(--bg-secondary)"
                onClick={() => setRulesModalOpen(false)}
                aria-label="Close"
              >
                <X className="size-4" />
              </button>
            </div>

            <div className="space-y-4 px-4 py-4 sm:px-5 sm:py-5">
              <div>
                <label className="mb-1 block text-xs font-semibold tracking-[0.08em] text-(--accent-navy)">Policy Link</label>
                <div className="flex items-center gap-2 rounded-md border border-(--border-default) px-3 py-2">
                  <Link2 className="size-4 text-(--text-secondary)" />
                  <input
                    type="url"
                    value={modalLink}
                    onChange={(e) => {
                      setModalLink(e.target.value);
                      setRulesInputError(null);
                    }}
                    placeholder="https://rbi.org.in/..."
                    className="w-full bg-transparent text-sm text-(--text-primary) outline-none"
                  />
                </div>
                <p className="mt-1 text-xs text-(--text-secondary)">Paste circular/master direction URL for full rule extraction.</p>
              </div>

              <div className="text-center text-xs font-semibold tracking-[0.08em] text-(--text-secondary)">OR</div>

              <div>
                <label className="mb-1 block text-xs font-semibold tracking-[0.08em] text-(--accent-navy)">Policy PDF</label>
                <label className="flex cursor-pointer items-center justify-between rounded-md border border-dashed border-(--border-default) px-3 py-3 text-sm hover:border-(--accent-saffron)">
                  <span className="truncate text-(--text-secondary)">{modalPolicyFile?.name ?? "Choose .pdf file"}</span>
                  <span className="rounded bg-(--accent-saffron) px-2 py-1 text-xs font-semibold text-white">Browse</span>
                  <input
                    type="file"
                    accept=".pdf"
                    className="hidden"
                    onChange={(e) => {
                      setModalPolicyFile(e.target.files?.[0] ?? null);
                      setRulesInputError(null);
                    }}
                  />
                </label>
              </div>

              <div className="text-center text-xs font-semibold tracking-[0.08em] text-(--text-secondary)">OR</div>

              <div>
                <label className="mb-1 block text-xs font-semibold tracking-[0.08em] text-(--accent-navy)">RBI Circular Code</label>
                <input
                  type="text"
                  value={modalCircularCode}
                  onChange={(e) => {
                    setModalCircularCode(e.target.value);
                    setRulesInputError(null);
                  }}
                  placeholder="e.g., DNBS (PD) CC No.339 /03.10.42/ 2013-14"
                  className="w-full rounded-md border border-(--border-default) px-3 py-2 text-sm text-(--text-primary) outline-none"
                />
                <p className="mt-1 text-xs text-(--text-secondary)">Search for RBI circular/master direction by code.</p>
              </div>

              {rulesInputError && (
                <p className="text-xs font-medium text-(--violation)">{rulesInputError}</p>
              )}
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-(--border-default) px-4 py-3">
              <button
                type="button"
                onClick={() => setRulesModalOpen(false)}
                className="rounded-md border border-(--border-default) bg-white px-3 py-2 text-xs font-semibold text-(--accent-navy)"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={saveRulesInput}
                className="rounded-md bg-(--accent-saffron) px-3 py-2 text-xs font-semibold text-white"
              >
                Save Rules Source
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
