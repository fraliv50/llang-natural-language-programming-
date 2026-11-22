"""llang — a structured natural-language interpreter.

Public API:
    run_source(source) -> Interpreter
    run_file(path) -> None
    lint_source(source) -> list[Diagnostic]
    lint_program(program) -> list[Diagnostic]
"""

from .errors import LangError
from .lexer import Lexer
from .parser import Parser
from .interpreter import Interpreter
from .linter import lint_program, lint_source


def run_source(source: str) -> Interpreter:
    """Tokenize, parse, and execute source text. Returns the interpreter."""
    tokens = Lexer(source).tokenize()
    program = Parser(tokens).parse_program()
    interpreter = Interpreter()
    interpreter.run(program)
    return interpreter


def run_file(path) -> None:
    with open(path, "r", encoding="utf-8-sig") as handle:
        run_source(handle.read())


__all__ = ["LangError", "Lexer", "Parser", "Interpreter", "run_source", "run_file",
           "lint_source", "lint_program"]
