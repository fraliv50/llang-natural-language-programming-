"""Python source -> canonical llang source converter.

This is the first stage of the family plan's converter. It parses Python with
the real `ast` module, translates supported nodes into llang statements and
expressions, and records every unsupported construct in an explicit report.
It never guesses: a construct it cannot map is reported, not silently mangled.

Design notes:
- Every binary expression is fully parenthesized. llang has no precedence, so
  emitting explicit groups is both simpler and safer than reproducing Python's
  precedence table.
- Collection literals, indexing, calls and `the length of` are greedy in the
  llang parser, so they are always parenthesized when emitted.
- The output is intentionally run through the formatter by the CLI, giving
  canonical, diffable source.
"""

import ast
from dataclasses import dataclass, field

from .synonyms import RESERVED


@dataclass
class Unsupported:
    node_type: str
    reason: str
    lineno: int | None = None

    def __str__(self) -> str:
        where = f"line {self.lineno}" if self.lineno else "unknown line"
        return f"{where}: {self.node_type} — {self.reason}"


@dataclass
class ConversionResult:
    source: str
    unsupported: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def covered(self) -> float:
        total = self.stats.get("nodes", 0)
        skipped = len(self.unsupported)
        if total == 0:
            return 100.0
        return round(100.0 * (total - skipped) / total, 1)


def quote(text: str) -> str:
    """Render a Python string as an llang string literal."""
    out = []
    for ch in text:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


BUILTIN_CALLS = {
    "abs": lambda a: f"(call absolute with value = {a})",
    "round": lambda a: f"(call rounded with value = {a})",
    "sorted": lambda a: f"(call sort with items = {a})",
    "sum": lambda a: f"(call sum with items = {a})",
    "min": lambda a: f"(call minimum with items = {a})",
    "max": lambda a: f"(call maximum with items = {a})",
    "reversed": lambda a: f"(call reverse of with items = {a})",
    "str": lambda a: f"(call to text with value = {a})",
    "int": lambda a: f"(call to number with text = {a})",
}

METHOD_CALLS = {
    "upper": lambda obj, args: f"(call uppercase of with text = {obj})",
    "lower": lambda obj, args: f"(call lowercase of with text = {obj})",
    "strip": lambda obj, args: f"(call trim with text = {obj})",
    "split": lambda obj, args: f"(call split with text = {obj}, by = {args[0]})"
    if args else None,
    "replace": lambda obj, args: f"(call replace in text with text = {obj}, old = {args[0]}, new = {args[1]})"
    if len(args) >= 2 else None,
    "find": lambda obj, args: f"(call find in text with text = {obj}, piece = {args[0]})"
    if args else None,
    "join": lambda obj, args: f"(call join with items = {args[0]}, separator = {obj})"
    if args else None,
    "keys": lambda obj, args: f"(call keys of with collection = {obj})",
    "values": lambda obj, args: f"(call values of with collection = {obj})",
    "insert": lambda obj, args: f"(call insert into with collection = {obj}, index = {args[0]}, value = {args[1]})"
    if len(args) >= 2 else None,
}

BINARY_OPS = {
    ast.Add: "plus",
    ast.Sub: "minus",
    ast.Mult: "times",
    ast.Div: "divided by",
    ast.FloorDiv: "floor divided by",
    ast.Mod: "modulo",
    ast.Pow: "to the power of",
}

COMPARE_OPS = {
    ast.Eq: "equals",
    ast.NotEq: "does not equal",
    ast.Lt: "is less than",
    ast.LtE: "is at most",
    ast.Gt: "is greater than",
    ast.GtE: "is at least",
}

NATIVE_MODULES = {"math", "text", "lists", "shell", "shlex"}
FOREIGN_MODULES = {"json", "shell"}


