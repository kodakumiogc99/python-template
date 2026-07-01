#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# ///
"""
create_project.py — Python project template creator

Stack  : uv · hatchling · src layout
Quality: ruff · mypy · pytest · pre-commit · GitHub Actions
Options: python-dotenv · Dockerfile · multiple project types · license
Platform: Windows & Linux (auto-detected)

Usage:
  python create_project.py                              # full interactive
  python create_project.py my-tool                     # pre-fill name
  python create_project.py my-api --type api           # pre-fill type
  python create_project.py my-svc --type api cli --yes # non-interactive
  python create_project.py --help
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
    "api": "REST API (FastAPI + uvicorn)",
    "lib": "Python Library",
}

# (id, display label)
LICENSES: list[tuple[str, str]] = [
    ("MIT",          "MIT — permissive, most popular"),
    ("Apache-2.0",   "Apache 2.0 — permissive, patent protection"),
    ("GPL-3.0",      "GPL v3 — copyleft, source sharing required"),
    ("AGPL-3.0",     "AGPL v3 — copyleft + network use clause"),
    ("BSD-3-Clause", "BSD 3-Clause — permissive, no endorsement"),
    ("BSD-2-Clause", "BSD 2-Clause — permissive, simplified"),
    ("ISC",          "ISC — like MIT, very short"),
    ("MPL-2.0",      "MPL 2.0 — weak copyleft, file-based"),
    ("Unlicense",    "Unlicense — public domain dedication"),
    ("Proprietary",  "Proprietary — all rights reserved"),
]
LICENSE_IDS = [l[0] for l in LICENSES]

IS_WINDOWS = platform.system() == "Windows"
PLATFORM_NAME = platform.system()

_UV_EXTRA_PATHS = [
    Path.home() / ".local" / "bin",
    Path.home() / ".cargo" / "bin",
    *(
        [
            Path(os.environ.get("APPDATA", "")) / "uv" / "bin",
            Path(os.environ.get("USERPROFILE", "")) / ".local" / "bin",
        ]
        if IS_WINDOWS else []
    ),
]


# ─────────────────────────────────────────────────────────────
# TERMINAL UI  (arrow-key menus)
# ─────────────────────────────────────────────────────────────

def _enable_ansi() -> None:
    """Enable VT/ANSI processing on Windows."""
    if not IS_WINDOWS:
        return
    try:
        import ctypes
        k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = k32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        k32.GetConsoleMode(handle, ctypes.byref(mode))
        k32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        os.system("")


def _read_key_windows() -> str:
    import msvcrt
    ch = msvcrt.getwch()
    if ch in ('\x00', '\xe0'):
        ch2 = msvcrt.getwch()
        return {'H': 'UP', 'P': 'DOWN', 'K': 'LEFT', 'M': 'RIGHT'}.get(ch2, f'_W{ch2}')
    if ch == '\r':
        return 'ENTER'
    if ch == ' ':
        return 'SPACE'
    if ch == '\x03':
        raise KeyboardInterrupt
    return ch


def _read_key_unix() -> str:
    import tty, termios, select
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == '\x1b':
            r, _, _ = select.select([sys.stdin], [], [], 0.05)
            if r:
                ch2 = sys.stdin.read(1)
                if ch2 == '[':
                    r, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if r:
                        ch3 = sys.stdin.read(1)
                        return {'A': 'UP', 'B': 'DOWN', 'C': 'RIGHT', 'D': 'LEFT'}.get(ch3, f'_E{ch3}')
            return 'ESC'
        if ch in ('\r', '\n'):
            return 'ENTER'
        if ch == ' ':
            return 'SPACE'
        if ch == '\x03':
            raise KeyboardInterrupt
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _read_key() -> str:
    return _read_key_windows() if IS_WINDOWS else _read_key_unix()


def _menu_fallback(
    title: str,
    options: list[tuple[str, str]],
    multi: bool,
    default: Optional[list[str]],
) -> list[str]:
    """Numbered fallback when stdin is not a TTY."""
    default = default or [options[0][0]]
    print(f"\n  {title}:")
    for i, (k, lbl) in enumerate(options, 1):
        marker = " [default]" if k in default else ""
        print(f"    {i}. {lbl}{marker}")

    if multi:
        hint, default_str = "Numbers (space-separated)", " ".join(
            str(i) for i, (k, _) in enumerate(options, 1) if k in default
        )
    else:
        hint, default_str = "Number", str(
            next(i for i, (k, _) in enumerate(options, 1) if k in default)
        )

    while True:
        raw = _ask(hint, default_str)
        try:
            idxs = [int(x) - 1 for x in raw.split()] if multi else [int(raw) - 1]
            if idxs and all(0 <= i < len(options) for i in idxs):
                return [options[i][0] for i in idxs]
        except ValueError:
            pass
        print(f"    Enter number(s) 1–{len(options)}.")


def select_menu(
    title: str,
    options: list[tuple[str, str]],
    multi: bool = False,
    default: Optional[list[str]] = None,
) -> list[str]:
    """
    Arrow-key selection menu. Returns list of selected keys.
    Falls back to numbered input when stdin is not a TTY.
    """
    if not sys.stdin.isatty():
        return _menu_fallback(title, options, multi, default)

    _enable_ansi()

    n = len(options)
    selected: set[str] = set(default) if default else {options[0][0]}
    cursor = next(
        (i for i, (k, _) in enumerate(options) if k in selected), 0
    )
    hint = (
        "[↑↓] navigate  [Space] toggle  [Enter] confirm"
        if multi else
        "[↑↓] navigate  [Enter] select"
    )

    def render() -> int:
        count = 0
        print()
        count += 1
        print(f"  {title}:")
        count += 1
        for i, (k, lbl) in enumerate(options):
            ptr = "▶" if i == cursor else " "
            dot = "●" if k in selected else "○"
            print(f"    {ptr} {dot}  {lbl}")
            count += 1
        print()
        count += 1
        print(f"    {hint}")
        count += 1
        sys.stdout.flush()
        return count

    total = render()

    while True:
        key = _read_key()

        if key == "UP":
            cursor = (cursor - 1) % n
            if not multi:
                selected = {options[cursor][0]}
        elif key == "DOWN":
            cursor = (cursor + 1) % n
            if not multi:
                selected = {options[cursor][0]}
        elif key == "SPACE" and multi:
            k = options[cursor][0]
            if k in selected and len(selected) > 1:
                selected.discard(k)
            elif k not in selected:
                selected.add(k)
        elif key == "ENTER":
            if not multi:
                selected = {options[cursor][0]}
            if selected:
                break

        sys.stdout.write(f"\033[{total}A\033[0J")
        sys.stdout.flush()
        total = render()

    sys.stdout.write(f"\033[{total}A\033[0J")
    sys.stdout.flush()

    result = [k for k, _ in options if k in selected]
    labels = [lbl for k, lbl in options if k in selected]
    print(f"\n  {title}: {', '.join(labels)}")
    return result


# ─────────────────────────────────────────────────────────────
# AUTO-INSTALL
# ─────────────────────────────────────────────────────────────

def _refresh_path() -> None:
    current = os.environ.get("PATH", "")
    extras = [str(p) for p in _UV_EXTRA_PATHS if p.exists()]
    if extras:
        os.environ["PATH"] = os.pathsep.join(extras) + os.pathsep + current


def auto_install_uv() -> bool:
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
    pip_exe = shutil.which("pip3") or shutil.which("pip")
    candidates.append([pip_exe or sys.executable, "-m", "pip", "install", "--user", "uv"])

    for cmd in candidates:
        print(f"    $ {' '.join(cmd)}")
        if subprocess.run(cmd, capture_output=True).returncode == 0:
            _refresh_path()
            if shutil.which("uv"):
                print("    uv installed successfully.")
                return True
    return False


# ─────────────────────────────────────────────────────────────
# DEPENDENCY CHECKS
# ─────────────────────────────────────────────────────────────

def check_requirements(skip_prompt: bool = False) -> None:
    errors: list[str] = []
    if sys.version_info < (3, 8):
        errors.append(
            f"Python 3.8+ required (current: {sys.version_info.major}.{sys.version_info.minor})"
        )

    _refresh_path()
    if shutil.which("uv") is None:
        print("  uv not found in PATH.")
        do_install = True if skip_prompt else (
            input("  Auto-install uv now? [Y/n]: ").strip().lower() in ("", "y", "yes")
        )
        if skip_prompt:
            print("  (--yes flag set — attempting auto-install...)")
        if do_install:
            if not auto_install_uv():
                errors.append("'uv' could not be installed automatically")
                print("  Install manually:")
                if IS_WINDOWS:
                    print("    irm https://astral.sh/uv/install.ps1 | iex")
                else:
                    print("    curl -LsSf https://astral.sh/uv/install.sh | sh")
        else:
            errors.append("'uv' not found in PATH")

    if errors:
        print("\n" + "─" * 60)
        print("ERROR — missing requirements:")
        for e in errors:
            print(f"  • {e}")
        print("─" * 60)
        sys.exit(1)

    try:
        r = subprocess.run(["uv", "--version"], capture_output=True, text=True, check=True)
        print(f"  {r.stdout.strip()}")
    except Exception:
        pass


def git_available() -> bool:
    return shutil.which("git") is not None


def get_git_config(key: str) -> Optional[str]:
    try:
        return subprocess.check_output(
            ["git", "config", key], stderr=subprocess.DEVNULL, text=True
        ).strip() or None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
# CLI ARGUMENT PARSER
# ─────────────────────────────────────────────────────────────

EPILOG = """
examples:
  python create_project.py                              # interactive
  python create_project.py my-tool                     # pre-fill name
  python create_project.py my-api --type api --yes     # non-interactive
  python create_project.py my-svc --type cli api --dotenv --yes
  python create_project.py my-lib --type lib --license MIT --yes
  python create_project.py my-tool --output ~/projects # custom output dir

