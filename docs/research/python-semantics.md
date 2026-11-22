# Python Semantic Reference Matrix

**Purpose.** Grounding reference for designing an English-surface language whose *semantics* are a faithful re-expression of Python's semantics. Every claim below is traceable to the official CPython documentation; surface phrasings are **candidates**, not a final grammar.

**Authority / provenance.** Official docs for Python 3.15 (Language Reference, Tutorial, Built-in Types, Built-in Exceptions, Programming FAQ), retrieved 2026-11-22 from `docs.python.org/3/`. Items marked **[version]** are version-specific; unmarked items are stable across Python 3.x. Doc anchors are cited inline, e.g. `[Ref: Expr §6.16]`.

**Notation.** `Py:` = Python behavior. `⇒` = semantically equivalent to. `≈` = approximately equivalent to (differences noted). `Surface:` = candidate English-like syntax. **Bold** phrasing = recommended primary candidate.

---

## 0. Cross-cutting invariants (read first)

1. **Everything is an object; names are bindings, not storage boxes.** `y = x` binds `y` to the *same object*; it does not copy. Assignment, `def`, `class`, `import`, `for`-targets, `with ... as`, `except ... as`, and pattern capture all bind names. Mutation through one alias is visible through all others. `[Ref: Exec §4.2.1; Tutorial §9.1; FAQ "Why did changing list 'y' also change list 'x'?"]`
2. **Evaluation order is left-to-right**, with three critical exceptions to internalize: (a) in `a = expr`, the RHS is evaluated *before* the LHS target; (b) in `a += expr`, the target is evaluated *before* the RHS; (c) in function calls the callable is evaluated first, then all arguments left-to-right, before any binding occurs. `[Ref: Expr §6.16; Simple §7.2, §7.2.1; Expr §6.3.3]`
3. **Truthiness is universal and overloadable.** False: `None`, `False`, numeric zero of *any* numeric type, empty `str`/`tuple`/`list`/`dict`/`set`/`frozenset`/`range(0)`. Everything else is true unless the class defines `__bool__()` (used first) or `__len__()` (zero ⇒ false). Boolean operators and comparisons may call `bool()` on custom results. `[Ref: StdTypes "Truth Value Testing"; Expr §6.10, §6.11]`
4. **Scopes are determined statically (textually) but resolved dynamically (at runtime).** Resolution order: local → enclosing function scopes (nearest first) → module globals → builtins. A name bound anywhere in a block is local to that block for the *whole* block (source of `UnboundLocalError`). A class body is **not** an enclosing scope for methods. `[Ref: Exec §4.2.2; Tutorial §9.2]`
5. **Iteration is protocol-driven.** `for` evaluates its iterable expression once, calls `iter()` once to obtain an iterator, then repeatedly calls `__next__()` until `StopIteration`. Generators are iterators with suspended frames. `[Ref: Compound §8.3; StdTypes "Iterators", "Generator types"]`
6. **Exceptions use a termination model.** An uncaught exception unwinds to the caller; handlers cannot resume the failing operation in place. `finally` always runs on the way out. `[Ref: Exec §4.3; Compound §8.4]`
7. **Mutability matters.** `list`, `dict`, `set`, and most user objects are mutable; `int`, `float`, `complex`, `bool`, `str`, `tuple`, `frozenset`, `None` are immutable. In-place mutators in the standard library return `None`. `+=` may mutate in place for mutable targets. `[Ref: StdTypes "Built-in Types"; FAQ "Why did changing list 'y' also change list 'x'?"]`
8. **Argument passing is "by assignment" / by object reference.** Rebinding a parameter inside a callee is invisible to the caller; mutating the referred object is visible. There is no call-by-reference. `[Ref: FAQ "How do I write a function with output parameters (call by reference)?"]`

---

## 1. Literals and built-in types

### (a) Semantics & evaluation order
- `int`, `float`, `complex`, `str`, `bytes` literals evaluate to objects of that type with that value; float/complex values may be approximated. Integer literals: decimal, `0b`, `0o`, `0x`; Unicode `Nd` digits allowed. Float literals require a `.` or exponent; `j`/`J` suffix yields an imaginary literal. `[Ref: Expr §6.2.3; StdTypes "Numeric Types"]`
- `-3` and `3+4.2j` are **not literals** — they are unary/binary arithmetic on literals. Negative numbers arise from the unary minus operator. `[Ref: Expr §6.2.3]`
- Built-in constants: `True`, `False`, `None`, `...` (`Ellipsis`) are **keywords** and cannot be assigned to or used as attributes. `bool` is a subclass of `int`; `True == 1`, `False == 0`, with identical hashes. `[Ref: Expr §6.2.1; StdTypes "Boolean Type — bool"]`
- Adjacent string literals concatenate at **compile time**: `"a" "b" ⇒ "ab"`; only literals (not expressions) may be concatenated this way; bytes literals concatenate only with bytes, template strings only with template strings. `[Ref: Expr §6.2.3.2]`
- Container displays evaluate their items left-to-right and insert them into a **new** container: `[a, b]`, `{a, b}` (set), `(a, b)` (tuple), `{k: v}` (dict). `*` unpacks iterables into list/tuple/set displays; `**` unpacks mappings into dict displays; later duplicates win. `[Ref: Expr §6.2.5]`
- Tuple syntax: the **comma** is the constructor, not the parentheses: `1,` is a 1-tuple; `(1)` is an int; `()` is the empty tuple. `{}` is an **empty dict**, not an empty set — use `set()`. `[Ref: Expr §6.2.5.3, §6.2.5.2; Expr §6.15]`

### (b) Edge cases / gotchas
- **Literal identity is not guaranteed.** Multiple evaluations of equal literals may or may not yield the same object. CPython interns small ints (`7 is 7` is true by default) but not large ones (`123456789 is 123456789` may be false); the boundary has changed historically and CPython emits `SyntaxWarning` for `is` with an int/str literal. Never use `is` for value comparison. `[Ref: Expr §6.2.3.1; FAQ "When can I rely on identity tests with the is operator?"]`
- Arbitrary-precision `int` (no overflow; `MemoryError` instead); `float` is usually IEEE-754 double with the usual rounding, `nan`/`inf` accepted by `float()`. Ordering/complex restrictions: complex numbers have no `<`/`>`; `nan == nan` is false and all ordered comparisons with `nan` are false. `[Ref: StdTypes "Numeric Types", "Comparisons"]`
- `//` is **floor division** (rounds toward −∞), not truncation toward zero: `1//2 == 0`, `(-1)//2 == -1`, `(-22)//10 == -3`; it is chosen so `%` has the sign of the divisor and `i == (i//j)*j + (i%j)`. `/` always produces a float. `0**0 == 1`. `[Ref: StdTypes "Numeric Types" notes; FAQ "Why does -22 // 10 return -3?"]`
- Strings are immutable sequences of Unicode code points; indexing by code point, comparisons lexicographic by code point (`ord()`), not locale-aware. `"" in "abc"` is true. `[Ref: Expr §6.10; StdTypes "Text Sequence Type — str"]`
- `bool` bitwise ops `&`, `|`, `^` return `bool` and are *not* short-circuiting; prefer `and`/`or`. `[Ref: StdTypes "Boolean Type — bool"]`
- Unhashable values (`list`, `dict`, `set`) cannot be dict keys or set elements; values comparing equal (`1`, `1.0`, `True`) index the same dict entry. `[Ref: StdTypes "Set Types", "Mapping types — dict"]`

