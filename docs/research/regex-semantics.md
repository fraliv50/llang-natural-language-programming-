# Regular expression semantics — grounding for llang

*Status: research for the `re` module feature. Authority: Python's official `re`
documentation and the CPython 3.11 parser/compiler. Where llang diverges, the
divergence is explicit and justified below. This document follows the method in
[`../METHOD.md`](../METHOD.md): semantics first, syntax second.*

**Sources (inline citations use these short tags):**

- **[RE]** <https://docs.python.org/3/library/re.html> — `re` module docs (syntax, flags, functions, Pattern/Match objects, examples, gotchas).
- **[PARSER]** <https://github.com/python/cpython/blob/3.11/Lib/re/_parser.py> — CPython 3.11 `re._parser` (the real implementation behind the `sre_parse.py` shim at <https://github.com/python/cpython/blob/3.11/Lib/sre_parse.py>).
- **[COMPILER]** <https://github.com/python/cpython/blob/3.11/Lib/re/_compiler.py> — CPython 3.11 `re._compiler` (opcodes, repeat branches, prefix optimization; the `sre_compile.py` shim is at <https://github.com/python/cpython/blob/3.11/Lib/sre_compile.py>).

---

## 1. What the reference language actually specifies

### 1.1 First useful subset to support

Grounded in **[RE]** "Regular expression syntax" and the opcode set in
**[PARSER]**/`_constants`. These are the constructs with the best ratio of
usefulness to semantic complexity for an AI-authored language.

| Construct | Surface (Python RE) | Semantics to implement | Include in v1? |
|---|---|---|---|
| Literal | `a`, `last` | Match the character itself; concatenation is sequential match. | **Yes** |
| Dot | `.` | Any one character **except newline** in default mode; `DOTALL` includes newline. Compiles to `ANY` / `ANY_ALL`. **[RE]**, **[COMPILER]** | **Yes** |
| Greedy quantifiers | `*`, `+`, `?` | 0+, 1+, 0-or-1 repetitions; match as many as possible, then backtrack. Compiles to `MAX_REPEAT` → `REPEAT`/`MAX_UNTIL`. **[RE]**, **[COMPILER]** | **Yes** |
| Lazy quantifiers | `*?`, `+?`, `??` | As few as possible; `MIN_REPEAT` → `REPEAT`/`MIN_UNTIL`. **[RE]**, **[COMPILER]** | **Yes** |
| Character class | `[amk]`, `[a-z]`, `[0-9A-Fa-f]`, `[^5]` | Set of characters; ranges; `^` negates only at first position; `-` literal at edges or escaped; `]` literal if first or escaped. Special chars except backslash lose meaning inside. **[RE]**, **[PARSER]** `_parse` `[` branch | **Yes** |
| Anchors | `^`, `$`, `\A`, `\Z` | `^` = start of string (or after each newline in MULTILINE); `$` = end or just before trailing newline (or before each newline in MULTILINE); `\A`/`\Z` = absolute start/end only. Compiles to `AT` opcodes. **[RE]**, **[COMPILER]** | **Yes** |
| Word boundary | `\b`, `\B` | Zero-width boundary between `\w` and `\W` (or string edge); `\B` its negation. **Inside a class `\b` means backspace.** **[RE]** | **Yes** |
| Groups | `(...)`, `(?:...)` | Capture (numbered from 1 by opening paren; group 0 = whole match) or group without capture. **[RE]** | **Yes** |
| Alternation | `A|B` | Try branches **left to right**, accept the first that lets the *whole* pattern succeed; not greedy, not longest. **[RE]** "The `|` operator is never greedy"; **[COMPILER]** `BRANCH` | **Yes** |
| Escapes | `\n \t \r \f \v \a \\`, `\.`, `\*`, `\d \D \w \W \s \S` | Standard character escapes; escaped metachar = literal; shorthand categories are Unicode-aware by default. **[RE]** "Special sequences"/"Standard escapes"; **[PARSER]** `ESCAPES`/`CATEGORIES` | **Yes** |
| Backreference | `\1`–`\9` | Re-match the text captured by that group. **[RE]**; **[PARSER]** `_escape` digit branch | **Yes** (cheap, high value) |
| Counted repetition | `{m}`, `{m,n}`, `{m,}`, `{m,n}?` | Exact/range repetition, greedy or lazy; `min > max` is an error. **[RE]**, **[PARSER]** | **Phase 2** (parser already handles it; wrapper/flags work first) |
| Named groups | `(?P<name>...)`, `(?P=name)` | Access captures by name. **[RE]** | **Phase 2** (our result map already has a `named` slot, so this is additive) |