project types (can combine):
  cli   CLI Application (argparse)
  gui   GUI Application (PyQt6)
  api   REST API (FastAPI + uvicorn)
  lib   Python Library (no entry point)

  Single type  → src/module/main.py + script 'name'
  Multi-type   → src/module/cli.py, src/module/api.py + scripts 'name-cli', 'name-api'

notes:
  --output  where to create the project (default: one level above this script)
  --docker  only applies when api is one of the selected types
  --dotenv  adds python-dotenv; creates src/<module>/config.py and .env.example
  --yes     skips confirmation; unspecified fields use defaults
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="create_project.py",
        description="Create a Python project with uv · hatchling · ruff · mypy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EPILOG,
    )
    parser.add_argument("name", nargs="?", metavar="NAME",
                        help="project name in kebab-case (e.g. my-tool)")
    parser.add_argument("--python", metavar="VERSION", choices=SUPPORTED_PYTHON_VERSIONS,
                        dest="python_version",
                        help=f"Python version [default: {DEFAULT_PYTHON}]")
    parser.add_argument("--type", nargs="+", metavar="TYPE", choices=PROJECT_TYPES,
                        dest="project_types",
                        help="one or more project types: cli gui api lib")
    parser.add_argument("--license", metavar="LICENSE", choices=LICENSE_IDS,
                        dest="license_id",
                        help=f"license ({', '.join(LICENSE_IDS)}) [default: MIT]")
    parser.add_argument("--description", metavar="TEXT",
                        help='short description [default: "A Python project"]')
    parser.add_argument("--author", metavar='"Name <email>"',
                        help="author; auto-read from git config if omitted")
    parser.add_argument("--no-git", action="store_true",
                        help="skip git init")
    parser.add_argument("--dotenv", action="store_true",
                        help="add python-dotenv (config.py + .env.example)")
    parser.add_argument("--docker", action="store_true",
                        help="generate Dockerfile + .dockerignore (requires api type)")
    parser.add_argument("--output", metavar="DIR",
                        help="directory where the project folder is created "
                             "[default: one level above this script]")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="skip confirmation; use defaults for unspecified fields")
    return parser


