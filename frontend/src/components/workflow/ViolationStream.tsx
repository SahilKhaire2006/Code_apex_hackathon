import { AlertCircle, CheckCircle, XCircle } from "lucide-react";
import type { ViolationItem } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

interface ViolationStreamProps {
  violations: ViolationItem[];
}

export function ViolationStream({ violations }: ViolationStreamProps) {
  return (
    <div className="space-y-2">
      {violations.slice(-5).map((item) => (
        <div key={item.id} className="ui-panel-muted rounded-lg p-2 text-xs">
          <div className="flex items-center justify-between gap-2 font-mono text-(--text-primary)">
            <span>{item.transactionId}</span>
            <span>{item.amount != null ? formatCurrency(item.amount) : "N/A"}</span>
          </div>
          <div className="mt-1 flex items-center gap-1 text-(--text-secondary)">
            {item.status === "COMPLIANT" && <CheckCircle className="size-3 text-(--accent-green)" />}
            {item.status === "VIOLATION" && <XCircle className="size-3 text-(--accent-red)" />}
            {item.status === "NEEDS_REVIEW" && <AlertCircle className="size-3 text-(--accent-amber)" />}
            <span
              className={`inline-flex rounded-sm px-1.5 py-0.5 text-[10px] font-semibold text-white ${
                item.status === "COMPLIANT"
                  ? "bg-(--compliant)"
                  : item.status === "VIOLATION"
                    ? "bg-(--violation)"
                    : "bg-(--warning)"
              }`}
            >
              {item.status}
            </span>
            <span>{item.rule} • {item.severity}</span>
          </div>
        </div>
      ))}
      {violations.length === 0 && <div className="text-xs text-(--text-secondary)">No violations streamed yet.</div>}
    </div>
  );
}
