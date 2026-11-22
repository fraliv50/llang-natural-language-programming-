"""Canonical source formatter.

Renders a canonical AST back into canonical llang source. Every surface synonym
is emitted using exactly one spelling, so formatting the same program twice (or
formatting two synonym-equivalent programs) always yields byte-identical text.

Indentation is decorative: four spaces per nesting level. The parser ignores it,
but it makes the output readable. Parentheses are inserted only where needed to
preserve llang's flat, left-associative expression semantics on a reparse.
"""

from .ast_nodes import (
    Program, Block, Literal, Variable, Unary, Binary, Call,
    Set, Show, Require, If, RepeatWhile, FunctionDef, Return,
    ListLiteral, MapLiteral, Index, Length, AddTo, SetItem,
    ForEach, Break, Continue, Fail, Expect, Use,
    ClassDef, MethodDef, MethodCall,
)
from .lexer import Lexer
from .parser import Parser


# One canonical phrase per operator code. These are exactly the phrases from
# docs/GRAMMAR.md that the parser maps back to the same operator code.
_OPERATOR_PHRASES = {
    "ADD": "plus",
    "SUB": "minus",
    "MUL": "times",
    "DIV": "divided by",
    "FLOORDIV": "floor divided by",
    "MOD": "modulo",
    "POW": "to the power of",
    "GT": "is greater than",
    "LT": "is less than",
    "GE": "is at least",
    "LE": "is at most",
    "EQ": "equals",
    "NE": "does not equal",
    "AND": "and",
    "OR": "or",
}

_POSTFIX_PREDICATES = {
    "IS_NOT_EMPTY": "is not empty",
    "IS_NOTHING": "is nothing",
    "IS_EMPTY": "is empty",
    "IS_NUMBER": "is a number",
    "IS_TEXT": "is text",
    "IS_LIST": "is a list",
    "IS_MAP": "is a map",
}

_INDENT = "    "


# --- public API ---------------------------------------------------------
def format_program(program) -> str:
    """Render a canonical ``Program`` as canonical llang source."""
    lines = _statements(program.statements, 0)
    return "\n".join(lines) + ("\n" if lines else "")


def format_source(source: str) -> str:
    """Tokenize + parse + format source text in one step."""
    program = Parser(Lexer(source).tokenize()).parse_program()
    return format_program(program)


# --- helpers ------------------------------------------------------------
def _line(text: str, level: int) -> str:
    return _INDENT * level + text


def _block_lines(body, level: int) -> list:
    """Flatten a body (Block, Program, list of statements, or single node)."""
    if body is None:
        return []
    if isinstance(body, (Block, Program)):
        statements = body.statements
    elif isinstance(body, list):
        statements = body
    else:
        statements = [body]
    return _statements(statements, level)


def _statements(statements, level: int) -> list:
    lines = []
    for statement in statements:
        lines.extend(_statement(statement, level))
    return lines


def _string(value: str) -> str:
    """Quote a string so the lexer reproduces it exactly."""
    escaped = []
    for ch in value:
        if ch == "\\":
            escaped.append("\\\\")
        elif ch == '"':
            escaped.append('\\"')
        elif ch == "\n":
            escaped.append("\\n")
        elif ch == "\t":
            escaped.append("\\t")
        else:
            escaped.append(ch)
    return '"' + "".join(escaped) + '"'


def _literal(value) -> str:
    if value is None:
        return "nothing"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, int):
        # llang has no unary minus: spell negatives as an explicit subtraction.
        return str(value) if value >= 0 else f"(0 minus {-value})"
    if isinstance(value, float):
        # llang has no exponent literals and no unary minus. Expand any
        # scientific notation to plain decimal and keep the value a float.
        if value != value:                      # nan
            return '(call to number with text = "nan")'
        if value in (float("inf"), float("-inf")):
            word = "inf" if value > 0 else "-inf"
            return f'(call to number with text = "{word}")'
        text = repr(value)
        if "e" in text or "E" in text:
            from decimal import Decimal
            text = format(Decimal(text), "f")
        if "." not in text:
            text += ".0"
        if text.startswith("-"):
            text = f"(0 minus {text[1:]})"
        return text
    return _string(str(value))