# ─────────────────────────────────────────────────────────────
# INTERACTIVE INPUT HELPERS
# ─────────────────────────────────────────────────────────────

def default_output_dir() -> Path:
    """One level above this script — sibling of the python/ directory."""
    return Path(__file__).resolve().parent.parent


def ask_output_dir(prefill: Optional[str] = None) -> Path:
    default = Path(prefill).expanduser().resolve() if prefill else default_output_dir()
    print()
    raw = _ask("Output directory (project will be created inside it)", str(default))
    path = Path(raw).expanduser().resolve()
    if not path.exists():
        print(f"    '{path}' does not exist.")
        if ask_yes_no("    Create it?"):
            path.mkdir(parents=True, exist_ok=True)
        else:
            print("  Aborted.")
            sys.exit(0)
    elif not path.is_dir():
        print(f"  ERROR: '{path}' is not a directory.")
        sys.exit(1)
    return path


def _ask(prompt: str, default: Optional[str] = None) -> str:
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
    return default if not raw else raw in ("y", "yes")


def ask_project_name(prefill: Optional[str] = None, output_dir: Optional[Path] = None) -> str:
    print()
    print("Project name")
    print("  Rules: lowercase, letters/digits/hyphens, start with a letter")
    print("  Example: my-tool, data-pipeline, web-scraper")
    while True:
        name = _ask("Name", prefill).lower()
        if not re.match(r'^[a-z][a-z0-9]*(-[a-z0-9]+)*$', name):
            print("    Invalid. Use lowercase letters, digits, and hyphens only.")
            prefill = None
            continue
        dest = (output_dir or Path.cwd()) / name
        if dest.exists():
            print(f"    Directory '{dest}' already exists.")
            prefill = None
            continue
        return name


def ask_python_version(prefill: Optional[str] = None) -> str:
    opts = [(v, f"{v}{'  ← default' if v == DEFAULT_PYTHON else ''}")
            for v in SUPPORTED_PYTHON_VERSIONS]
    result = select_menu("Python version", opts, multi=False,
                         default=[prefill or DEFAULT_PYTHON])
    return result[0]


def ask_project_types(prefill: Optional[list[str]] = None) -> list[str]:
    opts = [(t, PROJECT_TYPE_LABELS[t]) for t in PROJECT_TYPES]
    return select_menu("Project types", opts, multi=True,
                       default=prefill or ["cli"])


def ask_license(prefill: Optional[str] = None) -> str:
    result = select_menu("License", LICENSES, multi=False,
                         default=[prefill or "MIT"])
    return result[0]


def ask_description(prefill: Optional[str] = None) -> str:
    print()
    return _ask("Short description", prefill or "A Python project")


def ask_author(prefill: Optional[str] = None) -> str:
    print()
    if prefill is None:
        gn, ge = get_git_config("user.name"), get_git_config("user.email")
        prefill = f"{gn} <{ge}>" if gn and ge else None
    return _ask("Author (Name <email>)", prefill)


# ─────────────────────────────────────────────────────────────
# LICENSE FILE GENERATOR
# ─────────────────────────────────────────────────────────────

