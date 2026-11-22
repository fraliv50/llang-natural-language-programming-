# llang Language Reference

*The authoritative reference for the implemented language. Every rule below is derived from `src/llang/` (`lexer.py`, `parser.py`, `ast_nodes.py`, `synonyms.py`, `interpreter.py`, `errors.py`) as of this writing. Where an older design document proposes something the interpreter does not do, the code wins. Run a program with `python run.py file.ll`; the library API is `run_source(source) -> Interpreter` and `run_file(path) -> None`.*

---

## 1. Introduction and design principles

llang ("ell-lang") reads like structured English and behaves like Python. It is a dynamically typed tree-walking interpreter written in Python, with a small canonical AST and a closed surface vocabulary of English synonyms.

| Principle | What it means in the implementation |
|---|---|
| **Surface flexibility, canonical precision** | The parser desugars every surface spelling into exactly one canonical node (`ast_nodes.py`); the interpreter only ever sees canonical nodes. A synonym can never change behaviour. |
| **Python semantics underneath** | Truthiness, short-circuit/operand-returning `and`/`or`, float division, object-reference mutation, lexical closures and map insertion order follow Python. Divergences are listed in §9. |
| **No implicit coercion** | Incompatible operations fail loudly with a source location; there is no silent type conversion. |
| **One precedence, left to right** | Every binary operator has the same precedence and associates left to right; `(` `)` are the only grouping mechanism. |
| **Visible block structure** | Blocks are closed by `end if`, `end repeat`, `end function`, `end expect`, `end method`, `end class`. Indentation is decoration only. |
| **Explicit, labeled calls** | Arguments are `label = value` pairs, never positional; no defaults, no `*args`. |
| **AI-first** | Verbose, regular, unambiguous phrasing is preferred over brevity. Fast, localized diagnostics let a model self-correct. |
| **Closed vocabulary** | No user-defined syntax, macros, operator overloading, imports, or generators. A minimal class/record system (§5.4) is part of the closed grammar. Libraries extend values and types, never grammar. |

Programs are UTF-8 text. At startup the interpreter creates one global environment and preloads every entry of `interpreter.BUILTINS` (§6) into it as a `Builtin` value. Execution order is source order; expressions are evaluated left to right. `show` writes one rendered line to stdout and also records it in `interpreter.output`.

---

## 2. Lexical structure

**Token kinds.** `WORD`, `NUMBER`, `STRING`, `PUNCT`, `NEWLINE`, `EOF`. The lexer emits one `EOF` token at the end.

**Whitespace and lines.** Space, tab and carriage return (`\r`) are skipped everywhere between tokens; indentation has *no* syntactic meaning. Each `\n` produces a `NEWLINE` token (so CRLF files work). A statement is terminated by `NEWLINE` or `EOF`; blank lines are skipped by the parser.

**Comments.** `#` starts a comment that runs to the end of the line or EOF. Comments are discarded entirely. Only `#` is a comment marker — `//` and `--` are lexer errors.

**Identifiers (`WORD`).** First character must satisfy Python's `str.isalpha()` or be `_`; remaining characters must satisfy `str.isalnum()` or be `_`. Names are case-sensitive. Unicode letters are accepted by the lexer. A plain name may not be one of the 61 reserved words (§10). A leading `@` escapes that restriction: `@end`, `@function`, and `@method` are valid identifiers, labels, parameters, and definition names anywhere a name is accepted. The formatter emits the `@` automatically when it prints a reserved name, so formatting round-trips. Note that `a`, `an`, `is`, and `any` are **not** reserved, and neither are operator words such as `plus` or `equals` (these act as operators in expression position, so avoid them as variable names).

**Numbers.** One or more ASCII digits `0`–`9`, optionally followed by `.` and at least one more ASCII digit. Values become Python `int` or `float` via `int()`/`float()`. There is no leading sign, exponent, hexadecimal/octal/binary form, underscore separator, or leading `.`. Negative values are expressions: `0 minus 5`.

**Strings.** Double quotes only. Supported escapes: `\n` (newline), `\t` (tab), `\"` (quote), `\\` (backslash). Any other escape drops the backslash, so `\q` yields `q`. A newline or EOF before the closing quote raises `Unterminated string literal` at the *opening quote's* position; a trailing backslash at EOF raises `Unterminated escape sequence`. Single quotes are not string delimiters (`Unexpected character "'"`). There are no multiline strings, f-strings, or adjacent-literal concatenation.

**Punctuation.** Only `(`, `)`, `,`, `=`. `=` is used solely between a label and its value in a call. Every other symbol (`+ - * / % ** == != < > <= >= [ ] { } : . & | !`) is an `Unexpected character` lexer error.

**Source positions.** `SourcePos` is 1-based for both line and column. The lexer increments the column for every character consumed and resets it to 1 after `\n`. Positions are attached to AST nodes and used in all diagnostics.

---

## 3. Types and values

| llang notion | Runtime value |
|---|---|
| number | Python `int` or `float`, **excluding** `bool` (`_is_number`) |
| text | Python `str` (a sequence of Unicode code points) |
| boolean | Python `bool` (`true`, `false`) |
| nothing | Python `None` |
| list | Python `list` |
| map | Python `dict` (insertion-ordered) |
| function | `Function` (user-defined, with closure) or `Builtin` (standard library) |
| class | `ClassValue` (name, declared fields, method table, definition environment) |
| instance | `Instance` (an ordered field map plus a hidden class marker) |

