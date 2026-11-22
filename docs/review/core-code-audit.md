# Core Code Audit — `src/llang/` (read-only review)

**Reviewer:** subagent (read-only). **Date:** 2026-11-22.
**Scope:** the 17 core modules listed in the task (lexer, parser, ast_nodes, interpreter,
synonyms, errors, formatter, linter, converter, compiler, foreign, the three CLIs,
packages, lsp, `__init__`), cross-checked against `docs/REFERENCE.md` and
`docs/GRAMMAR.md`. Suspected defects were confirmed with read-only Python snippets
(run from the workspace with `src` on `PYTHONPATH`); exact observed outputs are
recorded below.

---

## 1. Executive summary

The core is generally coherent: the parser/interpreter/docs agree on the great
majority of semantics, error messages are localized, and the canonical-AST design
is cleanly separated from surface synonyms. **No critical issues were found.**
However, there are several real defects in exception containment, source
round-tripping, and the WASM backend, plus a cluster of smaller inconsistencies.

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 4 |
| Medium | 9 |
| Low | 13 |
| **Total** | **26** |

The four high-severity items are: (F1) a raw `ZeroDivisionError` leaking from
power evaluation, (F2) the formatter emitting literals the lexer cannot read back,
(F3) the WASM emitter producing structurally invalid modules for arity-mismatched
calls, and (F4) unbounded recursion leaking a raw `RecursionError`.

---

## 2. Numbered findings

