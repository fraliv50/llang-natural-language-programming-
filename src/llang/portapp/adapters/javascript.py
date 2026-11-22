"""JavaScript adapter -- translate a useful subset of JS into canonical llang.

Parsing is done with the real tree-sitter JavaScript grammar; anything the
translator does not understand is reported as an explicit :class:`Gap` (with a
line number and a source snippet) and is also visible as a comment in the
generated llang.  Nothing is silently dropped.

Supported subset
----------------
* ``const`` / ``let`` (and ``var``) declarations with simple identifier targets
* number, string, boolean and ``null`` literals
* arithmetic, comparison and boolean operators (fully parenthesized)
* ``if`` / ``else if`` / ``else``
* ``while`` and the simple (three-part) ``for`` loop
* function declarations with parameters and ``return``
* ``console.log`` mapped to ``show``, and calls to locally declared functions
* array literals and ``xs[i]`` indexing
* ``break`` / ``continue`` as a small bonus

Calls are emitted with llang's labeled argument syntax (the parameter names of
declared functions are used as labels), definitions use single-word names and
every block has an explicit terminator.
"""

from __future__ import annotations

import re

import tree_sitter_javascript
from tree_sitter import Language, Parser

from llang.portapp.models import ConversionResult, Gap
from llang.synonyms import RESERVED

from . import register

_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)?$")

# JS operator token -> canonical llang operator phrase.
BINARY_OPS = {
    "+": "plus",
    "-": "minus",
    "*": "times",
    "/": "divided by",
    "%": "modulo",
    "**": "to the power of",
    ">": "is greater than",
    "<": "is less than",
    ">=": "is at least",
    "<=": "is at most",
    "==": "equals",
    "===": "equals",
    "!=": "does not equal",
    "!==": "does not equal",
    "&&": "and",
    "||": "or",
}

AUGMENTED_OPS = {
    "+=": "plus",
    "-=": "minus",
    "*=": "times",
    "/=": "divided by",
    "%=": "modulo",
    "**=": "to the power of",
}

ESCAPES = {
    "\\n": "\n",
    "\\t": "\t",
    "\\r": "\r",
    "\\b": "\b",
    "\\f": "\f",
    "\\v": "\v",
    "\\0": "\0",
    "\\\\": "\\",
    '\\"': '"',
    "\\'": "'",
    "\\`": "`",
}


def quote(text: str) -> str:
    """Render a Python string as an llang double-quoted string literal."""
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
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


