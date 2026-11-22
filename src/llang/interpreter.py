"""Tree-walking evaluator over the canonical AST.

Semantics are grounded in Python (docs/reference/python-semantics.md) with the
explicit divergences recorded in docs/SEMANTIC-DECISIONS.md: no implicit
coercion, no chained comparisons, no loop-else, visible block terminators.
"""

from .ast_nodes import (Program, Block, Literal, Variable, Unary, Binary, Call,
                        Set, Show, Require, If, RepeatWhile, FunctionDef, Return,
                        ListLiteral, MapLiteral, Index, Length, AddTo, SetItem,
                        ForEach, Break, Continue, Fail, Expect, Use,
                         ClassDef, MethodDef, MethodCall)
from .errors import LangError, RuntimeErrorLang
from .foreign import FOREIGN_CONSTANTS, FOREIGN_FUNCTIONS
from pathlib import Path


class Builtin:
    """A standard-library operation with a closed set of labeled arguments."""

    def __init__(self, name, fn, spec=None):
        self.name = name
        self.fn = fn
        self.spec = spec


def _arg(kwargs, name):
    if name not in kwargs:
        raise ValueError(f"missing argument '{name}'")
    return kwargs[name]


def _b_to_text(**kw):
    return _render(_arg(kw, "value"))


def _b_to_number(**kw):
    text = _arg(kw, "text")
    if not isinstance(text, str):
        raise ValueError("to_number requires text")
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            raise ValueError(f"'{text}' is not a number")


def _b_is_number(**kw):
    return _is_number(_arg(kw, "value"))


def _b_is_text(**kw):
    return isinstance(_arg(kw, "value"), str)


def _b_is_list(**kw):
    return isinstance(_arg(kw, "value"), list)


def _b_is_map(**kw):
    return isinstance(_arg(kw, "value"), dict)


def _b_keys(**kw):
    value = _arg(kw, "collection")
    if not isinstance(value, dict):
        raise ValueError("keys requires a map")
    return list(value)


def _b_values(**kw):
    value = _arg(kw, "collection")
    if not isinstance(value, dict):
        raise ValueError("values requires a map")
    return list(value.values())


def _b_contains(**kw):
    collection = _arg(kw, "collection")
    value = _arg(kw, "value")
    if not isinstance(collection, (list, dict, str)):
        raise ValueError("contains requires a list, map, or text")
    return value in collection


def _b_join(**kw):
    items = _arg(kw, "items")
    separator = _arg(kw, "separator")
    if not isinstance(items, list) or not isinstance(separator, str):
        raise ValueError("join requires a list of items and a text separator")
    return separator.join(_render(item) for item in items)


def _b_split(**kw):
    text = _arg(kw, "text")
    by = _arg(kw, "by")
    if not isinstance(text, str) or not isinstance(by, str):
        raise ValueError("split requires text and a text delimiter")
    if by == "":
        raise ValueError("split delimiter cannot be empty")
    return text.split(by)


def _b_sort(**kw):
    items = _arg(kw, "items")
    if not isinstance(items, list):
        raise ValueError("sort requires a list")
    if not items:
        return []
    if all(_is_number(item) for item in items):
        return sorted(items)
    if all(isinstance(item, str) for item in items):
        return sorted(items)
    raise ValueError("sort requires all numbers or all text")


def _b_sum(**kw):
    items = _arg(kw, "items")
    if not isinstance(items, list) or not all(_is_number(item) for item in items):
        raise ValueError("sum requires a list of numbers")
    return sum(items)


def _b_extreme(want_minimum, **kw):
    items = _arg(kw, "items")
    if not isinstance(items, list) or not items:
        raise ValueError("minimum/maximum requires a non-empty list")
    if not all(_is_number(item) or isinstance(item, str) for item in items):
        raise ValueError("minimum/maximum requires all numbers or all text")
    if all(isinstance(item, str) for item in items) and \
            any(_is_number(item) for item in items):
        raise ValueError("minimum/maximum cannot mix text and numbers")
    return min(items) if want_minimum else max(items)


def _b_minimum(**kw):
    return _b_extreme(True, **kw)


def _b_maximum(**kw):
    return _b_extreme(False, **kw)


def _b_absolute(**kw):
    value = _arg(kw, "value")
    if not _is_number(value):
        raise ValueError("absolute requires a number")
    return abs(value)


def _b_rounded(**kw):
    value = _arg(kw, "value")
    places = kw.get("places", 0)
    if not _is_number(value) or not isinstance(places, int) or isinstance(places, bool):
        raise ValueError("rounded requires a number and a whole-number places")
    return round(value, places)


