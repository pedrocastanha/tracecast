import { BaseInstrumentor } from "./base";
import { getCurrentTrace } from "../core/tracer";
import { calculateCost } from "../core/costCalculator";
import { randomUUID } from "crypto";
import { SpanType, Span } from "../types";

export class GeminiInstrumentor implements BaseInstrumentor {
  private _original: any = null;
  private _patched = false;

  patch(): void {
    if (this._patched) return;
    let mod: any;
    try {
      mod = require("@google/generative-ai");
    } catch {
      throw new Error("@google/generative-ai not installed");
    }
    const GenerativeModel = mod.GenerativeModel ?? null;
    if (!GenerativeModel?.prototype?.generateContent) {
      throw new Error("@google/generative-ai: could not locate GenerativeModel.prototype.generateContent");
    }
    this._original = GenerativeModel.prototype.generateContent;
    const originalGenerate = this._original;
    GenerativeModel.prototype.generateContent = async function (this: any, ...args: any[]) {
      const trace = getCurrentTrace();
      if (!trace) return originalGenerate.apply(this, args);
      const model: string = (this as any).model ?? "gemini";
      const span: Span = {
        spanId: randomUUID(),
        type: SpanType.LLM,
        name: `llm:${model}`,
        model,
        startedAt: new Date(),
        metadata: {},
      };
      let result: any;
      try {
        result = await originalGenerate.apply(this, args);
      } catch (err: any) {
        span.finishedAt = new Date();
        span.metadata = { ...span.metadata, _error: err.message };
        trace.spans.push(span);
        throw err;
      }
      span.finishedAt = new Date();
      const response = result?.response ?? result;
      const usageMeta = response?.usageMetadata ?? {};
      span.tokensIn = usageMeta?.promptTokenCount ?? 0;
      span.tokensOut = usageMeta?.candidatesTokenCount ?? 0;
      span.tokensInCached = usageMeta?.cachedContentTokenCount ?? 0;
      span.costUsd = calculateCost(model, span.tokensIn!, span.tokensOut!);
      try {
        const parts = (response?.candidates?.[0]?.content?.parts ?? []) as any[];
        const text = parts.map((p: any) => p.text ?? "").join("");
        span.output = text || undefined;
      } catch { /* ignore */ }
      trace.spans.push(span);
      return result;
    };
    this._patched = true;
  }

  unpatch(): void {
    if (!this._patched || !this._original) return;
    try {
      const mod = require("@google/generative-ai");
      const GenerativeModel = mod.GenerativeModel ?? null;
      if (GenerativeModel?.prototype) {
        GenerativeModel.prototype.generateContent = this._original;
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