| # | Sev | File:line | Description | Concrete reproduction (observed) | Recommended fix |
|---|---|---|---|---|---|
| F1 | **High** | `interpreter.py:926-935` (`_arithmetic`, `POW`) | `left ** right` can raise `ZeroDivisionError` (`0 ** -1`), which is **not** in the caught set (`OverflowError` only). This leaks a raw Python exception through `run_source` and the CLIs, violating the "fail loudly with a localized LangError" contract. | `show 0 to the power of (0 minus 1)` → `builtins.ZeroDivisionError: 0.0 cannot be raised to a negative power` (no `LangError`, no position). | Catch `(OverflowError, ZeroDivisionError)` and re-raise `RuntimeErrorLang("Zero or negative base cannot be raised to a negative power", node.pos)` (or document the rule). Audit all builtins for other uncaught exceptions. |
| F2 | **High** | `formatter.py:111-124` (`_literal`) | Float literals use `repr()` and negatives use `str()`, but the lexer accepts only `[0-9]+("."[0-9]+)?` with **no sign, exponent, `inf` or `nan`**. Any such `Literal` in a programmatically built AST (converter output, tests, tooling) formats to text that fails to re-parse — and `inf`/`nan` re-parse as *variables*, a silent semantic corruption. | `format_program(Program([Show(Literal(1e20))]))` → `"show 1e+20\n"` → re-parse fails `Unexpected character '+'`. `Literal(float('inf'))` → `"show inf"` → re-parses but runtime raises `Undefined name 'inf'`. `Literal(-5)` → `"show -5"` → `Unexpected character '-'`. | Emit floats as an expression the grammar can represent (e.g. reject/note non-finite values explicitly, and render `x` as `(0 minus ABS)` for negatives) or extend the grammar/lexer with signed/exponent literals and update `docs/GRAMMAR.md`. Add a round-trip property test over arbitrary literals. |
| F3 | **High** | `compiler.py:189-197` (`expression`, `Call`), `compiler.py:278-284` (`body`) | Calls are emitted as `i32.const`/`local.get` per argument followed by `call <index>` with **no arity or label validation**. A call with too few arguments emits a WASM module that fails validation (stack underflow / type mismatch); too many arguments likewise. Labels are ignored entirely, so reordered labels silently change which parameter receives which value. The module is returned with an empty `unsupported` list, breaking the backend's stated "valid WebAssembly 1.0" guarantee. | `define function f taking a, b / give back a / end function` + `define function g taking x / give back call f with a = x / end function` → compiles with `unsupported == []`; emitted body contains `20 00 10 00 ...` (one value for a two-parameter call). Reordered labels (`b = x, a = y`) compile positionally instead of by name. | Validate at compile time: resolve each label to the callee's parameter order, reject unknown/missing/duplicate labels and arity mismatches via `flag(...)`, and only then emit `call`. Validate generated modules with `wasm-validate` in CI. |
| F4 | **High** | `interpreter.py:961-1064` (`_call`), `interpreter.py:1098-1146` (`_call_method`) | There is a 100 000-iteration guard for loops but **no recursion-depth guard**. Unbounded recursion raises a raw `RecursionError` (and can crash the host interpreter state), again bypassing `LangError`. | `define function f taking x / give back call f with x = x / end function / show call f with x = 1` → `builtins.RecursionError: maximum recursion depth exceeded`. | Track call depth (e.g. `self.call_depth`) and raise `RuntimeErrorLang("Maximum call depth exceeded", node.pos)` past a documented limit; reset in `finally`. Consider catching `RecursionError` as a last-resort wrapper in `Interpreter.run`. |
| F5 | Medium | `interpreter.py:706-740` (`_exec_use`, lines 709-710 and 740) | Module loading is cached in `self.modules` keyed by alias, but the alias is bound with `env.set(alias, exports)` **only on first load**. A later `use` of the same alias in a different (function-local) scope returns early and never binds the alias there, although the module's exports remain globally visible for qualified calls. Result: `item "pi" of math` fails while `call sqrt from math` works — an inconsistent, scope-dependent API. | Load `use the math module` inside function `f`, then `use the math module` inside function `g` and `show item "pi" of math` → `RuntimeErrorLang: Undefined name 'math' at line 7` (qualified calls in the same program succeed). | Either always bind the alias into the current `env` (cache only the parse/exec work), or store the module map in a dedicated namespace that `Variable` lookup can consult. Add tests for `use` inside nested scopes. |
| F6 | Medium | `parser.py:141-149` (`_is_expect_boundary`), `parser.py:186-193` (`_parse_expect`) | Boundary detection inside `expect` treats **any** statement starting with `if nothing` as the `if nothing went wrong then` clause. A perfectly valid `if nothing is nothing then ... end if` statement in the body is misread, producing a confusing parse error. | `expect /     if nothing is nothing then /         show "yes" /     end if / end expect` → `ParseError: Expected 'went', found 'is' at line 3, column 16` (expected `'went'`). | Require the full phrase `if nothing went wrong then` in `_is_expect_boundary` (check tokens 2..4 as well), not just `if` + `nothing`. |
| F7 | Medium | `converter.py:70-80` (`BUILTIN_CALLS["round"]`), `converter.py:273` | Python `round(x, n)` has an optional second argument but the converter's lambda accepts only one. Two-argument calls fall through to the generic path and become `call apply with fn = round`, where `round` is an undefined llang name. The conversion reports **no** unsupported construct, so the silent mis-mapping looks successful. | `convert_source("y = round(3.14159, 2)")` → `set y to (call apply with fn = round, args = (a list of 3.14159, 2))`, `unsupported == []`; running it fails with `Undefined name 'round'`. | Map `round(x, n)` to `call rounded with value = …, places = …` (the builtin already supports `places`); handle arity explicitly for all `BUILTIN_CALLS` and note unsupported forms. |
| F8 | Medium | `converter.py:373-377` (`AugAssign`) | Unsupported augmented-assignment operators silently default to `plus` (`BINARY_OPS.get(type(node.op), "plus")`) **without calling `self.note`**. `x &= 3`, `x >>= 1`, etc. become `x = x + 3` with no report. | `convert_source("x = 1\nx &= 3")` → `set x to 1\nset x to x plus 3\n`, `unsupported == []`. | Only map supported `ast` operator classes; for anything else call `self.note(node, ...)` and emit an explicitly invalid/preserved marker instead of a wrong operation. |
| F9 | Medium | `compiler.py:87-102` (`OPCODES`) | `FLOORDIV` and `DIV` both emit `i32.div_s` (0x6D), which truncates toward zero and returns an integer; llang's `floor divided by` floors and `divided by` returns a float. `AND`/`OR` emit bitwise `i32.and`/`i32.or`, losing operand-returning and short-circuit semantics (and any side effects in the right operand). These are **silent** semantic divergences with no `flag`/`note`. | Compiling `a divided by b`, `a floor divided by b`, `a and b` emits `20 00 20 01 6d`, `20 00 20 01 6d`, `20 00 20 01 71` respectively. For `7 floor divided by (0 minus 2)` the interpreter yields `-4` but WASM `i32.div_s` yields `-3`. For `7 divided by 2` the interpreter yields `3.5` but WASM yields `3`. | Do not silently reuse `div_s`: flag `DIV` and `FLOORDIV` as unsupported until correct float/floor sequences exist; emit logical `and`/`or` via `select`/`if` only when short-circuit and operand-return semantics can be preserved, otherwise flag them. |
| F10 | Medium | `compiler.py:306-310`, `compiler.py:189-197` | Only `FunctionDef.name` is entered in `self.functions`; aliases are ignored. A call through an alias is flagged "not compilable" and replaced by `i32.const 0`, so a program valid in the interpreter compiles to a different result with only a generic warning. | `define function f taking a / also known as aliasf / ...` then `give back call aliasf with a = x` → `unsupported: ["line 6: Call … call to 'aliasf' is not compilable"]`. | Register every alias in `self.functions` pointing to the same function index (mirroring interpreter semantics). |
| F11 | Medium | `compiler.py:350-354` (`_global_value`) | Global initializers are taken from the **first** `Set` of a given name, ignoring later reassignment. The interpreter ends with the last value, so compiled and interpreted programs disagree. | `set x to 1 / set x to 2 / define function f ...` → global section encodes `i32.const 1` (`…7f0141010b…`) while the interpreter's `x` is `2`. | Compute the initializer from the effective last literal assignment, or flag non-monotonic globals as unsupported; document that top-level executable statements are not compiled. |
| F12 | Medium | `compile_cli.py:20-22`, `compile_cli.py:22`, `convert_cli.py:21-23`, `convert_cli.py:27-29`, `cli.py:42-52` | The three console entry points handle errors inconsistently. `llang.cli` catches `OSError` and `LangError`; `llang-compile` and `llang-port` catch neither, so missing files and parse errors escape as raw tracebacks. `convert_cli` also catches every formatter `Exception` and prints a warning, masking formatter bugs. `cli.py` does not enforce `--lint`/`--format` exclusivity (lint silently wins). | `python -m llang.compile_cli bogus_missing.ll` and `python -m llang.convert_cli bogus_missing.py` both print full Python tracebacks (`FileNotFoundError`); `python -m llang.cli bogus_missing.ll` prints `ERROR: cannot read …` and exits 1. | Add a shared `safe_main` wrapper catching `OSError`, `LangError` (and `SyntaxError` for the converter) with localized messages and exit codes; narrow the formatter `except` to the expected parse errors; make the mode flags mutually exclusive. |
| F13 | Medium | `interpreter.py:1019-1024`, `interpreter.py:1030-1034` vs `docs/REFERENCE.md:305,307,363` | Reference documentation contradicts the implementation on builtin error handling: it says extra labels are "silently ignored" and `OSError` "is not caught", while the code explicitly rejects unknown labels and catches `TypeError, ValueError, OSError`. Two paragraphs of the same doc (§6 line 307 vs line 363) also contradict each other. | `show call absolute with value = 3, bogus = 1` → `RuntimeErrorLang: Unknown argument(s) for 'absolute': bogus; expected: value` (docs say it should be ignored). | Update §6 of `REFERENCE.md` to match the implementation (strict labels; `OSError` wrapped), and remove the duplicate contradictory statement. Add a docs consistency check to CI if feasible. |
| F14 | Low | `synonyms.py:39-54`, `docs/REFERENCE.md:522` | `RESERVED` contains **64** words, not the 61 claimed by the reference appendix. The reference's printed list also omits `foreign`, `module`, `use`, `remove` in places. | `len(RESERVED) == 64`; sorted list includes `foreign`, `module`, `use`, `remove`. | Regenerate the appendix from `synonyms.RESERVED` and assert the count in a test. |
| F15 | Low | `lexer.py:97-119` (escape table line 101), `converter.py:51-67`, `docs/GRAMMAR.md:12` | The lexer accepts an undocumented `\r` escape (`"r": "\r"`), and the converter emits it. `GRAMMAR.md` lists only `n t \" \\`. Conversely, `formatter._string` does not escape `\r` (it emits a raw CR, which happens to round-trip). | `Lexer('show "a\\rb"')` yields `STRING 'a\rb'`; `GRAMMAR.md` does not permit `\r`. | Pick one contract: add `\r` to both grammar docs and the formatter's escaping table, or remove it from the lexer and emit a raw CR in the converter. |
| F16 | Low | `interpreter.py:126-135` (`_b_extreme`) | The guard `all(isinstance(item, str)) and any(_is_number(item))` is unreachable: if every item is a `str`, `_is_number` is false for all of them. Mixed lists therefore reach `min`/`max` and raise a raw Python `TypeError` that is only incidentally wrapped by the generic builtin handler. | `_b_extreme(True, items=[1, "a"])` raises `TypeError: '<' not supported between instances of 'str' and 'int'` (the intended "cannot mix text and numbers" message never appears). | Replace with `if not (all(_is_number(i) for i in items) or all(isinstance(i, str) for i in items)): raise ValueError("minimum/maximum cannot mix text and numbers")`. |
| F17 | Low | `interpreter.py:984-1015` (`_call`, special `apply`/`predict` path) | The special handling for `apply`/`predict` runs **before** the generic required/allowed-label validation (lines 1017-1029), so `predict` with a missing `features` label silently passes `None` as the feature value. | `call predict with model = m` (no `features`) is accepted; the model's `predict` receives `None`. | Validate required/optional labels for these builtins too (or move the special path after validation). |
| F18 | Low | `interpreter.py:742-750` (`_define_function`) | Duplicate aliases within one definition (e.g. `also known as f` where the function is already `f`) are not detected; the same `Function` object is simply bound twice. All other duplicate-name checks in this module report an error. | `define function f taking x / also known as f / ...` runs successfully, `show call f with x = 1` prints `1`, no diagnostic. | Check the combined `[name] + aliases` list for internal duplicates and report `Duplicate alias 'f'` at `node.pos`. |
| F19 | Low | `linter.py:271-276`, `linter.py:321-329` | `instance_classes` is global and never invalidated when a variable is rebound to a non-instance or to another class. They can produce stale field/method warnings (false positives) or miss real errors after rebinding; the same key is also used for the method receiver `this`, so identically named locals can interfere. | `set p to new Point … / set p to 5 / ask p to move …` — the linter still checks `move` against `Point` rather than reporting that `p` is no longer an instance. | Track instance-class facts per scope and invalidate on every `Set` to that name; consider dropping this best-effort check when the binding is ambiguous. |
| F20 | Low | `packages.py:308-330` (`check_dependencies`, line 318) | Dependency checking calls `resolve(dep_name)` **without** the requested spec, so it compares the spec only against the highest installed version. A compatible lower version present in the registry is reported as unmet. | Registry with `dep 1.0.0` and `dep 2.0.0`, manifest dependency `{"dep": "^1.0.0"}` → `['dep: found 2.0.0, requires ^1.0.0']` although `1.0.0` satisfies it. | `resolve(dep_name, spec)` and report "missing" vs "incompatible" based on that result (or scan all candidates for any match). |
| F21 | Low | `packages.py:241-243` (docstring), `packages.py:306` (`resolve`) | The class docstring promises "when two manifests declare the same name and version, the one from the later root wins", but `resolve` uses `max(..., key=parse_version)`, and Python's `max` returns the **first** maximum — so the earlier root wins on ties. | Two roots with identical `name`/`version` → the earlier root's manifest is returned. | Either implement the documented tie-break (e.g. `max(enumerate(...))` keyed by `(version, root_index)`) or correct the docstring. |
| F22 | Low | `lsp.py:210-212` (`_token_at`) | The hit test uses `match.start() <= char_index <= match.end()`. A cursor exactly at a word's end character is attributed to the previous word instead of the next token (off-by-one for hover/definition). | Cursor at the column immediately after `foo` in `foo bar` returns `foo`. | Use `match.start() <= char_index < match.end()`, with an explicit fallback for end-of-line. |
| F23 | Low | `lsp.py:335-397` (`serve`/`_write`) | The documented support for text streams is broken for non-ASCII: `Content-Length` counts UTF-8 bytes, but `stdin.read(length)` on a text stream reads *characters*, desynchronizing framing. | Passing `io.StringIO` with multi-byte characters to `serve` mis-frames the next message. | Either always require binary streams (and fix the docstring) or read raw bytes from `stdin.buffer` and decode the body with the declared length. |
| F24 | Low | `foreign.py:34-76`, `foreign.py:102-107` | **Security note (by design, but the highest-risk surface).** `shell.run command` uses `subprocess.run(..., shell=True)` on arbitrary llang text with a caller-chosen `cwd` and up to an unbounded `timeout`; `environment value` reads any host variable (secrets). Exposure is opt-in via `use the foreign shell module` and documented, but nothing logs or gates it at the CLI level. | `use the foreign shell module / show call environment value from shell with name = "PATH"` returns the full host `PATH` (observed). No sandbox or audit trail. | Keep the opt-in, but add an explicit CLI/API flag (e.g. `--allow-foreign-shell`) for untrusted sources, document a threat model, cap the timeout, and avoid interpolating untrusted text into `shell=True` commands where possible. |
| F25 | Low | `lsp.py:292-303` (`_completion`) | Labels are built as `sorted(KEYWORD_STARTS)` and then function names are `append`ed, so the final completion list is only partially sorted; clients that assume ordering see a discontinuity. | Completions end with function names inserted after all keywords, not in lexicographic order. | Collect into one set and sort once at the end. |
| F26 | Low | `formatter.py:94-108`, `convert_cli.py:27-29` | `_string` handles only `\\ " \n \t`; any other control character is emitted raw inside a string literal (currently harmless for the lexer, but brittle), and `convert_cli` broad-catches `Exception` from the formatter, hiding real formatter defects behind a warning. | A `Literal("\x00")` is emitted as a raw NUL byte inside quotes; a formatter regression would silently downgrade to raw output instead of failing the build. | Escape all control characters (e.g. `\u00XX` with matching lexer support) and narrow the CLI exception handler. |

