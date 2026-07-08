"use client";

export interface Activity {
  label: string;
  done: boolean;
}

/**
 * Live "Agent activity" strip — the glass-box view in the customer chat.
 * Full list on wider screens; collapses to a single status line on mobile.
 * Iris pulse marks the in-progress step; done steps check off.
 */
export function ActivityStrip({ steps }: { steps: Activity[] }) {
  if (!steps.length) return null;
  const current = steps[steps.length - 1];

  return (
    <div
      className="animate-fade-slide rounded-lg border border-border px-3.5 py-2.5"
      style={{ background: "var(--surface)" }}
      role="status"
      aria-live="polite"
    >
      {/* mobile: single line */}
      <div className="flex items-center gap-2 sm:hidden">
        <span className="h-2 w-2 rounded-full animate-pulse-iris" style={{ background: "var(--primary)" }} />
        <span className="text-[13px] text-text-dim">{current.done ? "Finishing up…" : `${current.label}…`}</span>
      </div>

      {/* sm+: full checklist */}
      <div className="hidden flex-col gap-1.5 sm:flex">
        {steps.map((s, i) => (
          <div key={i} className="flex items-center gap-2 text-[13px]">
            {s.done ? (
              <span className="grid h-3.5 w-3.5 place-items-center rounded-full text-[9px] text-white" style={{ background: "var(--resolved)" }}>
                ✓
              </span>
            ) : (
              <span className="h-3.5 w-3.5 rounded-full border-2 animate-pulse-iris" style={{ borderColor: "var(--primary)" }} />
            )}
            <span style={{ color: s.done ? "var(--text-dim)" : "var(--text)" }}>{s.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
