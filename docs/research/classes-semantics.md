# Classes / records — grounding and minimal design for llang

*Status: research for the class/record feature. Authority: Python's official
data model, checked side-by-side with our existing semantic matrix. Syntax is a
proposal only; no implementation exists yet. Follows the method in
[`../METHOD.md`](../METHOD.md).*

**Sources:**

- **[DM]** <https://docs.python.org/3/reference/datamodel.html> — especially §3.2.8.2 "Instance methods", §3.2.10 "Custom classes", §3.2.11 "Class instances", `object.__new__`/`__init__`, `__slots__`.
- **[MRO]** <https://docs.python.org/3/howto/mro.html> and [DM] §3.2.10 — C3 method resolution order.
- **[EXPR]** <https://docs.python.org/3/reference/expressions.html#private-name-mangling> — private name mangling rule (reachable from [DM] §3.2.10).
- **[CLASS]** <https://docs.python.org/3/reference/compound_stmts.html#class> — the `class` statement as an executable definition.
- **[§10]** local `docs/research/python-semantics.md` §10 "Classes, attributes, methods, inheritance basics" (the canonical reference matrix this design must stay consistent with).
- **[DEC]** local `docs/SEMANTIC-DECISIONS.md` #12 / §2 `self`→`this`, and [DESIGN] guardrails via local `docs/DESIGN.md` §3, §6, §11.

---

## 1. What the reference language actually specifies

### 1.1 A class definition is an executable statement

`class Name(Base): …` evaluates the base expressions, executes the class body in
a **new namespace** with the original globals, constructs a class object from
that namespace, then binds `Name` in the surrounding scope; the default base is
`object`. Attribute definition order in the new namespace is preserved. **[DM]**
§3.2.10, **[CLASS]**, **[§10]** §10(a). Consequence for llang: a class definition
must be a statement that binds a class value at the point of execution — not a
macro expanded at parse time.

### 1.2 Instance attributes and lookup order

- An instance has a namespace (normally `__dict__`) that is the **first** place
  attribute references are searched; assignment/deletion update the instance
  dict, never the class dict. **[DM]** §3.2.11.
- If not found on the instance, search the class dict; if still not found, walk
  the base classes using **C3 linearization**; finally the `__getattr__()`
  fallback hook if defined. **[DM]** §3.2.10, §3.2.11, **[MRO]**, **[§10]** §10(a).
- Class attribute assignment writes the class's dict, **never a base's**.
  **[DM]** §3.2.10.
- Fields need no declaration: the first assignment creates an instance
  attribute. **[§10]** §10(a) (`Class(...)` calls `__init__`; instance
  attributes need no declaration).

### 1.3 Methods and `self`

- A function stored as a **class** attribute becomes a **bound method** when
  retrieved via an instance: `x.f(1)` is `C.f(x, 1)` — the instance is inserted
  as the first argument. `self` is only a naming convention; it has no magic
  meaning. **[DM]** §3.2.8.2, **[§10]** §10(b).
- A function stored on the **instance** is *not* converted to a bound method.
  Methods need not even be defined textually inside the class body. **[DM]**
  §3.2.8.2, **[§10]** §10(b).
- Forgetting `self` produces a confusing argument-count `TypeError`; all methods
  are effectively virtual, so a base method calling another method can dispatch
  to a derived override. **[§10]** §10(a), §10(b).
- Class bodies are **not** an enclosing scope for methods: a name bound in the
  class body is invisible inside a method (and inside a comprehension in the
  class body). Methods must use `self.a` or `C.a`. **[§10]** §10(b), **[DM]**
  plus execution-model grounding in **[§10]**. This is decision #12 in **[DEC]**.

### 1.4 Inheritance and MRO

- Search proceeds through the base classes; C3 linearization is left-to-right,
  visits each class once, and is monotonic, which enables cooperative `super()`.
  Diamond hierarchies work; inconsistent hierarchies, non-subclassable bases,
  metaclass conflicts and instance-layout conflicts are errors. **[DM]**
  §3.2.10, **[MRO]**, **[§10]** §10(a). `__mro__` records the resulting tuple.
- `super()` calls the next implementation in the MRO; a derived `__init__` must
  call a base `__init__` explicitly to initialize the base part. **[§10]**
  §10(a), **[DM]** `object.__init__`.

