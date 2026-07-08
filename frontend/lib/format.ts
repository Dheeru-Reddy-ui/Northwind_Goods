import type { Outcome } from "./types";

export function usd(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v < 0.01 && v > 0) return `$${v.toFixed(4)}`;
  return `$${v.toFixed(2)}`;
}

export function ms(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1000) return `${(v / 1000).toFixed(2)}s`;
  return `${Math.round(v)}ms`;
}

export function pct(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${Math.round(v * 100)}%`;
}

export function ago(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso).getTime();
  const s = Math.floor((Date.now() - d) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export const OUTCOME_META: Record<Outcome, { label: string; color: string }> = {
  resolved: { label: "Resolved", color: "var(--resolved)" },
  escalated: { label: "Escalated", color: "var(--escalated)" },
  pending_approval: { label: "Pending", color: "var(--pending)" },
  open: { label: "Open", color: "var(--text-dim)" },
};

// Trace step type -> color (matches the design system's node coding)
export const STEP_META: Record<string, { color: string; glyph: string }> = {
  model: { color: "var(--primary)", glyph: "◆" },
  tool: { color: "var(--info)", glyph: "▸" },
  retrieval: { color: "var(--accent)", glyph: "❋" },
  guardrail: { color: "var(--text-dim)", glyph: "▣" },
  escalation: { color: "var(--escalated)", glyph: "▲" },
  approval_gate: { color: "var(--pending)", glyph: "◈" },
  audio: { color: "var(--accent)", glyph: "♪" },
  message: { color: "var(--text-faint)", glyph: "●" },
};

export function stepMeta(t: string) {
  return STEP_META[t] || STEP_META.message;
}

export function titleCase(s: string | null): string {
  if (!s) return "";
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
