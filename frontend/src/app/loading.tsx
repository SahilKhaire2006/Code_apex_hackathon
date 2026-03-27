import { SkeletonGlass } from "@/components/ui/SkeletonGlass";

export default function Loading() {
  return (
    <div className="min-h-screen px-6 py-20">
      <div className="mx-auto grid max-w-6xl gap-4 md:grid-cols-2">
        <SkeletonGlass />
        <SkeletonGlass />
      </div>
    </div>
  );
}
