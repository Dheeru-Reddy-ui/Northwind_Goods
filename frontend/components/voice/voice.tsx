"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { voiceWsUrl } from "@/lib/api";
import { ActivityStrip, type Activity } from "@/components/chat/activity-strip";
import type { ChatResponse } from "@/lib/types";

type VoiceState = "idle" | "connecting" | "listening" | "thinking" | "speaking";
interface Turn {
  role: "user" | "agent";
  text: string;
}

const STATE_LABEL: Record<VoiceState, string> = {
  idle: "Tap to start a call",
  connecting: "Connecting…",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking…",
};

// iris for active listening/thinking, amber for speaking (in-progress output)
const STATE_COLOR: Record<VoiceState, string> = {
  idle: "var(--text-dim)",
  connecting: "var(--text-dim)",
  listening: "var(--primary)",
  thinking: "var(--primary)",
  speaking: "var(--accent)",
};

export function Voice() {
  const [state, setState] = useState<VoiceState>("idle");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [meta, setMeta] = useState<ChatResponse | null>(null);
  const [typed, setTyped] = useState("");
  const [sttSupported, setSttSupported] = useState(true);

  const wsRef = useRef<WebSocket | null>(null);
  const recRef = useRef<any>(null);
  const stateRef = useRef<VoiceState>("idle");
  const activeRef = useRef(false);
  const sttStartRef = useRef<number>(0);
  const rafRef = useRef<number>(0);
  const streamRef = useRef<MediaStream | null>(null);

  const setPhase = (s: VoiceState) => {
    stateRef.current = s;
    setState(s);
  };

  useEffect(() => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    setSttSupported(!!SR);
    return () => endCall();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- speech synthesis (TTS) ----
  const speak = useCallback((text: string) => {
    const synth = window.speechSynthesis;
    if (!synth) {
      setPhase("listening");
      restartRecognition();
      return;
    }
    synth.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.03;
    const t0 = performance.now();
    setPhase("speaking");
    u.onend = () => {
      wsRef.current?.send(JSON.stringify({ type: "tts_done", ms: Math.round(performance.now() - t0) }));
      if (activeRef.current) {
        setPhase("listening");
        restartRecognition();
      }
    };
    synth.speak(u);
  }, []);

  // ---- send a finalized utterance to the agent ----
  const sendUtterance = useCallback((text: string, sttMs: number) => {
    const clean = text.trim();
    if (!clean || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    setTurns((t) => [...t, { role: "user", text: clean }]);
    setActivity([]);
    setMeta(null);
    setPhase("thinking");
    wsRef.current.send(JSON.stringify({ type: "user_message", text: clean, stt_ms: sttMs }));
  }, []);

  // ---- speech recognition (STT) ----
  const restartRecognition = useCallback(() => {
    if (!activeRef.current || !recRef.current) return;
    try {
      recRef.current.start();
    } catch {
      /* already started */
    }
  }, []);

  const makeRecognition = useCallback(() => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) return null;
    const r = new SR();
    r.continuous = false;
    r.interimResults = true;
    r.lang = "en-US";
    r.onstart = () => {
      sttStartRef.current = performance.now();
    };
    r.onresult = (e: any) => {
      let finalText = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) finalText += e.results[i][0].transcript;
      }
      if (finalText.trim()) {
        const ms = Math.round(performance.now() - (sttStartRef.current || performance.now()));
        try {
          r.stop();
        } catch {
          /* noop */
        }
        sendUtterance(finalText, ms);
      }
    };
    r.onend = () => {
      if (stateRef.current === "listening" && activeRef.current) {
        try {
          r.start();
        } catch {
          /* noop */
        }
      }
    };
    r.onerror = () => {};
    return r;
  }, [sendUtterance]);

  // ---- barge-in: mic-level analyser cancels TTS when the user speaks ----
  const startAnalyser = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      streamRef.current = stream;
      const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
      const src = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      src.connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      let loud = 0;
      const tick = () => {
        analyser.getByteFrequencyData(data);
        const avg = data.reduce((a, b) => a + b, 0) / data.length;
        if (stateRef.current === "speaking") {
          if (avg > 30) {
            loud++;
            if (loud > 4) {
              bargeIn();
              loud = 0;
            }
          } else {
            loud = Math.max(0, loud - 1);
          }
        }
        rafRef.current = requestAnimationFrame(tick);
      };
      tick();
    } catch {
      /* mic denied — barge-in disabled, typed + recognition still work */
    }
  }, []);

  const bargeIn = useCallback(() => {
    window.speechSynthesis?.cancel();
    wsRef.current?.send(JSON.stringify({ type: "barge_in" }));
    setPhase("listening");
    restartRecognition();
  }, [restartRecognition]);

  // ---- call lifecycle ----
  const startCall = useCallback(() => {
    if (activeRef.current) return;
    activeRef.current = true;
    setTurns([]);
    setMeta(null);
    setActivity([]);
    setPhase("connecting");

    let attempt = 0;
    const open = () => {
      attempt += 1;
      setPhase("connecting");
      const ws = new WebSocket(voiceWsUrl());
      wsRef.current = ws;
      let opened = false;
      ws.onopen = () => {
        opened = true;
        setActivity([]);
        setPhase("listening");
        recRef.current = makeRecognition();
        restartRecognition();
        startAnalyser();
      };
      ws.onmessage = (e) => {
        const m = JSON.parse(e.data);
        if (m.type === "activity") {
          setActivity((prev) => {
            if (m.status === "active") return [...prev, { label: m.label, done: false }];
            const next = [...prev];
            for (let i = next.length - 1; i >= 0; i--) {
              if (next[i].label === m.label && !next[i].done) {
                next[i] = { ...next[i], done: true };
                break;
              }
            }
            return next;
          });
        } else if (m.type === "assistant_text") {
          setTurns((t) => [...t, { role: "agent", text: m.text }]);
          setActivity([]);
          speak(m.text);
        } else if (m.type === "done") {
          setMeta(m.result);
        } else if (m.type === "error") {
          setTurns((t) => [...t, { role: "agent", text: "Sorry, something went wrong." }]);
          setPhase("listening");
          restartRecognition();
        }
      };
      ws.onclose = () => {
        if (!activeRef.current) return;
        if (!opened && attempt < 4) {
          // free-tier cold start — the server is waking up; retry.
          setActivity([{ label: "Waking up the demo server…", done: false }]);
          setTimeout(() => {
            if (activeRef.current) open();
          }, 3000);
        } else {
          endCall();
        }
      };
      ws.onerror = () => {};
    };
    open();
  }, [makeRecognition, restartRecognition, speak, startAnalyser]);

  const endCall = useCallback(() => {
    activeRef.current = false;
    setPhase("idle");
    try {
      recRef.current?.stop();
    } catch {
      /* noop */
    }
    recRef.current = null;
    window.speechSynthesis?.cancel();
    cancelAnimationFrame(rafRef.current);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    wsRef.current?.close();
    wsRef.current = null;
  }, []);

  const active = state !== "idle";

  return (
    <div className="mx-auto flex min-h-[calc(100vh-57px)] max-w-[720px] flex-col items-center px-4 py-8">
      {/* orb + state */}
      <div className="flex flex-col items-center gap-4">
        <button
          onClick={active ? endCall : startCall}
          className="relative grid h-36 w-36 place-items-center rounded-full border-2 transition-transform active:scale-95"
          style={{
            borderColor: STATE_COLOR[state],
            background: "var(--surface)",
            boxShadow: active ? `0 0 40px -8px ${STATE_COLOR[state]}` : undefined,
          }}
          aria-label={active ? "End call" : "Start call"}
        >
          {state === "listening" || state === "speaking" ? (
            <Waveform color={STATE_COLOR[state]} />
          ) : (
            <span className="text-4xl" style={{ color: STATE_COLOR[state] }}>
              {active ? "■" : "🎙"}
            </span>
          )}
          {(state === "listening" || state === "thinking") && (
            <span
              className="absolute inset-0 rounded-full animate-pulse-iris"
              style={{ boxShadow: `0 0 0 2px ${STATE_COLOR[state]}`, opacity: 0.4 }}
            />
          )}
        </button>
        <div className="font-display text-[15px] font-500" style={{ color: STATE_COLOR[state] }}>
          {STATE_LABEL[state]}
        </div>
        {active && (
          <button onClick={endCall} className="text-[12px] text-text-dim underline-offset-2 hover:underline">
            End call
          </button>
        )}
        {!sttSupported && (
          <p className="max-w-[420px] text-center text-[12px] text-text-faint">
            Speech recognition isn't available in this browser — use the text box below to talk to the
            agent (it still runs the full voice pipeline and speaks back).
          </p>
        )}
      </div>

      {/* live activity */}
      {activity.length > 0 && (
        <div className="mt-5 w-full">
          <ActivityStrip steps={activity} />
        </div>
      )}

      {/* transcript */}
      <div className="mt-6 flex w-full flex-1 flex-col gap-3">
        {turns.map((t, i) => (
          <div key={i} className={t.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div
              className="max-w-[85%] rounded-lg px-3.5 py-2 text-[14px]"
              style={{
                background: t.role === "user" ? "var(--bubble-user)" : "var(--bubble-agent)",
                color: "var(--text)",
              }}
            >
              {t.text}
            </div>
          </div>
        ))}

        {meta && (meta.actions?.length || meta.pending_actions?.length || meta.escalations?.length || meta.citations?.length) ? (
          <div className="flex flex-col items-start gap-1.5">
            {meta.actions?.map((a, i) => (
              <span key={i} className="rounded-sm px-2.5 py-1 text-[12px] font-500"
                style={{ color: "var(--resolved)", background: "color-mix(in srgb, var(--resolved) 14%, transparent)" }}>
                ✓ {a.label}
              </span>
            ))}
            {meta.pending_actions?.map((p, i) => (
              <span key={`p${i}`} className="rounded-sm px-2.5 py-1 text-[12px] font-500"
                style={{ color: "var(--pending)", background: "color-mix(in srgb, var(--pending) 14%, transparent)" }}>
                ⏳ Awaiting approval · {p.amount}
              </span>
            ))}
            {meta.escalations?.map((e, i) => (
              <span key={i} className="rounded-sm px-2.5 py-1 text-[12px] font-500"
                style={{ color: "var(--escalated)", background: "color-mix(in srgb, var(--escalated) 12%, transparent)" }}>
                ▲ Escalated to a specialist
              </span>
            ))}
            {meta.conversation_id && (
              <Link href={`/ops?conversation=${meta.conversation_id}`} className="text-[12px]" style={{ color: "var(--primary)" }}>
                View this call in the dashboard →
              </Link>
            )}
          </div>
        ) : null}
      </div>

      {/* typed fallback — always available */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!active) startCall();
          // give the socket a moment to open on first send
          setTimeout(() => {
            sendUtterance(typed, 0);
            setTyped("");
          }, active ? 0 : 250);
        }}
        className="mt-4 flex w-full items-center gap-2"
      >
        <input
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          placeholder="…or type to talk (e.g. “where is my order ORD-00012?”)"
          className="flex-1 rounded-lg border border-border bg-surface px-3.5 py-2.5 text-[14px] text-text placeholder:text-text-faint focus:border-primary"
        />
        <button type="submit" disabled={!typed.trim()}
          className="rounded-lg px-4 py-2.5 text-[14px] font-500 text-white disabled:opacity-40"
          style={{ background: "var(--primary)" }}>
          Say it
        </button>
      </form>
    </div>
  );
}

function Waveform({ color }: { color: string }) {
  return (
    <div className="flex items-end gap-1" style={{ height: 40 }}>
      {[0, 1, 2, 3, 4].map((i) => (
        <span
          key={i}
          className="w-1.5 rounded-full"
          style={{
            background: color,
            height: 12,
            animation: `wf 0.9s ease-in-out ${i * 0.12}s infinite alternate`,
          }}
        />
      ))}
      <style>{`@keyframes wf { from { height: 8px } to { height: 34px } }`}</style>
    </div>
  );
}
