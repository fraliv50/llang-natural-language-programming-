"""Source locations and diagnostics.

Errors are part of the language spec: an LLM reader/writer depends on actionable,
localized feedback to self-correct.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SourcePos:
    line: int
    column: int

    def __str__(self) -> str:
        return f"line {self.line}, column {self.column}"


class LangError(Exception):
    """Base error with an optional source position and expected-token hints."""

    def __init__(self, message: str, pos: SourcePos | None = None,
                 expected=()):
        self.message = message
        self.pos = pos
        self.expected = tuple(expected)
        super().__init__(self.render())

    def render(self) -> str:
        where = f" at {self.pos}" if self.pos is not None else ""
        hint = ""
        if self.expected:
            options = ", ".join(repr(item) for item in self.expected)
            hint = f"\n  expected one of: {options}"
        return f"{self.message}{where}{hint}"


class ParseError(LangError):
    """Syntax error."""


class RuntimeErrorLang(LangError):
    """Runtime error (type mismatch, undefined name, failed assertion, ...)."""
