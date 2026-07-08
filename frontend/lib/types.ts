export type Outcome = "resolved" | "escalated" | "pending_approval" | "open";

export interface Citation {
  source: string;
  section: string;
  snippet: string;
}

export interface ActionChip {
  type: string;
  label: string;
  detail?: Record<string, unknown>;
}

export interface ToolCall {
  tool: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
}

export interface PendingActionRef {
  id: string;
  action: string;
  order_id?: string;
  amount?: string;
  reason: string;
}

export interface EscalationRef {
  id: string;
  reason: string;
  summary: string;
}

export interface ChatResponse {
  session_id: string;
  conversation_id: string;
  reply: string;
  outcome: Outcome;
  tool_calls_made: ToolCall[];
  citations: Citation[];
  actions: ActionChip[];
  pending_actions: PendingActionRef[];
  escalations: EscalationRef[];
  cost_usd: number;
  duration_ms: number;
}

export interface ConversationSummary {
  id: string;
  session_id: string;
  channel: string;
  source: string;
  category: string | null;
  outcome: Outcome;
  cost_usd: number;
  duration_ms: number;
  judge_score: number | null;
  customer_email: string | null;
  preview: string;
  tool_count: number;
  step_count: number;
  created_at: string | null;
}

export interface TraceStep {
  idx: number;
  step_type: string;
  label: string;
  detail: Record<string, unknown> | null;
  latency_ms: number;
  cost_usd: number;
  tokens_in: number;
  tokens_out: number;
  created_at: string | null;
}

export interface ConversationDetail extends ConversationSummary {
  steps: TraceStep[];
}

export interface CategoryMetric {
  category: string;
  count: number;
  resolved: number;
  resolution_rate: number;
}

export interface Metrics {
  total: number;
  resolution_rate: number;
  escalation_rate: number;
  pending_rate: number;
  avg_judge_score: number | null;
  avg_cost_usd: number;
  avg_duration_ms: number;
  open_escalations: number;
  pending_approvals: number;
  by_category: CategoryMetric[];
  by_channel: { channel: string; count: number }[];
}

export interface PendingAction {
  id: string;
  action: string;
  args: Record<string, unknown>;
  reason: string;
  status: string;
  conversation_id: string | null;
  created_at: string | null;
}
