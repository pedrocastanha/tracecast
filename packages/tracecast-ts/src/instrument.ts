import type { Tracer } from "./core/tracer";
import { setDefaultTracer } from "./integrations/llm";
import { BaseInstrumentor } from "./instrumentors/base";

const registry: Map<string, BaseInstrumentor> = new Map();
let instrumented = false;

function _registerBuiltins(): void {
  const { OpenAIInstrumentor } = require("./instrumentors/openaiInst");
  const { AnthropicInstrumentor } = require("./instrumentors/anthropicInst");
  const { GeminiInstrumentor } = require("./instrumentors/geminiInst");
  const { LangChainInstrumentor } = require("./instrumentors/langchainInst");
  registry.set("openai", new OpenAIInstrumentor());
  registry.set("anthropic", new AnthropicInstrumentor());
  registry.set("gemini", new GeminiInstrumentor());
  registry.set("langchain", new LangChainInstrumentor());
}

// Register built-in instrumentors at module load time
_registerBuiltins();

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
  _registerBuiltins();
}

export function _registerInstrumentor(name: string, inst: BaseInstrumentor): void {
  registry.set(name, inst);
}
