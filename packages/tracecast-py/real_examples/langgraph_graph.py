import logging
import operator
from pathlib import Path
from typing import Annotated, TypedDict

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parents[3] / ".env")
except ImportError:
    pass

from langgraph.graph import END, StateGraph
from tracecast import Tracer
from tracecast.exporters import JsonFileExporter
from tracecast.integrations.langchain import TraceCastCallback

logging.basicConfig(level=logging.INFO, format="%(message)s")

tracer = Tracer(
    exporters=[JsonFileExporter("./traces/langgraph_traces.jsonl")],
    logging=True,
    log_prefix="graph_orchestrator",
)
callback = TraceCastCallback(tracer=tracer)


class GraphState(TypedDict):
    messages: Annotated[list[str], operator.add]


def node_input(state: GraphState):
    return {"messages": ["Iniciando pipeline..."]}


def node_processor(state: GraphState):
    return {"messages": ["Processando dados..."]}


def node_output(state: GraphState):
    return {"messages": ["Pipeline concluído!"]}


workflow = StateGraph(GraphState)
workflow.add_node("input_node", node_input)
workflow.add_node("processor_node", node_processor)
workflow.add_node("output_node", node_output)
workflow.set_entry_point("input_node")
workflow.add_edge("input_node", "processor_node")
workflow.add_edge("processor_node", "output_node")
workflow.add_edge("output_node", END)
app = workflow.compile()


def run_workflow():
    with tracer.trace("langgraph_execution", user_id="user_pedro") as trace:
        result = app.invoke({"messages": []}, config={"callbacks": [callback]})
        print(f"\nMensagens: {result['messages']}")


if __name__ == "__main__":
    run_workflow()
