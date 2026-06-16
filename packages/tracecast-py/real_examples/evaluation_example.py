"""Exemplo completo de evaluation por golden dataset com TraceCast.

Mostra:
  - o decorator @evaluator marcando a funcao do agente (SUT) + path do golden dataset JSON
  - scorers deterministicos (similarity) + LLM-as-judge (rubrica multi-criterio)
  - execucao single-turn e multi-turn
  - export dos resultados para JSONL (visiveis na aba "Evaluators" do dashboard)

Roda offline com um judge heuristico local. Se a env OPENAI_API_KEY estiver setada,
usa LLM-as-judge real (LLMJudge).

Executar:
    python real_examples/evaluation_example.py

Equivalente via CLI:
    tracecast-eval --target support_bot --store ./eval_traces.jsonl

Visualizar no dashboard:
    TRACECAST_STORE="file://$(pwd)/eval_traces.jsonl" tracecast-server
    # abra http://127.0.0.1:7777/tracecast  ->  aba Evaluators
"""

import os
import re
import difflib
from pathlib import Path

from tracecast import evaluator, run_evaluation
from tracecast.eval import LLMJudge, JudgeResult
from tracecast.eval.models import CriterionScore
from tracecast.exporters import JsonFileExporter

DATASETS = Path(__file__).parent / "golden_datasets"

SUPPORT_KB = {
    "Qual o horario de atendimento?": "Atendemos de segunda a sexta, das 8h as 18h.",
    "Como peco reembolso?": "Voce pode solicitar reembolso em ate 7 dias pela pagina de pedidos.",
    "Qual o prazo de entrega?": "Entrega em 2 dias.",
}


@evaluator(
    dataset=str(DATASETS / "support_bot.json"),
    name="support_bot",
    scorers=["similarity"],
    threshold=0.7,
    project_id="suporte",
)
def support_bot(question: str) -> str:
    return SUPPORT_KB.get(question, "Nao sei responder.")


@evaluator(
    dataset=str(DATASETS / "cancelamento_multi_turn.json"),
    name="cancel_bot",
    scorers=["similarity"],
    threshold=0.6,
    project_id="suporte",
)
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
        scores = [
            CriterionScore(name=c["name"], score=round(ratio, 3),
                           reasoning=f"similaridade textual = {ratio:.2f}", kind="llm")
            for c in criteria
        ]
        return JudgeResult(scores=scores, tokens_in=0, tokens_out=0, cost_usd=0.0)


def _print_run(run):
    print(f"\n=== {run.name} ({run.dataset_name}) ===")
    print(f"pass_rate={run.pass_rate:.0%}  avg_score={run.avg_score:.3f}  "
          f"passed={run.passed}/{run.total_cases}  judge_cost=${run.judge_cost_usd:.4f}")
    for case in run.cases:
        flag = "PASS" if case.passed else case.status.upper()
        print(f"  [{flag}] {case.case_id}  score={case.overall_score:.3f}")
        for turn in case.turns:
            print(f"      turn#{turn.index} out={turn.output!r}")
            for s in turn.scores:
                print(f"        - {s.name} ({s.kind}): {s.score:.2f}")


def main():
    exporter = JsonFileExporter("./eval_traces.jsonl")
    judge = LLMJudge(model="gpt-4o-mini") if os.environ.get("OPENAI_API_KEY") else HeuristicJudge()
    print(f"judge: {type(judge).__name__}")

    for target in ("support_bot", "cancel_bot"):
        run = run_evaluation(target, exporters=[exporter], judge=judge)
        _print_run(run)

    print("\nResultados exportados para ./eval_traces.jsonl")
    print('Dashboard: TRACECAST_STORE="file://$(pwd)/eval_traces.jsonl" tracecast-server')


if __name__ == "__main__":
    main()