**Deliberately out of scope for v1** (all documented in **[RE]**): lookahead
`(?=...)`/`(?!...)`, lookbehind `(?<=...)`/`(?<!...)` (fixed-width restriction),
atomic groups `(?>...)`, possessive quantifiers `*+`/`++`/`?+` (both added in
3.11), inline flags `(?aiLmsux)` / scoped flags, conditional groups, comments
`(?#...)`, `\x`/`\u`/`\U`/`\N{...}`/octal escapes, bytes patterns (llang has no
`bytes`), `LOCALE`/`DEBUG` flags, and `re.TEMPLATE`. Accepting any of these must
raise a **localized invalid-pattern problem**, never silently mis-match.

**Quantifiers cannot be directly nested:** `a**` is `"multiple repeat"`;
`(?:a{2})*` is the legal workaround. **[RE]**, **[PARSER]** `_parse` checks
`item[0][0] in _REPEATCODES`.

### 1.2 Matching semantics (the hard part)

1. **Leftmost match wins.** `search` tries start positions 0, 1, 2, … and
   returns the first position where the pattern succeeds; `None` (no match) is
   distinct from a zero-length match at some position. **[RE]** `re.search`.
2. **Then pattern order / depth-first backtracking wins.** At a given start
   position the engine explores the pattern's own order: a greedy quantifier
   takes the maximum and gives characters back only when the remainder fails;
   a lazy quantifier takes the minimum and grows only when needed. CPython
   realizes this with `MAX_UNTIL` vs `MIN_UNTIL` backtracking entries
   **[COMPILER]** `_REPEATING_CODES`. Consequence: `.*` on `<a> b <c>` swallows
   the whole string; `<.*?>` gives `<a>` **[RE]**.
3. **Alternation is first-success, not longest.** `A|B` is tried A first; once A
   allows the whole RE to match, B is never tested "even if it would produce a
   longer overall match". `a|ab` against `ab` matches `a`. **[RE]**.
4. **"Greedy" is local, not a global-longest guarantee.** It means "as many
   repetitions as possible *subject to the rest of the pattern matching*".
5. **Groups.** Numbered by opening parenthesis left-to-right from 1; group 0 is
   the whole match; a group that matches multiple times yields only the **last**
   capture (`re.search(r"(..)+", "a1b2c3").group(1) == "c3"`); a group that did
   not participate is `None`; `groups()` returns groups 1..n in order.
   **[RE]** "Match objects".
6. **Zero-length matches.** Empty matches are returned by `findall`/`finditer`
   and can occur immediately after a non-empty match; scanning advances one
   character after an empty match (changed in 3.7, so no infinite loop).
   `re.sub('x*', '-', 'abxd')` → `'-a-b--d-'`. **[RE]** `findall`, `finditer`,
   `sub`.
7. **Anchors vs `pos`.** `^` in `search(string, pos)` still refers to the real
   string start, so `pos`-search is *not* equivalent to slicing; MULTILINE
   affects `search("^X", …)` but not `match("X", …)`. **[RE]** `Pattern.search`,
   "search() vs. prefixmatch()". (llang v1 exposes no `pos`/`endpos`.)
8. **Optimizations are semantics-neutral.** `[_parser._parse_sub]` factors a
   common prefix out of branches and collapses literal branches into a charset;
   `[_compiler._compile_info]` builds literal-prefix/charset info to skip
   positions. Neither changes which match is returned. **[PARSER]**,
   **[COMPILER]**.
9. **No step limit in CPython.** A pattern like `(a+)+$` on many `a`s followed by
   `b` exhibits catastrophic backtracking; the engine has no timeout. llang's
   100 000-iteration loop guard does **not** apply inside a host regex call.
   Document as a known risk; a native engine may add an explicit step budget.

### 1.3 Documented gotchas to carry into llang

Every item below is stated in **[RE]** unless noted.

- **`match` is prefix-only**, not "find anywhere": `re.match("c", "abcdef")` is
  `None` while `re.search("c", "abcdef")` matches. Since 3.15 `match` is soft
  deprecated in favour of `prefixmatch` precisely because most other languages
  use "match" for search-like behavior. Name this loudly in the llang API.
- **Backslash collision with string literals.** Python needs raw strings
  (`r"\n"` vs `"\n"`); unknown escapes of ASCII letters are errors in patterns
  (since 3.6), while unknown *non-letter* escapes are literals. llang has **no
  raw strings** and drops the backslash for unknown escapes (REFERENCE §2), so
  `"\d+"` would silently become `"d+"`. Rule: **double every regex backslash
  in an llang string** (`"\\d+"`), and add a linter warning for single
  backslashes followed by a letter inside a pattern argument.
