"""Tests for token counting."""

import pytest
from chuck.tokens import count_tokens, count_tokens_fallback, is_tiktoken_available


def test_fallback_empty():
    assert count_tokens_fallback("") == 0


def test_fallback_basic():
    # 4 chars ≈ 1 token
    text = "a" * 100
    assert count_tokens_fallback(text) == 25


def test_fallback_short():
    assert count_tokens_fallback("hi") == 1  # max(1, 2//4)


def test_count_tokens_uses_fallback_or_tiktoken():
    text = "Hello world, this is a test."
    result = count_tokens(text)
    assert result > 0
    assert isinstance(result, int)


def test_custom_counter():
    counter = lambda t: 42
    assert count_tokens("anything", counter=counter) == 42


def test_fallback_within_reasonable_margin():
    """
    Fallback should be within a reasonable margin of tiktoken for code.

    Note: The 4-chars-per-token heuristic works best for code files (Chuck's
    primary use case). For English prose, error can reach 25-30% because natural
    language has more tokens per character than code.
    """
    if not is_tiktoken_available():
        pytest.skip("tiktoken not available")

    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")

    # Use Python code — Chuck's primary use case — where the heuristic is most accurate
    sample = (
        "def process_context(name: str, paths: list, token_budget: int = 4000):\n"
        "    snapshot = build_snapshot(name, paths)\n"
        "    diff = diff_snapshots(name, snapshot)\n"
        "    return digest(name, token_budget=token_budget, format='markdown')\n"
    )
    true_tokens = len(enc.encode(sample))
    est_tokens = count_tokens_fallback(sample)
    pct_error = abs(true_tokens - est_tokens) / true_tokens
    assert pct_error <= 0.20, (
        f"Fallback error {pct_error:.1%} exceeds 20% for code sample. "
        f"True: {true_tokens}, Estimated: {est_tokens}"
    )
