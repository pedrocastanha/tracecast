from tracecast.eval.judge import LLMJudge, JudgeResponse, _extract_json


CRITERIA = [{"name": "faithfulness", "description": "fiel"}, {"name": "relevance", "description": "relevante"}]


def test_extract_json_plain():
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced_and_noisy():
    text = 'Sure!\n```json\n{"faithfulness": {"score": 0.9}}\n```\nThanks'
    assert _extract_json(text) == {"faithfulness": {"score": 0.9}}


def test_extract_json_invalid():
    assert _extract_json("no json here") is None


def test_judge_scores_each_criterion():
    payload = '{"faithfulness": {"score": 0.8, "reasoning": "ok"}, "relevance": {"score": 1.0, "reasoning": "yes"}}'
    judge = LLMJudge(model="gpt-4o-mini", call_fn=lambda s, u: JudgeResponse(payload, 10, 4))
    res = judge.score(input="q", output="o", expected="e", criteria=CRITERIA)
    by_name = {s.name: s for s in res.scores}
    assert by_name["faithfulness"].score == 0.8
    assert by_name["relevance"].score == 1.0
    assert by_name["faithfulness"].kind == "llm"
    assert res.tokens_in == 10 and res.tokens_out == 4
    assert res.cost_usd > 0


def test_judge_missing_criterion_is_parse_error():
    payload = '{"faithfulness": {"score": 0.5}}'
    judge = LLMJudge(call_fn=lambda s, u: JudgeResponse(payload, 1, 1))
    res = judge.score(input="q", output="o", expected="e", criteria=CRITERIA)
    by_name = {s.name: s for s in res.scores}
    assert by_name["relevance"].score == 0.0
    assert by_name["relevance"].reasoning == "parse_error"


def test_judge_invalid_json_all_zero():
    judge = LLMJudge(call_fn=lambda s, u: JudgeResponse("garbage", 0, 0))
    res = judge.score(input="q", output="o", expected="e", criteria=CRITERIA)
    assert all(s.score == 0.0 for s in res.scores)


def test_judge_clamps_score():
    payload = '{"faithfulness": {"score": 5}, "relevance": {"score": -2}}'
    judge = LLMJudge(call_fn=lambda s, u: JudgeResponse(payload, 0, 0))
    res = judge.score(input="q", output="o", expected="e", criteria=CRITERIA)
    by_name = {s.name: s.score for s in res.scores}
    assert by_name["faithfulness"] == 1.0
    assert by_name["relevance"] == 0.0


def test_judge_unavailable_degrades_without_raising():
    def boom(s, u):
        raise RuntimeError("no api key")
    judge = LLMJudge(call_fn=boom)
    res = judge.score(input="q", output="o", expected="e", criteria=CRITERIA)
    assert all(s.score == 0.0 for s in res.scores)
    assert all("judge_unavailable" in (s.reasoning or "") for s in res.scores)


def test_judge_no_criteria_empty():
    judge = LLMJudge(call_fn=lambda s, u: JudgeResponse("{}", 0, 0))
    assert judge.score(input="q", output="o", expected="e", criteria=[]).scores == []