### (c) Candidate surface phrasings
| Python | Candidate phrasings |
|---|---|
| `42`, `3.14`, `2+3j`, `0xFF` | **`42`**, `the number 42`; `3.14`; `two plus three j`; `255 in hexadecimal` |
| `"hi"`, `b"hi"` | **`"hi"`**, `the text "hi"`; `the bytes "hi"` |
| `True` / `False` | **`true` / `false`**, `yes / no`, `is true / is false` (avoid `True`/`False` casing if the surface language is case-insensitive) |
| `None` | **`nothing`**, `none`, `null`, `the null value` — pick one and reserve it; must be a keyword-like singleton, not assignable |
| `...` | `ellipsis`, `the ellipsis value` |
| `[1, 2]`, `(1, 2)`, `{1, 2}`, `{"a": 1}` | **`a list of 1, 2`**, `a tuple of 1, 2`, `a set of 1, 2`, `a map of "a" to 1` — but keep Python's *comma/empty-container* rules explicit in the grammar |

**Design warning:** English "is" strongly suggests equality. Map `==` to **`equals`** and reserve `is`/`is the same object as` for identity, or you will import Python's most common beginner bug into the surface language.

---

## 2. Operators, precedence/associativity; augmented assignment

### (a) Semantics & evaluation order
- Precedence, highest → lowest (same cell = same precedence; binary operators group left-to-right except `**` and conditional expressions, which group right-to-left): `[Ref: Expr §6.17]`

  | Precedence tier | Operators |
  |---|---|
  | display / binding | `(…)`, `[…]`, `{…}`, `x[i]`, `x[i:j]`, `x(args)`, `x.attr` |
  | await | `await x` |
  | exponent | `**` (right-assoc: `2**3**2 == 512`) |
  | unary | `+x`, `-x`, `~x` |
  | multiplicative | `*`, `@`, `/`, `//`, `%` |
  | additive | `+`, `-` |
  | shifts | `<<`, `>>` |
  | bitwise | `&` then `^` then `|` |
  | comparisons | `in`, `not in`, `is`, `is not`, `<`, `<=`, `>`, `>=`, `!=`, `==` (all same precedence; chain left-to-right) |
  | boolean | `not`, then `and`, then `or` |
  | conditional | `x if C else y` (right-assoc) |
  | lambda / walrus | `lambda`, `:=` |

- Arithmetic conversions: with mixed built-in numeric operands, the narrower type is widened (complex > float > int). Comparison of mixed numeric types compares exact values. `[Ref: Expr §6.1; StdTypes "Numeric Types"]`
- Bitwise operations on ints behave as if computed in infinite two's complement; negative shift counts raise `ValueError`; `x >> n` equals floor division by `2**n`. `[Ref: StdTypes "Bitwise Operations on Integer Types"]`
- **Augmented assignment** `t += expr`: evaluate `t` **once**, evaluate `expr`, apply the binary operator, assign the result back to `t`; if the type supports in-place mutation (`__iadd__`), the original object is mutated rather than replaced. `a[i] += f(x)` looks up `a[i]` first, then evaluates `f(x)`, then writes back. `[Ref: Simple §7.2.1; FAQ "Why did changing list 'y' also change list 'x'?"]`
- Assignment expressions (`:=`, walrus) bind a name *and* return the value; useful in `if (m := re.search(...))` and `while (chunk := f.read(...))`. `[Ref: Expr §6.12]`

### (b) Edge cases / gotchas
- `x += 1` is **not** exactly `x = x + 1`: target evaluated once, and possible in-place mutation. For immutable targets the result is a new object. `some_tuple[i] += [x]` fails even though `some_tuple[i] + [x]` works, because the write-back to the tuple slot fails. `[Ref: Simple §7.2.1; FAQ "Why does a_tuple[i] += ['item'] raise an exception…?"]`
- `//` vs `/` vs `int()` truncation: `/` is true (float) division; `//` floors; `int(x)` truncates toward zero. Do not conflate. `[Ref: StdTypes "Numeric Types"]`
- `**` binds tighter than unary minus on its left: `-2**2 == -(2**2) == -4`, but `2**-1 == 0.5`. `[Ref: Expr §6.17, §6.5]`
- The comma is **not an operator**; comma-separated expressions form tuples, so `"a" in "b", "a" ⇒ (False, 'a')`. `=`, `+=`, etc. are statement syntax, not expressions. `[Ref: FAQ "What's up with the comma operator's precedence?"]`
- `and`/`or` do **not** return booleans: they return the last evaluated operand (`0 or 'x' ⇒ 'x'`, `[] and 3 ⇒ []`). `not` always returns a `bool`. `[Ref: Expr §6.11; StdTypes "Boolean Operations"]`
- `not` has lower precedence than comparisons: `not a == b` ⇒ `not (a == b)`; `a == not b` is a syntax error. `[Ref: StdTypes "Boolean Operations"]`

### (c) Candidate surface phrasings
| Python | Candidate phrasings |
|---|---|
| `a + b`, `a * b`, `a / b`, `a // b`, `a % b`, `a ** b` | **`a plus b`**, `a times b`, `a divided by b` (float), `a floor-divided by b` / `the whole-number quotient of a by b`, `a modulo b` / `the remainder of a by b`, `a to the power b` |
| `a & b`, `a | b`, `a ^ b`, `~a`, `a << n` | `a bitwise and b`, `a bitwise or b`, `a bitwise xor b`, `the bitwise complement of a`, `a shifted left by n` — these rarely read naturally; consider keeping symbolic operators as an escape hatch |
| `x += 1` | **`increase x by 1`**, `add 1 to x`, `let x be x plus 1` (but must retain single-evaluation + in-place semantics) |
| `a[i] += f(x)` | `add f(x) to item i of a` (make single evaluation of `a[i]` explicit in the spec) |
| `-2**2` | `the negative of (two to the power two)` — require explicit grouping in ambiguous English |
| `x := expr` | **`bind m to expr and use it`**, `let m be expr (and keep its value)` |

---

## 3. Comparisons (chained), boolean logic, truthiness, short-circuit