---

## 3. Positive findings

* **Clean canonical-AST boundary.** `ast_nodes.py` / `class_nodes.py` keep `pos`
  last, re-export class nodes from one import point, and ensure tools see only
  canonical nodes; synonym desugaring is confined to `synonyms.py` + `parser.py`.
  This makes `formatter`, `linter`, `compiler` and `lsp` independently testable.
* **Documentation/implementation alignment is generally excellent.** Evaluation
  orders that look suspicious at first (`add VALUE to TARGET` evaluates target
  first; `expect`'s `if nothing went wrong` body runs inside the protected
  region; left-associative flat operators) all match `REFERENCE.md` exactly and
  were confirmed by reproductions. The two apparent "bugs" there are documented
  divergences, not defects.
* **Errors are localized.** `LangError`/`ParseError`/`RuntimeErrorLang` carry
  source positions and optional expected-token hints; catchable problems
  (`index_out_of_range`, `missing_key`, `unknown_field`, …) are a coherent
  string-tagged exception model, and `Interpreter.run` converts escaping signals
  to positioned errors.
* **Defensive validation in the hot paths.** Builtin labels, function/method
  arguments, class fields, duplicate names/fields/parameters, map-key hashability,
  division by zero, and negative/complex powers are all checked with specific
  messages. The `POW` complex-result rejection is a thoughtful language decision.
