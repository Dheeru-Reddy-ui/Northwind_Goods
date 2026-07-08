"use client";

import { useState } from "react";
import { ms, usd, stepMeta, titleCase } from "@/lib/format";
import { OutcomeBadge } from "@/components/ui";
import type { ConversationDetail, TraceStep } from "@/lib/types";

function TraceNode({ step, last }: { step: TraceStep; last: boolean }) {
  const [open, setOpen] = useState(false);
  const meta = stepMeta(step.step_type);
  const hasDetail = step.detail && Object.keys(step.detail).length > 0;
  const readout =
    step.step_type === "model"
      ? `${ms(step.latency_ms)} · ${usd(step.cost_usd)}`
      : step.latency_ms
      ? ms(step.latency_ms)
      : "";

  return (
    <li className="relative flex gap-3">
      {/* marker + connector = the spine */}
      <div className="relative flex flex-col items-center">
        <span
          className="mt-[3px] h-[11px] w-[11px] shrink-0 rounded-full border-2"
          style={{
            borderColor: meta.color,
            background: last ? meta.color : "var(--surface)",
            boxShadow: last ? `0 0 0 3px color-mix(in srgb, ${meta.color} 25%, transparent)` : undefined,
          }}
        />
        {!last && <span className="w-px flex-1" style={{ background: "var(--border)" }} />}
      </div>

      {/* content */}
      <div className="flex-1 pb-4">
        <button
          onClick={() => hasDetail && setOpen((o) => !o)}
          className="flex w-full items-center gap-2 text-left"
          style={{ cursor: hasDetail ? "pointer" : "default" }}
        >
          <span className="text-[13px] text-text">{step.label}</span>
          <span className="ml-auto shrink-0 font-mono text-[11px] text-text-dim">{readout}</span>
          {hasDetail && (
            <span className="shrink-0 font-mono text-[11px] text-text-faint">{open ? "−" : "+"}</span>
          )}
        </button>

        {open && hasDetail && (
          <pre className="mt-2 max-h-64 overflow-auto rounded-sm border border-border bg-surface-2 p-2.5 font-mono text-[11px] leading-relaxed text-text-dim">
            {JSON.stringify(step.detail, null, 2)}
          </pre>
        )}
      </div>
    </li>
  );
}

export function TraceTimeline({
  detail,
  loading,
}: {
  detail: ConversationDetail | null;
  loading: boolean;
}) {
  if (loading) {
    return <div className="p-6 text-[13px] text-text-dim">Loading trace…</div>;
  }
  if (!detail) {
    return (
      <div className="grid h-full place-items-center p-8 text-center">
        <div className="max-w-[240px] text-[13px] text-text-dim">
          Select a conversation to inspect its full reasoning trace — every model call, tool call,
          retrieval, guardrail, and escalation.
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* header */}
      <div className="border-b border-border p-4">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[12px] text-text-dim">{detail.id.slice(0, 8)}</span>
          <OutcomeBadge outcome={detail.outcome} />
          {detail.category && (
            <span className="rounded-sm bg-surface-2 px-2 py-0.5 text-[11px] text-text-dim">
              {titleCase(detail.category)}
            </span>
          )}
          <span className="ml-auto font-mono text-[11px] text-text-dim">
            {ms(detail.duration_ms)} · {usd(detail.cost_usd)}
            {detail.judge_score != null && ` · judge ${detail.judge_score}/5`}
          </span>
        </div>
        {detail.preview && <div className="mt-2 text-[13px] text-text-dim">“{detail.preview}”</div>}
      </div>

      {/* the spine */}
      <div className="flex-1 overflow-y-auto p-4">
        <ol className="spine-draw">
          {detail.steps.map((s, i) => (
            <TraceNode key={s.idx} step={s} last={i === detail.steps.length - 1} />
          ))}
        </ol>
      </div>
    </div>
  );
}
