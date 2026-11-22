"""C source -> canonical English llang adapter (powered by ``pycparser``).

The adapter deliberately targets a small, well understood subset of C:
signed/unsigned integer and floating point variables, arithmetic and
comparisons, ``if``/``else``, ``while``, counted ``for`` loops, functions with
parameters and return values, one-dimensional arrays, and simple ``printf``
calls used as output.

Everything else becomes an explicit :class:`~llang.portapp.models.Gap` with a
line number and a source snippet.  Generated llang is always canonical English
llang: single-word function names, labeled calls, explicit block closers and
parentheses around every compound expression (llang has no operator
precedence).  Unsupported statements are left as comments so that no source is
silently lost, while the gap record carries the exact reason.
"""

import ast
import re

from pycparser import c_ast, c_parser
from pycparser.c_generator import CGenerator

from llang.portapp.models import ConversionResult, Gap
from llang.synonyms import RESERVED

from . import register


# pycparser has no preprocessor.  These typedefs are prepended *without* a
# trailing newline so that source line numbers are unchanged; the fake nodes
# they create are skipped when walking the parsed translation unit.
_FAKE_TYPE_NAMES = (
    "int8_t", "uint8_t", "int16_t", "uint16_t", "int32_t", "uint32_t",
    "int64_t", "uint64_t", "int_least8_t", "uint_least8_t", "intptr_t",
    "uintptr_t", "size_t", "ssize_t", "ptrdiff_t", "wchar_t",
    "bool", "FILE", "va_list",
)
FAKE_TYPEDEFS = " ".join(f"typedef int {name};" for name in _FAKE_TYPE_NAMES)

BINARY_OPS = {
    "+": "plus",
    "-": "minus",
    "*": "times",
    "%": "modulo",
}
COMPARE_OPS = {
    "==": "equals",
    "!=": "does not equal",
    "<": "is less than",
    "<=": "is at most",
    ">": "is greater than",
    ">=": "is at least",
}
LOGIC_OPS = {"&&": "and", "||": "or"}
COMPOUND_ASSIGN = {"+=": "plus", "-=": "minus", "*=": "times",
                   "/=": "divided by", "%=": "modulo"}
INCREMENT_OPS = {"++": 1, "--": -1, "p++": 1, "p--": -1,
                 "postinc": 1, "postdec": -1}
FORMAT_SPEC = re.compile(r"%[-+ #0]*\d*(?:\.\d+)?[diouxXeEfFgG]")
PARSE_POSITION = re.compile(r":(\d+):(\d+)")


def line_of(node):
    """1-based source line of a pycparser node, when available."""
    coord = getattr(node, "coord", None)
    line = getattr(coord, "line", None)
    if isinstance(line, int):
        return line
    match = PARSE_POSITION.search(str(coord or ""))
    return int(match.group(1)) if match else None


def quote(text):
    """Render text as an llang string literal."""
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


def strip_comments(line, in_block):
    """Remove C comments from one line, preserving its length and strings."""
    out = []
    quote_char = None
    index = 0
    while index < len(line):
        ch = line[index]
        following = line[index + 1] if index + 1 < len(line) else ""
        if in_block:
            if ch == "*" and following == "/":
                in_block = False
                index += 2
            else:
                out.append(" ")
                index += 1
            continue
        if quote_char:
            out.append(ch)
            if ch == "\\" and following:
                out.append(following)
                index += 2
                continue
            if ch == quote_char:
                quote_char = None
            index += 1
            continue
        if ch in ('"', "'"):
            quote_char = ch
            out.append(ch)
            index += 1
            continue
        if ch == "/" and following == "/":
            break
        if ch == "/" and following == "*":
            in_block = True
            out.append("  ")
            index += 2
            continue
        out.append(ch)
        index += 1
    return "".join(out), in_block


