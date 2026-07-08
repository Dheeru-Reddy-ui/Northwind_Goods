"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";

const TABS = [
  { href: "/ops", label: "Console" },
  { href: "/ops/impact", label: "Impact" },
  { href: "/ops/insights", label: "Insights" },
];

export function OpsTabs() {
  const pathname = usePathname();
  return (
    <div className="inline-flex rounded-sm border border-border bg-surface p-0.5">
      {TABS.map((t) => {
        const active = pathname === t.href;
        return (
          <Link
            key={t.href}
            href={t.href}
            className={clsx(
              "rounded-[4px] px-3 py-1 text-[13px] transition-colors",
              active ? "text-text" : "text-text-dim hover:text-text"
            )}
            style={active ? { background: "var(--surface-2)" } : undefined}
          >
            {t.label}
          </Link>
        );
      })}
    </div>
  );
}
