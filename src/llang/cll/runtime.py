"""Checked interpreter for c-ll v1.

Pipeline: parse -> static type/layout check -> execute.  English-surface programs
never enter this module, so their behavior is unchanged.

The execution model is deliberately tiny but *addressable*:

* every object lives in a :class:`CCell` (type + value);
* :class:`CBlock` is a contiguous run of cells (a local object, an array, or an
  allocation); :class:`CPointer` is ``(block, index, pointee)`` so arithmetic and
  indexing are bounds-checked against the block;
* :class:`CArray` and :class:`CStruct` wrap cells for aggregate values.

Every C undefined-behaviour case from the design is replaced by a loud,
source-located error: signed overflow, division by zero, null/out-of-bounds
dereference, use-after-free, double/invalid free, unrelated pointer comparison,
out-of-range float->int conversion, missing return, and type errors.
"""

import math
from dataclasses import dataclass, field
from typing import Optional

from .ast import (
    CType, INT, FLOAT, VOID, TEXT, NULL_TYPE, pointer_to,
    Program, Block, Literal, Null, Variable, Unary, Binary, Cast, AddressOf,
    Deref, Index, MemberAccess, SizeOf, Alloc, Free, Call, TypedDecl, Set,
    Show, StructDef, FunctionDef, Return, If, RepeatWhile, CountedLoop, Break,
    Continue,
)
from ..errors import LangError, RuntimeErrorLang, SourcePos


INT_MIN = -(2 ** 31)
INT_MAX = 2 ** 31 - 1

_LVALUE_NODES = (Variable, Deref, Index, MemberAccess)


def _err(message: str, pos: Optional[SourcePos]) -> RuntimeErrorLang:
    return RuntimeErrorLang(message, pos)


# ---------------------------------------------------------------------------
# Layout (the pinned LP64-like model: int 4, float 8, pointer 8)
# ---------------------------------------------------------------------------

def _round_up(value: int, align: int) -> int:
    return (value + align - 1) // align * align


def type_align(ctype: CType, structs: dict, _stack=None) -> int:
    if ctype is None:
        return 1
    if ctype.kind == "int":
        return 4
    if ctype.kind in ("float", "pointer", "text"):
        return 8
    if ctype.kind == "array":
        return type_align(ctype.element, structs, _stack)
    if ctype.kind == "struct":
        return struct_layout(ctype.name, structs, _stack)[2]
    return 1


def type_size(ctype: CType, structs: dict, _stack=None) -> int:
    if ctype is None or ctype.kind in ("void",):
        return 0
    if ctype.kind == "int":
        return 4
    if ctype.kind in ("float", "pointer", "text"):
        return 8
    if ctype.kind == "array":
        return (ctype.length or 0) * type_size(ctype.element, structs, _stack)
    if ctype.kind == "struct":
        return struct_layout(ctype.name, structs, _stack)[1]
    return 0


def struct_layout(name: str, structs: dict, _stack=None):
    """Return ``(fields, size, align)`` for a struct.

    ``fields`` is a list of ``(field_name, offset, CType)`` in declaration order.
    A by-value cycle is rejected; self-reference through a pointer is fine
    because pointer size does not depend on the pointee's layout.
    """
    if not hasattr(struct_layout, "_cache"):
        struct_layout._cache = {}
    key = (id(structs), name)
    if key in struct_layout._cache:
        return struct_layout._cache[key]
    stack = set() if _stack is None else _stack
    if name in stack:
        raise RuntimeErrorLang(
            f"type error: struct {name} contains itself by value", None)
    if name not in structs:
        raise RuntimeErrorLang(f"unknown struct '{name}'", None)
    stack = stack | {name}

    offset = 0
    align = 1
    entries = []
    for field_name, field_type in structs[name]:
        falign = type_align(field_type, structs, stack)
        offset = _round_up(offset, falign)
        entries.append((field_name, offset, field_type))
        offset += type_size(field_type, structs, stack)
        align = max(align, falign)
    size = _round_up(offset, align)
    result = (entries, size, align)
    struct_layout._cache[key] = result
    return result


def clear_layout_cache() -> None:
    if hasattr(struct_layout, "_cache"):
        struct_layout._cache.clear()


# ---------------------------------------------------------------------------
# Runtime values
# ---------------------------------------------------------------------------

@dataclass
class CCell:
    ctype: CType
    value: object
    container: Optional["CBlock"] = None
    index: int = 0


@dataclass
class CBlock:
    cells: list
    ctype: CType
    freed: bool = False


@dataclass
class CPointer:
    block: Optional[CBlock]
    index: int
    pointee: CType

    @property
    def is_null(self) -> bool:
        return self.block is None

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return "null pointer" if self.is_null else f"pointer({self.index})"


@dataclass
class CArray:
    block: CBlock
    element: CType
    length: int


@dataclass
class CStruct:
    name: str
    fields: dict
    order: list
    ctype: CType