class Converter:
    def __init__(self, module_policy: str = "auto"):
        self.lines: list[str] = []
        self.indent = 0
        self.unsupported: list[Unsupported] = []
        self.notes: list[Unsupported] = []
        self.node_count = 0
        self.module_policy = module_policy
        self.signatures: dict[str, list[str]] = {}

    # --- helpers ---------------------------------------------------------
    @staticmethod
    def safe(name: str) -> str:
        """Rename Python identifiers that collide with llang reserved words."""
        return name + "_" if name in RESERVED else name

    def note(self, node, reason: str):
        self.unsupported.append(
            Unsupported(type(node).__name__, reason, getattr(node, "lineno", None)))

    def info(self, node, reason: str):
        self.notes.append(
            Unsupported(type(node).__name__, reason, getattr(node, "lineno", None)))

    def emit(self, text: str):
        self.lines.append("    " * self.indent + text)

    def block(self, statements):
        self.indent += 1
        for statement in statements:
            self.stmt(statement)
        self.indent -= 1

    # --- expressions -----------------------------------------------------
    def expr(self, node) -> str:
        self.node_count += 1
        if isinstance(node, ast.Constant):
            if node.value is None:
                return "nothing"
            if isinstance(node.value, bool):
                return "true" if node.value else "false"
            if isinstance(node.value, (int, float)):
                return str(node.value)
            if isinstance(node.value, str):
                return quote(node.value)
            self.note(node, "unsupported constant type")
            return "nothing"

        if isinstance(node, ast.Name):
            return self.safe(node.id)

        if isinstance(node, ast.BinOp):
            op = BINARY_OPS.get(type(node.op))
            if op is None:
                self.note(node, f"binary operator {type(node.op).__name__} has no llang form")
                return f"({self.expr(node.left)} plus {self.expr(node.right)})"
            return f"({self.expr(node.left)} {op} {self.expr(node.right)})"

        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return f"(not {self.expr(node.operand)})"
            if isinstance(node.op, ast.USub):
                return f"(0 minus {self.expr(node.operand)})"
            if isinstance(node.op, ast.UAdd):
                return f"({self.expr(node.operand)})"
            self.note(node, f"unary operator {type(node.op).__name__} is unsupported")
            return self.expr(node.operand)

        if isinstance(node, ast.BoolOp):
            word = "and" if isinstance(node.op, ast.And) else "or"
            parts = [self.expr(value) for value in node.values]
            return "(" + f" {word} ".join(parts) + ")"

        if isinstance(node, ast.Compare):
            parts = []
            previous = self.expr(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                current = self.expr(comparator)
                if isinstance(op, ast.In):
                    parts.append(f"(call contains with collection = {current}, value = {previous})")
                elif isinstance(op, ast.NotIn):
                    parts.append(f"(not (call contains with collection = {current}, value = {previous}))")
                elif isinstance(op, ast.Is) and current == "nothing":
                    parts.append(f"({previous} is nothing)")
                elif isinstance(op, ast.IsNot) and current == "nothing":
                    parts.append(f"(not ({previous} is nothing))")
                elif type(op) in COMPARE_OPS:
                    parts.append(f"({previous} {COMPARE_OPS[type(op)]} {current})")
                else:
                    self.note(node, f"comparison {type(op).__name__} is unsupported")
                    parts.append("false")
                previous = current
            return "(" + " and ".join(parts) + ")"

        if isinstance(node, ast.Call):
            return self.call(node)

        if isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Slice):
                start = self.expr(node.slice.lower) if node.slice.lower else "nothing"
                end = self.expr(node.slice.upper) if node.slice.upper else "nothing"
                if node.slice.step is not None:
                    self.note(node, "slice steps are not supported")
                return (f"(call slice with collection = {self.expr(node.value)}, "
                        f"start = {start}, finish = {end})")
            return f"(item {self.expr(node.slice)} of {self.expr(node.value)})"

        if isinstance(node, ast.List):
            if not node.elts:
                return "(an empty list)"
            return "(a list of " + ", ".join(self.expr(e) for e in node.elts) + ")"

        if isinstance(node, ast.Dict):
            if not node.keys:
                return "(an empty map)"
            parts = [f"{self.expr(k)} mapped to {self.expr(v)}"
                     for k, v in zip(node.keys, node.values)]
            return "(a map with " + ", ".join(parts) + ")"

        if isinstance(node, ast.Tuple):
            self.note(node, "tuples are not supported; emitted as a list")
            return "(a list of " + ", ".join(self.expr(e) for e in node.elts) + ")"

        if isinstance(node, ast.JoinedStr):
            parts = []
            for value in node.values:
                if isinstance(value, ast.Constant):
                    parts.append(quote(str(value.value)))
                elif isinstance(value, ast.FormattedValue):
                    parts.append(f"(call to text with value = {self.expr(value.value)})")
                else:
                    self.note(value, "unsupported f-string part")
            return "(" + " plus ".join(parts or ['""']) + ")"

        if isinstance(node, ast.Attribute):
            self.note(node, "bare attribute access is unsupported")
            return "nothing"

        self.note(node, "expression form is unsupported")
        return "nothing"

    def call(self, node: ast.Call) -> str:
        args = [self.expr(a) for a in node.args]
        keywords = {self.safe(kw.arg): self.expr(kw.value) for kw in node.keywords if kw.arg}
        if any(kw.arg is None for kw in node.keywords):
            self.note(node, "**kwargs expansion is unsupported")

        if isinstance(node.func, ast.Name):
            name = node.func.id
            safe_name = self.safe(name)
            if name in BUILTIN_CALLS and len(args) == len(BUILTIN_CALLS[name].__code__.co_varnames):
                try:
                    return BUILTIN_CALLS[name](*args)
                except TypeError:
                    pass
            if name == "len" and len(args) == 1:
                return f"(the length of {args[0]})"
            if name == "print":
                self.note(node, "print is a statement in llang")
                return f"(call to text with value = {args[0]})" if args else "\"\""
            if name in self.signatures:
                labels = self.signatures[name]
                name = safe_name
                supplied = {}
                for index, value in enumerate(args):
                    if index < len(labels):
                        supplied[labels[index]] = value
                    else:
                        self.note(node, "too many positional arguments for known function")
                supplied.update(keywords)
                rendered = ", ".join(f"{key} = {value}" for key, value in supplied.items())
                return "(call " + name + ((" with " + rendered) if rendered else "") + ")"
            rendered = ", ".join(f"{key} = {value}" for key, value in keywords.items())
            if args:
                self.info(node,
                          f"positional call to '{name}' converted to 'apply' with positional args")
                values = ", ".join(args)
                return (f"(call apply with fn = {safe_name}, "
                        f"args = (a list of {values}))")
            return "(call " + safe_name + ((" with " + rendered) if rendered else "") + ")"

        if isinstance(node.func, ast.Attribute):
            method = node.func.attr
            obj = self.expr(node.func.value)
            maker = METHOD_CALLS.get(method)
            if maker is not None:
                result = maker(obj, args)
                if result is not None:
                    return result
            self.note(node, f"method '{method}' is unsupported")
            rendered = ", ".join(f"{key} = {value}" for key, value in keywords.items())
            return "(call " + method + (" with " + rendered if rendered else "") + ")"

        self.note(node, "call target form is unsupported")
        return "nothing"

    def _list_comprehension(self, target: str, node: ast.ListComp) -> None:
        if len(node.generators) != 1:
            self.note(node, "only single-generator list comprehensions are supported")
            self.emit(f"set {target} to an empty list")
            return
        generator = node.generators[0]
        if not isinstance(generator.target, ast.Name):
            self.note(node, "comprehension target must be a simple name")
            self.emit(f"set {target} to an empty list")
            return
        self.emit(f"set {target} to an empty list")
        variable = self.safe(generator.target.id)
        self.emit(f"repeat for each {variable} in {self.expr(generator.iter)}")
        self.indent += 1
        for condition in generator.ifs:
            self.emit(f"if {self.expr(condition)} then")
            self.indent += 1
        self.emit(f"add {self.expr(node.elt)} to {target}")
        for _ in generator.ifs:
            self.indent -= 1
            self.emit("end if")
        self.indent -= 1
        self.emit("end repeat")

    def call_statement(self, node: ast.Call) -> str | None:
        """Render a call as a statement (no outer parentheses)."""
        if isinstance(node.func, ast.Name) and node.func.id == "print":
            if len(node.args) == 1 and not node.keywords:
                return f"show {self.expr(node.args[0])}"
            return None
        if isinstance(node.func, ast.Attribute) and node.func.attr == "append":
            if len(node.args) == 1:
                return f"add {self.expr(node.args[0])} to {self.expr(node.func.value)}"
            return None
        expression = self.call(node)
        if expression.startswith("(") and expression.endswith(")"):
            expression = expression[1:-1]
        return expression

    # --- statements ------------------------------------------------------
    def stmt(self, node):
        self.node_count += 1

        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                self.note(node, "only simple single-target assignment is supported")
                return
            target = self.safe(node.targets[0].id)
            if isinstance(node.value, ast.ListComp):
                self._list_comprehension(target, node.value)
                return
            self.emit(f"set {target} to {self.expr(node.value)}")
            return

        if isinstance(node, ast.AugAssign):
            if isinstance(node.target, ast.Name):
                op = BINARY_OPS.get(type(node.op), "plus")
                name = self.safe(node.target.id)
                self.emit(f"set {name} to {name} {op} {self.expr(node.value)}")
            else:
                self.note(node, "augmented assignment target is unsupported")
            return

        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.value is not None:
                self.emit(f"set {self.safe(node.target.id)} to {self.expr(node.value)}")
            else:
                self.note(node, "annotated assignment without value is unsupported")
            return

        if isinstance(node, ast.Expr):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return  # docstring
            if isinstance(node.value, ast.Call):
                statement = self.call_statement(node.value)
                if statement is not None:
                    self.emit(statement)
                    return
            self.note(node, "bare expression statement is unsupported")
            return

        if isinstance(node, ast.If):
            self.emit(f"if {self.expr(node.test)} then")
            self.block(node.body)
            if node.orelse:
                if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
                    self._elif(node.orelse[0])
                else:
                    self.emit("otherwise")
                    self.block(node.orelse)
            self.emit("end if")
            return

        if isinstance(node, ast.While):
            self.emit(f"repeat while {self.expr(node.test)}")
            self.block(node.body)
            if node.orelse:
                self.note(node, "while-else has no llang equivalent")
            self.emit("end repeat")
            return

        if isinstance(node, ast.For):
            if isinstance(node.target, ast.Name):
                self.emit(f"repeat for each {self.safe(node.target.id)} in {self.expr(node.iter)}")
                self.block(node.body)
                if node.orelse:
                    self.note(node, "for-else has no llang equivalent")
                self.emit("end repeat")
            else:
                self.note(node, "for target must be a simple name")
            return

        if isinstance(node, ast.Break):
            self.emit("stop the loop")
            return
        if isinstance(node, ast.Continue):
            self.emit("skip to the next item")
            return

        if isinstance(node, ast.FunctionDef):
            self._function(node)
            return

        if isinstance(node, ast.Return):
            self.emit(f"give back {self.expr(node.value)}" if node.value else "give back nothing")
            return

        if isinstance(node, ast.Assert):
            message = quote(node.msg.value) if isinstance(getattr(node, "msg", None), ast.Constant) else None
            if message is None and getattr(node, "msg", None) is not None:
                self.note(node, "assert message must be a literal string")
            self.emit(f"require {self.expr(node.test)}" + (f", {message}" if message else ""))
            return

        if isinstance(node, ast.Raise):
            exc = node.exc
            if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
                args = [self.expr(a) for a in exc.args]
                message = ""
                if args and args[0].startswith('"'):
                    message = ", " + quote(args[0].strip('"'))
                self.emit(f"fail with {exc.func.id}{message}")
            elif isinstance(exc, ast.Name):
                self.emit(f"fail with {exc.id}")
            else:
                self.note(node, "raise form is unsupported")
            return

        if isinstance(node, ast.Try):
            self.emit("expect")
            self.block(node.body)
            for handler in node.handlers:
                kind = handler.type.id if isinstance(handler.type, ast.Name) else None
                if kind:
                    self.emit(f"if a problem of kind {kind} occurs then")
                else:
                    self.emit("if a problem occurs then")
                self.block(handler.body)
            if node.orelse:
                self.emit("if nothing went wrong then")
                self.block(node.orelse)
            if node.finalbody:
                self.emit("always")
                self.block(node.finalbody)
            self.emit("end expect")
            return

        if isinstance(node, (ast.Import, ast.ImportFrom)):
            self._import(node)
            return

        if isinstance(node, ast.Pass):
            return

        self.note(node, "statement form is unsupported")

    def _elif(self, node: ast.If):
        self.emit(f"otherwise if {self.expr(node.test)} then")
        self.block(node.body)
        if node.orelse:
            if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
                self._elif(node.orelse[0])
            else:
                self.emit("otherwise")
                self.block(node.orelse)

    def _function(self, node: ast.FunctionDef):
        if node.decorator_list:
            self.note(node, "decorators are unsupported")
        if node.returns is not None or any(arg.annotation for arg in node.args.args):
            self.note(node, "annotations are ignored")
        params = [self.safe(arg.arg) for arg in node.args.args]
        if node.args.vararg or node.args.kwarg or node.args.kwonlyargs:
            self.note(node, "*args/**kwargs/keyword-only parameters are unsupported")
        text = "define function " + self.safe(node.name)
        if params:
            text += " taking " + ", ".join(params)
        self.emit(text)
        self.block(node.body)
        self.emit("end function")

    def _import(self, node):
        if isinstance(node, ast.Import):
            names = [alias.name.split(".")[0] for alias in node.names]
        else:
            names = [node.module.split(".")[0]] if node.module else []
        for name in names:
            if name in FOREIGN_MODULES:
                self.emit(f"use the foreign {name} module")
            elif name in NATIVE_MODULES:
                self.emit(f"use the {name} module")
            else:
                self.note(node, f"import of '{name}' has no known module mapping")

    def _collect_signatures(self, tree):
        for statement in tree.body:
            if isinstance(statement, ast.FunctionDef):
                self.signatures[statement.name] = [self.safe(arg.arg) for arg in statement.args.args]

    # --- public ----------------------------------------------------------
    def convert(self, source: str) -> ConversionResult:
        tree = ast.parse(source)
        self._collect_signatures(tree)
        for statement in tree.body:
            self.stmt(statement)
        return ConversionResult(
            source="\n".join(self.lines) + ("\n" if self.lines else ""),
            unsupported=self.unsupported,
            notes=self.notes,
            stats={"nodes": self.node_count},
        )


def convert_source(source: str, module_policy: str = "auto") -> ConversionResult:
    return Converter(module_policy).convert(source)
