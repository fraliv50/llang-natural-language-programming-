"""Canonical AST nodes for the minimal class/record system.

These nodes are defined in their own module (rather than directly in
``ast_nodes.py``) so that the core AST contract — which enumerates the
dataclasses declared in :mod:`llang.ast_nodes` — keeps describing exactly the
core language. They are re-exported from :mod:`llang.ast_nodes` so the rest of
the interpreter has a single import point.

As with every canonical node, ``pos`` is the LAST field.
"""

from dataclasses import dataclass, field

from .errors import SourcePos


@dataclass
class MethodDef:
    """A method definition inside a class body.

    ``params`` always starts with the literal name ``this``; the receiver is
    supplied by ``ask`` as an automatically-bound label, never by the caller.
    """

    name: str = ""
    params: list = field(default_factory=list)
    body: object = None
    pos: SourcePos | None = None


@dataclass
class ClassDef:
    """An executable ``define class`` statement.

    ``fields`` are constructor fields (the ``taking`` list). ``methods`` is a
    list of :class:`MethodDef` in source order. There is one base at most (the
    minimal system omits inheritance, so ``base`` stays ``None`` for now).
    """

    name: str = ""
    fields: list = field(default_factory=list)
    methods: list = field(default_factory=list)
    base: str = ""
    pos: SourcePos | None = None


@dataclass
class MethodCall:
    """An ``ask RECEIVER to METHOD with ...`` expression."""

    receiver: object = None
    method: str = ""
    args: list = field(default_factory=list)  # list of (label, expr)
    pos: SourcePos | None = None
