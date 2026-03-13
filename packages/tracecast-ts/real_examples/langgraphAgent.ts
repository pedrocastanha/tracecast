import path from "path";
import dotenv from "dotenv";
dotenv.config({ path: path.resolve(__dirname, "../../../.env") });

import { StateGraph, END, Annotation } from "@langchain/langgraph";
import { Tracer, JsonFileExporter, DictExporter } from "../src";
import { TraceCastCallback } from "../src/integrations/langchain";

const tracer = new Tracer({
  exporters: [
    new JsonFileExporter("./traces/ts_langgraph_traces.jsonl"),
    new DictExporter({
      onTrace: (d: any) =>
        console.log(`[ANALYTICS] ${d.name} spans=${d.spans?.length ?? 0} cost=$${d.costUsd.toFixed(4)}`),
    }),
  ],
  logging: true,
  logPrefix: "ts_langgraph_agent",
});
const cb = new TraceCastCallback(tracer);

const GraphState = Annotation.Root({
  history: Annotation<string[]>({ reducer: (x, y) => x.concat(y) }),
  status: Annotation<string>({ reducer: (_, y) => y }),
});

const nodeInput = async (state: typeof GraphState.State) => ({
  history: ["Iniciando pipeline..."],
  status: "processing",
});

const nodeProcessor = async (state: typeof GraphState.State) => ({
  history: ["Processando dados..."],
  status: "processing",
});

const nodeOutput = async (state: typeof GraphState.State) => ({
  history: ["Pipeline concluído!"],
  status: "done",
});

const workflow = new StateGraph(GraphState)
  .addNode("input_node", nodeInput)
  .addNode("processor_node", nodeProcessor)
  .addNode("output_node", nodeOutput)
  .addEdge("input_node", "processor_node")
  .addEdge("processor_node", "output_node")
  .addEdge("output_node", END)
  .setEntryPoint("input_node");

const app = workflow.compile();

async function run() {
  await tracer.trace(
    "langgraph_execution",
    async () => {
      const result = await app.invoke({ history: [], status: "" }, { callbacks: [cb] });
      console.log(`\nHistórico: ${result.history.join(" → ")}`);
    },
    { userId: "user_pedro" },
  );
}

if (require.main === module) {
  run().catch(console.error);
}