- **`.` excludes newline by default; `$` matches before a trailing newline**
  even without MULTILINE; searching `$` in `"foo\n"` finds two empty matches.
- **Inside `[...]`**: `\b` is backspace; numeric escapes are always octal;
  `^` is literal unless first; `]` is literal if first; `-` is literal at the
  ends; ranges must be ascending (`[z-a]` is `bad character range`).
- **Backreference vs octal:** `\1`–`\9` are group refs; a leading `0` or three
  octal digits means an octal character instead. In replacement templates use
  `\g<name>`/`\g<2>` to avoid `\20` ambiguity.
- **`re.escape` is for patterns only**, never replacement strings (only
  backslashes should be escaped there).
- **Unicode by default:** `\d`, `\w`, `\s` match non-ASCII characters unless an
  ASCII flag is set; `IGNORECASE` on `[a-z]` also matches `İ`, `ı`, `ſ`, `K`.
- **Match objects are always truthy**, so `if m:` tests success; no-match is
  `None`.
- **`findall` has a chameleon return shape** (strings / strings of one group /
  tuples of groups). llang has no tuples — see the API decision below.
- **Mixed `str`/`bytes` is forbidden**; irrelevant for llang, which has no bytes.

---

## 2. Proposed llang API

### 2.1 Shape of the module

Follow the established module precedent (REFERENCE §7b, `shell`): add `re` to
the foreign allowlist in `src/llang/foreign.py`, where host functions convert
every result to ordinary llang values (numbers, texts, lists, maps, `nothing`).
A thin native `lib/re.ll` layer can then add phrase aliases. Nothing about the
grammar changes.

```
use the foreign re module
show call search from re with pattern = "cat", text = "concatenate"
```

### 2.2 Operations (label → result; all catchable errors use `fail with` kinds)

| llang call (canonical name) | Python equivalent | Labels → result |
|---|---|---|
| `call match from re with …` | `re.match` / `prefixmatch` | `pattern`, `text`, optional `flags` → match map or `nothing` |
| `call search from re with …` | `re.search` | `pattern`, `text`, optional `flags` → match map or `nothing` |
| `call full match from re with …` | `re.fullmatch` | `pattern`, `text`, optional `flags` → match map or `nothing` |
| `call find all from re with …` | `re.finditer` (deliberate divergence from `findall`) | `pattern`, `text`, optional `flags` → list of match maps (possibly empty) |
| `call replace from re with …` | `re.sub` | `pattern`, `text`, `replacement`, optional `count`, `flags` → text |
| `call split from re with …` | `re.split` | `pattern`, `text`, optional `limit`, `flags` → list of texts |
| `call escape from re with …` | `re.escape` | `text` → text |
| `call matches from re with …` | `re.search(...) is not None` | `pattern`, `text`, optional `flags` → boolean |

**Naming decision — make `match` honest.** Keep Python's mapping (`match` =
prefix-only, `search` = anywhere) because the whole language is grounded in
Python and the oracle is Python's `re`. Add the alias `match at start` for
`match` and `find match` for `search` so intent is visible; document in one
sentence in REFERENCE §9 that `match` does **not** search the whole string.
`call new pattern from re with …` (`re.compile`) is **deferred**: llang has no
pattern value type, and CPython already caches compiled patterns. All functions
take `pattern` text; a later map handle `{"pattern": …, "flags": …}` can be
introduced additively without changing call sites.

**Result representation.** A successful match is an insertion-ordered map with
five fixed keys (mirror of `Match` in **[RE]** "Match objects"):

```
{
  "matched": <text>,                       # m.group(0)
  "start":   <number>,                     # m.start()
  "end":     <number>,                     # m.end()
  "groups":  <list of text or nothing>,    # m.groups(); None -> nothing
  "named":   <map name -> text or nothing> # m.groupdict(); insertion order
}
```

No match is `nothing`, so `… is nothing` is the idiom. A non-participating
group is `nothing` inside `groups`/`named`. This uniformly replaces
`findall`'s shape polymorphism and avoids inventing tuple values.

**Flags.** No bitwise operators exist in llang, so flags are a **list of closed
vocabulary texts**, mapped 1:1 to **[RE]** flags:

| llang flag text | Python flag |
|---|---|
| `"ignore case"` | `re.I` |
| `"multiline"` | `re.M` |
| `"dot all"` | `re.S` |
| `"verbose"` | `re.X` |
| `"ascii"` | `re.A` |