def make_block(element: CType, count: int, structs: dict) -> CBlock:
    cells = [CCell(element, zero_value(element, structs)) for _ in range(count)]
    block = CBlock(cells, element)
    for index, cell in enumerate(cells):
        cell.container = block
        cell.index = index
    return block


def zero_value(ctype: CType, structs: dict):
    if ctype.kind == "int":
        return 0
    if ctype.kind == "float":
        return 0.0
    if ctype.kind == "pointer":
        return CPointer(None, 0, ctype.pointee)
    if ctype.kind == "array":
        return CArray(make_block(ctype.element, ctype.length or 0, structs),
                      ctype.element, ctype.length or 0)
    if ctype.kind == "struct":
        entries = struct_layout(ctype.name, structs)[0]
        fields = {}
        order = []
        for name, _offset, ftype in entries:
            fields[name] = CCell(ftype, zero_value(ftype, structs))
            order.append(name)
        return CStruct(ctype.name, fields, order, ctype)
    if ctype.kind == "text":
        return ""
    raise RuntimeErrorLang(f"cannot create a value of type {ctype}", None)


# ---------------------------------------------------------------------------
# Signalling flow control
# ---------------------------------------------------------------------------

class ReturnSignal(Exception):
    def __init__(self, value, pos=None):
        self.value = value
        self.pos = pos


class BreakSignal(Exception):
    def __init__(self, pos=None):
        self.pos = pos


class ContinueSignal(Exception):
    def __init__(self, pos=None):
        self.pos = pos


class CEnv:
    """A lexical scope holding typed cells (blocks introduce new scopes)."""

    def __init__(self, parent=None):
        self.parent = parent
        self.cells = {}

    def declare(self, name: str, ctype: CType, value, pos=None) -> CCell:
        if name in self.cells:
            raise _err(f"name '{name}' is already declared in this scope", pos)
        cell = CCell(ctype, value)
        self.cells[name] = cell
        return cell

    def get_cell(self, name: str, pos=None) -> CCell:
        scope = self
        while scope is not None:
            if name in scope.cells:
                return scope.cells[name]
            scope = scope.parent
        raise _err(f"undefined name '{name}'", pos)


# ---------------------------------------------------------------------------
# Static checker
# ---------------------------------------------------------------------------

@dataclass
class TypeReport:
    errors: list = field(default_factory=list)
    structs: dict = field(default_factory=dict)   # name -> [(field, CType)]
    layouts: dict = field(default_factory=dict)   # name -> (entries, size, align)
    types: dict = field(default_factory=dict)     # id(node) -> CType


class _Scope:
    def __init__(self, parent=None):
        self.parent = parent
        self.names = {}

    def declare(self, name, ctype, pos):
        if name in self.names:
            raise _err(f"name '{name}' is already declared in this scope", pos)
        self.names[name] = ctype

    def lookup(self, name, pos):
        scope = self
        while scope is not None:
            if name in scope.names:
                return scope.names[name]
            scope = scope.parent
        raise _err(f"undefined name '{name}'", pos)


class _Context:
    def __init__(self, return_type=None, in_loop=False):
        self.return_type = return_type
        self.in_loop = in_loop

    def child(self, in_loop=None):
        return _Context(self.return_type,
                        self.in_loop if in_loop is None else in_loop)