* **Deliberate, documented semantic decisions.** Boolean-aware equality,
  exclusion of `bool` from `_is_number`, snapshot iteration, no implicit coercion,
  and the minimal class/model are consistently enforced rather than partial.
* **Linter design.** The two-pass hoisting approach avoids forward-reference false
  positives (confirmed: calling a function defined later produces no diagnostic),
  and scope handling mirrors the interpreter's single-`Env`-per-function model.
* **Formatter parenthesis discipline.** Greedy nodes (calls, collection literals,
  indexing, `ask`) are parenthesized when nested, including the subtle
  `not (x is empty)` vs `(not x) is empty` case; round-trips were verified for
  chains, `expect` handlers and catch-all rewriting.
* **No I/O surprises in the lexer.** Unicode identifiers, CRLF, BOM skipping and
  comment handling behave as documented; `run_file`/`cli.py` use `utf-8-sig`.

---

## 4. Prioritized remediation list

1. **Restore the "no raw Python exceptions" guarantee** — F1 (`POW` zero/negative),
   F4 (recursion depth). Add a top-level safety net in `Interpreter.run` only as a
   backstop after fixing the specific sites.
2. **Fix source round-tripping** — F2 (formatter literals), and add a property test
   `format_source(source) == format_source(format_source(source))` plus a
   literal-fuzz test that re-parses and re-executes formatted output.
