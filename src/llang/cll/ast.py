"""AST value objects for the c-ll v1 surface.

These nodes are deliberately *separate* from ``llang.ast_nodes``: c-ll carries
static types, lvalues, and addresses, while the English surface remains
byte-for-byte unchanged.  ``pos`` is always the last field so constructors read
naturally: ``Node(payload, ..., pos=source_position)``.

``SourcePos``/``LangError`` are imported from the shared error module so every
surface emits the same diagnosed message shape (``docs/REFERENCE.md`` §7).
"""

from dataclasses import dataclass, field
from typing import Optional

from ..errors import SourcePos


# ---------------------------------------------------------------------------
# Types (value objects, never executed)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CType:
    """A c-ll type.

    kind is one of ``int``, ``float``, ``void``, ``pointer``, ``array``,
    ``struct`` or the show-only ``text``.  Pointers carry ``pointee``, arrays
    carry ``element`` and ``length``, structs carry ``name``.
    """

    kind: str
    pointee: Optional["CType"] = None
    element: Optional["CType"] = None
    length: Optional[int] = None
    name: str = ""

    def __str__(self) -> str:
        if self.kind == "pointer":
            return f"pointer to {self.pointee}"
        if self.kind == "array":
            return f"array[{self.length}] of {self.element}"
        if self.kind == "struct":
            return f"struct {self.name}"
        return self.kind

    @property
    def is_pointer(self) -> bool:
        return self.kind == "pointer"

    @property
    def is_scalar(self) -> bool:
        return self.kind in ("int", "float", "pointer")


INT = CType("int")
FLOAT = CType("float")
VOID = CType("void")
TEXT = CType("text")          # output-only: produced by string literals for `show`
NULL_TYPE = CType("pointer")  # the untyped type of `null pointer`


def pointer_to(pointee: CType) -> CType:
    return CType("pointer", pointee=pointee)


def array_of(element: CType, length: int) -> CType:
    return CType("array", element=element, length=length)


def struct_type(name: str) -> CType:
    return CType("struct", name=name)


# Backwards-friendly alias used by the design document.
Type = CType


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

@dataclass
class Program:
    statements: list = field(default_factory=list)
    tier: int = 3
    pos: Optional[SourcePos] = None


@dataclass
class Block:
    statements: list = field(default_factory=list)
    pos: Optional[SourcePos] = None


@dataclass
class Literal:
    value: object = None
    ctype: Optional[CType] = None
    pos: Optional[SourcePos] = None


@dataclass
class Null:
    """The ``null pointer`` literal (convertible to any pointer type)."""

    pos: Optional[SourcePos] = None


@dataclass
class Variable:
    name: str = ""
    pos: Optional[SourcePos] = None


@dataclass
class Unary:
    """Only ``LNOT`` is a prefix unary op; address/deref have their own nodes."""

    op: str = ""
    operand: object = None
    pos: Optional[SourcePos] = None


@dataclass
class Binary:
    """One precedence level, left-to-right.

    op is one of ADD, SUB, MUL, DIV, REM, EQ, NE, LT, LE, GT, GE, LAND, LOR.
    DIV becomes IDIV or FDIV according to operand types.
    """

    op: str = ""
    left: object = None
    right: object = None
    pos: Optional[SourcePos] = None


@dataclass
class Cast:
    expr: object = None
    target: Optional[CType] = None
    pos: Optional[SourcePos] = None


@dataclass
class AddressOf:
    expr: object = None
    pos: Optional[SourcePos] = None


@dataclass
class Deref:
    """``value at EXPR`` — an lvalue."""

    expr: object = None
    pos: Optional[SourcePos] = None


@dataclass
class Index:
    """``item INDEX of EXPR`` — an lvalue over an array or pointer."""

    base: object = None
    index: object = None
    pos: Optional[SourcePos] = None


@dataclass
class MemberAccess:
    """``member F of EXPR`` (value) or ``member F via EXPR`` (pointer)."""

    base: object = None
    field: str = ""
    via_pointer: bool = False
    pos: Optional[SourcePos] = None


@dataclass
class SizeOf:
    target: Optional[CType] = None
    pos: Optional[SourcePos] = None


@dataclass
class Alloc:
    """``call allocate with type = T, count = N``."""

    element: Optional[CType] = None
    count: object = None
    pos: Optional[SourcePos] = None


@dataclass
class Free:
    """``call free with pointer = P``."""

    expr: object = None
    pos: Optional[SourcePos] = None


@dataclass
class Call:
    """Positional call; args is a list of expressions (no labels)."""

    name: str = ""
    args: list = field(default_factory=list)
    pos: Optional[SourcePos] = None


@dataclass
class TypedDecl:
    """``let NAME as TYPE be EXPR`` — the initializer is mandatory."""

    name: str = ""
    ctype: Optional[CType] = None
    init: object = None
    pos: Optional[SourcePos] = None


@dataclass
class Set:
    """``set LVALUE to EXPR`` — LVALUE is an lvalue node, not a name."""

    target: object = None
    expr: object = None
    pos: Optional[SourcePos] = None


@dataclass
class Show:
    exprs: list = field(default_factory=list)
    pos: Optional[SourcePos] = None


@dataclass
class StructDef:
    name: str = ""
    fields: list = field(default_factory=list)  # list of (name, CType)
    pos: Optional[SourcePos] = None


@dataclass
class FunctionDef:
    name: str = ""
    return_type: Optional[CType] = None
    params: list = field(default_factory=list)  # list of (name, CType)
    body: Optional[Block] = None
    pos: Optional[SourcePos] = None


@dataclass
class Return:
    expr: object = None
    pos: Optional[SourcePos] = None


@dataclass
class If:
    branches: list = field(default_factory=list)  # list of (cond, Block)
    otherwise: Optional[Block] = None
    pos: Optional[SourcePos] = None


@dataclass
class RepeatWhile:
    cond: object = None
    body: Optional[Block] = None
    pos: Optional[SourcePos] = None


@dataclass
class CountedLoop:
    name: str = ""
    start: object = None
    limit: object = None
    step: object = None
    body: Optional[Block] = None
    pos: Optional[SourcePos] = None


@dataclass
class Break:
    pos: Optional[SourcePos] = None


@dataclass
class Continue:
    pos: Optional[SourcePos] = None


__all__ = [
    "CType", "Type", "INT", "FLOAT", "VOID", "TEXT", "NULL_TYPE",
    "pointer_to", "array_of", "struct_type",
    "Program", "Block", "Literal", "Null", "Variable", "Unary", "Binary",
    "Cast", "AddressOf", "Deref", "Index", "MemberAccess", "SizeOf",
    "Alloc", "Free", "Call", "TypedDecl", "Set", "Show", "StructDef",
    "FunctionDef", "Return", "If", "RepeatWhile", "CountedLoop", "Break",
    "Continue",
]
