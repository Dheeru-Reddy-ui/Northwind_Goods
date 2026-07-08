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

export interface Impact {
  total: number;
  assumptions: {
    human_cost_per_ticket: number;
    human_minutes_per_ticket: number;
    monthly_volume: number;
  };
  autonomous_resolution_rate: number;
  deflection_rate: number;
  avg_agent_minutes: number;
  avg_agent_cost: number;
  minutes_saved_per_ticket: number;
  cost_saved_per_ticket: number;
  total_cost_saved_window: number;
  projected_monthly_savings: number;
  projected_annual_savings: number;
  series: { i: number; resolution_rate: number; cost_usd: number }[];
  volume_by_channel: { channel: string; count: number }[];
  savings_curve: { volume: number; monthly_savings: number }[];
}

export interface InsightCard {
  title: string;
  recommendation: string;
  metric_label: string;
  metric_value: string;
}

export interface Insights {
  aggregates: {
    total_conversations: number;
    top_categories: { name: string; count: number }[];
    top_escalation_reasons: { name: string; count: number }[];
    most_used_tools: { name: string; count: number }[];
    weak_retrieval_questions: number;
    refused_or_blocked: number;
    escalations: number;
  };
  insights: InsightCard[];
}

export interface Dims {
  n?: number;
  resolution_success: number;
  policy_adherence: number;
  groundedness: number;
  tone: number;
  overall: number;
}

export interface RetrievalConfig {
  "recall@1": number;
  "recall@3": number;
  "recall@5": number;
  mrr: number;
  abstention: number;
}

export interface Report {
  scorecard: {
    total: number;
    created_at: string | null;
    metrics: {
      by_category: Record<string, Dims>;
      overall: Dims;
      ragas: { faithfulness: number; answer_relevance: number; context_precision: number };
      naive_overall: Dims | null;
    };
  } | null;
  retrieval: {
    n: number;
    n_off: number;
    vector_only: RetrievalConfig;
    hybrid_rrf: RetrievalConfig;
  } | null;
  reliability: {
    provider: string;
    n: number;
    off: { success_rate: number; pass_k: number; failure_modes: Record<string, number> };
    on: { success_rate: number; pass_k: number; failure_modes: Record<string, number> };
  } | null;
}
