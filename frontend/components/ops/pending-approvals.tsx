"use client";

import { useState } from "react";
import { approveAction, rejectAction } from "@/lib/api";
import { Card, Eyebrow } from "@/components/ui";
import type { PendingAction } from "@/lib/types";

export function PendingApprovals({
  items,
  onResolved,
}: {
  items: PendingAction[];
  onResolved: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);

  async function act(id: string, approve: boolean) {
    setBusy(id);
    try {
      await (approve ? approveAction(id) : rejectAction(id));
      onResolved();
    } catch (e) {
      // surfaced by the parent's next refresh
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <Eyebrow>Pending approvals</Eyebrow>
        <span
          className="rounded-full px-2 py-0.5 text-[11px] font-500"
          style={{ color: "var(--pending)", background: "color-mix(in srgb, var(--pending) 16%, transparent)" }}
        >
          {items.length}
        </span>
      </div>

      {items.length === 0 ? (
        <div className="mt-3 text-[13px] text-text-dim">Nothing awaiting review.</div>
      ) : (
        <div className="mt-3 flex flex-col gap-2">
          {items.map((p) => (
            <div key={p.id} className="rounded-sm border border-border bg-surface-2 p-3">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[12px] text-text">
                  {String(p.args.order_id ?? "")}
                </span>
                <span className="font-mono text-[13px] font-500" style={{ color: "var(--pending)" }}>
                  ${((Number(p.args.amount_cents) || 0) / 100).toFixed(2)}
                </span>
              </div>
              <div className="mt-1 text-[12px] text-text-dim">{p.reason}</div>
              <div className="mt-2.5 flex gap-2">
                <button
                  onClick={() => act(p.id, true)}
                  disabled={busy === p.id}
                  className="rounded-sm px-3 py-1 text-[12px] font-500 text-white disabled:opacity-50"
                  style={{ background: "var(--resolved)" }}
                >
                  Approve
                </button>
                <button
                  onClick={() => act(p.id, false)}
                  disabled={busy === p.id}
                  className="rounded-sm border border-border px-3 py-1 text-[12px] text-text-dim hover:text-text disabled:opacity-50"
                >
                  Reject
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
