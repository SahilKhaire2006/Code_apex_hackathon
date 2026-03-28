import { JSONHighlight } from "@/components/ui/JSONHighlight";
import type { RuleItem } from "@/lib/api";

interface RuleExtractionFeedProps {
  rules: RuleItem[];
}

export function RuleExtractionFeed({ rules }: RuleExtractionFeedProps) {
  return (
    <div className="space-y-4">
      {rules.slice(-4).map((rule) => (
        <div key={rule.id} className="relative rounded-xl border border-white/10 p-1">
          {rule.status && (
            <div className="absolute right-3 top-3 z-10">
              <span
                className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold tracking-wider ${
                  rule.status === "MODIFIED"
                    ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                    : rule.status === "NEW"
                    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                    : rule.status === "EXISTING"
                    ? "bg-blue-500/20 text-blue-300 border border-blue-500/30"
                    : "bg-gray-500/20 text-gray-300 border border-gray-500/30"
                }`}
              >
                {rule.status}
              </span>
            </div>
          )}
          <JSONHighlight data={rule} />
          {rule.modification_summary && (
            <div className="mt-2 text-xs text-amber-300 bg-amber-500/10 p-2 rounded border border-amber-500/20">
              <span className="font-semibold">Modification: </span>{rule.modification_summary}
            </div>
          )}
        </div>
      ))}
      {rules.length === 0 && (
        <div className="ui-panel-muted rounded-xl p-3 text-xs text-(--text-secondary)">
          Awaiting extracted rules...
        </div>
      )}
    </div>
  );
}
