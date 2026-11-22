"""Static lint pass over the canonical AST.

The interpreter stays dynamic; this module only *reports* suspicious
constructs. It never changes execution. Two passes are used:

1. A collection pass hoists every function name/alias and every global
   binding. This is what keeps forward references from becoming false
   positives (a function may be called before its definition appears).
2. A walking pass checks uses in source order, within the scopes the
   interpreter actually creates (global, plus one scope per function).
   ``if``/loop/expect blocks share their enclosing scope, exactly as the
   interpreter's single ``Env`` per function does.
"""

from dataclasses import dataclass, fields

from .ast_nodes import (
    Program, Block, Literal, Variable, Unary, Binary, Call, Set, Show, Require,
    If, RepeatWhile, FunctionDef, Return, ListLiteral, MapLiteral, Index, Length,
    AddTo, SetItem, ForEach, Break, Continue, Fail, Expect, Use,
    ClassDef, MethodDef, MethodCall,
)
from .errors import SourcePos
from .interpreter import BUILTINS
from .foreign import FOREIGN_CONSTANTS, FOREIGN_FUNCTIONS
from pathlib import Path
from .lexer import Lexer
from .parser import Parser


@dataclass
class Diagnostic:
    """A single lint finding.

    ``severity`` is either ``"error"`` or ``"warning"``; ``pos`` is carried
    straight from the originating AST node so callers can localize it.
    """

    severity: str
    message: str
    pos: SourcePos | None = None

    def __str__(self) -> str:
        where = f" at {self.pos}" if self.pos is not None else ""
        return f"{self.severity}: {self.message}{where}"


_NODE_TYPES = (
    Program, Block, Literal, Variable, Unary, Binary, Call, Set, Show, Require,
    If, RepeatWhile, FunctionDef, Return, ListLiteral, MapLiteral, Index, Length,
    AddTo, SetItem, ForEach, Break, Continue, Fail, Expect, Use,
    ClassDef, MethodDef, MethodCall,
)

_TERMINATORS = {
    Return: "give back",
    Fail: "fail",
    Break: "stop the loop",
    Continue: "skip to the next item",
}


def _child_nodes(value):
    """Yield AST nodes found in a field value (recursing through lists/tuples).

    Call arguments, ``if`` branches, map entries and expect handlers are all
    tuples/lists that mix plain strings with nodes; the strings are simply
    ignored because they are not AST node instances.
    """
    if isinstance(value, _NODE_TYPES):
        return [value]
    if isinstance(value, (list, tuple)):
        result = []
        for item in value:
            result.extend(_child_nodes(item))
        return result
    return []


def _node_children(node):
    result = []
    for field in fields(node):
        result.extend(_child_nodes(getattr(node, field.name, None)))
    return result


def _pos(node):
    return getattr(node, "pos", None)


class _Scope:
    """A lexical scope with the names bound so far (source order)."""

    def __init__(self, parent=None):
        self.parent = parent
        self.defined = set()


