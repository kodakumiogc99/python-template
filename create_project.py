#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# ///
"""
create_project.py — Python project template creator

Stack  : uv (package manager) · hatchling (build backend) · src layout
Quality: ruff (lint/format) · mypy (type checking) · pytest (tests)
Options: python-dotenv · Dockerfile · GitHub Actions CI · pre-commit hooks
Platform: Windows & Linux (auto-detected)

Usage:
  python create_project.py                              # full interactive
  python create_project.py my-tool                     # pre-fill name
  python create_project.py my-api --type api           # pre-fill name + type
  python create_project.py my-api --type api --yes     # non-interactive
  python create_project.py --help                      # show help

Non-interactive example:
  python create_project.py my-service \\
      --type api --python 3.12 \\
      --description "Internal API" --author "Alice <alice@example.com>" \\
      --dotenv --docker --yes
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import platform
from pathlib import Path
from textwrap import dedent
from typing import Optional


# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────

SUPPORTED_PYTHON_VERSIONS = ["3.10", "3.11", "3.12", "3.13"]
DEFAULT_PYTHON = SUPPORTED_PYTHON_VERSIONS[-1]

PROJECT_TYPES = ["cli", "gui", "api", "lib"]
PROJECT_TYPE_LABELS = {
    "cli": "CLI Application (argparse)",
    "gui": "GUI Application (PyQt6)",
    "api": "REST API (FastAPI)",
    "lib": "Python Library",
}

IS_WINDOWS = platform.system() == "Windows"
PLATFORM_NAME = platform.system()

# uv install locations to check after auto-install
_UV_EXTRA_PATHS = [
    Path.home() / ".local" / "bin",
    Path.home() / ".cargo" / "bin",
    *(
        [
            Path(os.environ.get("APPDATA", "")) / "uv" / "bin",
            Path(os.environ.get("USERPROFILE", "")) / ".local" / "bin",
        ]
        if IS_WINDOWS
        else []
    ),
]


# ─────────────────────────────────────────────────────────────
# AUTO-INSTALL
# ─────────────────────────────────────────────────────────────

def _refresh_path() -> None:
    """Add known uv install dirs to PATH in the current process."""
    current = os.environ.get("PATH", "")
    extras = [str(p) for p in _UV_EXTRA_PATHS if p.exists()]
    if extras:
        os.environ["PATH"] = os.pathsep.join(extras) + os.pathsep + current


def auto_install_uv() -> bool:
    """Try to install uv. Returns True if successful."""
    print()
    print("  Attempting to install uv automatically...")

    candidates: list[list[str]] = []

    if IS_WINDOWS:
        candidates.append([
            "powershell", "-ExecutionPolicy", "Bypass", "-Command",
            "irm https://astral.sh/uv/install.ps1 | iex",
        ])
    else:
        if shutil.which("curl"):
            candidates.append(["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"])
        if shutil.which("wget"):
            candidates.append(["sh", "-c", "wget -qO- https://astral.sh/uv/install.sh | sh"])

    # pip fallback (most portable)
    pip_exe = shutil.which("pip3") or shutil.which("pip")
    if pip_exe:
        candidates.append([pip_exe, "install", "--user", "uv"])
    else:
        candidates.append([sys.executable, "-m", "pip", "install", "--user", "uv"])

    for cmd in candidates:
        print(f"    $ {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            _refresh_path()
            if shutil.which("uv"):
                print("    uv installed successfully.")
                return True

    return False


# ─────────────────────────────────────────────────────────────
# DEPENDENCY CHECKS
# ─────────────────────────────────────────────────────────────

def check_requirements(skip_prompt: bool = False) -> None:
    """Verify all required tools; offer to auto-install uv if missing.

    skip_prompt=True is used in --yes / non-interactive mode to auto-install
    without asking.
    """
    errors: list[str] = []

    if sys.version_info < (3, 8):
        errors.append(
            f"Python 3.8+ required "
            f"(current: {sys.version_info.major}.{sys.version_info.minor})"
        )

    _refresh_path()
    if shutil.which("uv") is None:
        print("  uv not found in PATH.")
        if skip_prompt:
            print("  (--yes flag detected — attempting auto-install...)")
            do_install = True
        else:
            answer = input("  Auto-install uv now? [Y/n]: ").strip().lower()
            do_install = answer in ("", "y", "yes")

        if do_install:
            if not auto_install_uv():
                errors.append("'uv' could not be installed automatically")
                print()
                print("  Install manually:")
                if IS_WINDOWS:
                    print("    PowerShell: irm https://astral.sh/uv/install.ps1 | iex")
                else:
                    print("    Shell: curl -LsSf https://astral.sh/uv/install.sh | sh")
                print("    Or:    pip install uv")
        else:
            errors.append("'uv' not found in PATH")

    if errors:
        print()
        print("─" * 60)
        print("ERROR — missing requirements:")
        for err in errors:
            print(f"  • {err}")
        print("─" * 60)
        sys.exit(1)

    try:
        result = subprocess.run(
            ["uv", "--version"], capture_output=True, text=True, check=True
        )
        print(f"  {result.stdout.strip()}")
    except Exception:
        pass


def git_available() -> bool:
    return shutil.which("git") is not None


def get_git_config(key: str) -> Optional[str]:
    try:
        return (
            subprocess.check_output(
                ["git", "config", key], stderr=subprocess.DEVNULL, text=True
            ).strip()
            or None
        )
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
# CLI ARGUMENT PARSER
# ─────────────────────────────────────────────────────────────

EPILOG = """
examples:
  # Interactive (prompts for everything)
  python create_project.py

  # Pre-fill name, prompt for the rest
  python create_project.py my-tool

  # Fully non-interactive
  python create_project.py my-api --type api --python 3.12 --yes

  # API with dotenv + Docker, skip confirmation
  python create_project.py my-service --type api --dotenv --docker --yes