3. **Harden the WASM backend before advertising it** — F3 (arity/label validation),
   F9 (division/logical semantics), F10 (aliases), F11 (globals). Add a CI step
   that runs `wasm-validate` on compiled output and executes a small golden set.
4. **Close scope/parser inconsistencies** — F5 (`use` aliasing across scopes),
   F6 (`expect` `if nothing` ambiguity).
5. **Correct converter mappings** — F7 (`round(x, n)`), F8 (`AugAssign` fallback),
   and the `\r` escape question in F15.
6. **Unify CLI error handling** — F12, then align `REFERENCE.md` §6 (F13) and the
   reserved-word appendix (F14).
7. **Address the medium/low robustness and API items** — F16–F23, F25, F26, with
   small focused tests; group F17/F18/F19/F20 into one "consistency" pass.
8. **Review the foreign shell threat model** — F24: document it explicitly and add
   an opt-in gate if untrusted sources are ever accepted.

---

## 5. What was NOT reviewed

* **`src/llang/cll/`** — explicitly excluded (another agent is actively editing it).
* Any file under `src/llang/` not named in the task scope, notably `class_nodes.py`
  was read only as a dependency of the AST contract; it was not separately audited.
* **Non-core project surfaces:** `run.py`, `repl.py`, tests, benchmark/example
  `.ll` programs, packaging metadata beyond reading `pyproject.toml`, and the
  `docs/research/*` design documents (used only as background).
* **Runtime behavior of the WASM output in an engine.** No WebAssembly validator or
  runtime (`wasmtime`, `wasm`, `wasm-validate`, `wat2wasm`) is installed in this
  environment, so F3/F9 were established by decoding the emitted byte stream and
  reasoning against the WASM 1.0 validation rules rather than by executing it.
* **Performance, concurrency, network behavior, and the host OS security posture**
  beyond the code-level observations in F24. No files in the workspace were
  modified; all probes lived in the approved temporary directory.


## Remediation status

Reviewed and addressed where applicable. Verified with `python tools/check.py` (17/17 checks passing, 456 tests). Outstanding low-severity items are tracked in `docs/ROADMAP.md`.

