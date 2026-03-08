"""
Chuck — Give any agent or human the right context at the right time.

Quick start:
    import chuck

    c = chuck.init(".")
    c.snap()               # full baseline + context to stdout
    # ... make changes ...
    c.patch()              # delta since last snap
"""

from .core import Chuck, ChuckError, NoSnapshotError
from .snapshot import Snapshot, SnapshotDiff, FileDiff
from .tokens import count_tokens, is_tiktoken_available

__version__ = "1.0.0"
__all__ = [
    "init",
    "Chuck",
    "ChuckError",
    "NoSnapshotError",
    "Snapshot",
    "SnapshotDiff",
    "FileDiff",
    "count_tokens",
    "is_tiktoken_available",
    "__version__",
]


def init(path: str = ".") -> Chuck:
    """
    Initialize Chuck at the given path and return a Chuck instance.

    Creates a .chuck/ directory if it doesn't exist. Safe to call multiple
    times (idempotent).

    Args:
        path: Directory to initialize. Defaults to current directory.

    Returns:
        A Chuck instance ready to use.

    Example:
        c = chuck.init(".")
        c.snap()
    """
    return Chuck.init(path)
