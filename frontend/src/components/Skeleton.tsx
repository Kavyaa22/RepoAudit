interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className = "" }: SkeletonProps) {
  return <div className={`animate-pulse rounded-md bg-slate-200/80 ${className}`} />;
}

export function WikiPageSkeleton() {
  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden">
      <aside className="w-64 shrink-0 border-r border-slate-200 bg-slate-50 p-4 space-y-4">
        <div className="flex gap-2">
          <Skeleton className="h-8 flex-1" />
          <Skeleton className="h-8 flex-1" />
        </div>
        <div className="flex items-center gap-2">
          <Skeleton className="h-7 w-7 rounded" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5 w-36" />
            <Skeleton className="h-2.5 w-20" />
          </div>
        </div>
        <div className="space-y-2 pt-2">
          {Array.from({ length: 8 }).map((_, idx) => (
            <Skeleton key={idx} className="h-8 w-full" />
          ))}
        </div>
      </aside>
      <div className="flex-1 flex flex-col">
        <div className="h-14 border-b border-slate-200 bg-white px-6 flex items-center justify-between">
          <Skeleton className="h-4 w-64" />
          <div className="flex gap-2">
            <Skeleton className="h-8 w-24" />
            <Skeleton className="h-8 w-24" />
          </div>
        </div>
        <div className="flex-1 p-8 space-y-4">
          <Skeleton className="h-8 w-72" />
          <Skeleton className="h-4 w-full max-w-2xl" />
          <Skeleton className="h-4 w-5/6 max-w-xl" />
          <div className="mt-8 space-y-2">
            <Skeleton className="h-10 w-full" />
            {Array.from({ length: 6 }).map((_, idx) => (
              <Skeleton key={idx} className="h-12 w-full" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function TableSkeleton({ rows = 6, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="generated-table-wrap rounded-xl border border-slate-200 bg-white overflow-hidden">
      <div className="grid gap-0">
        <div className="flex gap-3 bg-slate-50 px-4 py-3 border-b border-slate-200">
          {Array.from({ length: cols }).map((_, idx) => (
            <Skeleton key={idx} className="h-3.5 flex-1" />
          ))}
        </div>
        {Array.from({ length: rows }).map((_, row) => (
          <div key={row} className="flex gap-3 px-4 py-3.5 border-b border-slate-100 last:border-0">
            {Array.from({ length: cols }).map((_, col) => (
              <Skeleton key={col} className="h-3.5 flex-1" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export function CardSkeleton({ className = "" }: SkeletonProps) {
  return (
    <div className={`rounded-2xl border border-slate-200 bg-white p-5 ${className}`}>
      <div className="flex items-center gap-4 animate-pulse">
        <div className="w-10 h-10 rounded-xl bg-slate-200 shrink-0" />
        <div className="flex-1 space-y-2">
          <div className="h-3 w-24 bg-slate-200 rounded" />
          <div className="h-5 w-16 bg-slate-200 rounded" />
          <div className="h-2.5 w-28 bg-slate-200 rounded" />
        </div>
      </div>
    </div>
  );
}
