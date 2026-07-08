import type {
  ChatResponse,
  ConversationDetail,
  ConversationSummary,
  Metrics,
  PendingAction,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

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

export function simulateStreamUrl(limit = 20) {
  return `${API_BASE}/simulate/stream?limit=${limit}`;
}
