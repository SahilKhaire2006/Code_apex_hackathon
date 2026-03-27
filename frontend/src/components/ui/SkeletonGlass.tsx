export function SkeletonGlass() {
  return (
    <div className="glass-card relative overflow-hidden rounded-2xl p-6">
      <div className="shimmer absolute inset-0" />
      <div className="relative space-y-4">
        <div className="h-4 w-40 rounded bg-white/10" />
        <div className="h-24 rounded bg-white/5" />
        <div className="h-24 rounded bg-white/5" />
      </div>
    </div>
  );
}
