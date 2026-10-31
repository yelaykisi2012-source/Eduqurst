import type { HTMLAttributes } from "react";

interface SkeletonProps extends HTMLAttributes<HTMLDivElement> {
  className?: string;
}

export function Skeleton({ className = "", ...props }: SkeletonProps) {
  return (
    <div
      className={`animate-pulse rounded-2xl bg-slate-200/70 ${className}`}
      {...props}
    />
  );
}

export function SubjectCardSkeleton() {
  return (
    <div className="flex items-center gap-4 rounded-3xl bg-white p-5 border border-slate-100 shadow-sm">
      <Skeleton className="h-14 w-14 rounded-2xl" />
      <div className="flex-1 space-y-2">
        <Skeleton className="h-5 w-2/3" />
        <Skeleton className="h-3.5 w-1/3" />
        <Skeleton className="h-2 w-full mt-2" />
      </div>
    </div>
  );
}
