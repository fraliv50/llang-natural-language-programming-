# Rewrites of open-source Python software

This page records each real Python module we re-express in llang and verify against
the original. It is the practical test of `METHOD.md`. Every rewrite follows the
same pattern: `lib/<name>.ll`, `tests/test_<name>.py`, `tools/compare_<name>.py`,
and a differential comparison against the Python stdlib.

## Summary

| # | Module | llang implementation | Differential corpus | Result |
|---|---|---|---|---|
| 1 | CPython `shlex` | `lib/shlex.ll` | 59 cases | 0 mismatches |
| 2 | CPython `fnmatch` | `lib/fnmatch.ll` | 85 cases | 0 mismatches |
| 3 | CPython `textwrap` | `lib/textwrap.ll` | 240 cases | 0 mismatches |
| 4 | CPython `csv` (default dialect) | `lib/csv.ll` | 57 cases | 0 mismatches |
| 5 | CPython `json` (native, no bridge) | `lib/json.ll` | 95 cases | 0 mismatches |
| 6 | CPython `re` (first useful subset) | `lib/re.ll` | 118 cases | 0 mismatches |
| 7 | `pylev` 1.3.0 (BSD-3-Clause) | `lib/pylev.ll` | 222 cases | 0 mismatches |
| 8 | `humanize` number formatting (MIT) | `lib/humanize.ll` | 227 cases | 0 mismatches |
| 9 | `pypybox2d` physics engine (zlib) | `lib/box2d.ll` | 1,113 cases | 0 mismatches |

The engine rewrite is the largest port so far: a headless 10.5k-line pure-Python
physics engine reduced to a working llang subset (math primitives, geometry,
circle collision, gravity, semi-implicit Euler world step) that reproduces the
original's 60-step falling-body trajectory byte-for-byte. Provenance and the
documented omissions are in `tools/rewrites/pypybox2d/SOURCE.md`.

Provenance for the external repos is in `tools/rewrites/pylev/SOURCE.md` and
`tools/rewrites/humanize/SOURCE.md`. Both rewrites are pure llang; only the
allow-listed foreign math module supplies correctly-rounded primitives where
needed.

**What "compiles" means here:** a rewrite "compiles" when it parses, lints clean,
and runs under the interpreter producing output identical to the original module
on the test corpus. The primary execution path is the interpreter; the WASM
backend (see §6) covers the integer/function subset and is verified separately.

## 1. `shlex` — shell-like word splitting

- Source: CPython 3.11 `Lib/shlex.py` (PSF license)
- Scope: POSIX `split()`, `quote()`, `join()` with `whitespace_split=True`, no comments
- Not copied: the streaming class interface, pushback/source stack, punctuation chars, non-POSIX mode, `sourcehook`, debug tracing
- Integration: `lib/shell.ll` uses `shell_join` for safe command construction

## 2. `fnmatch` — wildcard matching

- Source: CPython 3.11 `Lib/fnmatch.py` (PSF license)
- Scope: `fnmatchcase` and `fnmatch`, implemented with recursion and character indexing — `*`, `?`, `[seq]`, `[!seq]`, ranges, empty strings, unclosed brackets. No regex, no slicing
- `fnmatch` lowercases both arguments, matching Windows `os.path.normcase` behaviour on our test host
- Not copied: `re`-based pattern compilation, `functools.lru_cache`, `os.path` helpers, `filter`, `purge`

## 3. `textwrap` — word wrapping

- Source: CPython 3.11 `Lib/textwrap.py` (PSF license)
- Scope: `wrap` and `fill` with greedy filling, whitespace chunking, long-word breaking, boundary whitespace dropping
- Not copied: `expand_tabs`, `replace_whitespace`, `break_on_hyphens`, indent/placeholder/max_lines, `TextWrapper` class

## 4. `csv` — comma-separated values

- Source: CPython 3.11 `Lib/csv.py` semantics (PSF license)
- Scope: `read_rows` and `write_rows` for the default Excel dialect — quoted fields, doubled quotes, embedded newlines, CRLF/LF endings, quote-only-when-needed writer
- Not copied: dialect registry, Sniffer, DictReader/DictWriter, QUOTE_* modes

## 5. `json` — native parser and serializer

- Source: CPython `json` semantics (PSF license)
- Scope: `parse` and `stringify` with the full value model, string escapes, `\uXXXX` including surrogate pairs, numbers/exponents, whitespace, and compact output matching `json.dumps(..., ensure_ascii=False)`
- No host calls: the module is pure llang, unlike the earlier `use the foreign json module` bridge, which remains available for host interop

## 6. WebAssembly backend

- Implementation: `src/llang/compiler.py` compiles a supported subset of the canonical AST into a valid WebAssembly 1.0 binary
- Scope: integer values, variables/globals, arithmetic, comparisons, boolean ops, user functions, `if`, `while`, `break`, `continue`, `return`
- Verification: `tests/test_compiler.py` executes the emitted `.wasm` in Node's WebAssembly runtime and compares results
- Unsupported constructs (text, lists, maps, builtins, foreign calls) are reported explicitly
- `tools/playground/` provides a browser playground that compiles llang to WASM through a small local server

## 7. Automated Python → llang converter

| Item | Detail |
|---|---|
| Implementation | `src/llang/converter.py` — parses with Python's real `ast`, emits llang source |
| CLI | `llang-port file.py -o ported.ll --report report.txt` (also `python tools/port.py ...`) |
| Tests | `tests/test_converter.py` — differential tests: convert Python, run llang, compare to Python's own output |
| Design | Every binary expression fully parenthesized; `is None` → `is nothing`; unsupported constructs reported with line numbers; successful transformations reported separately as notes |

### Pilot coverage

| Python module | Coverage | Remaining gaps |
|---|---|---|
| CPython 3.11 `bisect.py` | **97.3%** | keyword-only parameters, C `_bisect` import |
| `fnmatch.py` with slice/comprehension support | improved | `re`/`os`/`functools`, regex methods, `IfExp` |
| CPython 3.11 `fnmatch.py` | 85.6% | `re`/`os`/`functools`, regex methods, slices, comprehensions, `IfExp` |
| `humanize/filesize.py` | 75.5% | gettext calls, `IfExp`, `float`/`log` builtins |

## Bugs found by doing real rewrites

1. **Lexer escape gap** — `\r` in a string literal produced the letter `r`; fixed in `lexer.py`.
2. **No-precedence trap** — `a equals b or c equals d` needed explicit parentheses; documented in `SEMANTIC-DECISIONS.md`.
3. **Reserved-word collisions** — Python variables named `add` broke generated code; the converter now renames colliding identifiers.
4. **Formatter greedy-call bug** — zero-argument calls in expression position weren't parenthesized; fixed in `formatter.py`.
5. **Reserved argument label** — `apply` initially used a `function` label, but `function` is reserved; renamed to `fn`.

## What this means for "all Python libraries"

Translation is programmatic; what is not automatic is the semantic gap: C extensions,
regex, classes/generators/async (L2+), and Python-specific quirks. The coverage report
tells us exactly where to invest next, module by module. The four native rewrites above
show that pure-Python algorithmic modules can be re-expressed faithfully today.

## Next candidates

- `humanize.number` — number formatting with the existing `rounded`/`to text` builtins
- More `textwrap` options (indentation, `break_on_hyphens`) once the core is stable
- A native `bisect` module using the new `floor divided by` operator and `insert into` builtin

Anything requiring regex, bit manipulation, or native C extensions should wait for the stdlib/backend work.
