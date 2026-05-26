import { Tracer, getCurrentTrace } from "../core/tracer";
import { Span, SpanType } from "../types";
import { calculateCost } from "../core/costCalculator";
import { randomUUID } from "crypto";

let _defaultTracer: Tracer | null = null;

export function setDefaultTracer(tracer: Tracer): void {
  _defaultTracer = tracer;
}

export function getDefaultTracer(): Tracer | null {
  return _defaultTracer;
}

function resolveTracer(): Tracer {
  return _defaultTracer ?? new Tracer();
}

function extractTokens(response: any, provider: string): { input: number; output: number; cached: number } {
  if (provider === "openai") {
    const usage = response?.usage ?? {};
    const details = usage?.prompt_tokens_details ?? {};
    return {
      input: usage?.prompt_tokens ?? 0,
      output: usage?.completion_tokens ?? 0,
      cached: details?.cached_tokens ?? 0,
    };
  }
  if (provider === "anthropic") {
    const usage = response?.usage ?? {};
    return {
      input: usage?.input_tokens ?? 0,
      output: usage?.output_tokens ?? 0,
      cached: usage?.cache_read_input_tokens ?? 0,
    };
  }
  return { input: 0, output: 0, cached: 0 };
}

function extractContent(response: any, provider: string): string | undefined {
  if (provider === "openai") {
    try {
      const choices = response?.choices ?? [];
      if (choices.length) {
        const msg = choices[0]?.message;
        if (msg) return msg.content ?? msg.reasoning_content ?? "";
      }
    } catch { return undefined; }
  }
  if (provider === "anthropic") {
    try {
      const content = response?.content ?? [];
      const texts: string[] = [];
      for (const block of content) {
        if (block?.type === "text") texts.push(block.text ?? "");
        else if (block?.type === "thinking") texts.push(`[thinking] ${block.thinking ?? ""}`);
      }
      return texts.length ? texts.join("") : undefined;
    } catch { return undefined; }
  }
  return undefined;
}

function extractInputText(kwargs: Record<string, any>): string | undefined {
  const messages = kwargs?.messages as any[] | undefined;
  if (messages?.length) {
    const last = messages[messages.length - 1];
    if (last?.content) return String(last.content);
  }
  return undefined;
}

export async function traceLLMCall<T>(
  fn: () => Promise<T>,
  opts: {
    provider: string;
    model: string;
    inputText?: string;
    metadata?: Record<string, unknown>;
  },
): Promise<T> {
  const trace = getCurrentTrace();
  if (!trace) return fn();

  const span: Span = {
    spanId: randomUUID(),
    type: SpanType.LLM,
    name: `llm:${opts.model}`,
    model: opts.model,
    startedAt: new Date(),
    input: opts.inputText,
    metadata: opts.metadata ?? {},
  };

  const tracer = resolveTracer();
  const logger = (tracer as any)._logger ?? null;

  if (logger) {
    logger.llmStart(trace.name, opts.model);
  }

  let response: T;
  try {
    response = await fn();
  } catch (err: any) {
    if (logger) logger.llmError(trace.name, opts.model, err.message);
    span.finishedAt = new Date();
    span.metadata = { ...span.metadata, _error: err.message };
    trace.spans.push(span);
    throw err;
  }

  span.finishedAt = new Date();
  const tokens = extractTokens(response, opts.provider);
  span.tokensIn = tokens.input;
  span.tokensOut = tokens.output;
  span.tokensInCached = tokens.cached || undefined;
  span.costUsd = calculateCost(opts.model, tokens.input, tokens.output, undefined, tokens.cached);
  span.output = extractContent(response, opts.provider);
  trace.spans.push(span);

  if (logger) {
    const latencyMs = span.finishedAt.getTime() - span.startedAt.getTime();
    logger.llmEnd(trace.name, {
      model: opts.model,
      tokensIn: tokens.input,
      tokensOut: tokens.output,
      tokensInCached: tokens.cached || undefined,
      costUsd: span.costUsd,
      latencyMs,
    });
  }

  return response;
}

export function wrapOpenAI(client: any): any {
  return new Proxy(client, {
    get(target, prop, receiver) {
      const val = Reflect.get(target, prop, receiver);
      if (prop === "chat") {
        return new Proxy(val, {
          get(innerTarget, innerProp, innerReceiver) {
            const innerVal = Reflect.get(innerTarget, innerProp, innerReceiver);
            if (innerProp === "completions") {
              return new Proxy(innerVal, {
                get(deepTarget, deepProp, deepReceiver) {
                  const deepVal = Reflect.get(deepTarget, deepProp, deepReceiver);
                  if (deepProp === "create") {
                    return async function (this: any, ...args: any[]) {
                      const kwargs = args[0] ?? {};
                      const model = kwargs.model ?? "unknown";
                      const inputText = extractInputText(kwargs);
                      return traceLLMCall(
                        () => deepVal.apply(this, args),
                        { provider: "openai", model, inputText },
                      );
                    };
                  }
                  return deepVal;
                },
              });
            }
            return innerVal;
          },
        });
      }
      return val;
    },
  });
}

export function wrapAnthropic(client: any): any {
  return new Proxy(client, {
    get(target, prop, receiver) {
      const val = Reflect.get(target, prop, receiver);
      if (prop === "messages") {
        return new Proxy(val, {
          get(innerTarget, innerProp, innerReceiver) {
            const innerVal = Reflect.get(innerTarget, innerProp, innerReceiver);
            if (innerProp === "create") {
              return async function (this: any, ...args: any[]) {
                const kwargs = args[0] ?? {};
                const model = kwargs.model ?? "unknown";
                const inputText = extractInputText(kwargs);
                return traceLLMCall(
                  () => innerVal.apply(this, args),
                  { provider: "anthropic", model, inputText },
                );
              };
            }
            return innerVal;
          },
        });
      }
      return val;
    },
  });
}
