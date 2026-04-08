import { AsyncLocalStorage } from "async_hooks";
import { randomUUID } from "crypto";
import { Trace, Span, SpanType } from "../types";
import { BaseExporter } from "../exporters/base";
import { TraceCastLogger, LogFn } from "./logger";

interface TracerOptions {
  exporters?: BaseExporter[];
  
  failOnExportError?: boolean;
  
  logging?: boolean;
  
  logPrefix?: string;
  
  logFn?: LogFn;
  
  warnFn?: LogFn;
}

const storage = new AsyncLocalStorage<Trace>();

export class Tracer {
  private exporters: BaseExporter[];
  private failOnExportError: boolean;
  readonly _logger: TraceCastLogger | null;

  constructor(options: TracerOptions = {}) {
    this.exporters = options.exporters ?? [];
    this.failOnExportError = options.failOnExportError ?? false;
    this._logger = options.logging
      ? new TraceCastLogger(options.logPrefix, options.logFn, options.warnFn)
      : null;
  }

  async trace<T>(
    name: string,
    fn: (trace: Trace) => Promise<T>,
    opts: {
      sessionId?: string;
      userId?: string;
      projectId?: string;
      metadata?: Record<string, unknown>;
    } = {},
  ): Promise<T> {
    const trace: Trace = {
      traceId:        randomUUID(),
      name,
      startedAt:      new Date(),
      sessionId:      opts.sessionId,
      userId:         opts.userId,
      projectId:      opts.projectId,
      totalTokensIn:        0,
      totalTokensOut:       0,
      totalTokensInCached:  0,
      totalTokens:          0,
      costUsd:              0,
      toolsUsed:      {},
      spans:          [],
      metadata:       opts.metadata ?? {},
    };

    this._logger?.traceStart(name);

    let result: T;
    let userError: unknown;
    let hasError = false;

    try {
      result = await storage.run(trace, () => fn(trace));
    } catch (err) {
      userError = err;
      hasError = true;
    } finally {
      trace.finishedAt = new Date();
      if (hasError) {
        trace.metadata = {
          ...trace.metadata,
          _error: userError instanceof Error ? userError.message : String(userError),
        };
      }
      this._finalize(trace);
      this._logger?.traceEnd(name, {
        totalTokens: trace.totalTokens,
        costUsd:     trace.costUsd,
        latencyMs:   trace.latencyMs,
        toolsUsed:   trace.toolsUsed,
      });
      await this._safeExport(trace);
    }

    if (hasError) throw userError;
    return result!;
  }

  currentTrace(): Trace | null {
    return storage.getStore() ?? null;
  }

  addSpan(span: Span): void {
    const trace = this.currentTrace();
    if (trace) trace.spans.push(span);
  }

  private async _safeExport(trace: Trace): Promise<void> {
    for (const exporter of this.exporters) {
      try {
        await exporter.export(trace);
      } catch (err) {
        if (this.failOnExportError) throw err;
        console.warn(
          `[TraceCast] Exporter ${exporter.constructor?.name ?? "unknown"} failed:`,
          err,
        );
      }
    }
  }

  private _finalize(trace: Trace): void {
    trace.totalTokensIn        = trace.spans.reduce((s, sp) => s + (sp.tokensIn        ?? 0), 0);
    trace.totalTokensOut       = trace.spans.reduce((s, sp) => s + (sp.tokensOut       ?? 0), 0);
    trace.totalTokensInCached  = trace.spans.reduce((s, sp) => s + (sp.tokensInCached  ?? 0), 0);
    trace.totalTokens          = trace.totalTokensIn + trace.totalTokensOut;
    trace.costUsd              = trace.spans.reduce((s, sp) => s + (sp.costUsd         ?? 0), 0);

    if (trace.finishedAt) {
      trace.latencyMs = trace.finishedAt.getTime() - trace.startedAt.getTime();
    }

    const llmSpans = trace.spans.filter((s) => s.type === SpanType.LLM && s.model);
    if (llmSpans.length) {
      trace.model = llmSpans.reduce((a, b) =>
        ((a.tokensIn ?? 0) + (a.tokensOut ?? 0)) >= ((b.tokensIn ?? 0) + (b.tokensOut ?? 0)) ? a : b
      ).model;
    }

    trace.toolsUsed = {};
    for (const span of trace.spans) {
      if (span.type === SpanType.TOOL) {
        trace.toolsUsed[span.name] = (trace.toolsUsed[span.name] ?? 0) + 1;
      }
    }
  }
}