**Display (`_render`).** `nothing → "nothing"`, `true → "true"`, `false → "false"`, list → `"[" + ", ".join(render(item)) + "]"`, map → `"{" + ", ".join(render(key) + ": " + render(value)) + "}"` in insertion order, instance → `Name(field: value, ...)` with fields in declaration order, everything else → Python `str(value)`. Floats therefore render as Python does (`3.5`, `2.0`). Rendering is used by `show`, by `text of`, and by `join`.

**Truthiness (`_truthy`).** Exactly Python `bool(value)`. Falsy: `nothing`, `false`, numeric zero (`0`, `0.0`), empty text, empty list, empty map. Everything else — including functions and non-empty strings — is truthy. Empty-predicates are intentionally narrower: `0 is empty` and `false is empty` are **false** (§4).

**Equality (`_equal`).** Booleans only equal booleans: `true equals 1` is `false` (a deliberate divergence from Python's `True == 1`). Otherwise Python `==` is used, so `5 equals 5.0` is true, lists/maps compare structurally, and `5 equals "5"` is false.

**Mutability and aliasing.** Names are *bindings*, not boxes. `set x to xs` binds `x` to the same object; it never copies. Lists, maps, and instances are mutable: `add VALUE to LIST`, `set item KEY of COLL to VALUE`, and map/list/instance in-place mutations are visible through every alias. Numbers, text, booleans and `nothing` are immutable. There are no copy operations. Function parameters are bound to the passed objects in a fresh environment: rebinding a parameter inside a function is invisible to the caller, but mutating a shared list is visible.

**No other types.** There are no tuples, sets, bytes, generators, exception objects, or modules. Classes and instances are the only user-defined value types (§5.4).

---

## 4. Expressions

### 4.1 Operators

`expr ::= unary (operator unary)*`. All binary operators have identical precedence and associate **left to right**. There is no precedence table. `(` expr `)` is the only way to override grouping. `2 plus 3 times 4` is `(2 plus 3) times 4 = 20`; `2 plus (3 times 4) = 14`.

Operator phrases are matched from the longest table entry first (`synonyms.OPERATOR_PHRASES`), over a run of consecutive `WORD` tokens. Symbolic operators do not exist.

| Canonical code | Surface spellings | Semantics |
|---|---|---|
| `ADD` | `plus` | numbers + numbers → arithmetic sum; text + text → concatenation; anything else → `Operator 'ADD' requires numbers (or two texts for plus), got X and Y` |
| `SUB` | `minus` | numbers only |
| `MUL` | `times` | numbers only |
| `DIV` | `divided by` | numbers only; always float (`7 divided by 2 → 3.5`); zero → `Division by zero` |
| `FLOORDIV` | `floor divided by` | numbers only; floor division (`7 floor divided by 2 → 3`), rounds toward negative infinity; zero → `Floor division by zero` |
| `MOD` | `modulo` | numbers only; Python `%`; zero → `Modulo by zero` |
| `POW` | `to the power of` | numbers only; Python `**` |
| `GT` | `is greater than`, `is more than`, `exceeds` | two numbers or two texts |
| `LT` | `is less than` | two numbers or two texts |
| `GE` | `is at least` | two numbers or two texts |
| `LE` | `is at most` | two numbers or two texts |
| `EQ` | `equals`, `is equal to` | value equality with the boolean guard of §3 |
| `NE` | `does not equal`, `is not equal to`, `differs from` | negation of `EQ` |
| `AND` | `and` | short-circuit; returns an operand |
| `OR` | `or` | short-circuit; returns an operand |
| `NOT` | `not` (prefix) | returns a boolean |

Ordering comparisons require two numbers **or** two texts; mixed pairs raise `Comparison requires two numbers or two texts, got X and Y`. There is no comparison chaining: `a is less than b is less than c` groups as `(a < b) < c` and fails on types; use `(a is less than b) and (b is less than c)`. There is no identity operator; bare `is` is not an operator at all.

`and` / `or` follow Python: they evaluate the left operand, short-circuit, and return the last evaluated *operand*, not necessarily a boolean (`0 or "fallback"` → `"fallback"`; `"kept" and "second"` → `"second"`). `not` is the only prefix operator and binds to the immediately following unary expression: `not a equals b` groups as `(not a) equals b`. Because all operators have equal precedence, parenthesize each comparison inside a boolean expression.

`not`, binary operators and postfix predicates compose as: `unary ::= "not" unary | postfix`; `postfix ::= primary predicate*`; `expr ::= unary (operator unary)*`.

### 4.2 Postfix predicates

These are parsed after a primary and may be chained. They map to unary AST nodes.

| Phrase | True when |
|---|---|
| `is empty` | value is `nothing`, or an empty text/list/map. `0` and `false` are **not** empty. |
| `is not empty` | negation of `is empty` |
| `is nothing` | value `is None` (the only singleton check) |
| `is a number` | `int`/`float` but not `bool` |
| `is text` | value is a `str` |
| `is a list` | value is a `list` |
| `is a map` | value is a `dict` |

Examples: `show (an empty list) is empty` → `true`; `show 0 is empty` → `false`; `show nothing is nothing` → `true`.

### 4.3 Literals and collection literals

- Number literals, string literals, and `true`, `false`, `nothing` (reserved singleton words).
- `a list of expr (, expr)*` — at least one element; elements evaluated left to right.
- `an empty list` — `[]`.
- `a map with key mapped to value (, key mapped to value)*` — at least one entry; keys evaluated and hashed first, then values; duplicate keys keep the last value; insertion order is preserved.
- `an empty map` — `{}`.
- `a` / `an` are **not** reserved words. They only begin a collection literal when immediately followed by `list`, `map`, or `empty`; otherwise they are ordinary identifiers (`set a to 5` is legal).

### 4.4 Indexing, length, calls

- `item KEY of COLL` evaluates the collection first, then the key. For text/list the key must be a non-boolean whole number in `[0, len)`; negative indices are rejected. Out of range raises the catchable problem `index_out_of_range` with message `index K is out of range`; a wrong key type raises `Index must be a whole number`. For a map, a missing key raises the catchable problem `missing_key` with message `map has no key RENDERED_KEY`. Indexing anything else raises `Indexing requires a list, map, or text`.
- `the length of COLL` returns `len` for text/list/map; anything else raises `Length requires a list, map, or text`.
- `ask INSTANCE to METHOD [with label = expr, ...]` calls a method and is a primary expression, so it can be nested (`show ask p to total` or `show (ask p to total) plus 1`). The receiver is evaluated first, then the argument values left to right. It supplies `this` = receiver automatically; callers must not pass a `this` label. Details in §5.4.
- `call NAME [with label = expr, ...]` is a primary expression, so it can be nested anywhere: `show call welcome with name = "Ada"`, `set n to (call text of with value = 42) plus "!"`. A bare `call ...` statement evaluates and discards the result.
- **Call names** are the maximal run of `WORD` tokens after `call`, stopping at `with`, end of line/EOF, or punctuation. Reserved and operator words are allowed inside a call name; this is how phrase names such as `call uppercase of with ...`, `call is text with ...`, and `call read text from with ...` work. No call name may contain `with`, because `with` introduces the arguments. An empty name raises `Expected a function or built-in name after 'call'`.
- **Labels** are non-reserved identifiers, or any word prefixed with `@` when the parameter itself is reserved (e.g. `call total with @end = 41`). Label order is arbitrary; all parameters are mandatory. Argument *values* are parsed with the full expression parser, which is greedy: parenthesize a collection literal or other compound value that precedes another label, e.g. `call join with items = (a list of 1, 2, 3), separator = ","`. Without parentheses the list literal absorbs the following label and parsing fails.
- Call evaluation order: the callable name is resolved first, then argument values are evaluated left to right, then labels are validated.

---

## 5. Statements

One statement per line. `block ::= statement*`, terminated by its explicit closer. Blocks do **not** create a new scope; they share the enclosing environment.

### 5.1 Variables and mutation

| Statement | Semantics |
|---|---|
| `set NAME to EXPR` / `let NAME be EXPR` | Evaluate `EXPR`, then bind `NAME` in the current environment (RHS before LHS). Rebinding is allowed; there is no declaration step. |
| `set item KEY of TARGET to VALUE` | Evaluate target, then key, then value; mutate in place. List target: key must be a non-boolean whole number in range, else `List index must be a whole number` / `List index K is out of range`. Map target: key must be hashable, else `Map key must be a hashable value`; an existing key keeps its position. Other targets: `'set item ... of ...' requires a list or map`. |
| `add VALUE to TARGET` | Evaluate target first, then value; append to a list, mutating in place. Non-list target → `'add ... to ...' requires a list`. |
| `show EXPR` / `display EXPR` / `print EXPR` | Three exact synonyms. Render the value (`_render`), print one line, append to `interpreter.output`. |

### 5.2 Checks, conditionals and loops

| Statement | Semantics |
|---|---|
| `require EXPR [, "message"]` | Evaluate condition with universal truthiness. Truthy → no output. Falsy → runtime error with the literal message (parsed at the `require` statement's position) or `Requirement failed`. The optional message must be a double-quoted string literal. |
| `if EXPR then` … [`otherwise if EXPR then` …]* [`otherwise` …] `end if` | Conditions evaluated top to bottom; the first truthy branch runs, the rest are skipped. `end if` is mandatory. |
| `repeat while EXPR` … `end repeat`, or `while EXPR` … `end repeat` | Condition re-evaluated before each pass. Both openers close with `end repeat`. |
| `repeat for each NAME in EXPR` … `end repeat` | Evaluate the iterable once and **snapshot** it: list → items, text → code points, map → keys in insertion order. Anything else → `Iteration requires a list, map, or text`. `NAME` is bound in the current environment on each pass and remains bound after the loop. Mutations to the collection during iteration do not affect the loop. `for each` alone is not a statement; the `repeat` prefix is required. |
| `stop the loop` | Break out of the nearest loop. Outside a loop → `'stop the loop' used outside a loop`. |
| `skip to the next item` | Continue with the next iteration. Outside a loop → `'skip to the next item' used outside a loop`. |

Both loop forms have a safety guard: after more than **100 000** iterations they raise `Loop exceeded 100000 iterations (possible infinite loop)` at the loop's position.

### 5.3 Functions

```
define function NAME [taking p1, p2, ...]
also known as ALIAS1, ALIAS2        # optional; or: also called [as] ALIAS1, ALIAS2
    ...
end function
```

- `define a function ...` is an exact synonym of `define function ...`.
- The alias line must come immediately after the definition line. `also known as`, `also called`, and `also called as` are accepted. Every alias binds to the *same* `Function` object.
- Function, class, and method **definition names may be multi-word phrases** (e.g. `define function find all taking xs`), which are then called as `call find all with xs = ...`. Names, aliases, and parameters must be non-reserved identifiers unless escaped with `@`; the method receiver must be `this` (or `@this`). Parameters are mandatory, labeled, and have **no defaults**.
- If any of the function's names is already bound locally in the environment where the definition executes, the definition fails: `Name 'X' is already defined; a function alias cannot shadow it`. At global scope the builtin names count as already bound, so a user function cannot be named `trim`, `sort`, etc.
- A function body runs in a fresh `Env(parent=definition_env)`. Free variables are resolved at call time through that parent chain (lexical closure, late binding).
- `give back EXPR` / `return EXPR` (exact synonyms) exit the function with a value. Falling off the end returns `nothing`. A `give back` outside a function raises `'give back' used outside a function` at its position.
- `call NAME with label = value, ...` invokes a user function or builtin. For user functions: unknown label → `Unknown argument 'X' for function 'F'; expected: p1, p2` (or `(none)`); missing labels → `Missing argument(s) for 'F': p, q`; duplicate labels → `Argument 'X' supplied twice`. A name bound to a non-callable → `'X' is not a function`; an unbound name → `Undefined name 'X'`. All at the call's position.

### 5.4 Classes and methods (minimal system)

```
define class NAME [taking field1, field2, ...]
    define method METHOD taking this, param1, param2, ...
        ...
        give back value
    end method
end class
```

`define class NAME ... end class` is an executable statement: it creates a
`ClassValue` and binds `NAME` in the current environment at that point, so the
name must be defined before it is constructed. `define a class` is an exact
synonym. The `taking` list declares the constructor fields (in order, no
duplicates). A class may contain only method definitions; any other statement
in a class body is a parse error. `define method` / `define a method` are exact
synonyms; every method must declare `this` as its first parameter (a parse-time
error otherwise), and a missing `end method` is a parse error.

Construction is a `Call` whose name starts with `new `:

```
set p to call new Point with x = 1, y = 2
```

- The class name is looked up at the call position. An unbound name raises
  `Unknown class 'C'`; a bound non-class raises `'C' is not a class`.
- Every declared field is mandatory and may be supplied exactly once:
  `Missing argument(s) for 'C': y`, `Unknown argument 'z' for class 'C';
  expected: x, y`, `Argument 'x' supplied twice`. `this` cannot be a
  constructor label.
- A fresh `Instance` is created with an ordered field map containing exactly
  the supplied fields. There is no constructor body and no way to return a
  value from construction.

Fields are accessed with the ordinary item syntax; the key must be text:

- `item "x" of p` reads a field. An undeclared field raises the **catchable**
  problem `unknown_field` with message `class 'C' has no field 'x'`; a
  declared-but-uninitialized field raises the catchable problem
  `missing_field` with message `field 'x' was never initialized` (defensive:
  construction initializes every declared field). A non-text key raises
  `Field name must be text`.
- `set item "x" of p to value` writes to the **instance** field map only.
  Undeclared fields raise `unknown_field`; a non-text key raises
  `Field name must be text`. There are no class variables to shadow.

Methods are called with `ask`:

```
ask p to move with dx = 3, dy = 4
show ask p to total            # methods are expressions too
```

- The receiver must be an `Instance` (`'ask' requires an instance`), and the
  method is looked up on the receiver's class (`no such method 'm' on C`).
- `this` is bound in a fresh environment to the receiver; the method body runs
  in `Env(parent=definition_env)`, exactly like a function body. All other
  labels are mandatory, like function/call arguments: unknown labels raise
  `Unknown argument 'x' for method 'm'; expected: this, ...`, missing labels
  raise `Missing argument(s) for 'm': ...`, and a caller-supplied `this` label
  is rejected at parse time with `'this' is supplied automatically and cannot
  be a call label`.
- `give back` / `return` exits a method with a value; falling off the end
  returns `nothing`. A `give back` in a method never escapes as "'give back'
  used outside a function". Break/continue and the 100 000-iteration loop guard
  behave exactly as in functions.
- A method can call another method on `this` (`ask this to other with ...`);
  lookup always starts from the receiver's class, so an override would be used
  if inheritance were added.

**Scope rule (decision #12).** A class body is *not* an enclosing scope for
methods. Methods see their parameters (including `this`), their own locals, the
environment where the class was defined, and globals — never sibling methods
or class-body names as bare identifiers. Read fields with `item "x" of this`.

**Aliasing.** Instances are ordinary mutable values: `set q to p` aliases the
same object, and field writes through `q` are visible through `p`. There is no
copy operation.

**Deliberately omitted (first version).** Single inheritance is not
implemented, so there is no `inherits` clause, no base chain, and no
`super()`/`__mro__`. Also omitted: class variables (all state is declared
fields), name mangling (field names are plain text), privacy enforcement,
descriptors, `__slots__`, metaclasses, `__getattr__`, operator/special methods,
method assignment (monkey-patching), and a `when created` constructor body.
These divergences are recorded in §9.

### 5.5 Problems (exceptions)

```
fail with KIND [, "message"]

expect
    ...body...
[if a problem of kind KIND occurs then
    ...handler...]*
[if a problem occurs then              # catch-all (kind "any")
    ...handler...]*
[if nothing went wrong then
    ...else body...]
[always
    ...cleanup...]
end expect
```

- `fail with KIND [, "message"]` raises a problem. `KIND` is a non-reserved name (an ordinary string tag, not a class); `any` is the reserved-by-convention catch-all tag. The message must be a double-quoted string literal.
- An unhandled problem reaching the top level becomes `ERROR: Unhandled problem 'KIND': message at line X, column Y` (the `: message` part is omitted when absent).
- `expect` is Python's `try`. The body runs; zero or more problem handlers follow, checked in source order on a raised problem; the first handler whose kind is `any` or exactly equals the problem's kind runs, the rest are skipped, and an unmatched problem is re-raised. `if nothing went wrong then` is the `else` clause; `always` is `finally` and runs on every exit path.
- Block boundaries inside `expect` are recognized at `always`, `end`, `if nothing`, and `if a problem`. `end expect` is mandatory; a missing one raises `Unexpected end of input — missing 'end expect'`.
- Divergences worth noting: the `if nothing went wrong then` body executes **inside** the protected region, so a problem it raises *is* caught by handlers (Python's `try/else` is not). `give back` / `stop the loop` / `skip to the next item` are not forbidden inside `always`; they propagate like Python `finally` signals.

---

## 6. Builtins

`Interpreter.__init__` preloads all 57 names below into the global environment. They are values of type `Builtin`; each call resolves the name, evaluates the labeled arguments, then invokes the underlying Python function with those labels as keyword arguments. Consequences that apply to **every** row:

- A missing required label raises `Missing argument(s) for 'NAME': label` at the call position.
- An unknown/extra label raises `Unknown argument(s) for 'NAME': label; expected: ...`. Every builtin has a closed label contract in `BUILTIN_SPECS`.
- A duplicate label is rejected earlier by the call machinery: `Argument 'label' supplied twice`.
- Type/value errors from a builtin are wrapped as `In call to 'NAME': <reason>` at the call position. `OSError` from file I/O is wrapped the same way.
- All spellings in one row are aliases for the identical function.

### 6.1 Conversions and predicates

| Call name(s) | Labels → result | Semantics |
|---|---|---|
| `text of`, `to text`, `to_text` | `value` → text | `_render(value)`: `nothing`/`true`/`false` become words, lists/maps render recursively |
| `number from text`, `to number`, `to_number` | `text` → number | Python `int(text)` first, then `float(text)`; accepts whitespace and signs; a failure raises `'<text>' is not a number` |
| `number`, `is number`, `is_number` | `value` → boolean | number but not boolean |
| `text`, `is text`, `is_text` | `value` → boolean | `isinstance(value, str)` |
| `list`, `is list`, `is_list` | `value` → boolean | `isinstance(value, list)` |
| `map`, `is map`, `is_map` | `value` → boolean | `isinstance(value, dict)` |

### 6.2 Maps and collections

| Call name(s) | Labels → result | Semantics |
|---|---|---|
| `keys of`, `keys` | `collection` → list | Keys of a map, in insertion order; non-map → `keys requires a map` |
| `values of`, `values` | `collection` → list | Values of a map, in insertion order; non-map → `values requires a map` |
| `contains`, `does contain` | `collection`, `value` → boolean | Python `in`: list membership, map **keys**, text substring; other collection types → `contains requires a list, map, or text` |
| `join`, `join items` | `items`, `separator` → text | Renders each item with `_render`, then `separator.join(...)`; requires a list and a text separator; empty list → `""` |
| `split`, `split text` | `text`, `by` → list | Python `str.split(by)`; an empty delimiter → `split delimiter cannot be empty` |
| `sort`, `sorted` | `items` → list | New sorted list; all numbers or all text, empty list → `[]`; mixed types → `sort requires all numbers or all text` |
| `sum`, `sum of` | `items` → number | Python `sum`; list of numbers required; empty → `0` |
| `minimum`, `minimum of` | `items` → item | Python `min`; non-empty list of all numbers or all text; mixed types raise a wrapped comparison error |
| `maximum`, `maximum of` | `items` → item | Python `max`; same constraints as `minimum` |
| `reverse of`, `reverse` | `items` → list | New list in reverse order; does not mutate the original |

### 6.3 Numbers and text

| Call name(s) | Labels → result | Semantics |
|---|---|---|
| `absolute`, `absolute value of` | `value` → number | Python `abs`; booleans rejected (`absolute requires a number`) |
| `rounded`, `rounded to places` | `value`, [`places` = 0] → number | Python `round(value, places)` — ties-to-even; `places` must be a whole number (not boolean) |
| `uppercase of`, `uppercase` | `text` → text | Python `str.upper()` |
| `lowercase of`, `lowercase` | `text` → text | Python `str.lower()` |
| `trim` | `text` → text | Python `str.strip()` |
| `find in text` | `text`, `piece` → number | Python `str.find`: first 0-based index or `-1` (empty piece → `0`) |
| `replace in text` | `text`, `old`, `new` → text | Replace **all** occurrences (Python `str.replace`); an empty `old` → `the text to replace cannot be empty` |
| `insert into` | `collection`, `index`, `value` → nothing | Insert `value` into the list at `index`, shifting later items; mutates in place; index must be a whole number in `0..length` |
| `slice` | `collection`, optional `start`/`finish` → list or text | Python-style `[start:finish]` with clipping; `nothing` means omitted; negative bounds count from the end; `finish <= start` yields empty |

### 6.4 Higher-order calls

| Call name(s) | Labels → result | Semantics |
|---|---|---|
| `apply` | `fn`, `args` → any | Call the function value in `fn` with a **list of positional values** bound to its parameters in order. Arity mismatch is a localized error. This is how the converter translates Python calls to callable parameters such as `key(x)`. |
| `predict` | `model`, `features` → any | Call the `predict` function value stored in a model map, passing `(model, features)`. Used by the machine-learning library so models are self-describing maps. |

### 6.5 Files

| Call name(s) | Labels → result | Semantics |
|---|---|---|
| `read text from`, `read_file` | `path` → text | Open `path` with UTF-8 and return its whole contents; `path` must be text. There is no sandbox or path policy. |
| `write text to`, `write_file` | `path`, `content` → nothing | Truncate/write `content` to `path` as UTF-8, return `nothing`; parent directories must exist. |

Both file builtins require text arguments (`read_file requires a text path`, `write_file requires text path and content`). `OSError` from `open()` is wrapped into a source-located `RuntimeErrorLang` with the message `In call to '<name>': <reason>`.

**Builtin names are ordinary global bindings.** A single-word builtin such as `trim` can be overwritten with `set trim to 5`; phrase names containing spaces cannot be used as variable names. `lint_source` / `lint_program` (in `src/llang/linter.py`) can warn about shadowing, but the linter is opt-in and is not called by `run_source` or `run.py`.

---

## 7. Errors and diagnostics

**Format.** `LangError.render()` produces:

```
message at line X, column Y
  expected one of: 'token1', 'token2'
```

The second line appears only when the error carries expected-token hints (each item `repr`-quoted). Positions are `line X, column Y`, both 1-based; they come from the token or AST node where the problem was detected. `run.py` prints `ERROR: ` followed by that rendering and exits with status 1. Library callers receive the exception; output produced before the failure is retained in `interpreter.output`.

**Classes.** `ParseError` (syntax) and `RuntimeErrorLang` (runtime) subclass `LangError`; the lexer raises the base `LangError` directly. An internal `ProblemSignal` from `fail with` is converted by `Interpreter.run` into a `LangError` with message `Unhandled problem 'KIND'` plus `: message` when supplied.

**Common exact messages** (all followed by ` at line X, column Y` unless noted):

| Phase | Message |
|---|---|
| Lexer | `Unexpected character 'X'`, `Unterminated string literal`, `Unterminated escape sequence` |
| Parser | `Expected 'WORD', found 'X'` (+ hint), `Expected a name, found 'X'` (+ `'a non-reserved identifier'`), `Reserved word 'X' cannot be used here`, `Expected end of line, found 'X'`, `Unexpected token 'X' in expression`, `Unexpected end of input — missing matching 'end'`, `Unexpected end of input — missing 'end expect'`, `Unexpected end of input — missing 'end class'`, `Expected 'method', found 'X'`, `A method's first parameter must be 'this'`, `Only method definitions are allowed in a class body`, `'this' is supplied automatically and cannot be a call label`, `Unexpected 'end' — no matching block opener`, `Unexpected 'otherwise' — no matching block opener`, `Expected 'known' or 'called' after 'also'`, `Expected a string message after ','` / `Expected a message text after ','` (+ `'string'`), `Expected a function or built-in name after 'call'`, `Unknown statement starting with 'X'` (+ 11 hints: `set`, `show`, `require`, `if`, `repeat`, `define`, `give back`, `call`, `add`, `stop the loop`, `skip to the next item`) |
| Runtime — names/calls | `Undefined name 'X'`, `'X' is not a function`, `Argument 'X' supplied twice`, `Unknown argument 'X' for function 'F'; expected: p1, p2`, `Missing argument(s) for 'F': p, q`, `In call to 'NAME': ...`, `Name 'X' is already defined; a function alias cannot shadow it` |
| Runtime — classes | `Unknown class 'C'`, `'C' is not a class`, `Unknown argument 'z' for class 'C'; expected: x`, `Missing argument(s) for 'C': y`, `Duplicate field 'x' in class 'C'`, `Duplicate method 'f' in class 'C'`, `no such method 'm' on C`, `'ask' requires an instance`, `Field name must be text`, catchable problems `unknown_field` / `missing_field`, `Name 'C' is already defined` |
| Runtime — values | `Operator 'ADD' requires numbers (or two texts for plus), got X and Y` (the parenthetical appears only for `ADD`), `Division by zero`, `Modulo by zero`, `Comparison requires two numbers or two texts, got X and Y`, `Length requires a list, map, or text`, `Index must be a whole number`, `Indexing requires a list, map, or text`, `'add ... to ...' requires a list`, `'set item ... of ...' requires a list or map`, `List index must be a whole number`, `List index K is out of range`, `Map key must be a hashable value`, `Iteration requires a list, map, or text`, `Requirement failed` (or the custom message) |
| Runtime — control | `Loop exceeded 100000 iterations (possible infinite loop)`, `'give back' used outside a function`, `'stop the loop' used outside a loop`, `'skip to the next item' used outside a loop`, `Unhandled problem 'KIND': message` |

**Position conventions.** Arithmetic/comparison errors use the left operand's position (the `Binary` node inherits it); statement errors (`require`, `add`, `set item`, loops, `fail`, `define`) use the statement's first token; call errors use the `call` keyword; `show call ...` errors therefore point at `call`, not at `show`. Operator error operands are rendered with `_render`.

**Optional linter diagnostics** use the shape `error: message at line X, column Y` or `warning: message at line X, column Y` (`Diagnostic.__str__`); these are produced only by `lint_source`/`lint_program` and never affect execution.

---

## 7b. Modules and libraries

A module is a `.ll` file whose top-level functions and values become exports. Load it with `use the <name> module`; it is looked up as `lib/<name>.ll` (then `<name>.ll` in the working directory) and loaded once. The module's functions close over the module environment, so they can call each other by unqualified name.

Call an export with a qualified name; the words before `with` form the call name:

```
use the math module
show call sqrt from math with value = 81
show item "pi" of math
```

`use the <name> module as <alias>` binds the module under a different name, which lets a native and a foreign module with the same name coexist.

**Foreign modules are explicitly opt-in and labeled** with the `foreign` keyword:

```
use the foreign json module
use the foreign math module as hostmath
```

Foreign modules are an allowlist in `src/llang/foreign.py` (`json`, `math`, `shell`). They are host-language code, not llang-native; values cross the boundary as ordinary numbers, texts, lists and maps. Every foreign call goes through the same labeled-argument validation as a builtin. Native libraries live in `lib/` and are written entirely in llang.

**The `shell` module** is the most powerful foreign entry and is opt-in by construction. Its calls take the command as visible text, capture stdout/stderr/exit code into a map, enforce a timeout, and never execute implicitly:

```
use the foreign shell module
set result to call run command from shell with command = "echo hello"
show item "code" of result      # 0
show item "output" of result    # "hello\n"
```

`output of command` raises on a nonzero exit; `command succeeds` returns a boolean; `environment value` reads a host variable. The native `lib/shell.ll` layer wraps these with `run`, `capture`, `succeeds`, `must_succeed`, `lines`, `run_each`, and `env`, and aliases the foreign module internally to avoid a name collision. Design grounding and the full safety model are in `docs/research/terminal-semantics.md`.

---

## 8. Grammar summary (compact EBNF)

```ebnf
program      ::= (statement NEWLINE | NEWLINE)*
statement    ::= set | set_item | add | show | require | if | repeat
               | stop | skip | function_def | return | call | fail | expect | use
               | class_def | method_def | ask_expr
set          ::= ("set" name "to" | "let" name "be") expr
set_item     ::= "set item" expr "of" expr "to" expr
add          ::= "add" expr "to" expr
show         ::= ("show" | "display" | "print") expr
require      ::= "require" expr ["," STRING]
use          ::= "use the" ["foreign"] name "module" ["as" name]
if           ::= "if" expr "then" NEWLINE block
                 ("otherwise if" expr "then" NEWLINE block)*
                 ["otherwise" NEWLINE block] "end if" NEWLINE
repeat       ::= ("repeat while" expr | "while" expr) NEWLINE block "end repeat" NEWLINE
               | "repeat for each" name "in" expr NEWLINE block "end repeat" NEWLINE
stop         ::= "stop the loop"
skip         ::= "skip to the next item"
function_def ::= "define" ["a"] "function" name ["taking" name_list] NEWLINE
                 [alias_line] block "end function" NEWLINE
class_def    ::= "define" ["a"] "class" name ["taking" name_list] NEWLINE
                 method_def* "end class" NEWLINE
method_def   ::= "define" ["a"] "method" name "taking" name_list NEWLINE
                 block "end method" NEWLINE
ask_expr     ::= "ask" expr "to" name ["with" arg_list]
alias_line   ::= ("also known as" | "also called" ["as"]) name_list NEWLINE
return       ::= ("give back" | "return") expr
call         ::= "call" call_name ["with" arg_list]
call_name    ::= WORD+                       (* up to 'with', EOL/EOF, or punctuation *)
arg_list     ::= name "=" expr ("," name "=" expr)*
fail         ::= "fail with" name ["," STRING]
expect       ::= "expect" NEWLINE block
                 ("if a problem" ["of kind" name] "occurs then" NEWLINE block)*
                 ["if nothing went wrong then" NEWLINE block]
                 ["always" NEWLINE block] "end expect" NEWLINE
name_list    ::= name ("," name)*
block        ::= (statement NEWLINE | NEWLINE)*

expr         ::= unary (op unary)*
unary        ::= "not" unary | postfix
postfix      ::= primary predicate*
predicate    ::= "is empty" | "is not empty" | "is nothing"
               | "is a number" | "is text" | "is a list" | "is a map"
primary      ::= NUMBER | STRING | "true" | "false" | "nothing" | name
               | "(" expr ")" | call | ask_expr
               | ("a" | "an") ("list of" expr ("," expr)* | "empty list")
               | ("a" | "an") ("map with" entry ("," entry)* | "empty map")
               | "item" expr "of" expr | "the length of" expr
entry        ::= expr "mapped to" expr
op           ::= "plus" | "minus" | "times" | "divided by" | "floor divided by" | "modulo" | "to the power of"
               | "to the power of" | "is greater than" | "is more than"
               | "exceeds" | "is less than" | "is at least" | "is at most"
               | "equals" | "is equal to" | "does not equal"
               | "is not equal to" | "differs from" | "and" | "or"
name         ::= WORD | "@" WORD  (* @ admits reserved words *)
def_name     ::= WORD+            (* definitions may be named by a phrase *)
```

Lexical notes: `NUMBER ::= DIGIT+ ("." DIGIT+)?` with ASCII digits only; `STRING ::= '"' ('\n' | '\t' | '\"' | '\\' | any-char-but-quote-newline)* '"'`; `WORD ::= (letter | "_") (letter | digit | "_")*` using Python Unicode letter/digit predicates; `# ... NEWLINE` is a comment; whitespace and indentation are insignificant.

---

## 9. Divergences from Python

1. **English operators only.** No `+ - * / % ** == != < > <= >=`, no `[ ] { }`, no `.attribute`, no `:`; `=` appears only in call labels. Negative numbers use `0 minus 5`.
2. **No precedence.** Every binary operator is left-associative at the same level; Python's precedence table (and `**` right-associativity) does not apply.
3. **No comparison chaining**, no `in`/`not in` operator, no `is` identity operator. `equals` is value equality; `is nothing` is the only singleton test.
4. **Boolean equality is guarded.** `true equals 1` is false, whereas Python's `True == 1` is true. `_is_number` also excludes `bool`.
5. **`plus` is not generic concatenation.** Only number+number or text+text; lists/maps cannot be added. No implicit conversion (`"5" plus 5` fails).
6. **`divided by` is always true (float) division.** Floor division is the separate operator `floor divided by` (Python `//`); `int()`-style truncation toward zero is not available.
7. **Different block keywords and mandatory closers.** `if/otherwise if/otherwise/end if`, `repeat while|while/end repeat`, `define function/end function`. No `elif`, `else`, or indentation-defined suites. No loop `else`.
8. **Iteration is snapped, not live.** `repeat for each` snapshots its collection at loop start; Python iterates the live object. Maps yield keys (as Python does) and text yields code points. Negative indices are rejected and there is no slicing.
9. **No augmented assignment or expression assignment.** `add ... to ...` and `set item ... of ...` are statements that return nothing; `set` is not an expression; there is no `+=`, walrus, or tuple unpacking.
10. **Calls are labeled only.** No positional arguments, defaults, `*args`, `**kwargs`, or callable expressions. All parameters are mandatory. Extra labels passed to *builtins* are silently ignored, where Python would raise `TypeError`.
11. **Scoping.** Functions get a new environment parented to their definition environment (lexical closure, late-bound); `if`/loop/`expect` blocks do not create scopes. There is no `global`/`nonlocal`, no class scope, no comprehensions, no generators, and no modules/imports. The minimal class/record system (§5.4) has no enclosing class scope for methods (decision #12).
12. **Exceptions are string-tagged problems.** `fail with KIND` raises a value-less tag with an optional message; there are no exception classes, inheritance, `raise from`, or exception objects. Handlers match by exact kind name or the catch-all `any`. The `if nothing went wrong then` clause runs *inside* the protected region, so its problems are caught (unlike Python's `try/else`). `give back` is not forbidden in `always`. Unhandled problems become a localized `LangError` with no traceback.
13. **Infinite-loop guard.** Loops stop after 100 000 iterations; Python has no such limit.
14. **Different standard library.** Builtins are phrase-named calls (`the length of` is syntax, `read text from` is a call), and `show`/`display`/`print` are statements, not functions. File I/O uses UTF-8 and has no sandbox; Python `OSError`s are not wrapped as llang errors.
15. **Strings.** Double quotes only; no f-strings, no adjacent literal concatenation; unknown escapes silently drop the backslash.
16. **No implicit truthiness overrides or operator overloading** (instances are not Python classes and cannot define special methods).
17. **Minimal classes, not Python classes.** Instances are records with declared fields and a hidden class marker, not Python `__dict__`-based objects. `this` is an explicit first parameter supplied by `ask`, not an implicit bound-method `self`. Construction requires every declared field; there is no `__init__` body, no mutable-default fields, no class variables, no inheritance/MRO/`super()`, no name mangling, no descriptors/`__slots__`/metaclasses/`__getattr__`, no privacy enforcement, and no monkey-patching. Field access is always the explicit `item "field" of instance` syntax — there is no `.attribute` operator. See §5.4 and the grounding document `docs/research/classes-semantics.md` §2.5.

---

## 10. Appendix: reserved words and synonym table

### Reserved words (61 — `synonyms.RESERVED`)

```
add     also    always  and     as      ask     back    be
call    called  class   define  display each    empty   end
expect  fail    false   from    function give   if      in
item    kind    known   length  let     list    loop    map
mapped  method  next    not     nothing occurs  of      or
otherwise print  problem remove  repeat  require return  set
show    skip    stop    taking  the     then    this    to
true    went    while   with    wrong
```

Not reserved: `a`, `an`, `is`, `any`, and every operator word (`plus`, `minus`, `times`, `divided by`, `modulo`, `to`, `equals`, `exceeds`, `is greater than`, …). `to` *is* reserved but is still recognized inside operator phrases (`to the power of`) and inside call names. Reserved words are rejected by `_expect_name()` (variables, parameters, labels, aliases, problem kinds) and by `_parse_primary()`; they are allowed inside multi-word call names. The two exceptions in `_parse_primary()` are `ask` (starts a method-call expression) and `this` (the receiver parameter inside a method body).

### Canonical synonym table

| Concept | Accepted surface forms | Canonical node / op |
|---|---|---|
| add | `plus` | `ADD` |
| subtract | `minus` | `SUB` |
| multiply | `times` | `MUL` |
| divide | `divided by` | `DIV` |
| floor divide | `floor divided by` | `FLOORDIV` |
| modulo | `modulo` | `MOD` |
| power | `to the power of` | `POW` |
| greater than | `is greater than`, `is more than`, `exceeds` | `GT` |
| less than | `is less than` | `LT` |
| at least | `is at least` | `GE` |
| at most | `is at most` | `LE` |
| equal | `equals`, `is equal to` | `EQ` |
| not equal | `does not equal`, `is not equal to`, `differs from` | `NE` |
| boolean logic | `and`, `or`, `not` | `AND`, `OR`, `NOT` |
| assignment | `set ... to ...`, `let ... be ...` | `Set` |
| output | `show`, `display`, `print` | `Show` |
| while loop | `repeat while ...`, `while ...` | `RepeatWhile` |
| function definition | `define function`, `define a function` | `FunctionDef` |
| function alias | `also known as ...`, `also called ...`, `also called as ...` | `FunctionDef.aliases` |
| return | `give back ...`, `return ...` | `Return` |
| class definition | `define class ...`, `define a class ...` | `ClassDef` |
| method definition | `define method ...`, `define a method ...` | `MethodDef` |
| method call | `ask ... to ...` | `MethodCall` |

Builtin aliases are listed exhaustively in §6; postfix predicates (§4.2) and problem-clause spellings (§5.4) are fixed phrases, not synonyms. All synonym forms produce byte-identical canonical ASTs apart from source positions.
