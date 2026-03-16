# uv Research Report for Agentic Use

Date: 2026-03-16
Primary sources: official uv docs at docs.astral.sh/uv (concepts, guides, pip interface, CLI reference)

## 1) Executive summary

uv is a Rust-based Python package and project manager designed to replace multiple tools in one binary:
- package install and resolution (pip)
- lockfile workflows (pip-tools/poetry-like)
- virtual environment creation (virtualenv)
- Python runtime installation and pinning (pyenv-like)
- CLI tool execution/installation (pipx-like)
- package build and publish helpers (build/twine-like)

Agentically, uv is most useful because it unifies project management and environment management under one command surface, while staying fast and scriptable.

## 2) Core mental model

uv has two distinct operating modes:

1. Project mode (high-level)
- Uses `pyproject.toml` as source of truth.
- Manages `.venv` and `uv.lock` automatically.
- Commands: `uv init`, `uv add`, `uv remove`, `uv lock`, `uv sync`, `uv run`.

2. pip-compatible mode (low-level)
- Works directly on environments and requirements files.
- Does not rely on pip internally.
- Commands under `uv pip ...` and `uv venv`.

Rule of thumb for agents:
- If repository has `pyproject.toml` and looks app/library oriented, prefer project mode.
- If repository is requirements-first or legacy, use `uv pip` mode.

## 3) Key files and their roles

- `pyproject.toml`: desired dependency constraints and project metadata.
- `uv.lock`: exact, universal lock for cross-platform reproducibility in uv project workflows.
- `.venv`: project environment managed by uv.
- `.python-version`: Python version request/pin used by uv commands.

Important distinction:
- `uv.lock` is uv-specific.
- `pylock.toml` (PEP 751) is interoperable and can be exported/generated in certain flows.

## 4) Command map for agents

Project lifecycle:
- `uv init` -> create new project
- `uv add <pkg>` -> add dependency, update lock, sync env
- `uv remove <pkg>` -> remove dependency, update lock, sync env
- `uv lock` -> resolve/update lockfile
- `uv sync` -> sync environment to lockfile
- `uv run <cmd|script>` -> run with lock + env consistency checks

Python runtime management:
- `uv python list`
- `uv python install <request>`
- `uv python pin <request>`
- `uv python find [request]`
- `uv python upgrade [minor]`

Tool execution/installation:
- `uvx <tool>` (alias of `uv tool run`)
- `uv tool install <tool>`
- `uv tool upgrade <tool>`
- `uv tool list`

pip-compatible operations:
- `uv venv`
- `uv pip install ...`
- `uv pip sync requirements.txt`
- `uv pip compile requirements.in -o requirements.txt`
- `uv pip list/tree/check`

Build/publish/export:
- `uv build`
- `uv publish`
- `uv export -o requirements.txt|pylock.toml|cyclonedx.json`

## 5) Resolution and locking behavior that agents must know

Universal resolution:
- `uv.lock` is resolved universally (cross-platform/cross-python markers), not just current machine.
- This can produce multiple versions of same package in lock with markers.

Preference behavior:
- Existing locked versions are preferred until incompatible or explicitly upgraded.
- Use `--upgrade` or `--upgrade-package` when drift to newer versions is intended.

Resolution strategies:
- Default: `highest` (latest compatible)
- Alternatives: `lowest`, `lowest-direct`
- Useful for CI compatibility testing against lower bounds.

Pre-release behavior:
- Conservative by default.
- Broaden with `--prerelease allow` when needed.

Index security:
- Default index strategy favors first matching index (`first-index`) to reduce dependency confusion risks.

Reproducibility knobs:
- `--locked`: require lockfile up to date, fail otherwise.
- `--frozen`: use existing lockfile as truth, do not update it.
- `--exclude-newer` and package-specific variants for time-based reproducibility/cooldowns.

## 6) Python version behavior that often surprises agents

Managed vs system Python:
- uv can use system Pythons and also install its own managed Pythons.
- By default, uv prefers managed if available, but can still use system.

Control flags:
- `--managed-python`: only managed
- `--no-managed-python`: only system
- `--no-python-downloads`: disable automatic interpreter downloads

Version request formats are rich:
- exact versions, ranges, impl-specific requests, variant requests (freethreaded/debug), and interpreter paths.

Pinning:
- `.python-version` influences default interpreter selection for commands.
- `uv python pin` writes this file.

## 7) Tools mode (uvx and uv tool) for agent workflows

`uvx` behavior:
- Runs tools in isolated, cached ephemeral environments.
- Great for one-off commands in CI/dev shells.

`uv tool install` behavior:
- Creates persistent isolated tool env and exposes executables on PATH.

