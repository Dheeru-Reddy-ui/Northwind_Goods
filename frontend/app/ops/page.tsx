"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  getConversation,
  getMetrics,
  listConversations,
  listPending,
} from "@/lib/api";
import { MetricCard } from "@/components/ops/metric-card";
import { ConversationsTable } from "@/components/ops/conversations-table";
import { TraceTimeline } from "@/components/ops/trace-timeline";
import { PendingApprovals } from "@/components/ops/pending-approvals";
import { SimulationControl } from "@/components/ops/simulation-control";
import { OpsTabs } from "@/components/ops/ops-tabs";
import { Card, Eyebrow } from "@/components/ui";
import type {
  ConversationDetail,
  ConversationSummary,
  Metrics,
  PendingAction,
} from "@/lib/types";

export default function OpsPage() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [rows, setRows] = useState<ConversationSummary[]>([]);
  const [pending, setPending] = useState<PendingAction[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [autoRun, setAutoRun] = useState(false);
  const didInit = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const [m, c, p] = await Promise.all([getMetrics(), listConversations({ limit: 60 }), listPending()]);
      setMetrics(m);
      setRows(c.conversations);
      setPending(p);
    } catch (e) {
      /* backend offline — cards show zeros */
    }
  }, []);

  const select = useCallback(async (id: string) => {
    setSelectedId(id);
    setLoadingDetail(true);
    try {
      setDetail(await getConversation(id));
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    if (didInit.current) return;
    didInit.current = true;
    refresh();
    const params = new URLSearchParams(window.location.search);
    const cid = params.get("conversation");
    if (cid) select(cid);
    if (params.get("run") === "1") setAutoRun(true);
  }, [refresh, select]);

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6">
      <div className="mb-3">
        <OpsTabs />
      </div>
      {/* control bar */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <Eyebrow>Ops console</Eyebrow>
          <h1 className="font-display text-[22px] font-600 text-text">Autonomous support</h1>
        </div>
        <SimulationControl autoStart={autoRun} onTick={refresh} onDone={refresh} />
      </div>

      {/* metric cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <MetricCard label="Resolution rate" value={metrics?.resolution_rate ?? 0} format="percent" accent="var(--resolved)" />
        <MetricCard label="Escalation rate" value={metrics?.escalation_rate ?? 0} format="percent" accent="var(--escalated)" />
        <MetricCard label="Judge score" value={metrics?.avg_judge_score ?? 0} format="raw" suffix="/5" accent="var(--primary)" />
        <MetricCard label="Avg cost" value={metrics?.avg_cost_usd ?? 0} format="usd" accent="var(--info)" />
        <MetricCard label="Avg latency" value={metrics?.avg_duration_ms ?? 0} suffix="ms" accent="var(--accent)" />
        <MetricCard label="Conversations" value={metrics?.total ?? 0} accent="var(--text-dim)" />
      </div>

      {/* two-pane split */}
      <div className="mt-4 grid gap-4 lg:grid-cols-[1.05fr,1fr]">
        <div className="flex flex-col gap-4">
          <Card className="overflow-hidden">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <Eyebrow>Conversations</Eyebrow>
              <span className="font-mono text-[11px] text-text-dim">{rows.length}</span>
            </div>
            <div className="max-h-[440px] overflow-y-auto">
              <ConversationsTable rows={rows} selectedId={selectedId} onSelect={select} />
            </div>
          </Card>
          <PendingApprovals items={pending} onResolved={refresh} />
        </div>

        <Card className="min-h-[540px] overflow-hidden">
          <div className="flex items-center gap-2 border-b border-border px-4 py-3">
            <Eyebrow>Agent trace timeline</Eyebrow>
            <span className="ml-auto font-mono text-[10px] text-text-faint">signature view</span>
          </div>
          <div className="h-[calc(100%-49px)]">
            <TraceTimeline detail={detail} loading={loadingDetail} />
          </div>
        </Card>
      </div>

      {/* category breakdown */}
      {metrics && metrics.by_category.length > 0 && (
        <Card className="mt-4 p-4">
          <Eyebrow>Resolution by category</Eyebrow>
          <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3 lg:grid-cols-4">
            {metrics.by_category.map((c) => (
              <div key={c.category} className="flex items-center gap-2">
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${c.resolution_rate * 100}%`, background: "var(--resolved)" }}
                  />
                </div>
                <span className="w-28 shrink-0 truncate text-[12px] text-text-dim">
                  {c.category.replace(/_/g, " ")}
                </span>
                <span className="font-mono text-[11px] text-text-faint">{c.count}</span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
