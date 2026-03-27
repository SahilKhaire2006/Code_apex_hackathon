import { Shield } from "lucide-react";

export function GovernmentFooter() {
  const year = new Date().getFullYear();
  const lastUpdated = new Date().toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });

  return (
    <footer className="mt-16 border-t-4 border-t-(--accent-saffron) bg-(--bg-dark) text-(--text-on-dark)">
      <div className="mx-auto grid max-w-7xl gap-6 px-6 py-8 md:grid-cols-3 md:items-start">
        <div className="space-y-2">
          <div className="inline-flex items-center gap-2 text-sm font-semibold">
            <Shield className="size-4" />
            PolicyGuard AI is part of India's Digital Governance Initiative
          </div>
        </div>

        <nav className="flex flex-wrap gap-4 text-sm">
          <a href="#">About</a>
          <a href="#guidelines">Guidelines</a>
          <a href="#">Privacy Policy</a>
          <a href="#">Help</a>
        </nav>

        <div className="text-sm md:text-right">
          <div>Last updated: {lastUpdated}</div>
          <div className="text-white/80">Version 1.0.0</div>
        </div>
      </div>

      <div className="border-t border-white/10 px-6 py-3 text-center text-xs text-white/70">
        © {year} Government of India. All Rights Reserved.
      </div>
    </footer>
  );
}