### 1.5 Class variables vs instance variables

- A mutable class variable is shared across all instances (`tricks = []` on a
  class means every instance appends to the same list); per-instance state
  belongs in `__init__`. **[§10]** §10(b), **[DM]** §3.2.10.
- **Read/write asymmetry:** `inst.x = inst.x + 1` when `x` exists only on the
  class reads the class value and creates a new **instance** attribute; `C.x`
  is unchanged. **[§10]** §10(b).
- There is no enforced data hiding: clients can add and modify attributes;
  `_x` is only a convention. `__slots__` and descriptors are advanced control
  mechanisms, out of scope here. **[DM]** §3.2.8.2, §3.3.2.4, **[§10]** §10(b).

### 1.6 `__init__`, construction, name mangling

- Calling a class yields an instance. Arguments go to `__new__(cls, …)`, then
  normally to `__init__(self, …)`. `__init__` runs after the instance is
  created, must return `None` (a non-`None` return raises `TypeError`), and is
  where fields are initialized. **[DM]** §3.2.8.8, `object.__new__`,
  `object.__init__`, **[§10]** §10(a).
- **Name mangling:** any identifier of the form `__x` (two leading underscores,
  at most one trailing) appearing in a class body is textually rewritten to
  `_ClassName__x`. It is a compile-time textual transformation — a form of
  hidden context, not a runtime privacy check. **[EXPR]**, **[§10]** §10(a).

### 1.7 Documented pitfalls to carry forward

From **[§10]** §10(b) and **[DM]**: class scope not closed over by methods;
forgetting `self`; shared mutable class variables; shadowing a class variable on
write; no enforced privacy; attribute order preserved; methods assigned to an
instance are not bound; special methods are looked up on the type, not the
instance (irrelevant here because llang forbids operator overloading);
`__slots__`, descriptors, metaclasses and `__getattr__` are advanced hooks.

---

## 2. Proposed llang design: explicit records with single inheritance

### 2.1 Constraints inherited from the existing language (non-negotiable)

From `docs/GRAMMAR.md`, `docs/REFERENCE.md`, and **[DEC]**:

- No `.` attribute syntax (every punctuation symbol except `( ) , =` is a lexer
  error). No operator overloading, no metaprogramming, no user-defined syntax.
- Calls are `call NAME with label = expr`; argument values are labeled, all
  mandatory; call names are runs of `WORD`s up to `with`/EOL.
- `item KEY of COLL` is the existing read primitive; `set item KEY of COLL to
  VALUE` and `add VALUE to TARGET` are the mutation statements. Maps/lists are
  ordinary values with reference semantics; `nothing` is the missing value;
  problems are string-tagged `fail with kind, "msg"`.
- `this` is the chosen spelling for `self` **[DEC]** §2; blocks need explicit
  closers; indentation is decoration.
- Class-body names are **not** an enclosing scope for methods **[DEC]** #12.

### 2.2 Syntax sketch (two stacked features)

**Records (data only, no inheritance) — the minimal core:**

```
define a record Point with fields x, y
set p to call new Point with x = 1, y = 2
show item "x" of p
set item "y" of p to 5
```

**Classes (records + methods + single inheritance):**

```
define a class Animal with fields name

define a class Dog inherits from Animal with fields tricks
    when created with this, name
        set item "name" of this to name
        set item "tricks" of this to an empty list
    define a method speak taking this, phrase
        show item "name" of this plus " says " plus phrase
        give back phrase
    end method
end class

set d to call new Dog with name = "Rex", tricks = (an empty list)
ask d to speak with phrase = "woof"
```

**New grammar productions** (only three; all use existing keywords plus new
reserved words `record`, `class`, `inherits`, `fields`, `when`, `created`,
`method`, `ask`, `to`, `this` — `to` is already reserved):

```
class_def   := ("define a record" | "define a class") name
               ["inherits from" name] ["with fields" name_list] NEWLINE
               [constructor] [method_def*] "end class"
constructor := "when created with" name_list NEWLINE block
method_def  := "define a method" name "taking" name_list NEWLINE block "end method"
ask_expr    := "ask" expr "to" name ["with" arg_list]      (* primary expression *)
```

