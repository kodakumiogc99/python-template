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
# Interactive — arrow-key menus for version, type, and license
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
| `--output DIR` | Directory where the project folder is created | one level above the script |
| `--type TYPE [TYPE ...]` | One or more project types (see below) | `cli` |
| `--python VERSION` | Python version | `3.13` |
| `--license LICENSE` | License identifier (see below) | `MIT` |
| `--description TEXT` | Short description | `"A Python project"` |
| `--author "Name <email>"` | Author (auto-read from git config) | prompted |
| `--dotenv` | Add python-dotenv + `config.py` + `.env.example` | off |
| `--docker` | Add Dockerfile + `.dockerignore` (API only) | off |
| `--no-git` | Skip `git init` and initial commit | off |
| `--yes` / `-y` | Skip confirmation prompt | off |

### Project types

Types can be **combined** — e.g. `--type cli api`.

| Type | Description | Entry point |
|------|-------------|-------------|
| `cli` | CLI Application (argparse) | `uv run <name>` |
| `gui` | GUI Application (PyQt6) | `uv run <name>` |
| `api` | REST API (FastAPI + uvicorn) | `uv run <name>` → port 8000 |
| `lib` | Python Library | imported as a package |

**Single type** → `src/module/main.py` + script `name`  
**Multiple types** → `src/module/cli.py`, `src/module/api.py`, ... + scripts `name-cli`, `name-api`, ...

### Licenses

| ID | Description |
|----|-------------|
| `MIT` | Permissive, most popular |
| `Apache-2.0` | Permissive, patent protection |
| `GPL-3.0` | Copyleft, source sharing required |
| `AGPL-3.0` | Copyleft + network use clause |
| `BSD-3-Clause` | Permissive, no endorsement |
| `BSD-2-Clause` | Permissive, simplified |
| `ISC` | Like MIT, very short |
| `MPL-2.0` | Weak copyleft, file-based |
| `Unlicense` | Public domain dedication |
| `Proprietary` | All rights reserved |

---

## Examples

```bash
# CLI app, fully interactive (arrow-key menus)
bash run.sh

# CLI app, non-interactive
bash run.sh my-tool --type cli --yes

# FastAPI service with dotenv + Docker
bash run.sh my-service --type api --python 3.12 --dotenv --docker --yes

# CLI + REST API combined
bash run.sh my-svc --type cli api --dotenv --yes

# PyQt6 GUI app, Apache license
bash run.sh my-app --type gui --license Apache-2.0 --yes

# Python library, MIT, no git
bash run.sh my-lib --type lib --license MIT --no-git --yes
```

---

## Generated Project Structure

```
my-project/
├── src/
│   └── my_project/
│       ├── __init__.py        # __version__ + public API
│       ├── main.py            # entry point (single type)
│       ├── cli.py             # (multi-type: CLI entry)
│       ├── api.py             # (multi-type: API entry)
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
├── LICENSE                    # (not generated for Proprietary)
├── pyproject.toml
├── README.md
├── STRUCTURE.md
└── .gitignore
```

---

## What Happens During Creation

1. Create directories (`src/`, `tests/`, `.github/workflows/`)
2. Write all source, config, and license files
3. `uv python install <version>` — download Python if not present
4. `uv python pin <version>` — write `.python-version`
5. `uv sync --all-groups` — create `.venv`, install all deps
6. `git init` + initial commit (unless `--no-git`)

---

## After Creation

```bash
cd my-project

uv run my-project        # run (single type)
uv run my-project-cli    # run CLI (multi-type)
uv run my-project-api    # run API (multi-type) → http://localhost:8000

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

---

## `.gitignore` includes

- Python caches, build artifacts, `.venv`
- `.env` and `*.env.*` (except `.env.example`)
- Private keys: `*.pem`, `*.key`, `*.pfx`, `*.p12`, `id_rsa*`
- Credential files: `credentials*.json`, `secrets*.json`, `service-account*.json`
- `.claude/` (Claude Code project config)
- IDE files: `.vscode/`, `.idea/`
