# Chuck

**Give any agent or human the right context at the right time, and know when that context has changed.**

Chuck is a standalone Python library and CLI that sits between raw project files and whatever consumes them — LLMs, agents, pipelines, humans. It ingests files, tracks changes, and produces clean, token-aware context digests in markdown, XML, or JSON.

Chuck is not a framework. No daemon, no server, no background process. Think of it like `.gitignore` — a simple standard anyone can adopt.

```bash
pip install chucky

chuck init
chuck snap | claude "review this codebase"

# ... make changes ...

chuck patch | claude "fix the bug in auth.py"
```

---

## Why Chuck

Every AI-assisted workflow has the same bottleneck: context. Agents need to know what files exist, what changed, what matters, and how much fits in their window. Chuck is the standard.

- **Agnostic.** No dependency on Claude, GPT, Ollama, Cursor, or any specific tool.
- **Standalone.** `pip install chuck`. No daemon, no server, no background process.
- **Two speeds.** `snap` for full baseline, `patch` for delta. The model always gets the right amount of context.
- **Persistent by convention.** State lives in `.chuck/` at the project root. Delete it and Chuck starts fresh. Commit it and your team shares context state.

---

## Install

```bash
pip install chucky
```

Python 3.9+ required. No required dependencies — tiktoken is optional (falls back to a word-based estimator).

```bash
pip install "chucky[tiktoken]"  # For accurate token counting with cl100k_base
```

---

## Core Workflow

Chuck uses a two-speed model:

- **`snap`** — full baseline. Saves the current state and emits full context to stdout. Use after significant changes.
- **`patch`** — partial delta. Emits only what changed since the last snap, without moving the baseline. Use for small iterative changes before prompting a model.

```bash
# First time — model gets the full picture
chuck snap | claude "review this codebase"

# Small changes — model gets only the delta
chuck patch | claude "fix the bug in auth.py"

# Silent snap for git hooks / CI
chuck snap --quiet
```

---

## Concepts

| Concept | Description |
|---------|-------------|
| **Instance** | A directory tracked by Chuck. Created with `chuck init`. |
| **Snap** | Full baseline snapshot. Saves state and emits complete context. |
| **Patch** | Delta since the last snap. Emits only what changed; baseline unchanged. |
| **Chunk** | A section of content sized to fit within a token budget. |

---

## The Git Mental Model

**The directory is the context.** Each directory that needs tracking gets its own `chuck init`, producing its own `.chuck/` folder. There are no named contexts to define.

```bash
chuck init          # tracks everything here, no patterns needed
```

Use `.chuckignore` to exclude what you don't want:

```gitignore
# .chuckignore — same syntax as .gitignore
dist/
*.log
secrets.env
```

For a monorepo, initialize each subdirectory independently and ignore overlaps:

```
my-app/           ← chuck init (tracks README, root config, etc.)
my-app/backend/   ← chuck init (tracks backend only)
my-app/frontend/  ← chuck init (tracks frontend only)
```

Root `.chuckignore`:
```gitignore
/frontend/
/backend/
```

---

## CLI Quickstart

```bash
# 1. Initialize
chuck init

# 2. Take a full snapshot (baseline) — outputs full context to stdout
chuck snap

# 3. Work on files...

# 4. Get only the delta — outputs changes to stdout
chuck patch

# 5. Check what changed (metadata only, no content)
chuck diff

# 6. Show instance status
chuck status
```

### All CLI Commands

| Command | Description |
|---------|-------------|
| `chuck init [path]` | Initialize `.chuck/` in a directory |
| `chuck snap [path]` | Full baseline snapshot — saves and emits to stdout |
| `chuck patch [path]` | Delta since last snap — emits to stdout, baseline unchanged |
| `chuck diff [path]` | Show change summary (files/tokens) without emitting content |
| `chuck status [path]` | Show instance metadata |
| `chuck ls [path]` | List all Chuck instances found under a path |
| `chuck reset [path]` | Clear snapshot history |
| `chuck integrate <agent> [path]` | Generate agent-specific integration files |

All `[path]` arguments default to the current directory.