def _is_greedy(node) -> bool:
    """True when the node's parser consumes sub-expressions with ``parse_expr``.

    Such a node will swallow any following operator, postfix predicate, or
    comma that belongs to the enclosing construct, so it must be parenthesized
    when used as a sub-part of a larger expression.
    """
    if isinstance(node, (ListLiteral, MapLiteral, Index, Length, MethodCall)):
        return True
    if isinstance(node, Call):
        return True
    return False


def _sub(node, *, binary_left: bool = False, postfix_operand: bool = False) -> str:
    """Format a child expression that is parsed by ``_parse_unary``.

    ``binary_left`` marks the left operand of a Binary: a nested Binary is safe
    there (the chain is left-associative). ``postfix_operand`` marks the operand
    of a postfix predicate: a nested ``not`` must be parenthesized there because
    ``not`` would otherwise capture the predicate.
    """
    text = _expr(node, nested=True)
    needs_parens = isinstance(node, Binary) and not binary_left
    if postfix_operand and isinstance(node, Unary) and node.op == "NOT":
        needs_parens = True
    return f"({text})" if needs_parens else text


# --- expressions --------------------------------------------------------
def _expr(node, *, nested: bool = False) -> str:
    """Format an expression.

    ``nested`` is true when the expression is a component of a larger construct
    (an argument, list element, operand, ...). A "greedy" node -- one whose
    parser consumes sub-expressions with ``parse_expr`` -- must then be wrapped
    in parentheses, otherwise it would swallow a following operator or comma
    that belongs to the enclosing construct.
    """
    greedy = _is_greedy(node)
    wrap = nested and greedy

    if isinstance(node, Literal):
        return _literal(node.value)

    if isinstance(node, Variable):
        return node.name

    if isinstance(node, Unary):
        if node.op == "NOT":
            return "not " + _sub(node.operand)
        return (
            _sub(node.operand, postfix_operand=True)
            + " "
            + _POSTFIX_PREDICATES[node.op]
        )

    if isinstance(node, Binary):
        left = _sub(node.left, binary_left=True)
        right = _sub(node.right)
        return f"{left} {_OPERATOR_PHRASES[node.op]} {right}"

    if isinstance(node, Call):
        text = "call " + node.name
        if node.args:
            args = ", ".join(
                f"{label} = {_expr(value, nested=True)}" for label, value in node.args
            )
            text += " with " + args
        return f"({text})" if wrap else text

    if isinstance(node, MethodCall):
        text = "ask " + _expr(node.receiver, nested=True) + " to " + node.method
        if node.args:
            text += " with " + ", ".join(
                f"{label} = {_expr(value, nested=True)}"
                for label, value in node.args
            )
        return f"({text})" if wrap else text

    if isinstance(node, ListLiteral):
        if not node.elements:
            return "an empty list"
        text = "a list of " + ", ".join(
            _expr(element, nested=True) for element in node.elements
        )
        return f"({text})" if wrap else text

    if isinstance(node, MapLiteral):
        if not node.entries:
            return "an empty map"
        text = "a map with " + ", ".join(
            f"{_expr(key, nested=True)} mapped to {_expr(value, nested=True)}"
            for key, value in node.entries
        )
        return f"({text})" if wrap else text

    if isinstance(node, Index):
        key = _expr(node.key, nested=True)
        collection = _expr(node.collection, nested=True)
        text = f"item {key} of {collection}"
        return f"({text})" if wrap else text

    if isinstance(node, Length):
        text = f"the length of {_expr(node.collection, nested=True)}"
        return f"({text})" if wrap else text

    # Statement nodes have no expression form; fail loudly on a malformed AST.
    raise TypeError(f"Cannot format a {type(node).__name__} as an expression")