Everything else reuses existing nodes: `call new <Class> with …` is a `Call`
whose name happens to be `new <Class>` (exactly how `apply`, `slice`, and
`read text from` already work); field reads/writes reuse `Index`/`SetItem` with
a text key. Only `ClassDef`, `MethodDef` (or `FunctionDef` with a `method` flag),
and `MethodCall` are genuinely new canonical nodes.

### 2.3 Semantics — the rules that must be locked before parsing

1. **Construction.** `call new C with …` looks up class value `C`, requires every
   declared field (including inherited ones) exactly once, creates an instance
   holding an ordered field map plus a class pointer, then runs `when created`
   in a fresh environment. Unknown/missing labels → the same localized errors
   functions use (`Unknown argument 'x' for class 'C'; expected: …`).
2. **`this` is an explicit first parameter, never an implicit lookup.** Every
   constructor and method **must** declare `this` first. The call machinery
   inserts `this = <receiver>` as an automatically supplied label, exactly as
   Python inserts the instance but *visible in the signature* — no hidden
   context. A caller who supplies `this` explicitly, or a method that omits it,
   is a localized error. This directly answers the design warning in **[§10]**
   §10(c): the binding rule is stated and enforced.
3. **Field access.** `item "x" of obj` reads a field; key must be a text naming a
   declared field of the class or an ancestor. Missing/unknown field →
   catchable problems `missing_field` / `unknown_field`. Writes always go to the
   **instance** field map; there are no class variables to shadow (§2.5).
4. **Lookup order.** Instance fields → method of the defining class → method of
   its single base, walking the base chain to the root. No `__getattr__`, no
   class-level fallthrough, no descriptors. One base only ⇒ the MRO is simply
   the linear chain `[C, base(C), base(base(C)), …]`; C3/multiple inheritance is
   deliberately omitted (see §1.4 for what Python does).
5. **Virtual dispatch.** A method of a base calling another method resolves it
   starting from the *receiver's* class, so derived overrides are used — matching
   Python's "all methods are effectively virtual" **[§10]** §10(a).
