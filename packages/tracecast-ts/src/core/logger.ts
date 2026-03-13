

export type LogFn = (msg: string) => void;


function inline(text: string, maxChars = 120): string {
  const normalized = text.replace(/[\r\n\t]+/g, " ").replace(/ {2,}/g, " ").trim();
  return normalized.length > maxChars ? normalized.slice(0, maxChars) + "..." : normalized;
}

export class TraceCastLogger {
  private readonly prefix: string | undefined;
  private readonly logFn: LogFn;
  private readonly warnFn: LogFn;

  constructor(prefix?: string, logFn?: LogFn, warnFn?: LogFn) {
    this.prefix  = prefix;
    this.logFn   = logFn  ?? ((msg) => console.log(msg));
    this.warnFn  = warnFn ?? ((msg) => console.warn(msg));
  }

  private fmt(traceName: string, msg: string): string {
    return `[${this.prefix ?? traceName}] ${msg}`;
  }

  traceStart(traceName: string): void {
    this.logFn(this.fmt(traceName, "Trace started"));
  }

  traceEnd(
    traceName: string,
    opts: {
      totalTokens: number;
      costUsd: number;
      latencyMs?: number;
      toolsUsed: Record<string, number>;
    },
  ): void {
    const latency = opts.latencyMs != null ? `${(opts.latencyMs / 1000).toFixed(2)}s` : "n/a";
    const toolEntries = Object.entries(opts.toolsUsed);
    const toolsStr = toolEntries.length
      ? " | tools: " + toolEntries.map(([k, v]) => `${k}×${v}`).join(", ")
      : "";
    this.logFn(
      this.fmt(
        traceName,
        `Trace finished → total: ${opts.totalTokens} tokens | $${opts.costUsd.toFixed(4)} | ${latency}${toolsStr}`,
      ),
    );
  }

  llmStart(traceName: string, model: string): void {
    this.logFn(this.fmt(traceName, `LLM started → ${model}`));
  }

  llmEnd(
    traceName: string,
    opts: { model: string; tokensIn: number; tokensOut: number; costUsd: number; latencyMs?: number },
  ): void {
    const latency = opts.latencyMs != null ? `${(opts.latencyMs / 1000).toFixed(2)}s` : "n/a";
    this.logFn(
      this.fmt(
        traceName,
        `LLM end → ${opts.model} | tokens: ${opts.tokensIn} in / ${opts.tokensOut} out | $${opts.costUsd.toFixed(4)} | ${latency}`,
      ),
    );
  }

  llmError(traceName: string, model: string, error: string): void {
    this.warnFn(this.fmt(traceName, `LLM error → ${model} | ⚠ ${inline(error)}`));
  }

  toolStart(traceName: string, name: string, inputStr: string): void {
    this.logFn(this.fmt(traceName, `Tool call → ${name} | ${inline(inputStr, 80)}`));
  }

  toolEnd(traceName: string, name: string, latencyMs?: number): void {
    const latency = latencyMs != null ? `${(latencyMs / 1000).toFixed(2)}s` : "n/a";
    this.logFn(this.fmt(traceName, `Tool end → ${name} | ${latency}`));
  }

  toolError(traceName: string, name: string, error: string): void {
    this.warnFn(this.fmt(traceName, `Tool error → ${name} | ⚠ ${inline(error)}`));
  }

  chainStart(traceName: string, name: string): void {
    this.logFn(this.fmt(traceName, `Chain → ${name}`));
  }

  chainError(traceName: string, name: string, error: string): void {
    this.warnFn(this.fmt(traceName, `Chain error → ${name} | ⚠ ${inline(error)}`));
  }
}
