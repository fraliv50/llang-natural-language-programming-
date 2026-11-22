"""Minimal WebAssembly backend for llang.

Compiles a supported subset of the canonical AST to a valid WebAssembly 1.0
module. All values are i32; text, lists, maps, builtins and foreign calls are
reported as unsupported rather than being silently dropped.

The subset: integer literals, variables, arithmetic/comparison/boolean ops,
user function calls, assignment, if/else, while loops, break/continue, return.

Usage:
    from llang.compiler import compile_source
    result = compile_source(source)
    Path("out.wasm").write_bytes(result.wasm)
"""

from dataclasses import dataclass, field

from .ast_nodes import (Program, Block, Literal, Variable, Unary, Binary, Call,
                        Set, Show, Require, If, RepeatWhile, FunctionDef, Return,
                        ListLiteral, MapLiteral, Index, Length, AddTo, SetItem,
                        ForEach, Break, Continue, Fail, Expect, Use)
from .errors import LangError
from .lexer import Lexer
from .parser import Parser


@dataclass
class CompileUnsupported:
    node_type: str
    reason: str
    lineno: int | None = None

    def __str__(self):
        where = f"line {self.lineno}" if self.lineno else "unknown line"
        return f"{where}: {self.node_type} — {self.reason}"


@dataclass
class CompileResult:
    wasm: bytes
    unsupported: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)