```llang
use the foreign re module
set flags to a list of "ignore case", "dot all"
set first to call search from re with pattern = "\\bcat\\b", text = line, flags = flags

if first is nothing then
    show "not found"
otherwise
    show item "matched" of first
    show item "start" of first
end if

set all to call find all from re with pattern = "(\\w+)=(\\d+)", text = line
repeat for each m in all
    show item "groups" of m
end repeat

set cleaned to call replace from re with pattern = "\\d+", text = line, replacement = "#"
```

**Errors.** Host `re.error`/`PatternError` is caught and re-raised as a
source-located `ProblemSignal("invalid_pattern", reason)`; unknown flag text →
`invalid_flag`; wrong argument type → `bad_argument`. All are catchable with
`expect … if a problem of kind invalid_pattern occurs then …`. This mirrors how
existing builtins wrap `ValueError` (REFERENCE §6) and keeps "no undefined
behavior".

### 2.3 Deliberate divergences from Python `re`

1. `find all` always returns match maps (Python `finditer` shape), never strings/tuples.
2. No compiled-pattern value, no `pos`/`endpos`, no `re.subn`, no `re.purge`.
3. Patterns are ordinary llang strings: regex backslashes must be doubled because
   there is no raw-string literal. A linter warning is proposed for the easy mistake.
4. Pattern syntax subset is closed (§1.1); unsupported extensions fail loudly.
5. Backtracking is unbounded (same as Python) — no step budget in v1.

---

## 3. Verification plan

**Oracle.** Because the interpreter is written in Python, v1's foreign layer can
call `re` directly: differential testing validates the *binding contract*
(label names, escape handling, result-map shape, error kinds), not the engine.
If a native engine is later written, the same corpus becomes a true semantic
oracle. Reference: **[RE]** examples §"Regular expression examples".

**A. Curated differential corpus** (`tests/re_corpus/`, one `.ll` file plus a
Python expectation per case). For each case normalize both sides to a tuple:

- match → `(matched, start, end, tuple(groups), tuple(sorted(named.items())))`
- find all → tuple of the above (from Python `finditer`)
- replace/split → `(string, tuple(list))`
- no match → `nothing` / `None`

Categories, each drawn from documented examples: literals & concatenation;
`.*` vs `.*?` on `"<a> b <c>"`; `a|ab` on `"ab"` (first-branch); `ab*` on
`"a"`, `"ab"`, `"abbb"`; `[0-5][0-9]`, `[a-z]`, `[^5]`, `[-a]`, `[a-]`, `[(+*)]`;
`^`, `$`, `\A`, `\Z`, MULTILINE `^X` on `"A\nB\nX"`; `\b` on `at`, `at.`,
`(at)`, `attempt`; `\d\w\s` vs uppercase negations; named groups and repeated
groups (`(..)+`); `sub('x*','-','abxd')`; empty class matches in `split`;
`findall(r'(\w+)=(\d+)')` shape; `re.escape('https://www.python.org')`.
All five flag combinations plus multi-flag lists.

**B. Escape round-trip tests.** Assert `"\\d+"` in llang source reaches the host
as `\d+`; assert the naive `"\d+"` becomes `d+` (documented trap, so we notice
if escape handling changes); assert `"\\\\"` reaches host as `\\` (literal
backslash) using the **[RE]** raw-string examples.

**C. Error mapping tests.** Patterns `(`, `[a`, `a**`, `\q`, `a{3,2}`,
`(?=x)`, `(?P<n>x)` (unsupported in v1) → expect `invalid_pattern` catchable;
assert the message contains Python's reason text. Unknown flag → `invalid_flag`.
Show that an unhandled one renders `ERROR: Unhandled problem 'invalid_pattern': …`
with the call's source position (REFERENCE §7).

**D. Randomized differential fuzzing.** Generate patterns from the supported
grammar (depth ≤ 3, length ≤ 12) and texts over `a`, `b`, `1`, ` `, `\n`, `é`;
run oracle `re.search`/`finditer`/`sub` and the llang calls; compare normalized
results; minimize any mismatch with delta debugging. Bound text length and add a
watchdog to avoid catastrophic-backtracking hangs; skip patterns the oracle
flags as invalid (those go to category C).

**E. Regression + CI.** Add `tests/test_regex_module.py` using `run_source`,
asserting `interp.output` and direct return values; add the corpus as fixtures;
include a linter test for the single-backslash warning. **Not** in CI: a
documented catastrophic-backtracking demo (`(a+)+$` on `"a"*25 + "b"`).

**F. Documentation gate.** Every supported construct's row in §1.1 must have at
least one passing corpus case; every gotcha in §1.2–§2.3 must have either a test
or an explicit "documented, no test" note in REFERENCE §9.
