"use client";

import clsx from "clsx";
import { StatusDot } from "@/components/ui";
import { ago, ms, usd, titleCase } from "@/lib/format";
import type { ConversationSummary } from "@/lib/types";

export function ConversationsTable({
  rows,
  selectedId,
  onSelect,
}: {
  rows: ConversationSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (!rows.length) {
    return (
      <div className="grid h-40 place-items-center text-center text-[13px] text-text-dim">
        No conversations yet. Run the simulation or chat with the agent to populate this.
      </div>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-border text-left">
            <th className="px-3 py-2 font-500 text-text-dim">Conversation</th>
            <th className="px-2 py-2 font-500 text-text-dim">Category</th>
            <th className="px-2 py-2 font-500 text-text-dim">Judge</th>
            <th className="px-2 py-2 text-right font-500 text-text-dim">Cost</th>
            <th className="px-2 py-2 text-right font-500 text-text-dim">Time</th>
            <th className="px-3 py-2 text-right font-500 text-text-dim">When</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr
              key={c.id}
              onClick={() => onSelect(c.id)}
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && onSelect(c.id)}
              className={clsx(
                "cursor-pointer border-b border-border/60 transition-colors",
                selectedId === c.id ? "bg-surface-2" : "hover:bg-surface-2/60"
              )}
            >
              <td className="px-3 py-2.5">
                <div className="flex items-center gap-2">
                  <StatusDot outcome={c.outcome} />
                  <div className="min-w-0">
                    <div className="truncate text-text">{c.preview || c.session_id}</div>
                    <div className="font-mono text-[11px] text-text-faint">
                      {c.id.slice(0, 8)}
                      {c.channel === "voice" ? " · voice" : ""}
                      {c.source === "simulation" ? " · sim" : ""}
                    </div>
                  </div>
                </div>
              </td>
              <td className="px-2 py-2.5 text-text-dim">{titleCase(c.category)}</td>
              <td className="px-2 py-2.5 font-mono text-text-dim">
                {c.judge_score != null ? `${c.judge_score}` : "—"}
              </td>
              <td className="px-2 py-2.5 text-right font-mono text-text-dim">{usd(c.cost_usd)}</td>
              <td className="px-2 py-2.5 text-right font-mono text-text-dim">{ms(c.duration_ms)}</td>
              <td className="px-3 py-2.5 text-right text-text-faint">{ago(c.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
