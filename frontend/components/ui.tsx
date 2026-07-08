import clsx from "clsx";
import { OUTCOME_META } from "@/lib/format";
import type { Outcome } from "@/lib/types";

export function StatusDot({ outcome, className }: { outcome: Outcome; className?: string }) {
  const meta = OUTCOME_META[outcome] || OUTCOME_META.open;
  return (
    <span
      className={clsx("inline-block h-2 w-2 rounded-full", className)}
      style={{ background: meta.color }}
      aria-hidden
    />
  );
}

export function OutcomeBadge({ outcome }: { outcome: Outcome }) {
  const meta = OUTCOME_META[outcome] || OUTCOME_META.open;
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-sm px-2 py-0.5 text-[11px] font-500"
      style={{ color: meta.color, background: `color-mix(in srgb, ${meta.color} 14%, transparent)` }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: meta.color }} />
      {meta.label}
    </span>
  );
}

export function Card({
  children,
  className,
  ...rest
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={clsx("rounded-lg border border-border bg-surface", className)}
      {...rest}
    >
      {children}
    </div>
  );
}

export function Eyebrow({ children }: { children: React.ReactNode }) {
  return <div className="eyebrow">{children}</div>;
}
