"""Repository discovery for the porting pipeline.

Walks a source tree, skips dependency/vendored/generated directories, and
reports every file that a registered adapter can translate.  The scanner never
reads file contents: language detection is purely extension based, delegated
to :func:`llang.portapp.adapters.adapter_for` so newly registered adapters are
picked up automatically.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from .adapters import adapter_for

# Directory names that never contain first-party source worth porting.
# Dependencies, VCS metadata, caches, vendored/rewritten trees and build output
# are all excluded: porting them would produce noise, not signal.
DEFAULT_SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", ".bzr",
    "node_modules", "bower_components", "jspm_packages",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    ".eggs", "site-packages",
    ".venv", "venv", "env", ".env",
    "vendor", "vendored", "third_party", "third-party", "external",
    "rewrites", "rewritten", "rewrites_output", "generated", "gen",
    "build", "dist", "out", "output", "target", "_build", ".next",
    ".idea", ".vscode", "coverage", ".coverage",
})

ScannedFile = tuple[str, str, str]
"""A scanned file is ``(relative_path, absolute_path, adapter_name)``."""


def _normalize_extension(extension: str) -> str:
    return extension.strip().lower().lstrip(".")


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def scan_repo(
    root: str | Path,
    output_dir: str | Path | None = None,
    include: Iterable[str] | None = None,
    skip_dirs: Iterable[str] | None = None,
) -> list[ScannedFile]:
    """Return ``(relative_path, absolute_path, adapter_name)`` for portables.

    Args:
        root: repository (or any source directory) to walk.
        output_dir: generated-output directory to prune when it lives inside
            ``root``.  Prevents a previous run's ``.ll`` files (or any other
            generated source) from being scanned again.
        include: optional iterable of extensions, with or without a leading
            dot.  When given, only matching files are returned.
        skip_dirs: additional directory names to prune (on top of the
            defaults).

    Raises:
        ValueError: if ``root`` is not an existing directory.
    """
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise ValueError(f"not a directory: {root}")

    skipped = set(DEFAULT_SKIP_DIRS)
    if skip_dirs:
        skipped.update(name for name in skip_dirs)

    # If the output directory sits inside the repository, prune its top-level
    # component everywhere in the walk.
    output_component: str | None = None
    if output_dir is not None:
        resolved_output = Path(output_dir).resolve()
        if _is_within(resolved_output, root_path):
            relative_output = resolved_output.relative_to(root_path)
            if str(relative_output) != ".":
                output_component = relative_output.parts[0]

    include_extensions = None
    if include is not None:
        include_extensions = {_normalize_extension(item) for item in include}

    entries: list[ScannedFile] = []
    for directory, dirnames, filenames in os.walk(root_path):
        dirnames[:] = sorted(
            name for name in dirnames
            if name not in skipped and name != output_component
        )
        for filename in sorted(filenames):
            path = Path(directory) / filename
            adapter = adapter_for(str(path))
            if adapter is None:
                continue
            suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            if include_extensions is not None and suffix not in include_extensions:
                continue
            relative = path.relative_to(root_path).as_posix()
            entries.append((relative, str(path.resolve()), adapter.name))

    entries.sort(key=lambda item: item[0])
    return entries
