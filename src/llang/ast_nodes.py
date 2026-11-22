"""Canonical AST.

The interpreter only ever sees these nodes. Every surface synonym has already
been normalized to exactly one of them by the parser.

`pos` is deliberately the LAST field of every node so constructor calls read
naturally: Node(payload, ..., pos=source_position).
"""

from dataclasses import dataclass, field

from .errors import SourcePos


@dataclass
class Program:
    statements: list = field(default_factory=list)
    pos: SourcePos | None = None


@dataclass
class Block:
    statements: list = field(default_factory=list)
    pos: SourcePos | None = None


@dataclass
class Literal:
    value: object = None
    pos: SourcePos | None = None


@dataclass
class Variable:
    name: str = ""
    pos: SourcePos | None = None


@dataclass
class Unary:
    op: str = ""
    operand: object = None
    pos: SourcePos | None = None


@dataclass
class Binary:
    op: str = ""
    left: object = None
    right: object = None
    pos: SourcePos | None = None


@dataclass
class Call:
    name: str = ""
    args: list = field(default_factory=list)  # list of (label: str, expr: node)
    pos: SourcePos | None = None


@dataclass
class Set:
    name: str = ""
    expr: object = None
    pos: SourcePos | None = None


@dataclass
class Show:
    expr: object = None
    pos: SourcePos | None = None


@dataclass
class Require:
    cond: object = None
    message: str | None = None
    pos: SourcePos | None = None


@dataclass
class If:
    branches: list = field(default_factory=list)  # list of (cond, Block)
    otherwise: object = None
    pos: SourcePos | None = None


@dataclass
class RepeatWhile:
    cond: object = None
    body: object = None
    pos: SourcePos | None = None


@dataclass
class FunctionDef:
    name: str = ""
    aliases: list = field(default_factory=list)
    params: list = field(default_factory=list)
    body: object = None
    pos: SourcePos | None = None


@dataclass
class Return:
    expr: object = None
    pos: SourcePos | None = None


@dataclass
class ListLiteral:
    elements: list = field(default_factory=list)
    pos: SourcePos | None = None


@dataclass
class MapLiteral:
    entries: list = field(default_factory=list)  # list of (key_expr, value_expr)
    pos: SourcePos | None = None


@dataclass
class Index:
    collection: object = None
    key: object = None
    pos: SourcePos | None = None


@dataclass
class Length:
    collection: object = None
    pos: SourcePos | None = None


@dataclass
class AddTo:
    value: object = None
    target: object = None
    pos: SourcePos | None = None


@dataclass
class SetItem:
    target: object = None
    key: object = None
    value: object = None
    pos: SourcePos | None = None


@dataclass
class ForEach:
    name: str = ""
    iterable: object = None
    body: object = None
    pos: SourcePos | None = None


@dataclass
class Break:
    pos: SourcePos | None = None


@dataclass
class Continue:
    pos: SourcePos | None = None


@dataclass
class Fail:
    kind: str = ""
    message: str | None = None
    pos: SourcePos | None = None


@dataclass
class Expect:
    body: object = None
    handlers: list = field(default_factory=list)  # list of (kind, Block)
    else_body: object = None
    always_body: object = None
    pos: SourcePos | None = None


@dataclass
class Use:
    name: str = ""
    foreign: bool = False
    alias: str = ""
    pos: SourcePos | None = None


# --- class / record system ------------------------------------------------
# These dataclasses live in ``class_nodes`` so the core AST contract keeps
# enumerating only the core language. They are re-exported here so every tool
# imports all canonical nodes from a single module.
from .class_nodes import ClassDef, MethodDef, MethodCall  # noqa: E402,F401
