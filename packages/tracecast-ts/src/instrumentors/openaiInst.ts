import { BaseInstrumentor } from "./base";
import { getCurrentTrace } from "../core/tracer";
import { calculateCost } from "../core/costCalculator";
import { randomUUID } from "crypto";
import { SpanType, Span } from "../types";

export class OpenAIInstrumentor implements BaseInstrumentor {
  private _original: any = null;
  private _patched = false;

  patch(): void {
    if (this._patched) return;
    let openaiMod: any;
    try {
      openaiMod = require("openai");
    } catch {
      throw new Error("openai not installed");
    }
    const OpenAI = openaiMod.default ?? openaiMod.OpenAI ?? openaiMod;
    if (!OpenAI?.Chat?.Completions?.prototype?.create) return;
    this._original = OpenAI.Chat.Completions.prototype.create;
    const originalCreate = this._original;
    OpenAI.Chat.Completions.prototype.create = async function (this: any, ...args: any[]) {
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
      span.tokensIn = usage?.prompt_tokens ?? 0;
      span.tokensOut = usage?.completion_tokens ?? 0;
      span.tokensInCached = usage?.prompt_tokens_details?.cached_tokens ?? 0;
      span.costUsd = calculateCost(model, span.tokensIn!, span.tokensOut!);
      try {
        span.output = response?.choices?.[0]?.message?.content ?? undefined;
      } catch { /* ignore */ }
      trace.spans.push(span);
      return response;
    };
    this._patched = true;
  }

  unpatch(): void {
    if (!this._patched || !this._original) return;
    try {
      const openaiMod = require("openai");
      const OpenAI = openaiMod.default ?? openaiMod.OpenAI ?? openaiMod;
      if (OpenAI?.Chat?.Completions?.prototype) {
        OpenAI.Chat.Completions.prototype.create = this._original;
      }
    } catch { /* ignore */ }
    this._original = null;
    this._patched = false;
  }

  isPatched(): boolean {
    return this._patched;
  }
}