project types:
  cli   CLI Application (argparse)
  gui   GUI Application (PyQt6)
  api   REST API (FastAPI + uvicorn)
  lib   Python Library (no entry point)

notes:
  --docker  only applies to --type api
  --dotenv  adds python-dotenv; creates src/<module>/config.py and .env.example
  --yes     skips the final confirmation prompt (unspecified fields use defaults)
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="create_project.py",
        description="Create a Python project with uv · hatchling · ruff · mypy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EPILOG,
    )

    parser.add_argument(
        "name",
        nargs="?",
        metavar="NAME",
        help="project name in kebab-case (e.g. my-tool)",
    )
    parser.add_argument(
        "--python",
        metavar="VERSION",
        choices=SUPPORTED_PYTHON_VERSIONS,
        dest="python_version",
        help=f"Python version ({', '.join(SUPPORTED_PYTHON_VERSIONS)}) [default: {DEFAULT_PYTHON}]",
    )
    parser.add_argument(
        "--type",
        metavar="TYPE",
        choices=PROJECT_TYPES,
        dest="project_type",
        help="project type: cli, gui, api, lib [default: cli]",
    )
    parser.add_argument(
        "--description",
        metavar="TEXT",
        help='short project description [default: "A Python project"]',
    )
    parser.add_argument(
        "--author",
        metavar='"Name <email>"',
        help="author string; auto-read from git config if omitted",
    )
    parser.add_argument(
        "--no-git",
        action="store_true",
        help="skip git init and initial commit",
    )
    parser.add_argument(
        "--dotenv",
        action="store_true",
        help="add python-dotenv support (config.py + .env.example)",
    )
    parser.add_argument(
        "--docker",
        action="store_true",
        help="generate Dockerfile + .dockerignore (API type only)",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="skip confirmation prompt; use defaults for unspecified fields",
    )

    return parser


# ─────────────────────────────────────────────────────────────
# INTERACTIVE INPUT HELPERS
# ─────────────────────────────────────────────────────────────

