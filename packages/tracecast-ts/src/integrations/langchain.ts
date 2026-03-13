import { Tracer } from "../core/tracer";
import { TraceCastLogger } from "../core/logger";
import { Span, SpanType } from "../types";
import { calculateCost } from "../core/costCalculator";


export class TraceCastCallback {
  readonly name = "TraceCastCallback";
  private spans = new Map<string, Span>();
  private readonly logger: TraceCastLogger | null;

  constructor(private tracer: Tracer) {
    this.logger = tracer._logger ?? null;
  }


  private traceName(): string {
    return this.tracer.currentTrace()?.name ?? "tracecast";
  }

  private elapsedMs(span: Span): number | undefined {
    if (span.finishedAt && span.startedAt) {
      return span.finishedAt.getTime() - span.startedAt.getTime();
    }
    return undefined;
  }


  async handleLLMStart(serialized: Record<string, any>, _prompts: string[], runId: string): Promise<void> {
    const model: string =
      serialized?.kwargs?.model_name ??
      serialized?.kwargs?.model ??
      serialized?.name ??
      "unknown";
    this.spans.set(runId, {
      spanId: runId,
      type: SpanType.LLM,
      name: `llm:${model}`,
      model,
      startedAt: new Date(),
    });
    this.logger?.llmStart(this.traceName(), model);
  }

  async handleLLMEnd(output: Record<string, any>, runId: string): Promise<void> {
    const span = this.spans.get(runId);
    if (!span) return;
    this.spans.delete(runId);

    span.finishedAt = new Date();
    const usage = output?.llmOutput?.tokenUsage ?? output?.llmOutput?.usage ?? {};
    const tokensIn  = usage.promptTokens     ?? usage.input_tokens  ?? 0;
    const tokensOut = usage.completionTokens ?? usage.output_tokens ?? 0;
    span.tokensIn  = tokensIn;
    span.tokensOut = tokensOut;
    span.costUsd = calculateCost(span.model!, tokensIn, tokensOut);
    this.tracer.currentTrace()?.spans.push(span);

    this.logger?.llmEnd(this.traceName(), {
      model:     span.model!,
      tokensIn,
      tokensOut,
      costUsd:   span.costUsd,
      latencyMs: this.elapsedMs(span),
    });
  }

  async handleLLMError(err: Error, runId: string): Promise<void> {
    const span = this.spans.get(runId);
    if (span) this.logger?.llmError(this.traceName(), span.model ?? "unknown", err.message);
    this._closeSpanWithError(runId, err);
  }


  async handleToolStart(serialized: Record<string, any>, input: string, runId: string): Promise<void> {
    const name: string = serialized?.name ?? "unknown_tool";
    this.spans.set(runId, {
      spanId: runId,
      type: SpanType.TOOL,
      name,
      startedAt: new Date(),
    });
    this.logger?.toolStart(this.traceName(), name, input);
  }

  async handleToolEnd(output: string, runId: string): Promise<void> {
    const span = this.spans.get(runId);
    if (!span) return;
    this.spans.delete(runId);
    span.finishedAt = new Date();
    this.tracer.currentTrace()?.spans.push(span);
    this.logger?.toolEnd(this.traceName(), span.name, this.elapsedMs(span));
  }

  async handleToolError(err: Error, runId: string): Promise<void> {
    const span = this.spans.get(runId);
    if (span) this.logger?.toolError(this.traceName(), span.name, err.message);
    this._closeSpanWithError(runId, err);
  }


  async handleChainStart(
    serialized: Record<string, any>,
    _inputs: Record<string, any>,
    runId: string,
    parentRunId?: string,
  ): Promise<void> {
    const name: string = serialized?.id?.at(-1) ?? serialized?.name ?? "chain";
    this.spans.set(runId, {
      spanId: runId,
      type: SpanType.AGENT,
      name: `chain:${name}`,
      startedAt: new Date(),
    });
    if (!parentRunId) {
      this.logger?.chainStart(this.traceName(), name);
    }
  }

  async handleChainEnd(_outputs: Record<string, any>, runId: string): Promise<void> {
    const span = this.spans.get(runId);
    if (!span) return;
    this.spans.delete(runId);
    span.finishedAt = new Date();
    this.tracer.currentTrace()?.spans.push(span);
  }

  async handleChainError(err: Error, runId: string): Promise<void> {
    const span = this.spans.get(runId);
    if (span) this.logger?.chainError(this.traceName(), span.name, err.message);
    this._closeSpanWithError(runId, err);
  }


  private _closeSpanWithError(runId: string, err: Error): void {
    const span = this.spans.get(runId);
    if (!span) return;
    this.spans.delete(runId);
    span.finishedAt = new Date();
    span.metadata = { ...span.metadata, _error: err.message };
    this.tracer.currentTrace()?.spans.push(span);
  }
}
