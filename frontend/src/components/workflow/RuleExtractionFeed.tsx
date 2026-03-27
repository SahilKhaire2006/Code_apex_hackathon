import { JSONHighlight } from "@/components/ui/JSONHighlight";
import type { RuleItem } from "@/lib/api";

interface RuleExtractionFeedProps {
  rules: RuleItem[];
}

export function RuleExtractionFeed({ rules }: RuleExtractionFeedProps) {
  return (
    <div className="space-y-2">
      {rules.slice(-2).map((rule) => (
        <JSONHighlight key={rule.id} data={rule} />
      ))}
      {rules.length === 0 && (
        <div className="rounded-xl border border-white/10 bg-black/25 p-3 text-xs text-(--text-secondary)">
          Awaiting extracted rules...
        </div>
      )}
    </div>
  );
}