6. **No class-level scope for methods.** A method body sees only its parameters
   (`this` included), its own locals, the enclosing definition environment and
   globals — never sibling fields or class-body names as bare identifiers
   (decision #12 **[DEC]**). Use `item "x" of this`.
7. **Constructors cannot return values.** `give back` inside `when created`
   fails with `bad_constructor` (the analog of Python's `__init__` `TypeError`
   for non-`None` return **[DM]** `object.__init__`).
8. **Aliasing.** Instances are ordinary mutable values: `set d2 to d` aliases the
   same object; `set item "x" of d2 to 9` is visible through `d`. No copy
   operation, consistent with REFERENCE §3.
9. **Type tests (phase 2).** `call is instance of from types with value = d,
   type = Dog` → boolean; plain `call class name of with value = d` → text.
   Argument `type` is the class *value* bound by `define a class`, which is legal
   as a labeled expression.

### 2.4 Diagnostics and problem kinds

| Situation | Result |
|---|---|
| unknown/missing constructor field | localized runtime error at the `call`, message like functions' |
| `ask` a receiver with no such method | `no such method 'speak' on Dog` at the `ask` node |
| `item` with a non-declared field | `unknown_field` problem (catchable) |
| read of a field never initialized | `missing_field` problem (catchable) |
| method without `this` first / explicit `this` at call site | parse-time or call-time localized error |
| duplicate field names, duplicate methods, unknown base | definition-time localized error |
| `give back` in `when created` | `bad_constructor` problem |
| class with two bases, `end class`/`end method` missing | parse error with expected-token hints |

### 2.5 What we deliberately omit (and why)

- **Multiple inheritance / C3 / `super()`.**

  Python's C3 is correct but adds a whole linearization algorithm, MRO conflicts,
  and cooperative-`super()` reasoning **[DM]** §3.2.10, **[MRO]**. Single
  inheritance covers the common case; a base method can still be invoked by an
  explicit name if we add that later. Documented divergence.
- **Class variables.** All state is declared fields initialized per instance.
  This removes the shared-mutable-class-variable trap and the shadowing
  asymmetry described in §1.5. Module-level values are the idiom for constants.
- **Name mangling.** No textual rewrite: field names are plain texts and are
  always explicit (`item "x" of this`). A leading `_` is a naming convention
  only. Mangling is hidden context and provides no real privacy **[EXPR]**.
- **Privacy enforcement, descriptors, `__slots__`, metaclasses, `__getattr__`.**
  No enforced data hiding in Python either **[DM]** §3.2.8.2; class bodies stay
  ordinary statement lists.
- **Operator/special methods, `__call__`, inheritance of exception classes.**
  llang problems are string-tagged values (REFERENCE §9); no `__init__` on exceptions.
- **Method assignment / monkey-patching**, because methods live in a closed
  class table, not a mutable instance dict (avoids the "function on instance is
  not bound" trap **[DM]** §3.2.8.2).
- **Synonyms?** In keeping with DESIGN §11 we may later accept `define class`
  and `define a class`, `inherits from`/`extends`, but every spelling must
  produce a byte-identical canonical AST.

### 2.6 Runtime representation sketch (interpreter-facing)

Add a host `Instance` value with `class_obj` (a `ClassValue` holding name, base,
declared fields, and method table) and `fields` (an insertion-ordered Python
`dict`). Extend `_eval_index` and `_exec_set_item` to accept `Instance` in
addition to list/map/text; extend `_call` with a special branch for names
starting `new ` (mirroring the existing `apply` special case in
`interpreter.py`) and a new `_exec_ask` for `MethodCall`. No change to `Env` is
needed for class scope: method bodies run in `Env(parent=definition_env)` with
`this` bound as an ordinary parameter, so decision #12 holds automatically.

---

## 3. Verification plan

**Oracle.** A Python harness executes the equivalent program and records a
normalized trace of field reads/writes, method results, and error categories.
Because llang is intentionally a re-expression of Python semantics **[§10]**,
the trace should be identical except for the documented divergences in §2.5.

**A. Semantic matrix tests (one test per §1 rule).** Map each llang construct to
its Python equivalent and assert the same trace:

| Python | llang |
|---|---|
| `p = Point(1,2); p.x` | `set p to call new Point with x = 1, y = 2` / `item "x" of p` |
| `p.x = 5` | `set item "x" of p to 5` |
| `d.speak("woof")` | `ask d to speak with phrase = "woof"` |
| `Dog.__mro__` (single chain) | base-chain lookup in §2.3.4 |
| base method dispatching to override | `ask` from a base-defined method |
| `hasattr`/`getattr` of a missing field | `missing_field` problem |
| `__init__` returning non-`None` | `bad_constructor` problem |

**B. Golden programs from the docs.** Port the canonical tutorial examples that
motivated **[§10]**: `Dog` with per-instance `tricks` list (assert the list is
**not** shared — the documented class-variable trap), `inst.x = inst.x + 1`
shadowing behavior (in llang: no class variable exists, so assert only the
instance field changes), an override called through a base method (virtual
dispatch), and a multi-level `Animal → Dog → Puppy` lookup chain.

**C. Scope and binding tests.** Assert a class-body name is invisible in a method
(decision #12) and produces `Undefined name '…'`, not a silent read; assert
omitting `this` and supplying `this` explicitly are both rejected; assert
forgetting `this` in another parameter position does not bind the receiver.

**D. Aliasing and mutation tests.** `set d2 to d` then mutate `d2`: assert `d`
observes the change (Python object-reference semantics, REFERENCE §3); assert
constructor field maps are fresh per instance (no shared defaults).

**E. Diagnostic tests.** Exact messages and source positions for every row of
§2.4; parse errors for missing `end class`/`end method`, duplicate fields,
unknown base, two bases; synonym-equivalence AST tests if aliases are added.

**F. Structural / linter tests.** `lint_source` warns on a field text that is not
declared by any visible class where statically knowable, and on a method missing
`this`; no warning for the leading-`_` privacy convention.

**G. Interpreter unit + regression.** One test per new canonical node
(`ClassDef`, `MethodDef`, `MethodCall`, extended `Index`/`SetItem`); a test that
`ask` inside a loop obeys the 100 000-iteration guard; a test that a `give back`
from a method does not escape as "'give back' used outside a function"; and a
test that an unhandled problem from a method renders with the `ask` position.
Store fixtures under `tests/classes/` and run via `run_source`.

**H. Documentation gate.** Every deliberate omission in §2.5 must be listed in
REFERENCE §9 "Divergences from Python", and §1.1–§1.7 must each map to at least
one passing test or an explicit note in that section.