def ask(prompt: str, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        value = input(f"  {prompt}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        print("    (required)")


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    raw = input(f"  {prompt} [{hint}]: ").strip().lower()
    if not raw:
        return default
    return raw in ("y", "yes")


def ask_project_name(prefill: Optional[str] = None) -> str:
    print()
    print("Project name")
    print("  Rules: lowercase, letters/digits/hyphens, must start with a letter")
    print("  Example: my-tool, data-pipeline, web-scraper")
    while True:
        raw = ask("Name", prefill)
        name = raw.lower()
        if not re.match(r'^[a-z][a-z0-9]*(-[a-z0-9]+)*$', name):
            print("    Invalid. Use lowercase letters, digits, and hyphens only.")
            prefill = None
            continue
        if Path(name).exists():
            print(f"    Directory '{name}' already exists.")
            prefill = None
            continue
        return name


def ask_python_version(prefill: Optional[str] = None) -> str:
    print()
    print("Python version:")
    for i, v in enumerate(SUPPORTED_PYTHON_VERSIONS, 1):
        tag = " ← default" if v == DEFAULT_PYTHON else ""
        print(f"  {i}. {v}{tag}")
    while True:
        raw = ask("Choose (number or version)", prefill or DEFAULT_PYTHON)
        if raw in SUPPORTED_PYTHON_VERSIONS:
            return raw
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(SUPPORTED_PYTHON_VERSIONS):
                return SUPPORTED_PYTHON_VERSIONS[idx]
        except ValueError:
            pass
        print(f"    Enter 1–{len(SUPPORTED_PYTHON_VERSIONS)} or a version string.")


def ask_project_type(prefill: Optional[str] = None) -> str:
    print()
    print("Project type:")
    for i, pt in enumerate(PROJECT_TYPES, 1):
        print(f"  {i}. {pt:<4}  {PROJECT_TYPE_LABELS[pt]}")
    default = prefill or "cli"
    while True:
        raw = ask("Choose (number or name)", default)
        if raw in PROJECT_TYPES:
            return raw
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(PROJECT_TYPES):
                return PROJECT_TYPES[idx]
        except ValueError:
            pass
        print(f"    Enter 1–{len(PROJECT_TYPES)} or a type name (cli/gui/api/lib).")


def ask_description(prefill: Optional[str] = None) -> str:
    print()
    return ask("Short description", prefill or "A Python project")


def ask_author(prefill: Optional[str] = None) -> str:
    print()
    if prefill is None:
        git_name = get_git_config("user.name")
        git_email = get_git_config("user.email")
        prefill = f"{git_name} <{git_email}>" if git_name and git_email else None
    return ask("Author (Name <email>)", prefill)


# ─────────────────────────────────────────────────────────────
# FILE CONTENT GENERATORS
# ─────────────────────────────────────────────────────────────

def to_module_name(project_name: str) -> str:
    return project_name.replace("-", "_")


def _author_toml(author: str) -> str:
    m = re.match(r'^(.+?)\s*<(.+?)>\s*$', author)
    if m:
        a_name, a_email = m.group(1).strip(), m.group(2).strip()
        return f'\nauthors = [\n  {{name = "{a_name}", email = "{a_email}"}},\n]'
    if author:
        return f'\nauthors = [\n  {{name = "{author}"}},\n]'
    return ""


def gen_pyproject_toml(
    name: str,
    module: str,
    description: str,
    author: str,
    python_version: str,
    project_type: str,
    use_dotenv: bool,
) -> str:
    runtime: list[str] = []
    if project_type == "gui":
        runtime.append('    "PyQt6>=6.4",')
    elif project_type == "api":
        runtime.append('    "fastapi>=0.100",')
        runtime.append('    "uvicorn[standard]>=0.20",')
    if use_dotenv and project_type != "lib":
        runtime.append('    "python-dotenv>=1.0",')
    deps_block = "[\n" + "\n".join(runtime) + "\n]" if runtime else "[]"

    dev: list[str] = [
        '    "pytest>=7",',
        '    "pytest-cov",',
        '    "ruff",',
        '    "mypy>=1.10",',
    ]
    if project_type == "api":
        dev.append('    "httpx",')
    dev_block = "[\n" + "\n".join(dev) + "\n]"

    scripts_section = (
        f'\n[project.scripts]\n{name} = "{module}.main:main"\n'
        if project_type != "lib"
        else ""
    )

    ruff_target = f"py{python_version.replace('.', '')}"
    mypy_stubs = ""
    if project_type == "gui":
        mypy_stubs = '\n[[tool.mypy.overrides]]\nmodule = "PyQt6.*"\nignore_missing_imports = true\n'
    elif project_type == "api":
        mypy_stubs = '\n[[tool.mypy.overrides]]\nmodule = "uvicorn.*"\nignore_missing_imports = true\n'

    return dedent(f"""\
        [build-system]
        requires = ["hatchling"]
        build-backend = "hatchling.build"

        [project]
        name = "{name}"
        version = "0.1.0"
        description = "{description}"{_author_toml(author)}
        readme = "README.md"
        license = {{text = "MIT"}}
        requires-python = ">={python_version}"
        dependencies = {deps_block}

        [dependency-groups]
        dev = {dev_block}
        {scripts_section}
        [tool.hatch.build.targets.wheel]
        packages = ["src/{module}"]

        [tool.ruff]
        line-length = 88
        target-version = "{ruff_target}"

        [tool.ruff.lint]
        select = ["E", "F", "I", "W"]

        [tool.mypy]
        python_version = "{python_version}"
        warn_return_any = true
        warn_unused_configs = true
        no_implicit_optional = true
        ignore_missing_imports = true
        {mypy_stubs}
        [tool.pytest.ini_options]
        testpaths = ["tests"]
        addopts = "--tb=short"
    """)


def gen_init(name: str) -> str:
    return dedent(f'''\
        """{name}."""

        __version__ = "0.1.0"
    ''')


def gen_config_py(project_type: str) -> str:
    extras = {
        "cli": '    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")\n',
        "gui": '    WINDOW_TITLE: str = os.getenv("WINDOW_TITLE", "App")\n',
        "api": '    HOST: str = os.getenv("HOST", "0.0.0.0")\n    PORT: int = int(os.getenv("PORT", "8000"))\n',
    }.get(project_type, "")

    return dedent(f'''\
        """Application configuration loaded from environment / .env file."""

        import os

        from dotenv import load_dotenv

        load_dotenv()


        class Config:
            DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
        {extras}

        config = Config()
    ''')


def gen_env_example(project_type: str) -> str:
    base = "DEBUG=false\n"
    extras = {
        "cli":  "LOG_LEVEL=INFO\n",
        "gui":  "WINDOW_TITLE=My App\n",
        "api":  "HOST=0.0.0.0\nPORT=8000\n",
    }.get(project_type, "")
    return base + extras


def gen_main_cli(name: str, use_dotenv: bool) -> str:
    dotenv_import = "from .config import config\n\n\n" if use_dotenv else ""
    dotenv_usage = "\n    if config.DEBUG:\n        print(\"[debug] running\")" if use_dotenv else ""
    return dedent(f'''\
        """Entry point for {name}."""

        import argparse

        {dotenv_import}
        def main() -> None:
            parser = argparse.ArgumentParser(description="{name}")
            parser.add_argument("--version", action="version", version="0.1.0")
            _args = parser.parse_args()
            {dotenv_usage}
            print("Hello from {name}!")


        if __name__ == "__main__":
            main()
    ''')


def gen_main_gui(name: str, use_dotenv: bool) -> str:
    dotenv_import = "from .config import config\n" if use_dotenv else ""
    title_expr = 'config.WINDOW_TITLE' if use_dotenv else f'"{name}"'
    return dedent(f'''\
        """Entry point for {name}."""

        import sys

        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow
        {dotenv_import}

        class MainWindow(QMainWindow):
            def __init__(self) -> None:
                super().__init__()
                self.setWindowTitle({title_expr})
                self.setMinimumSize(800, 600)
                label = QLabel("Hello from {name}!")
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.setCentralWidget(label)


        def main() -> None:
            app = QApplication(sys.argv)
            window = MainWindow()
            window.show()
            sys.exit(app.exec())


        if __name__ == "__main__":
            main()
    ''')


def gen_main_api(name: str, module: str, use_dotenv: bool) -> str:
    if use_dotenv:
        dotenv_import = "from .config import config\n"
        run_line = (
            f'    uvicorn.run("{module}.main:app", '
            f'host=config.HOST, port=config.PORT, reload=config.DEBUG)'
        )
    else:
        dotenv_import = ""
        run_line = f'    uvicorn.run("{module}.main:app", host="0.0.0.0", port=8000, reload=True)'

    return dedent(f'''\
        """Entry point for {name}."""

        import uvicorn
        from fastapi import FastAPI
        {dotenv_import}
        app = FastAPI(title="{name}", version="0.1.0")


        @app.get("/")
        def root() -> dict:
            return {{"message": "Hello from {name}!"}}


        @app.get("/health")
        def health() -> dict:
            return {{"status": "ok"}}


        def main() -> None:
            {run_line}


        if __name__ == "__main__":
            main()
    ''')


def gen_test_cli_gui(module: str) -> str:
    return dedent(f'''\
        from {module} import __version__


        def test_version() -> None:
            assert __version__ == "0.1.0"
    ''')


def gen_test_api(module: str) -> str:
    return dedent(f'''\
        from fastapi.testclient import TestClient

        from {module}.main import app

        client = TestClient(app)


        def test_root() -> None:
            response = client.get("/")
            assert response.status_code == 200


        def test_health() -> None:
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json() == {{"status": "ok"}}
    ''')


def gen_test_lib(module: str) -> str:
    return dedent(f'''\
        from {module} import __version__


        def test_version() -> None:
            assert __version__ == "0.1.0"
    ''')


def gen_pre_commit_config() -> str:
    return dedent("""\
        repos:
          # ruff: linting + formatting (uses its own isolated env — fast)
          - repo: https://github.com/astral-sh/ruff-pre-commit
            rev: v0.11.2
            hooks:
              - id: ruff
                args: [--fix, --exit-non-zero-on-fix]
              - id: ruff-format

          # mypy: type checking (local hook uses the project's uv env)
          - repo: local
            hooks:
              - id: mypy
                name: mypy
                entry: uv run mypy
                language: system
                types: [python]
                args: [src/]
                pass_filenames: false
    """)


def gen_github_ci(
    name: str,
    module: str,
    python_version: str,
    project_type: str,
) -> str:
    mypy_target = "src/" if project_type != "lib" else f"src/{module}/"
    extra_steps = ""
    if project_type == "api":
        extra_steps = """
      - name: Check API starts
        run: |
          uv run uvicorn {module}.main:app --host 0.0.0.0 --port 8000 &
          sleep 3
          curl -sf http://localhost:8000/health
        shell: bash
""".format(module=module)

    return dedent(f"""\
        name: CI

        on:
          push:
            branches: [main]
          pull_request:

        jobs:
          quality:
            name: Lint & Type Check
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v4

              - uses: astral-sh/setup-uv@v4
                with:
                  python-version: "{python_version}"
                  enable-cache: true

              - name: Install dependencies
                run: uv sync --all-groups

              - name: Ruff lint
                run: uv run ruff check .

              - name: Ruff format check
                run: uv run ruff format --check .

              - name: mypy
                run: uv run mypy {mypy_target}

          test:
            name: Tests (Python ${{{{ matrix.python-version }}}})
            runs-on: ubuntu-latest
            strategy:
              matrix:
                python-version: ["{python_version}"]
            steps:
              - uses: actions/checkout@v4

              - uses: astral-sh/setup-uv@v4
                with:
                  python-version: ${{{{ matrix.python-version }}}}
                  enable-cache: true

              - name: Install dependencies
                run: uv sync --all-groups
              {extra_steps}
              - name: Run tests
                run: uv run pytest --cov=src --cov-report=term-missing
    """)


def gen_dockerfile(name: str, module: str, python_version: str) -> str:
    return dedent(f"""\
        # Build stage
        FROM python:{python_version}-slim AS builder

        COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

        WORKDIR /app
        COPY pyproject.toml uv.lock* ./
        RUN uv sync --frozen --no-dev

        # Runtime stage
        FROM python:{python_version}-slim

        WORKDIR /app
        COPY --from=builder /app/.venv /app/.venv
        COPY src/ ./src/

        ENV PATH="/app/.venv/bin:$PATH"
        EXPOSE 8000

        CMD ["uvicorn", "{module}.main:app", "--host", "0.0.0.0", "--port", "8000"]
    """)


def gen_dockerignore() -> str:
    return dedent("""\
        .venv/
        __pycache__/
        *.pyc
        .pytest_cache/
        .ruff_cache/
        .mypy_cache/
        dist/
        build/
        .git/
        .env
        tests/
        *.md
    """)


def gen_gitignore() -> str:
    return dedent("""\
        # Python
        __pycache__/
        *.py[cod]
        *.egg-info/
        dist/
        build/
        .eggs/

        # uv / virtualenv
        .venv/
        .uv/
        .python-version

        # Testing / quality
        .pytest_cache/
        .coverage
        htmlcov/
        .ruff_cache/
        .mypy_cache/

        # IDE
        .vscode/
        .idea/
        *.swp

        # OS
        .DS_Store
        Thumbs.db
        desktop.ini

        # Environment
        .env
        .env.*
        !.env.example
    """)


def gen_readme(
    name: str,
    description: str,
    project_type: str,
    python_version: str,
    has_docker: bool,
) -> str:
    module = to_module_name(name)
    type_label = PROJECT_TYPE_LABELS[project_type]

    run_block = {
        "cli": f"```bash\nuv run {name}\n```",
        "gui": f"```bash\nuv run {name}\n```",
        "api": (
            f"```bash\nuv run {name}\n"
            f"# API:  http://localhost:8000\n"
            f"# Docs: http://localhost:8000/docs\n```"
        ),
        "lib": f"```python\nfrom {module} import __version__\nprint(__version__)\n```",
    }[project_type]

    docker_section = ""
    if has_docker:
        docker_section = f"""
## Docker

```bash
docker build -t {name} .
docker run -p 8000:8000 {name}
```
"""

    return dedent(f"""\
        # {name}

        > {description}

        **Type:** {type_label} | **Python:** {python_version}+

        ## Setup

        ```bash
        uv sync
        ```

        ## Run

        {run_block}

        ## Development

        ```bash
        uv run pytest                # tests
        uv run ruff check .          # lint
        uv run ruff format .         # format
        uv run mypy src/             # type check
        ```

        ## Build

        ```bash
        uv build
        ```
        {docker_section}
    """)


def gen_structure_md(
    name: str,
    module: str,
    description: str,
    project_type: str,
    python_version: str,
    author: str,
    has_dotenv: bool,
    has_docker: bool,
) -> str:
    type_label = PROJECT_TYPE_LABELS[project_type]

    dotenv_lines = (
        "│       └── config.py          # env/dotenv configuration\n"
        if has_dotenv
        else ""
    )
    api_extra = (
        "│       ├── routers/           # FastAPI APIRouter modules\n"
        "│       └── schemas/           # Pydantic request/response models\n"
        if project_type == "api"
        else ""
    )
    docker_lines = (
        "├── Dockerfile\n"
        "├── .dockerignore\n"
        if has_docker
        else ""
    )
    dotenv_example_line = "├── .env.example\n" if has_dotenv else ""

    run_desc = {
        "cli": f"`uv run {name}` — runs the CLI",
        "gui": f"`uv run {name}` — launches the PyQt6 window",
        "api": f"`uv run {name}` — starts uvicorn on http://localhost:8000",
        "lib": "imported as a package (`from {module} import ...`)",
    }[project_type]

    docker_row = (
        "| `Dockerfile` | Multi-stage image (builder + slim runtime) |\n"
        if has_docker
        else ""
    )
    dotenv_row = (
        f"| `src/{module}/config.py` | Loads `.env`, exposes typed `config` object |\n"
        f"| `.env.example` | Template for environment variables |\n"
        if has_dotenv
        else ""
    )

    return dedent(f"""\
        # Project Structure — {name}

        **Description:** {description}
        **Type:** {type_label}
        **Python:** {python_version}+
        **Author:** {author}

        ---

        ## Directory Layout

        ```
        {name}/
        ├── src/
        │   └── {module}/
        │       ├── __init__.py        # __version__ & public API
        │       └── main.py            # entry point / app factory
        {dotenv_lines}{api_extra}├── tests/
        │   ├── __init__.py
        │   └── test_main.py
        ├── .github/
        │   └── workflows/
        │       └── ci.yml             # lint · type-check · test
        ├── .pre-commit-config.yaml    # ruff + mypy hooks
        {docker_lines}{dotenv_example_line}├── pyproject.toml
        ├── README.md
        ├── STRUCTURE.md
        └── .gitignore
        ```

        ---

        ## Key Files

        | File | Purpose |
        |------|---------|
        | `pyproject.toml` | Metadata, deps, build config (hatchling), tool settings |
        | `src/{module}/__init__.py` | Exposes `__version__` and public API |
        | `src/{module}/main.py` | Application entry point |
        | `tests/test_main.py` | Pytest test suite |
        | `.github/workflows/ci.yml` | GitHub Actions: lint + mypy + test |
        | `.pre-commit-config.yaml` | Pre-commit: ruff + mypy on every commit |
        {docker_row}{dotenv_row}
        ---

        ## Toolchain

        | Tool | Role |
        |------|------|
        | [uv](https://docs.astral.sh/uv/) | Package & environment manager |
        | [hatchling](https://hatch.pypa.io/) | Build backend |
        | [ruff](https://docs.astral.sh/ruff/) | Linter + formatter |
        | [mypy](https://mypy-lang.org/) | Static type checker |
        | [pytest](https://docs.pytest.org/) | Test runner |
        | [pre-commit](https://pre-commit.com/) | Git hooks framework |

        ---

        ## Entry Point

        {run_desc}

        ---

        ## Common Commands

        ```bash
        uv sync                  # install / update all deps
        uv run {name:<20} # run
        uv run pytest            # test
        uv run ruff check .      # lint
        uv run ruff format .     # format
        uv run mypy src/         # type-check
        uv build                 # build wheel + sdist → dist/
        uv add <pkg>             # add runtime dependency
        uv add --group dev <pkg> # add dev dependency
        ```

        ## Setting Up Pre-commit

        ```bash
        uv tool install pre-commit   # install pre-commit globally
        pre-commit install           # activate hooks for this repo
        pre-commit run --all-files   # run manually on all files
        ```
    """)


# ─────────────────────────────────────────────────────────────
# PROJECT CREATION
# ─────────────────────────────────────────────────────────────

def run_cmd(
    args: list,
    cwd: Optional[Path] = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    print(f"    $ {' '.join(str(a) for a in args)}")
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if check and result.returncode != 0:
        print(f"    FAILED (exit {result.returncode})")
        if result.stderr.strip():
            for line in result.stderr.strip().splitlines():
                print(f"    {line}")
        sys.exit(1)
    return result


def step(label: str, message: str) -> None:
    print(f"\n  [{label}] {message}")


def create_project(
    name: str,
    description: str,
    author: str,
    python_version: str,
    project_type: str,
    init_git: bool,
    use_dotenv: bool,
    use_docker: bool,
) -> None:
    module = to_module_name(name)
    root = Path(name)
    total_steps = 6

    print()
    print(f"  Creating '{name}' ({PROJECT_TYPE_LABELS[project_type]})...")

    # ── 1. Directories ────────────────────────────────────────
    step(f"1/{total_steps}", "Creating directory structure")
    (root / "src" / module).mkdir(parents=True)
    (root / "tests").mkdir()
    (root / ".github" / "workflows").mkdir(parents=True)

    # ── 2. Source files ───────────────────────────────────────
    step(f"2/{total_steps}", "Writing source files")

    main_content: Optional[str] = {
        "cli": gen_main_cli(name, use_dotenv),
        "gui": gen_main_gui(name, use_dotenv),
        "api": gen_main_api(name, module, use_dotenv),
        "lib": None,
    }[project_type]

    test_content: str = {
        "cli": gen_test_cli_gui(module),
        "gui": gen_test_cli_gui(module),
        "api": gen_test_api(module),
        "lib": gen_test_lib(module),
    }[project_type]

    files: dict[str, str] = {
        "pyproject.toml": gen_pyproject_toml(
            name, module, description, author, python_version, project_type, use_dotenv
        ),
        f"src/{module}/__init__.py": gen_init(name),
        "tests/__init__.py": "",
        "tests/test_main.py": test_content,
        ".github/workflows/ci.yml": gen_github_ci(name, module, python_version, project_type),
        ".pre-commit-config.yaml": gen_pre_commit_config(),
        ".gitignore": gen_gitignore(),
        "README.md": gen_readme(name, description, project_type, python_version, use_docker),
        "STRUCTURE.md": gen_structure_md(
            name, module, description, project_type,
            python_version, author, use_dotenv, use_docker,
        ),
    }

    if main_content is not None:
        files[f"src/{module}/main.py"] = main_content

    if use_dotenv and project_type != "lib":
        files[f"src/{module}/config.py"] = gen_config_py(project_type)
        files[".env.example"] = gen_env_example(project_type)

    if use_docker and project_type == "api":
        files["Dockerfile"] = gen_dockerfile(name, module, python_version)
        files[".dockerignore"] = gen_dockerignore()

    for rel_path, content in files.items():
        (root / rel_path).write_text(content, encoding="utf-8")
        print(f"    + {rel_path}")

    # ── 3. Python version ─────────────────────────────────────
    step(f"3/{total_steps}", f"Installing Python {python_version}")
    run_cmd(["uv", "python", "install", python_version], cwd=root)
    run_cmd(["uv", "python", "pin", python_version], cwd=root)

    # ── 4. Dependencies ───────────────────────────────────────
    step(f"4/{total_steps}", "Syncing dependencies")
    run_cmd(["uv", "sync", "--all-groups"], cwd=root)

    # ── 5. Git ────────────────────────────────────────────────
    if init_git:
        step(f"5/{total_steps}", "Initializing git repository")
        run_cmd(["git", "init"], cwd=root)
        run_cmd(["git", "add", "."], cwd=root)
        run_cmd(
            ["git", "commit", "-m", "chore: initial project scaffold"],
            cwd=root,
        )
    else:
        step(f"5/{total_steps}", "Skipping git init")

    # ── 6. Done ───────────────────────────────────────────────
    step(f"6/{total_steps}", "Done")
    print()
    print("─" * 62)
    print(f"  ✓  '{name}' created successfully!")
    print()
    print("  Next steps:")
    print(f"    cd {name}")
    if project_type == "api":
        print(f"    uv run {name:<20}  # start API → http://localhost:8000")
    elif project_type in ("cli", "gui"):
        print(f"    uv run {name:<20}  # run the app")
    print(f"    uv run pytest               # run tests")
    print(f"    uv run mypy src/            # type check")
    if not init_git:
        print()
        print("  Enable pre-commit (after git init):")
        print("    uv tool install pre-commit")
        print("    pre-commit install")
    print("─" * 62)


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = build_parser()
    cli = parser.parse_args()

    # ── Banner ────────────────────────────────────────────────
    print()
    print("┌──────────────────────────────────────────────────┐")
    print("│  Python Project Template Creator                 │")
    print("│  uv · hatchling · ruff · mypy · pytest           │")
    print(f"│  Platform: {PLATFORM_NAME:<39}│")
    print("└──────────────────────────────────────────────────┘")
    print()

    # ── Requirements ──────────────────────────────────────────
    print("Checking requirements...")
    check_requirements(skip_prompt=cli.yes)

    # ── Collect inputs (CLI args + interactive fallback) ──────
    non_interactive = cli.yes and cli.name is not None

    if non_interactive:
        # All unspecified values use defaults; no prompts
        name = cli.name.lower()
        if not re.match(r'^[a-z][a-z0-9]*(-[a-z0-9]+)*$', name):
            print(f"ERROR: invalid project name '{name}'")
            sys.exit(1)
        if Path(name).exists():
            print(f"ERROR: directory '{name}' already exists")
            sys.exit(1)
        python_version = cli.python_version or DEFAULT_PYTHON
        project_type = cli.project_type or "cli"
        description = cli.description or "A Python project"
        author = cli.author or (
            f"{get_git_config('user.name')} <{get_git_config('user.email')}>"
            if get_git_config("user.name")
            else ""
        )
        init_git = not cli.no_git and git_available()
    else:
        # Interactive — use CLI args as defaults where provided
        name = ask_project_name(cli.name)
        python_version = (
            cli.python_version or ask_python_version()
        )
        project_type = cli.project_type or ask_project_type()
        description = cli.description or ask_description()
        author = ask_author(cli.author)
        print()
        init_git = (
            (not cli.no_git and ask_yes_no("Initialize git repository?"))
            if git_available()
            else False
        )
        if not git_available():
            print("  (git not found — skipping git init)")

    use_dotenv = cli.dotenv
    use_docker = cli.docker and project_type == "api"

    if cli.docker and project_type != "api":
        print("  Note: --docker is only supported for --type api; ignoring.")

    # ── Interactive options not expressible as CLI flags ──────
    if not non_interactive and not cli.dotenv and project_type != "lib":
        print()
        use_dotenv = ask_yes_no("Add python-dotenv support (config.py + .env.example)?", False)

    if not non_interactive and not cli.docker and project_type == "api":
        print()
        use_docker = ask_yes_no("Generate Dockerfile + .dockerignore?", False)

    # ── Confirm ───────────────────────────────────────────────
    module = to_module_name(name)
    print()
    print("─" * 62)
    print("  Summary:")
    print(f"    Name:         {name}  (module: {module})")
    print(f"    Python:       {python_version}")
    print(f"    Type:         {PROJECT_TYPE_LABELS[project_type]}")
    print(f"    Description:  {description}")
    print(f"    Author:       {author}")
    print(f"    Git init:     {'yes' if init_git else 'no'}")
    print(f"    python-dotenv: {'yes' if use_dotenv else 'no'}")
    print(f"    Docker:       {'yes' if use_docker else 'no'}")
    print("─" * 62)
    print()

    if not cli.yes:
        if not ask_yes_no("Create project?"):
            print("  Aborted.")
            sys.exit(0)

    create_project(
        name=name,
        description=description,
        author=author,
        python_version=python_version,
        project_type=project_type,
        init_git=init_git,
        use_dotenv=use_dotenv,
        use_docker=use_docker,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nAborted.")
        sys.exit(130)
