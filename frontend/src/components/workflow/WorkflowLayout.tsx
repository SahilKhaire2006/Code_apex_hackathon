"use client";

import { motion } from "framer-motion";
import { Phase1Panel } from "@/components/workflow/Phase1Panel";
import { Phase2Panel } from "@/components/workflow/Phase2Panel";

export function WorkflowLayout() {
  return (
    <div className="relative grid min-h-[calc(100vh-88px)] grid-cols-1 md:grid-cols-[1fr_auto_1fr]">
      <div className="min-h-[50vh] md:h-[calc(100vh-88px)] md:overflow-y-auto lg:h-[calc(100vh-96px)]">
        <Phase1Panel />
      </div>

      <div className="relative mx-auto hidden w-px bg-[rgba(0,212,255,0.2)] md:block">
        <motion.div
          className="absolute left-0 h-20 w-px bg-[linear-gradient(180deg,transparent,#00D4FF,transparent)]"
          animate={{ y: [0, 760] }}
          transition={{ duration: 2.5, repeat: Infinity, ease: "linear" }}
        />
      </div>

      <div className="min-h-[50vh] md:h-[calc(100vh-88px)] md:overflow-y-auto lg:h-[calc(100vh-96px)]">
        <Phase2Panel />
      </div>
    </div>
  );
}
