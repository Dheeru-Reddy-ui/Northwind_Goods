"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getImpact } from "@/lib/api";
import { Card, Eyebrow } from "@/components/ui";
import { OpsTabs } from "@/components/ops/ops-tabs";
import { pct, usd } from "@/lib/format";
import type { Impact } from "@/lib/types";

const tooltipStyle = {
  background: "var(--surface-2)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  fontSize: 12,
  color: "var(--text)",
};

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="p-4">
      <Eyebrow>{title}</Eyebrow>
      <div className="mt-3 h-[180px]">{children}</div>
    </Card>
  );
}

function AssumptionInput({
  label,
  value,
  onChange,
  prefix,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  prefix?: string;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="eyebrow">{label}</span>
      <div className="flex items-center rounded-sm border border-border bg-surface px-2.5">
        {prefix && <span className="text-[13px] text-text-dim">{prefix}</span>}
        <input
          type="number"
          value={value}
          onChange={(e) => onChange(Number(e.target.value) || 0)}
          className="w-full bg-transparent py-1.5 font-mono text-[14px] text-text focus:outline-none"
        />
      </div>
    </label>
  );
}

export default function ImpactPage() {
  const [volume, setVolume] = useState(8000);
  const [cost, setCost] = useState(6.5);
  const [minutes, setMinutes] = useState(6);
  const [data, setData] = useState<Impact | null>(null);

  const load = useCallback(async () => {
    try {
      setData(
        await getImpact({
          monthly_volume: volume,
          human_cost_per_ticket: cost,
          human_minutes_per_ticket: minutes,
        })
      );
    } catch {
      /* backend offline */
    }
  }, [volume, cost, minutes]);

  useEffect(() => {
    const t = setTimeout(load, 200);
    return () => clearTimeout(t);
  }, [load]);

  const empty = !data || data.total === 0;

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6">
      <div className="mb-3">
        <OpsTabs />
      </div>
      <div className="mb-4">
        <Eyebrow>Impact</Eyebrow>
        <h1 className="font-display text-[22px] font-600 text-text">Return on automation</h1>
      </div>

      {empty ? (
        <Card className="grid h-40 place-items-center text-[13px] text-text-dim">
          No conversations yet — run the simulation on the Console tab to populate the ROI model.
        </Card>
      ) : (
        <>
          {/* assumptions */}
          <Card className="mb-4 p-4">
            <Eyebrow>Business assumptions — edit to recompute live</Eyebrow>
            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
              <AssumptionInput label="Monthly ticket volume" value={volume} onChange={setVolume} />
              <AssumptionInput label="Human cost / ticket" value={cost} onChange={setCost} prefix="$" />
              <AssumptionInput label="Human minutes / ticket" value={minutes} onChange={setMinutes} />
            </div>
          </Card>

          {/* headline numbers */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Headline value={pct(data!.autonomous_resolution_rate)} label="resolved autonomously" accent="var(--resolved)" />
            <Headline value={`${data!.minutes_saved_per_ticket}m`} label="saved per ticket" accent="var(--info)" />
            <Headline
              value={usd(data!.projected_monthly_savings)}
              label={`/mo saved at ${data!.assumptions.monthly_volume.toLocaleString()} tickets`}
              accent="var(--primary)"
            />
            <Headline value={usd(data!.projected_annual_savings)} label="projected annual savings" accent="var(--accent)" />
          </div>

          {/* charts */}
          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <ChartCard title="Resolution rate (rolling, over conversations)">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data!.series} margin={{ top: 6, right: 8, bottom: 0, left: -18 }}>
                  <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="i" tick={{ fill: "var(--text-faint)", fontSize: 11 }} stroke="var(--border)" />
                  <YAxis domain={[0, 1]} tick={{ fill: "var(--text-faint)", fontSize: 11 }} stroke="var(--border)" />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => pct(v)} />
                  <Line type="monotone" dataKey="resolution_rate" stroke="var(--resolved)" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard title="Cost per conversation (USD)">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data!.series} margin={{ top: 6, right: 8, bottom: 0, left: -8 }}>
                  <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="i" tick={{ fill: "var(--text-faint)", fontSize: 11 }} stroke="var(--border)" />
                  <YAxis tick={{ fill: "var(--text-faint)", fontSize: 11 }} stroke="var(--border)" />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => usd(v)} />
                  <Line type="monotone" dataKey="cost_usd" stroke="var(--info)" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard title="Projected monthly savings at scale">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data!.savings_curve} margin={{ top: 6, right: 8, bottom: 0, left: 6 }}>
                  <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="volume" tick={{ fill: "var(--text-faint)", fontSize: 11 }} stroke="var(--border)"
                    tickFormatter={(v: number) => `${v / 1000}k`} />
                  <YAxis tick={{ fill: "var(--text-faint)", fontSize: 11 }} stroke="var(--border)"
                    tickFormatter={(v: number) => `$${Math.round(v / 1000)}k`} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => usd(v)}
                    labelFormatter={(l) => `${Number(l).toLocaleString()} tickets/mo`} />
                  <Bar dataKey="monthly_savings" fill="var(--primary)" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            <Card className="p-4">
              <Eyebrow>Model breakdown</Eyebrow>
              <dl className="mt-3 flex flex-col gap-2 text-[13px]">
                <Row k="Deflection (no human)" v={pct(data!.deflection_rate)} />
                <Row k="Avg agent handle time" v={`${(data!.avg_agent_minutes * 60).toFixed(1)}s`} />
                <Row k="Avg agent cost / ticket" v={usd(data!.avg_agent_cost)} />
                <Row k="Cost saved / deflected ticket" v={usd(data!.cost_saved_per_ticket)} />
                <Row k="Saved so far (this window)" v={usd(data!.total_cost_saved_window)} />
              </dl>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function Headline({ value, label, accent }: { value: string; label: string; accent: string }) {
  return (
    <Card className="relative overflow-hidden p-4">
      <div className="font-display text-[26px] font-600 leading-tight text-text">{value}</div>
      <div className="mt-1 text-[13px] text-text-dim">{label}</div>
      <div className="absolute inset-x-0 bottom-0 h-[3px]" style={{ background: accent, opacity: 0.7 }} />
    </Card>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between border-b border-border/50 pb-1.5">
      <span className="text-text-dim">{k}</span>
      <span className="font-mono text-text">{v}</span>
    </div>
  );
}
