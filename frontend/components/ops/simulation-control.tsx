"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { resetDemo, simulateStreamUrl } from "@/lib/api";

interface Progress {
  index: number;
  total: number;
  counts: { resolved?: number; escalated?: number; pending_approval?: number };
}

export function SimulationControl({
  autoStart,
  onTick,
  onDone,
}: {
  autoStart: boolean;
  onTick: () => void;
  onDone: () => void;
}) {
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<Progress | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const started = useRef(false);

  const run = useCallback(() => {
    if (esRef.current) return;
    setRunning(true);
    setProgress(null);
    const es = new EventSource(simulateStreamUrl(50));
    esRef.current = es;
    es.addEventListener("ticket", (e) => {
      const d = JSON.parse((e as MessageEvent).data) as Progress;
      setProgress(d);
      onTick();
    });
    es.addEventListener("done", () => {
      es.close();
      esRef.current = null;
      setRunning(false);
      onDone();
    });
    es.onerror = () => {
      es.close();
      esRef.current = null;
      setRunning(false);
    };
  }, [onTick, onDone]);

  useEffect(() => {
    if (autoStart && !started.current) {
      started.current = true;
      run();
    }
    return () => esRef.current?.close();
  }, [autoStart, run]);

  async function reset() {
    await resetDemo();
    setProgress(null);
    onDone();
  }

  const c = progress?.counts || {};
  const pctDone = progress ? (progress.index / progress.total) * 100 : 0;

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <div className="flex gap-2">
        <button
          onClick={run}
          disabled={running}
          className="rounded-sm px-3.5 py-1.5 text-[13px] font-500 text-white transition-colors disabled:opacity-60"
          style={{ background: "var(--primary)" }}
        >
          {running ? "Running…" : "Run simulation"}
        </button>
        <button
          onClick={reset}
          disabled={running}
          className="rounded-sm border border-border px-3 py-1.5 text-[13px] text-text-dim hover:text-text disabled:opacity-50"
        >
          Reset demo
        </button>
      </div>

      {progress && (
        <div className="flex min-w-[240px] flex-1 items-center gap-3">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
            <div
              className="h-full rounded-full transition-[width] duration-200"
              style={{ width: `${pctDone}%`, background: running ? "var(--accent)" : "var(--resolved)" }}
            />
          </div>
          <div className="whitespace-nowrap font-mono text-[11px] text-text-dim">
            {progress.index}/{progress.total} · <span style={{ color: "var(--resolved)" }}>{c.resolved || 0}✓</span>{" "}
            <span style={{ color: "var(--escalated)" }}>{c.escalated || 0}▲</span>{" "}
            <span style={{ color: "var(--pending)" }}>{c.pending_approval || 0}⏳</span>
          </div>
        </div>
      )}
    </div>
  );
}
