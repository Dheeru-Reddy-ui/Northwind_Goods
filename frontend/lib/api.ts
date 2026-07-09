import type {
  ChatResponse,
  ConversationDetail,
  ConversationSummary,
  Impact,
  Insights,
  Metrics,
  PendingAction,
  Report,
} from "./types";

// Normalize: a bare host (e.g. from Render's fromService) gets an https:// scheme.
const _rawBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
export const API_BASE = /^https?:\/\//.test(_rawBase) ? _rawBase : `https://${_rawBase}`;

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${path}: ${body}`);
  }
  return res.json();
}

/** Fire-and-forget ping to start waking a sleeping free-tier backend. */
export function warmBackend(): void {
  fetch(`${API_BASE}/health`, { cache: "no-store" }).catch(() => {});
}

export function sendChat(message: string, sessionId: string | null, channel = "chat") {
  return j<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({ message, session_id: sessionId, channel }),
  });
}

export function getMetrics(hours = 720) {
  return j<Metrics>(`/observability/metrics?hours=${hours}`);
}

export function listConversations(params: {
  limit?: number;
  offset?: number;
  outcome?: string;
  channel?: string;
  source?: string;
} = {}) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v != null && q.set(k, String(v)));
  return j<{ total: number; conversations: ConversationSummary[] }>(
    `/observability/conversations?${q.toString()}`
  );
}

export function getConversation(id: string) {
  return j<ConversationDetail>(`/observability/conversations/${id}`);
}

export function listPending() {
  return j<PendingAction[]>("/actions/pending");
}

export function approveAction(id: string) {
  return j<{ status: string }>(`/actions/${id}/approve`, { method: "POST" });
}

export function rejectAction(id: string) {
  return j<{ status: string }>(`/actions/${id}/reject`, { method: "POST" });
}

export function resetDemo() {
  return j<{ cleared: number }>("/observability/reset", { method: "POST" });
}

export function getImpact(params: {
  monthly_volume?: number;
  human_cost_per_ticket?: number;
  human_minutes_per_ticket?: number;
} = {}) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v != null && q.set(k, String(v)));
  return j<Impact>(`/observability/impact?${q.toString()}`);
}

export function getInsights() {
  return j<Insights>("/observability/insights");
}

export function getReport() {
  return j<Report>("/observability/report");
}

export function voiceWsUrl(): string {
  return API_BASE.replace(/^http/, "ws") + "/voice/ws";
}

export function getVoiceConfig() {
  return j<{ stt: string; tts: string; server_audio: boolean }>("/voice/config");
}

export function simulateStreamUrl(limit = 20) {
  return `${API_BASE}/simulate/stream?limit=${limit}`;
}

export interface StreamHandlers {
  onActivity: (a: { label: string; status: "active" | "done" }) => void;
  onToken: (t: string) => void;
  onDone: (r: ChatResponse & { session_id: string }) => void;
  onError: () => void;
}

/** Open a streaming chat turn over SSE. Returns a function to close the stream. */
export function streamChat(
  message: string,
  sessionId: string | null,
  h: StreamHandlers
): () => void {
  const q = new URLSearchParams({ message });
  if (sessionId) q.set("session_id", sessionId);
  const es = new EventSource(`${API_BASE}/chat/stream?${q.toString()}`);
  let finished = false;

  es.addEventListener("activity", (e) => h.onActivity(JSON.parse((e as MessageEvent).data)));
  es.addEventListener("token", (e) => h.onToken(JSON.parse((e as MessageEvent).data).t));
  es.addEventListener("done", (e) => {
    finished = true;
    h.onDone(JSON.parse((e as MessageEvent).data));
    es.close();
  });
  es.addEventListener("failed", () => {
    finished = true;
    h.onError();
    es.close();
  });
  es.onerror = () => {
    if (!finished) {
      finished = true;
      h.onError();
      es.close();
    }
  };
  return () => es.close();
}