def gen_license_file(license_id: str, year: int, author: str) -> Optional[str]:
    """Returns LICENSE file content. None means no file (proprietary uses NOTICE)."""
    m = re.match(r'^(.+?)\s*<.+?>\s*$', author)
    name = m.group(1).strip() if m else author

    texts: dict[str, str] = {
        "MIT": dedent(f"""\
            MIT License

            Copyright (c) {year} {name}

            Permission is hereby granted, free of charge, to any person obtaining a copy
            of this software and associated documentation files (the "Software"), to deal
            in the Software without restriction, including without limitation the rights
            to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
            copies of the Software, and to permit persons to whom the Software is
            furnished to do so, subject to the following conditions:

            The above copyright notice and this permission notice shall be included in all
            copies or substantial portions of the Software.

            THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
            IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
            FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
            AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
            LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
            OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
            SOFTWARE.
        """),
        "ISC": dedent(f"""\
            ISC License

            Copyright (c) {year} {name}

            Permission to use, copy, modify, and/or distribute this software for any
            purpose with or without fee is hereby granted, provided that the above
            copyright notice and this permission notice appear in all copies.

            THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
            REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
            AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
            INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
            LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
            OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
            PERFORMANCE OF THIS SOFTWARE.
        """),
        "BSD-2-Clause": dedent(f"""\
            BSD 2-Clause License

            Copyright (c) {year}, {name}
            All rights reserved.

            Redistribution and use in source and binary forms, with or without
            modification, are permitted provided that the following conditions are met:

            1. Redistributions of source code must retain the above copyright notice, this
               list of conditions and the following disclaimer.

            2. Redistributions in binary form must reproduce the above copyright notice,
               this list of conditions and the following disclaimer in the documentation
               and/or other materials provided with the distribution.

            THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
            AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
            IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
            DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
            FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
            DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
            SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
            CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
            OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
            OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
        """),
        "BSD-3-Clause": dedent(f"""\
            BSD 3-Clause License

            Copyright (c) {year}, {name}
            All rights reserved.

            Redistribution and use in source and binary forms, with or without
            modification, are permitted provided that the following conditions are met:

            1. Redistributions of source code must retain the above copyright notice, this
               list of conditions and the following disclaimer.

            2. Redistributions in binary form must reproduce the above copyright notice,
               this list of conditions and the following disclaimer in the documentation
               and/or other materials provided with the distribution.

            3. Neither the name of the copyright holder nor the names of its contributors
               may be used to endorse or promote products derived from this software
               without specific prior written permission.

            THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
            AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
            IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
            DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
            FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
            DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
            SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
            CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
            OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
            OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
        """),
        "Unlicense": dedent("""\
            This is free and unencumbered software released into the public domain.

            Anyone is free to copy, modify, publish, use, compile, sell, or distribute
            this software, either in source code form or as a compiled binary, for any
            purpose, commercial or non-commercial, and by any means.

            In jurisdictions that recognize copyright laws, the author or authors of this
            software dedicate any and all copyright interest in the software to the public
            domain. We make this dedication for the benefit of the public at large and to
            the detriment of our heirs and successors. We intend this dedication to be an
            overt act of relinquishment in perpetuity of all present and future rights to
            this software under copyright law.

            THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
            IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
            FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
            AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
            ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
            WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

            For more information, please refer to <https://unlicense.org>
        """),
        "Apache-2.0": dedent(f"""\
            SPDX-License-Identifier: Apache-2.0

            Copyright (c) {year} {name}

            Licensed under the Apache License, Version 2.0 (the "License");
            you may not use this file except in compliance with the License.
            You may obtain a copy of the License at

                https://www.apache.org/licenses/LICENSE-2.0

            Unless required by applicable law or agreed to in writing, software
            distributed under the License is distributed on an "AS IS" BASIS,
            WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
            See the License for the specific language governing permissions and
            limitations under the License.
        """),
        "GPL-3.0": dedent(f"""\
            SPDX-License-Identifier: GPL-3.0-only

            Copyright (c) {year} {name}

            This program is free software: you can redistribute it and/or modify it under
            the terms of the GNU General Public License as published by the Free Software
            Foundation, version 3.

            This program is distributed in the hope that it will be useful, but WITHOUT
            ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
            FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

            You should have received a copy of the GNU General Public License along with
            this program. If not, see <https://www.gnu.org/licenses/gpl-3.0.html>.
        """),
        "AGPL-3.0": dedent(f"""\
            SPDX-License-Identifier: AGPL-3.0-only

            Copyright (c) {year} {name}

            This program is free software: you can redistribute it and/or modify it under
            the terms of the GNU Affero General Public License as published by the Free
            Software Foundation, version 3.

            This program is distributed in the hope that it will be useful, but WITHOUT
            ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
            FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for more
            details.

            You should have received a copy of the GNU Affero General Public License
            along with this program. If not, see
            <https://www.gnu.org/licenses/agpl-3.0.html>.
        """),
        "MPL-2.0": dedent(f"""\
            SPDX-License-Identifier: MPL-2.0

            Copyright (c) {year} {name}

            This Source Code Form is subject to the terms of the Mozilla Public License,
            v. 2.0. If a copy of the MPL was not distributed with this file, You can
            obtain one at https://mozilla.org/MPL/2.0/.
        """),
        "Proprietary": dedent(f"""\
            Copyright (c) {year} {name}. All Rights Reserved.

            This software and associated documentation files (the "Software") are
            proprietary and confidential. Unauthorized copying, modification, distribution,
            or use of this software, in whole or in part, without prior written permission
            from the copyright holder is strictly prohibited.
        """),
    }
    return texts.get(license_id)


# ─────────────────────────────────────────────────────────────
# FILE CONTENT GENERATORS
# ─────────────────────────────────────────────────────────────

def to_module_name(name: str) -> str:
    return name.replace("-", "_")


def _author_toml(author: str) -> str:
    m = re.match(r'^(.+?)\s*<(.+?)>\s*$', author)
    if m:
        return f'\nauthors = [\n  {{name = "{m.group(1).strip()}", email = "{m.group(2).strip()}"}},\n]'
    if author:
        return f'\nauthors = [\n  {{name = "{author}"}},\n]'
    return ""


def _executable_types(types: list[str]) -> list[str]:
    return [t for t in types if t != "lib"]