class JavaScriptTranslator:
    """Stateful walker over one tree-sitter parse tree."""

    def __init__(self, source: str):
        self.source = source
        self.source_bytes = source.encode("utf-8")
        self.lines: list[str] = []
        self.pending_comments: list[str] = []
        self.indent = 0
        self.gaps: list[Gap] = []
        self.notes: list[Gap] = []
        self.node_count = 0
        self.names: dict[str, str] = {}
        self.signatures: dict[str, list[str]] = {}

    # --- low-level helpers ------------------------------------------------
    def text(self, node) -> str:
        if node is None:
            return ""
        return self.source_bytes[node.start_byte:node.end_byte].decode(
            "utf-8", "replace")

    def snippet(self, node) -> str:
        if node is None:
            return ""
        text = self.text(node).replace("\r", " ").replace("\n", " ")
        text = re.sub(r"\s+", " ", text).strip()
        return text[:200]

    def line(self, node) -> int | None:
        return node.start_point[0] + 1 if node is not None else None

    def gap(self, node, reason: str, node_type: str | None = None) -> None:
        """Record an unsupported construct without losing sight of it."""
        kind = node_type or (node.type if node is not None else "unknown")
        line = self.line(node)
        snippet = self.snippet(node)
        self.gaps.append(Gap(kind, reason, line, snippet))
        where = f"line {line}" if line else "unknown line"
        self.pending_comments.append(
            f"# GAP ({where}): {kind}: {reason} | {snippet}")

    def note(self, node, reason: str) -> None:
        self.notes.append(Gap(node.type if node else "note", reason,
                              self.line(node), self.snippet(node)))

    def emit(self, text: str) -> None:
        for comment in self.pending_comments:
            self.lines.append("    " * self.indent + comment)
        self.pending_comments.clear()
        self.lines.append("    " * self.indent + text)

    def name_for(self, js_name: str) -> str:
        """Map a JS identifier to a legal, non-reserved, unique llang name."""
        if js_name in self.names:
            return self.names[js_name]
        cleaned = "".join(
            ch if (ch.isalnum() or ch == "_") else "_" for ch in js_name)
        if not cleaned or not (cleaned[0].isalpha() or cleaned[0] == "_"):
            cleaned = "_" + cleaned
        if cleaned in RESERVED:
            cleaned += "_"
        candidate, index = cleaned, 2
        used = set(self.names.values())
        while candidate in used:
            candidate = f"{cleaned}_{index}"
            index += 1
        self.names[js_name] = candidate
        return candidate

    # --- signature pre-pass ----------------------------------------------
    def _walk(self, node):
        yield node
        for child in node.named_children:
            yield from self._walk(child)

    def _param_labels(self, params_node) -> list[str]:
        if params_node is None:
            return []
        labels = []
        for index, param in enumerate(params_node.named_children):
            if param.type == "identifier":
                labels.append(self.name_for(self.text(param)))
            else:
                labels.append(self.name_for(f"arg{index + 1}"))
        return labels

    def collect_signatures(self, root) -> None:
        """Find declared functions first so calls can use the right labels."""
        for node in self._walk(root):
            if node.type != "function_declaration":
                continue
            name_node = node.child_by_field_name("name")
            if name_node is None:
                continue
            self.signatures[self.text(name_node)] = self._param_labels(
                node.child_by_field_name("parameters"))

    # --- literals ---------------------------------------------------------
    def number(self, node) -> str:
        raw = self.text(node).replace("_", "")
        if _NUMBER_RE.match(raw):
            return raw
        self.gap(node, f"numeric literal '{raw}' has no direct llang form")
        try:
            lowered = raw.lower()
            if lowered.startswith("0x"):
                return str(int(lowered, 16))
            if lowered.startswith("0b"):
                return str(int(lowered, 2))
            if lowered.startswith("0o"):
                return str(int(lowered, 8))
            return str(float(raw))
        except (ValueError, OverflowError):
            return "0"

    def escape_value(self, node) -> str:
        raw = self.text(node)
        if raw in ESCAPES:
            return ESCAPES[raw]
        try:
            if raw.startswith("\\x") and len(raw) == 4:
                return chr(int(raw[2:], 16))
            if raw.startswith("\\u") and len(raw) == 6:
                return chr(int(raw[2:], 16))
            if raw.startswith("\\u{") and raw.endswith("}"):
                return chr(int(raw[3:-1], 16))
        except ValueError:
            pass
        self.gap(node, f"string escape '{raw}' has no llang equivalent")
        return raw[1:] if len(raw) > 1 else raw

    def string_parts(self, node) -> str:
        parts = []
        for child in node.named_children:
            if child.type == "string_fragment":
                parts.append(self.text(child))
            elif child.type == "escape_sequence":
                parts.append(self.escape_value(child))
            else:
                self.gap(child, f"string part '{child.type}' is unsupported")
        return "".join(parts)

    # --- expressions ------------------------------------------------------
    def expr(self, node) -> str:
        if node is None:
            return "nothing"
        self.node_count += 1
        kind = node.type

        if kind == "parenthesized_expression":
            inner = node.named_children[0] if node.named_children else None
            return "(" + self.expr(inner) + ")"

        if kind == "identifier":
            name = self.text(node)
            if name in ("undefined", "NaN", "Infinity"):
                self.gap(node, f"constant '{name}' has no llang equivalent")
                return "nothing"
            return self.name_for(name)

        if kind == "number":
            return self.number(node)

        if kind == "string":
            return quote(self.string_parts(node))

        if kind == "template_string":
            substitutions = [c for c in node.named_children
                             if c.type == "template_substitution"]
            if not substitutions:
                return quote(self.string_parts(node))
            self.gap(node, "template literals with interpolation are unsupported")
            for sub in substitutions:
                self.gap(sub, "template interpolation is unsupported")
            return "nothing"

        if kind == "true":
            return "true"
        if kind == "false":
            return "false"
        if kind == "null":
            return "nothing"

        if kind == "binary_expression":
            op_node = node.child_by_field_name("operator")
            op = self.text(op_node)
            left = self.expr(node.child_by_field_name("left"))
            right = self.expr(node.child_by_field_name("right"))
            word = BINARY_OPS.get(op)
            if word is None:
                self.gap(op_node or node, f"operator '{op}' has no llang form")
                return "(nothing)"
            return f"({left} {word} {right})"

        if kind == "unary_expression":
            op_node = node.child_by_field_name("operator")
            op = self.text(op_node)
            argument = self.expr(node.child_by_field_name("argument"))
            if op == "-":
                return f"(0 minus {argument})"
            if op == "+":
                return f"({argument})"
            if op == "!":
                return f"(not {argument})"
            self.gap(op_node or node, f"unary operator '{op}' is unsupported")
            return "(nothing)"

        if kind == "call_expression":
            return self.call(node)

        if kind == "subscript_expression":
            obj = self.expr(node.child_by_field_name("object"))
            index = self.expr(node.child_by_field_name("index"))
            return f"(item {index} of {obj})"

        if kind == "array":
            items = [self.expr(child) for child in node.named_children
                     if child.type != "comment"]
            if not items:
                return "(an empty list)"
            return "(a list of " + ", ".join(items) + ")"

        if kind in ("object", "object_pattern", "array_pattern"):
            self.gap(node, f"{kind} literal has no llang equivalent")
            return "nothing"

        if kind == "arrow_function":
            self.gap(node, "arrow functions are unsupported")
            return "nothing"

        if kind == "function_expression":
            self.gap(node, "function expressions are unsupported")
            return "nothing"

        if kind in ("assignment_expression", "augmented_assignment_expression",
                    "update_expression"):
            self.gap(node, "assignment is a statement in llang, not an expression")
            return "nothing"

        if kind == "new_expression":
            self.gap(node, "object construction is unsupported")
            return "nothing"

        if kind == "conditional_expression":
            self.gap(node, "the ternary operator is unsupported")
            return "nothing"

        if kind in ("await_expression", "yield_expression"):
            self.gap(node, f"'{kind}' is unsupported (async code)")
            return "nothing"

        if kind == "member_expression":
            self.gap(node, "property access is unsupported")
            return "nothing"

        if kind == "spread_element":
            self.gap(node, "spread arguments are unsupported")
            return "nothing"

        self.gap(node, f"expression '{kind}' has no llang translation")
        return "nothing"

    def is_console_log(self, func) -> bool:
        if func is None or func.type != "member_expression":
            return False
        obj = func.child_by_field_name("object")
        prop = func.child_by_field_name("property")
        return (obj is not None and self.text(obj) == "console"
                and prop is not None and self.text(prop) in ("log", "info"))

    def call_args(self, node) -> list[str]:
        args_node = node.child_by_field_name("arguments")
        if args_node is None:
            return []
        return [self.expr(child) for child in args_node.named_children]

    def call(self, node) -> str:
        func = node.child_by_field_name("function")
        args = self.call_args(node)
        if self.is_console_log(func):
            if len(args) > 1:
                self.gap(node, "console.log with several arguments is unsupported")
            self.gap(node, "console.log used as an expression has no llang form")
            return "(nothing)"
        if func is not None and func.type == "identifier":
            name = self.text(func)
            if name in self.signatures:
                labels = self.signatures[name]
                supplied = list(args)
                if len(args) > len(labels):
                    self.gap(node, "too many arguments for declared function")
                if len(args) < len(labels):
                    self.gap(node, "missing arguments for declared function")
                    supplied += ["nothing"] * (len(labels) - len(args))
                rendered = ", ".join(
                    f"{label} = {value}" for label, value in zip(labels, supplied))
                tail = f" with {rendered}" if rendered else ""
                return f"(call {self.name_for(name)}{tail})"
            self.gap(node, f"call to unknown function '{name}' cannot be labeled")
            return "(nothing)"
        self.gap(node, "call target form is unsupported")
        return "(nothing)"

    # --- statements -------------------------------------------------------
    def stmt(self, node) -> None:
        if node is None:
            return
        self.node_count += 1
        kind = node.type

        if kind == "comment":
            self.emit("# " + self.snippet(node))
            return

        if kind in ("lexical_declaration", "variable_declaration"):
            self.declaration(node)
            return

        if kind == "expression_statement":
            self.expression_statement(node)
            return

        if kind == "if_statement":
            self.if_statement(node)
            return

        if kind == "while_statement":
            self.emit("repeat while " + self.expr(
                node.child_by_field_name("condition")))
            self.block(node.child_by_field_name("body"))
            self.emit("end repeat")
            return

        if kind == "for_statement":
            self.for_statement(node)
            return

        if kind == "function_declaration":
            self.function(node)
            return

        if kind == "return_statement":
            value = node.child_by_field_name("value")
            other = [c for c in node.named_children if c.type not in ("return_statement",)]
            value = value or (other[0] if other else None)
            self.emit("give back " + self.expr(value) if value else "give back nothing")
            return

        if kind == "break_statement":
            self.emit("stop the loop")
            return
        if kind == "continue_statement":
            self.emit("skip to the next item")
            return

        if kind == "statement_block":
            self.block(node)
            return

        if kind == "empty_statement":
            return

        if kind == "assignment_expression":
            self.assignment(node, "=")
            return
        if kind == "augmented_assignment_expression":
            op_node = node.child_by_field_name("operator")
            op = self.text(op_node)
            self.assignment(node, AUGMENTED_OPS.get(op, "="))
            if op not in AUGMENTED_OPS:
                self.gap(op_node or node, f"assignment operator '{op}' is unsupported")
            return
        if kind == "update_expression":
            self.update(node)
            return

        if kind == "call_expression":
            self.render_expression(node)
            return

        if kind == "class_declaration":
            self.gap(node, "classes are unsupported")
        elif kind in ("export_statement", "import_statement"):
            self.gap(node, "modules are unsupported")
        elif kind == "for_in_statement":
            self.gap(node, "for-of / for-in loops are unsupported")
        elif kind == "do_statement":
            self.gap(node, "do-while loops are unsupported")
        elif kind == "switch_statement":
            self.gap(node, "switch statements are unsupported")
        elif kind == "try_statement":
            self.gap(node, "try/catch statements are unsupported")
        elif kind == "throw_statement":
            self.gap(node, "throw statements are unsupported")
        else:
            self.gap(node, f"statement '{kind}' is unsupported")
        self.emit("# (untranslated) " + self.snippet(node))

    def block(self, node) -> None:
        if node is None:
            return
        self.indent += 1
        for child in node.named_children:
            self.stmt(child)
        self.indent -= 1

    def declaration(self, node) -> None:
        for child in node.named_children:
            if child.type != "variable_declarator":
                continue
            name_node = child.child_by_field_name("name")
            if name_node is None or name_node.type != "identifier":
                self.gap(name_node or child, "destructuring declarations are unsupported")
                continue
            value_node = child.child_by_field_name("value")
            value = self.expr(value_node) if value_node else "nothing"
            self.emit(f"set {self.name_for(self.text(name_node))} to {value}")

    def assignment(self, node, word: str) -> None:
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        if left is None or left.type != "identifier":
            self.gap(left or node, "assignment target is not a simple name")
            return
        name = self.name_for(self.text(left))
        value = self.expr(right)
        if word == "=":
            self.emit(f"set {name} to {value}")
        else:
            self.emit(f"set {name} to ({name} {word} {value})")

    def update(self, node) -> None:
        argument = node.child_by_field_name("argument")
        operator = node.child_by_field_name("operator")
        op = self.text(operator)
        if argument is None or argument.type != "identifier":
            self.gap(argument or node, "update target is not a simple name")
            return
        name = self.name_for(self.text(argument))
        word = "plus" if op == "++" else "minus"
        if op not in ("++", "--"):
            self.gap(operator or node, f"update operator '{op}' is unsupported")
            return
        self.emit(f"set {name} to ({name} {word} 1)")

    def expression_statement(self, node) -> None:
        inner = None
        for child in node.named_children:
            if child.type != "comment":
                inner = child
                break
        if inner is not None:
            self.render_expression(inner)

    def render_expression(self, inner) -> None:
        """Render an expression that appears in statement position."""
        kind = inner.type

        if kind == "call_expression" and self.is_console_log(
                inner.child_by_field_name("function")):
            args = self.call_args(inner)
            if not args:
                self.emit('show ""')
            else:
                self.emit("show " + args[0])
                for extra in args[1:]:
                    self.gap(extra, "additional console.log argument is unsupported")
            return

        if kind in ("assignment_expression", "augmented_assignment_expression"):
            op_node = inner.child_by_field_name("operator")
            op = self.text(op_node) or "="
            self.assignment(inner, AUGMENTED_OPS.get(op, "=")
                            if op != "=" else "=")
            if op != "=" and op not in AUGMENTED_OPS:
                self.gap(op_node or inner, f"assignment operator '{op}' is unsupported")
            return

        if kind == "update_expression":
            self.update(inner)
            return

        if kind in ("string", "number", "true", "false", "null"):
            # JS directive prologues such as "use strict" are not code.
            self.emit("# directive " + self.snippet(inner))
            return

        if kind == "call_expression":
            rendered = self.call(inner)
            if rendered.startswith("(") and rendered.endswith(")"):
                rendered = rendered[1:-1]
            self.emit(rendered)
            return

        self.gap(inner, f"expression statement '{kind}' is unsupported")
        self.emit("# (untranslated) " + self.snippet(inner))

    def if_statement(self, node, first: bool = True) -> None:
        condition = self.expr(node.child_by_field_name("condition"))
        self.emit(("if " if first else "otherwise if ") + condition + " then")
        self.block(node.child_by_field_name("consequence"))
        alternative = node.child_by_field_name("alternative")
        if alternative is not None:
            inner = next((c for c in alternative.named_children
                          if c.type != "comment"), None)
            if inner is not None and inner.type == "if_statement":
                self.if_statement(inner, first=False)
            elif inner is not None:
                self.emit("otherwise")
                self.block(inner)
        if first:
            self.emit("end if")

    def for_statement(self, node) -> None:
        initializer = node.child_by_field_name("initializer")
        condition = node.child_by_field_name("condition")
        increment = node.child_by_field_name("increment")
        body = node.child_by_field_name("body")

        if initializer is not None and initializer.type != "empty_statement":
            self.stmt(initializer)
        else:
            self.gap(node, "for loop without an initializer")

        if condition is not None and condition.type != "empty_statement":
            condition_text = self.expr(condition)
        else:
            condition_text = "true"
            self.gap(node, "for loop without a condition")

        self.emit("repeat while " + condition_text)
        self.block(body)
        if increment is not None and increment.type != "empty_statement":
            self.indent += 1
            self.stmt(increment)
            self.indent -= 1
        else:
            self.gap(node, "for loop without an increment")
        self.emit("end repeat")

    def function(self, node) -> None:
        if any(self.text(child) == "async" for child in node.children):
            self.gap(node, "async functions are unsupported")
        name_node = node.child_by_field_name("name")
        if name_node is None:
            self.gap(node, "anonymous function declarations are unsupported")
            return
        params_node = node.child_by_field_name("parameters")
        labels = self._param_labels(params_node)
        for param in (params_node.named_children if params_node else []):
            if param.type != "identifier":
                self.gap(param, f"parameter form '{param.type}' is unsupported")
        header = "define function " + self.name_for(self.text(name_node))
        if labels:
            header += " taking " + ", ".join(labels)
        self.emit(header)
        self.block(node.child_by_field_name("body"))
        self.emit("end function")

    # --- public -----------------------------------------------------------
    def convert(self) -> ConversionResult:
        parser = Parser(Language(tree_sitter_javascript.language()))
        root = parser.parse(self.source_bytes).root_node
        self.collect_signatures(root)
        for child in root.named_children:
            self.stmt(child)
        for comment in self.pending_comments:
            self.lines.append(comment)
        self.pending_comments.clear()
        source = "\n".join(self.lines) + ("\n" if self.lines else "")
        return ConversionResult(
            source=source,
            gaps=self.gaps,
            notes=self.notes,
            stats={"nodes": self.node_count},
            source_language="javascript",
        )


class JavaScriptAdapter:
    """Porting adapter for JavaScript / JSX source files."""

    name = "javascript"
    extensions = ("js", "jsx", "mjs", "cjs")

    def convert(self, source: str, path: str) -> ConversionResult:
        return JavaScriptTranslator(source).convert()


register(JavaScriptAdapter())