class _Linter:
    def __init__(self, program):
        self.program = program
        self.diagnostics = []
        self.builtins = set(BUILTINS)

        # Filled by the collection pass.
        self.function_names = set()   # every function name and alias
        self.global_vars = set()      # every global assignment / loop variable
        self.module_aliases = {}      # alias -> set of exports
        self.class_names = set()      # every class name
        self.class_info = {}          # class -> (fields, method names)
        self.instance_classes = {}    # variable -> class (best effort)

        self._collect(program, in_function=False)

        qualified = {
            f"{export} from {alias}"
            for alias, exports in self.module_aliases.items()
            for export in exports
        }
        self.known_callables = (self.builtins | self.function_names | qualified
                                | {f"new {name}" for name in self.class_names})
        self.all_global_names = (
            self.builtins | self.function_names | self.global_vars
            | set(self.module_aliases) | self.class_names
        )

    # --- helpers --------------------------------------------------------
    def _add(self, severity, message, pos=None):
        self.diagnostics.append(Diagnostic(severity, message, pos))

    def _module_exports(self, node):
        if node.foreign:
            return (set(FOREIGN_FUNCTIONS.get(node.name, {}))
                    | set(FOREIGN_CONSTANTS.get(node.name, {})))
        candidates = [Path("lib") / f"{node.name}.ll", Path(f"{node.name}.ll")]
        path = next((item for item in candidates if item.is_file()), None)
        if path is None:
            self._add("error", f"Cannot find module '{node.name}'", node.pos)
            return set()
        source = path.read_text(encoding="utf-8-sig")
        module = Parser(Lexer(source).tokenize()).parse_program()
        exports = set()
        for statement in module.statements:
            if isinstance(statement, FunctionDef):
                exports.add(statement.name)
                exports.update(statement.aliases)
            elif isinstance(statement, Set):
                exports.add(statement.name)
        return exports

    def _register_use(self, node):
        alias = node.alias or node.name
        if alias in self.module_aliases:
            return
        self.module_aliases[alias] = self._module_exports(node)

    # --- pass 1: hoist names --------------------------------------------
    def _collect(self, node, in_function):
        if isinstance(node, Use):
            self._register_use(node)
            return

        if isinstance(node, ClassDef):
            if node.name in self.class_names:
                self._add("error",
                          f"Class '{node.name}' is defined more than once",
                          node.pos)
            else:
                self.class_names.add(node.name)
            self.class_info[node.name] = (
                list(node.fields),
                {method.name for method in node.methods},
            )
            for method in node.methods:
                self._collect(method, True)
            return

        if isinstance(node, MethodDef):
            for child in _node_children(node):
                self._collect(child, True)
            return

        if isinstance(node, FunctionDef):
            for name in [node.name] + list(node.aliases):
                if name in self.function_names:
                    self._add("error",
                              f"Function '{name}' is defined more than once",
                              node.pos)
                else:
                    self.function_names.add(name)
            for child in _node_children(node):
                self._collect(child, True)
            return

        if isinstance(node, (Set, ForEach)) and not in_function:
            self.global_vars.add(node.name)

        for child in _node_children(node):
            self._collect(child, in_function)

    # --- pass 2: walking ------------------------------------------------
    def run(self):
        global_scope = _Scope()
        global_scope.defined.update(self.builtins)
        global_scope.defined.update(self.function_names)
        global_scope.defined.update(self.module_aliases)
        self._walk(self.program, global_scope, in_function=False)
        return self.diagnostics

    def _walk_statements(self, statements, scope, in_function):
        terminator = None
        for statement in statements:
            if terminator is not None:
                self._add("warning",
                          f"Unreachable code after '{terminator}'",
                          _pos(statement))
            self._walk(statement, scope, in_function)
            for kind, word in _TERMINATORS.items():
                if isinstance(statement, kind):
                    terminator = word
                    break

    def _walk(self, node, scope, in_function):
        if node is None:
            return

        if isinstance(node, (Program, Block)):
            self._walk_statements(node.statements, scope, in_function)
            return

        if isinstance(node, ClassDef):
            scope.defined.add(node.name)
            for method in node.methods:
                self._walk_method_def(method, scope, node.name)
            return

        if isinstance(node, MethodDef):
            self._walk_method_def(node, scope, None)
            return

        if isinstance(node, MethodCall):
            self._walk_method_call(node, scope, in_function)
            return

        if isinstance(node, Index):
            self._walk(node.collection, scope, in_function)
            self._walk(node.key, scope, in_function)
            if (isinstance(node.collection, Variable)
                    and isinstance(node.key, Literal)
                    and isinstance(node.key.value, str)):
                class_name = self.instance_classes.get(node.collection.name)
                info = self.class_info.get(class_name)
                if info is not None and node.key.value not in info[0]:
                    self._add("warning",
                              f"Class '{class_name}' has no field '{node.key.value}'",
                              node.pos)
            return

        if isinstance(node, Variable):
            if not self._is_known(node.name, scope, in_function):
                self._add("error", f"Undefined name '{node.name}'", node.pos)
            return

        if isinstance(node, Literal):
            return

        if isinstance(node, Call):
            self._walk_call(node, scope, in_function)
            return

        if isinstance(node, Set):
            # The right-hand side is evaluated before the binding is created.
            self._walk(node.expr, scope, in_function)
            if isinstance(node.expr, Call) and node.expr.name.startswith("new "):
                self.instance_classes[node.name] = node.expr.name[4:].strip()
            self._check_binding(node.name, node.pos, scope)
            return

        if isinstance(node, Require):
            if isinstance(node.cond, Literal) and node.cond.value is True:
                self._add("warning", "'require' condition is literal true",
                          node.cond.pos or node.pos)
            self._walk(node.cond, scope, in_function)
            return

        if isinstance(node, ForEach):
            self._walk(node.iterable, scope, in_function)
            self._check_binding(node.name, node.pos, scope)
            self._walk(node.body, scope, in_function)
            return

        if isinstance(node, FunctionDef):
            self._walk_function_def(node, scope)
            return

        # Remaining nodes (Unary, Binary, Show, If, RepeatWhile, Return,
        # ListLiteral, MapLiteral, Index, Length, AddTo, SetItem, Break,
        # Continue, Fail, Expect, ...) need no scope changes of their own:
        # their children are walked in the very same scope.
        for child in _node_children(node):
            self._walk(child, scope, in_function)

    def _walk_call(self, node, scope, in_function):
        if node.name.startswith("new "):
            class_name = node.name[4:].strip()
            info = self.class_info.get(class_name)
            if info is not None:
                for label, _expr in node.args:
                    if label not in info[0]:
                        self._add(
                            "warning",
                            f"Class '{class_name}' has no field '{label}'",
                            node.pos)
        elif node.name not in self.known_callables:
            self._add("error",
                      f"Call to unknown function or builtin '{node.name}'",
                      node.pos)
        for _label, expr in node.args:
            self._walk(expr, scope, in_function)

    def _walk_method_call(self, node, scope, in_function):
        self._walk(node.receiver, scope, in_function)
        if isinstance(node.receiver, Variable):
            class_name = self.instance_classes.get(node.receiver.name)
            info = self.class_info.get(class_name)
            if info is not None and node.method not in info[1]:
                self._add("warning",
                          f"Class '{class_name}' has no method '{node.method}'",
                          node.pos)
        for _label, expr in node.args:
            self._walk(expr, scope, in_function)

    def _walk_method_def(self, node, scope, class_name):
        if not node.params or node.params[0] != "this":
            self._add("error",
                      f"Method '{node.name}' must declare 'this' as its first "
                      f"parameter", node.pos)
        method_scope = _Scope(parent=scope)
        seen = set()
        for param in node.params:
            if param in seen:
                self._add("error", f"Duplicate parameter '{param}'", node.pos)
            seen.add(param)
            method_scope.defined.add(param)

        previous = None
        if class_name is not None:
            previous = self.instance_classes.get("this")
            self.instance_classes["this"] = class_name
        self._walk(node.body, method_scope, in_function=True)
        if class_name is not None:
            if previous is None:
                self.instance_classes.pop("this", None)
            else:
                self.instance_classes["this"] = previous

    def _walk_function_def(self, node, scope):
        # The name and aliases are already hoisted into the global scope by
        # pass 1; add them locally too so a nested definition can recurse.
        for name in [node.name] + list(node.aliases):
            if name in self.builtins:
                self._add("warning", f"Name '{name}' shadows a builtin",
                          node.pos)
            scope.defined.add(name)

        function_scope = _Scope(parent=scope)
        seen_params = set()
        for param in node.params:
            if param in seen_params:
                self._add("error", f"Duplicate parameter '{param}'", node.pos)
            seen_params.add(param)
            if param in self.builtins:
                self._add("warning", f"Name '{param}' shadows a builtin",
                          node.pos)
            if param in self.function_names:
                self._add("error",
                          f"Local binding '{param}' shadows function '{param}'",
                          node.pos)
            function_scope.defined.add(param)

        self._walk(node.body, function_scope, in_function=True)

    def _check_binding(self, name, pos, scope):
        if name in self.builtins:
            self._add("warning", f"Name '{name}' shadows a builtin", pos)
        if name in self.function_names:
            self._add("error",
                      f"Local binding '{name}' shadows function '{name}'",
                      pos)
        scope.defined.add(name)

    def _is_known(self, name, scope, in_function):
        current = scope
        while current is not None:
            if name in current.defined:
                return True
            current = current.parent
        # A function body is checked where the function is *defined*, which
        # may precede a global assignment it uses. Allow any global binding
        # there rather than invent a forward-reference error.
        if in_function and name in self.all_global_names:
            return True
        return False


def lint_program(program) -> list[Diagnostic]:
    """Lint an already-parsed canonical ``Program``."""
    return _Linter(program).run()


def lint_source(source: str) -> list[Diagnostic]:
    """Tokenize, parse and lint source text (parse errors propagate)."""
    program = Parser(Lexer(source).tokenize()).parse_program()
    return lint_program(program)
