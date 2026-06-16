"""Demonstração real de evaluation por golden dataset com TraceCast.

Avalia dois agentes (single-turn e multi-turn) contra golden datasets JSON, com
scorers determinísticos + judge (heurístico offline, ou LLM real se OPENAI_API_KEY
estiver setada). Exporta os resultados para JSONL.

Executar:
    python demo/evaluation_demo.py

Visualizar no dashboard:
    TRACECAST_STORE="file://$(pwd)/demo/demo_output/eval_traces.jsonl" tracecast-server
    # http://127.0.0.1:7777/tracecast  ->  aba Evaluators

Equivalente via CLI (quando o target está num módulo importável do seu projeto):
    tracecast-eval --target seu_modulo:support_bot \
        --store file://$(pwd)/demo/demo_output/eval_traces.jsonl
"""

import difflib
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "packages" / "tracecast-py"))

from tracecast import evaluator, run_evaluation
from tracecast.eval import LLMJudge, JudgeResult
from tracecast.eval.models import CriterionScore
from tracecast.exporters import JsonFileExporter

HERE = pathlib.Path(__file__).parent
DATASETS = HERE / "golden_datasets"
OUT = HERE / "demo_output"
OUT.mkdir(exist_ok=True)

SUPPORT_KB = {
    "Qual o horario de atendimento?": "Atendemos de segunda a sexta, das 8h as 18h.",
    "Como peco reembolso?": "Voce pode solicitar reembolso em ate 7 dias pela pagina de pedidos.",
    "Qual o prazo de entrega?": "Entrega em 2 dias.",
}


@evaluator(dataset=str(DATASETS / "support_bot.json"), name="support_bot",
           scorers=["similarity"], threshold=0.7, project_id="demo")
def support_bot(question: str) -> str:
    return SUPPORT_KB.get(question, "Nao sei responder.")


@evaluator(dataset=str(DATASETS / "cancelamento_multi_turn.json"), name="cancel_bot",
           scorers=["similarity"], threshold=0.6, project_id="demo")
def cancel_bot(messages: list) -> str:
    last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    numbers = re.findall(r"\d+", last_user)
    if numbers:
        return f"Pedido {numbers[0]} cancelado com sucesso. Reembolso em ate 7 dias."
    if "cancel" in last_user.lower():
        return "Claro, me informe o numero do pedido para prosseguir."
    return "Como posso ajudar?"


class HeuristicJudge:
    def score(self, *, input, output, expected, criteria):
        ratio = difflib.SequenceMatcher(None, output or "", expected or "").ratio()
        scores = [CriterionScore(name=c["name"], score=round(ratio, 3),
                                 reasoning=f"similaridade = {ratio:.2f}", kind="llm") for c in criteria]
        return JudgeResult(scores=scores)


def main():
    exporter = JsonFileExporter(str(OUT / "eval_traces.jsonl"))
    judge = LLMJudge("gpt-4o-mini") if os.environ.get("OPENAI_API_KEY") else HeuristicJudge()
    print(f"judge: {type(judge).__name__}")

    for target in ("support_bot", "cancel_bot"):
        run = run_evaluation(target, exporters=[exporter], judge=judge)
        print(f"\n=== {run.name} ({run.dataset_name}) ===")
        print(f"pass_rate={run.pass_rate:.0%}  avg_score={run.avg_score:.3f}  passed={run.passed}/{run.total_cases}")
        for case in run.cases:
            print(f"  [{'PASS' if case.passed else case.status.upper()}] {case.case_id}  score={case.overall_score:.3f}")

    print(f"\nExportado para {OUT / 'eval_traces.jsonl'}")


if __name__ == "__main__":
    main()
