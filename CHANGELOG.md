# Changelog

## 1.0.0 — 2026-03-07

Initial public release.

- `chuck init` — initialize `.chuck/` tracking in any directory
- `chuck snap` — full baseline snapshot with markdown/XML/JSON output
- `chuck patch` — delta since last snap, auto-promotes when threshold exceeded
- `chuck diff` — change summary without content
- `chuck status` — instance metadata
- `chuck ls` — find all Chuck instances
- `chuck reset` — clear snapshot history
- `chuck integrate <agent>` — generate agent-specific integration files
- `chuck-aider` — launch Aider with Chuck context
- `chuck-aider-init` — generate `.aider.conf.yml`
- Token-aware chunking with configurable budgets
- `.chuckignore` support (gitignore syntax)
- Python API: `chuck.init()`, `snap()`, `patch()`, `diff()`, `status()`
- Optional tiktoken support for accurate token counting