def gen_pyproject_toml(
    name: str,
    module: str,
    description: str,
    author: str,
    python_version: str,
    types: list[str],
    license_id: str,
    use_dotenv: bool,
) -> str:
    exe = _executable_types(types)

    # Runtime dependencies (combined, deduplicated)
    runtime: list[str] = []
    if "gui" in types:
        runtime.append('    "PyQt6>=6.4",')
    if "api" in types:
        runtime.append('    "fastapi>=0.100",')
        runtime.append('    "uvicorn[standard]>=0.20",')
    if use_dotenv and exe:
        runtime.append('    "python-dotenv>=1.0",')
    deps_block = "[\n" + "\n".join(runtime) + "\n]" if runtime else "[]"

    # Dev dependencies
    dev = ['    "pytest>=7",', '    "pytest-cov",', '    "ruff",', '    "mypy>=1.10",']
    if "api" in types:
        dev.append('    "httpx",')
    dev_block = "[\n" + "\n".join(dev) + "\n]"

    # Scripts section — always includes `help`
    help_entry = f'help = "{module}._help:main"'
    if not exe:
        scripts_section = f'\n[project.scripts]\n{help_entry}\n'
    elif len(exe) == 1:
        scripts_section = f'\n[project.scripts]\n{name} = "{module}.main:main"\n{help_entry}\n'
    else:
        entries = "\n".join(f'{name}-{t} = "{module}.{t}:main"' for t in exe)
        scripts_section = f'\n[project.scripts]\n{entries}\n{help_entry}\n'

    # mypy overrides
    overrides: list[str] = []
    if "gui" in types:
        overrides.append('[[tool.mypy.overrides]]\nmodule = "PyQt6.*"\nignore_missing_imports = true')
    if "api" in types:
        overrides.append('[[tool.mypy.overrides]]\nmodule = "uvicorn.*"\nignore_missing_imports = true')
    mypy_extra = ("\n\n" + "\n\n".join(overrides)) if overrides else ""

    ruff_target = f"py{python_version.replace('.', '')}"
    # SPDX id mapping
    spdx_map = {"GPL-3.0": "GPL-3.0-only", "AGPL-3.0": "AGPL-3.0-only"}
    spdx = spdx_map.get(license_id, license_id)

    return dedent(f"""\
        [build-system]
        requires = ["hatchling"]
        build-backend = "hatchling.build"

        [project]
        name = "{name}"
        version = "0.1.0"
        description = "{description}"{_author_toml(author)}
        readme = "README.md"
        license = {{text = "{spdx}"}}
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
        {mypy_extra}

        [tool.pytest.ini_options]
        testpaths = ["tests"]
        addopts = "--tb=short"
    """)


def gen_help_py(name: str, module: str) -> str:
    return dedent(f'''\
        """List available uv run commands for {name}."""

        from importlib.metadata import entry_points


        def main() -> None:
            dist_name = __name__.split(".")[0].replace("_", "-")
            eps = entry_points(group="console_scripts")
            scripts = sorted(
                ep.name for ep in eps
                if ep.dist is not None and ep.dist.name == dist_name
            )
            visible = [s for s in scripts if s != "help"]

            print(f"\\n  {{dist_name}} — available commands:\\n")
            for script in visible:
                print(f"    uv run {{script}}")
            print(f"    uv run help                  list all commands")
            print()
    ''')


def gen_init(name: str) -> str:
    return dedent(f'''\
        """{name}."""

        __version__ = "0.1.0"
    ''')


def gen_config_py(types: list[str]) -> str:
    extras: list[str] = []
    if "cli" in types:
        extras.append('    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")')
    if "gui" in types:
        extras.append('    WINDOW_TITLE: str = os.getenv("WINDOW_TITLE", "App")')
    if "api" in types:
        extras.append('    HOST: str = os.getenv("HOST", "0.0.0.0")')
        extras.append('    PORT: int = int(os.getenv("PORT", "8000"))')
    extras_str = ("\n" + "\n".join(extras)) if extras else ""

    return dedent(f'''\
        """Application configuration from environment / .env file."""

        import os

        from dotenv import load_dotenv

        load_dotenv()


        class Config:
            DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
        {extras_str}

        config = Config()
    ''')


def gen_env_example(types: list[str]) -> str:
    lines = ["DEBUG=false"]
    if "cli" in types:
        lines.append("LOG_LEVEL=INFO")
    if "gui" in types:
        lines.append("WINDOW_TITLE=My App")
    if "api" in types:
        lines.append("HOST=0.0.0.0")
        lines.append("PORT=8000")
    return "\n".join(lines) + "\n"