# --- statements ---------------------------------------------------------
def _statement(node, level: int) -> list:
    # Containers may appear wherever a statement is allowed.
    if isinstance(node, (Program, Block)):
        return _statements(node.statements, level)

    if isinstance(node, Set):
        return [_line(f"set {node.name} to {_expr(node.expr)}", level)]

    if isinstance(node, Show):
        return [_line(f"show {_expr(node.expr)}", level)]

    if isinstance(node, Require):
        text = f"require {_expr(node.cond, nested=True)}"
        if node.message is not None:
            text += f", {_string(node.message)}"
        return [_line(text, level)]

    if isinstance(node, If):
        lines = []
        for index, (cond, body) in enumerate(node.branches):
            keyword = "if" if index == 0 else "otherwise if"
            lines.append(_line(f"{keyword} {_expr(cond, nested=True)} then", level))
            lines.extend(_block_lines(body, level + 1))
        if node.otherwise is not None:
            lines.append(_line("otherwise", level))
            lines.extend(_block_lines(node.otherwise, level + 1))
        lines.append(_line("end if", level))
        return lines

    if isinstance(node, RepeatWhile):
        lines = [_line(f"repeat while {_expr(node.cond, nested=True)}", level)]
        lines.extend(_block_lines(node.body, level + 1))
        lines.append(_line("end repeat", level))
        return lines

    if isinstance(node, ForEach):
        lines = [
            _line(
                f"repeat for each {node.name} in {_expr(node.iterable, nested=True)}",
                level,
            )
        ]
        lines.extend(_block_lines(node.body, level + 1))
        lines.append(_line("end repeat", level))
        return lines

    if isinstance(node, MethodDef):
        text = (f"define method {node.name} taking "
                + ", ".join(node.params))
        lines = [_line(text, level)]
        lines.extend(_block_lines(node.body, level + 1))
        lines.append(_line("end method", level))
        return lines

    if isinstance(node, ClassDef):
        text = f"define class {node.name}"
        if node.fields:
            text += " taking " + ", ".join(node.fields)
        lines = [_line(text, level)]
        for method in node.methods:
            lines.extend(_statement(method, level + 1))
        lines.append(_line("end class", level))
        return lines

    if isinstance(node, FunctionDef):
        text = f"define function {node.name}"
        if node.params:
            text += " taking " + ", ".join(node.params)
        lines = [_line(text, level)]
        if node.aliases:
            lines.append(_line("also known as " + ", ".join(node.aliases), level))
        lines.extend(_block_lines(node.body, level + 1))
        lines.append(_line("end function", level))
        return lines

    if isinstance(node, Return):
        return [_line(f"return {_expr(node.expr)}", level)]

    if isinstance(node, Call):
        return [_line(_expr(node), level)]

    if isinstance(node, MethodCall):
        return [_line(_expr(node), level)]

    if isinstance(node, AddTo):
        text = (
            f"add {_expr(node.value, nested=True)} "
            f"to {_expr(node.target, nested=True)}"
        )
        return [_line(text, level)]

    if isinstance(node, SetItem):
        text = (
            f"set item {_expr(node.key, nested=True)} "
            f"of {_expr(node.target, nested=True)} "
            f"to {_expr(node.value, nested=True)}"
        )
        return [_line(text, level)]

    if isinstance(node, Break):
        return [_line("stop the loop", level)]

    if isinstance(node, Continue):
        return [_line("skip to the next item", level)]

    if isinstance(node, Fail):
        text = f"fail with {node.kind}"
        if node.message is not None:
            text += f", {_string(node.message)}"
        return [_line(text, level)]

    if isinstance(node, Expect):
        lines = [_line("expect", level)]
        lines.extend(_block_lines(node.body, level + 1))
        for kind, body in node.handlers:
            lines.append(_line(f"if a problem of kind {kind} occurs then", level))
            lines.extend(_block_lines(body, level + 1))
        if node.else_body is not None:
            lines.append(_line("if nothing went wrong then", level))
            lines.extend(_block_lines(node.else_body, level + 1))
        if node.always_body is not None:
            lines.append(_line("always", level))
            lines.extend(_block_lines(node.always_body, level + 1))
        lines.append(_line("end expect", level))
        return lines

    if isinstance(node, Use):
        text = "use the "
        if node.foreign:
            text += "foreign "
        text += f"{node.name} module"
        if node.alias and node.alias != node.name:
            text += f" as {node.alias}"
        return [_line(text, level)]

    raise TypeError(f"Cannot format a {type(node).__name__} as a statement")
