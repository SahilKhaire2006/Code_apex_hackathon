import { cn } from "@/lib/utils";

interface JSONHighlightProps {
  data: unknown;
  className?: string;
}

export function JSONHighlight({ data, className }: JSONHighlightProps) {
  const json = JSON.stringify(data, null, 2) ?? "{}";

  const highlighted = json
    .replace(/"(.*?)"(?=:)/g, '<span class="text-(--accent-teal)">"$1"</span>')
    .replace(/: "(.*?)"/g, ': <span class="text-(--accent-green)">"$1"</span>')
    .replace(/: ([0-9.]+)/g, ': <span class="text-(--accent-amber)">$1</span>')
    .replace(/: (true|false)/g, ': <span class="text-violet-400">$1</span>')
    .replace(/: null/g, ': <span class="text-(--accent-red)">null</span>');

  return (
    <pre
      className={cn("overflow-x-auto rounded-xl border border-white/10 bg-black/30 p-3 font-mono text-[13px] text-slate-200", className)}
      dangerouslySetInnerHTML={{ __html: highlighted }}
    />
  );
}