def _b_read_file(**kw):
    path = _arg(kw, "path")
    if not isinstance(path, str):
        raise ValueError("read_file requires a text path")
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _b_write_file(**kw):
    path = _arg(kw, "path")
    content = _arg(kw, "content")
    if not isinstance(path, str) or not isinstance(content, str):
        raise ValueError("write_file requires text path and content")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return None


def _b_uppercase(**kw):
    text = _arg(kw, "text")
    if not isinstance(text, str):
        raise ValueError("uppercase requires text")
    return text.upper()


def _b_lowercase(**kw):
    text = _arg(kw, "text")
    if not isinstance(text, str):
        raise ValueError("lowercase requires text")
    return text.lower()


def _b_trim(**kw):
    text = _arg(kw, "text")
    if not isinstance(text, str):
        raise ValueError("trim requires text")
    return text.strip()


def _b_find(**kw):
    text = _arg(kw, "text")
    piece = _arg(kw, "piece")
    if not isinstance(text, str) or not isinstance(piece, str):
        raise ValueError("find requires text and a text piece")
    return text.find(piece)


def _b_replace(**kw):
    text = _arg(kw, "text")
    old = _arg(kw, "old")
    new = _arg(kw, "new")
    if not all(isinstance(item, str) for item in (text, old, new)):
        raise ValueError("replace requires three texts")
    if old == "":
        raise ValueError("the text to replace cannot be empty")
    return text.replace(old, new)


def _b_reverse(**kw):
    items = _arg(kw, "items")
    if not isinstance(items, list):
        raise ValueError("reverse requires a list")
    return list(reversed(items))


def _b_insert(**kw):
    collection = _arg(kw, "collection")
    index = _arg(kw, "index")
    value = _arg(kw, "value")
    if not isinstance(collection, list):
        raise ValueError("insert into requires a list")
    if not isinstance(index, int) or isinstance(index, bool):
        raise ValueError("insert index must be a whole number")
    if index < 0 or index > len(collection):
        raise ValueError("insert index is out of range")
    collection.insert(index, value)
    return None


def _b_apply(**kw):
    # Handled specially in Interpreter._call; this exists only to register the
    # name and its labeled-argument contract.
    raise ValueError("apply requires a function value")


def _b_predict(**kw):
    # Handled specially in Interpreter._call.
    raise ValueError("predict requires a model map")


def _b_slice(**kw):
    collection = _arg(kw, "collection")
    start = kw.get("start")
    end = kw.get("finish")
    if not isinstance(collection, (list, str)):
        raise ValueError("slice requires a list or text")
    length = len(collection)
    low = 0 if start is None else start
    high = length if end is None else end
    if not isinstance(low, int) or isinstance(low, bool):
        raise ValueError("slice start must be a whole number")
    if not isinstance(high, int) or isinstance(high, bool):
        raise ValueError("slice end must be a whole number")
    if low < 0:
        low = max(0, length + low)
    if high < 0:
        high = max(0, length + high)
    low = min(max(low, 0), length)
    high = min(max(high, 0), length)
    if high < low:
        high = low
    return collection[low:high]


# Required and optional labeled arguments for every builtin spelling. This is a
# closed contract: an unknown or missing label is a localized error, never a
# silently ignored argument.
_SPEC_GROUPS = [
    (("text of", "to text", "to_text"), ("value",), ()),
    (("number from text", "to number", "to_number"), ("text",), ()),
    (("number", "is number", "is_number"), ("value",), ()),
    (("text", "is text", "is_text"), ("value",), ()),
    (("list", "is list", "is_list"), ("value",), ()),
    (("map", "is map", "is_map"), ("value",), ()),
    (("keys of", "keys"), ("collection",), ()),
    (("values of", "values"), ("collection",), ()),
    (("contains", "does contain"), ("collection", "value"), ()),
    (("join", "join items"), ("items", "separator"), ()),
    (("split", "split text"), ("text", "by"), ()),
    (("sort", "sorted"), ("items",), ()),
    (("sum", "sum of"), ("items",), ()),
    (("minimum", "minimum of"), ("items",), ()),
    (("maximum", "maximum of"), ("items",), ()),
    (("reverse of", "reverse"), ("items",), ()),
    (("absolute", "absolute value of"), ("value",), ()),
    (("rounded", "rounded to places"), ("value",), ("places",)),
    (("uppercase of", "uppercase"), ("text",), ()),
    (("lowercase of", "lowercase"), ("text",), ()),
    (("trim",), ("text",), ()),
    (("find in text",), ("text", "piece"), ()),
    (("replace in text",), ("text", "old", "new"), ()),
    (("insert into",), ("collection", "index", "value"), ()),
    (("slice",), ("collection",), ("start", "finish")),
    (("apply",), ("fn", "args"), ()),
    (("predict",), ("model", "features"), ()),
    (("read text from", "read_file"), ("path",), ()),
    (("write text to", "write_file"), ("path", "content"), ()),
]

