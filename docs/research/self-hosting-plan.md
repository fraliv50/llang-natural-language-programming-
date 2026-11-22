# Self-Hosting Plan for llang

**Status:** forward-looking design document. Nothing in this file is shipped today.
**Authority:** every claim below was checked against `src/llang/lexer.py`, `parser.py`,
`ast_nodes.py`, `interpreter.py`, `synonyms.py`, `errors.py`, `converter.py`, the
language docs (`docs/GRAMMAR.md`, `docs/REFERENCE.md`, `docs/METHOD.md`), the
grounding matrix (`docs/research/python-semantics.md`), and the tooling
(`tools/port.py`, `src/llang/compiler.py`, `tests/test_converter.py`,
`tests/test_compiler.py`). As everywhere in this project, **the code wins** over
older design prose.

---

## 1. What self-hosting means concretely here

*Self-hosting* means: there exists a program written entirely in llang — call it
`self_host.ll` — whose input is llang source text and whose observable behaviour
(token stream, canonical AST, evaluation, output, diagnostics) is identical to
the current Python implementation (`src/llang/`). Concretely:

1. **`self_host.ll` contains its own front end.** It implements `Lexer.tokenize`
   (`lexer.py:43`), the token helpers and grammar routines of `Parser`
   (`parser.py:14`), the canonical node shapes of `ast_nodes.py`, and the
   evaluator of `Interpreter`/`Env` (`interpreter.py:436`, `:393`) as llang
   functions over maps and lists.
2. **It can run an arbitrary `.ll` program.** `llang self_host.ll program.ll`
   (invoked today through the Python runner `python run.py self_host.ll`, later
   through whatever minimal seed remains) must produce the same
   `Interpreter.output` list and the same final bindings as
   `python run.py program.ll` produces today.
3. **It can read itself.** Feeding `self_host.ll` to `self_host.ll` and then
   running a test program on that second-generation interpreter must give the
   same results — the classic bootstrap fixpoint.
4. **The dependency on Python shrinks to a seed.** Full "no Python anywhere"
   execution is *not* achievable without a compiler (there is no way for llang
   to execute machine code by itself). The achievable target is a **thin host
   seed** supplying only byte-level I/O and the final `show`: file read/write
   and an output sink. Everything that decides *what llang means* lives in
   `self_host.ll`.

This is the final proof of capability because it is the only test that closes
the loop on all of the project's claims at once:

- **Semantic fidelity.** A single wrong truthiness rule, evaluation-order
  detail, or aliasing behaviour (all enumerated in
  `docs/research/python-semantics.md` §0 and encoded in
  `interpreter._eval_binary`, `_arithmetic`, `_equal`) becomes observable the
  moment the llang implementation runs the corpus that the Python one runs.
- **Expressiveness.** The interpreter uses nearly every construct the language
  has (functions, closures, recursion, labeled calls, exception-like signals,
  mutation, modules, file I/O). If llang can express its own interpreter, it can
  express any program in its own accepted corpus.
- **Tooling honesty.** `tools/port.py` (`convert_source` +
  `format_source`) claims a coverage percentage. Porting the interpreter is the
  hardest possible audit of that claim: any construct the converter reports as
  "unsupported" but that the interpreter actually needs becomes a concrete,
  non-hypothetical gap.
