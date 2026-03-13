import logging
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parents[3] / ".env")
except ImportError:
    pass

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.tools import tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from tracecast import Tracer
from tracecast.exporters import DictExporter, JsonFileExporter
from tracecast.integrations.langchain import TraceCastCallback

logging.basicConfig(level=logging.INFO, format="%(message)s")

tracer = Tracer(
    exporters=[
        JsonFileExporter("./traces/langchain_traces.jsonl"),
        DictExporter(on_trace=lambda d: print(f"[ANALYTICS] {d['name']} cost=${d['cost_usd']:.4f}")),
    ],
    logging=True,
    log_prefix="financial_agent",
)
callback = TraceCastCallback(tracer=tracer)


@tool
def get_stock_price(ticker: str) -> str:
    prices = {"PETR4": 38.75, "VALE3": 65.20, "ITUB4": 32.10}
    price = prices.get(ticker.upper(), 0.0)
    return f"{ticker.upper()}: R$ {price:.2f}"


@tool
def calculate_investment_return(principal: float, rate: float, months: int) -> str:
    total = principal * ((1 + rate / 100) ** months)
    return f"Principal: R$ {principal:.2f} → Total: R$ {total:.2f} em {months} meses a {rate}% a.m."

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, stream_usage=True)
tools = [get_stock_price, calculate_investment_return]
prompt = ChatPromptTemplate.from_messages([
    ("system", "Você é um assistente financeiro brasileiro. Responda sempre em português."),
    MessagesPlaceholder("chat_history", optional=True),
    ("user", "{input}"),
    MessagesPlaceholder("agent_scratchpad"),
])
agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools, verbose=False)


def analyze_portfolio(question: str) -> str:
    with tracer.trace("financial_agent_run", user_id="user_pedro"):
        result = executor.invoke({"input": question}, config={"callbacks": [callback]})
        return result["output"]


if __name__ == "__main__":
    questions = [
        "Qual a cotação de PETR4?",
        "Rendimento de R$ 10.000 a 0.8% por 12 meses",
        "Compare PETR4 e VALE3 e calcule rendimento de R$ 5.000 a 0.9% por 6 meses",
    ]
    for q in questions:
        answer = analyze_portfolio(q)
        print(f"\nPergunta: {q}\nResposta: {answer}\n")
