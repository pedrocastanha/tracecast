import pytest

from tracecast.eval.scorers import run_scorer


def test_exact_match():
    assert run_scorer("exact_match", "abc", "abc").score == 1.0
    assert run_scorer("exact_match", "abc ", " abc").score == 1.0
    assert run_scorer("exact_match", "abc", "abd").score == 0.0


def test_contains():
    assert run_scorer("contains", "the answer is 42", "42").score == 1.0
    assert run_scorer("contains", "nope", "42").score == 0.0


def test_regex():
    assert run_scorer("regex", "order 123 done", r"\d+").score == 1.0
    assert run_scorer("regex", "no digits", r"\d+").score == 0.0
    assert run_scorer("regex", "x", "[").score == 0.0


def test_similarity_bounds():
    assert run_scorer("similarity", "hello", "hello").score == 1.0
    s = run_scorer("similarity", "hello world", "hello there").score
    assert 0.0 < s < 1.0


def test_kind_is_deterministic():
    assert run_scorer("exact_match", "a", "a").kind == "deterministic"


def test_unknown_scorer_raises():
    with pytest.raises(ValueError):
        run_scorer("nope", "a", "b")


def test_none_expected_scores_zero():
    assert run_scorer("contains", "x", None).score == 0.0
