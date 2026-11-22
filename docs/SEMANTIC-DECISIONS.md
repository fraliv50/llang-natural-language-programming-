# Semantic decisions forced by grounding in Python

*Derived from `docs/research/python-semantics.md`. These are the places where a natural-language surface can silently change meaning. Each needs a locked rule before the parser is written. "Recommended" = my proposal; override as you like.*

## 0. Vocabulary collision found

`expect` was proposed in `DESIGN.md` for runtime assertions, and in the reference matrix for the `try` block. **Resolution: `require` for assertions, `expect` for the try-block.**

## 0b. Synonyms: deliberate decision (user override of precedent advice)

Precedent research recommends "one spelling per construct." We are **keeping a closed synonym set** because the failure mode it warns about (writer cannot predict validity) is handled by our architecture: every synonym normalizes to one canonical node, and a formatter collapses them. Function aliases are first-class (multiple names → one implementation). See `DESIGN.md` §11.

| Concept | Word |
|---|---|
| Programmer-written runtime check | `require x > 0` |
| Risky operation with handlers | `expect ... ; if a problem occurs ...` |

---

## 1. Decisions to lock

| # | Trap | Risk if hand-waved | Recommended rule | Status |
|---|---|---|---|---|
| 1 | `is` vs `==` | English "is" implies equality; Python's `is` is identity | No general identity operator in v1. `equals` for value equality; `is nothing` as the only singleton check. Forbid identity against literals. | Proposed |
| 2 | `and`/`or` return operands | Translating them to pure booleans breaks `s or "default"` | Keep Python's operand-returning semantics; document explicitly. Provide `the first truthy of ...` as a clear idiom. | Proposed |
| 3 | Chained comparisons (`0 < x <= 10`) | "between" is usually inclusive-inclusive in English | **Drop chaining in v1** (document divergence): write `x is greater than 0 and x is at most 10`. Simpler grammar. | Proposed |
| 4 | Loop `else` | No natural English equivalent; reads like "otherwise" | **Drop loop-`else` in v1** (document divergence). Rarely used. | Proposed |
| 5 | Mutable default args | "defaulting to `[]`" suggests a fresh value each call | Defaults evaluated **once at definition** (Python-faithful); lint warning for mutable defaults. | Proposed |
| 6 | Closure late binding | English suggests capture-at-creation | Free variables resolved **at call time** (Python-faithful). Document with the classic loop example. | Proposed |
| 7 | Comprehension scope | Loop variables may or may not leak | Leftmost iterable evaluated in enclosing scope; the rest in a nested scope. (Phase 5+.) | Proposed |
| 8 | Eager vs lazy | "a list of ... for each ..." hides memory/time behavior | Require an explicit `on demand` marker for generator expressions. | Proposed |
| 9 | Dict vs set ordering | "collection" hides the distinction | Guarantee dict **insertion order**; declare set iteration order **unspecified**. | Proposed |
| 10 | `/` vs `//` and `%` | English "divide" implies truncation | Distinct words: `divided by` (float) vs `whole-number quotient of ... by ...` (floor); define remainder sign explicitly. | Proposed |
| 11 | Cleanup + `return` | Cleanup silently overrides results / swallows errors | ~~Forbid `return`/`break`/`continue` inside `always`.~~ **Overruled:** Python `finally` semantics were kept; signals in `always` propagate like the reference implementation. | Superseded |
| 12 | Class scope vs method scope | "inside the class" suggests visibility | Class-body names are **not** an enclosing scope for methods (Python-faithful). | Proposed |

## 1b. Classes / records — locked rules (§5.4 of REFERENCE.md)

Grounding: `docs/research/classes-semantics.md` (Python data model checked
against our semantic matrix). These rules are locked so a natural-language
spelling can never silently change meaning.

