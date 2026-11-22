"""Shared data model for the porting pipeline."""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class Gap:
    """One construct the adapter could not translate mechanically."""

    node_type: str
    reason: str
    line: int | None = None
    source_snippet: str = ""

    def __str__(self) -> str:
        where = f"line {self.line}" if self.line else "unknown line"
        snippet = f" | {self.source_snippet[:80]}" if self.source_snippet else ""
        return f"{where}: {self.node_type} - {self.reason}{snippet}"


@dataclass
class ConversionResult:
    """Output of one adapter for one source file."""

    source: str
    gaps: list[Gap] = field(default_factory=list)
    notes: list[Gap] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    source_language: str = ""

    @property
    def covered(self) -> float:
        total = self.stats.get("nodes", 0)
        if total == 0:
            return 100.0 if not self.gaps else 0.0
        return round(100.0 * max(0, total - len(self.gaps)) / total, 1)

    @property
    def complete(self) -> bool:
        return not self.gaps


@runtime_checkable
class Adapter(Protocol):
    """A source-language adapter."""

    name: str
    extensions: tuple[str, ...]

    def convert(self, source: str, path: str) -> ConversionResult:
        """Translate one source file. Never guess: report every gap."""
        ...
