"""Chuck — main orchestrator class (directory-based model)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

from .digest import build_diff_digest, build_digest
from .ignore import IgnoreFilter
from .snapshot import Snapshot, SnapshotDiff, build_snapshot, diff_snapshots


class ChuckError(Exception):
    """Base exception for Chuck errors."""


class NoSnapshotError(ChuckError):
    """Raised when no snapshot exists."""


class Chuck:
    """
    Main Chuck interface. One instance per directory.

    Usage:
        c = chuck.init(".")
        c.snap()               # baseline + full context to stdout
        # ... make changes ...
        c.patch()              # delta since last snap
    """

    CHUCK_DIR = ".chuck"
    CONFIG_FILE = "config.json"
    STATE_FILE = "state.json"
    MANIFEST_FILE = "manifest.json"
    PATCH_FILE = "patch.md"
    SNAPSHOTS_DIR = "snapshots"

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.chuck_dir = self.root / self.CHUCK_DIR
        self._config: Dict = {
            "settings": {
                "auto_snap_threshold": {"files": 10, "tokens": 2000}
            }
        }
        self._token_cache: Dict[str, int] = {}
        if self.chuck_dir.exists():
            self._load_config()

    # ─── Initialization ───────────────────────────────────────────────────────

    @classmethod
    def init(cls, path: str = ".") -> "Chuck":
        """Initialize .chuck/ at the given path. Idempotent."""
        root = Path(path).resolve()
        chuck_dir = root / cls.CHUCK_DIR
        chuck_dir.mkdir(parents=True, exist_ok=True)
        (chuck_dir / cls.SNAPSHOTS_DIR).mkdir(exist_ok=True)

        instance = cls(root)
        if not (chuck_dir / cls.CONFIG_FILE).exists():
            instance._save_config()
        return instance

    # ─── Config ───────────────────────────────────────────────────────────────

    def _config_path(self) -> Path:
        return self.chuck_dir / self.CONFIG_FILE

    def _load_config(self):
        config_path = self._config_path()
        if config_path.exists():
            try:
                loaded = json.loads(config_path.read_text(encoding="utf-8"))
                if "settings" in loaded:
                    self._config["settings"].update(loaded["settings"])
                self._config.update({k: v for k, v in loaded.items() if k != "settings"})
            except (json.JSONDecodeError, OSError):
                pass

    def _save_config(self):
        self.chuck_dir.mkdir(parents=True, exist_ok=True)
        self._config_path().write_text(
            json.dumps(self._config, indent=2), encoding="utf-8"
        )

    # ─── File Resolution ──────────────────────────────────────────────────────

    def _resolve_files(self) -> List[Path]:
        """Resolve all tracked files, applying .chuckignore rules."""
        chuckignore_path = self.root / ".chuckignore"
        ignore_filter = IgnoreFilter.from_file(chuckignore_path, root=self.root)

        files = []
        try:
            for item in self.root.rglob("*"):
                try:
                    if item.is_file() and not ignore_filter.is_ignored(item):
                        files.append(item)
                except (OSError, PermissionError):
                    continue
        except (OSError, PermissionError):
            pass
        return sorted(files)

    # ─── Snapshot Storage ─────────────────────────────────────────────────────

    def _snapshots_dir(self) -> Path:
        return self.chuck_dir / self.SNAPSHOTS_DIR

    def _manifest_path(self) -> Path:
        return self.chuck_dir / self.MANIFEST_FILE

    def _list_snapshot_paths(self) -> List[Path]:
        snap_dir = self._snapshots_dir()
        if not snap_dir.exists():
            return []
        return sorted(snap_dir.glob("*.json"))

    def _latest_snapshot(self) -> Optional[Snapshot]:
        manifest = self._manifest_path()
        if manifest.exists():
            try:
                return Snapshot.load(manifest, self.root)
            except (OSError, json.JSONDecodeError):
                pass
        paths = self._list_snapshot_paths()
        if not paths:
            return None
        return Snapshot.load(paths[-1], self.root)

    def _save_snapshot(self, snap: Snapshot):
        """Persist snapshot to snapshots/ dir and update manifest."""
        snap_dir = self._snapshots_dir()
        snap_dir.mkdir(parents=True, exist_ok=True)
        safe_ts = snap.timestamp.replace(":", "-")
        snap.save(snap_dir / f"{safe_ts}.json")
        snap.save(self._manifest_path())

    # ─── State ────────────────────────────────────────────────────────────────

    def _update_state(
        self,
        snap: Snapshot,
        diff: Optional[SnapshotDiff] = None,
    ):
        """Write .chuck/state.json with current status."""
        state = {
            "last_snap": snap.timestamp,
            "files": snap.file_count,
            "tokens": snap.total_tokens,
            "changes_since_snap": {
                "files": len(diff.changed_files) if diff else 0,
                "tokens_delta": diff.tokens_changed if diff else 0,
            },
            "paths": {
                "snap": f"{self.CHUCK_DIR}/{self.MANIFEST_FILE}",
                "patch": f"{self.CHUCK_DIR}/{self.PATCH_FILE}",
            },
        }
        (self.chuck_dir / self.STATE_FILE).write_text(
            json.dumps(state, indent=2), encoding="utf-8"
        )

    # ─── Snap ─────────────────────────────────────────────────────────────────

    def snap(
        self,
        quiet: bool = False,
        format: str = "markdown",
        budget: Optional[int] = None,
        token_counter: Optional[Callable[[str], int]] = None,
    ) -> Optional[Union[str, List[str]]]:
        """
        Full baseline snapshot — saves and optionally emits content.

        Args:
            quiet: Suppress output (for git hooks, CI).
            format: 'markdown', 'xml', or 'json'.
            budget: Token budget per chunk.
            token_counter: Optional custom token counting function.

        Returns:
            Digest string (or list if chunked), or None if quiet.
        """
        context_name = self.root.name or "."
        files = self._resolve_files()
        snap = build_snapshot(context_name, files, self.root, token_counter, self._token_cache)
        self._save_snapshot(snap)
        self._update_state(snap)

        if quiet:
            return None

        return build_digest(context_name, snap, self.root, budget, format, token_counter)

    # ─── Patch ────────────────────────────────────────────────────────────────

    def patch(
        self,
        quiet: bool = False,
        format: str = "markdown",
        budget: Optional[int] = None,
        token_counter: Optional[Callable[[str], int]] = None,
    ) -> Tuple[Optional[Union[str, List[str]]], bool]:
        """
        Delta since last snap — emits diff, baseline unchanged.

        Auto-promotes to snap if no baseline exists or diff exceeds threshold.

        Args:
            quiet: Suppress stdout output.
            format: 'markdown', 'xml', or 'json'.
            budget: Token budget per chunk.
            token_counter: Optional custom token counting function.

        Returns:
            (output, auto_snapped) tuple.
        """
        latest = self._latest_snapshot()
        if latest is None:
            result = self.snap(quiet=quiet, format=format, budget=budget, token_counter=token_counter)
            return result, True

        context_name = self.root.name or "."
        files = self._resolve_files()
        current = build_snapshot(context_name, files, self.root, token_counter, self._token_cache)
        diff = diff_snapshots(context_name, latest, current, self.root)

        # Check auto-snap threshold
        threshold = self._config.get("settings", {}).get("auto_snap_threshold", {})
        threshold_files = threshold.get("files", 10)
        threshold_tokens = threshold.get("tokens", 2000)

        if (len(diff.changed_files) >= threshold_files
                or abs(diff.tokens_changed) >= threshold_tokens):
            self._save_snapshot(current)
            self._update_state(current)
            if quiet:
                return None, True
            result = build_digest(context_name, current, self.root, budget, format, token_counter)
            return result, True

        # Normal patch: emit diff, write patch.md, update state
        diff_content = build_diff_digest(
            context_name, diff, latest, self.root, budget, format, token_counter
        )

        if isinstance(diff_content, list):
            patch_text = "\n\n---\n\n".join(diff_content)
        else:
            patch_text = diff_content or ""
        (self.chuck_dir / self.PATCH_FILE).write_text(patch_text, encoding="utf-8")

        self._update_state(latest, diff)

        if quiet:
            return None, False

        return diff_content, False

    # ─── Diff ─────────────────────────────────────────────────────────────────

    def diff(
        self,
        token_counter: Optional[Callable[[str], int]] = None,
    ) -> SnapshotDiff:
        """
        Compute metadata diff from last snap to current state.

        Raises:
            NoSnapshotError: If no baseline snapshot exists.
        """
        latest = self._latest_snapshot()
        if latest is None:
            raise NoSnapshotError("No snapshot exists. Run: chuck snap")

        context_name = self.root.name or "."
        files = self._resolve_files()
        current = build_snapshot(context_name, files, self.root, token_counter, self._token_cache)
        return diff_snapshots(context_name, latest, current, self.root)

    # ─── Status ───────────────────────────────────────────────────────────────

    def status(self) -> Dict:
        """Return metadata about this Chuck instance."""
        snap = self._latest_snapshot()
        snap_count = len(self._list_snapshot_paths())

        changes = None
        state_path = self.chuck_dir / self.STATE_FILE
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                changes = state.get("changes_since_snap")
            except (json.JSONDecodeError, OSError):
                pass

        return {
            "root": str(self.root),
            "file_count": snap.file_count if snap else 0,
            "total_tokens": snap.total_tokens if snap else 0,
            "last_snapshot": snap.timestamp if snap else None,
            "snapshot_count": snap_count,
            "changes_since_snap": changes,
        }

    # ─── Reset ────────────────────────────────────────────────────────────────

    def reset(self):
        """Clear all snapshots, manifest, state, and patch files."""
        import shutil
        snap_dir = self._snapshots_dir()
        if snap_dir.exists():
            shutil.rmtree(snap_dir)
            snap_dir.mkdir(parents=True, exist_ok=True)
        for fname in [self.MANIFEST_FILE, self.STATE_FILE, self.PATCH_FILE]:
            p = self.chuck_dir / fname
            if p.exists():
                p.unlink()

    # ─── Integrate ────────────────────────────────────────────────────────────

    def integrate(self, agent: str) -> Dict[str, str]:
        """
        Generate agent-specific integration files at the project root.

        Args:
            agent: One of 'claude', 'goose', 'agents'.

        Returns:
            Dict mapping keys to file paths written.

        Raises:
            ChuckError: If agent is not recognized.
        """
        chuck_section = (
            "## Chuck Context\n\n"
            "This project uses Chuck for context management.\n\n"
            f"- State: `.{self.CHUCK_DIR}/{self.STATE_FILE}` — snapshot metadata and change counts\n"
            f"- Patch: `.{self.CHUCK_DIR}/{self.PATCH_FILE}` — what changed since last snap\n"
            f"- Full context: `.{self.CHUCK_DIR}/{self.MANIFEST_FILE}` — complete snapshot\n\n"
            "On each message, check the patch first. Read the full context only if the\n"
            "patch is too large to reason about, or if you have no prior context.\n"
        )

        written = {}

        if agent == "claude":
            target = self.root / "CLAUDE.md"
            marker = "## Chuck Context"
            if target.exists():
                content = target.read_text(encoding="utf-8")
                if marker not in content:
                    content = content.rstrip() + "\n\n" + chuck_section
                    target.write_text(content, encoding="utf-8")
            else:
                target.write_text(chuck_section, encoding="utf-8")
            written["claude_md"] = str(target)

        elif agent == "goose":
            target = self.root / ".goose" / "context.md"
            target.parent.mkdir(exist_ok=True)
            target.write_text(chuck_section, encoding="utf-8")
            written["goose_context"] = str(target)

            # Write a wrapper script that injects context.md via --system.
            # The wrapper shadows the real goose when .goose/ is prepended to PATH.
            real_goose = shutil.which("goose")
            if real_goose:
                wrapper = self.root / ".goose" / "goose"
                wrapper_script = (
                    "#!/bin/bash\n"
                    "# Goose wrapper: injects Chuck context via --system when present.\n"
                    "# Created by: chuck integrate goose\n"
                    f'REAL_GOOSE="{real_goose}"\n'
                    'if [ "$1" = "run" ] && [ -f ".goose/context.md" ]; then\n'
                    "  shift\n"
                    '  CHUCK_CONTEXT=$(< .goose/context.md)\n'
                    '  exec "$REAL_GOOSE" run --system "$CHUCK_CONTEXT" "$@"\n'
                    "else\n"
                    '  exec "$REAL_GOOSE" "$@"\n'
                    "fi\n"
                )
                wrapper.write_text(wrapper_script, encoding="utf-8")
                wrapper.chmod(0o755)
                written["goose_wrapper"] = str(wrapper)

        elif agent == "agents":
            target = self.root / "AGENTS.md"
            target.write_text(chuck_section, encoding="utf-8")
            written["agents_md"] = str(target)

        elif agent == "kilo":
            rules_dir = self.root / ".kilocode" / "rules"
            rules_dir.mkdir(parents=True, exist_ok=True)
            target = rules_dir / "chuck.md"
            target.write_text(chuck_section, encoding="utf-8")
            written["kilo_rules"] = str(target)

        else:
            raise ChuckError(
                f"Unknown agent '{agent}'. Supported: claude, goose, agents, kilo"
            )

        return written

    # ─── ls ───────────────────────────────────────────────────────────────────

    @classmethod
    def ls(cls, path: str = ".") -> List[Path]:
        """Find all Chuck instances (directories with .chuck/) under path."""
        root = Path(path).resolve()
        instances = []
        try:
            for chuck_dir in sorted(root.rglob(".chuck")):
                if chuck_dir.is_dir() and (chuck_dir / cls.CONFIG_FILE).exists():
                    instances.append(chuck_dir.parent)
        except (OSError, PermissionError):
            pass
        return instances