| # | Trap | Locked rule |
|---|---|---|
| 13 | Implicit `self` vs explicit receiver | `ask INSTANCE to METHOD` inserts `this` as an automatically supplied label, and **every method must declare `this` first** (parse-time error otherwise). A caller who supplies `this` is rejected. No hidden context. |
| 14 | Class body as enclosing scope (decision #12) | A class body is **not** an enclosing scope: methods see their parameters, locals, the definition environment and globals — never sibling methods as bare names. Fields are read with `item "x" of this`. |
| 15 | Mutable class variables / shared defaults | There are no class variables. The `taking` list declares per-instance fields, all mandatory, so every instance gets a fresh field map and there is no shared-mutable-default trap. |
| 16 | Construction / `__init__` returns | Construction requires every declared field exactly once and cannot run a body or return a value; the `when created` / `bad_constructor` machinery from the research sketch is deliberately omitted for v1. |
| 17 | Inheritance complexity | Single inheritance is **omitted** in v1: no `inherits` clause, no base chain, no C3/MRO, no `super()`. Lookup is just the receiver's class method table. |
| 18 | Privacy / mangling / descriptors | No name mangling (field names are plain text), no privacy enforcement, no descriptors, `__slots__`, metaclasses or `__getattr__`. A leading `_` is a naming convention only. |
| 19 | Monkey-patching / operator overloading | Methods live in a closed class table, not a mutable instance dict; no method assignment and no operator/special methods. |

All class-related diagnostics are localized (§7 of REFERENCE.md); `unknown_field`
and `missing_field` are catchable problems. See the research document §2.5 for
the full list of deliberate divergences and the rationale.

## 2. Core vocabulary (from the matrix, recommended primaries)

| Python | Our surface |
|---|---|
| `x = 5` | `set x to 5` (alias: `let x be 5`) |
| `==` | `equals` (never bare `is`) |
| `!=` | `does not equal` |
| `<` / `<=` / `>` / `>=` | `is less than` / `is at most` / `is greater than` / `is at least` |
| `None` | `nothing` (reserved singleton) |
| `True` / `False` | `true` / `false` |
| `if / elif / else` | `if ... then ... otherwise if ... otherwise ...` |
| `while` | `repeat while ...` |
| `for x in xs` | `for each x in xs` |
| `break` / `continue` | `stop the loop` / `skip to the next item` |
| `def f(...)` | `define a function f taking ...` |
| `return x` | `give back x` |
| `import math` | `use the math module` |
| `try` | `expect ...` |
| `except E` | `if a problem of kind E occurs, handle it by ...` |
| `else:` (try) | `if nothing went wrong, then ...` |
| `finally:` | `always, whether it worked or not, ...` |
| `assert cond` | `require cond` |
| `raise E` | `fail with E` |
| `yield x` | `produce x` (word reserved so `give back` vs `produce` stay distinct) |
| `self` | `this` (choose once, be consistent) |
| `class C:` | `define class C taking fields` / `end class` |
| `def m(self, x): ...` | `define method m taking this, x` / `end method` |
| `obj.m(x)` | `ask obj to m with x = ...` |
| `C(x=1)` | `call new C with x = 1` |
| `obj.x` | `item "x" of obj` |

## 3. Cross-cutting rules (non-negotiable, from the reference)

1. Everything is an object; names are bindings, not boxes. Assignment does not copy.
2. Left-to-right evaluation, with three documented exceptions: RHS-before-LHS in `set`; target-before-RHS in `increase x by ...`; callable-before-arguments in calls.
3. Universal truthiness with Python's rules (false: `nothing`, `false`, zero of any numeric type, empty containers/strings).
4. Resolution order: local → enclosing → global → builtin. Statically scoped, dynamically resolved.
5. Iteration via a protocol (`iter`/`next`), iterable evaluated once at loop start.
6. No implicit type coercion. Incompatible operations fail loudly with a source location.
7. No undefined behavior: every construct has a defined result or a defined, loud error.

## 4. Later decisions (collections, predicates, problems)

| Topic | Decision |
|---|---|
| Collection literals | `a list of ...`, `an empty list`, `a map with k mapped to v, ...`, `an empty map` — English forms, no symbol soup |
| Indexing | `item KEY of COLLECTION`; lists/strings by whole number, maps by hashable key; out-of-range and missing keys fail loudly |
| Mutation | `add VALUE to LIST` and `set item KEY of COLL to VALUE` mutate in place (Python object-reference semantics); they are statements returning nothing |
| Iteration | `repeat for each x in COLL` iterates keys for maps, items for lists, code points for text |
| **Divergence from Python** | Iteration snapshots the collection at loop start. Python iterates live and can skip/duplicate items when the collection is mutated; we choose deterministic behavior for an AI-authored language |
| Predicates | Postfix `is empty` / `is not empty` / `is nothing` / `is a number` / `is text` / `is a list` / `is a map`. "Empty" means nothing, empty text/list/map only — `0` and `false` are NOT empty |
| Problems | `expect` is try; `if a problem of kind X occurs then` is except; `if nothing went wrong then` is else; `always` is finally; `fail with kind, "msg"` raises. Termination model matches Python; signals (`give back`, `stop`) inside `always` propagate exactly as Python `finally` does |
| Call names | Multi-word phrase names are allowed (`call uppercase of with text = ...`); the name is the run of words between `call` and `with`/EOL. No phrase may contain `with` |
| Reserved words | `a` and `an` are NOT reserved — they are identifiers unless followed by `list`/`map`/`empty` in a collection literal. All other structural words are reserved |
| Builtin naming | Every builtin has a phrase name plus a short underscore alias; all are closed-vocabulary. Libraries extend values/types, never syntax |