# --- binary encoding helpers --------------------------------------------
def uleb(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def sleb(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        done = (value == 0 and not (byte & 0x40)) or (value == -1 and (byte & 0x40))
        if done:
            out.append(byte)
            return bytes(out)
        out.append(byte | 0x80)


def vec(items) -> bytes:
    payload = b"".join(items)
    return uleb(len(items)) + payload


def name(text: str) -> bytes:
    encoded = text.encode("utf-8")
    return uleb(len(encoded)) + encoded


def section(section_id: int, payload: bytes) -> bytes:
    return bytes([section_id]) + uleb(len(payload)) + payload


I32 = 0x7F
VOID = 0x40

OPCODES = {
    "ADD": 0x6A,
    "SUB": 0x6B,
    "MUL": 0x6C,
    "DIV": 0x6D,
    "FLOORDIV": 0x6D,
    "MOD": 0x6F,
    "EQ": 0x46,
    "NE": 0x47,
    "LT": 0x48,
    "GT": 0x4A,
    "LE": 0x4C,
    "GE": 0x4E,
    "AND": 0x71,
    "OR": 0x72,
}


class _FunctionCompiler:
    def __init__(self, compiler, definition):
        self.compiler = compiler
        self.definition = definition
        self.locals = {}
        self.frames = []          # 'if', 'block', 'loop' in nesting order
        self.code = bytearray()

        for index, param in enumerate(definition.params):
            self.locals[param] = index
        for node in self._all_nodes(definition.body):
            if isinstance(node, Set) and node.name not in self.locals:
                self.locals[node.name] = len(self.locals)

    @staticmethod
    def _all_nodes(node):
        if node is None:
            return []
        fields = getattr(node, "__dict__", {})
        result = [node]
        for value in fields.values():
            if isinstance(value, (list, tuple)):
                for item in value:
                    if hasattr(item, "__dict__"):
                        result.extend(_FunctionCompiler._all_nodes(item))
            elif hasattr(value, "__dict__"):
                result.extend(_FunctionCompiler._all_nodes(value))
        return result

    def emit(self, *pieces):
        for piece in pieces:
            if isinstance(piece, int):
                self.code.append(piece)
            else:
                self.code.extend(piece)

    def br_depth(self, kind):
        for depth, frame in enumerate(reversed(self.frames)):
            if frame == kind:
                return depth
        return None

    # --- expressions -----------------------------------------------------
    def expression(self, node):
        if isinstance(node, Literal):
            if isinstance(node.value, bool):
                self.emit(0x41, sleb(1 if node.value else 0))
            elif isinstance(node.value, int):
                self.emit(0x41, sleb(node.value))
            else:
                self.compiler.flag(node, "only integer literals compile to WASM")
                self.emit(0x41, sleb(0))
            return

        if isinstance(node, Variable):
            if node.name in self.locals:
                self.emit(0x20, uleb(self.locals[node.name]))
            elif node.name in self.compiler.globals:
                self.emit(0x23, uleb(self.compiler.globals[node.name]))
            else:
                self.compiler.flag(node, f"unknown variable '{node.name}'")
                self.emit(0x41, sleb(0))
            return

        if isinstance(node, Unary):
            if node.op == "NOT":
                self.expression(node.operand)
                self.emit(0x45)          # i32.eqz
            else:
                self.compiler.flag(node, f"unary operator '{node.op}'")
                self.emit(0x41, sleb(0))
            return

        if isinstance(node, Binary):
            opcode = OPCODES.get(node.op)
            if opcode is None:
                self.compiler.flag(node, f"operator '{node.op}'")
                self.emit(0x41, sleb(0))
                return
            self.expression(node.left)
            self.expression(node.right)
            self.emit(opcode)
            return

        if isinstance(node, Call):
            if " from " in node.name or node.name not in self.compiler.functions:
                self.compiler.flag(node, f"call to '{node.name}' is not compilable")
                self.emit(0x41, sleb(0))
                return
            expected = self.compiler.signatures[node.name]
            supplied = [label for label, _value in node.args]
            if supplied != expected:
                self.compiler.flag(
                    node,
                    f"call to '{node.name}' has labels {supplied}, expected {expected}")
                self.emit(0x41, sleb(0))
                return
            for _label, value in node.args:
                self.expression(value)
            self.emit(0x10, uleb(self.compiler.functions[node.name]))
            return

        self.compiler.flag(node, "expression form is not compilable")
        self.emit(0x41, sleb(0))

    # --- statements ------------------------------------------------------
    def statements(self, statements):
        for statement in statements:
            self.statement(statement)

    def statement(self, node):
        if isinstance(node, Set):
            self.expression(node.expr)
            if node.name in self.locals:
                self.emit(0x21, uleb(self.locals[node.name]))   # local.set
            elif node.name in self.compiler.globals:
                self.emit(0x24, uleb(self.compiler.globals[node.name]))  # global.set
            else:
                self.compiler.flag(node, f"unknown assignment target '{node.name}'")
            return

        if isinstance(node, Show):
            self.expression(node.expr)
            self.emit(0x1A)              # drop
            self.compiler.note(node, "show is a no-op in WASM (no host I/O)")
            return

        if isinstance(node, Return):
            self.expression(node.expr)
            self.emit(0x0F)              # return
            return

        if isinstance(node, If):
            for condition, body in node.branches:
                self.expression(condition)
                self.frames.append("if")
                self.emit(0x04, VOID)    # if void
                self.statements(body.statements)
                if node.otherwise is not None or len(node.branches) > 1:
                    self.emit(0x05)      # else
                self.frames.pop()
            if node.otherwise is not None:
                self.statements(node.otherwise.statements)
            for _ in node.branches:
                self.emit(0x0B)          # end
            return

        if isinstance(node, RepeatWhile):
            self.frames.append("block")
            self.frames.append("loop")
            self.emit(0x02, VOID)        # block
            self.emit(0x03, VOID)        # loop
            self.expression(node.cond)
            self.emit(0x45)              # i32.eqz
            self.emit(0x0D, uleb(1))     # br_if 1 -> exit block
            self.statements(node.body.statements)
            self.emit(0x0C, uleb(0))     # br 0 -> repeat loop
            self.emit(0x0B)              # end loop
            self.emit(0x0B)              # end block
            self.frames.pop()
            self.frames.pop()
            return

        if isinstance(node, Break):
            depth = self.br_depth("block")
            if depth is None:
                self.compiler.flag(node, "break outside a loop")
            else:
                self.emit(0x0C, uleb(depth))
            return

        if isinstance(node, Continue):
            depth = self.br_depth("loop")
            if depth is None:
                self.compiler.flag(node, "continue outside a loop")
            else:
                self.emit(0x0C, uleb(depth))
            return

        self.compiler.flag(node, "statement form is not compilable")

    def body(self) -> bytes:
        self.statements(self.definition.body.statements)
        self.emit(0x41, sleb(0))         # default i32 result
        extra_locals = len(self.locals) - len(self.definition.params)
        declarations = vec([]) if extra_locals <= 0 else vec([uleb(extra_locals) + bytes([I32])])
        body = declarations + bytes(self.code) + b"\x0b"
        return uleb(len(body)) + body


class Compiler:
    def __init__(self):
        self.unsupported: list = []
        self.notes: list = []
        self.functions: dict[str, int] = {}
        self.signatures: dict[str, list] = {}
        self.globals: dict[str, int] = {}
        self.definitions: list = []
        self.node_count = 0

    def flag(self, node, reason):
        self.unsupported.append(CompileUnsupported(
            type(node).__name__, reason, getattr(node, "pos", None).line
            if getattr(node, "pos", None) else None))

    def note(self, node, reason):
        self.notes.append(CompileUnsupported(
            type(node).__name__, reason, getattr(node, "pos", None).line
            if getattr(node, "pos", None) else None))

    def compile(self, program: Program) -> CompileResult:
        for statement in program.statements:
            if isinstance(statement, FunctionDef):
                self.functions[statement.name] = len(self.functions)
                self.signatures[statement.name] = list(statement.params)
                self.definitions.append(statement)
            elif isinstance(statement, Set) and isinstance(statement.expr, Literal) \
                    and isinstance(statement.expr.value, int):
                self.globals[statement.name] = len(self.globals)
            else:
                self.flag(statement, "top-level form is not compilable")

        compiled = []
        for index, definition in enumerate(self.definitions):
            function_compiler = _FunctionCompiler(self, definition)
            compiled.append(function_compiler.body())

        type_section = section(1, vec([
            b"\x60"
            + vec([bytes([I32])] * len(definition.params))
            + vec([bytes([I32])])
            for definition in self.definitions
        ]))
        function_section = section(3, vec([uleb(index) for index in range(len(self.definitions))]))
        global_section = section(6, vec([
            bytes([I32, 0x01]) + b"\x41" + sleb(self._global_value(program, name)) + b"\x0b"
            for name in self.globals
        ]))
        export_section = section(7, vec([
            name(definition.name) + b"\x00" + uleb(index)
            for index, definition in enumerate(self.definitions)
        ]))
        code_section = section(10, vec(compiled))

        wasm = b"\x00asm\x01\x00\x00\x00" + type_section + function_section \
            + global_section + export_section + code_section
        return CompileResult(
            wasm=wasm,
            unsupported=self.unsupported,
            stats={"functions": len(self.definitions),
                   "globals": len(self.globals),
                   "bytes": len(wasm),
                   "notes": len(self.notes)},
        )

    def _global_value(self, program, wanted):
        for statement in program.statements:
            if isinstance(statement, Set) and statement.name == wanted:
                return statement.expr.value
        return 0


def compile_program(program: Program) -> CompileResult:
    return Compiler().compile(program)


def compile_source(source: str) -> CompileResult:
    program = Parser(Lexer(source).tokenize()).parse_program()
    return compile_program(program)
