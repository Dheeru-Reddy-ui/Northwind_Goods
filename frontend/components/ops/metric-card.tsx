"use client";

import { useEffect, useRef, useState } from "react";

function useCountUp(target: number, duration = 800) {
  const [val, setVal] = useState(0);
  const prev = useRef(0);
  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setVal(target);
      prev.current = target;
      return;
    }
    const from = prev.current;
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setVal(from + (target - from) * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
      else prev.current = target;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);
  return val;
}

export function MetricCard({
  label,
  value,
  suffix = "",
  format = "number",
  accent = "var(--primary)",
}: {
  label: string;
  value: number;
  suffix?: string;
  format?: "number" | "percent" | "usd" | "raw";
  accent?: string;
}) {
  const animated = useCountUp(value);
  let display: string;
  if (format === "percent") display = `${Math.round(animated * 100)}%`;
  else if (format === "usd") display = `$${animated.toFixed(animated < 0.01 ? 4 : 2)}`;
  else if (format === "raw") display = animated.toFixed(1);
  else display = Math.round(animated).toString();

  return (
    <div className="relative overflow-hidden rounded-lg border border-border bg-surface p-4">
      <div className="eyebrow">{label}</div>
      <div className="mt-1.5 font-display text-[28px] font-600 leading-none text-text tabular-nums">
        {display}
        {suffix && <span className="ml-0.5 text-[15px] text-text-dim">{suffix}</span>}
      </div>
      <div className="absolute inset-x-0 bottom-0 h-[3px]" style={{ background: accent, opacity: 0.7 }} />
    </div>
  );
}