### (a) Semantics & evaluation order
- All eight comparisons (`<`, `<=`, `>`, `>=`, `==`, `!=`, `is`, `is not`) have the same precedence, lower than arithmetic/bitwise/shift. `[Ref: Expr §6.10]`
- **Chaining:** `a op1 b op2 c … opN z` ⇒ `a op1 b and b op2 c and … y opN z`, **except each subexpression is evaluated at most once**. Evaluation is short-circuit: if `a op1 b` is false, `c` (and all later operands) are never evaluated. `x < y > z` is legal and asserts no relation between `x` and `z`. `[Ref: Expr §6.10; StdTypes "Comparisons"]`
- `==`/`!=` default to identity for user objects unless `__eq__` is defined; `<`, `>`, `<=`, `>=` have **no default** — they raise `TypeError` unless the type defines rich comparison methods. Custom rich comparison methods may return non-bool values, which are coerced with `bool()` in boolean contexts. `[Ref: Expr §6.10.1; StdTypes "Comparisons"]`
- `is` / `is not` test object identity (`id()`), cannot be overloaded, and never raise. `in` / `not in` share comparison precedence: for containers `x in y ⇒ any(x is e or x == e for e in y)`; for `str`/`bytes` it is substring; for `dict` it tests **keys**; `__contains__` → `__iter__` → `__getitem__` fallback chain. `[Ref: Expr §6.10.2, §6.10.3]`
- `and`/`or` short-circuit and return **operands**; `not` returns `bool`. In control-flow positions, truthiness rules from §0.3 apply. `[Ref: Expr §6.11; StdTypes "Boolean Operations"]`

### (b) Edge cases / gotchas
- Middle operand of a chain evaluated once — critical if it has side effects or is expensive: `f() < g() < h()` calls `g()` once, not twice. `[Ref: Expr §6.10]`
- Strings compare lexicographically by Unicode code point; sequences compare element-wise and require same type for equality (`[1,2] == (1,2)` is false); ordering across sequence types raises `TypeError`. `[Ref: Expr §6.10.1]`
- Dicts compare by `(key, value)` pairs; ordering comparisons on dicts raise `TypeError`. Sets compare by subset/superset relations and are **not totally ordered** — `min()/max()/sorted()` on sets gives undefined results. `[Ref: Expr §6.10.1; StdTypes "Set Types"]`
- NaN is unequal to itself and all ordered comparisons against it are false. `[Ref: Expr §6.10.1]`
- `None` and `NotImplemented` are singletons; PEP 8 says compare with `is`, never `==`. `[Ref: Expr §6.10.1]`
- `and`/`or` returning operands is why `s or 'default'` works and why `expr and on_true or on_false` is an **unsafe** ternary emulation (fails when `on_true` is falsy) — use `x if C else y`. `[Ref: FAQ "Is there an equivalent of C's ?: ternary operator?"]`

### (c) Candidate surface phrasings
| Python | Candidate phrasings |
|---|---|
| `x < 5` | **`x is less than 5`**, `x is under 5` |
| `x <= 5`, `x > 5`, `x >= 5` | `x is at most 5`, `x is greater than 5`, `x is at least 5` |
| `x == 5` | **`x equals 5`**, `x is equal to 5` (NOT "x is 5") |
| `x != 5` | **`x does not equal 5`**, `x differs from 5` |
| `x is None` | **`x is nothing`**, `x is the null value` (reserve "is" for identity/singleton) |
| `0 < x <= 10` | **`0 is less than x, which is at most 10`**, `x is between 0 (exclusive) and 10 (inclusive)` — grammar must preserve *middle-evaluated-once* + short-circuit |
| `a and b`, `a or b`, `not a` | **`a and b`**, `a or b`, `a is not true` / `not a` — spec must state operand-returning semantics |
| `x in s` | **`x is in s`**, `s contains x` (for dict: "s has the key x") |

**Design warning:** "between" in natural language is usually inclusive-inclusive. If you offer it, require explicit `inclusive`/`exclusive` markers, otherwise you lose Python's chained-comparison semantics.

---

## 4. Assignment, multiple assignment, unpacking

### (a) Semantics & evaluation order
- Assignment evaluates the RHS expression list (a comma-separated list yields a tuple), then assigns the resulting object to each target list **left-to-right**. `[Ref: Simple §7.2]`
- Target forms: identifier, parenthesized/bracketed target lists, attribute reference, subscription/slice, and `*target` (starred). Assignment to attribute/subscription is dispatched to the object (`__setattr__`/`__setitem__`); invalid assignments raise exceptions. `[Ref: Simple §7.2; Expr §6.3.1, §6.3.2]`
- Unpacking: `a, b = iterable` requires exact length; `a, *rest, b = iterable` allows one starred target, which receives a **list** (possibly empty) of the remaining items. `[Ref: Simple §7.2; PEP 3132]`
- Slice assignment may change the sequence's length; extended slices (`step != 1`) require the replacement iterable to have exactly the same length as the slice. `[Ref: Simple §7.2; StdTypes "Mutable Sequence Types"]`
- Chain assignment `a = b = expr` assigns the same object to both targets left-to-right. `[Ref: Simple §7.2]`

### (b) Edge cases / gotchas
- **RHS before LHS**, and overlaps *within* the target list are processed left-to-right: `x = [0,1]; i = 0; i, x[i] = 1, 2` leaves `x == [0,2]` because `i` is updated before `x[i]` is resolved. By contrast `a, b = b, a` swaps correctly because RHS is fully evaluated first. `[Ref: Simple §7.2]`
- `for`-loop targets overwrite prior bindings and are **not deleted** when the loop ends; if the iterable is empty the targets are never bound by the loop. `[Ref: Compound §8.3]`
- Attribute target caveat: `inst.x = inst.x + 1` may read a **class** attribute on the RHS and create a new **instance** attribute on the LHS (`Cls.x` stays 3). `[Ref: Simple §7.2]`
- Assignment to a list subscript cannot extend the list: `IndexError` if index out of range; dict assignment inserts or replaces. `[Ref: Simple §7.2]`
- Starred target always produces a `list`, even when unpacking a tuple; at most one starred target is allowed. `[Ref: Simple §7.2]`

### (c) Candidate surface phrasings
| Python | Candidate phrasings |
|---|---|
| `x = 5` | **`set x to 5`**, `let x be 5`, `bind x to 5` |
| `a, b = b, a` | **`set a and b to b and a, simultaneously`**, `swap a and b` — must state RHS-first evaluation |
| `first, *rest = items` | **`set first to the first item of items, and rest to a list of the others`**, `give first the head of items and rest the tail` |
| `obj.attr = v` | `set the attr of obj to v` |
| `a[i] = v` | `set item i of a to v` |
| `x = y = 0` | `set both x and y to 0` |

---

## 5. Control flow: if/elif/else, for, while, break/continue/else

