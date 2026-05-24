import { BaseInstrumentor } from "./base";
import { getCurrentTrace } from "../core/tracer";
import { calculateCost } from "../core/costCalculator";
import { randomUUID } from "crypto";
import { SpanType, Span } from "../types";

export class AnthropicInstrumentor implements BaseInstrumentor {
  private _original: any = null;
  private _patched = false;

  patch(): void {
    if (this._patched) return;
    let anthropicMod: any;
    try {
      anthropicMod = require("@anthropic-ai/sdk");
    } catch {
      throw new Error("@anthropic-ai/sdk not installed");
    }
    const Anthropic = anthropicMod.default ?? anthropicMod.Anthropic ?? anthropicMod;
    if (!Anthropic?.Messages?.prototype?.create) {
      throw new Error("@anthropic-ai/sdk: could not locate Messages.prototype.create");
    }
    this._original = Anthropic.Messages.prototype.create;
    const originalCreate = this._original;
    Anthropic.Messages.prototype.create = async function (this: any, ...args: any[]) {
      const trace = getCurrentTrace();
      if (!trace) return originalCreate.apply(this, args);
      const kwargs = args[0] ?? {};
      const model = kwargs.model ?? "unknown";
      const messages = kwargs.messages as any[] | undefined;
      const inputText = messages?.length
        ? String(messages[messages.length - 1]?.content ?? "")
        : undefined;
      const span: Span = {
        spanId: randomUUID(),
        type: SpanType.LLM,
        name: `llm:${model}`,
        model,
        startedAt: new Date(),
        input: inputText,
        metadata: {},
      };
      let response: any;
      try {
        response = await originalCreate.apply(this, args);
      } catch (err: any) {
        span.finishedAt = new Date();
        span.metadata = { ...span.metadata, _error: err.message };
        trace.spans.push(span);
        throw err;
      }
      span.finishedAt = new Date();
      const usage = response?.usage ?? {};
      span.tokensIn = usage?.input_tokens ?? 0;
      span.tokensOut = usage?.output_tokens ?? 0;
      span.tokensInCached = usage?.cache_read_input_tokens ?? 0;
      span.costUsd = calculateCost(model, span.tokensIn!, span.tokensOut!);
      try {
        const blocks = (response?.content ?? []) as any[];
        const text = blocks
          .filter((b: any) => b.type === "text")
          .map((b: any) => b.text)
          .join("");
        span.output = text || undefined;
      } catch { /* ignore */ }
      trace.spans.push(span);
      return response;
    };
    this._patched = true;
  }

  unpatch(): void {
    if (!this._patched || !this._original) return;
    try {
      const anthropicMod = require("@anthropic-ai/sdk");
      const Anthropic = anthropicMod.default ?? anthropicMod.Anthropic ?? anthropicMod;
      if (Anthropic?.Messages?.prototype) {
        Anthropic.Messages.prototype.create = this._original;
      }
      this._original = null;
      this._patched = false;
    } catch {
      // prototype not restored — leave _patched=true so retry is possible
    }
  }

  isPatched(): boolean {
    return this._patched;
  }
}