BUILTIN_SPECS = {}
for _names, _required, _optional in _SPEC_GROUPS:
    for _name in _names:
        BUILTIN_SPECS[_name] = (_required, _optional)


BUILTINS = {
    # conversions and predicates (phrase names + underscore aliases)
    "text of": _b_to_text, "to text": _b_to_text, "to_text": _b_to_text,
    "number from text": _b_to_number, "to number": _b_to_number, "to_number": _b_to_number,
    "number": _b_is_number, "is number": _b_is_number, "is_number": _b_is_number,
    "text": _b_is_text, "is text": _b_is_text, "is_text": _b_is_text,
    "list": _b_is_list, "is list": _b_is_list, "is_list": _b_is_list,
    "map": _b_is_map, "is map": _b_is_map, "is_map": _b_is_map,
    # maps
    "keys of": _b_keys, "keys": _b_keys,
    "values of": _b_values, "values": _b_values,
    # collections
    "contains": _b_contains, "does contain": _b_contains,
    "join": _b_join, "join items": _b_join,
    "split": _b_split, "split text": _b_split,
    "sort": _b_sort, "sorted": _b_sort,
    "sum": _b_sum, "sum of": _b_sum,
    "minimum": _b_minimum, "minimum of": _b_minimum,
    "maximum": _b_maximum, "maximum of": _b_maximum,
    "reverse of": _b_reverse, "reverse": _b_reverse,
    # numbers
    "absolute": _b_absolute, "absolute value of": _b_absolute,
    "rounded": _b_rounded, "rounded to places": _b_rounded,
    # text
    "uppercase of": _b_uppercase, "uppercase": _b_uppercase,
    "lowercase of": _b_lowercase, "lowercase": _b_lowercase,
    "trim": _b_trim,
    "find in text": _b_find,
    "replace in text": _b_replace,
    # files
    "insert into": _b_insert,
    "slice": _b_slice,
    "apply": _b_apply,
    "predict": _b_predict,
    "read text from": _b_read_file, "read_file": _b_read_file,
    "write text to": _b_write_file, "write_file": _b_write_file,
}


class Function:
    def __init__(self, definition, closure):
        self.definition = definition
        self.closure = closure

    @property
    def name(self):
        return self.definition.name

    @property
    def params(self):
        return self.definition.params

    @property
    def body(self):
        return self.definition.body


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


class ProblemSignal(Exception):
    """A raised llang problem (exception), carrying a kind and message."""

    def __init__(self, kind, message, pos=None):
        self.kind = kind
        self.message = message
        self.pos = pos
        super().__init__(f"Unhandled problem '{kind}'"
                         + (f": {message}" if message else "")
                         + (f" at {pos}" if pos is not None else ""))


class Env:
    def __init__(self, parent=None):
        self.parent = parent
        self.values = {}

    def get(self, name, pos=None):
        if name in self.values:
            return self.values[name]
        if self.parent is not None:
            return self.parent.get(name, pos)
        raise RuntimeErrorLang(f"Undefined name '{name}'", pos)

    def set(self, name, value):
        self.values[name] = value

    def has_local(self, name):
        return name in self.values


class Method:
    """A method stored in a class table. It is *not* bound until ``ask``."""

    def __init__(self, definition, closure, owner=None):
        self.definition = definition
        self.closure = closure
        self.owner = owner

    @property
    def name(self):
        return self.definition.name

    @property
    def params(self):
        return self.definition.params

    @property
    def body(self):
        return self.definition.body


class ClassValue:
    """The value bound by ``define class``: fields, methods, and a base link.

    Inheritance is deliberately omitted in this first version, so ``base`` is
    always ``None``. The helper methods below still walk a base chain so the
    lookup rule is stated in one place and can be extended later.
    """

    def __init__(self, name, fields, methods, definition_env, base=None):
        self.name = name
        self.fields = list(fields)
        self.methods = dict(methods)
        self.base = base
        self.definition_env = definition_env

    def all_fields(self):
        """Declared fields of this class and its bases, in source order."""
        result = []
        current = self
        seen = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            for name in current.fields:
                if name not in result:
                    result.append(name)
            current = current.base
        return result

    def find_method(self, name):
        """Look up a method on this class, then on its single base chain."""
        current = self
        seen = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            if name in current.methods:
                return current.methods[name]
            current = current.base
        return None


class Instance:
    """A constructed object: an ordered field map plus a hidden class marker."""

    def __init__(self, class_obj, fields):
        self.class_obj = class_obj
        self.fields = dict(fields)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _truthy(value):
    return bool(value)


