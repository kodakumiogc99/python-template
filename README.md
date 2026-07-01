# Python Project Template Creator

Scaffolds a Python project with a consistent, production-ready structure.

**Stack:** uv · hatchling · ruff · mypy · pytest · pre-commit · GitHub Actions

---

## Prerequisites

**Nothing** — the launcher scripts install everything automatically.

If you already have Python, you can run `create_project.py` directly.

---

## Quick Start

### Windows

```powershell
# Allow PowerShell scripts (one-time, if not already set)
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

.\run.ps1
```

### Linux / macOS

```bash
# No chmod needed — call via bash directly
bash run.sh
```

---

## Usage

All three entry points accept the same arguments:

```
create_project.py [NAME] [OPTIONS]
```

### Entry points

| Platform | Command | Python required? |
|----------|---------|-----------------|
| Windows | `.\run.ps1 [args]` | No |
| Linux/macOS | `bash run.sh [args]` | No |
| Any (Python installed) | `python create_project.py [args]` | Yes (3.8+) |
| Any (uv installed) | `uv run create_project.py [args]` | No |

### Modes

```bash
# Interactive — prompts for everything
bash run.sh

# Pre-fill name, prompt for the rest
bash run.sh my-tool

# Non-interactive — unspecified fields use defaults
bash run.sh my-api --type api --yes

# Show help
bash run.sh --help
```

---

## Options

| Flag | Description | Default |
|------|-------------|---------|
| `NAME` | Project name (kebab-case) | prompted |
| `--type TYPE` | Project type (see below) | `cli` |
| `--python VERSION` | Python version | `3.13` |
| `--description TEXT` | Short description | `"A Python project"` |
| `--author "Name <email>"` | Author (auto-read from git config) | prompted |
| `--dotenv` | Add python-dotenv + `config.py` + `.env.example` | off |
| `--docker` | Add Dockerfile + `.dockerignore` (API only) | off |
| `--no-git` | Skip `git init` and initial commit | off |
| `--yes` / `-y` | Skip confirmation prompt | off |

### Project types

| Type | Description | Entry point |
|------|-------------|-------------|
| `cli` | CLI Application (argparse) | `uv run <name>` |
| `gui` | GUI Application (PyQt6) | `uv run <name>` |
| `api` | REST API (FastAPI + uvicorn) | `uv run <name>` → port 8000 |
| `lib` | Python Library | imported as a package |

---

## Examples

```bash
# CLI app, fully interactive
bash run.sh

# CLI app, non-interactive
bash run.sh my-tool --type cli --yes

# FastAPI service with dotenv + Docker
bash run.sh my-service --type api --python 3.12 --dotenv --docker --yes

# PyQt6 GUI app
bash run.sh my-app --type gui --yes

# Python library, no git
bash run.sh my-lib --type lib --no-git --yes
```

---

## Generated Project Structure

```
my-project/
├── src/
│   └── my_project/
│       ├── __init__.py        # __version__ + public API
│       ├── main.py            # entry point / app factory
│       └── config.py          # (if --dotenv) typed config from .env
├── tests/
│   ├── __init__.py
│   └── test_main.py
├── .github/
│   └── workflows/
│       └── ci.yml             # lint · mypy · pytest
├── .pre-commit-config.yaml    # ruff + mypy on every commit
├── Dockerfile                 # (if --docker, API only)
├── .dockerignore              # (if --docker)
├── .env.example               # (if --dotenv)
├── pyproject.toml
├── README.md
├── STRUCTURE.md
└── .gitignore
```

---

## What Happens During Creation

1. Create directories (`src/`, `tests/`, `.github/workflows/`)
2. Write all source and config files
3. `uv python install <version>` — download Python if not present
4. `uv python pin <version>` — write `.python-version`
5. `uv sync --all-groups` — create `.venv`, install all deps
6. `git init` + initial commit (unless `--no-git`)

---

## After Creation

```bash
cd my-project

uv run my-project        # run the app (cli / gui / api)
uv run pytest            # run tests
uv run mypy src/         # type check
uv run ruff check .      # lint
uv run ruff format .     # format
uv build                 # build wheel + sdist → dist/
```

### Enable pre-commit hooks

```bash
uv tool install pre-commit
pre-commit install
```

---

## Auto-install Behaviour

| Tool | Missing behaviour |
|------|-------------------|
| `uv` | Prompted to auto-install (or silent with `--yes`) |
| `git` | Skips git init with a notice |
| Python | Downloaded automatically by uv |
| All deps | Installed by `uv sync` during creation |
