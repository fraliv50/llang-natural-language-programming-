"""c-ll — a typed, checked C-like surface for the canonical llang IR.

c-ll v1 pins ``int`` to signed 32-bit and ``float`` to binary64, makes every
conversion explicit, bounds-checks all pointers, and turns every C undefined
behaviour into a source-located error.  The English surface is untouched.

Public API:
    run_c_source(source) -> CInterpreter
    compile_c_source(source) -> CompileResult
"""

from .lexer import CLLexer, lex_c
from .parser import CLParser, parse_c
from .runtime import CInterpreter, TypeChecker, TypeReport
from .api import check_c_source, run_c_source, compile_c_source

__all__ = [
    "CLLexer", "lex_c", "CLParser", "parse_c", "CInterpreter", "TypeChecker",
    "TypeReport", "check_c_source", "run_c_source", "compile_c_source",
]