def _render(value):
    if value is None:
        return "nothing"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, list):
        return "[" + ", ".join(_render(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(
            f"{_render(key)}: {_render(item)}" for key, item in value.items()
        ) + "}"
    if isinstance(value, Instance):
        body = ", ".join(
            f"{key}: {_render(item)}" for key, item in value.fields.items()
        )
        return f"{value.class_obj.name}({body})"
    return str(value)


class Interpreter:
    def __init__(self, max_iterations: int = 100_000, library_paths=None):
        self.global_env = Env()
        for name, fn in BUILTINS.items():
            self.global_env.set(name, Builtin(name, fn))
        self.max_iterations = max_iterations
        self.output = []
        self.modules = {}          # name -> map of exported functions/values
        self.foreign_modules = set()
        self.library_paths = [Path(p) for p in (library_paths or ["lib"])]

    def run(self, program: Program):
        try:
            self._exec_block(program, self.global_env)
        except ProblemSignal as problem:
            detail = f"Unhandled problem '{problem.kind}'"
            if problem.message:
                detail += f": {problem.message}"
            raise LangError(detail, problem.pos)
        except ReturnSignal as signal:
            raise LangError("'give back' used outside a function", signal.pos)
        except BreakSignal as signal:
            raise LangError("'stop the loop' used outside a loop", signal.pos)
        except ContinueSignal as signal:
            raise LangError("'skip to the next item' used outside a loop", signal.pos)
        except RecursionError:
            raise LangError("Maximum recursion depth exceeded")

    # --- statements -----------------------------------------------------
    def _exec_block(self, block, env):
        for statement in block.statements:
            self._exec_stmt(statement, env)

    def _exec_stmt(self, node, env):
        if isinstance(node, Set):
            env.set(node.name, self._eval(node.expr, env))
        elif isinstance(node, Show):
            text = _render(self._eval(node.expr, env))
            self.output.append(text)
            print(text)
        elif isinstance(node, Require):
            if not _truthy(self._eval(node.cond, env)):
                raise RuntimeErrorLang(node.message or "Requirement failed", node.pos)
        elif isinstance(node, If):
            self._exec_if(node, env)
        elif isinstance(node, RepeatWhile):
            self._exec_repeat(node, env)
        elif isinstance(node, FunctionDef):
            self._define_function(node, env)
        elif isinstance(node, Return):
            raise ReturnSignal(self._eval(node.expr, env), node.pos)
        elif isinstance(node, Call):
            self._call(node, env)
        elif isinstance(node, MethodCall):
            self._call_method(node, env)
        elif isinstance(node, AddTo):
            self._exec_add_to(node, env)
        elif isinstance(node, SetItem):
            self._exec_set_item(node, env)
        elif isinstance(node, ForEach):
            self._exec_for_each(node, env)
        elif isinstance(node, Break):
            raise BreakSignal(node.pos)
        elif isinstance(node, Continue):
            raise ContinueSignal(node.pos)
        elif isinstance(node, Fail):
            raise ProblemSignal(node.kind, node.message, node.pos)
        elif isinstance(node, Expect):
            self._exec_expect(node, env)
        elif isinstance(node, Use):
            self._exec_use(node, env)
        elif isinstance(node, ClassDef):
            self._define_class(node, env)
        elif isinstance(node, MethodDef):
            raise RuntimeErrorLang(
                "A method can only be defined inside a class", node.pos)
        else:
            raise RuntimeErrorLang(f"Cannot execute node {type(node).__name__}",
                                   getattr(node, "pos", None))

    def _exec_if(self, node: If, env):
        for cond, body in node.branches:
            if _truthy(self._eval(cond, env)):
                self._exec_block(body, env)
                return
        if node.otherwise is not None:
            self._exec_block(node.otherwise, env)

    def _exec_repeat(self, node: RepeatWhile, env):
        iterations = 0
        while _truthy(self._eval(node.cond, env)):
            iterations += 1
            if iterations > self.max_iterations:
                raise RuntimeErrorLang(
                    f"Loop exceeded {self.max_iterations} iterations (possible infinite loop)",
                    node.pos)
            try:
                self._exec_block(node.body, env)
            except ContinueSignal:
                continue
            except BreakSignal:
                break

    def _exec_for_each(self, node: ForEach, env):
        collection = self._eval(node.iterable, env)
        # Snapshot the collection so mutation during iteration is deterministic.
        if isinstance(collection, dict):
            items = list(collection)          # keys, like Python
        elif isinstance(collection, (list, str)):
            items = list(collection)
        else:
            raise RuntimeErrorLang(
                "Iteration requires a list, map, or text", node.pos)
        iterations = 0
        for item in items:
            iterations += 1
            if iterations > self.max_iterations:
                raise RuntimeErrorLang(
                    f"Loop exceeded {self.max_iterations} iterations (possible infinite loop)",
                    node.pos)
            env.set(node.name, item)
            try:
                self._exec_block(node.body, env)
            except ContinueSignal:
                continue
            except BreakSignal:
                break

    def _exec_add_to(self, node: AddTo, env):
        target = self._eval(node.target, env)
        value = self._eval(node.value, env)
        if not isinstance(target, list):
            raise RuntimeErrorLang("'add ... to ...' requires a list", node.pos)
        target.append(value)

    def _exec_set_item(self, node: SetItem, env):
        target = self._eval(node.target, env)
        key = self._eval(node.key, env)
        value = self._eval(node.value, env)
        if isinstance(target, Instance):
            if not isinstance(key, str):
                raise RuntimeErrorLang("Field name must be text", node.pos)
            if key not in target.class_obj.all_fields():
                raise ProblemSignal(
                    "unknown_field",
                    f"class '{target.class_obj.name}' has no field '{key}'",
                    node.pos)
            target.fields[key] = value
            return
        if isinstance(target, list):
            if not isinstance(key, int) or isinstance(key, bool):
                raise RuntimeErrorLang("List index must be a whole number", node.pos)
            if key < 0 or key >= len(target):
                raise RuntimeErrorLang(f"List index {key} is out of range", node.pos)
            target[key] = value
        elif isinstance(target, dict):
            try:
                hash(key)
            except TypeError:
                raise RuntimeErrorLang("Map key must be a hashable value", node.pos)
            target[key] = value
        else:
            raise RuntimeErrorLang("'set item ... of ...' requires a list or map", node.pos)

    def _exec_expect(self, node: Expect, env):
        try:
            self._exec_block(node.body, env)
            if node.else_body is not None:
                self._exec_block(node.else_body, env)
        except ProblemSignal as problem:
            for kind, handler in node.handlers:
                if kind in ("any", problem.kind):
                    self._exec_block(handler, env)
                    break
            else:
                raise
        finally:
            if node.always_body is not None:
                self._exec_block(node.always_body, env)

    def _find_module(self, name, pos):
        candidates = [base / f"{name}.ll" for base in self.library_paths]
        candidates.append(Path(f"{name}.ll"))
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        places = ", ".join(str(item) for item in candidates)
        raise RuntimeErrorLang(
            f"Cannot find module '{name}' (looked in: {places})", pos)

    def _exec_use(self, node: Use, env):
        name = node.name
        alias = node.alias or name
        if alias in self.modules:
            return

        if node.foreign:
            if name not in FOREIGN_FUNCTIONS:
                available = ", ".join(sorted(FOREIGN_FUNCTIONS)) or "(none)"
                raise RuntimeErrorLang(
                    f"Unknown foreign module '{name}'; available: {available}",
                    node.pos)
            exports = {}
            for fn_name, (fn, required, optional) in FOREIGN_FUNCTIONS[name].items():
                exports[fn_name] = Builtin(fn_name, fn, (required, optional))
            for constant, value in FOREIGN_CONSTANTS.get(name, {}).items():
                exports[constant] = value
            self.foreign_modules.add(alias)
        else:
            path = self._find_module(name, node.pos)
            source = path.read_text(encoding="utf-8-sig")
            from .lexer import Lexer
            from .parser import Parser
            program = Parser(Lexer(source).tokenize()).parse_program()
            module_env = Env(parent=self.global_env)
            try:
                self._exec_block(program, module_env)
            except ProblemSignal as problem:
                raise LangError(
                    f"While loading module '{name}': "
                    f"{problem.message or problem.kind}", problem.pos)
            exports = dict(module_env.values)

        self.modules[alias] = exports
        env.set(alias, exports)

    def _define_function(self, node: FunctionDef, env):
        for name in [node.name] + list(node.aliases):
            if env.has_local(name):
                raise RuntimeErrorLang(
                    f"Name '{name}' is already defined; a function alias cannot shadow it",
                    node.pos)
        function = Function(node, env)
        for name in [node.name] + list(node.aliases):
            env.set(name, function)

    def _define_class(self, node: ClassDef, env):
        if env.has_local(node.name):
            raise RuntimeErrorLang(
                f"Name '{node.name}' is already defined", node.pos)
        declared = []
        for name in node.fields:
            if name in declared:
                raise RuntimeErrorLang(
                    f"Duplicate field '{name}' in class '{node.name}'", node.pos)
            declared.append(name)

        methods = {}
        for definition in node.methods:
            if definition.name in methods:
                raise RuntimeErrorLang(
                    f"Duplicate method '{definition.name}' in class '{node.name}'",
                    definition.pos)
            if not definition.params or definition.params[0] != "this":
                raise RuntimeErrorLang(
                    f"Method '{definition.name}' must declare 'this' as its "
                    f"first parameter", definition.pos)
            if len(definition.params) != len(set(definition.params)):
                raise RuntimeErrorLang(
                    f"Duplicate parameter in method '{definition.name}'",
                    definition.pos)
            # Methods close over the definition environment, NOT a class scope.
            methods[definition.name] = Method(definition, env)

        class_obj = ClassValue(node.name, declared, methods, env)
        for method in methods.values():
            method.owner = class_obj
        env.set(node.name, class_obj)

    # --- expressions ----------------------------------------------------
    def _eval(self, node, env):
        if isinstance(node, Literal):
            return node.value
        if isinstance(node, Variable):
            return env.get(node.name, node.pos)
        if isinstance(node, Unary):
            return self._eval_unary(node, env)
        if isinstance(node, Binary):
            return self._eval_binary(node, env)
        if isinstance(node, Call):
            return self._call(node, env)
        if isinstance(node, ListLiteral):
            return [self._eval(element, env) for element in node.elements]
        if isinstance(node, MapLiteral):
            result = {}
            for key_expr, value_expr in node.entries:
                key = self._eval(key_expr, env)
                try:
                    hash(key)
                except TypeError:
                    raise RuntimeErrorLang("Map key must be a hashable value", node.pos)
                result[key] = self._eval(value_expr, env)
            return result
        if isinstance(node, Index):
            return self._eval_index(node, env)
        if isinstance(node, MethodCall):
            return self._call_method(node, env)
        if isinstance(node, Length):
            return self._eval_length(node, env)
        raise RuntimeErrorLang(f"Cannot evaluate node {type(node).__name__}",
                               getattr(node, "pos", None))

    def _eval_index(self, node: Index, env):
        collection = self._eval(node.collection, env)
        key = self._eval(node.key, env)
        if isinstance(collection, Instance):
            if not isinstance(key, str):
                raise RuntimeErrorLang("Field name must be text", node.pos)
            fields = collection.class_obj.all_fields()
            if key not in fields:
                raise ProblemSignal(
                    "unknown_field",
                    f"class '{collection.class_obj.name}' has no field '{key}'",
                    node.pos)
            if key not in collection.fields:
                raise ProblemSignal(
                    "missing_field", f"field '{key}' was never initialized",
                    node.pos)
            return collection.fields[key]
        if isinstance(collection, (str, list)):
            if not isinstance(key, int) or isinstance(key, bool):
                raise RuntimeErrorLang("Index must be a whole number", node.pos)
            if key < 0 or key >= len(collection):
                raise ProblemSignal("index_out_of_range",
                                    f"index {key} is out of range", node.pos)
            return collection[key]
        if isinstance(collection, dict):
            if key not in collection:
                raise ProblemSignal("missing_key",
                                    f"map has no key {_render(key)}", node.pos)
            return collection[key]
        raise RuntimeErrorLang("Indexing requires a list, map, or text", node.pos)

    def _eval_length(self, node: Length, env):
        value = self._eval(node.collection, env)
        if not isinstance(value, (list, dict, str)):
            raise RuntimeErrorLang(
                "Length requires a list, map, or text", node.pos)
        return len(value)

    def _eval_unary(self, node: Unary, env):
        op = node.op
        if op == "NOT":
            return not _truthy(self._eval(node.operand, env))
        value = self._eval(node.operand, env)
        if op in ("IS_EMPTY", "IS_NOT_EMPTY"):
            # Zero and false are NOT empty — emptiness is about containers/text.
            empty = value is None or (
                isinstance(value, (str, list, dict)) and len(value) == 0)
            return empty if op == "IS_EMPTY" else not empty
        if op == "IS_NOTHING":
            return value is None
        if op == "IS_NUMBER":
            return _is_number(value)
        if op == "IS_TEXT":
            return isinstance(value, str)
        if op == "IS_LIST":
            return isinstance(value, list)
        if op == "IS_MAP":
            return isinstance(value, dict)
        raise RuntimeErrorLang(f"Unknown unary operator '{op}'", node.pos)

    def _eval_binary(self, node: Binary, env):
        # and / or short-circuit and return operands (Python semantics).
        if node.op == "AND":
            left = self._eval(node.left, env)
            return self._eval(node.right, env) if _truthy(left) else left
        if node.op == "OR":
            left = self._eval(node.left, env)
            return left if _truthy(left) else self._eval(node.right, env)

        left = self._eval(node.left, env)
        right = self._eval(node.right, env)
        op = node.op

        if op in ("ADD", "SUB", "MUL", "DIV", "FLOORDIV", "MOD", "POW"):
            return self._arithmetic(op, left, right, node)
        if op in ("GT", "LT", "GE", "LE"):
            return self._order(op, left, right, node)
        if op in ("EQ", "NE"):
            equal = self._equal(left, right)
            return equal if op == "EQ" else not equal
        raise RuntimeErrorLang(f"Unknown operator '{op}'", node.pos)

    def _arithmetic(self, op, left, right, node):
        if op == "ADD" and isinstance(left, str) and isinstance(right, str):
            return left + right
        if not (_is_number(left) and _is_number(right)):
            raise RuntimeErrorLang(
                f"Operator '{op}' requires numbers"
                + (" (or two texts for plus)" if op == "ADD" else "")
                + f", got {_render(left)} and {_render(right)}", node.pos)
        if op == "ADD":
            return left + right
        if op == "SUB":
            return left - right
        if op == "MUL":
            return left * right
        if op == "DIV":
            if right == 0:
                raise RuntimeErrorLang("Division by zero", node.pos)
            return left / right
        if op == "FLOORDIV":
            if right == 0:
                raise RuntimeErrorLang("Floor division by zero", node.pos)
            return left // right
        if op == "MOD":
            if right == 0:
                raise RuntimeErrorLang("Modulo by zero", node.pos)
            return left % right
        if op == "POW":
            try:
                result = left ** right
            except OverflowError:
                raise RuntimeErrorLang("Power result overflow", node.pos)
            except ZeroDivisionError:
                raise RuntimeErrorLang("Power by zero", node.pos)
            if isinstance(result, complex):
                raise RuntimeErrorLang(
                    "A negative base with a fractional exponent has no real "
                    "result in llang", node.pos)
            return result
        raise RuntimeErrorLang(f"Unknown arithmetic operator '{op}'", node.pos)

    def _order(self, op, left, right, node):
        if not ((_is_number(left) and _is_number(right)) or
                (isinstance(left, str) and isinstance(right, str))):
            raise RuntimeErrorLang(
                f"Comparison requires two numbers or two texts, got "
                f"{_render(left)} and {_render(right)}", node.pos)
        if op == "GT":
            return left > right
        if op == "LT":
            return left < right
        if op == "GE":
            return left >= right
        if op == "LE":
            return left <= right
        raise RuntimeErrorLang(f"Unknown comparison '{op}'", node.pos)

    @staticmethod
    def _equal(left, right):
        # Avoid Python's True == 1 surprise: booleans only equal booleans.
        if isinstance(left, bool) != isinstance(right, bool):
            return False
        return left == right

    def _call(self, node: Call, env):
        if node.name.startswith("new "):
            return self._construct(node, env)
        if " from " in node.name:
            fn_name, _, module_name = node.name.rpartition(" from ")
            module = self.modules.get(module_name)
            if module is None:
                raise RuntimeErrorLang(
                    f"Module '{module_name}' is not loaded — add "
                    f"'use the {module_name} module'", node.pos)
            if fn_name not in module:
                raise RuntimeErrorLang(
                    f"Module '{module_name}' has no export '{fn_name}'", node.pos)
            target = module[fn_name]
        else:
            target = env.get(node.name, node.pos)

        supplied = {}
        for label, value_expr in node.args:
            if label in supplied:
                raise RuntimeErrorLang(f"Argument '{label}' supplied twice", node.pos)
            supplied[label] = self._eval(value_expr, env)

        if isinstance(target, Builtin) and target.name in ("apply", "predict"):
            if target.name == "apply":
                function = supplied.get("fn")
                arguments = supplied.get("args")
                if not isinstance(function, Function):
                    raise RuntimeErrorLang(
                        "'apply' requires an 'fn' label holding a function value",
                        node.pos)
                if not isinstance(arguments, list):
                    raise RuntimeErrorLang("'apply' requires a list of arguments",
                                           node.pos)
            else:
                model = supplied.get("model")
                if not isinstance(model, dict):
                    raise RuntimeErrorLang("'predict' requires a model map", node.pos)
                function = model.get("predict")
                if not isinstance(function, Function):
                    raise RuntimeErrorLang(
                        "the model has no 'predict' function value", node.pos)
                arguments = [model, supplied.get("features")]
            if len(arguments) != len(function.params):
                raise RuntimeErrorLang(
                    f"'{target.name}' got {len(arguments)} arguments but "
                    f"'{function.name}' takes {len(function.params)}", node.pos)
            local = Env(parent=function.closure)
            for param, value in zip(function.params, arguments):
                local.set(param, value)
            try:
                self._exec_block(function.body, local)
            except ReturnSignal as signal:
                return signal.value
            return None

        if isinstance(target, Builtin):
            required, optional = target.spec or BUILTIN_SPECS.get(target.name, ((), ()))
            allowed = set(required) | set(optional)
            unknown = [label for label in supplied if label not in allowed]
            if unknown:
                raise RuntimeErrorLang(
                    f"Unknown argument(s) for '{target.name}': {', '.join(unknown)}; "
                    f"expected: {', '.join(allowed) or '(none)'}", node.pos)
            missing = [label for label in required if label not in supplied]
            if missing:
                raise RuntimeErrorLang(
                    f"Missing argument(s) for '{target.name}': {', '.join(missing)}",
                    node.pos)
            try:
                return target.fn(**supplied)
            except (TypeError, ValueError, OSError) as exc:
                raise RuntimeErrorLang(
                    f"In call to '{target.name}': {exc}", node.pos)

        if not isinstance(target, Function):
            raise RuntimeErrorLang(f"'{node.name}' is not a function", node.pos)

        expected = list(target.params)
        for label in supplied:
            if label not in expected:
                raise RuntimeErrorLang(
                    f"Unknown argument '{label}' for function '{target.name}'; "
                    f"expected: {', '.join(expected) or '(none)'}", node.pos)
        missing = [name for name in expected if name not in supplied]
        if missing:
            raise RuntimeErrorLang(
                f"Missing argument(s) for '{target.name}': {', '.join(missing)}",
                node.pos)

        local = Env(parent=target.closure)
        for name in expected:
            local.set(name, supplied[name])
        try:
            self._exec_block(target.body, local)
        except ReturnSignal as signal:
            return signal.value
        except BreakSignal:
            raise RuntimeErrorLang(
                "'stop the loop' used outside a loop", node.pos)
        except ContinueSignal:
            raise RuntimeErrorLang(
                "'skip to the next item' used outside a loop", node.pos)
        return None

    # --- classes and methods ---------------------------------------------
    def _construct(self, node: Call, env):
        class_name = node.name[len("new "):].strip()
        try:
            target = env.get(class_name, node.pos)
        except RuntimeErrorLang:
            raise RuntimeErrorLang(f"Unknown class '{class_name}'", node.pos)
        if not isinstance(target, ClassValue):
            raise RuntimeErrorLang(f"'{class_name}' is not a class", node.pos)

        declared = target.all_fields()
        supplied = {}
        for label, value_expr in node.args:
            if label == "this":
                raise RuntimeErrorLang(
                    "'this' cannot be supplied when constructing", node.pos)
            if label in supplied:
                raise RuntimeErrorLang(f"Argument '{label}' supplied twice", node.pos)
            supplied[label] = self._eval(value_expr, env)

        unknown = [label for label in supplied if label not in declared]
        if unknown:
            raise RuntimeErrorLang(
                f"Unknown argument '{unknown[0]}' for class '{target.name}'; "
                f"expected: {', '.join(declared) or '(none)'}", node.pos)
        missing = [name for name in declared if name not in supplied]
        if missing:
            raise RuntimeErrorLang(
                f"Missing argument(s) for '{target.name}': {', '.join(missing)}",
                node.pos)
        return Instance(target, supplied)

    def _call_method(self, node: MethodCall, env):
        receiver = self._eval(node.receiver, env)
        if not isinstance(receiver, Instance):
            raise RuntimeErrorLang("'ask' requires an instance", node.pos)
        method = receiver.class_obj.find_method(node.method)
        if method is None:
            raise RuntimeErrorLang(
                f"no such method '{node.method}' on {receiver.class_obj.name}",
                node.pos)

        supplied = {}
        for label, value_expr in node.args:
            if label == "this":
                raise RuntimeErrorLang(
                    "'this' is supplied automatically and cannot be a call label",
                    node.pos)
            if label in supplied:
                raise RuntimeErrorLang(f"Argument '{label}' supplied twice", node.pos)
            supplied[label] = self._eval(value_expr, env)

        expected = list(method.params)
        for label in supplied:
            if label not in expected:
                raise RuntimeErrorLang(
                    f"Unknown argument '{label}' for method '{node.method}'; "
                    f"expected: {', '.join(expected) or '(none)'}", node.pos)
        missing = [name for name in expected
                   if name != "this" and name not in supplied]
        if missing:
            raise RuntimeErrorLang(
                f"Missing argument(s) for '{node.method}': {', '.join(missing)}",
                node.pos)

        local = Env(parent=method.closure)
        local.set("this", receiver)
        for name in expected:
            if name != "this":
                local.set(name, supplied[name])
        try:
            self._exec_block(method.body, local)
        except ReturnSignal as signal:
            return signal.value
        except BreakSignal:
            raise RuntimeErrorLang(
                "'stop the loop' used outside a loop", node.pos)
        except ContinueSignal:
            raise RuntimeErrorLang(
                "'skip to the next item' used outside a loop", node.pos)
        return None
