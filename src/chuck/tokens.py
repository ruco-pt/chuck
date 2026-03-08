"""Token counting with tiktoken and word-based fallback."""

from __future__ import annotations

from typing import Callable, Optional

_tiktoken_encoder = None
_tiktoken_available: Optional[bool] = None


def _get_tiktoken_encoder():
    global _tiktoken_encoder, _tiktoken_available
    if _tiktoken_available is None:
        try:
            import tiktoken
            _tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
            _tiktoken_available = True
        except ImportError:
            _tiktoken_available = False
    return _tiktoken_encoder if _tiktoken_available else None


def count_tokens_tiktoken(text: str) -> int:
    enc = _get_tiktoken_encoder()
    if enc is None:
        raise RuntimeError("tiktoken is not available")
    return len(enc.encode(text))


def count_tokens_fallback(text: str) -> int:
    """Estimate token count: 4 chars ≈ 1 token."""
    return max(1, len(text) // 4) if text else 0


def count_tokens(text: str, counter: Optional[Callable[[str], int]] = None) -> int:
    """Count tokens using the provided counter, tiktoken, or fallback."""
    if counter is not None:
        return counter(text)
    enc = _get_tiktoken_encoder()
    if enc is not None:
        return len(enc.encode(text))
    return count_tokens_fallback(text)


def is_tiktoken_available() -> bool:
    _get_tiktoken_encoder()
    return bool(_tiktoken_available)