def clean_source(source):
    """Blank comments and preprocessor lines, keeping line numbers intact.

    Returns ``(cleaned_source, directives)`` where ``directives`` is a list of
    ``(line_number, text)`` pairs.  Directives are never fed to pycparser, but
    they are reported as gaps/notes by the adapter.
    """
    in_block = False
    uncommented = []
    for line in source.splitlines():
        cleaned, in_block = strip_comments(line, in_block)
        uncommented.append(cleaned)

    cleaned_lines = []
    directives = []
    index = 0
    while index < len(uncommented):
        line = uncommented[index]
        if line.lstrip().startswith("#"):
            start = index + 1
            text = line.strip()
            while line.rstrip().endswith("\\") and index + 1 < len(uncommented):
                index += 1
                line = uncommented[index]
                text += " " + line.strip()
            directives.append((start, text))
            cleaned_lines.extend([""] * (index + 2 - start))
        else:
            cleaned_lines.append(line)
        index += 1
    return "\n".join(cleaned_lines) + "\n", directives


class CAdapter:
    name = "c"
    extensions = ("c", "h")

    def __init__(self):
        self.source_lines = []
        self.lines = []
        self.indent = 0
        self.gaps = []
        self.notes = []
        self.node_count = 0
        self.signatures = {}
        self.returns = {}
        self.types = {}
        self.used_names = set()
        self.div_name = ""
        self.mod_name = ""
        self.use_div = False
        self.use_mod = False
        self.loop_depth = 0
        self.generator = CGenerator()

    # --- common helpers --------------------------------------------------
    @staticmethod
    def safe(name):
        """Rename identifiers colliding with llang reserved words."""
        return name + "_" if name in RESERVED else name

    def emit(self, text):
        self.lines.append("    " * self.indent + text)

    def comment(self, text):
        one_line = " ".join(str(text).split())
        self.emit("# " + one_line[:300])

    def snippet(self, line, node=None):
        if isinstance(line, int) and 1 <= line <= len(self.source_lines):
            text = self.source_lines[line - 1].strip()
            if text:
                return text[:200]
        if node is not None:
            try:
                return self.generator.visit(node).strip()[:200]
            except Exception:
                return type(node).__name__
        return ""

    def record(self, target, node, reason, kind=None, line=None, snippet=None):
        where = line_of(node) if line is None else line
        text = snippet if snippet is not None else self.snippet(where, node)
        resolved = kind or (type(node).__name__ if node is not None else "CConstruct")
        target.append(Gap(resolved, reason, where, text))

    def gap(self, node, reason, kind=None, line=None, snippet=None):
        self.record(self.gaps, node, reason, kind, line, snippet)

    def note(self, node, reason, kind=None, line=None, snippet=None):
        self.record(self.notes, node, reason, kind, line, snippet)

    def unique(self, base):
        candidate = base
        suffix = 2
        while candidate in self.used_names:
            candidate = f"{base}_{suffix}"
            suffix += 1
        self.used_names.add(candidate)
        return candidate

    # --- light type inference -------------------------------------------
    @classmethod
    def base_kind(cls, type_node):
        if isinstance(type_node, c_ast.ArrayDecl):
            return "array"
        if isinstance(type_node, c_ast.PtrDecl):
            return "pointer"
        if isinstance(type_node, c_ast.FuncDecl):
            return "function"
        inner = type_node.type if isinstance(type_node, c_ast.TypeDecl) else type_node
        if isinstance(inner, c_ast.IdentifierType):
            if "float" in inner.names or "double" in inner.names:
                return "float"
            if "void" in inner.names:
                return "void"
            return "int"
        return "unknown"

    @classmethod
    def element_kind(cls, type_node):
        inner = type_node
        while isinstance(inner, c_ast.ArrayDecl):
            inner = inner.type
        return cls.base_kind(inner)

    def expr_kind(self, node):
        if isinstance(node, c_ast.Constant):
            if node.type in ("float", "double", "long double") or any(
                    ch in str(node.value) for ch in ".eE"):
                return "float"
            return "int"
        if isinstance(node, c_ast.ID):
            return self.types.get(node.name, "unknown")
        if isinstance(node, c_ast.BinaryOp):
            if node.op in COMPARE_OPS or node.op in LOGIC_OPS:
                return "int"
            left = self.expr_kind(node.left)
            right = self.expr_kind(node.right)
            return "float" if "float" in (left, right) else "int"
        if isinstance(node, c_ast.UnaryOp):
            return "int" if node.op == "!" else self.expr_kind(node.expr)
        if isinstance(node, c_ast.ArrayRef):
            return self.element_kind(node.name.type) if isinstance(
                getattr(node.name, "type", None), c_ast.ArrayDecl) else "unknown"
        if isinstance(node, c_ast.FuncCall) and isinstance(node.name, c_ast.ID):
            return self.returns.get(node.name.name, "unknown")
        if isinstance(node, c_ast.Cast):
            return self.base_kind(node.to_type.type)
        return "unknown"

    def _collect(self, ext):
        """Collect function signatures and global variable types up front."""
        for node in ext:
            if isinstance(node, c_ast.FuncDef):
                decl = node.decl
                if not decl.name:
                    continue
                func_type = decl.type
                params = []
                if func_type.args:
                    for param in func_type.args.params:
                        if param.name and self.base_kind(param.type) != "void":
                            params.append(param.name)
                            self.types[param.name] = self.base_kind(param.type)
                self.signatures[decl.name] = params
                self.returns[decl.name] = self.base_kind(func_type.type)
                self.types[decl.name] = "function"
                self.used_names.add(self.safe(decl.name))
                for param in params:
                    self.used_names.add(self.safe(param))
            elif isinstance(node, c_ast.Decl) and node.name:
                self.types[node.name] = self.base_kind(node.type)
                self.used_names.add(self.safe(node.name))

    # --- expressions -----------------------------------------------------
    def expr(self, node):
        self.node_count += 1
        if node is None:
            return "nothing"

        if isinstance(node, c_ast.Constant):
            value = str(node.value)
            if node.type == "string":
                self.gap(node, "string literals have no general llang form")
                return '""'
            if node.type in ("float", "double", "long double"):
                try:
                    return str(float(value))
                except ValueError:
                    pass
            elif node.type != "char":  # int, unsigned, long, suffixes ...
                match = re.match(r"^[+-]?(?:0[xX][0-9a-fA-F]+|[0-9]+)", value)
                if match:
                    digits = match.group(0)
                    try:
                        return str(int(digits, 0))
                    except ValueError:
                        try:  # C octal spelling, e.g. 010
                            return str(int(digits, 8))
                        except ValueError:
                            pass
            self.gap(node, f"literal '{value}' has no llang form")
            return "0"

        if isinstance(node, c_ast.ID):
            name = self.safe(node.name)
            if (self.types.get(node.name) in ("unknown", "function")
                    and node.name not in self.signatures
                    and node.name not in self.types):
                self.gap(node, f"identifier '{node.name}' is not declared in the mapped subset")
            return name

        if isinstance(node, c_ast.BinaryOp):
            left = self.expr(node.left)
            right = self.expr(node.right)
            kind = self.expr_kind(node)
            if node.op in COMPARE_OPS:
                return f"({left} {COMPARE_OPS[node.op]} {right})"
            if node.op in LOGIC_OPS:
                return f"({left} {LOGIC_OPS[node.op]} {right})"
            if node.op == "/" and kind == "float":
                return f"({left} divided by {right})"
            if node.op == "/" and self.returns.get(self.div_name, None) is not None:
                self.use_div = True
                return f"(call {self.div_name} with a = {left}, b = {right})"
            if node.op == "%" and kind == "float":
                return f"({left} modulo {right})"
            if node.op == "%":
                self.use_div = True
                self.use_mod = True
                return f"(call {self.mod_name} with a = {left}, b = {right})"
            word = BINARY_OPS.get(node.op)
            if word is None:
                self.gap(node, f"binary operator '{node.op}' has no llang equivalent")
                return "nothing"
            return f"({left} {word} {right})"

        if isinstance(node, c_ast.UnaryOp):
            operand = self.expr(node.expr)
            if node.op == "+":
                return f"({operand})"
            if node.op == "-":
                return f"(0 minus {operand})"
            if node.op == "!":
                return f"(not {operand})"
            if node.op in INCREMENT_OPS:
                self.gap(node, f"in-expression '{node.op}' changes a value; llang has no expression assignment")
                return operand
            self.gap(node, f"unary operator '{node.op}' has no llang equivalent")
            return "nothing"

        if isinstance(node, c_ast.ArrayRef):
            index = self.expr(node.subscript)
            target = self.expr(node.name)
            self.note(node, "C array indexed as an llang list (bounds are not checked)",
                      kind="ArrayIndex")
            return f"(item {index} of {target})"

        if isinstance(node, c_ast.FuncCall):
            return self.call_expr(node)

        if isinstance(node, c_ast.Cast):
            self.gap(node, "C casts have no exact llang equivalent (no truncation/coercion builtin)")
            return self.expr(node.expr)

        if isinstance(node, c_ast.TernaryOp):
            self.gap(node, "conditional operator ?: has no llang expression form")
            self.expr(node.cond)
            self.expr(node.iftrue)
            self.expr(node.iffalse)
            return "nothing"

        if isinstance(node, c_ast.StructRef):
            self.gap(node, "struct/union member access is unsupported")
            return "nothing"

        if isinstance(node, c_ast.InitList):
            self.gap(node, "initializer list is only supported in array declarations")
            for item in node.exprs or []:
                self.expr(item)
            return "nothing"

        self.gap(node, f"{type(node).__name__} expression is unsupported")
        for _, child in node.children():
            if isinstance(child, c_ast.Node):
                self.expr(child)
        return "nothing"

    def labelled_args(self, node, name):
        """Render positional C arguments as llang labeled arguments."""
        params = self.signatures.get(name)
        args = list(node.args.exprs) if node.args else []
        rendered = []
        if params is None:
            self.gap(node, f"call to unknown function '{name}' cannot be mapped to a labeled llang call")
            for arg in args:
                self.expr(arg)
            return None
        if len(args) > len(params):
            self.gap(node, f"too many arguments for function '{name}' ({len(args)} > {len(params)})")
        for index, arg in enumerate(args):
            value = self.expr(arg)
            if index < len(params):
                rendered.append(f"{self.safe(params[index])} = {value}")
        if len(args) < len(params):
            self.gap(node, f"missing arguments for function '{name}': "
                           + ", ".join(params[len(args):]))
        return ", ".join(rendered)

    def call_expr(self, node):
        if isinstance(node.name, c_ast.ID):
            name = node.name.name
        else:
            self.gap(node, "indirect calls (function pointers) are unsupported")
            return "nothing"
        if name in ("printf", "scanf", "puts", "malloc", "free"):
            self.gap(node, f"library call '{name}' is not supported in expression position")
            return "nothing"
        label = self.labelled_args(node, name)
        if label is None:
            return "nothing"
        call = "call " + self.safe(name)
        return f"({call} with {label})" if label else f"({call})"

    # --- statements ------------------------------------------------------
    def stmt(self, node):
        self.node_count += 1
        if node is None:
            return

        if isinstance(node, c_ast.Compound):
            for item in node.block_items or []:
                self.stmt(item)
            return

        if isinstance(node, c_ast.DeclList):
            for declaration in node.decls or []:
                self.stmt(declaration)
            return

        if isinstance(node, c_ast.EmptyStatement):
            return

        if isinstance(node, c_ast.Decl):
            self.declaration(node)
            return

        if isinstance(node, c_ast.Assignment):
            self.assignment(node)
            return

        if isinstance(node, c_ast.UnaryOp) and node.op in INCREMENT_OPS:
            if isinstance(node.expr, c_ast.ID):
                target = self.safe(node.expr.name)
                step = INCREMENT_OPS[node.op]
                word = "plus" if step > 0 else "minus"
                self.note(node, f"'{node.op}' expanded to an explicit set statement",
                          kind="Increment")
                self.emit(f"set {target} to ({target} {word} 1)")
            else:
                self.gap(node, f"'{node.op}' on a non-name target is unsupported")
                self.comment(f"unsupported: {node.op} on {self.snippet(line_of(node), node)}")
            return

        if isinstance(node, c_ast.If):
            self.if_chain(node)
            return

        if isinstance(node, c_ast.While):
            self.emit(f"repeat while {self.expr(node.cond)}")
            self.indent += 1
            self.loop_depth += 1
            self.stmt(node.stmt)
            self.loop_depth -= 1
            self.indent -= 1
            self.emit("end repeat")
            return

        if isinstance(node, c_ast.For):
            self.for_loop(node)
            return

        if isinstance(node, c_ast.DoWhile):
            self.gap(node, "do/while loops have no llang equivalent")
            self.comment(f"unsupported do/while: {self.snippet(line_of(node), node)}")
            return

        if isinstance(node, c_ast.Return):
            if node.expr is None:
                self.emit("give back nothing")
            else:
                self.emit(f"give back {self.expr(node.expr)}")
            return

        if isinstance(node, c_ast.FuncCall):
            self.call_statement(node)
            return

        if isinstance(node, c_ast.Break):
            if not self.loop_depth:
                self.gap(node, "'break' outside a loop is unsupported")
            self.emit("stop the loop")
            return

        if isinstance(node, c_ast.Continue):
            if not self.loop_depth:
                self.gap(node, "'continue' outside a loop is unsupported")
            elif getattr(self, "in_for_loop", False):
                self.gap(node, "'continue' in a for loop would skip the C increment expression")
                self.comment("unsupported: continue in a for loop")
                return
            self.emit("skip to the next item")
            return

        if isinstance(node, c_ast.Switch) or isinstance(node, (c_ast.Case, c_ast.Default)):
            self.gap(node, "switch/case has no llang equivalent")
            self.comment(f"unsupported switch/case: {self.snippet(line_of(node), node)}")
            if isinstance(node, c_ast.Switch):
                self.stmt(node.stmt)
            return

        if isinstance(node, (c_ast.Goto, c_ast.Label)):
            self.gap(node, "goto/labels have no llang equivalent")
            self.comment(f"unsupported goto/label: {self.snippet(line_of(node), node)}")
            return

        if isinstance(node, c_ast.FuncDef):
            self.gap(node, "nested function definitions are unsupported")
            self.comment(f"unsupported nested function: {self.snippet(line_of(node), node)}")
            return

        self.gap(node, f"{type(node).__name__} statement is unsupported")
        self.comment(f"unsupported statement: {self.snippet(line_of(node), node)}")

    def declaration(self, node):
        kind = self.base_kind(node.type)
        if isinstance(node.type, c_ast.PtrDecl):
            self.gap(node, "pointer declarations are unsupported (no addresses in llang)",
                     kind="Pointer")
            self.comment(f"unsupported pointer declaration: {self.snippet(line_of(node), node)}")
            return
        if isinstance(node.type, (c_ast.Struct, c_ast.Union, c_ast.Enum)) or kind == "pointer":
            self.gap(node, f"{type(node.type).__name__} declarations are unsupported",
                     kind=type(node.type).__name__)
            self.comment(f"unsupported declaration: {self.snippet(line_of(node), node)}")
            return
        if kind == "function":
            self.note(node, "function prototype ignored; the definition supplies the signature",
                      kind="Prototype")
            return
        if isinstance(node.type, c_ast.FuncDecl):
            self.note(node, "function prototype ignored; the definition supplies the signature",
                      kind="Prototype")
            return

        name = self.safe(node.name)
        self.used_names.add(name)
        if isinstance(node.type, c_ast.ArrayDecl):
            self.array_declaration(node, name)
            return

        self.types[node.name] = kind
        inner = node.type.type if isinstance(node.type, c_ast.TypeDecl) else None
        if isinstance(inner, (c_ast.Struct, c_ast.Union, c_ast.Enum)):
            self.gap(node, f"{type(inner).__name__} variable declarations are unsupported",
                     kind=type(inner).__name__)
            self.comment(f"unsupported declaration: {self.snippet(line_of(node), node)}")
            return
        if kind in ("unknown", "void"):
            self.gap(node, f"variable type '{kind}' is unsupported")
            self.comment(f"unsupported declaration: {self.snippet(line_of(node), node)}")
            return
        # Detect unsigned through the underlying IdentifierType names.
        if isinstance(inner, c_ast.IdentifierType) and "unsigned" in inner.names:
            self.note(node, "unsigned integer mapped to an llang number; modular range is not preserved",
                      kind="Unsigned")
        if node.init is None:
            default = "0.0" if kind == "float" else "0"
            self.note(node, "uninitialized C scalar given a zero default (llang has no uninitialized values)",
                      kind="DefaultValue")
            self.emit(f"set {name} to {default}")
        else:
            self.emit(f"set {name} to {self.expr(node.init)}")

    def array_declaration(self, node, name):
        array_type = node.type
        self.types[node.name] = "array"
        element = self.element_kind(array_type)
        inner = array_type.type
        if element == "pointer":
            self.gap(node, "arrays of pointers are unsupported")
            self.comment(f"unsupported array: {self.snippet(line_of(node), node)}")
            self.emit(f"set {name} to (an empty list)")
            return
        if isinstance(inner, c_ast.ArrayDecl):
            self.gap(node, "multi-dimensional arrays are unsupported")
            self.comment(f"unsupported array: {self.snippet(line_of(node), node)}")
            self.emit(f"set {name} to (an empty list)")
            return

        dimension = None
        if isinstance(array_type.dim, c_ast.Constant):
            try:
                dimension = int(str(array_type.dim.value), 0)
            except ValueError:
                dimension = None
        elif array_type.dim is not None:
            self.gap(array_type.dim, "only constant array sizes are supported")
        if dimension is not None and dimension < 0:
            self.gap(node, "negative array size is invalid")
            dimension = 0
        if dimension is None and array_type.dim is not None:
            self.gap(node, "non-constant array size is unsupported (no VLAs)")
            dimension = 0

        values = []
        if isinstance(node.init, c_ast.InitList):
            values = [self.expr(item) for item in (node.init.exprs or [])]
            if dimension is None:
                dimension = len(values)
            if len(values) > dimension:
                self.gap(node.init, f"initializer has {len(values)} values for an array of {dimension}")
                values = values[:dimension]
        elif node.init is not None:
            self.gap(node.init, f"array initializer {type(node.init).__name__} is unsupported")
            if dimension is None:
                dimension = 0

        if dimension is None:
            dimension = 0
        if dimension:
            default = "0.0" if element == "float" else "0"
            values.extend([default] * (dimension - len(values)))
            self.emit(f"set {name} to (a list of {', '.join(values)})")
        else:
            self.emit(f"set {name} to (an empty list)")
        if node.init is not None:
            self.note(node, "C array mapped to an llang list (fixed size is not enforced)",
                      kind="Array")

    def assignment(self, node):
        if node.op not in ("=", *COMPOUND_ASSIGN):
            self.gap(node, f"assignment operator '{node.op}' is unsupported")
            self.comment(f"unsupported assignment: {self.snippet(line_of(node), node)}")
            return
        target = node.lvalue
        if isinstance(target, c_ast.ID):
            name = self.safe(target.name)
            value = self.expr(node.rvalue)
            if node.op != "=":
                value = f"({name} {COMPOUND_ASSIGN[node.op]} {value})"
                self.note(node, f"compound assignment '{node.op}' expanded to an explicit set",
                          kind="CompoundAssignment")
            self.emit(f"set {name} to {value}")
            return
        if isinstance(target, c_ast.ArrayRef):
            index = self.expr(target.subscript)
            collection = self.expr(target.name)
            value = self.expr(node.rvalue)
            if node.op != "=":
                old = f"(item {index} of {collection})"
                value = f"({old} {COMPOUND_ASSIGN[node.op]} {value})"
            self.emit(f"set item {index} of {collection} to {value}")
            self.note(node, "array element assignment mapped to an llang list item write",
                      kind="ArrayWrite")
            return
        self.gap(node, f"assignment target {type(target).__name__} is unsupported "
                       "(pointers and struct members are not addressable in llang)")
        self.comment(f"unsupported assignment: {self.snippet(line_of(node), node)}")

    def if_chain(self, node):
        self.emit(f"if {self.expr(node.cond)} then")
        self.indent += 1
        self.stmt(node.iftrue)
        self.indent -= 1
        alternative = node.iffalse
        while alternative is not None:
            if isinstance(alternative, c_ast.If):
                self.emit(f"otherwise if {self.expr(alternative.cond)} then")
                self.indent += 1
                self.stmt(alternative.iftrue)
                self.indent -= 1
                alternative = alternative.iffalse
                continue
            self.emit("otherwise")
            self.indent += 1
            self.stmt(alternative)
            self.indent -= 1
            alternative = None
        self.emit("end if")

    def for_loop(self, node):
        self.emit("# counted C for loop")
        if node.init is not None:
            self.stmt(node.init)
        condition = self.expr(node.cond) if node.cond is not None else "true"
        self.emit(f"repeat while {condition}")
        self.indent += 1
        self.loop_depth += 1
        previous = getattr(self, "in_for_loop", False)
        self.in_for_loop = True
        self.stmt(node.stmt)
        self.in_for_loop = previous
        if node.next is not None:
            self.stmt(node.next)
        self.loop_depth -= 1
        self.indent -= 1
        self.emit("end repeat")
        self.note(node, "C for loop lowered to a while loop with the increment at the end of the body",
                  kind="ForLowering")

    def printf_statement(self, node):
        args = list(node.args.exprs) if node.args else []
        if not args or not isinstance(args[0], c_ast.Constant) or args[0].type != "string":
            self.gap(node, "printf requires a literal format string")
            self.comment(f"unsupported printf: {self.snippet(line_of(node), node)}")
            return
        try:
            fmt = ast.literal_eval(str(args[0].value))
        except (ValueError, SyntaxError):
            self.gap(node, "printf format string could not be decoded")
            self.comment(f"unsupported printf: {self.snippet(line_of(node), node)}")
            return
        # A literal '%%' is not a conversion; protect it from the spec regex.
        fmt = fmt.replace("%%", "\x01")
        specs = list(FORMAT_SPEC.finditer(fmt))
        value_args = args[1:]
        if len(value_args) > len(specs):
            self.gap(node, "printf has more arguments than conversions")
        if len(value_args) < len(specs):
            self.gap(node, "printf conversion has no argument")
            self.comment(f"unsupported printf: {self.snippet(line_of(node), node)}")
            return
        if not specs:
            self.emit(f"show {quote(fmt.replace(chr(1), '%'))}")
        else:
            parts = []
            position = 0
            for spec, value in zip(specs, value_args):
                literal = fmt[position:spec.start()].replace(chr(1), "%")
                if literal:
                    parts.append(quote(literal))
                parts.append(f"(call to text with value = {self.expr(value)})")
                position = spec.end()
            tail = fmt[position:].replace("\n", "").replace("\r", "").replace(chr(1), "%")
            if tail:
                parts.append(quote(tail))
            self.emit("show " + (parts[0] if len(parts) == 1
                                 else "(" + " plus ".join(parts) + ")"))
        if "%f" in fmt or "%F" in fmt:
            self.note(node, "printf %f uses C six-decimal rendering; llang renders floats natively",
                      kind="PrintfFormat")
        self.note(node, "simple printf mapped to the llang show statement", kind="Printf")

    def call_statement(self, node):
        if isinstance(node.name, c_ast.ID) and node.name.name == "printf":
            self.printf_statement(node)
            return
        if isinstance(node.name, c_ast.ID):
            name = node.name.name
            if name in ("scanf", "malloc", "free", "puts"):
                self.gap(node, f"library call '{name}' is unsupported")
                self.comment(f"unsupported call: {self.snippet(line_of(node), node)}")
                return
            label = self.labelled_args(node, name)
            if label is not None:
                self.emit("call " + self.safe(name)
                          + (f" with {label}" if label else ""))
                return
        else:
            self.gap(node, "indirect calls (function pointers) are unsupported")
        self.comment(f"unsupported call: {self.snippet(line_of(node), node)}")

    def function(self, node):
        decl = node.decl
        name = decl.name
        safe_name = self.safe(name)
        func_type = decl.type
        params = self.signatures.get(name, [])
        header = "define function " + safe_name
        if params:
            header += " taking " + ", ".join(self.safe(param) for param in params)
        self.emit(header)
        saved_types = dict(self.types)
        if func_type.args:
            for param in func_type.args.params:
                if param.name:
                    self.types[param.name] = self.base_kind(param.type)
                    if self.types[param.name] == "pointer":
                        self.gap(param, "pointer parameters are unsupported (llang has no addresses)",
                                 kind="PointerParameter")
        self.indent += 1
        self.stmt(node.body)
        self.indent -= 1
        self.emit("end function")
        self.types = saved_types

    def helper_definitions(self):
        helpers = []
        if self.use_div:
            helpers.extend([
                f"define function {self.div_name} taking a, b",
                "    set q to (a floor divided by b)",
                "    if ((a is less than 0) does not equal (b is less than 0)) "
                "and ((a modulo b) does not equal 0) then",
                "        give back (q plus 1)",
                "    end if",
                "    give back q",
                "end function",
            ])
        if self.use_mod:
            helpers.extend([
                f"define function {self.mod_name} taking a, b",
                f"    set q to (call {self.div_name} with a = a, b = b)",
                "    give back (a minus (q times b))",
                "end function",
            ])
        return helpers

    # --- public API ------------------------------------------------------
    def convert(self, source, path="<source>"):
        source = source.replace("\ufeff", "", 1)
        self.source_lines = source.splitlines()
        self.lines = []
        self.indent = 0
        self.gaps = []
        self.notes = []
        self.node_count = 0
        self.signatures = {}
        self.returns = {}
        self.types = {}
        self.used_names = set()
        self.use_div = False
        self.use_mod = False
        self.loop_depth = 0
        self.in_for_loop = False

        cleaned, directives = clean_source(source)
        self.div_name = self.unique("cport_div_int")
        self.mod_name = self.unique("cport_mod_int")
        self.signatures[self.div_name] = ["a", "b"]
        self.returns[self.div_name] = "int"
        self.signatures[self.mod_name] = ["a", "b"]
        self.returns[self.mod_name] = "int"

        for line, text in directives:
            self.node_count += 1
            kind = text.split(None, 1)[0] if text else "#"
            if kind in ("#include", "#import"):
                self.note(None, "preprocessor include ignored; llang has no headers",
                          kind="PreprocessorInclude", line=line, snippet=text)
            else:
                self.gap(None, f"preprocessor directive '{kind}' has no llang equivalent",
                         kind="PreprocessorDirective", line=line, snippet=text)

        try:
            tree = c_parser.CParser().parse(FAKE_TYPEDEFS + cleaned)
        except Exception as exc:
            line_match = PARSE_POSITION.search(str(exc))
            line = int(line_match.group(1)) if line_match else None
            self.node_count += 1
            self.gap(None, f"C source could not be parsed: {exc}",
                     kind="ParseError", line=line,
                     snippet=self.snippet(line) if line else source[:200])
            return ConversionResult(
                source="# C source could not be parsed; see gaps for details.\n",
                gaps=self.gaps, notes=self.notes,
                stats={"nodes": self.node_count}, source_language=self.name,
            )

        top_level = list(tree.children())
        # Skip the fake typedef nodes introduced to satisfy pycparser.
        real = [child for _, child in top_level[len(_FAKE_TYPE_NAMES):]]
        self._collect(real)

        for node in real:
            if isinstance(node, c_ast.FuncDef):
                self.function(node)
            elif isinstance(node, c_ast.Decl):
                self.stmt(node)
            elif isinstance(node, (c_ast.Struct, c_ast.Union, c_ast.Enum)):
                self.gap(node, f"{type(node).__name__} definition is unsupported")
                self.comment(f"unsupported type definition: {self.snippet(line_of(node), node)}")
            elif isinstance(node, c_ast.Typedef):
                self.gap(node, "user typedefs are unsupported")
                self.comment(f"unsupported typedef: {self.snippet(line_of(node), node)}")
            else:
                self.gap(node, f"{type(node).__name__} top-level construct is unsupported")
                self.comment(f"unsupported declaration: {self.snippet(line_of(node), node)}")

        if "main" in self.signatures:
            if self.signatures["main"]:
                self.gap(None, "main with argc/argv parameters is unsupported",
                         kind="MainSignature", line=self.main_line(real),
                         snippet=self.snippet(self.main_line(real)))
            else:
                self.note(None, "C entry point 'main' invoked at the end of the llang program",
                          kind="EntryPoint", line=self.main_line(real))
                self.lines.append("call main")

        source_lines = self.helper_definitions() + self.lines
        return ConversionResult(
            source="\n".join(source_lines) + ("\n" if source_lines else ""),
            gaps=self.gaps, notes=self.notes,
            stats={"nodes": self.node_count}, source_language=self.name,
        )

    @staticmethod
    def main_line(real_nodes):
        for node in real_nodes:
            if isinstance(node, c_ast.FuncDef) and node.decl.name == "main":
                return line_of(node)
        return None


register(CAdapter())
