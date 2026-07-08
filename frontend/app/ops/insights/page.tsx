"use client";

import { useCallback, useEffect, useState } from "react";
import { getInsights } from "@/lib/api";
import { Card, Eyebrow } from "@/components/ui";
import { OpsTabs } from "@/components/ops/ops-tabs";
import { titleCase } from "@/lib/format";
import type { Insights } from "@/lib/types";

export default function InsightsPage() {
  const [data, setData] = useState<Insights | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await getInsights());
    } catch {
      /* backend offline */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const agg = data?.aggregates;
  const empty = !agg || agg.total_conversations === 0;

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6">
      <div className="mb-3">
        <OpsTabs />
      </div>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <Eyebrow>Insights</Eyebrow>
          <h1 className="font-display text-[22px] font-600 text-text">What the data is telling you</h1>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="rounded-sm border border-border px-3 py-1.5 text-[13px] text-text-dim hover:text-text disabled:opacity-50"
        >
          {loading ? "Analyzing…" : "Regenerate"}
        </button>
      </div>

      {empty ? (
        <Card className="grid h-40 place-items-center text-[13px] text-text-dim">
          No conversations yet — run the simulation on the Console tab to generate insights.
        </Card>
      ) : (
        <>
          <p className="mb-4 max-w-[760px] text-[13px] text-text-dim">
            Each recommendation is generated from the aggregated numbers below — no figure is invented.
            The supporting metric is shown on every card so it's verifiable, not a black box.
          </p>

          {/* insight cards */}
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {data!.insights.map((c, i) => (
              <Card key={i} className="flex flex-col p-4">
                <div className="flex items-start justify-between gap-3">
                  <h3 className="font-display text-[15px] font-500 text-text">{c.title}</h3>
                </div>
                <p className="mt-2 flex-1 text-[13px] leading-relaxed text-text-dim">{c.recommendation}</p>
                <div className="mt-3 flex items-center gap-2 border-t border-border/60 pt-3">
                  <span className="eyebrow">{c.metric_label}</span>
                  <span
                    className="ml-auto rounded-sm px-2 py-0.5 font-mono text-[13px] font-500"
                    style={{ color: "var(--primary)", background: "var(--primary-tint)" }}
                  >
                    {c.metric_value}
                  </span>
                </div>
              </Card>
            ))}
          </div>

          {/* supporting aggregates */}
          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
            <AggBars title="Top ticket categories" rows={agg!.top_categories} accent="var(--primary)" />
            <AggBars title="Most-used tools" rows={agg!.most_used_tools} accent="var(--info)" />
            <AggBars title="Escalation reasons" rows={agg!.top_escalation_reasons} accent="var(--escalated)" />
          </div>
        </>
      )}
    </div>
  );
}

function AggBars({
  title,
  rows,
  accent,
}: {
  title: string;
  rows: { name: string; count: number }[];
  accent: string;
}) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <Card className="p-4">
      <Eyebrow>{title}</Eyebrow>
      <div className="mt-3 flex flex-col gap-2">
        {rows.length === 0 && <div className="text-[13px] text-text-faint">None recorded.</div>}
        {rows.map((r) => (
          <div key={r.name} className="flex items-center gap-2 text-[12px]">
            <span className="w-32 shrink-0 truncate text-text-dim" title={r.name}>
              {titleCase(r.name.slice(0, 40))}
            </span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
              <div className="h-full rounded-full" style={{ width: `${(r.count / max) * 100}%`, background: accent }} />
            </div>
            <span className="w-6 shrink-0 text-right font-mono text-text-faint">{r.count}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}