- **Method closure.** `docs/METHOD.md` says every surface is grounded in an
  authoritative spec *and an executable oracle*. Self-hosting makes the Python
  implementation itself the oracle for the llang implementation — the strongest
  form of the oracle principle the project already uses for `shlex`/`fnmatch`/
  `textwrap`/`csv`/`json` (`docs/REWRITES.md`, `docs/METHOD.md` §"oracle
  principle").

A useful distinction: **"interpreter-in-llang hosted by Python"** (stage 2–4
below) is already a meaningful milestone and is what most people mean by a
self-hosted interpreter for a tree-walking language. The **fixpoint** (stage 5)
is the stronger claim, and the **WASM target** (§4) is what eventually removes
the Python seed.

---

## 2. Feature-by-feature gap analysis

Reading of the required sources first, so the table is grounded:

- `lexer.py` imports only `dataclasses`, `.errors`, `.synonyms`. **There is no
  `import re` anywhere in the lexer** (or in `parser.py`, `interpreter.py`,
  `ast_nodes.py`, `errors.py`, `synonyms.py`, `converter.py`). Regex appears only
  in `lsp.py` and `packages.py`, which are *not* part of the interpreter core.
  Tokenization in `Lexer.tokenize`/`_word`/`_number`/`_string` is hand-written
  character scanning using `self.src[self.i]`, `len`, `ch in " \t\r\ufeff"`,
  `ch.isdigit()`, `ch.isalpha()`, `ch.isalnum()`, `"0" <= ch <= "9"`, `float()`,
  `int()`, and a small `escapes` dictionary with `.get(ch, ch)`.
- `parser.py` uses generator expressions and `enumerate` in
  `Parser._parse_unary` (`all(self._at_word(word, off) ...)`, line 445), tuple
  slicing and `tuple(...)` in `_match_operator` (`:417–423`), `self.i +=
  len(phrase)`, `", ".join(words)`, and `word or t.text` (operand-returning
  `or`) in `parse_statement` (`:116`).
- `interpreter.py` uses `@property` (`:352`, `:356`, `:360`), `@staticmethod`
  (`:798`), `with open(...) as handle` (`:164`, `:173`), `*`/`**` expansion into
  called functions (`target.fn(**supplied)` at `:862`), tuple unpacking in
  `for name, fn in BUILTINS.items()` (`:439`) and `for fn_name, (fn, required,
  optional) in ...items()` (`:620`), `zip()` (`:840`), `rpartition(" from ")`
  (`:807`), slicing `collection[low:high]` (`:266`), `is None` / `is True` /
  `is False` identity checks (`:155`, `:231`, `:800`), `isinstance(x, (a, b))`
  multi-type checks, `hash()` in `try/except TypeError`, `getattr(node, "pos",
  None)` and `type(node).__name__` reflection, and a dynamic module import
  inside a function (`from .lexer import Lexer` at `:628`).

### Master gap table

Legend — **Yes**: directly expressible in llang today. **Rewrite**: expressible
only after a mechanical source rewrite (no language change required).
**No**: not expressible; a language/runtime feature is missing.

| # | Python construct used by `src/llang/*.py` | Representative site | llang today | Missing feature / required workaround |
|---|---|---|---|---|
| 1 | Strings & escapes | `Lexer._string` (`:97–119`), `quote()` in `converter.py:51` | **Partial (Rewrite)** | Double-quoted strings with `\n \t \r \" \\` work and unknown escapes drop the backslash (`GRAMMAR.md` §Lexical; `lexer.py:101`). Missing: f-strings (item 15), `\uXXXX`/`\x..`, single-quoted/raw/triple strings, `str.startswith`, `str.strip('"')`, `str.rpartition` (`:807`). Workaround: phrase-named builtins `uppercase of`, `trim`, `find in text`, `replace in text`, `split`, `join`, `slice`, plus a small `rpartition` helper built from `find in text` + `slice`. The `escapes` dict itself becomes an llang map (`"n" mapped to "\n"`, …) and `escapes.get(ch, ch)` becomes `if (call contains ...) then ... otherwise ch`. |
| 2 | Char indexing | `Lexer._peek` (`:30`), `_advance` (`:33`), `self.src[self.i+1]` (`:89`), `Interpreter._eval_index` (`:684`) | **Yes** | `item KEY of COLL` on text returns the code point at a non-negative whole index (`REFERENCE.md` §4.4). Negative indices are rejected, but the lexer never uses them. Character-as-integer (`ord`/`chr`) is **not** available; needed only if the port chooses numeric comparisons — instead compare characters with `equals` (text equality works). |
| 3 | Regex | **None in the core** (`lexer.py` has no `import re`) | **N/A** | No regex feature needed. `packages.py`/`lsp.py` use `re`, but they are not part of the self-hosted interpreter. Do not add a regex engine as a prerequisite. |
| 4 | Dataclasses / records | `@dataclass` `Token` (`lexer.py:9`), all 24 AST nodes (`ast_nodes.py`), `SourcePos` (`errors.py:10`, `frozen=True`), `Unsupported`/`ConversionResult` (`converter.py:24,35`) | **No (Rewrite)** | No record/struct type and no attribute syntax. Encode every node as a **map** with string keys (`a map with "kind" mapped to ..., "text" mapped to ...`) and replace `node.pos` with `item "pos" of node`, `node.statements` with `item "statements" of node`. `field(default_factory=list)` becomes an explicit `a list of ...` / `an empty list` at each constructor. A small library of constructor functions (`make_token`, `make_binary`, …) in `lib/ast.ll` is strongly recommended; see §5 P0. |
| 5 | Lists/maps with nested mutation | `Env.values` (`interpreter.py:393`), `target[key] = value` (`:571`, `:577`), `self.modules[alias] = exports` (`:640`), `collection.insert(...)` (`:235`) | **Yes** | `add VALUE to LIST`, `set item KEY of COLL to VALUE`, and reference/aliasing semantics are exactly Python's (`REFERENCE.md` §3, §5.1). Nested mutation through aliases works. `list.insert` is the builtin `insert into`. Mutation of a map inside a function is visible to the caller. |
| 6 | Exceptions | `LangError`/`ParseError`/`RuntimeErrorLang` (`errors.py:19,38,42`), `ReturnSignal`/`BreakSignal`/`ContinueSignal`/`ProblemSignal` (`interpreter.py:365–390`), `try/except` in `_exec_expect` (`:581–595`) and `_call` (`:861–865`), bare `raise` rethrow (`:592`), `finally` (`:593`) | **Partial** | llang has `fail with KIND, "msg"` and `expect … end expect` with handlers, `if nothing went wrong then`, and `always` (`GRAMMAR.md` §statements). Missing: (a) **exception objects with fields** — encode a signal as a map `{"kind":..., "message":..., "pos":...}` and `fail with <kind>` can only carry a *literal* message, not a runtime value; use a single kind plus a map value held in an enclosing variable, or extend `fail` to accept an expression (§5 P0). (b) **rethrow the active problem** (`raise` at `:592`) — no `fail again`. (c) **bind the caught problem to a name** (`except E as e`) — no syntax. (d) typed class hierarchy/inheritance/`raise from` — not needed for these files. (e) `if nothing went wrong then` runs *inside* the protected region (`REFERENCE.md` §5.4), a divergence to preserve deliberately. |
| 7 | First-class functions | `BUILTINS` dict of callables (`:309`), `Builtin.fn` (`:20`), `Function` (`:347`), `call apply with fn = ..., args = ...` (`_call:826–846`) | **Yes** | Functions are values; store them in maps/lists, pass them via `apply`, define nested functions inside blocks (lexical closure through `Env(parent=...)`). Limitation: no anonymous `lambda` (item 18 rewrite) and a function name may not shadow an existing local (`_define_function:643`), so constructor helpers need distinct names. |
| 8 | Recursion | `Interpreter._exec_block` ↔ `_exec_stmt` ↔ `_eval` ↔ `_call` mutual recursion; `Parser.parse_expr` ↔ `_parse_unary` ↔ `_parse_primary`; `Env.get` (:398) | **Yes** | A function can call itself/other functions by name via environment lookup; `give back` returns a value. No tail-call optimization, but the interpreters recurse only as deep as the input AST. |
| 9 | Module imports | `Interpreter._exec_use` (`:607`), `_find_module` (`:597`), dynamic `from .lexer import Lexer` inside `_exec_use` (`:628`), `converter._import` (`:520`) | **Partial** | `use the X module` + `call f from X with ...` exist and are resolved by the *host* interpreter from `lib/` (`REFERENCE.md` §7b). Missing: `use` with a **computed** module name/path (grammar requires a literal NAME at `parser.py:205`), and re-entrancy — a self-hosted interpreter must read source (`read text from`), tokenize and parse it *itself*. For one-file `self_host.ll` this is moot; for a multi-module port it is a P1 gap. |
| 10 | File I/O | `_b_read_file`/`_b_write_file` (`:160–175`), `open(..., encoding="utf-8")`, `path.read_text(encoding="utf-8-sig")` (`:627`), `__init__.py:26` | **Partial (Rewrite)** | Language-level builtins `read text from` / `write text to` exist and use UTF-8. Missing: `with` context-manager syntax (`with open(...) as h`), streaming reads, and — critically — a **host I/O primitive available to the self-hosted interpreter**. In the Python-hosted stages, expose `read text from`/`write text to` as foreign/builtin values; in the WASM endgame they become imported host functions (§4). |
| 11 | Integer vs float types | `_is_number` (`:412`), `isinstance(places, int)` (`:155`), `isinstance(index, bool)` (`:231`, `:567`), `int()`/`float()` in `Lexer._number` (`:94`) | **No** | llang has one `number` type and `is a number` (excludes bool). It cannot ask "is this a whole number / an int rather than a float" or "is this a boolean". Workaround today: `call rounded with value = x, places = 0` compared with `x` approximates wholeness, but it is not exact for floats. Add predicates `is a whole number` and `is a boolean` (§5 P0); identity-style `x equals true`/`x equals false` already discriminate booleans because `_equal` guards them (`:798–803`). |
| 12 | `is` identity | `value is None` / `is True` / `is False` / `is not None` (`:155`, `:231`, `:719`, `:800`) | **Partial** | `x is nothing` covers `is None`; `not (x is nothing)` covers `is not None`. `x equals true` / `x equals false` correctly emulate `is True`/`is False` thanks to the boolean-only-equality guard in `_equal`. Missing: general object identity (`a is b` for lists/functions/maps). Not needed by these files, but document that `equals` is value equality, never identity (`REFERENCE.md` §9.3). |
| 13 | Slicing | `words[:len(phrase)]` (`parser.py:421`), `collection[low:high]` (`interpreter.py:266`), `expression[1:-1]` (`converter.py:355`) | **Yes** | `call slice with collection = ..., start = ..., end = ...` exists with Python-style clipping and `nothing` = omitted (`GRAMMAR.md` builtins; `_b_slice:245`). Negative step is unsupported, but none of the core files use it. Note `_b_slice` implements the negative-index clipping itself, so the builtin matches Python semantics for the cases used. |
| 14 | Comprehensions / genexprs | `[Path(p) for p in ...]` (`:445`), `all(... for item in items)` (`:111`, `:129`), `separator.join(_render(item) for item in items)` (`:92`), `enumerate(...)` generator (`parser.py:445`) | **No (Rewrite)** | No comprehension or generator-expression syntax. `converter._list_comprehension` (`:319`) already demonstrates the rewrite for simple list comprehensions: `set acc to an empty list` → `repeat for each …` → `add … to acc`. Generator expressions inside `all`/`any`/`join`/`sum` need named helper functions or inline loops with early exit. Additive but not blocking (§5 P1). |
| 15 | f-strings / interpolation | `Token.__repr__` (`:17`), nearly every `LangError`/`RuntimeErrorLang` message, `converter` emit strings (`:71–96`, `:293`) | **No (Rewrite)** | No f-strings (`REFERENCE.md` §2, §9.15). Rewrite as `call join with items = (a list of <literal>, (call to text with value = x), <literal>), separator = ""` — or add a compact interpolation form. `converter.py:246–255` already lowers Python `JoinedStr` to `call to text` plus `plus` concatenation, which is a usable pattern. **High impact** because diagnostics are built this way everywhere (§5 P0). |
| 16 | Decorators | `@dataclass`, `@dataclass(frozen=True)` (`errors.py:10`), `@property` (`interpreter.py:352,356,360`), `@staticmethod` (`lexer.py:79`, `interpreter.py:798`) | **No (Rewrite)** | No decorators or metaprogramming. Eliminate by refactoring: dataclasses → map constructors (item 4); `@property` → ordinary functions (`call function name of obj`); `@staticmethod` → plain global functions. Do **not** add decorators to llang for this (§5 P2). |
| 17 | `*args` / `**kwargs` / defaults | `_b_extreme(want_minimum, **kw)` (`:125`), `fn(**supplied)` (`:862`), `_shell_run(command, directory=None, timeout=30)` (`foreign.py:34`) | **No (Rewrite)** | Calls are labeled-only, all parameters mandatory; no variadics, no defaults (`REFERENCE.md` §9.10). `apply` (`:826`) covers positional-list dispatch, and optional labels exist for *builtins* (`BUILTIN_SPECS`, `:272`) but not for user functions. Workaround: pass an explicit options map (`an empty map` + `set item`) as a single labeled parameter. Converter already reports these as unsupported (`converter.py:511–512`). |
| 18 | Anonymous functions (`lambda`) | `OPERATOR_PHRASES.sort(key=lambda pair: -len(pair[0]))` (`synonyms.py:32`), `max(..., key=lambda ...)` (`packages.py:306`, not core) | **No (Rewrite)** | No lambda. `synonyms.py`'s sort is a one-off initialization: precompute the sorted list in source order, or define a named `phrase_length` function. Low impact in the core. |
| 19 | Classes / instances / methods / `self` | `class Lexer`, `class Parser`, `class Interpreter`, `class Env`, `class Builtin`, `class Function`, signal/exception classes | **No (Rewrite)** | No classes, attribute access, bound methods, or inheritance. **The biggest structural gap.** Encode an object as a map of fields plus functions that take the object explicitly as their first parameter: `define function tokenize taking self … set item "i" of self to …`. `Lexer._pos` → `call lexer_pos with self = L`; `Interpreter._eval` dispatch → `call eval with self = I, node = N, env = E`. This works because maps are mutable and functions are first-class, but it is verbose and error-prone; see §5 P0 for the record/attribute decision. No inheritance is needed for these files, so a minimal record type suffices. |
| 20 | Generators (`yield`) | **None in the core** — only generator *expressions* (item 14). `yield` appears in `lsp.py:40,42`, which is out of scope | **N/A** | Do not add generators as a prerequisite. If later desired, `docs/research/python-semantics.md` §12 requires an explicit `on demand` marker; it is irrelevant to stage 1–5. |
| 21 | Additional discovered constructs | `with open` (item 10), `zip()` (`:840`), `enumerate()` (`parser.py:445`), `hash()` + `try/except TypeError` (`:573–576`, `:671–674`), `getattr`/`type().__name__` (`:504`, `:681`), `super().__init__` (`errors.py:27`, `interpreter.py:388`), dynamic import (`:628`), set union `\|` (`synonyms.py:54`), `set`/tuple types, `in` on sets/lists/maps | **Mostly Rewrite** | `zip`/`enumerate` → index loops using `the length of`; `hash()` → not expressible (drop the explicit hashability check and rely on `set item` semantics, or add an `is hashable` predicate); `getattr`/`type` reflection → replace the `isinstance` dispatch chain with a `kind` field on every map-encoded node (`item "kind" of node`), which is actually *cleaner* than the Python code. `super().__init__` disappears once exceptions become maps. Set union is a one-time constant build in `synonyms.py:54` and can be precomputed in source. |

### Net assessment of the analysis

- **Trivially portable:** char indexing, list/map nested mutation, recursion,
  first-class functions, slicing, `is nothing`/boolean identity.
- **Portable with mechanical rewrites:** strings/f-strings, comprehensions,
  lambdas, decorators, `*args`/defaults, classes → maps with explicit `self`,
  context managers, reflection via a `kind` field.
- **True language gaps that should be fixed rather than worked around:** a
  record/attribute mechanism (or a committed map-encoding convention), a
  **rethrow** and **problem binding** form for `expect`, integer/boolean type
  predicates, and (if multi-module) computed imports. These are collected and
  prioritized in §5.
- **Explicitly not gaps:** regex and `yield` generators are absent from the
  interpreter core; no work is needed there.

---

## 3. Staged plan

The guiding rule from `docs/METHOD.md`: find an authoritative spec **and an
executable oracle** before building. Here the spec is `docs/REFERENCE.md` +
`docs/research/python-semantics.md` and the oracle is the existing Python
implementation. Move in dependency order so each stage is testable before the
next begins.

### Stage 0 — freeze the data contract (no porting yet)

1. Decide the map encoding for AST nodes and runtime objects (§5 P0). Write it
   down as `docs/SEMANTIC-DECISIONS.md` entry: every node map carries a
   `"kind"` string and fixed keys, e.g.
   `{"kind":"Binary","op":"ADD","left":<node>,"right":<node>,"pos":<pos>}`.
   The `"kind"` field replaces `isinstance(node, Binary)` dispatch throughout
   `interpreter._exec_stmt`/`_eval` (`:467`, `:654`), which is the llang
   equivalent of the Python dispatch chain.
2. Add only the language prerequisites that unblock the port: a record helper
   library `lib/ast.ll` (constructor/accessor functions over maps), an
   integer/boolean predicate, and an `expect` rethrow/binding form.
3. Gate: a small `.ll` program can build, read, mutate and render every node
   shape, with a golden test comparing the rendered map to a Python-side dump.

### Stage 1 — data model (`ast_nodes.py`, `errors.py`, `synonyms.py`)

Port first because everything else depends on it and it has no behaviour to get
wrong.

- `lib/ast.ll`: constructors `make_program`, `make_token`, `make_literal`,
  `make_binary`, … one per class in `ast_nodes.py:15–189`, plus `make_source_pos`
  and `make_error` from `errors.py:10,19`.
- `lib/synonyms.ll`: port `OPERATOR_PHRASES`, `POSTFIX_PREDICATES`
  (`parser.py:426`), `RESERVED` (`synonyms.py:39`) as literal lists/maps, in the
  **already-sorted** order (`OPERATOR_PHRASES.sort(key=…)` at `synonyms.py:32`
  is precomputed in source).
- `tools/port.py` first draft: `python tools/port.py src/llang/ast_nodes.py -o drafts/ast.ll --report drafts/ast.report.txt`. Expect near-total failure (every class → unsupported); use the generated skeleton only as a checklist of fields.

**Verify:** round-trip golden node dumps (Stage 0 gate) plus synonym table
equality — the sorted phrase list rendered from llang must byte-match the
Python `OPERATOR_PHRASES`.

### Stage 2 — lexer (`lexer.py`)

Port next: it is a pure function of its input, has no dependency on the AST, and
`errors.py` is already available.

- `define function tokenize taking source` implementing the loop of
  `Lexer.tokenize` (`:43–69`). State (`self.i`, `self.line`, `self.col`) lives in
  a map `self` passed explicitly; `self.src[self.i]` → `item i of source`;
  `_advance` (`:33`) becomes a helper that returns `(char, new_self)` because
  llang has no multiple return values — carry the updated `self` map back via
  `set item "i" of self to ...` on the shared map (mutation is visible through
  aliases, per `REFERENCE.md` §3).
- `ch in " \t\r\ufeff"` → `call contains with collection = " \t\r\ufeff", value = ch`.
  `ch.isdigit()` / `isalpha()` / `isalnum()` → small `is_digit`/`is_alpha`/
  `is_alnum` helpers using lexicographic `is at least`/`is at most` comparisons
  and `is a letter`-style ranges (Unicode `isalpha` is a known divergence —
  document it; `REFERENCE.md` §2).
- `_string` (`:97–119`): port the `escapes` map and the `escapes.get(ch, ch)`
  fallback exactly; this is the highest-risk routine because a single escape
  mismatch corrupts every string in every later stage.
- `tools/port.py` draft: `python tools/port.py src/llang/lexer.py -o drafts/lexer.ll --report drafts/lexer.report.txt`. Expect unsupported: dataclass, class methods, f-string in `__repr__`, `staticmethod`; the *tokenizing loop itself* maps well to `repeat while`/`if`/`set item`.

**Verify:** token-stream differential harness (§6 Layer 1) over the golden
corpus and fuzzed strings. **Gate: zero token mismatches** before writing the
parser.

### Stage 3 — parser (`parser.py`)

- Port the token helpers (`_tok`, `_at_word`, `_accept_word`, `_expect_word`,
  `_accept_punct`, `_expect_punct`, `_expect_name`, `_skip_newlines`,
  `_end_statement`, `:20–68`) onto a `self` map with `"tokens"` and `"i"`.
- Port `parse_program`/`parse_statement` (`:71–119`) and each `_parse_*`
  routine in source order. Use the node constructors from Stage 1.
- Rewrite the two tricky idioms explicitly:
  - `_match_operator` (`:414–424`): iterate `OPERATOR_PHRASES`, take
    `call slice with collection = words, start = 0, end = the length of phrase`,
    compare with the phrase via `equals` (list equality is structural —
    `REFERENCE.md` §3), advance `self.i` by `the length of phrase`.
  - `_parse_unary` postfix loop (`:442–452`): replace the generator
    `all(... for offset, word in enumerate(phrase))` with a `repeat for each`
    loop over phrase offsets using the index built from `the length of`.
- Keep the `pos = self._tok().pos` bookkeeping; the differential AST dump
  includes positions so this is checked.
- `tools/port.py` draft: `python tools/port.py src/llang/parser.py -o drafts/parser.ll --report drafts/parser.report.txt`.

**Verify:** canonical AST differential harness (§6 Layer 2) — parse the same
corpus with Python `Parser(Lexer(src).tokenize())` and with the llang parser,
normalize both to text, compare byte for byte. **Gate: zero AST mismatches.**

### Stage 4 — evaluator (`interpreter.py` core)

The largest stage. Split it further so each sub-stage has its own oracle:

1. **Runtime primitives:** `Env` (`get`/`set`/`has_local`, `:393–410`) as a map
   with `"parent"` and `"values"`; `Function`/`Builtin` (`:17`, `:347`);
   `_is_number`, `_truthy`, `_render` (`:412–433`). `_render` is a good early
   target because its output is directly comparable via `show`.
2. **Expression evaluator:** `_eval` and its helpers (`_eval_index`,
   `_eval_length`, `_eval_unary`, `_eval_binary`, `_arithmetic`, `_order`,
   `_equal`, `:654–803`). Dispatch on `item "kind" of node` instead of
   `isinstance`. Preserve short-circuit/operand-returning `and`/`or`
   (`:731–737`) and the boolean equality guard (`:798–803`).
3. **Statement executor:** `_exec_block`, `_exec_stmt`, `_exec_if`,
   `_exec_repeat`, `_exec_for_each` (snapshot semantics!), `_exec_add_to`,
   `_exec_set_item`, `:463–579`. The 100 000-iteration guard (`:519`, `:543`)
   must be reproduced or deliberately waived with a documented decision.
4. **Calls and control signals:** `_call` (`:805–895`) including module-qualified
   names, label validation, `apply`, and `ReturnSignal`/`BreakSignal`/
   `ContinueSignal`/`ProblemSignal`; `_exec_expect` (`:581–595`) including
   `always` and rethrow. This is where the §5 P0 exception extensions are used.
5. **Builtins:** initially **do not port** `_b_*` functions. Expose them from
   the Python host as foreign/builtin values (the seed in §1.4). Port them to
   llang one group at a time (conversions → collections → text → files),
   re-running the full oracle after each group. Several already have pure-llang
   equivalents in `lib/` (`lib/lists.ll`, `lib/text.ll`, `lib/math.ll`), so this
   is largely wiring.

`tools/port.py` draft: `python tools/port.py src/llang/interpreter.py -o drafts/interpreter.ll --report drafts/interpreter.report.txt`. The report will be long — treat it as the worklist; expect unsupported classes, `with open`, `**kw`, f-strings, generator expressions, `zip`, slicing, `isinstance`/`getattr`/`type`, dynamic import.

**Verify:** behavioural differential harness (§6 Layer 3) over `examples/*.ll`,
`lib/*.ll`, `tests/fixtures`, and the rewrite corpus. **Gate: zero output/error
mismatches** before attempting the fixpoint.

### Stage 5 — module system, file I/O, and the fixpoint

- Port `_find_module`/`_exec_use` (`:597–641`) so the llang interpreter can load
  `.ll` modules itself: `read text from` → `call tokenize` → `call parse_program`
  → `call exec_block`. This needs the computed-path import of §5 P1 if modules
  remain separate files; alternatively keep `self_host.ll` as one file and treat
  `use` as a builtin the host seed resolves.
- Run `python run.py self_host.ll program.ll` for every corpus program, then
  **substitute**: replace each remaining host-provided helper (file read,
  output sink, numeric builtins) with its llang counterpart one at a time,
  re-running the full oracle after each swap. This is the "pull yourself up by
  the bootstraps" ladder; never swap more than one component per gate.
- Final fixpoint: `python run.py self_host.ll self_host.ll` must produce an
  interpreter that still passes the corpus.

### Stage 6 — converter and compiler (optional, last)

`converter.py` is a *Python-source* front end, not part of the runtime loop;
porting it is unnecessary for self-hosting but would close the tooling loop.
`compiler.py` is addressed in §4. Both depend on the full value model and should
wait until Stage 5 is green.

### How `tools/port.py` fits into every stage

`tools/port.py:21–58` calls `convert_source` (`converter.py:552`) then
`format_source`, writes the `.ll` and prints a coverage report with one line per
unsupported construct (`tools/port.py:41–54`). Use it as a **draft generator and
worklist**, never as a finisher:

- `python tools/port.py <file.py> -o drafts/<name>.ll --report drafts/<name>.report.txt`
- The `coverage` percentage (`converter.py:42–48`) measures *nodes converted*,
  not *semantics correct*; treat 100% coverage as "nothing left to hand-fix",
  not "correct".
- The formatter may reject generated source (`tools/port.py:34–36`); a
  `WARNING: formatter rejected generated source` means the draft is not even
  parseable and must be rewritten by hand.
- Because the converter deliberately maps `is None` → `is nothing`, f-strings →
  `to text` + `plus`, `try` → `expect`, slices → `call slice`, and calls to
  known functions to labeled form (`converter.py:196–228`, `:246–255`,
  `:467–484`), its output is a useful *starting skeleton* whose remaining
  report items are exactly the rewrites enumerated in §2.

---

## 4. Bootstrap sequence and the WASM backend

### The ladder, without a compiler

There is no llang compiler that can produce a standalone executable today, so
bootstrap is a **sequence of hosted interpretations**, each verified, with the
host shrinking at every step:

```
R0  Python:  run.py                     runs  program.ll        (today)
R1  Python:  run.py                     runs  self_host.ll      with program.ll as data
           (self_host.ll implemented in llang; its builtins/files still host-provided)
R2  Python:  run.py                     runs  self_host.ll      running self_host.ll
           (fixpoint: the llang implementation executes an identical copy of itself)
R3  Python:  run.py + WASM-compiled seed (see below) — auxiliary oracle / eventual seed
R4  No Python semantics: WASM module provides the entire interpreter,
    with only host-imported I/O (the "thin seed" of §1.4)
```

Key properties:

- At **R1** the Python interpreter is still the *engine*; llang code is the
  *program*. This is the first honest "interpreter written in llang".
- At **R2** the engine and the program are both llang; Python only supplies the
  outer `run.py` loop plus file/input primitives. All semantic decisions —
  truthiness, evaluation order, dispatch, errors — are made by llang code.
- The swap from R1→R2 is done **one component at a time** (lexer first, then
  parser, then evaluator, then builtins) with a full oracle run after each,
  exactly as in Stage 5. There is never a moment where an unverified component
  is trusted.
- The "thin seed" at R4 is unavoidable in principle: a language cannot provide
  its own byte-level I/O or its own execution loop without a host. The goal is
  to minimize the seed, not imagine it away.

### Where the WASM backend fits

`src/llang/compiler.py` compiles a **subset** of the canonical AST to a valid
WebAssembly 1.0 binary: all values are i32; only integer literals, variables,
arithmetic/comparison/boolean ops, user functions, `if`/`while`/`break`/
`continue`/`return` are supported; text, lists, maps, builtins and foreign
calls are reported unsupported (`compiler.py:1–13`, `docs/REWRITES.md` §6).
`tests/test_compiler.py:20–33` executes emitted `.wasm` under Node via
`tools/run_wasm.js` and compares results.

This gives the WASM backend **three distinct roles**, none of which is "the
first bootstrap step":

1. **Independent oracle for the numeric core (available now).** For integer
   programs, there are three implementations: the Python interpreter, the
   llang interpreter, and compiled WASM executed by Node. Disagreement among
   the three localizes bugs fast. This is the same pattern `METHOD.md` §oracle
   describes for recovering the WASM compiler's correctness with Node.
2. **The eventual compiler that removes the Python seed (long term).** Only
   once a WASM backend supports the **full value model** — strings, lists,
   maps, closures, builtins, exception-like control flow — plus a heap/GC
   design and imported host functions for I/O, can `self_host.ll` be compiled
   to a `.wasm` that runs the corpus without Python. That is the real
   "self-hosting with a compiler" milestone, and it is strictly downstream of
   Stages 1–5.
3. **NOT a stage-0 accelerator.** Today's i32-only compiler cannot even compile
   the lexer, because `item i of source` returns a character (text) and the
   token stream is a list of maps. Do not plan on using WASM to "compile the
   bootstrap interpreter" until role 2 is achieved.

Ordering therefore: **Python interpreter → llang interpreter (hosted) →
fixpoint → extend WASM backend → compile the self-hosted interpreter to WASM →
run with only I/O imports.**

---

## 5. Honest assessment — what must be added, prioritized by impact

The language can already express a surprising amount of the interpreter
(functions, recursion, mutation, labeled calls, `apply`, slices, `is nothing`).
The blockers are concentrated in a few areas.

| Priority | Item | Why it blocks / helps | Concrete proposal |
|---|---|---|---|
| **P0-1** | **Record/object representation with attribute-style access** (gap 4, 19) | 25+ dataclasses/classes in `ast_nodes.py`, `lexer.py`, `interpreter.py` have no native form; map-encoding everything works but `item "op" of node` everywhere is verbose and easy to mistype. | Minimum: commit to the map convention + `lib/ast.ll` constructors/accessors (no language change). Better: add a small record type `define a record Token with kind, text, pos, value` giving `item "kind" of t`-equivalent syntax and a `kind` tag for dispatch. Decide in `SEMANTIC-DECISIONS.md` before Stage 1. |
| **P0-2** | **`expect` rethrow + problem binding** (gap 6) | `Interpreter._exec_expect` re-raises unmatched problems (`interpreter.py:591–592`); `_call` wraps host errors; `run` converts signals to diagnostics. Without a rethrow and a way to carry a runtime message/kind, control-flow signals cannot be faithfully ported. | Add `fail again` (rethrow the active problem) and `if a problem of kind K occurs as p then` (bind the problem map to `p`). Keep the documented `if nothing went wrong then` and `always` semantics unchanged. |
| **P0-3** | **Integer / boolean type predicates** (gap 11) | `_b_rounded`, `_b_insert`, `_b_slice`, `_eval_index` all distinguish whole numbers from floats and reject booleans; llang cannot. | Add `is a whole number` (int but not bool/float) and `is a boolean`. Keep `is a number` as-is. `is nothing` and `equals true/false` already cover the singleton cases. |
| **P0-4** | **String interpolation or disciplined `join`+`to text` convention** (gap 15) | Diagnostics and converter output are built from f-strings throughout; without this, every message is a long `call join` expression. | Either add a minimal interpolation form, or (cheaper) standardize a `lib/fmt.ll` helper `concatenate` over lists of values and use it everywhere. Converter already lowers `JoinedStr`; reuse that lowering. |
| **P1-1** | **Comprehension lowering helpers** (gap 14) | Many `all(... for ...)` / `join(... for ...)` idioms in builtins; rewriting by hand is mechanical but error-prone. | Library-level `all_satisfy`, `any_satisfy`, `map_collect` taking a function value; optionally native comprehension syntax later. |
| **P1-2** | **Computed `use` / dynamic module path** (gap 9) | Needed only if the port is split across multiple `.ll` files; a single-file `self_host.ll` avoids it. | Allow `use the module named <expr>` or a `call load module with path = ...` host/foreign primitive. |
| **P1-3** | **Stable foreign I/O primitive for the seed** (gap 10) | The self-hosted interpreter must read source files and emit output. | Formalize `read text from`/`write text to` as the seed contract; keep `OSError` handling deliberate (`REFERENCE.md` §6.5 divergence). |
| **P2-1** | Lambdas / anonymous functions (gap 18) | Only `synonyms.py:32` uses one in the core. | Named helper function; do not add to language. |
| **P2-2** | Decorators / property / staticmethod (gap 16) | Used but eliminable by refactoring. | Rewrite; explicitly **do not** add decorators to llang. |
| **P2-3** | Default / variadic parameters (gap 17) | Used in host-facing builtins, not in the semantic core. | Use an options map or builtin optional-label specs; `apply` covers positional dispatch. |
| **P2-4** | Slice steps, generators, regex, `with`, `hash()` reflection | Confirmed absent or non-essential in the interpreter core. | Do not build. Document as out of scope. |

**Blunt bottom line:** with the four P0 items in place, self-hosting is
*feasible* — verbose, because classes become maps with explicit `self`, but
mechanically achievable. Without P0-1 and P0-2 in particular, a faithful port
is effectively impossible (you would be simulating objects and rethrows with
ad-hoc conventions that no oracle can validate). The converter's current
coverage report on `interpreter.py` would be low; that number is a symptom, not
the goal.

---

## 6. Verification oracle — proving each staged port correct

`docs/METHOD.md` §"oracle principle" makes the rule explicit: authoritative
spec **plus executable oracle**. For self-hosting, the Python implementation is
the executable oracle, and the ground truth is "what the Python runner does to
the same llang source." Build one harness with four layers and a strict stage
gate.

### Oracle ground truth

The reference behaviour of program `P` is captured by the current public API
(`src/llang/__init__.py:17–23`):

```python
interp = run_source(P)          # Python Lexer -> Parser -> Interpreter
golden_output = interp.output   # list of rendered lines
golden_error  = None or (kind, message, line, column)
```

For error cases use `LangError.render()` (`errors.py:29–35`) normalized to
`(message, line, column)`. Any llang-implementation result that differs in
output lines, error kind/message/position, or final bindings is a mismatch.

### Layer 1 — token-stream differential (gates Stage 2)

- For each source string `s` in the corpus, serialize Python
  `Lexer(s).tokenize()` to a canonical line per token:
  `kind | text | line | column | rendered(value)` (using `_render` semantics
  from `interpreter.py:420` so numbers/bools/nothing render identically).
- Serialize the llang lexer's token list to the same format. Compare as sorted
  line lists (or exact order — exact order is stronger; use it).
- Corpus: every `.ll` file in `examples/`, `lib/`, `docs/` examples,
  `tools/fixtures/sample.ll`, plus randomized strings from the fuzz generator
  (`tools/fuzz_semantics.py` pattern, `tests/test_fuzz_semantics.py`) covering
  all escape sequences and Unicode edge cases.
- **Stage gate: 0 mismatches.**

### Layer 2 — canonical AST differential (gates Stage 3)

- Serialize Python `Parser(Lexer(s).tokenize()).parse_program()` to a stable
  dump: depth-first, node `kind` first, then fields in the fixed order of
  `ast_nodes.py`, then `pos` last. Reuse the `pos`-last convention documented at
  `ast_nodes.py:5–8`.
- Serialize the llang parser's map-encoded AST with the same dumper. Compare
  byte for byte. Because every synonym normalizes to one canonical node
  (`REFERENCE.md` §1, `METHOD.md` step 4), a formatter pass on the source can
  be used to remove synonym noise before comparison.
- Include one fixture per statement/expression form in `docs/GRAMMAR.md`, plus
  the "expected error" cases from `REFERENCE.md` §7 table (e.g. missing
  `end if`, reserved word as name) and compare normalized error tuples too.
- **Stage gate: 0 mismatches.**

### Layer 3 — behavioural differential (gates Stage 4)

- Golden corpus: `examples/*.ll`, `lib/*.ll` (public stdlib), `tools/fixtures/`,
  the end-to-end tests in `tests/test_end_to_end.py`, and the rewrite corpus
  from `docs/REWRITES.md` (`shlex`, `fnmatch`, `textwrap`, `csv`, `json` ports).
- For each program, run twice:
  1. `run_source(P)` under Python → `golden_output`, `golden_error`.
  2. the llang interpreter under development → its `output` and error.
- Compare output arrays exactly and final global bindings (rendered) exactly.
- For randomized programs, reuse `tools/fuzz_semantics.py` to generate
  expression/statement programs and compare Python vs llang evaluation — the
  same strategy that already gives the project property-based semantic tests.
- Converter cross-check: reuse `tests/test_converter.py:18–31` `roundtrip()`
  (Python source → `.ll` → both interpreters) to exercise a much wider program
  space automatically.
- **Stage gate: 0 mismatches** before Stage 5.

### Layer 4 — fixpoint and substitution checks (gates Stage 5)

- **Fixpoint:** run `self_host.ll` on `self_host.ll`, then run the resulting
  second-generation interpreter on the entire corpus; outputs must equal the
  Python golden outputs byte for byte.
- **One-swap rule:** every time a host-provided helper is replaced by its llang
  implementation (lexer, parser, evaluator, each builtin group, file I/O),
  re-run Layers 1–4. A swap is accepted only if the full suite stays green.
  This is what prevents "bootstrap by assertion."
- **Port report manifest:** keep the `--report` files from `tools/port.py` for
  each module under `docs/research/bootstrap-reports/`. A stage is complete
  only when every `unsupported` entry is either (a) removed by a hand rewrite
  documented in the manifest, or (b) covered by a new language feature with a
  `SEMANTIC-DECISIONS.md` entry. The count must reach zero.

### Independent third oracle (the WASM leg)

For integer/function programs only, compile the same source with
`compile_source` (`compiler.py`) and execute under Node as in
`tests/test_compiler.py:20–33`. Require Python-interpreter == llang-interpreter
== WASM-result. This does not cover strings/maps, but it independently
validates the arithmetic, comparison, control-flow, and function-call core that
the evaluator shares.

### Why this is a real proof

The oracle is not a hand-written expectation list that could share a bug with
the port; it is the *existing, independently written Python implementation*
that the project already trusts to run all of its examples and tests. If a
staged port matches it on token streams, ASTs, outputs, diagnostics, and the
fixpoint — with zero mismatches and a clean port manifest — then, by the same
standard the project already applies to its rewrites and compiler, the
self-hosted interpreter is correct for the entire accepted corpus. That is the
sense in which this is the final proof of capability.

## Implementation status

Stage 0 (data contract) and Stage 2 (lexer) are implemented:
`lib/ast_contract.ll` and `lib/llang_lexer.ll`. The llang-written tokenizer is
verified token-for-token against the Python bootstrap lexer by
`tools/compare_lexer.py` (14 sources, 0 mismatches). Stage 1 (data model) and
Stage 3 (parser) remain.

Stage 0 (data contract) is implemented in `lib/ast_contract.ll` and verified by
`tests/test_ast_contract.py`. It provides llang-native token and AST node maps,
field accessors, structural equality, digests, and token rendering. Automatic
first-draft conversions of the interpreter modules are kept as diagnostic
artifacts in `tools/selfhost/` (see its README). Stages 1–5 remain to be built.