### (a) Semantics & evaluation order
- **if/elif/else:** evaluate each condition in order until one is true, execute that suite only, skip all remaining conditions; if none true, execute `else` (if present). `[Ref: Compound §8.1]`
- **while:** repeatedly test the condition; if false (possibly on the first test) execute `else` (if present) and terminate. `break` skips `else`; `continue` jumps back to the condition test. `[Ref: Compound §8.2; Simple §7.9, §7.10]`
- **for:** evaluate the iterable expression once, create an iterator, then for each yielded item assign it to the target list using standard assignment rules and execute the suite. On iterator exhaustion execute `else` (if present). `break` skips `else`; `continue` proceeds to the next item (or to `else` if none). `[Ref: Compound §8.3]`
- `break` terminates the **nearest enclosing loop** and skips the loop's `else`; it is illegal inside a function/class definition nested in that loop. `continue` continues the nearest enclosing loop. Both run any intervening `finally` clauses on the way out. `[Ref: Simple §7.9, §7.10]`
- `range(n)` yields `0..n-1`; `range(a, b, step)` is an immutable, memory-efficient arithmetic sequence with negative-index and slice support. `[Ref: StdTypes "Ranges"]`

### (b) Edge cases / gotchas
- **Mutable default / mutation during iteration:** the iterator is created from the iterable object, so mutating a `list` while iterating can skip items or repeat them; mutating a `dict` (adding/removing keys) during iteration raises `RuntimeError: dictionary changed size during iteration`. The safe pattern is iterating over a copy (e.g., `list(d)` or `d.copy()`). Iterating a `dict` yields its **keys** in insertion order. `[Ref: Compound §8.3; StdTypes "Mapping types — dict", "Dictionary view objects"]`
- `for` targets are rebound, not deleted, after the loop; reassigning the loop variable inside the suite has no effect on iteration (`i = 5` inside the loop is overwritten on the next iteration). `[Ref: Compound §8.3]`
- Loop `else` is **not** "otherwise if no break condition was written"; it is "ran to exhaustion without break". Empty iterable ⇒ `else` runs. Very easy to mistranslate into English. `[Ref: Compound §8.2, §8.3]`
- An `if` suite on the same line as the header cannot contain a nested compound statement (`if a: if b: ...` is illegal); the dangling-`else` problem is solved by requiring indentation. `[Ref: Compound §8 intro]`
- `while True` with a `break` is the standard "loop forever until" idiom; `while` conditions are re-evaluated each iteration (unlike `for`'s iterable, evaluated once). `[Ref: Compound §8.2, §8.3]`

### (c) Candidate surface phrasings
| Python | Candidate phrasings |
|---|---|
| `if x > 5: ... elif x == 5: ... else: ...` | **`if x is greater than 5, then …; otherwise, if x equals 5, then …; otherwise …`** — support `else if` / `otherwise if` as an alias for `elif` |
| `while cond: ...` | **`repeat while cond`**, `while cond is true, do …`, `keep doing … as long as cond` |
| `for x in items: ...` | **`for each item in items`**, `repeat for every x in items`, `do this for each x in items` |
| `for i in range(n): ...` | `repeat n times, with i counting from 0` |
| `break` | **`stop the loop`**, `break out of the loop` |
| `continue` | **`skip to the next item`**, `continue with the next iteration` |
| `for ... else:` | **`after the loop finishes normally (no stop)`**, `when the loop is exhausted without stopping` — *never* translate as "otherwise" |

**Design warning:** loop-`else` has no natural English equivalent. Either provide an explicit, verbose phrase as above, or deliberately drop it (but document that this loses Python semantics).

---

## 6. Functions: params, defaults, keyword args, *args/**kwargs, return, scope & closures

### (a) Semantics & evaluation order
- `def` is an **executable statement**: when executed it binds a function object (holding a reference to the current globals) in the local namespace. The body is **not** executed then. Decorators are evaluated at definition time in the enclosing scope and applied bottom-up: `@f1 @f2 def fn` ⇒ `fn = f1(f2(fn))`. `[Ref: Compound §8.7; Expr §6.14]`
- Parameter kinds in order: positional-only (`a, /`) → positional-or-keyword → `*args` (or bare `*` marker) → keyword-only → `**kwargs`. Positional-only params can only be supplied by position; keyword-only only by name. `[Ref: Compound §8.7; Expr §6.3.3; FAQ "What does the slash(/)…mean?"]`
- **Call binding algorithm:** create slots for formal params; place N positional arguments in first N slots; for each keyword argument fill the matching slot (duplicate ⇒ `TypeError`); fill remaining slots from defaults; if any slot lacks a value ⇒ `TypeError`. Excess positional arguments go to `*args` as a **tuple** (empty if none); excess keyword arguments go to `**kwargs` as a **new ordered dict** (empty if none). If no `*args`, too many positional args ⇒ `TypeError`; if no `**kwargs`, unknown keyword ⇒ `TypeError`. `[Ref: Expr §6.3.3]`
- `*expr` in a call must be iterable and is expanded into positional arguments; `**expr` must be a mapping with string keys, expanded into keyword arguments; a duplicate keyword raises `TypeError`. `*expr` is processed **before** keyword args even if it appears after them: `f(b=1, *(2,))` passes `a=2, b=1`. `[Ref: Expr §6.3.3]`
- **Defaults are evaluated left-to-right once, at function-definition time**, not per call. `[Ref: Compound §8.7]`
- `return expr` evaluates expr and exits the function with that value; falling off the end returns `None`. `return` in a generator means "done" and becomes `StopIteration.value`. `[Ref: Simple §7.6]`
- **Closures:** free variables are resolved from enclosing function scopes at **call time** (late binding), and functions are first-class (nested `def` can be returned/passed). `nonlocal` rebinds a name in the nearest enclosing function scope; `global` rebinds in module scope. `[Ref: Exec §4.2.2, §4.2.6; Compound §8.7; Simple §7.12, §7.13]`

### (b) Edge cases / gotchas
- **Mutable default argument trap:** `def f(x=[])` shares one list across all calls that omit `x`. Correct pattern: `def f(x=None): if x is None: x = []`. `[Ref: Compound §8.7; FAQ "Why are default values shared between objects?"]`
- **Closure late binding:** `squares = [lambda: x**2 for x in range(5)]` yields five functions all returning `16`, because `x` is looked up when called, after the loop has left `x == 4`. Fix by binding per-iteration with a default: `lambda n=x: n**2`. Applies to regular nested functions too. `[Ref: FAQ "Why do lambdas defined in a loop with different values all return the same result?"]`
- `UnboundLocalError`: assigning to `x` anywhere in a function makes `x` local for the whole function, so reading it before assignment fails even if a global `x` exists; fix with `global`/`nonlocal`. `[Ref: Exec §4.2.2; FAQ "Why am I getting an UnboundLocalError…?"]`
- Class scope is not an enclosing scope for methods: a name defined in a class body is invisible inside a method or a comprehension nested in the class body (annotation scopes are an exception). `[Ref: Exec §4.2.2]`
- Keyword arguments cannot fill positional-only slots; `def f(a, /, b)` means `f(1, b=2)` works but `f(a=1, b=2)` fails. `[Ref: FAQ "What does the slash(/)…mean?"]`
- Annotations (`: int`, `-> str`) do **not** change runtime semantics; from 3.14 they are lazily evaluated in annotation scopes. `[Ref: Compound §8.7, §8.11; Exec §4.2.3, §4.2.4]`
- A `lambda` is a single expression with an implicit `return`; it cannot contain statements or annotations. `[Ref: Expr §6.14]`
- `sys.exception()` is available inside handlers; an exception bound with `as e` is **deleted at the end of the `except` clause** (`except E as e: ... ⇒ ... finally: del e`) to avoid traceback reference cycles. `[Ref: Compound §8.4.1]`

### (c) Candidate surface phrasings
| Python | Candidate phrasings |
|---|---|
| `def f(a, b=2): ...` | **`define a function f taking a, and b defaulting to 2:`**, `to compute f of a and b (which defaults to 2):` |
| `def f(a, /, b, *, c): ...` | `define f taking a position-only, then b, then a keyword-only c` — expose explicitly; natural language has no positional-only convention |
| `def f(*args, **kwargs)` | **`define f taking any extra positional items in args and any extra named items in kwargs`** |
| `return x` | **`give back x`**, `return x`, `yield x as the result` (do NOT use "yield" if that means generators elsewhere) |
| `global x` / `nonlocal x` | `use the global x`, `refer to x from the enclosing function` |
| `f(x=1, *ys, **kw)` | `call f with x set to 1, then the items of ys, then the named items of kw` |
| `lambda x: x+1` | `the function that maps x to x plus 1` |

**Design warning:** "defaulting to 2" must be defined as *evaluated once at definition*, not "fresh each call", or the mutable-default bug resurfaces.

---

## 7. Data structures: list, dict, tuple, set — construction, indexing, slicing, mutability, ordering

### (a) Semantics & evaluation order
- **list** `[...]`: mutable sequence; `[]` empty; items evaluated left-to-right; `+` concatenates (new list), `*` repeats (references, not copies — `[[*]]*n` aliases the inner list). `[Ref: Expr §6.2.5; StdTypes "Sequence Types"]`
- **tuple** `(...)`: immutable sequence; comma is the constructor; `tuple()` / `()` empty; `(x,)` single item; hashable iff all elements hashable. `[Ref: Expr §6.2.5.3; StdTypes "Tuples"]`
- **dict** `{k: v}`: mapping from hashable keys to arbitrary values; `{}` empty; duplicate keys keep the **last** value; `**` unpacking merges with later values winning. **Insertion order is guaranteed (3.7+)**: updating a key does not change its position; a deleted key re-added goes to the end. `[Ref: Expr §6.2.5.4; StdTypes "Mapping types — dict"]`
- **set** `{...}`: unordered collection of distinct hashable objects; no literal for empty set (`set()` required); no indexing/slicing; set operations implement subset/superset comparisons. `frozenset` is the immutable, hashable counterpart. `[Ref: Expr §6.2.5.2; StdTypes "Set Types"]`
- **Indexing:** `s[i]`; negative indices add `len(s)`; out-of-range ⇒ `IndexError`; dict missing key ⇒ `KeyError` (or `__missing__`); subscription dispatches to `__getitem__`. `[Ref: Expr §6.3.2; StdTypes "Sequence Types"]`
- **Slicing** `s[i:j:k]`: indices `i + n*k` with `0 <= n < (j-i)/k`, `j` exclusive; omitted bounds default to 0 and `len(s)` for positive `k`; for negative `k`, bounds default to the other end and `s[::-1]` reverses; `k` cannot be zero; out-of-range bounds are clipped. Slicing returns a **new** container. Extended-slice assignment requires equal length. `[Ref: Expr §6.3.2.1; StdTypes "Common Sequence Operations", "Mutable Sequence Types"]`
- `in` on dict tests keys; on str/bytes tests substring; on other containers uses equality/identity. `[Ref: Expr §6.10.2]`

### (b) Edge cases / gotchas
- **Aliasing:** `b = a` then `a.append(x)` is visible via `b`; `a = a + [x]` creates a new list and leaves `b` unchanged. In-place mutators return `None`. `[Ref: FAQ "Why did changing list 'y' also change list 'x'?"]`
- **Shallow vs deep copy:** `l[:]` and `d.copy()` are shallow; nested mutable objects remain shared; use `copy.deepcopy()` for full isolation. `[Ref: FAQ "How do I copy an object in Python?"]`
- **Dict ordering guarantee applies to insertion order, not sorted order**; `sorted(d)` gives sorted keys but does not reorder `d`. Iterating a view (`d.keys()`, `d.items()`) is live: changes to `d` are reflected, and resizing during iteration raises `RuntimeError`. `[Ref: StdTypes "Mapping types — dict", "Dictionary view objects"]`
- **Set ordering is unspecified** and may change between runs/versions — never depend on iteration order. Sets are not totally ordered (`min`/`max`/`sorted` undefined on them). `[Ref: StdTypes "Set Types"; Expr §6.10.1]`
- `True`/`1`/`1.0` are interchangeable dict keys and compare equal; hashing is consistent with equality across numeric types. `[Ref: StdTypes "Mapping types — dict", "Hashing of numeric types"]`
- Slice bounds are clipped, so `s[100:200]` returns `[]` rather than raising; `-0` is `0`, so `s[-0:]` is the whole sequence. `[Ref: StdTypes "Common Sequence Operations" notes]`
- Class-level mutable attributes are shared by all instances; initialize per-instance in `__init__` instead. `[Ref: Tutorial §9.3.5; Compound §8.8]`

### (c) Candidate surface phrasings
| Python | Candidate phrasings |
|---|---|
| `[1, 2, 3]` | `a list of 1, 2, 3` |
| `d = {"a": 1}` | `set d to a map with "a" mapped to 1` |
| `a[0]`, `d["k"]` | `the first item of a` (index 0), `the item of d keyed by "k"` |
| `a[1:3]`, `a[::-1]` | `the slice of a from item 1 up to item 3`, `a in reverse order` |
| `len(a)` | `the size of a`, `how many items a has` |
| `x in d` | `d has the key x` |
| `set()` | `a new empty set` |
| `s.add(x)`, `l.append(x)` | `add x to s`, `append x to l` — document that these mutate and return nothing |

---

## 8. Comprehensions and generator expressions

### (a) Semantics & evaluation order
- List/set/dict comprehensions are container displays computed by looping/filtering: `[expr for t in iterable if cond]`, `{expr for ...}`, `{k: v for ...}`. Each `for`/`if` clause is a nested block, left-to-right. `[Ref: Expr §6.2.6]`
- At runtime: the **leftmost iterable expression is evaluated in the enclosing scope** and passed into an implicit nested function scope; everything else (targets, later iterables, filters, output expression) runs in that nested scope, so loop variables **do not leak**. `[Ref: Expr §6.2.6.2]`
- Dict comprehension key is evaluated before value (3.8+); duplicate keys keep the last value. There are **no tuple comprehensions** — `tuple(x**2 for x in ...)` uses a generator expression instead. `[Ref: Expr §6.2.6]`
- `yield`/`yield from` are forbidden inside the implicit comprehension scope; assignment expressions are forbidden in comprehension iterable expressions. `[Ref: Expr §6.2.6.2]`
- **Generator expression** `(expr for t in iterable if cond)` returns a generator iterator yielding the same values as the equivalent list comprehension, lazily. The leftmost iterable (and creation of its iterator) is evaluated **immediately** at definition; all other expressions are evaluated lazily when values are requested. Parentheses may be omitted when it is the sole argument to a call: `sum(x*x for x in xs)`. `[Ref: Expr §6.2.7]`
- Comprehensions of all kinds are roughly equivalent to a helper function that loops and appends/adds/assigns. `[Ref: Expr §6.2.6]`

### (b) Edge cases / gotchas
- **Scope leak:** `x = 'old'; [x**2 for x in range(10)]` leaves `x == 'old'` (unlike a `for` statement at module level, which would leave `x == 9`). But the leftmost iterable sees the enclosing `x`: `[x for x in xs if x > threshold]` is fine. `[Ref: Expr §6.2.6.2]`
- **Lazy genexp errors:** `(x for x in nonexistent)` raises `NameError` immediately (leftmost iterable), but `(nonexistent_expr for x in range(10))` raises only when iterated; `(x*y for x in range(10) for y in bad_iterable)` also fails late. `[Ref: Expr §6.2.7]`
- `list(genexp)` consumes the generator; reusing the same generator object afterwards yields nothing. `[Ref: StdTypes "Generator types"]`
- Generator expressions are more memory-friendly than list comprehensions but hold references to their source iterators; if the source is mutated before consumption, results may differ. `[Ref: Tutorial §9.10]`

### (c) Candidate surface phrasings
| Python | Candidate phrasings |
|---|---|
| `[x*x for x in xs]` | **`a list of x squared for each x in xs`**, `collect x squared over every x in xs` |
| `[x for x in xs if x > 0]` | `a list of x for each x in xs, keeping only those greater than zero` |
| `{k: v for k, v in pairs}` | `a map from k to v for each pair k, v in pairs` |
| `{x for x in xs}` | `a set of x for each x in xs` |
| `(x*x for x in xs)` | **`the sequence of x squared as x ranges over xs (computed on demand)`** — must convey laziness explicitly |
| `sum(x for x in xs)` | `the sum of x for each x in xs` |

**Design warning:** English "list of … for each …" is easily confused with eager vs lazy. Require a marker such as `on demand`/`lazily` for generator expressions, or you will silently change memory/time behavior.

---

## 9. Exceptions: try/except/else/finally/raise, hierarchy basics

### (a) Semantics & evaluation order
- **try/except:** execute the `try` suite; if an exception occurs, stop the suite and search `except` clauses in order. A clause matches if the raised object is an instance of the named class or a **non-virtual base class**, or of a class in a named tuple; an unqualified `except` (bare) catches everything and must be last. At most one handler runs. If none matches, propagation continues outward. `[Ref: Compound §8.4, §8.4.1; Tutorial §8.3]`
- **else:** runs only if the `try` suite completed with no exception and no `return`/`break`/`continue`; exceptions raised in `else` are **not** caught by the preceding `except` clauses. `[Ref: Compound §8.4.3; Tutorial §8.3]`
- **finally:** always runs as the last task before the `try` statement completes, including on `return`/`break`/`continue` ("on the way out"). If a pending exception exists it is re-raised after `finally`; if `finally` itself raises, the pending exception becomes the new exception's `__context__`; if `finally` does `return`/`break`/`continue`, the pending exception is **discarded**. A `return` in `finally` overrides any earlier `return`. `[Ref: Compound §8.4.4; Tutorial §8.7]`
- **raise:** with no expression, re-raises the active exception (`RuntimeError` if none active). With a class, instantiates it with no arguments; with an instance, raises that instance. `raise E from cause` sets `__cause__` (explicit chaining, shown as "direct cause"); raising while another exception is being handled sets `__context__` implicitly ("during handling"); `raise E from None` suppresses context display. `[Ref: Simple §7.8; StdTypes "Exception context"; Tutorial §8.5]`
- **Hierarchy:** `BaseException` → `Exception` (all non-system-exiting errors; user exceptions should derive from here), `SystemExit`, `KeyboardInterrupt`, `GeneratorExit`, `BaseExceptionGroup`. `Exception` → `ArithmeticError` (`ZeroDivisionError`, `OverflowError`), `AssertionError`, `AttributeError`, `LookupError` (`IndexError`, `KeyError`), `OSError` (`FileNotFoundError`, `PermissionError`, …), `TypeError`, `ValueError`, `RuntimeError`, `StopIteration`, etc. `[Ref: Exceptions "Exception hierarchy"; Tutorial §8.3]`
- `assert expr[, msg]` raises `AssertionError` and is **removed entirely** under `-O` (`__debug__` is false). `[Ref: Simple §7.3]`
- **[3.11+]** `ExceptionGroup`/`BaseExceptionGroup` bundle multiple exceptions; `except*` matches and splits subgroups rather than catching the group as a whole; `break`/`continue`/`return` are forbidden in `except*`. `[Ref: Compound §8.4.2; Exceptions "Exception groups"]`

### (b) Edge cases / gotchas
- Handler order matters: put specific classes before base classes; `except B` before `except D` catches `D` as `B`. `[Ref: Tutorial §8.3]`
- `except Exception as e` clears `e` at the end of the clause — save it to another name if needed later. `[Ref: Compound §8.4.1]`
- `raise` inside an `except` re-raises with the (possibly modified) current traceback (3.11+). `[Ref: Simple §7.8]`
- `finally` + `return` silently swallows exceptions and earlier returns; 3.14+ emits `SyntaxWarning` for `return`/`break`/`continue` in `finally`. `[Ref: Compound §8.4.4; Tutorial §8.7]`
- `except:` (bare) also catches `KeyboardInterrupt` and `SystemExit`; prefer `except Exception:`. `[Ref: Tutorial §8.3; Exceptions "Base classes"]`
- `StopIteration` raised inside a generator is converted to `RuntimeError` (PEP 479, 3.7+); `return value` in a generator is the supported way to signal completion. `[Ref: Exceptions "StopIteration"]`
- Exception **messages are not part of the API** and may change between versions; match on exception types, not message text. `[Ref: Exec §4.3]`

### (c) Candidate surface phrasings
| Python | Candidate phrasings |
|---|---|
| `try: ... except ValueError: ...` | **`expect …; if a ValueError occurs, handle it by …`**, `attempt …; on ValueError …` |
| `except E as e` | `if an E occurs, call it e and …` |
| `else:` | **`if nothing went wrong, then …`** |
| `finally:` | **`always, whether it worked or not, …`**, `clean up by …` |
| `raise E("msg")` | **`fail with E("msg")`**, `raise an E saying "msg"` |
| `raise` | `fail again with the same problem` |
| `raise E from cause` | `fail with E, caused by cause` |
| `assert cond, msg` | `require cond, or fail with msg` |

**Design warning:** `expect` (suggested in the task) is a good surface word for the `try` block, but the `else` clause must be phrased as "if nothing went wrong" — never as an `otherwise` that suggests it belongs to an `if`.

---

## 10. Classes, attributes, methods, inheritance basics

### (a) Semantics & evaluation order
- `class Name(Base): ...` is an **executable statement**: evaluate base expressions, execute the class body in a **new namespace** with the original globals, then create a class object from that namespace and bind it to `Name` in the surrounding scope. Default base is `object`. Decorators apply like function decorators (bottom-up). `[Ref: Compound §8.8; Tutorial §9.3.1, §9.3.2]`
- Attribute lookup order for an instance: instance `__dict__` → class → bases (MRO) → (fallback hooks `__getattr__`). Functions stored as class attributes become **bound methods** when accessed through an instance: `x.f()` ⇒ `Class.f(x)`, i.e. the instance is inserted as the first argument (`self` is only a convention). `[Ref: Tutorial §9.3.4; Expr §6.3.1; Compound §8.8]`
- `Class(...)` calls `__init__(self, ...)` after creating the instance; `__init__` must return `None`. Instance attributes need no declaration; first assignment creates them. `[Ref: Tutorial §9.3.2, §9.3.3]`
- Inheritance: attribute search proceeds through the base classes; a method of a base that calls another method may end up calling an override in the derived class (all methods are effectively virtual). `isinstance(obj, C)` / `issubclass(A, B)` for checks; `super()` for cooperative calls. `[Ref: Tutorial §9.5]`
- **MRO:** multiple inheritance uses C3 linearization — left-to-right, each base visited once, monotonic, enabling cooperative `super()`. Inconsistent hierarchies, non-subclassable bases, metaclass conflicts, or instance-layout conflicts are errors. `[Ref: Tutorial §9.5.1; Compound §8.8.1]`
- **Name mangling:** identifiers `__x` (two leading underscores, at most one trailing) inside a class body are textually rewritten to `_ClassName__x`; `_x` is only a convention for "private". `[Ref: Expr §6.2.2.1; Tutorial §9.6]`

### (b) Edge cases / gotchas
- **Class scope is not closed over by methods:** `class A: a = 42; b = list(a + i for i in range(10))` fails because the comprehension cannot see `a`; methods likewise must use `self.a` or `A.a`. `[Ref: Exec §4.2.2]`
- **Mutable class variable** shared by all instances: `tricks = []` at class level means every `Dog` accumulates the same list; initialize inside `__init__` instead. `[Ref: Tutorial §9.3.5; Compound §8.8]`
- Instance attribute hides class attribute on read, but `inst.x = inst.x + 1` with only a class `x` creates a new instance attribute; class `x` is unchanged. `[Ref: Simple §7.2; Tutorial §9.4]`
- `self` has no magic meaning; forgetting it in a method signature produces a confusing `TypeError` about argument counts. Methods are just functions assigned as class attributes; they need not be defined textually inside the class. `[Ref: Tutorial §9.4]`
- There is no enforced data hiding; clients can add/modify attributes; `__slots__` and descriptors are advanced mechanisms for controlling this. `[Ref: Tutorial §9.4, §9.7]`
- Attribute definition order is preserved in `Class.__dict__` right after creation (for classes defined with `class` syntax). `[Ref: Compound §8.8]`

### (c) Candidate surface phrasings
| Python | Candidate phrasings |
|---|---|
| `class Dog: ...` | **`define a class Dog:`**, `a Dog is a kind of thing with …` |
| `class Dog(Animal): ...` | **`define a class Dog that inherits from Animal:`** |
| `def __init__(self, name): self.name = name` | **`when a Dog is created with a name, set its name to that name`** |
| `dog.bark()` | `ask dog to bark`, `call bark on dog` |
| `self.x = 1` | `set this object's x to 1` (choose `this`/`self` once and be consistent) |
| `super().method()` | `call the base implementation of method` |

**Design warning:** hiding the explicit `self` parameter is tempting in an English surface language, but you must still define the binding rule (instance inserted as first argument) so method calls and overrides behave like Python's.

---

## 11. Modules, imports, namespaces

### (a) Semantics & evaluation order
- A module is a file executed in its own namespace; the namespace is created on first import and cached in `sys.modules` (so modules are singletons, and re-imports are cheap). The top-level script runs as `__main__`. `[Ref: Tutorial §9.2; Exec §4.2.2; FAQ "How can I share global variables across modules?"]`
- `import x.y` performs two steps: (1) find/load/initialize the module (executing its top-level code), (2) bind a name in the current namespace. If no `as` clause, the **top-level package** name is bound (`import a.b.c` binds `a`, and `a.b.c` must be accessed through it); `import a.b.c as z` binds the full module as `z`. `[Ref: Simple §7.11]`
- `from m import x` finds/loads `m`, then for each name: check for an attribute; if absent try importing a submodule; if still absent raise `ImportError`; otherwise bind a reference to the value in the current namespace. `[Ref: Simple §7.11]`
- `from m import *` binds all names in `m` that do not start with `_`, or exactly the names in `m.__all__` if defined; allowed only at module level (a `SyntaxError` inside a function/class). `[Ref: Simple §7.11]`
- Relative imports use leading dots: `.` = current package, `..` = one level up, etc. `[Ref: Simple §7.11]`
- `global`/`nonlocal` are parser directives affecting the whole current block; `global` must precede any use of the name in that block. `[Ref: Simple §7.12, §7.13]`
- **[3.15]** `lazy import`/`lazy from` creates a proxy that loads the module on first use; only allowed at module scope; `__lazy_modules__` provides opt-in compatibility. `[Ref: Simple §7.11.1]`
- `from __future__ import feature` is a compiler directive that must appear near the top of the module; most historical features are now redundant. `[Ref: Simple §7.11.2]`

### (b) Edge cases / gotchas
- Module objects are shared: `config.x = 1` in one module is visible to all modules that imported `config`. `from config import x` instead binds a **snapshot** of the value at import time; later reassignment of `config.x` is invisible to that name. `[Ref: FAQ "How can I share global variables across modules?"]`
- Editing an imported module and re-importing it does not reload it; `importlib.reload()` is required. `[Ref: FAQ "When I edit an imported module and reimport it, the changes don't show up…"]`
- Circular imports work with plain `import m` but break with `from m import name` at module top-level when `m` is still initializing; move the `from` import into the function that needs it. `[Ref: FAQ "How can I have modules that mutually import each other?"]`
- `eval()`/`exec()` cannot see enclosing function scopes for free variables — they resolve free names in globals (unless namespaces are supplied explicitly). `[Ref: Exec §4.2.6]`
- Module name resolution is not affected by aliases: a function's global namespace is the module where it was **defined**, not where it is called. `[Ref: Tutorial §9.2]`

### (c) Candidate surface phrasings
| Python | Candidate phrasings |
|---|---|
| `import math` | **`use the math module`**, `bring in math` |
| `import os.path as p` | `use os.path, calling it p` |
| `from math import sqrt` | **`take sqrt from the math module`**, `import sqrt out of math` |
| `from . import util` | `take util from the current package` |
| `from m import *` | `take every public name from m` — consider disallowing by design |
| `global x` | `mean x as the module-level x when assigning` |
| `nonlocal x` | `mean x from the enclosing function when assigning` |

---

## 12. Iterators and generators basics

### (a) Semantics & evaluation order
- **Iterable** implements `__iter__()` returning an **iterator**. **Iterator** implements `__iter__()` (returning `self`) and `__next__()` (returns the next item, raises `StopIteration` when exhausted). Once `__next__()` raises `StopIteration`, it must continue to do so. `[Ref: StdTypes "Iterables", "Iterators"]`
- `for`, comprehensions, unpacking, `in`, and many builtins consume iterables through this protocol. `iter(obj)` returns the iterator; `next(it)` advances it. `[Ref: Tutorial §9.8; Expr §6.10.2]`
- A **generator function** contains `yield`; calling it returns a generator iterator without executing the body. Execution begins at the first `next()` (or `send(None)`), runs to the first `yield`, suspends (retaining locals, instruction pointer, evaluation stack, exception state), and returns the yielded value. Resuming with `__next__()` makes the current `yield` expression evaluate to `None`; `send(v)` makes it evaluate to `v`. `[Ref: Expr §6.2.8; StdTypes "Generator types"]`
- `return expr` in a generator ends it and sets `StopIteration.value = expr`. `yield from subiterable` delegates to a subiterator, forwarding `send()`/`throw()` and taking the subiterator's `StopIteration.value` as the `yield from` expression's value. `[Ref: Expr §6.2.8; Simple §7.6]`
- `gen.close()` throws `GeneratorExit` at the suspension point to run `finally` cleanup; calling a generator method while it is already executing raises `ValueError`. Generators are closed automatically when garbage collected. `[Ref: StdTypes "generator.close"]`
- Generator expressions are the expression form (see §8). `[Ref: Expr §6.2.7]`

### (b) Edge cases / gotchas
- `StopIteration` escaping a generator body is converted to `RuntimeError` (PEP 479) — do not manually raise it inside generators to terminate. `[Ref: Exceptions "StopIteration"]`
- A generator is **single-use** and stateful: after exhaustion it yields nothing forever; two consumers on the same generator interfere. `[Ref: StdTypes "Iterators"]`
- `send()` on a not-yet-started generator must pass `None`; a non-`None` value is a `TypeError`. `[Ref: StdTypes "generator.send"]`
- `close()` on a generator that yields during cleanup raises `RuntimeError`; swallowing `GeneratorExit` and continuing is also an error. `[Ref: StdTypes "generator.close"]`
- Iterating a mutable container while modifying it changes what the iterator sees (skips/duplications for lists, `RuntimeError` for dict resizing) — see §5. `[Ref: Compound §8.3; StdTypes "Dictionary view objects"]`
- `yield` is prohibited inside the implicit scope of comprehensions/genexprs because it would corrupt the iteration semantics. `[Ref: Expr §6.2.6.2, §6.2.7]`

### (c) Candidate surface phrasings
| Python | Candidate phrasings |
|---|---|
| `yield x` | **`produce x`**, `yield x`, `give x to the consumer and pause here` |
| `yield from it` | `produce every item from it`, `pass through all items of it` |
| `next(it)` | `ask it for the next item` |
| `iter(xs)` | `get an iterator over xs` |
| `def gen(): ... yield ...` | **`define a generator gen that produces …`** — the word "generator" must be reserved so `return` vs `yield` semantics stay distinct |
| `gen.close()` | `close gen (run its cleanup)` |
| `(x for x in xs)` | `the on-demand sequence of x over xs` (see §8) |

---

## Appendix A — Decisions the new language must make explicitly

| Python semantic surface | Risk if hand-waved in English syntax | Recommended explicit rule |
|---|---|---|
| `is` vs `==` | English "is" implies equality | Reserve a distinct word for each |
| `and`/`or` return operands | Translating to pure booleans breaks `s or 'default'` | State operand-returning semantics in the spec |
| Chained comparisons | "between" is usually inclusive in English | Require explicit inclusive/exclusive markers; middle evaluated once |
| Loop `else` | No English equivalent | Use a verbose "when the loop finishes without stopping" or deliberately omit |
| Mutable defaults | "defaulting to []" suggests freshness | Define "evaluated once at definition" |
| Closure late binding | English suggests capture-at-creation | Define free-variable lookup at call time |
| Comprehension scope | Loop variables leaking vs not | Define leftmost-iterable-in-enclosing-scope, rest nested |
| Eager vs lazy | "list of … for each" vs "on demand" | Require a laziness marker for generator expressions |
| Dict vs set ordering | "collection" hides the distinction | Guarantee dict insertion order; declare set order unspecified |
| `//` and `%` | English "divide" implies truncation | Distinguish "floor-divided" from "divided"; define sign of remainder |
| `finally` + `return` | Cleanup silently overriding results | Either keep Python rule and warn, or forbid `return` in cleanup |
| Class scope vs method scope | English "inside the class" suggests visibility | State that class-body names are not enclosing scope for methods |
| Identity/literals | CPython small-int interning leaks into "obvious" behavior | Forbid identity comparison against literals in the surface language |

## Appendix B — Source map

- Language Reference: [Expressions](https://docs.python.org/3/reference/expressions.html), [Simple statements](https://docs.python.org/3/reference/simple_stmts.html), [Compound statements](https://docs.python.org/3/reference/compound_stmts.html), [Execution model](https://docs.python.org/3/reference/executionmodel.html), [Import system](https://docs.python.org/3/reference/import.html)
- Tutorial: [Errors and Exceptions](https://docs.python.org/3/tutorial/errors.html), [Classes](https://docs.python.org/3/tutorial/classes.html)
- Built-ins: [Built-in Types](https://docs.python.org/3/library/stdtypes.html), [Built-in Exceptions](https://docs.python.org/3/library/exceptions.html)
- FAQ: [Programming FAQ](https://docs.python.org/3/faq/programming.html)
