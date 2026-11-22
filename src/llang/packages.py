"""Minimal package manifests and a local package registry for llang.

This module is deliberately self-contained: it uses only the Python standard
library and JSON manifests (``llang.json``), not TOML or any third-party
package.  Modules still extend values and types, never syntax -- a manifest
only describes where a module lives and what it needs.

Manifest shape (``llang.json``)::

    {
      "name": "text",
      "version": "1.2.0",
      "entry": "text.ll",
      "exports": ["uppercase", "lowercase"],
      "dependencies": {"lists": "^1.0.0"}
    }

``name``, ``version`` and ``entry`` are required.  ``exports`` and
``dependencies`` are optional and default to empty.

Supported versions and specs
----------------------------
Versions are simple ``x.y.z`` triples of non-negative integers (for example
``1.2.3``); prerelease/build suffixes are intentionally not supported.

Version specs (used in ``dependencies`` and in ``resolve``):

===================  =========================================================
Spec                 Matches
===================  =========================================================
``"*"`` or ``""``     any version
``"1.2.3"``          exactly 1.2.3 (``"==1.2.3"`` is the same)
``">=1.2.3"``        greater than or equal to 1.2.3
``">1.2.3"``         strictly greater than 1.2.3
``"<=1.2.3"``        less than or equal to 1.2.3
``"<1.2.3"``         strictly less than 1.2.3
``"^1.2.3"``         compatible within the major version: >=1.2.3, <2.0.0
``"~1.2.3"``         compatible within the minor version: >=1.2.3, <1.3.0
===================  =========================================================

Comparison is numeric on (major, minor, patch), not lexicographic, so
``1.10.0 > 1.9.9``.  An unknown spec is rejected with ``ValueError`` by
:func:`version_matches`; :meth:`PackageRegistry.check_dependencies` reports it
as a problem rather than raising.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "MANIFEST_FILENAME",
    "Manifest",
    "PackageNotFound",
    "load_manifest",
    "parse_version",
    "compare_versions",
    "version_matches",
    "PackageRegistry",
]


#: Conventional filename for a llang package manifest.
MANIFEST_FILENAME = "llang.json"

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")
_SPEC_RE = re.compile(r"(>=|<=|==|>|<|\^|~)?\s*(\d+)\.(\d+)\.(\d+)")

_SUPPORTED_SPECS = ("*", "1.2.3", ">=1.2.3", ">1.2.3", "<=1.2.3",
                    "<1.2.3", "^1.2.3", "~1.2.3")


# The workspace root is three levels up from this file:
# <workspace>/src/llang/packages.py -> <workspace>.
_WORKSPACE = Path(__file__).resolve().parent.parent.parent


@dataclass
class Manifest:
    """Description of one installable llang package.

    ``path`` records where the manifest was found.  It is excluded from
    equality and repr so two identical manifests from different directories
    still compare equal.
    """

    name: str
    version: str
    entry: str
    exports: list[str] = field(default_factory=list)
    dependencies: dict[str, str] = field(default_factory=dict)
    path: Path | None = field(default=None, compare=False, repr=False)


class PackageNotFound(LookupError, ValueError):
    """Raised by :meth:`PackageRegistry.resolve` when nothing matches.

    It inherits from both ``LookupError`` and ``ValueError`` so callers can
    catch it either way.
    """


def parse_version(text: str) -> tuple[int, int, int]:
    """Return ``(major, minor, patch)`` for a simple ``x.y.z`` version.

    Raises ``ValueError`` with a clear message for anything else.
    """
    if not isinstance(text, str):
        raise ValueError(f"version must be text, got {type(text).__name__}")
    match = _VERSION_RE.fullmatch(text.strip())
    if match is None:
        raise ValueError(f"invalid version {text!r}; expected x.y.z (e.g. 1.2.3)")
    return tuple(int(part) for part in match.groups())


def compare_versions(left: str, right: str) -> int:
    """Compare two ``x.y.z`` versions: -1, 0 or 1."""
    a = parse_version(left)
    b = parse_version(right)
    return (a > b) - (a < b)


def version_matches(version: str, spec: str) -> bool:
    """Return whether ``version`` (``x.y.z``) satisfies ``spec``.

    See the module docstring for the full list of supported specs.  Malformed
    versions or specs raise ``ValueError``.
    """
    if not isinstance(spec, str):
        raise ValueError(f"version spec must be text, got {type(spec).__name__}")
    parsed = parse_version(version)

    text = spec.strip()
    if text in ("", "*"):
        return True

    match = _SPEC_RE.fullmatch(text)
    if match is None:
        supported = ", ".join(repr(item) for item in _SUPPORTED_SPECS)
        raise ValueError(f"unsupported version spec {spec!r}; supported: {supported}")

    operator = match.group(1) or "=="
    target = tuple(int(part) for part in match.groups()[1:])

    if operator == "==":
        return parsed == target
    if operator == ">=":
        return parsed >= target
    if operator == ">":
        return parsed > target
    if operator == "<=":
        return parsed <= target
    if operator == "<":
        return parsed < target
    if operator == "^":
        # Compatible within the major version: >=x.y.z and <(x+1).0.0.
        return target <= parsed < (target[0] + 1, 0, 0)
    if operator == "~":
        # Compatible within the minor version: >=x.y.z and <x.(y+1).0.
        return target <= parsed < (target[0], target[1] + 1, 0)
    raise ValueError(f"unsupported version spec {spec!r}")  # pragma: no cover


def _required_string(data: dict, name: str) -> str:
    if name not in data:
        raise ValueError(f"manifest is missing required field '{name}'")
    value = data[name]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"manifest field '{name}' must be a non-empty string")
    return value


def load_manifest(path) -> Manifest:
    """Read and validate a JSON manifest at ``path``.

    Every validation error is a ``ValueError`` whose message names the bad
    field.  Missing files and invalid JSON are also reported as ``ValueError``.
    """
    location = Path(path)
    try:
        text = location.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read manifest '{location}': {exc}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifest '{location}' is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")

    name = _required_string(data, "name")
    version = _required_string(data, "version")
    # Validate the version syntax now so bad manifests fail at load time.
    try:
        parse_version(version)
    except ValueError as exc:
        raise ValueError(f"manifest field 'version' is invalid: {exc}") from exc
    entry = _required_string(data, "entry")

    exports = data.get("exports", [])
    if (not isinstance(exports, list) or
            any(not isinstance(item, str) or not item.strip() for item in exports)):
        raise ValueError("manifest field 'exports' must be a list of non-empty strings")

    dependencies = data.get("dependencies", {})
    if not isinstance(dependencies, dict):
        raise ValueError(
            "manifest field 'dependencies' must be an object mapping package "
            "names to version specs")
    for dep_name, spec in dependencies.items():
        if not isinstance(dep_name, str) or not dep_name.strip():
            raise ValueError(
                f"manifest field 'dependencies' has an invalid package name: {dep_name!r}")
        if not isinstance(spec, str) or not spec.strip():
            raise ValueError(
                f"manifest field 'dependencies' has an invalid version spec "
                f"for '{dep_name}': {spec!r}")

    return Manifest(
        name=name,
        version=version,
        entry=entry,
        exports=list(exports),
        dependencies=dict(dependencies),
        path=location,
    )


class PackageRegistry:
    """Find and query local llang packages.

    ``roots`` may be a single directory or an iterable of directories.  When
    omitted, the defaults are the workspace ``lib/`` and ``packages/``
    directories.  Non-existent roots are simply skipped.

    Search roots are scanned in order; when two manifests declare the same
    name and version, the one from the later root wins.
    """

    def __init__(self, roots=None):
        if roots is None:
            roots = [_WORKSPACE / "lib", _WORKSPACE / "packages"]
        elif isinstance(roots, (str, Path)):
            roots = [roots]
        self.roots = [Path(root) for root in roots]
        self._by_name: dict[str, list[Manifest]] = {}
        self._discovered = False

    def discover(self) -> list[Manifest]:
        """Find every ``llang.json`` under the search roots.

        Returns the list of loaded manifests and refreshes the internal name
        index used by :meth:`resolve` and :meth:`check_dependencies`.  Invalid
        manifests raise the ``ValueError`` from :func:`load_manifest`.
        """
        found: list[Manifest] = []
        for root in self.roots:
            if not root.is_dir():
                continue
            for path in sorted(root.rglob(MANIFEST_FILENAME)):
                if path.is_file():
                    found.append(load_manifest(path))

        index: dict[str, list[Manifest]] = {}
        for manifest in found:
            index.setdefault(manifest.name, []).append(manifest)
        self._by_name = index
        self._discovered = True
        return found

    def _ensure_discovered(self) -> None:
        if not self._discovered:
            self.discover()

    def resolve(self, name: str, version: str | None = None) -> Manifest:
        """Return the manifest for ``name``.

        With no ``version``, the highest available version is returned.  A
        ``version`` spec (see module docstring) restricts the candidates.
        Raises :class:`PackageNotFound` when no manifest matches.
        """
        self._ensure_discovered()
        candidates = self._by_name.get(name, [])
        if not candidates:
            raise PackageNotFound(f"package '{name}' was not found")

        if version is not None:
            matched = []
            for candidate in candidates:
                try:
                    if version_matches(candidate.version, version):
                        matched.append(candidate)
                except ValueError:
                    # A malformed spec simply matches nothing.
                    continue
            if not matched:
                raise PackageNotFound(
                    f"package '{name}' has no version matching '{version}'")
            candidates = matched

        return max(candidates, key=lambda item: parse_version(item.version))

    def check_dependencies(self, manifest: Manifest) -> list[str]:
        """Return human-readable problems for unmet dependencies.

        An empty list means every dependency is installed at a compatible
        version.  Missing packages and incompatible versions each produce one
        entry; no exception is raised for a bad dependency spec.
        """
        problems: list[str] = []
        for dep_name, spec in sorted(manifest.dependencies.items()):
            try:
                installed = self.resolve(dep_name)
            except PackageNotFound:
                problems.append(f"{dep_name}: missing (required {spec})")
                continue
            try:
                compatible = version_matches(installed.version, spec)
            except ValueError as exc:
                problems.append(f"{dep_name}: invalid version spec '{spec}' ({exc})")
                continue
            if not compatible:
                problems.append(
                    f"{dep_name}: found {installed.version}, requires {spec}")
        return problems

    @staticmethod
    def describe(manifest: Manifest) -> str:
        """Return a short, human-readable summary of ``manifest``."""
        lines = [f"{manifest.name} {manifest.version}"]
        lines.append(f"  entry: {manifest.entry}")
        exports = ", ".join(manifest.exports) if manifest.exports else "(none)"
        lines.append(f"  exports: {exports}")
        if manifest.dependencies:
            deps = ", ".join(
                f"{name} {spec}"
                for name, spec in sorted(manifest.dependencies.items()))
        else:
            deps = "(none)"
        lines.append(f"  dependencies: {deps}")
        if manifest.path is not None:
            lines.append(f"  location: {manifest.path}")
        return "\n".join(lines)
