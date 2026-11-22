"""Verification of converted ``.ll`` files.

Every converted file is checked twice:

1. a *parse check* using the real llang lexer/parser (in-process, fast), and
2. the project's canonical lint command, ``python run.py --lint <file>``,
   launched in a subprocess with a timeout.

The verifier only reads files; it never edits source or converted output.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from llang import LangError, Lexer, Parser

# src/llang/portapp/verifier.py -> repository root (where run.py lives).
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TIMEOUT = 30


@dataclass
class FileVerification:
    """Pass/fail result for one converted file."""

    path: str
    passed: bool
    lint_ok: bool
    parse_ok: bool
    lint_output: str = ""
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def parse_check(source: str) -> tuple[bool, str]:
    """Tokenize and parse llang source; return ``(ok, message)``."""
    if not source.strip():
        return True, ""
    try:
        tokens = Lexer(source).tokenize()
        Parser(tokens).parse_program()
    except LangError as exc:
        return False, str(exc)
    except Exception as exc:  # defensive: a parser crash is a failed check
        return False, f"{type(exc).__name__}: {exc}"
    return True, ""


def lint_file(
    path: str | Path,
    project_root: str | Path | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[bool, str]:
    """Run ``python run.py --lint <path>``; return ``(ok, output)``.

    ``project_root`` locates ``run.py``; it defaults to the llang repository
    root and can be overridden in tests or alternate installations.
    """
    project = Path(project_root).resolve() if project_root else PROJECT_ROOT
    runner = project / "run.py"
    if not runner.is_file():
        return False, f"lint runner not found: {runner}"
    command = [sys.executable, str(runner), "--lint", str(path)]
    try:
        completed = subprocess.run(
            command,
            cwd=str(project),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"lint timed out after {timeout}s"
    except OSError as exc:
        return False, f"lint failed to start: {exc}"

    output = ((completed.stdout or "") + (completed.stderr or "")).strip()
    error_lines = [
        line for line in output.splitlines()
        if line.startswith(("error:", "ERROR:", "Traceback", "ERROR "))
    ]
    ok = completed.returncode == 0 and not error_lines
    return ok, output


def verify_file(
    path: str | Path,
    project_root: str | Path | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> FileVerification:
    """Verify one ``.ll`` file without modifying it."""
    file_path = Path(path)
    if not file_path.is_file():
        return FileVerification(
            path=str(file_path), passed=False, lint_ok=False, parse_ok=False,
            errors=[f"missing output file: {file_path}"],
        )

    source = file_path.read_text(encoding="utf-8", errors="replace")
    parse_ok, parse_error = parse_check(source)
    lint_ok, lint_output = lint_file(file_path, project_root, timeout)

    errors: list[str] = []
    if not parse_ok:
        errors.append(f"parse: {parse_error}")
    if not lint_ok:
        errors.append(lint_output or "lint failed")
    return FileVerification(
        path=str(file_path),
        passed=parse_ok and lint_ok,
        lint_ok=lint_ok,
        parse_ok=parse_ok,
        lint_output=lint_output,
        errors=errors,
    )


def verify_many(
    paths: Iterable[str | Path],
    project_root: str | Path | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[FileVerification]:
    """Verify an iterable of ``.ll`` paths."""
    return [
        verify_file(path, project_root=project_root, timeout=timeout)
        for path in paths
    ]


def verify_tree(
    directory: str | Path,
    project_root: str | Path | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[FileVerification]:
    """Verify every ``.ll`` file below ``directory`` (recursively)."""
    root = Path(directory)
    paths = sorted(root.rglob("*.ll")) if root.is_dir() else []
    return verify_many(paths, project_root=project_root, timeout=timeout)
