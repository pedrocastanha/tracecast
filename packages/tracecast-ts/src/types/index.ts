export enum SpanType {
  LLM   = "llm",
  TOOL  = "tool",
  AGENT = "agent",
}

export interface Span {
  spanId: string;
  type: SpanType;
  name: string;
  startedAt: Date;
  finishedAt?: Date;
  model?: string;
  tokensIn?: number;
  tokensOut?: number;
  costUsd?: number;
  metadata?: Record<string, unknown>;
}

export interface Trace {
  traceId: string;
  name: string;
  startedAt: Date;
  finishedAt?: Date;
  sessionId?: string;
  userId?: string;
  projectId?: string;
  model?: string;
  totalTokensIn: number;
  totalTokensOut: number;
  totalTokens: number;
  costUsd: number;
  latencyMs?: number;
  toolsUsed: Record<string, number>;
  spans: Span[];
  metadata: Record<string, unknown>;
}
