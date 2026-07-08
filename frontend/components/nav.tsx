"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import clsx from "clsx";

const LINKS = [
  { href: "/", label: "Chat" },
  { href: "/voice", label: "Voice" },
  { href: "/ops", label: "Dashboard" },
];

export function Nav() {
  const pathname = usePathname();
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const saved = (localStorage.getItem("nw-theme") as "dark" | "light") || "dark";
    setTheme(saved);
    document.documentElement.setAttribute("data-theme", saved);
  }, []);

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("nw-theme", next);
  }

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-bg/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-6 px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2.5">
          <span
            className="grid h-6 w-6 place-items-center rounded-sm text-[13px]"
            style={{ background: "var(--primary-tint)", color: "var(--primary)" }}
            aria-hidden
          >
            ◆
          </span>
          <span className="font-display text-[15px] font-600 tracking-tight text-text">
            Northwind Support AI
          </span>
        </Link>

        <nav className="flex items-center gap-1">
          {LINKS.map((l) => {
            const active = l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
            return (
              <Link
                key={l.href}
                href={l.href}
                className={clsx(
                  "rounded-sm px-3 py-1.5 text-[13px] transition-colors",
                  active ? "text-text" : "text-text-dim hover:text-text"
                )}
                style={active ? { background: "var(--surface-2)" } : undefined}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <Link
            href="/ops?run=1"
            className="rounded-sm px-3 py-1.5 text-[13px] font-500 text-white transition-colors"
            style={{ background: "var(--primary)" }}
          >
            Run simulation
          </Link>
          <button
            onClick={toggle}
            aria-label="Toggle theme"
            className="grid h-8 w-8 place-items-center rounded-sm text-text-dim hover:text-text"
            style={{ background: "var(--surface)" }}
          >
            {theme === "dark" ? "☾" : "☀"}
          </button>
        </div>
      </div>
    </header>
  );
}
