# llang Standard Library — Design Proposal

*Status: proposal. Grounded in `docs/DESIGN.md`, `docs/GRAMMAR.md`, `docs/SEMANTIC-DECISIONS.md`, `docs/research/python-semantics.md`, and the current implementation (`lexer.py`, `parser.py`, `interpreter.py`, `synonyms.py`). Every builtin below is a thin, explicitly-documented re-expression of a Python call — no new semantics are invented.*

---

## 0. What exists today (hard constraints on the stdlib)

Facts read directly from the code, not assumed:

| Fact | Consequence for stdlib |
|---|---|
| `call := "call" name ["with" arg_list]`, and `name = self._expect_name()` — a **single** non-reserved `WORD` | A true multi-word surface name (`the length of`) **cannot** be parsed today. Must use G1 or G2 (see §2). |
| `arg_list := name "=" expr`, and labels go through `_expect_name()` → `RESERVED` rejected | Parameter labels may not be `to`, `with`, `as`, `end`, `call`, `and`, `or`, `not`, `a`, … (§4). |
| Argument values are parsed with `parse_expr()` | The value expression is **greedy**: `call f with x = a plus 1` passes `a plus 1` as `x`. To operate on a call result, parenthesize: `set n to (call the length of with text = s) plus 1`. Document this; no grammar change needed. |
| `Call` is produced both as a statement (`parse_statement`) and as a `primary` expression | Every builtin is usable as a statement **and** nested inside expressions, for free. |
| No builtin scope exists. `Interpreter.global_env` is a plain `Env`; `Env.get` walks local → parent and then raises `Undefined name` | Need runtime change R1 (§6): prepopulate a builtin namespace and add a native-callable type. |
| Runtime types today: `int`, `float`, `str`, `bool`, `None`, `Function`. **No list, map, tuple, set, bytes, index syntax, or container literals.** `punct := "(" \| ")" \| "," \| "="` | All list/map builtins are **phase-gated** behind G4. They are specified here but cannot ship in v1. |
| `ADD` handles `str + str`; `DIV` is `/`; `MOD` is `%`; `POW` is `**`; order comparisons handle `str` and numbers; truthiness is Python `bool()` | Text concat, float division, and floor division (via SEMANTIC-DECISIONS #10) already exist as operators — do **not** duplicate them as builtins. |
| `_render` maps `None → "nothing"`, `True → "true"`, `False → "false"` | `text of` must reuse `_render`, not raw Python `str` (§6). |
| `RESERVED` has 39 entries; operator phrases include `plus`, `minus`, `times`, `divided by`, `modulo`, `to the power of`, `equals`, `exceeds`, `differs from`, `is greater than`, … | Several natural English names/labels collide (§4). |
| Phase roadmap: Phase 5 collections, Phase 7 modules + file I/O | List/map builtins → Phase 5; file I/O + trig/log (via `use the math module`) → Phase 7. |

**Design stance.** The stdlib is a **closed vocabulary of phrase names + closed labeled parameter names**, registered in one place (extend `synonyms.py` with a `BUILTIN_SPECS` table and expose it as the builtin scope). Libraries extend *values and types*, never syntax — per `DESIGN.md` §12. User-defined functions with aliases remain the open extension mechanism.

---

## 1. Grammar-fit legend

| Code | Meaning |
|---|---|
| **fit** | Runs with the grammar exactly as written today (single-word alias name + labeled args). |
| **phrase** | Needs **G1**: multi-word call name. |
| **postfix** | Needs **G3**: postfix predicate expression (`value is empty`). |
| **type** | Needs **G4**: list/map runtime types + literals/indexing (Phase 5). |
| **io** | No grammar change, but needs a Phase-7 file-access policy (sandboxing) before shipping. |
| **runtime** | Needs runtime change R1/R2 (builtin scope / native function type), not grammar. |

All builtins need **runtime**. The column below records *additional* requirements.

---

## 2. Minimal grammar extensions (proposed)

### G1 — Phrase names for calls (required for the English surface)

```
call          := "call" phrase_name ["with" arg_list]
phrase_name   := WORD+          # maximal run of WORD tokens after "call"
```

- The name is the longest run of `WORD` tokens after `call`, stopping at `with`, `NEWLINE`, `EOF`, or any `PUNCT`.
- Change `Parser.parse_call_expr`: replace `name = self._expect_name()` with a `phrase_name` collector; keep `_expect_name()` for **labels**.
- Apply the same collector to `alias_line` so builtins can declare phrase aliases: `also known as the size of, how long`.
- Reserved words are **allowed inside** a phrase (the phrase is already delimited by `call`/`with`/newline). This lets `call not nothing with ...` parse as a name; we simply never define such a builtin.
- **Hard rule:** no phrase name may contain the word `with` — it is the argument delimiter. `join … with …` and `starts with` are therefore renamed (§4).
- Diagnostic: if a user writes `call the length of "hi"` the tail is collected into the name; error must say `Unknown built-in 'the length of "hi"' — did you mean 'call the length of with text = …'?`.

### G2 — Zero-change fallback (make this the implementation identity)

Every phrase also gets an underscore identifier: `the_length_of`, `uppercase_of`, `does_text_contain`. These are valid `word` tokens (`[A-Za-z_][A-Za-z0-9_]*`), so `call the_length_of with text = s` works **today**. Recommended rollout order: ship P0 with G2 identifiers, land G1 immediately after, then switch the documented canonical spelling to the phrase. This decouples stdlib delivery from parser work.

### G3 — Postfix predicates (required to honor existing docs)

`DESIGN.md` §4 already advertises `expect name is not empty` and `SEMANTIC-DECISIONS.md` §1 already promises `is nothing`. Neither parses today (`is not` is not an operator; `is` alone is not either). Add to `OPERATOR_PHRASES`/`_parse_unary` as postfix unary forms:

```
postfix := ("is" "empty") | ("is" "not" "empty") | ("is" "nothing")
           | ("is" "a" "number") | ("is" "text") | ("is" "a" "list") | ("is" "a" "map")
```

Canonically these desugar to a `Predicate(op, operand)` node. This is a genuine new grammar form (postfix unary) — the current `_match_operator` is binary-only. Alternative if G3 is deferred: every predicate is a prefix builtin (`call is empty with value = name`) — workable but reads worse than what the docs already promise.

### G4 — Collection literals and indexing (Phase 5; blocks all list/map builtins)

```
punct       := ... | "[" | "]" | "{" | "}" | ":"
list_display := "[" [expr ("," expr)*] "]"
map_display  := "{" [expr ":" expr ("," expr ":" expr)*] ""
index        := postfix "[" expr "]"          # or G1 builtins "item at" / "value for key"
```

Without this there is **no way to construct a list or map value at all** — labeled args cannot express a variable-length sequence (`call list containing with item = 1, item = 2` is rejected as a duplicate label). This is the single largest blocker; resolve it before the Phase-5 builtin batch.

### G5 — Quoted phrase names (optional escape hatch, P2)

```
phrase_name := WORD+ | STRING      # call "join with" with left = ..., right = ...
```

Resolves any future collision with a reserved/preposition word without renaming. Adds a STRING-as-name path and a second name representation to diagnostics; only add if a required phrase cannot be renamed.

### Non-grammar runtime changes

- **R1** — builtin scope as the ultimate parent of `global_env` (resolution order local → enclosing → global → builtin, per `SEMANTIC-DECISIONS.md` §3.4).
- **R2** — `NativeFunction` callable type with `name`, `params`, `invoke(args, pos)`, reusing the existing duplicate/unknown/missing-label validation in `Interpreter._call`.
- **R3** — default parameter values (optional, P1). Today every labeled arg is mandatory; several builtins (`round`, `slice`, `replace`, `random`) want defaults. Until R3 lands, supply separate phrase variants (`rounded to places`, `a slice of … from … up to …`, `replace first`).
- **R4** — wrap Python exceptions (`ValueError`, `OSError`, `OverflowError`, `IndexError`, `KeyError`) into `RuntimeErrorLang` carrying the `Call` node's source position and a "did you mean …" hint. Never leak a raw Python traceback.

---

## 3. Naming conventions (locked proposal)

1. **Canonical internal id** = lowercase words joined by `_`: `the_length_of`, `read_text_from`. This is also the G2 alias.
2. **Surface phrase** = the same words separated by spaces: `the length of`.
3. **Short alias** = one word where unambiguous and non-reserved: `length`, `trim`, `round`, `uppercase`.
4. **No phrase contains `with`** (arg delimiter) or `to`/`as`/`end`/`call` (reserved). `of`, `the`, `from`, `by`, `into`, `using`, `on`, `at` are safe.
5. **Article rule:** `a` is reserved but `the` is not. Prefer phrases without `a`; G1 allows `a` internally anyway.
6. **Parameter labels** are nouns/adjectives, never prepositions: `text`, `piece`, `start`, `end`, `path`, `value`, `key`, `separator` — not `to`, `with`, `from`, `in`, `as`.
7. **Mutation** is marked in the phrase: `append to`, `put into`, `remove from`. Pure variants return a new value and use `… of` / `… from`: `reversed of`, `sorted`. Document that in-place mutators return `nothing` and are visible through every alias (Python object-reference semantics, `python-semantics.md` §0.1/§0.7).
8. **Exceptions/errors in phrase** avoided: `read text from` fails loudly rather than returning `nothing`.

---

## 4. Naming collisions and resolutions

| Collision | Why it breaks | Resolution |
|---|---|---|
| `show` / `display` / `print` as builtin names | Reserved; `call print with …` → `_expect_name` rejects `print` | Not builtins — they are the `Show` statement. Use `write text to` for output-to-file. |
| `require`, `if`, `end`, `repeat`, `while`, `define`, `return`, `give`, `call`, `with`, `set`, `let`, `a`, `not`, `and`, `or`, `true`, `false`, `nothing` | All in `RESERVED`; cannot be a single-word call name or a parameter label | Never name a builtin or label with these. Phrase names may contain them under G1, but we don't. |
| **`with`** in `join … with …`, `starts with`, `begins with` | It is the call-argument introducer. `call join with items = …, with sep = …` is unparseable | Rename: `join items using separator`, `has prefix`, `has suffix`. G5 (`call "join with" with …`) is the fallback if the original spelling is ever required. |
| **`to`** in `convert … to …`, label `to` | Reserved; cannot be a label; also ambiguous with `set … to …` | Use label `into` or `target`: `call whole number from text with text = s`, `call convert into text with value = n`. |
| **`as`** in `read … as …` | Reserved | Use `into` / `as_text` phrase: `call text of with value = n`. |
| **`in`** in `x in xs` / label `in` | Not reserved today, but planned for `for each x in xs` (Phase 5) | Avoid as a label. Use `within`, `value`, `collection`. |
| **operator words** `plus`, `minus`, `times`, `divided by`, `modulo`, `exceeds`, `equals` | Not all reserved, but `_match_operator` treats them as operators in expression position; a builtin named `times` is confusing | Don't define builtins named after operators. `repeat text` uses label `count`, not a builtin `times`. |
| **`is`** | Not reserved, but `is empty` / `is nothing` are G3 postfix predicates, not call names | Never define a builtin whose phrase begins with `is`. |
| **`expect`** | Reserved *semantically* for try-block (`SEMANTIC-DECISIONS.md` §0), though not in `RESERVED` yet | Do not use for predicates or I/O. Add it to `RESERVED` when Phase 7 lands. |
| **`use`, `module`, `produce`, `this`, `fail`, `each`** | Planned keywords (`SEMANTIC-DECISIONS.md` §2) | Avoid as builtin names/labels; add to `RESERVED` in their phase. |
| **`length` on text vs list vs map** | Silent semantic drift if undefined | Define explicitly: text → code-point count; list → item count; map → key count. Same phrase, documented per-type behavior. |
| **`round`** | Python uses ties-to-even, not "round half up" | Keep Python semantics; document loudly in the builtin table and in diagnostics. |

---

## 5. Builtin catalog

Parameters shown as `label: expected-type`. `→` gives the result type. `Grammar` uses the §1 legend; every row also needs R1/R2.

### 5.1 Text operations

| Surface name (canonical; aliases) | Labeled parameters | Semantics | Python equivalent | Edge cases | Grammar | Priority |
|---|---|---|---|---|---|---|
| `the length of`; `length`, `len` | `text: text` → number | Number of Unicode **code points** | `len(text)` | `"" → 0`; combining marks / emoji ZWJ sequences count as multiple code points; non-text → loud error | phrase (G2 alias fits) | **P0** |
| `uppercase of`; `uppercase` | `text: text` → text | Unicode uppercase mapping | `s.upper()` | Non-letters unchanged; may change length (e.g. `ß → SS`); locale-independent | phrase | P1 |
| `lowercase of`; `lowercase` | `text: text` → text | Unicode lowercase mapping | `s.lower()` | Same Unicode caveats | phrase | P1 |
| `trim`; `strip` | `text: text` → text | Strip leading/trailing whitespace | `s.strip()` | Returns new text; whitespace is Python's `str.isspace()` set; no char-set param until R3 | fit (`trim`, `strip`) | **P0** |
| `trim left of` / `trim right of` | `text: text` → text | One-sided strip | `s.lstrip()` / `s.rstrip()` | — | phrase | P2 |
| `a slice of`; `slice` | `text: text`, `start: whole number`, `end: whole number` → text | Half-open `[start, end)` by code point | `s[start:end]` | Negative indices add length; out-of-range bounds clipped, not errors (Python slicing); `start ≥ end → ""`; non-whole-number index → loud error. No step until R3 | phrase | **P0** |
| `does text contain`; `contains text` | `text: text`, `piece: text` → boolean | Substring test | `piece in s` | `"" in s → true`; case-sensitive; non-text piece → error | phrase | **P0** |
| `has prefix` (alias `starts with`* ) | `text: text`, `prefix: text` → boolean | Prefix test | `s.startswith(prefix)` | `"" → true`; the `starts with` alias needs G5 because of `with` | phrase | P1 |
| `has suffix` (alias `ends with`* ) | `text: text`, `suffix: text` → boolean | Suffix test | `s.endswith(suffix)` | Same as prefix | phrase | P1 |
| `find in text` | `text: text`, `piece: text` → number | First 0-based index, or `-1` | `s.find(piece)` | Empty piece → `0`; `-1` is a value, not an error | phrase | P2 |
| `index of in text` | `text: text`, `piece: text` → number | Like `find` but loud failure if absent | `s.index(piece)` | Absent → `RuntimeErrorLang` with pos + `did you mean find in text?` | phrase | P2 |
| `replace in text` | `text: text`, `old: text`, `new: text` → text | Replace **all** occurrences | `s.replace(old, new)` | `old = ""` inserts between every code point (Python behavior — document); count-limited variant `replace first in text` until R3 | phrase | P1 |
| `count of in text` | `text: text`, `piece: text` → number | Non-overlapping occurrence count | `s.count(piece)` | Overlaps not counted (`"aaa".count("aa") → 1`) | phrase | P2 |
| `repeat text` | `text: text`, `count: whole number` → text | Concatenate `count` copies | `s * n` | `count ≤ 0 → ""`; huge counts → memory error, wrap; label is `count` (not reserved `times`) | phrase | P2 |
| `characters of` | `text: text` → list of text | One-character strings | `list(s)` | Returns code points, not grapheme clusters | phrase + type | P2 |
| `lines of` | `text: text` → list of text | Split on line boundaries, drop terminators | `s.splitlines()` | Handles `\n`, `\r\n`, `\r`, and Unicode line separators | phrase + type | P2 |
| `join items using separator` (alias `join with`* ) | `items: list of text`, `separator: text` → text | Concatenate with separator | `sep.join(items)` | `[] → ""`; non-text item → loud error; alias needs G5 | phrase + type | **P1** |
| `split text on delimiter` | `text: text`, `delimiter: text` → list of text | Split into pieces | `s.split(delim)` | Empty delimiter → loud error (Python `ValueError`); consecutive delimiters yield empty pieces; `"" → [""]` | phrase + type | **P1** |
| `fill in template` | `template: text`, `values: map` → text | Substitute named fields | `template.format(**values)` | Missing/unknown keys → loud error; brace escaping; never `eval` user code | phrase + type | P1 |

`*` alias requires G5 (quoted phrase name) or must be dropped.

### 5.2 Numbers / math

| Surface name | Labeled parameters | Semantics | Python equivalent | Edge cases | Grammar | Priority |
|---|---|---|---|---|---|---|
| `absolute value of`; `absolute` | `number: number` → number | Magnitude | `abs(x)` | `abs(bool)` must error (bool is not a number in `_is_number`) | phrase | P1 |
| `rounded to places` | `number: number`, `places: whole number` → number | Round to N decimal places | `round(x, n)` | **Ties-to-even** (banker's rounding): `round(2.5) → 2`; float representation surprises; negative `places` rounds tens/hundreds | phrase | P1 |
| `whole number of`; `floor of` | `number: number` → whole number | Largest integer ≤ x | `math.floor(x)` | `nan`/`inf` → loud error; already-integer → same value | phrase | P1 |
| `ceiling of` | `number: number` → whole number | Smallest integer ≥ x | `math.ceil(x)` | Same as floor | phrase | P1 |
| `square root of` | `number: number` → number | Principal square root | `math.sqrt(x)` | Negative → loud error (no complex in v1); `-0.0 → -0.0` | phrase | P1 |
| `whole-number quotient of … by …` | *(operator, not a call)* | Floor division | `a // b` | Rounds toward −∞; `%` has divisor's sign; add phrase `whole-number quotient of` to `OPERATOR_PHRASES`, do **not** duplicate as a builtin | grammar add | P1 |
| `minimum of` / `maximum of` | `values: list of number` → number | Extrema | `min(vals)` / `max(vals)` | Empty list → loud error; mixed number/text → error; NaN comparisons are false — define rejection | phrase + type | P1 |
| `sum of` | `values: list of number` → number | Sum | `sum(vals)` | `[] → 0`; float accumulation order is left-to-right (deterministic) | phrase + type | P1 |
| `average of`; `mean of` | `values: list of number` → number | Arithmetic mean | `sum(vals)/len(vals)` | Empty → loud error | phrase + type | P2 |
| `greatest common divisor of` | `a: whole number`, `b: whole number` → whole number | GCD | `math.gcd(a, b)` | Negative inputs → non-negative result | phrase | P2 |
| `random number between` | `low: number`, `high: number` → number | Uniform `[low, high)` | `random.uniform(low, high)` | **Non-deterministic**: needs a seed policy for reproducible tests/AI debugging; document seed injection as open decision | phrase | P2 |
| `random whole number between` | `low: whole number`, `high: whole number` → whole number | Inclusive integer | `random.randint(low, high)` | `low > high` → loud error; same seed policy | phrase | P2 |
| `sine of` / `cosine of` / `tangent of` | `angle: number` → number | Radians trig | `math.sin/cos/tan` | Radians, not degrees (document); huge values lose precision | phrase | P2 |
| `natural log of` / `log base` | `number: number`, [`base: number`] → number | Logarithm | `math.log(x[, base])` | `x ≤ 0` → loud error; `base ≤ 0` or `1` → error | phrase | P2 |
| `clamp` | `number: number`, `low: number`, `high: number` → number | Constrain to range | `min(high, max(low, x))` | `low > high` → loud error | fit (`clamp`) | P2 |
| constants `pi`, `e` | — → number | Builtin **values**, not calls | `math.pi`, `math.e` | Injected into builtin scope; names not reserved but must not be shadowable silently (lint warning) | runtime only | P2 |

Covered by operators — do **not** add: `power of` (`to the power of`), `modulo` (`remainder of`), `plus`/`minus`/`times`/`divided by`.

### 5.3 Predicates

Two delivery modes: **G3 postfix** (preferred, matches existing docs) and **prefix builtin** (no grammar change). The table gives both spellings; priority assumes G3.

| Surface (postfix / prefix) | Labeled parameter (prefix form) | Semantics | Python equivalent | Edge cases | Grammar | Priority |
|---|---|---|---|---|---|---|
| `value is empty` / `is empty` | `value: any` → boolean | True for `nothing`, empty text, empty list/map; **false for numbers and booleans** | `v is None or (hasattr(v,"__len__") and len(v)==0)` — define explicitly, do not use bare truthiness | `0` and `false` are **not** empty (differs from `not v`); undefined for custom objects without length | postfix / phrase | **P0** |
| `value is not empty` / `is not empty` | `value: any` → boolean | Negation of above | `not is_empty(v)` | Same; this exact phrase is promised in `DESIGN.md` §4 | postfix / phrase | **P0** |
| `value is nothing` / `is nothing` | `value: any` → boolean | Singleton check only | `v is None` | Promised in `SEMANTIC-DECISIONS.md` #1; no identity checks against literals | postfix / phrase | **P0** |
| `value is a number` | `value: any` → boolean | int/float, excluding bool | `isinstance(v,(int,float)) and not isinstance(v,bool)` | Mirrors `_is_number`; `true` → false | postfix | P1 |
| `value is text` / `is a list` / `is a map` / `is a boolean` / `is a function` | `value: any` → boolean | Type tests | `isinstance` | Lists/maps need G4 | postfix | P1 |
| `value is truthy` | `value: any` → boolean | Python truth test | `bool(v)` | Makes implicit truthiness explicit for AI readers | postfix | P2 |
| `value is within` | `value`, `low`, `high` → boolean | Inclusive-inclusive range (English default) | `low <= v <= high` | Exclusive variant `is strictly within` until R3; chaining is dropped, so this is the safe idiom | phrase | P2 |
| `all of` / `any of` / `none of` | `values: list` → boolean | Quantifiers | `all(vals)`, `any(vals)`, `not any(vals)` | `[] → true/false/true`; uses universal truthiness | phrase + type | P1 |
| `the first truthy of` | `values: list` → any | First truthy operand, else last value | `functools.reduce(lambda a,b: a or b, vals)` | Explicit idiom promised by `SEMANTIC-DECISIONS.md` §2; preserves operand-returning `or` | phrase + type | P1 |

### 5.4 Conversions

| Surface name | Labeled parameters | Semantics | Python equivalent | Edge cases | Grammar | Priority |
|---|---|---|---|---|---|---|
| `text of`; `as text` | `value: any` → text | **llang render**, not raw `str` | `_render(value)` | `nothing → "nothing"`, `true → "true"`, `false → "false"`; list/map rendering needs a defined canonical format (insertion-ordered, quoted strings) | phrase | **P0** |
| `whole number from text` | `text: text` → whole number | Base-10 integer parse | `int(s)` | Leading/trailing whitespace accepted; `"+3"`/`"-3"` ok; `"3.0"` → error; **no coercion**, invalid → loud error with pos | phrase | **P0** |
| `decimal number from text` | `text: text` → number | Float parse | `float(s)` | `"nan"`/`"inf"` accepted by Python — recommend rejecting as loud error; `"1e3"` ok | phrase | **P0** |
| `boolean from text` | `text: text` → boolean | Strict `true`/`false` parse (case-insensitive?) | `s.lower()=="true"` etc. | Any other text → loud error; decide case-sensitivity explicitly | phrase | P2 |
| `character with code` / `code of character` | `code: whole number` / `character: text` | Unicode code point ↔ char | `chr(n)` / `ord(c)` | Range `0..0x10FFFF`; surrogates allowed by `chr` but may not render; multi-code-point text → error | phrase | P2 |
| `list from` (text) | `text: text` → list | Parse delimited text | user-defined | Needs a delimiter spec — prefer `split text on delimiter` instead; do not duplicate | — | P2 |
| `pairs of` / `keys of` / `values of` | `map: map` → list | Map projections | `list(d.items())`, `list(d)`, `list(d.values())` | Insertion order guaranteed; views are live in Python — return **snapshots** | phrase + type | P1 |
| `map from pairs` | `pairs: list of pair` → map | Build map | `dict(pairs)` | Duplicate keys → last wins; unhashable key → loud error | phrase + type | P2 |

### 5.5 List operations (Phase 5, gated on G4)

| Surface name | Labeled parameters | Semantics | Python equivalent | Edge cases | Grammar | Priority |
|---|---|---|---|---|---|---|
| `the length of` (reuse) | `list: list` → number | Item count | `len(xs)` | Same phrase as text/map; per-type semantics documented | phrase + type | P1 |
| `item at index` | `list: list`, `index: whole number` → any | Indexed access | `xs[i]` | Negative index adds length; out of range → loud error (Python `IndexError`); bool index → error. Recommend native `xs[i]` syntax instead of this builtin | phrase + type | P1 |
| `append to` | `list: list`, `item: any` → nothing | In-place append | `xs.append(item)` | Mutates shared object (aliasing!); returns `nothing`; document | phrase + type | P1 |
| `insert into` | `list: list`, `index: whole number`, `item: any` → nothing | Insert before index | `xs.insert(i, item)` | `i ≤ 0 → front`, `i ≥ len → end` | phrase + type | P2 |
| `remove from` | `list: list`, `item: any` → nothing | Remove first match | `xs.remove(item)` | Absent → loud error; equality uses `_equal` (bool-safe) | phrase + type | P2 |
| `take item from` | `list: list`, `index: whole number` → any | Remove + return | `xs.pop(i)` | Out of range → loud error; default last item needs R3 → add `take last item from` | phrase + type | P2 |
| `reversed of` | `list: list` → list | New reversed list | `list(reversed(xs))` | Returns a **copy**; does not mutate | phrase + type | P2 |
| `sorted` | `values: list` → list | New sorted list | `sorted(xs)` | Mixed types → loud error; Unicode-code-point ordering for text; `sorted descending` variant until R3 | fit (`sorted`) + type | P1 |
| `flatten` | `values: list of list` → list | One-level flatten | `[y for x in xs for y in x]` | One level only; deeper needs explicit repeats | fit (`flatten`) + type | P2 |
| `take first` / `take last` | `list: list`, `count: whole number` → list | Prefix/suffix copy | `xs[:n]`, `xs[-n:]` | Clip bounds; `count=0 → []` | phrase + type | P2 |
| `does list contain` | `list: list`, `item: any` → boolean | Membership | `item in xs` | Uses `_equal`; for maps this phrase tests keys (document) | phrase + type | P1 |

### 5.6 Map operations (Phase 5, gated on G4)

| Surface name | Labeled parameters | Semantics | Python equivalent | Edge cases | Grammar | Priority |
|---|---|---|---|---|---|---|
| `the length of` (reuse) | `map: map` → number | Number of keys | `len(d)` | Documented overloading of the same phrase | phrase + type | P1 |
| `value for key` | `map: map`, `key: any` → any | Lookup, loud on missing | `d[k]` | Unhashable key → loud error; `true`/`1`/`1.0` collide as keys (Python) — document | phrase + type | **P1** |
| `value for key or default` | `map: map`, `key: any`, `default: any` → any | Tolerant lookup | `d.get(k, default)` | `default` evaluated before call (left-to-right args) | phrase + type | P1 |
| `put into` | `map: map`, `key: any`, `value: any` → nothing | Insert/replace | `d[k] = v` | Updating an existing key keeps its insertion position; in-place mutator | phrase + type | P1 |
| `does map have key` | `map: map`, `key: any` → boolean | Key membership | `k in d` | Tests keys only, not values | phrase + type | P1 |
| `remove key from` | `map: map`, `key: any` → nothing | Delete | `del d[k]` | Missing → loud error | phrase + type | P2 |
| `merge` | `left: map`, `right: map` → map | New merged map | `{**left, **right}` | Right wins on duplicate keys; insertion order of *left* keys preserved | fit (`merge`) + type | P2 |
| `copy of` | `map: map` → map | Shallow copy | `d.copy()` | Nested mutables remain shared — document | phrase + type | P2 |

### 5.7 File I/O (Phase 7; needs a sandbox policy)

| Surface name | Labeled parameters | Semantics | Python equivalent | Edge cases | Grammar | Priority |
|---|---|---|---|---|---|---|
| `read text from` | `path: text` → text | Read whole file as UTF-8 | `open(path, encoding="utf-8").read()` | Missing/permission/unreadable → loud error incl. path; universal newline translation (`\r\n → \n`); BOM not stripped by default — document; **no implicit path coercion** (path must be text) | phrase + io | **P0** (caveat below) |
| `write text to` | `path: text`, `text: text` → nothing | Write/truncate UTF-8 file | `open(path, "w", encoding="utf-8").write(text)` | **Overwrites** — must be explicit in the phrase/docs; returns `nothing`; parent dirs must exist | phrase + io | **P0** (caveat) |
| `append text to` | `path: text`, `text: text` → nothing | Append UTF-8 | `open(path, "a", encoding="utf-8").write(text)` | Creates file if absent; no separator inserted | phrase + io | P1 |
| `read lines from` | `path: text` → list of text | Lines without terminators | `f.read().splitlines()` | Empty file → `[]`; trailing newline does not add an empty line | phrase + io + type | P1 |
| `write lines to` | `path: text`, `lines: list of text` → nothing | Write one line per item | `f.write("\n".join(lines) + "\n")` | Define final-newline policy explicitly | phrase + io + type | P2 |
| `file exists at` | `path: text` → boolean | Existence test | `os.path.exists(path)` | Race conditions: check-then-use is not atomic | phrase + io | P2 |
| `list files in` | `path: text` → list of text | Directory entries | `os.listdir(path)` | Unspecified order — sort explicitly if needed | phrase + io + type | P2 |
| `make directory at` | `path: text` → nothing | Create one directory | `os.mkdir(path)` | Existing → loud error; parents not created | phrase + io | P2 |
| `delete file at` | `path: text` → nothing | Remove file | `os.remove(path)` | Destructive — require `require` confirmation or an allowlist policy | phrase + io | P2 |
| `join path from` | `parts: list of text` → text | OS-aware path join | `os.path.join(*parts)` | Absolute part resets earlier parts (Python behavior) | phrase + type | P2 |
| `read bytes from` / `write bytes to` | `path: text`, `data: bytes` | Binary I/O | `open(path,"rb"/"wb")` | No `bytes` type in v1 — defer entirely | phrase + io | P2 |

**P0 caveat:** file I/O is only P0 *after* a security decision. Because the primary author is an LLM (`DESIGN.md` §8), recommend: confine paths to the workspace root, reject `..` traversal and absolute paths outside it, maintain a per-run writable allowlist, and surface the resolved path in every error. If that policy is not agreed before v1, demote `read text from`/`write text to` to P1 and P0 has no persistence.

### 5.8 Date / time (Phase 7; low priority)

| Surface name | Labeled parameters | Semantics | Python equivalent | Edge cases | Grammar | Priority |
|---|---|---|---|---|---|---|
| `current time` | *(none)* → number | Unix epoch seconds, float | `time.time()` | Non-deterministic; wraps as zero-arg call `call current time` | phrase | P2 |
| `current date` | *(none)* → text | ISO `YYYY-MM-DD` local date | `datetime.date.today().isoformat()` | Local timezone dependence — document; consider UTC variant | phrase | P2 |
| `format time` | `time: number`, `format: text` → text | Timestamp → formatted text | `datetime.fromtimestamp(t).strftime(fmt)` | Invalid format codes → Python leaves them literal; out-of-range timestamp → loud error | phrase | P2 |
| `parse time from text` | `text: text`, `format: text` → number | Formatted text → timestamp | `datetime.strptime(...).timestamp()` | Mismatch → loud error; timezone-naive result | phrase | P2 |
| `parts of time` | `time: number` → map | `year`, `month`, `day`, `hour`, … fields | `datetime.fromtimestamp(t)` → map | Local timezone; map keys must be documented | phrase + type | P2 |
| `time between` | `start: number`, `end: number` → number | Duration in seconds | `end - start` | Negative if `end < start` — document; no new type needed | phrase | P2 |
| `wait for seconds` | `seconds: number` → nothing | Sleep | `time.sleep(s)` | Blocks; sandbox/timeout policy; negative → loud error | phrase | P2 |

---

## 6. Grammar-extension matrix (explicit answer to requirement 3)

| Extension | Builtins that need it | Ship gate |
|---|---|---|
| **G0/G2 — none** (single-word alias like `trim`, `round`, `sorted`, `merge`, `clamp`, `flatten`, plus underscore ids `the_length_of`, …) | ~15 rows have a fit alias; **all** rows have a G2 underscore id | Can ship today, no parser change |
| **G1 — phrase call names** | Every canonical English phrase in §5 (the vast majority) | Land early; hard requirement for the advertised surface |
| **G3 — postfix predicates** | `is empty`, `is not empty`, `is nothing`, type checks, `is truthy`, `is within` | Early — `DESIGN.md` already promises two of them |
| **G4 — list/map literals + indexing** | All of §5.5, §5.6, and `split`, `join`, `min/max`, `sum`, quantifiers, `keys of`, etc. | Phase 5; **blocks** these builtins |
| **G5 — quoted phrase names** | Only the `with`-containing aliases (`join with`, `starts with`, `ends with`) | Optional/P2; avoid by renaming |
| **R3 — default params** | `round`, `a slice of`, `replace`, `random`, `take item from`, `format time` | P1 quality-of-life; work around with phrase variants |
| **operator phrase add** | `whole-number quotient of … by …` | Phase 2 vocabulary update |
| **io policy** (not grammar) | All of §5.7 | Must be decided before file I/O ships |
| **R1/R2/R4** (not grammar) | Every builtin | Required for any stdlib at all |

---

## 7. Implementation notes

1. **One registry.** Add `BUILTIN_SPECS: dict[str, BuiltinSpec]` to `synonyms.py` (the existing single-source-of-truth module). Each spec: `canonical_id`, `surface_phrases[]`, `params[]`, `native_callable`, `return_type_doc`, `phase`, `min_types`. Reuse the existing alias mechanism: a builtin is a "native function with aliases."
2. **Builtin lookup.** In `Interpreter.__init__`, create `builtin_env`, populate with `NativeFunction` objects, and set `global_env = Env(parent=builtin_env)`. Then `Env.get` already implements local → global → builtin for free. Shadowing a builtin with a user binding should emit a lint warning (Phase 6).
3. **Native callable contract.** `invoke(args: dict, pos: SourcePos) → value`. Validate labels with **exactly** the existing duplicate/unknown/missing logic from `_call`; factor that block into a helper shared by both `Function` and `NativeFunction` so diagnostics are identical.
4. **No coercion.** Every native checks its own types (e.g. `_is_number`, `isinstance(v, str)`) and raises `RuntimeErrorLang` with the call's `pos`. `bool` is never a number (matches `_is_number` and `_equal`).
5. **Wrap Python exceptions.** Never let `ValueError: empty separator` or `FileNotFoundError` escape unwrapped. Use `RuntimeErrorLang(f"{phrase}: <clear reason>", pos, suggestions=[...])`.
6. **Determinism.** No builtin may depend on hash iteration order: maps are insertion-ordered; `keys of`/`values of`/`list files in` return deterministic or explicitly documented orders. Random/time builtins are isolated in P2 and need a seed/clock injection policy for reproducible tests.
7. **Mutation doc.** In-place builtins return `nothing` and must state that all aliases see the change — Python's "names are bindings, not boxes" (`python-semantics.md` §0.1).
8. **Desugaring equivalence tests.** For each phrase and its G2 alias, assert identical `Call(canonical_id, …)` ASTs — mirroring the synonym tests mandated by `DESIGN.md` §5.7.
9. **Formatter normalization.** The formatter collapses all phrases to one canonical surface spelling for stable diffs (`DESIGN.md` §11).
10. **Versioned docs.** Every builtin's Python equivalent and edge cases listed above go verbatim into the generated reference page so the grounding stays auditable.

---

## 8. Recommended smallest P0 set

**13 builtins (15 surface phrases counting `is not empty`).** Chosen so a v1 script can complete the whole useful loop — **read → inspect → transform → convert → validate → write** — without lists, maps, or new grammar beyond G1/G3.

| # | Builtin | Why it earns P0 |
|---|---|---|
| 1 | `the length of` | The single most common operation; defined on text now, later extended to list/map |
| 2 | `read text from` | Makes the language interact with the outside world (with sandbox caveat) |
| 3 | `write text to` | Completes the persistence loop |
| 4 | `text of` | Required for `show` of computed values and for building messages |
| 5 | `whole number from text` | The main conversion used with file/data input |
| 6 | `decimal number from text` | Same for float data |
| 7 | `uppercase of` | Cheapest, most obvious text transform |
| 8 | `lowercase of` | Symmetric with above; normalization for comparisons |
| 9 | `trim` | Input cleanup — almost always needed after `read text from` |
| 10 | `a slice of` | Substring extraction; enables parsing without regexes |
| 11 | `does text contain` | The primary search predicate |
| 12 | `is empty` / `is not empty` | Already promised in `DESIGN.md` §4; the input-validation workhorse |
| 13 | `is nothing` | Already promised in `SEMANTIC-DECISIONS.md` #1; safe singleton check |

**Deliberately excluded from P0 (and why):**
- `has prefix`/`has suffix`, `replace in text`, `absolute value of`, `rounded` — useful but deferable; P1.
- **Every list/map builtin** — impossible until G4 lands (Phase 5). Including them in P0 would block the release.
- `join`, `split`, `sorted`, `min`/`max`, `sum` — same G4 dependency.
- `random`, trig/log, date/time — P2; non-determinism and module policy need decisions first.
- `expect`/try, `use the math module` — separate Phase-7 language features, not builtins.

**Ship sequence:** (a) R1/R2 + G2 underscore ids + the 13 P0 specs → usable v1 stdlib; (b) G1 phrase names + G3 postfix predicates → advertised surface; (c) G4 + Phase-5 collection builtins; (d) G5/R3 + io policy + Phase-7 I/O/date/time.

---

## 9. Open decisions (need owner sign-off)

1. **G1 details:** are reserved words legal *inside* phrase names? (Proposal: yes, but ban `with`.) Do phrase aliases on `also known as` lines use the same collector? (Proposal: yes.)
2. **G3 or prefix-only predicates?** G3 costs a new unary AST node but keeps the docs' promises.
3. **File-I/O sandbox:** workspace-root confinement? allowlist? resolved-path errors?
4. **Random/clock injection** for deterministic tests.
5. **Default parameters (R3)** — do we add `defaulting to` syntax now, or keep phrase variants?
6. **"Empty" definition** — proposal: `nothing`, empty text/list/map only; `0` and `false` are **not** empty. Confirm.
7. **`text of` rendering** — confirm llang `_render` (nothing/true/false) rather than Python `str`.
8. **`round` semantics** — confirm ties-to-even with loud docs.
9. **`index of in text` vs `find in text`** — keep both, or only the loud one?
10. **Map key equality** — confirm that `true`, `1`, and `1.0` collide as keys (Python) despite `_equal`'s bool guard for `equals`.