def gen_entry_files(
    types: list[str],
    name: str,
    module: str,
    use_dotenv: bool,
) -> dict[str, str]:
    """Returns {filename: content} for entry point .py files (relative to src/module/)."""
    exe = _executable_types(types)
    if not exe:
        return {}

    single = len(exe) == 1
    result: dict[str, str] = {}

    for t in exe:
        fname = "main" if single else t
        entry_ref = f"{module}.{fname}"

        if t == "cli":
            dotenv_import = "from .config import config\n\n\n" if use_dotenv else ""
            dotenv_usage = "\n    if config.DEBUG:\n        print(\"[debug] running\")" if use_dotenv else ""
            content = dedent(f'''\
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
        elif t == "gui":
            dotenv_import = "from .config import config\n" if use_dotenv else ""
            title_expr = "config.WINDOW_TITLE" if use_dotenv else f'"{name}"'
            content = dedent(f'''\
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
        else:  # api
            if use_dotenv:
                dotenv_import = "from .config import config\n"
                run_line = (
                    f'    uvicorn.run("{entry_ref}:app", '
                    f'host=config.HOST, port=config.PORT, reload=config.DEBUG)'
                )
            else:
                dotenv_import = ""
                run_line = f'    uvicorn.run("{entry_ref}:app", host="0.0.0.0", port=8000, reload=True)'

            content = dedent(f'''\
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

        result[f"{fname}.py"] = content

    return result


def gen_test_main(types: list[str], module: str) -> str:
    exe = _executable_types(types)
    single = len(exe) == 1
    api_fname = "main" if (single and "api" in exe) else "api"

    parts: list[str] = [dedent(f"""\
        from {module} import __version__


        def test_version() -> None:
            assert __version__ == "0.1.0"
    """)]

    if "api" in types:
        parts.append(dedent(f"""\
            from fastapi.testclient import TestClient

            from {module}.{api_fname} import app

            client = TestClient(app)


            def test_api_root() -> None:
                response = client.get("/")
                assert response.status_code == 200


            def test_api_health() -> None:
                response = client.get("/health")
                assert response.status_code == 200
                assert response.json() == {{"status": "ok"}}
        """))

    return "\n".join(parts)


def gen_pre_commit_config() -> str:
    return dedent("""\
        repos:
          - repo: https://github.com/astral-sh/ruff-pre-commit
            rev: v0.11.2
            hooks:
              - id: ruff
                args: [--fix, --exit-non-zero-on-fix]
              - id: ruff-format

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
    types: list[str],
) -> str:
    exe = _executable_types(types)
    single = len(exe) == 1
    api_fname = "main" if (single and "api" in exe) else "api"

    api_step = ""
    if "api" in types:
        api_step = f"""
      - name: Check API starts
        run: |
          uv run uvicorn {module}.{api_fname}:app --host 0.0.0.0 --port 8000 &
          sleep 3
          curl -sf http://localhost:8000/health
        shell: bash
"""

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
              - run: uv sync --all-groups
              - run: uv run ruff check .
              - run: uv run ruff format --check .
              - run: uv run mypy src/

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
              - run: uv sync --all-groups
              {api_step}
              - run: uv run pytest --cov=src --cov-report=term-missing
    """)


def gen_dockerfile(name: str, module: str, python_version: str, api_fname: str = "main") -> str:
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
        CMD ["uvicorn", "{module}.{api_fname}:app", "--host", "0.0.0.0", "--port", "8000"]
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

        # Environment / secrets
        .env
        .env.*
        !.env.example
        *.pem
        *.key
        *.pfx
        *.p12
        credentials*.json
        secrets*.json
        service-account*.json
        *_rsa
        *_ecdsa

        # Claude Code / personal tool config
        .claude/
    """)


def gen_readme(
    name: str,
    description: str,
    types: list[str],
    python_version: str,
    license_id: str,
    has_docker: bool,
) -> str:
    module = to_module_name(name)
    exe = _executable_types(types)
    single = len(exe) == 1
    type_labels = ", ".join(PROJECT_TYPE_LABELS[t] for t in types)

    run_lines: list[str] = []
    for t in exe:
        cmd = name if single else f"{name}-{t}"
        if t == "api":
            run_lines.append(f"uv run {cmd}")
            run_lines.append("# API:  http://localhost:8000")
            run_lines.append("# Docs: http://localhost:8000/docs")
        else:
            run_lines.append(f"uv run {cmd}")

    if not exe:
        run_block = f"```python\nfrom {module} import __version__\nprint(__version__)\n```"
    else:
        run_block = "```bash\n" + "\n".join(run_lines) + "\n```"

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

        **Type:** {type_labels} | **Python:** {python_version}+ | **License:** {license_id}

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
    types: list[str],
    python_version: str,
    author: str,
    license_id: str,
    has_dotenv: bool,
    has_docker: bool,
) -> str:
    exe = _executable_types(types)
    single = len(exe) == 1
    type_labels = ", ".join(PROJECT_TYPE_LABELS[t] for t in types)

    # Entry files in tree
    if not exe:
        entry_lines = ""
    elif single:
        entry_lines = "│       └── main.py            # entry point\n"
    else:
        entry_lines = "".join(f"│       ├── {t}.py{' ' * (14 - len(t))} # {PROJECT_TYPE_LABELS[t]}\n" for t in exe)

    config_line = "│       └── config.py          # dotenv configuration\n" if has_dotenv else ""
    api_extra = (
        "│       ├── routers/           # FastAPI routers\n"
        "│       └── schemas/           # Pydantic models\n"
        if "api" in types else ""
    )
    docker_lines = "├── Dockerfile\n├── .dockerignore\n" if has_docker else ""
    dotenv_line = "├── .env.example\n" if has_dotenv else ""
    license_line = "├── LICENSE\n" if license_id != "Proprietary" else ""

    # Run commands
    run_cmds: list[str] = []
    for t in exe:
        cmd = name if single else f"{name}-{t}"
        suffix = " → http://localhost:8000" if t == "api" else ""
        run_cmds.append(f"uv run {cmd:<22} #{suffix}")

    if not run_cmds:
        run_section = f"Imported as a package: `from {module} import ...`"
    else:
        run_section = "\n".join(run_cmds)

    scripts_row = ""
    if exe:
        if single:
            scripts_row = f"| `[project.scripts]` | `{name}` → `{module}.main:main` |\n"
        else:
            scripts = ", ".join(f"`{name}-{t}`" for t in exe)
            scripts_row = f"| `[project.scripts]` | {scripts} |\n"

    return dedent(f"""\
        # Project Structure — {name}

        **Description:** {description}
        **Type:** {type_labels}
        **Python:** {python_version}+
        **License:** {license_id}
        **Author:** {author}

        ---

        ## Directory Layout

        ```
        {name}/
        ├── src/
        │   └── {module}/
        │       ├── __init__.py        # __version__ & public API
        {entry_lines}{config_line}{api_extra}├── tests/
        │   ├── __init__.py
        │   └── test_main.py
        ├── .github/
        │   └── workflows/
        │       └── ci.yml             # lint · mypy · test
        ├── .pre-commit-config.yaml
        {docker_lines}{dotenv_line}{license_line}├── pyproject.toml
        ├── README.md
        ├── STRUCTURE.md
        └── .gitignore
        ```

        ---

        ## Key Files

        | File | Purpose |
        |------|---------|
        | `pyproject.toml` | Metadata, deps, build (hatchling), tool config |
        | `src/{module}/__init__.py` | `__version__` + public API |
        | `tests/test_main.py` | Pytest test suite |
        | `.github/workflows/ci.yml` | lint + mypy + test on push/PR |
        | `.pre-commit-config.yaml` | ruff + mypy on every commit |
        {scripts_row}
        ---

        ## Toolchain

        | Tool | Role |
        |------|------|
        | [uv](https://docs.astral.sh/uv/) | Package & environment manager |
        | [hatchling](https://hatch.pypa.io/) | Build backend |
        | [ruff](https://docs.astral.sh/ruff/) | Linter + formatter |
        | [mypy](https://mypy-lang.org/) | Static type checker |
        | [pytest](https://docs.pytest.org/) | Test runner |
        | [pre-commit](https://pre-commit.com/) | Git hooks |

        ---

        ## Entry Points

        {run_section}

        ---

        ## Common Commands

        ```bash
        uv sync                  # install / update deps
        uv run pytest            # test
        uv run ruff check .      # lint
        uv run ruff format .     # format
        uv run mypy src/         # type-check
        uv build                 # build wheel + sdist
        uv add <pkg>             # add runtime dep
        uv add --group dev <pkg> # add dev dep
        ```

        ## Enable Pre-commit

        ```bash
        uv tool install pre-commit
        pre-commit install
        ```
    """)


# ─────────────────────────────────────────────────────────────
# PROJECT CREATION
# ─────────────────────────────────────────────────────────────

def run_cmd(args: list, cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
    print(f"    $ {' '.join(str(a) for a in args)}")
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if check and result.returncode != 0:
        print(f"    FAILED (exit {result.returncode})")
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
    types: list[str],
    license_id: str,
    init_git: bool,
    use_dotenv: bool,
    use_docker: bool,
    output_dir: Optional[Path] = None,
) -> None:
    import datetime
    module = to_module_name(name)
    root = (output_dir or Path.cwd()) / name
    exe = _executable_types(types)
    single = len(exe) == 1
    api_fname = "main" if (single and "api" in exe) else "api"
    year = datetime.datetime.now().year
    total = 6

    type_labels = ", ".join(PROJECT_TYPE_LABELS[t] for t in types)
    print()
    print(f"  Creating '{name}' ({type_labels})...")

    # ── 1. Directories ─────────────────────────────────────────
    step(f"1/{total}", "Creating directory structure")
    (root / "src" / module).mkdir(parents=True)
    (root / "tests").mkdir()
    (root / ".github" / "workflows").mkdir(parents=True)

    # ── 2. Files ───────────────────────────────────────────────
    step(f"2/{total}", "Writing source files")

    files: dict[str, str] = {
        "pyproject.toml": gen_pyproject_toml(
            name, module, description, author, python_version, types, license_id, use_dotenv
        ),
        f"src/{module}/__init__.py": gen_init(name),
        f"src/{module}/_help.py": gen_help_py(name, module),
        "tests/__init__.py": "",
        "tests/test_main.py": gen_test_main(types, module),
        ".github/workflows/ci.yml": gen_github_ci(name, module, python_version, types),
        ".pre-commit-config.yaml": gen_pre_commit_config(),
        ".gitignore": gen_gitignore(),
        "README.md": gen_readme(name, description, types, python_version, license_id, use_docker),
        "STRUCTURE.md": gen_structure_md(
            name, module, description, types, python_version,
            author, license_id, use_dotenv, use_docker,
        ),
    }

    # Entry point files
    for fname, content in gen_entry_files(types, name, module, use_dotenv).items():
        files[f"src/{module}/{fname}"] = content

    # Dotenv support
    if use_dotenv and exe:
        files[f"src/{module}/config.py"] = gen_config_py(types)
        files[".env.example"] = gen_env_example(types)

    # Docker
    if use_docker and "api" in types:
        files["Dockerfile"] = gen_dockerfile(name, module, python_version, api_fname)
        files[".dockerignore"] = gen_dockerignore()

    # LICENSE
    license_text = gen_license_file(license_id, year, author)
    if license_text:
        files["LICENSE"] = license_text

    for rel, content in files.items():
        (root / rel).write_text(content, encoding="utf-8")
        print(f"    + {rel}")

    # ── 3. Python version ──────────────────────────────────────
    step(f"3/{total}", f"Installing Python {python_version}")
    run_cmd(["uv", "python", "install", python_version], cwd=root)
    run_cmd(["uv", "python", "pin", python_version], cwd=root)

    # ── 4. Dependencies ────────────────────────────────────────
    step(f"4/{total}", "Syncing dependencies")
    run_cmd(["uv", "sync", "--all-groups"], cwd=root)

    # ── 5. Git ─────────────────────────────────────────────────
    if init_git:
        step(f"5/{total}", "Initializing git repository")
        run_cmd(["git", "init"], cwd=root)
        run_cmd(["git", "add", "."], cwd=root)
        run_cmd(["git", "commit", "-m", "chore: initial project scaffold"], cwd=root)
    else:
        step(f"5/{total}", "Skipping git init")

    # ── 6. Done ────────────────────────────────────────────────
    step(f"6/{total}", "Done")
    print()
    print("─" * 62)
    print(f"  ✓  '{root}' created!")
    print()
    print("  Next steps:")
    print(f"    cd {root}")
    for t in exe:
        cmd = name if single else f"{name}-{t}"
        if t == "api":
            print(f"    uv run {cmd:<22}  # start API → http://localhost:8000")
        else:
            print(f"    uv run {cmd:<22}  # run")
    print(f"    uv run help                    # list all commands")
    print(f"    uv run pytest                  # test")
    print(f"    uv run mypy src/               # type check")
    if init_git:
        print()
        print("  Enable pre-commit:")
        print("    uv tool install pre-commit && pre-commit install")
    print("─" * 62)


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = build_parser()
    cli = parser.parse_args()

    print()
    print("┌──────────────────────────────────────────────────┐")
    print("│  Python Project Template Creator                 │")
    print("│  uv · hatchling · ruff · mypy · pytest           │")
    print(f"│  Platform: {PLATFORM_NAME:<39}│")
    print("└──────────────────────────────────────────────────┘")
    print()

    print("Checking requirements...")
    check_requirements(skip_prompt=cli.yes)

    non_interactive = cli.yes and cli.name is not None

    # Resolve output directory
    if cli.output:
        output_dir = Path(cli.output).expanduser().resolve()
        if not output_dir.exists():
            output_dir.mkdir(parents=True, exist_ok=True)
        elif not output_dir.is_dir():
            print(f"ERROR: '{output_dir}' is not a directory.")
            sys.exit(1)
    elif non_interactive:
        output_dir = default_output_dir()
    else:
        output_dir = ask_output_dir()

    if non_interactive:
        name = cli.name.lower()
        if not re.match(r'^[a-z][a-z0-9]*(-[a-z0-9]+)*$', name):
            print(f"ERROR: invalid project name '{name}'")
            sys.exit(1)
        if (output_dir / name).exists():
            print(f"ERROR: directory '{output_dir / name}' already exists")
            sys.exit(1)
        python_version = cli.python_version or DEFAULT_PYTHON
        types = cli.project_types or ["cli"]
        license_id = cli.license_id or "MIT"
        description = cli.description or "A Python project"
        author = cli.author or (
            (f"{get_git_config('user.name')} <{get_git_config('user.email')}>"
             if get_git_config("user.name") else "")
        )
        init_git = not cli.no_git and git_available()
    else:
        name = ask_project_name(cli.name, output_dir)
        python_version = cli.python_version or ask_python_version()
        types = cli.project_types or ask_project_types()
        license_id = cli.license_id or ask_license()
        description = cli.description or ask_description()
        author = ask_author(cli.author)

        # Git init: always on unless --no-git or git not found
        if not git_available():
            print("\n  (git not found — skipping git init)")
        init_git = not cli.no_git and git_available()

    exe = _executable_types(types)
    use_dotenv = cli.dotenv
    use_docker = cli.docker and "api" in types

    if cli.docker and "api" not in types:
        print("  Note: --docker requires api type; ignoring.")

    # Ask dotenv/docker interactively if not set via flag
    if not non_interactive and not cli.dotenv and exe:
        print()
        use_dotenv = ask_yes_no("Add python-dotenv (config.py + .env.example)?")
    if not non_interactive and not cli.docker and "api" in types:
        print()
        use_docker = ask_yes_no("Generate Dockerfile + .dockerignore?")

    # Summary
    module = to_module_name(name)
    type_labels = ", ".join(PROJECT_TYPE_LABELS[t] for t in types)
    print()
    print("─" * 62)
    print("  Summary:")
    print(f"    Output:        {output_dir / name}")
    print(f"    Name:          {name}  (module: {module})")
    print(f"    Python:        {python_version}")
    print(f"    Types:         {type_labels}")
    print(f"    License:       {license_id}")
    print(f"    Description:   {description}")
    print(f"    Author:        {author}")
    print(f"    Git init:      {'yes' if init_git else 'no'}")
    print(f"    python-dotenv: {'yes' if use_dotenv else 'no'}")
    print(f"    Docker:        {'yes' if use_docker else 'no'}")
    print("─" * 62)
    print()

    if not cli.yes and not ask_yes_no("Create project?"):
        print("  Aborted.")
        sys.exit(0)

    create_project(
        name=name,
        description=description,
        author=author,
        python_version=python_version,
        types=types,
        license_id=license_id,
        init_git=init_git,
        use_dotenv=use_dotenv,
        use_docker=use_docker,
        output_dir=output_dir,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nAborted.")
        sys.exit(130)
