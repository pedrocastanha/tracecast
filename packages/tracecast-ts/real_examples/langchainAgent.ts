import path from "path";
import dotenv from "dotenv";
dotenv.config({ path: path.resolve(__dirname, "../../../.env") });

import { ChatOpenAI } from "@langchain/openai";
import { ChatPromptTemplate } from "@langchain/core/prompts";
import { Tracer, JsonFileExporter, DictExporter } from "../src";
import { TraceCastCallback } from "../src/integrations/langchain";

const tracer = new Tracer({
  exporters: [
    new JsonFileExporter("./traces/ts_langchain_traces.jsonl"),
    new DictExporter({
      onTrace: (d: any) =>
        console.log(`[ANALYTICS] ${d.name} cost=$${d.costUsd.toFixed(4)}`),
    }),
  ],
  logging: true,
  logPrefix: "ts_langchain_agent",
});
const cb = new TraceCastCallback(tracer);

async function translate(text: string, targetLang: string): Promise<string> {
  const llm = new ChatOpenAI({ model: "gpt-4o-mini", temperature: 0 });
  const prompt = ChatPromptTemplate.fromMessages([
    ["system", `Você é um tradutor especializado. Traduza o texto para ${targetLang}. Responda apenas com a tradução.`],
    ["user", "{text}"],
  ]);
  const chain = prompt.pipe(llm as any) as any;

  return tracer.trace(
    "langchain_translate",
    async () => {
      const result = await chain.invoke({ text }, { callbacks: [cb] });
      return result.content as string;
    },
    { userId: "user_pedro", metadata: { targetLang, framework: "langchain" } },
  );
}

if (require.main === module) {
  const examples = [
    { text: "Hello, how are you?", lang: "Português" },
    { text: "The quick brown fox jumps over the lazy dog", lang: "Espanhol" },
  ];

  (async () => {
    for (const { text, lang } of examples) {
      const result = await translate(text, lang);
      console.log(`\n[${lang}] ${text}\n→ ${result}`);
    }
  })().catch(console.error);
}
