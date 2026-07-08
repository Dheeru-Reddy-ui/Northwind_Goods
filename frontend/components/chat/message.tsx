import Link from "next/link";
import clsx from "clsx";
import type { ChatResponse, Citation } from "@/lib/types";

export interface ChatMessage {
  role: "user" | "agent";
  text: string;
  meta?: ChatResponse;
}

function Citations({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null;
  return (
    <div className="mt-2 flex flex-col gap-1.5">
      {citations.map((c, i) => (
        <div
          key={i}
          className="rounded-sm bg-surface px-3 py-2 text-[12px]"
          style={{ borderLeft: "2px solid var(--info)" }}
        >
          <div className="font-mono text-[11px]" style={{ color: "var(--info)" }}>
            {c.source}
            {c.section ? ` › ${c.section}` : ""}
          </div>
          <div className="mt-0.5 line-clamp-2 text-text-dim">{c.snippet}</div>
        </div>
      ))}
    </div>
  );
}

function ActionChips({ meta }: { meta: ChatResponse }) {
  const chips = meta.actions || [];
  const pend = meta.pending_actions || [];
  if (!chips.length && !pend.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {chips.map((a, i) => (
        <span
          key={`a${i}`}
          className="inline-flex items-center gap-1.5 rounded-sm px-2.5 py-1 text-[12px] font-500"
          style={{ color: "var(--resolved)", background: "color-mix(in srgb, var(--resolved) 14%, transparent)" }}
        >
          ✓ {a.label}
        </span>
      ))}
      {pend.map((p, i) => (
        <span
          key={`p${i}`}
          className="inline-flex items-center gap-1.5 rounded-sm px-2.5 py-1 text-[12px] font-500"
          style={{ color: "var(--pending)", background: "color-mix(in srgb, var(--pending) 14%, transparent)" }}
        >
          ⏳ Awaiting approval · {p.amount}
        </span>
      ))}
    </div>
  );
}

function EscalationCard({ meta }: { meta: ChatResponse }) {
  if (!meta.escalations?.length) return null;
  const e = meta.escalations[0];
  return (
    <div
      className="mt-2 rounded-sm px-3 py-2.5 text-[12px]"
      style={{ background: "color-mix(in srgb, var(--escalated) 10%, transparent)", borderLeft: "2px solid var(--escalated)" }}
    >
      <div className="font-500" style={{ color: "var(--escalated)" }}>
        ▲ Escalated to a human specialist
      </div>
      <div className="mt-1 text-text-dim">{e.summary}</div>
    </div>
  );
}

export function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  const meta = msg.meta;
  const deepLink =
    meta && meta.conversation_id && meta.outcome !== "open"
      ? `/ops?conversation=${meta.conversation_id}`
      : null;

  return (
    <div className={clsx("flex animate-fade-slide", isUser ? "justify-end" : "justify-start")}>
      <div className={clsx("max-w-[85%]", isUser && "items-end")}>
        <div
          className={clsx("whitespace-pre-wrap rounded-lg px-4 py-2.5 text-[14px] leading-relaxed")}
          style={{
            background: isUser ? "var(--bubble-user)" : "var(--bubble-agent)",
            color: "var(--text)",
            borderTopRightRadius: isUser ? 4 : undefined,
            borderTopLeftRadius: isUser ? undefined : 4,
          }}
        >
          {msg.text}
        </div>

        {meta && !isUser && (
          <>
            <Citations citations={meta.citations || []} />
            <ActionChips meta={meta} />
            <EscalationCard meta={meta} />
            {deepLink && (
              <Link
                href={deepLink}
                className="mt-2 inline-flex items-center gap-1 text-[12px] transition-colors hover:underline"
                style={{ color: "var(--primary)" }}
              >
                View this conversation in the dashboard →
              </Link>
            )}
          </>
        )}
      </div>
    </div>
  );
}