class TypeChecker:
    """Validates types, lvalues, arity, layout and return paths before execution."""

    def check(self, program: Program) -> TypeReport:
        report = TypeReport()
        clear_layout_cache()
        self.report = report
        self._functions = {}

        # Pass 1: definitions (order independent, so recursion/self-reference work).
        for statement in program.statements:
            if isinstance(statement, StructDef):
                self._define_struct(statement)
            elif isinstance(statement, FunctionDef):
                self._define_function(statement)
        struct_pos = {stmt.name: stmt.pos for stmt in program.statements
                      if isinstance(stmt, StructDef)}
        for name, fields in report.structs.items():
            try:
                report.layouts[name] = struct_layout(name, report.structs)
            except RuntimeErrorLang as exc:
                report.errors.append(
                    _err(exc.message, struct_pos.get(name)))

        # Pass 2: executables.
        global_scope = _Scope()
        for statement in program.statements:
            if isinstance(statement, (StructDef, FunctionDef)):
                continue
            try:
                self._check_stmt(statement, global_scope, _Context())
            except RuntimeErrorLang as exc:
                report.errors.append(exc)
        for definition in program.statements:
            if not isinstance(definition, FunctionDef):
                continue
            scope = _Scope(global_scope)
            for name, ctype in definition.params:
                scope.declare(name, ctype, definition.pos)
            try:
                self._check_stmt(definition.body, scope,
                                 _Context(definition.return_type, False))
            except RuntimeErrorLang as exc:
                report.errors.append(exc)
        return report

    # --- definitions -----------------------------------------------------
    def _define_struct(self, node: StructDef):
        if node.name in self.report.structs:
            self.report.errors.append(
                _err(f"struct '{node.name}' is defined twice", node.pos))
            return
        # Register the name *before* validating fields so self-reference via
        # `pointer to struct T` resolves to the struct being defined.
        self.report.structs[node.name] = []
        fields = []
        seen = set()
        for name, ctype in node.fields:
            if name in seen:
                self.report.errors.append(
                    _err(f"duplicate field '{name}' in struct {node.name}", node.pos))
            seen.add(name)
            try:
                self._validate_type(ctype, node.pos)
            except RuntimeErrorLang as exc:
                self.report.errors.append(exc)
            fields.append((name, ctype))
        self.report.structs[node.name] = fields

    def _define_function(self, node: FunctionDef):
        if not hasattr(self, "_functions"):
            self._functions = {}
        if node.name in self._functions:
            self.report.errors.append(
                _err(f"function '{node.name}' is defined twice", node.pos))
            return
        try:
            self._validate_type(node.return_type, node.pos)
            seen = set()
            for name, ctype in node.params:
                if name in seen:
                    raise _err(f"duplicate parameter '{name}'", node.pos)
                seen.add(name)
                self._validate_type(ctype, node.pos)
        except RuntimeErrorLang as exc:
            self.report.errors.append(exc)
        self._functions[node.name] = node

    def _validate_type(self, ctype: CType, pos):
        if ctype is None:
            raise _err("missing type", pos)
        if ctype.kind in ("int", "float", "void", "text"):
            return
        if ctype.kind == "pointer":
            self._validate_type(ctype.pointee, pos)
            return
        if ctype.kind == "array":
            if ctype.length is None or ctype.length < 0:
                raise _err("array length must be non-negative", pos)
            self._validate_type(ctype.element, pos)
            return
        if ctype.kind == "struct":
            if ctype.name not in self.report.structs:
                raise _err(f"unknown struct '{ctype.name}'", pos)
            return
        raise _err(f"unknown type '{ctype.kind}'", pos)

    # --- helpers ---------------------------------------------------------
    def _annotate(self, node, ctype):
        self.report.types[id(node)] = ctype
        return ctype

    @staticmethod
    def _compatible(actual: CType, expected: CType) -> bool:
        if actual == expected:
            return True
        # `null pointer` is the one implicit conversion in v1.
        if expected.kind == "pointer" and actual.kind == "pointer" \
                and actual.pointee is None:
            return True
        return False

    def _expect(self, actual, expected, node, what):
        if not self._compatible(actual, expected):
            raise _err(f"type error: {what} has type {actual}, expected {expected}",
                       getattr(node, "pos", None))

    @staticmethod
    def _is_lvalue(node) -> bool:
        return isinstance(node, _LVALUE_NODES)

    @staticmethod
    def _is_scalar(ctype: CType) -> bool:
        return ctype is not None and (ctype.kind in ("int", "float")
                                      or ctype.kind == "pointer")

    def _get_field(self, ctype, field, node):
        ctype = self._validate_type_name(ctype, node)
        if ctype.kind != "struct":
            raise _err(f"member access requires a struct, got {ctype}",
                       getattr(node, "pos", None))
        fields = dict(self.report.structs.get(ctype.name, []))
        if field not in fields:
            raise _err(f"struct {ctype.name} has no field '{field}'",
                       getattr(node, "pos", None))
        return fields[field]

    def _validate_type_name(self, ctype, node):
        if ctype.kind == "struct" and ctype.name not in self.report.structs:
            raise _err(f"unknown struct '{ctype.name}'", getattr(node, "pos", None))
        return ctype

    # --- statements ------------------------------------------------------
    def _check_stmt(self, node, scope, ctx):
        if isinstance(node, Block):
            child = _Scope(scope)
            for stmt in node.statements:
                self._check_stmt(stmt, child, ctx)
            return
        if isinstance(node, TypedDecl):
            self._validate_type(node.ctype, node.pos)
            if node.ctype.kind == "void":
                raise _err("cannot declare a variable of type void", node.pos)
            actual = self._infer(node.init, scope, ctx)
            self._expect(actual, node.ctype, node, "initializer")
            scope.declare(node.name, node.ctype, node.pos)
            return
        if isinstance(node, Set):
            if not self._is_lvalue(node.target):
                raise _err("the target of 'set' must be an lvalue", node.pos)
            target_type = self._infer(node.target, scope, ctx)
            value_type = self._infer(node.expr, scope, ctx)
            self._expect(value_type, target_type, node, "assigned value")
            return
        if isinstance(node, Show):
            for expr in node.exprs:
                ctype = self._infer(expr, scope, ctx)
                if ctype.kind not in ("int", "float", "text"):
                    raise _err(f"cannot show a value of type {ctype}",
                               getattr(expr, "pos", node.pos))
            return
        if isinstance(node, If):
            for cond, body in node.branches:
                if not self._is_scalar(self._infer(cond, scope, ctx)):
                    raise _err("condition must be a scalar", getattr(cond, "pos", node.pos))
                self._check_stmt(body, scope, ctx)
            if node.otherwise is not None:
                self._check_stmt(node.otherwise, scope, ctx)
            return
        if isinstance(node, RepeatWhile):
            if not self._is_scalar(self._infer(node.cond, scope, ctx)):
                raise _err("condition must be a scalar", getattr(node.cond, "pos", node.pos))
            self._check_stmt(node.body, scope, ctx.child(in_loop=True))
            return
        if isinstance(node, CountedLoop):
            for part in (node.start, node.limit, node.step):
                self._expect(self._infer(part, scope, ctx), INT, part, "loop bound")
            child = _Scope(scope)
            child.declare(node.name, INT, node.pos)
            for stmt in node.body.statements:
                self._check_stmt(stmt, child, ctx.child(in_loop=True))
            return
        if isinstance(node, Break):
            if not ctx.in_loop:
                raise _err("'stop the loop' outside a loop", node.pos)
            return
        if isinstance(node, Continue):
            if not ctx.in_loop:
                raise _err("'skip to the next item' outside a loop", node.pos)
            return
        if isinstance(node, Return):
            if ctx.return_type is None:
                raise _err("'give back' outside a function", node.pos)
            if ctx.return_type.kind == "void":
                raise _err("cannot give a value back from a void function", node.pos)
            actual = self._infer(node.expr, scope, ctx)
            self._expect(actual, ctx.return_type, node, "return value")
            return
        if isinstance(node, Call):
            self._infer(node, scope, ctx)
            return
        if isinstance(node, Free):
            self._infer(node, scope, ctx)
            return
        if isinstance(node, (StructDef, FunctionDef)):
            return
        raise _err(f"cannot check statement {type(node).__name__}",
                   getattr(node, "pos", None))

    # --- expressions -----------------------------------------------------
    def _infer(self, node, scope, ctx):
        if isinstance(node, Literal):
            if node.ctype is INT and isinstance(node.value, int) \
                    and not (INT_MIN <= node.value <= INT_MAX):
                raise _err("integer literal out of int range", getattr(node, "pos", None))
            return self._annotate(node, node.ctype)
        if isinstance(node, Null):
            return self._annotate(node, NULL_TYPE)
        if isinstance(node, Variable):
            return self._annotate(node, scope.lookup(node.name, node.pos))
        if isinstance(node, Unary):
            operand = self._infer(node.operand, scope, ctx)
            if not self._is_scalar(operand):
                raise _err("'not' requires a scalar", node.pos)
            return self._annotate(node, INT)
        if isinstance(node, Cast):
            self._validate_type(node.target, node.pos)
            if node.target.kind not in ("int", "float"):
                raise _err("v1 can only cast between int and float", node.pos)
            actual = self._infer(node.expr, scope, ctx)
            if actual.kind not in ("int", "float"):
                raise _err("cast requires an int or float operand", node.pos)
            return self._annotate(node, node.target)
        if isinstance(node, AddressOf):
            if not self._is_lvalue(node.expr):
                raise _err("'address of' requires an lvalue", node.pos)
            t = self._infer(node.expr, scope, ctx)
            return self._annotate(node, pointer_to(t))
        if isinstance(node, Deref):
            t = self._infer(node.expr, scope, ctx)
            if t.kind != "pointer" or t.pointee is None:
                raise _err("'value at' requires a typed pointer", node.pos)
            return self._annotate(node, t.pointee)
        if isinstance(node, Index):
            base = self._infer(node.base, scope, ctx)
            self._expect(self._infer(node.index, scope, ctx), INT, node, "index")
            if base.kind == "array":
                return self._annotate(node, base.element)
            if base.kind == "pointer" and base.pointee is not None:
                return self._annotate(node, base.pointee)
            raise _err("'item ... of' requires an array or pointer", node.pos)
        if isinstance(node, MemberAccess):
            base = self._infer(node.base, scope, ctx)
            if node.via_pointer:
                if base.kind != "pointer" or base.pointee is None:
                    raise _err("'member ... via' requires a pointer to struct", node.pos)
                base = base.pointee
            return self._annotate(node, self._get_field(base, node.field, node))
        if isinstance(node, SizeOf):
            self._validate_type(node.target, node.pos)
            if node.target.kind == "void":
                raise _err("cannot take the size of void", node.pos)
            return self._annotate(node, INT)
        if isinstance(node, Alloc):
            self._validate_type(node.element, node.pos)
            if node.element.kind == "void":
                raise _err("cannot allocate void", node.pos)
            self._expect(self._infer(node.count, scope, ctx), INT, node, "count")
            return self._annotate(node, pointer_to(node.element))
        if isinstance(node, Free):
            t = self._infer(node.expr, scope, ctx)
            if t.kind != "pointer":
                raise _err("'free' requires a pointer", node.pos)
            return self._annotate(node, VOID)
        if isinstance(node, Call):
            definition = getattr(self, "_functions", {}).get(node.name)
            if definition is None:
                raise _err(f"unknown function '{node.name}'", node.pos)
            if len(node.args) != len(definition.params):
                raise _err(
                    f"function '{node.name}' takes {len(definition.params)} "
                    f"arguments, got {len(node.args)}", node.pos)
            for (pname, ptype), arg in zip(definition.params, node.args):
                actual = self._infer(arg, scope, ctx)
                self._expect(actual, ptype, arg, f"argument '{pname}'")
            return self._annotate(node, definition.return_type)
        if isinstance(node, Binary):
            return self._annotate(node, self._infer_binary(node, scope, ctx))
        raise _err(f"cannot type expression {type(node).__name__}",
                   getattr(node, "pos", None))

    def _infer_binary(self, node, scope, ctx):
        op = node.op
        left = self._infer(node.left, scope, ctx)
        right = self._infer(node.right, scope, ctx)

        if op in ("LAND", "LOR"):
            if not (self._is_scalar(left) and self._is_scalar(right)):
                raise _err(f"'{op}' requires scalars", node.pos)
            return INT

        if op in ("EQ", "NE", "LT", "LE", "GT", "GE"):
            if left.kind == "pointer" or right.kind == "pointer":
                if not (left.kind == "pointer" and right.kind == "pointer"):
                    raise _err("cannot compare a pointer with a non-pointer", node.pos)
                if (left.pointee is not None and right.pointee is not None
                        and left != right):
                    raise _err("cannot compare pointers of different types", node.pos)
                return INT
            if left.kind == right.kind and left.kind in ("int", "float"):
                return INT
            raise _err(f"cannot compare {left} with {right}", node.pos)

        if op in ("ADD", "SUB") and left.kind == "pointer" and right.kind == "int":
            if left.pointee is None:
                raise _err("pointer arithmetic requires a typed pointer", node.pos)
            return left
        if op == "ADD" and left.kind == "int" and right.kind == "pointer":
            if right.pointee is None:
                raise _err("pointer arithmetic requires a typed pointer", node.pos)
            return right
        if op == "SUB" and left.kind == "pointer" and right.kind == "pointer":
            if left.pointee is None or right.pointee is None or left != right:
                raise _err("pointer subtraction requires compatible pointers", node.pos)
            return INT

        if left != right:
            raise _err(f"type error: operator '{op}' cannot mix {left} and {right}",
                       node.pos)
        if left.kind == "int":
            if op in ("ADD", "SUB", "MUL", "DIV", "REM"):
                return INT
        if left.kind == "float":
            if op in ("ADD", "SUB", "MUL", "DIV"):
                return FLOAT
        raise _err(f"operator '{op}' is not defined for {left}", node.pos)