### Common Flags

```bash
chuck snap --quiet          # save only, no stdout output (for git hooks, CI)
chuck snap --format xml     # XML output instead of markdown
chuck snap --format json    # JSON output
chuck snap --budget 4000    # chunk output to fit token budget

chuck patch --quiet         # write patch.md only, no stdout
chuck diff --json           # machine-readable diff
```

---

## Auto-snap Threshold

If the diff grows beyond a configurable threshold, `patch` automatically promotes to `snap` before outputting. The user never has to think about it.

```json
// .chuck/config.json
{
  "settings": {
    "auto_snap_threshold": {
      "files": 10,
      "tokens": 2000
    }
  }
}
```

When auto-promoted, Chuck notifies on stderr:
```
auto-snapped: diff exceeded threshold. new baseline set.
```

---

## Agent Integrations

Chuck generates thin integration glue per agent on request:

```bash
chuck integrate claude   # appends a Chuck section to CLAUDE.md
chuck integrate goose    # writes .goose/context.md
chuck integrate agents   # writes AGENTS.md (generic)
```

The generated content tells the agent where Chuck's state and patch files are and how to use them.

---

## Aider Integration

Chuck ships two tools for seamless [Aider](https://aider.chat) sessions — no
manual `/read` steps, no git requirement.

### `chuck-aider` — launch Aider with Chuck context

```bash
chuck-aider                             # auto-selects patch.md or manifest.json
chuck-aider --model claude-sonnet-4-6  # all flags forwarded to aider
```

Before handing off to Aider, `chuck-aider` prints which file was loaded:

```
chuck-aider: loading patch → /path/to/.chuck/patch.md
```

**Context selection logic:**

| Condition | File passed to Aider |
|-----------|----------------------|
| ≤ 20 files changed AND patch.md ≤ 2000 words | `.chuck/patch.md` |
| > 20 files changed OR patch.md too large | `.chuck/manifest.json` |
| patch.md absent | `.chuck/manifest.json` |

Override the file-count threshold via env var:
```bash
CHUCK_AIDER_PATCH_THRESHOLD=10 chuck-aider
```

### `chuck-aider-init` — generate `.aider.conf.yml`

```bash
chuck-aider-init
```

Writes `.aider.conf.yml` at the Chuck root:

```yaml
# .aider.conf.yml — generated by chuck-aider-init
read:
  - .chuck/patch.md
auto-commits: false
gitignore: false
```

After `chuck-aider-init` runs, plain `aider` picks up Chuck context
automatically on every subsequent invocation. Re-running overwrites with
current values (idempotent).

If the project is a git repo, `chuck-aider-init` also appends `.aider*` and
`.chuck/` to `.gitignore`.

---

## Python API

```python
import chuck

# Initialize
c = chuck.init(".")

# Full snapshot — saves baseline and returns digest
digest = c.snap()                           # str
digest = c.snap(format="xml")              # XML format
digest = c.snap(budget=4000)               # list[str] if chunked
c.snap(quiet=True)                         # save only, no output

# Delta since last snap
output, auto_snapped = c.patch()           # (str, bool)
c.patch(quiet=True)                        # write patch.md only

# Diff metadata (no content)
diff = c.diff()
print(f"Changed: +{len(diff.added)} -{len(diff.removed)} ~{len(diff.modified)}")
print(f"Token delta: {diff.tokens_changed:+d}")

# Status
status = c.status()
print(f"Files: {status['file_count']}, Tokens: {status['total_tokens']:,}")

# Find all instances
instances = chuck.Chuck.ls(".")

# Reset
c.reset()

# Agent integration
written = c.integrate("claude")   # returns dict of paths written
```

---

## Output Formats

### Markdown (default)

```markdown
# Context: my-project
## Snapshot: 2026-03-02T10:00:00Z | Files: 12 | Tokens: 3,847

### src/main.py (142 tokens)
​```python
[file content]
​```
```

### XML

```xml
<chuck context="my-project" snapshot="2026-03-02T10:00:00Z" total_files="12" total_tokens="3847">
  <file path="src/main.py" tokens="142">
    <content><![CDATA[file content]]></content>
  </file>
</chuck>
```

### JSON

```json
{
  "context": "my-project",
  "snapshot": "2026-03-02T10:00:00Z",
  "files": [
    {"path": "src/main.py", "tokens": 142, "content": "..."}
  ],
  "meta": {"total_files": 12, "total_tokens": 3847}
}
```

---

## Token Budget and Chunking

When content exceeds the token budget, Chuck splits into independent chunks:

```bash
chuck snap --budget 4000
```

```python
result = c.snap(budget=4000)
if isinstance(result, list):
    for chunk in result:
        send_to_llm(chunk)
else:
    send_to_llm(result)
```

---

## `.chuck/` Folder Structure

Chuck stores **metadata only** — never copies of your files.

```
.chuck/
├── config.json        # Settings (auto_snap_threshold, etc.)
├── state.json         # Always-current lightweight state
├── patch.md           # Always-current delta content
├── manifest.json      # Latest full snapshot
└── snapshots/
    ├── 2026-03-02T10-00-00Z.json
    └── ...
```

**`state.json`** — machine-readable status for agent tools:

```json
{
  "last_snap": "2026-03-02T10:00:00Z",
  "files": 42,
  "tokens": 8432,
  "changes_since_snap": { "files": 3, "tokens_delta": 210 },
  "paths": {
    "snap": ".chuck/manifest.json",
    "patch": ".chuck/patch.md"
  }
}
```

**`patch.md`** — always-current delta content. Agent models read this on demand instead of receiving content in every prompt.

---

## Two Output Modes

**Stdout (non-agent models)** — default. Content piped directly into prompts.

```bash
chuck patch | llm "fix the auth bug"
chuck snap  | llm "review this codebase"
```

**Files on disk (agent models)** — agent reads files via tool calls on demand.

```bash
chuck patch --quiet  # writes .chuck/patch.md, no stdout
chuck snap --quiet   # writes .chuck/manifest.json, no stdout
```

---

## Usage Patterns

### Two-speed workflow

```bash
chuck snap          # Baseline before a big change
# ... refactor ...
chuck snap          # New baseline after the refactor

# ... small fix ...
chuck patch | claude "review my change"
```

### Git hooks

```bash
# .git/hooks/post-commit
chuck patch --quiet
```

### CI/CD

```yaml
- name: Snapshot baseline
  run: chuck snap --quiet

- name: Run tests and build
  run: make test build

- name: Get changes for AI review
  run: chuck patch --format json > /tmp/patch.json

- name: AI review
  run: cat /tmp/patch.json | your-ai-review-tool
```

### Monorepo

```bash
chuck snap backend    # full baseline for backend
chuck patch frontend  # delta for frontend
chuck ls .            # show all instances
```

---

## `.chuckignore`

Uses gitignore syntax:

```gitignore
# .chuckignore
dist/
*.log
secrets.env
node_modules/
```

Default patterns (always applied):
```
.git/
.chuck/
node_modules/
__pycache__/
*.pyc
.env
.env.*
```

---

## Development

```bash
git clone https://github.com/ruco-pt/chuck
cd chuck
pip install -e ".[dev]"
pytest
```

### Project structure

```
chuck/
├── pyproject.toml
├── chuck_aider.py        # chuck-aider entry point
├── chuck_aider_init.py   # chuck-aider-init entry point
├── src/
│   └── chuck/
│       ├── __init__.py   # Public API
│       ├── core.py       # Chuck class — main orchestrator
│       ├── snapshot.py   # Snapshot creation and diffing
│       ├── digest.py     # Digest generation and formatting
│       ├── chunker.py    # Token-aware content chunking
│       ├── tokens.py     # Token counting (tiktoken + fallback)
│       ├── ignore.py     # .chuckignore parser
│       ├── hasher.py     # File hashing (SHA-256)
│       ├── context.py    # File resolution utilities
│       └── cli.py        # CLI entry point
├── tests/                # 144 tests covering all modules
└── examples/
```

---

## License

MIT — see [LICENSE](LICENSE).
