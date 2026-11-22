"""Public entry points for the c-ll surface.

``run_c_source`` is the checked interpreter path.  ``compile_c_source`` reuses
the *shared* WebAssembly backend by lowering the int-only, pointer-free subset
to canonical llang AST nodes; constructs the old backend cannot represent are
reported in ``result.unsupported`` instead of being silently dropped.  No
existing llang file is modified by this module.
"""

from .ast import (
    Program, Block, Literal, Variable, Unary, Binary, Cast, Call, TypedDecl,
    Set, Show, FunctionDef, Return, If, RepeatWhile, Break, Continue,
)
from .lexer import lex_c
from .parser import parse_c
from .runtime import CInterpreter, TypeChecker
from .. import ast_nodes as canon
from ..compiler import CompileResult, CompileUnsupported, compile_program
from ..errors import LangError


def check_c_source(source: str):
    """Return ``(program, report)`` after lexing, parsing and type checking."""
    program = parse_c(lex_c(source))
    report = TypeChecker().check(program)
    return program, report


def run_c_source(source: str, *, inputs=None) -> CInterpreter:
    """Lex, parse, type-check and execute c-ll source.

    ``inputs`` is accepted for API parity with the English surface; v1 has no
    input statement, so it is unused.
    """
    program = parse_c(lex_c(source))
    return CInterpreter().run(program)


# ---------------------------------------------------------------------------
# Lowering to the canonical IR (int-only subset)
# ---------------------------------------------------------------------------

class _Lowerer:
    def __init__(self):
        self.unsupported: list[CompileUnsupported] = []

    def flag(self, node, reason):
        pos = getattr(node, "pos", None)
        self.unsupported.append(CompileUnsupported(
            type(node).__name__, reason, pos.line if pos else None))

    def expr(self, node):
        if isinstance(node, Literal):
            return canon.Literal(node.value)
        if isinstance(node, Variable):
            return canon.Variable(node.name)
        if isinstance(node, Unary) and node.op == "LNOT":
            return canon.Unary("NOT", self.expr(node.operand))
        if isinstance(node, Binary):
            op = {"REM": "MOD", "LAND": "AND", "LOR": "OR"}.get(node.op, node.op)
            return canon.Binary(op, self.expr(node.left), self.expr(node.right))
        if isinstance(node, Call):
            return canon.Call(node.name,
                              [(f"arg{i}", self.expr(arg))
                               for i, arg in enumerate(node.args)])
        self.flag(node, "no canonical IR lowering for this c-ll expression")
        return canon.Literal(0)

    def block(self, block):
        lowered = []
        for statement in block.statements:
            result = self.stmt(statement)
            if isinstance(result, list):
                lowered.extend(result)
            elif result is not None:
                lowered.append(result)
        return canon.Block(lowered)

    def stmt(self, node):
        if isinstance(node, TypedDecl):
            if node.ctype.kind == "pointer":
                self.flag(node, "pointer declarations are not in the old backend")
            return canon.Set(node.name, self.expr(node.init))
        if isinstance(node, Set) and isinstance(node.target, Variable):
            return canon.Set(node.target.name, self.expr(node.expr))
        if isinstance(node, Show):
            result = []
            for expr in node.exprs:
                result.append(canon.Show(self.expr(expr)))
            return result
        if isinstance(node, If):
            branches = [(self.expr(c), self.block(b)) for c, b in node.branches]
            otherwise = self.block(node.otherwise) if node.otherwise else None
            return canon.If(branches, otherwise)
        if isinstance(node, RepeatWhile):
            return canon.RepeatWhile(self.expr(node.cond), self.block(node.body))
        if isinstance(node, Return):
            return canon.Return(self.expr(node.expr))
        if isinstance(node, Break):
            return canon.Break()
        if isinstance(node, Continue):
            return canon.Continue()
        if isinstance(node, FunctionDef):
            return canon.FunctionDef(
                node.name, [], [name for name, _t in node.params],
                self.block(node.body))
        self.flag(node, "no canonical IR lowering for this c-ll statement")
        return None

    def program(self, program: Program):
        statements = []
        for node in program.statements:
            lowered = self.stmt(node)
            if isinstance(lowered, list):
                statements.extend(lowered)
            elif lowered is not None:
                statements.append(lowered)

        executable = [s for s in statements if not isinstance(s, canon.FunctionDef)]
        if executable:
            # Top-level statements become a synthetic function so the old
            # backend never has to emit naked executable globals.
            body = list(executable) + [canon.Return(canon.Literal(0))]
            statements.append(canon.FunctionDef(
                "__cll_top", [], [], canon.Block(body)))
        return canon.Program(statements)


def compile_c_source(source: str) -> CompileResult:
    """Type-check c-ll source and compile its int-only subset to WASM."""
    program, report = check_c_source(source)
    if report.errors:
        raise report.errors[0]
    lowerer = _Lowerer()
    canonical = lowerer.program(program)
    result = compile_program(canonical)
    result.unsupported.extend(lowerer.unsupported)
    return result


__all__ = [
    "lex_c", "parse_c", "check_c_source", "run_c_source", "compile_c_source",
    "LangError",
]