# ---------------------------------------------------------------------------
# Checked evaluator
# ---------------------------------------------------------------------------

def _truthy(value) -> bool:
    if isinstance(value, CPointer):
        return not value.is_null
    if isinstance(value, CArray) or isinstance(value, CStruct):
        return True
    return bool(value)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_float(value) -> bool:
    return isinstance(value, float)


class CInterpreter:
    """Executes a checked c-ll Program with pinned, source-located errors."""

    def __init__(self, max_iterations: int = 100_000):
        self.output: list[str] = []
        self.max_iterations = max_iterations
        self.global_env = CEnv()
        self.functions: dict[str, FunctionDef] = {}
        self.structs: dict[str, list] = {}
        self.report: Optional[TypeReport] = None

    # --- driver ----------------------------------------------------------
    def run(self, program: Program):
        self.report = TypeChecker().check(program)
        if self.report.errors:
            raise self.report.errors[0]
        self.structs = dict(self.report.structs)
        clear_layout_cache()
        # Definitions are visible throughout the program, regardless of the
        # order in which their defining statements appear.
        for statement in program.statements:
            if isinstance(statement, StructDef):
                self.structs[statement.name] = list(statement.fields)
            elif isinstance(statement, FunctionDef):
                self.functions[statement.name] = statement
        try:
            self._exec_block(program, self.global_env, _Context())
        except ReturnSignal as signal:
            raise _err("'give back' used outside a function", signal.pos)
        except BreakSignal as signal:
            raise _err("'stop the loop' used outside a loop", signal.pos)
        except ContinueSignal as signal:
            raise _err("'skip to the next item' used outside a loop", signal.pos)
        return self

    # --- values ----------------------------------------------------------
    def _coerce(self, value, ctype: CType, pos):
        """Apply v1's only implicit conversion: null literal -> typed pointer."""
        if isinstance(value, CPointer) and value.is_null and ctype.kind == "pointer":
            if value.pointee is None:
                return CPointer(None, 0, ctype.pointee)
        return self._copy_value(value)

    def _copy_value(self, value):
        """Struct/array assignment in C copies bytes; pointers stay aliases."""
        if isinstance(value, CArray):
            block = make_block(value.element, value.length, self.structs)
            for old, new in zip(value.block.cells, block.cells):
                new.value = self._copy_value(old.value)
            return CArray(block, value.element, value.length)
        if isinstance(value, CStruct):
            fields = {}
            for name, cell in value.fields.items():
                fields[name] = CCell(cell.ctype, self._copy_value(cell.value))
            return CStruct(value.name, fields, list(value.order), value.ctype)
        return value

    def _checked_int(self, value: int, pos):
        if value < INT_MIN or value > INT_MAX:
            raise _err("integer overflow", pos)
        return value

    @staticmethod
    def _trunc_div(a: int, b: int) -> int:
        q = abs(a) // abs(b)
        return -q if (a < 0) != (b < 0) else q

    def _idiv(self, a: int, b: int, pos):
        if b == 0:
            raise _err("division by zero", pos)
        if a == INT_MIN and b == -1:
            raise _err("integer overflow", pos)
        return self._checked_int(self._trunc_div(a, b), pos)

    def _irem(self, a: int, b: int, pos):
        if b == 0:
            raise _err("division by zero", pos)
        if a == INT_MIN and b == -1:
            raise _err("integer overflow", pos)
        return self._checked_int(a - self._trunc_div(a, b) * b, pos)

    @staticmethod
    def _fdiv(a: float, b: float):
        if b == 0.0:
            if a == 0.0 or math.isnan(a):
                return float("nan")
            return math.copysign(float("inf"), a) * math.copysign(1.0, b)
        return a / b

    def _cell(self, pointer: CPointer, pos, action: str = "dereference") -> CCell:
        if pointer.is_null:
            raise _err(f"null pointer {action}", pos)
        if pointer.block.freed:
            raise _err("use after free", pos)
        if pointer.index < 0 or pointer.index >= len(pointer.block.cells):
            raise _err("pointer out of bounds", pos)
        return pointer.block.cells[pointer.index]

    # --- statements ------------------------------------------------------
    def _exec_block(self, block, env, ctx):
        for statement in block.statements:
            self._exec_stmt(statement, env, ctx)

    def _exec_stmt(self, node, env, ctx):
        if isinstance(node, Block):
            child = CEnv(env)
            for statement in node.statements:
                self._exec_stmt(statement, child, ctx)
            return
        if isinstance(node, StructDef):
            self.structs[node.name] = list(node.fields)
            clear_layout_cache()
            return
        if isinstance(node, FunctionDef):
            self.functions[node.name] = node
            return
        if isinstance(node, TypedDecl):
            value = self._eval(node.init, env)
            value = self._coerce(value, node.ctype, node.pos)
            env.declare(node.name, node.ctype, value, node.pos)
            return
        if isinstance(node, Set):
            cell = self._eval_lvalue(node.target, env)
            value = self._coerce(self._eval(node.expr, env), cell.ctype, node.pos)
            cell.value = value
            return
        if isinstance(node, Show):
            pieces = []
            for expr in node.exprs:
                pieces.append(self._render(self._eval(expr, env)))
            text = " ".join(pieces)
            self.output.append(text)
            print(text)
            return
        if isinstance(node, If):
            for cond, body in node.branches:
                if _truthy(self._eval(cond, env)):
                    self._exec_stmt(body, CEnv(env), ctx)
                    return
            if node.otherwise is not None:
                self._exec_stmt(node.otherwise, CEnv(env), ctx)
            return
        if isinstance(node, RepeatWhile):
            iterations = 0
            while _truthy(self._eval(node.cond, env)):
                iterations += 1
                if iterations > self.max_iterations:
                    raise _err("loop exceeded iteration limit (possible infinite loop)",
                               node.pos)
                try:
                    self._exec_stmt(node.body, CEnv(env), ctx.child(in_loop=True))
                except ContinueSignal:
                    continue
                except BreakSignal:
                    break
            return
        if isinstance(node, CountedLoop):
            value = self._eval(node.start, env)
            limit = self._eval(node.limit, env)
            step = self._eval(node.step, env)
            if step == 0:
                raise _err("counted loop step cannot be zero", node.pos)
            iterations = 0
            while (value < limit) if step > 0 else (value > limit):
                iterations += 1
                if iterations > self.max_iterations:
                    raise _err("loop exceeded iteration limit (possible infinite loop)",
                               node.pos)
                child = CEnv(env)
                cell = child.declare(node.name, INT, value, node.pos)
                try:
                    self._exec_stmt(node.body, child, ctx.child(in_loop=True))
                except ContinueSignal:
                    pass
                except BreakSignal:
                    break
                value = self._checked_int(cell.value + step, node.pos)
            return
        if isinstance(node, Return):
            raise ReturnSignal(self._eval(node.expr, env), node.pos)
        if isinstance(node, Break):
            raise BreakSignal(node.pos)
        if isinstance(node, Continue):
            raise ContinueSignal(node.pos)
        if isinstance(node, Call):
            self._call(node, env)
            return
        if isinstance(node, Free):
            self._free(self._eval(node.expr, env), node.pos)
            return
        raise _err(f"cannot execute node {type(node).__name__}",
                   getattr(node, "pos", None))

    # --- expressions -----------------------------------------------------
    def _eval(self, node, env):
        if isinstance(node, Literal):
            return node.value
        if isinstance(node, Null):
            return CPointer(None, 0, None)
        if isinstance(node, Variable):
            return env.get_cell(node.name, node.pos).value
        if isinstance(node, Cast):
            return self._cast(self._eval(node.expr, env), node.target, node.pos)
        if isinstance(node, AddressOf):
            cell = self._eval_lvalue(node.expr, env)
            if cell.container is None:
                block = CBlock([cell], cell.ctype)
                cell.container = block
                cell.index = 0
                return CPointer(block, 0, cell.ctype)
            return CPointer(cell.container, cell.index, cell.ctype)
        if isinstance(node, (Deref, Index, MemberAccess)):
            return self._eval_lvalue(node, env).value
        if isinstance(node, SizeOf):
            return type_size(node.target, self.structs)
        if isinstance(node, Alloc):
            return self._allocate(node, env)
        if isinstance(node, Call):
            return self._call(node, env)
        if isinstance(node, Binary):
            return self._eval_binary(node, env)
        if isinstance(node, Unary):
            if node.op == "LNOT":
                return 0 if _truthy(self._eval(node.operand, env)) else 1
            raise _err(f"unknown unary operator '{node.op}'", node.pos)
        raise _err(f"cannot evaluate node {type(node).__name__}",
                   getattr(node, "pos", None))

    def _eval_lvalue(self, node, env) -> CCell:
        if isinstance(node, Variable):
            return env.get_cell(node.name, node.pos)
        if isinstance(node, Deref):
            pointer = self._eval(node.expr, env)
            if not isinstance(pointer, CPointer):
                raise _err("'value at' requires a pointer", node.pos)
            return self._cell(pointer, node.pos)
        if isinstance(node, Index):
            base = self._eval(node.base, env)
            index = self._eval(node.index, env)
            if not _is_int(index):
                raise _err("index must be an int", node.pos)
            if isinstance(base, CArray):
                if index < 0 or index >= base.length:
                    raise _err(f"array index {index} is out of bounds", node.pos)
                return base.block.cells[index]
            if isinstance(base, CPointer):
                if base.is_null:
                    raise _err("null pointer dereference", node.pos)
                if base.block.freed:
                    raise _err("use after free", node.pos)
                effective = base.index + index
                if effective < 0 or effective >= len(base.block.cells):
                    raise _err("pointer out of bounds", node.pos)
                return base.block.cells[effective]
            raise _err("'item ... of' requires an array or pointer", node.pos)
        if isinstance(node, MemberAccess):
            if node.via_pointer:
                pointer = self._eval(node.base, env)
                if not isinstance(pointer, CPointer):
                    raise _err("'member ... via' requires a pointer", node.pos)
                struct = self._cell(pointer, node.pos).value
            else:
                struct = self._eval(node.base, env)
            if not isinstance(struct, CStruct):
                raise _err("member access requires a struct", node.pos)
            if node.field not in struct.fields:
                raise _err(f"struct {struct.name} has no field '{node.field}'",
                           node.pos)
            return struct.fields[node.field]
        raise _err("not an lvalue", getattr(node, "pos", None))

    def _cast(self, value, target: CType, pos):
        if target.kind == "int":
            if _is_float(value):
                if math.isnan(value) or math.isinf(value) \
                        or value < INT_MIN or value > INT_MAX:
                    raise _err("invalid conversion: float is out of int range", pos)
                return int(value)          # C truncates toward zero
            if _is_int(value):
                return value
        elif target.kind == "float":
            if _is_int(value) or _is_float(value):
                return float(value)
        raise _err(f"invalid cast to {target}", pos)

    def _allocate(self, node: Alloc, env):
        count = self._eval(node.count, env)
        if not _is_int(count) or count <= 0:
            raise _err("invalid allocation count", node.pos)
        total = count * type_size(node.element, self.structs)
        if total > INT_MAX:
            raise _err("invalid allocation: size overflow", node.pos)
        return CPointer(make_block(node.element, count, self.structs), 0,
                        node.element)

    def _free(self, value, pos):
        if not isinstance(value, CPointer):
            raise _err("'free' requires a pointer", pos)
        if value.is_null:
            return                       # free(NULL) is a no-op, as in C
        if value.block.freed:
            raise _err("double free", pos)
        if value.index != 0:
            raise _err("invalid free: pointer is not the start of an allocation", pos)
        value.block.freed = True

    def _call(self, node: Call, env):
        definition = self.functions.get(node.name)
        if definition is None:
            raise _err(f"unknown function '{node.name}'", node.pos)
        values = [self._eval(arg, env) for arg in node.args]   # left-to-right
        if len(values) != len(definition.params):
            raise _err(f"function '{node.name}' takes {len(definition.params)} "
                       f"arguments, got {len(values)}", node.pos)
        local = CEnv(self.global_env)    # top-level functions, no closures
        for (name, ctype), value in zip(definition.params, values):
            local.declare(name, ctype, self._coerce(value, ctype, node.pos), node.pos)
        ctx = _Context(definition.return_type, False)
        try:
            self._exec_stmt(definition.body, local, ctx)
        except ReturnSignal as signal:
            return self._coerce(signal.value, definition.return_type, node.pos)
        if definition.return_type.kind != "void":
            raise _err(f"function '{node.name}' ended without 'give back'", node.pos)
        return None

    def _eval_binary(self, node: Binary, env):
        op = node.op
        if op == "LAND":
            left = self._eval(node.left, env)
            return 1 if (_truthy(left) and _truthy(self._eval(node.right, env))) else 0
        if op == "LOR":
            left = self._eval(node.left, env)
            return 1 if (_truthy(left) or _truthy(self._eval(node.right, env))) else 0

        left = self._eval(node.left, env)
        right = self._eval(node.right, env)
        pos = node.pos

        # pointer arithmetic and comparison (normalize int + pointer once,
        # without re-evaluating either operand)
        if op == "ADD" and _is_int(left) and isinstance(right, CPointer):
            left, right = right, left
        if isinstance(left, CPointer):
            if op in ("ADD", "SUB") and _is_int(right):
                delta = right if op == "ADD" else -right
                if left.is_null:
                    raise _err("invalid pointer arithmetic on null pointer", pos)
                if left.block.freed:
                    raise _err("use after free", pos)
                index = left.index + delta
                if index < 0 or index > len(left.block.cells):
                    raise _err("pointer out of bounds", pos)
                return CPointer(left.block, index, left.pointee)
            if isinstance(right, CPointer):
                if op == "SUB":
                    if left.is_null or right.is_null:
                        raise _err("null pointer subtraction", pos)
                    if left.block is not right.block:
                        raise _err("pointer subtraction of unrelated objects", pos)
                    return left.index - right.index
                return self._compare_pointers(op, left, right, pos)
            if op in ("EQ", "NE"):
                return 1 if ((left.is_null and right == 0) or
                             (not left.is_null and right != 0)) else 0
            raise _err(f"invalid pointer operation '{op}'", pos)
        if _is_int(left) and _is_int(right):
            if op == "ADD":
                return self._checked_int(left + right, pos)
            if op == "SUB":
                return self._checked_int(left - right, pos)
            if op == "MUL":
                return self._checked_int(left * right, pos)
            if op == "DIV":
                return self._idiv(left, right, pos)
            if op == "REM":
                return self._irem(left, right, pos)
            return self._compare(op, left, right, pos)
        if _is_float(left) and _is_float(right):
            if op == "ADD":
                return left + right
            if op == "SUB":
                return left - right
            if op == "MUL":
                return left * right
            if op == "DIV":
                return self._fdiv(left, right)
            return self._compare(op, left, right, pos)
        raise _err(f"operator '{op}' cannot be applied to these values", pos)

    @staticmethod
    def _compare(op, left, right, pos):
        if op == "EQ":
            return 1 if left == right else 0
        if op == "NE":
            return 1 if left != right else 0
        if op == "LT":
            return 1 if left < right else 0
        if op == "LE":
            return 1 if left <= right else 0
        if op == "GT":
            return 1 if left > right else 0
        if op == "GE":
            return 1 if left >= right else 0
        raise _err(f"unknown comparison '{op}'", pos)

    @staticmethod
    def _compare_pointers(op, left: CPointer, right: CPointer, pos):
        ln, rn = left.is_null, right.is_null
        if op in ("EQ", "NE"):
            if ln or rn:
                equal = ln and rn
            else:
                equal = left.block is right.block and left.index == right.index
            return (1 if equal else 0) if op == "EQ" else (0 if equal else 1)
        if ln or rn or left.block is not right.block:
            raise _err("pointer ordering requires pointers into one object", pos)
        a, b = left.index, right.index
        return {
            "LT": 1 if a < b else 0, "LE": 1 if a <= b else 0,
            "GT": 1 if a > b else 0, "GE": 1 if a >= b else 0,
        }[op]

    @staticmethod
    def _render(value) -> str:
        if isinstance(value, CPointer):
            return "null pointer" if value.is_null else "pointer"
        if isinstance(value, bool):
            return "1" if value else "0"
        return str(value)


def run_program(program: Program) -> CInterpreter:
    return CInterpreter().run(program)
