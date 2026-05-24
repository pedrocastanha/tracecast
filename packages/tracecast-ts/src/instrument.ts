import type { Tracer } from "./core/tracer";
import { setDefaultTracer } from "./integrations/llm";
import { BaseInstrumentor } from "./instrumentors/base";
import { OpenAIInstrumentor } from "./instrumentors/openaiInst";
import { AnthropicInstrumentor } from "./instrumentors/anthropicInst";
import { GeminiInstrumentor } from "./instrumentors/geminiInst";
import { LangChainInstrumentor } from "./instrumentors/langchainInst";

const registry: Map<string, BaseInstrumentor> = new Map();
let instrumented = false;

// Register built-in instrumentors
registry.set("openai", new OpenAIInstrumentor());
registry.set("anthropic", new AnthropicInstrumentor());
registry.set("gemini", new GeminiInstrumentor());
registry.set("langchain", new LangChainInstrumentor());

export function autoInstrument(tracer?: Tracer): void {
  if (instrumented) return;
  if (tracer) setDefaultTracer(tracer);
  for (const [, inst] of registry) {
    try {
      inst.patch();
    } catch {
      // SDK not installed — skip silently
    }
  }
  instrumented = true;
}

export function _resetInstrument(): void {
  for (const inst of registry.values()) {
    try {
      if (inst.isPatched()) inst.unpatch();
    } catch { /* ignore */ }
  }
  registry.clear();
  instrumented = false;
}

export function _registerInstrumentor(name: string, inst: BaseInstrumentor): void {
  registry.set(name, inst);
}