Agent guidance:
- Prefer `uvx` for transient steps.
- Prefer `uv tool install` if repeated use or required by external scripts.
- Do not mutate tool envs manually with pip.

## 8) Cache model and implications

Cache characteristics:
- Aggressive global cache for wheels/sdists/git metadata.
- Safe for concurrent uv commands (thread-safe + environment lock for install targets).

Useful cache commands:
- `uv cache dir`
- `uv cache clean`
- `uv cache clean <package>`
- `uv cache prune`
- `uv cache prune --ci` (recommended in CI end step)

Refresh/reinstall controls:
- `--refresh`, `--refresh-package`
- `--reinstall`, `--reinstall-package`

Performance note:
- Cache and env on same filesystem improves link-mode efficiency.

## 9) Agent decision recipes

Recipe A: Existing uv project, run command safely
1. `uv run <cmd>`
2. If lock drift errors: run `uv lock` (or `uv sync`) according to policy.
3. For CI reproducibility: use `uv run --locked ...`.

Recipe B: Add dependency in uv project
1. `uv add <pkg>`
2. If specific upgrade only: `uv lock --upgrade-package <pkg>`.
3. Validate with `uv run` tests/lint.

Recipe C: Requirements-based repo migration path
1. `uv venv`
2. `uv pip compile requirements.in -o requirements.txt` (optional lock style)
3. `uv pip sync requirements.txt`
4. Later migrate to project mode (`uv init`, dependency import, lock).

Recipe D: Need specific Python quickly
1. `uv python install <request>` (or rely on auto-download)
2. `uv python pin <request>` in project
3. `uv run --python <request> ...` when overriding per command

Recipe E: One-off tooling
1. `uvx <tool> ...`
2. For persistent use: `uv tool install <tool>`

## 10) CI patterns

Strict and reproducible install:
- `uv sync --locked`

Upgrade job:
- `uv lock --upgrade` (or `--upgrade-package ...`), then tests.

Lower-bound compatibility job (library contexts):
- Use resolution mode `lowest` or `lowest-direct` in relevant compile/install flows.

Cache strategy:
- Persist uv cache between runs.
- Run `uv cache prune --ci` before saving cache artifact.

## 11) Common pitfalls and mitigations

1. Mixing project mode and manual environment mutation
- Pitfall: `uv pip install` into a uv-managed project env can create drift.
- Mitigation: prefer `uv add/remove` in project mode.

2. Assuming pip parity in edge cases
- Pitfall: expecting exact pip behavior for uncommon flags/flows.
- Mitigation: check uv pip compatibility docs for edge semantics.

3. Hidden interpreter changes
- Pitfall: auto Python downloads in constrained environments.
- Mitigation: set `--no-python-downloads` or configure policy.

4. Overly broad multi-index behavior
- Pitfall: weakening dependency confusion protection.
- Mitigation: keep default index strategy unless intentionally changed.

5. Broken tool env via manual edits
- Pitfall: mutating tool venv by hand.
- Mitigation: reinstall/upgrade via uv tool commands only.

## 12) Recommended default policy for autonomous agents

- Prefer project mode commands when `pyproject.toml` exists.
- Use `uv run` for command execution in project repos.
- Use `--locked` in CI or when deterministic behavior is required.
- Do not edit `uv.lock` manually.
- Avoid direct mutation of `.venv` via ad-hoc pip operations in uv-managed projects.
- Keep Python version explicit via `.python-version` for team consistency.
- Use `uvx` for ephemeral tools.

## 13) Practical quick-reference snippets

Install uv on macOS/Linux:
- `curl -LsSf https://astral.sh/uv/install.sh | sh`

Start project:
- `uv init`
- `uv add requests`
- `uv run python -c "import requests; print(requests.__version__)"`

Lock/sync:
- `uv lock`
- `uv sync`
- `uv sync --locked`

pip-style lock and sync:
- `uv pip compile requirements.in -o requirements.txt`
- `uv pip sync requirements.txt`

Python pin:
- `uv python pin 3.12`

Tooling:
- `uvx ruff check .`
- `uv tool install ruff`

## 14) Sources consulted

- https://docs.astral.sh/uv/
- https://docs.astral.sh/uv/getting-started/installation/
- https://docs.astral.sh/uv/guides/projects/
- https://docs.astral.sh/uv/concepts/projects/layout/
- https://docs.astral.sh/uv/concepts/resolution/
- https://docs.astral.sh/uv/concepts/cache/
- https://docs.astral.sh/uv/concepts/tools/
- https://docs.astral.sh/uv/concepts/python-versions/
- https://docs.astral.sh/uv/pip/
- https://docs.astral.sh/uv/reference/cli/
