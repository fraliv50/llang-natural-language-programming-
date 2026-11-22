# Test-suite audit (read-only)

Read-only audit performed 2026-11-22 against the working tree at
`D:\natural language code`. No project file was modified; this report is the
only file created. Scope: everything under `tests/` except `tests/test_cll.py`
(being edited by another agent), all `tools/compare_*.py` harnesses,
`tools/fuzz_semantics.py`, `tools/check.py`, and `.github/workflows/ci.yml`.
Source files and `docs/research/test-plan.md` were read only to judge whether
tests are meaningful, never changed.

Baseline: `python -m unittest discover -s tests` was executed with bytecode
writes disabled. **449 tests ran in ~171 s and all passed.** The findings below
are therefore about *coverage, verification strength and reproducibility*, not
about a currently red suite. One benign-but-noisy third-party warning
(joblib/loky cannot count physical cores on this Windows host) is emitted to
stderr by the data-science tests.

## 1. Executive summary

The suite is large and mostly well written: formatter round-trips, class
semantics, stdlib differential corpora and the seeded expression fuzzer are
genuinely useful. However, the verification chain is only green *on this
machine*. A fresh checkout is very likely to fail `tools/check.py`/CI because
the test-only third-party dependencies are undeclared and one required oracle
lives inside a nested git repository that a clone will not contain. CI also
runs a single OS and Python version, so the Windows console-encoding class of
bugs the project has already seen cannot be caught there.

Within the tests themselves the dominant pattern is **weak assertions on
strong-looking tests**: a UTF-16 test that only checks that a response exists,
a fuzz test that asserts a count is >= 0, differential harnesses that compare
with `zip` without checking result counts, and stdout substring assertions that
pin the exact number of corpus cases. None of these fail today, but none would
detect the regression their name advertises.

No test was found that confidently pins *incorrect language semantics as
correct*. The closest problems are verification that can mask a wrong result
(differential normalization in the converter test, harness `zip` truncation,
boolean/error-relaxing normalizations) and assertions that are vacuous
(UTF-16, rubiks file existence, skipped-case count).

| Severity | Count |
|---|---|
| High | 4 |
| Medium | 17 |
| Low | 6 |
| **Total** | **27** |

## 2. Numbered findings

| # | Sev | File:line | Problem | Impact | Recommended fix |
|---|---|---|---|---|---|
| 1 | High | `pyproject.toml:15-24`; `.github/workflows/ci.yml:15-18`; `tests/test_machinelearning.py:21-30`; `tools/compare_ml.py:18-30`, `tools/compare_datascience.py:18-19` | Test/oracle dependencies (scikit-learn, pandas, NumPy) are not declared anywhere; CI only runs `pip install -e .`. `test_machinelearning.py` imports sklearn at module scope, so discovery itself fails when it is absent; the ML/data-science harnesses import it at startup. | A clean CI runner (setup-python toolcaches do not ship these packages) cannot collect or run the suite; the local green run is not reproducible. | Add a pinned `[project.optional-dependencies] test = [...]` extra and install it in CI (`pip install -e '.[test]'`). |
| 2 | High | `tools/check.py:78-84`; `tools/compare_box2d.py:22`, `28-29`; `tools/rewrites/pypybox2d/source/.git` | `check.py` always runs `compare_box2d.py`, which raises `RuntimeError` if the pinned pypybox2d source tree is missing. That tree is a nested git repository (`.git` directory present) and is not absorbed into the parent checkout. | Fresh clone → `check.py` and CI fail at the box2d harness regardless of code quality. Mirrors the nested-repo finding in `docs/review/provenance-audit.md`. | Flatten/vendor the oracle as normal tracked files (or fetch a pinned commit in a dedicated CI step); make the harness fail with an explicit setup message, not a generic runtime error. |
| 3 | High | `.github/workflows/ci.yml:9`, `12-14`, `19-23` | Single job: `ubuntu-latest` + Python 3.11 only, despite `requires-python = ">=3.10"`. Node is assumed preinstalled; no `timeout-minutes` on the job; no Windows job. | Python 3.10/3.12+ regressions and every platform-specific behavior (cp1252 console, `echo`/CRLF, path separators) are invisible. A hang in any subprocess (finding 4) can burn the full default 360-minute job timeout. | Matrix over Python 3.10/3.11/3.12 (and 3.13 if supported) × ubuntu/windows; explicitly set up Node with a pinned version; add `timeout-minutes: 15`. |
| 4 | High | `tools/check.py:20`, `65`; harnesses `compare_box2d.py:333`, `compare_csv.py:133`, `compare_datascience.py:647`, `compare_fnmatch.py:89`, `compare_humanize.py:466`, `compare_json.py:92`, `compare_math.py:309`, `compare_ml.py:238,254`, `compare_pylev.py:86`, `compare_re.py:327`, `compare_shlex.py:86`, `compare_textwrap.py:92`, `compare_wasm.py:54`; tests `test_advanced_math.py:220,229`, `test_box2d.py:230`, `test_compiler.py:28`, `test_csv.py:150`, `test_datascience.py:306,314`, `test_fnmatch.py:105`, `test_humanize.py:126,134`, `test_json_native.py:117`, `test_machinelearning.py:408`, `test_pylev.py:487`, `test_re.py:170`, `test_shlex.py:46`, `test_textwrap.py:86` | No `subprocess.run(...)` call in the entire test/harness/CI verification path specifies `timeout=`. The language's own shell bridge *does* enforce a 30 s timeout (`src/llang/foreign.py:34-52`), but the harnesses that drive the interpreter do not. | One hung interpreter, Node process or C compiler hangs the whole suite indefinitely; no useful diagnostic. | Add explicit `timeout=` to every subprocess call and convert `TimeoutExpired` into a labeled failure; centralize via a shared helper used by `check.py` and the harnesses. |
| 5 | Medium | `compare_shlex.py:99,108,114`; `compare_fnmatch.py:102`; `compare_textwrap.py:105`; `compare_csv.py:146,152`; `compare_json.py:112-117`; `compare_re.py:340`; `compare_ml.py:280,296,313,327,342,353,366`; `compare_datascience.py:661` | Harnesses iterate `zip(CASES, results[...])`. If the llang side writes fewer entries, `zip` silently stops at the shorter list; the printed total still uses `len(CASES)`, so "compared N cases, 0 mismatches" is printed even though tail cases were never compared. `compare_math.py:320` and `compare_humanize.py:477` are the only harnesses that check counts. | A truncated or partially failing harness can pass, hiding real mismatches; the headline count is misleading. | Assert `len(results[key]) == len(CASES)` for every result list before zipping (as math/humanize already do); report the number actually compared. |
| 6 | Medium | `tests/test_re.py:177`; `tests/test_humanize.py:140`; `tests/test_fnmatch.py:112` | Tests assert exact corpus sizes in harness stdout (`"118 cases"`, `"227 cases"`, `"85 cases"`). This pins an implementation detail of the harness, and a substring assertion would still pass if the harness printed the constant but compared zero cases. | Adding cases — a coverage improvement — breaks tests; the assertion provides no evidence that cases ran. | Remove exact-count strings; assert harness return code plus a count check inside the harness (finding 5), or parse the count and assert `> 0`. |
| 7 | Medium | `tests/test_converter.py:18-31` (esp. 23-30), `35-39` | The differential normalizer rewrites Python stdout with `.replace("True","true").replace("False","false")` and strips every `'...'` pair with a regex. This operates on arbitrary program output, not on typed values. A genuine semantic bug can be normalized away: Python `print("True")` (a *string*) becomes `true`, so a converter that emitted boolean `true` would pass; stripping quotes can likewise erase a dropped-quote bug. | Correctness bugs in string/boolean conversion can be silently accepted as "matching Python". It can also cause false failures for strings containing `True`/quotes. | Normalize at a typed boundary (compare parsed values or `repr` with explicit type tags), never with blind substring replacement on rendered output; add negative tests that prove the normalizer rejects a wrong type, mirroring `test_fuzz_semantics.py:73-85`. |
| 8 | Medium | `tests/test_fuzz_semantics.py:63-71`; `tools/fuzz_semantics.py:39-43`, `238-282`; `tools/check.py:83` | `assertGreaterEqual(report.skipped, 0)` is a tautology. The fuzzer is always run with one fixed seed and 500 cases, and its grammar covers only integer/boolean expressions — no strings, floats, lists, maps, variables, functions or statements. `evaluate_case` also catches only `LangError`, so an unexpected host exception aborts the run rather than being reported as a mismatch. | "Property-based differential testing" is much narrower than advertised; the skip path is unverified; a single seed can miss whole bug classes; harness crashes are mislabeled. | Assert a known nonzero skip count for a crafted seed (or inject explicit division-by-zero cases); run several seeds in CI; broaden the grammar incrementally; catch `Exception` in `evaluate_case` and record it as a mismatch. |
| 9 | Medium | `tests/test_lsp.py:98-104` | `test_utf16_offsets_for_non_bmp_characters` opens a document containing an emoji, requests hover, and only asserts `assertIn("result", response)`. No character offset, range or content is checked. | UTF-16 position conversion — a subtle, high-risk LSP feature — is effectively untested; any offset regression passes. | Assert the exact hover range/contents at a position after the emoji (and a second position inside it), using the `_location`/`_position` helpers already defined. |
| 10 | Medium | `tests/test_core.py:123-125`; `tests/test_lsp.py:189-193`; `docs/research/test-plan.md:178-217`, `536-571`, `707-722`; `src/llang/lexer.py:101`, `104-117` | The documented lexer/parser/diagnostic suites (`test_lexer.py`, `test_parser.py`, `test_diagnostics.py`, `tests/_helpers.py`, fixtures) do not exist. Only spot checks are present. Uncovered escapes: `\r`, unknown escape fallback (`"a\qb"` → `aqb`), unterminated string at EOF vs at newline, trailing backslash, single-quote rejection. Parser error catalog (34 exact messages, hints, line/column) is unasserted. Reserved words: only `set end to 5`; no table over `RESERVED`, no pin of the known "operator words are not reserved" behavior (`equals` as identifier). | Lexer/parser regressions and diagnostic-quality regressions are silent; error text is part of the spec but unverified. | Implement the planned suites/helpers/fixtures with `subTest` tables; at minimum add the escape, reserved-word and exact-message tables from `test-plan.md` §3.3, §3.5, §4.2, §7.1. |
| 11 | Medium | `tests/test_collections.py:32-36`, `38-56`; `docs/research/test-plan.md:492`, `497`; `src/llang/foreign.py` n/a | `test_mutation` mutates one variable; there is no list/map aliasing test (`set b to a` then mutate), no snapshot-on-mutation iteration test, no unhashable-key or duplicate-key-last-wins test. Class instances *are* aliasing-tested (`test_classes.py:195-215`), so the gap is specific to plain collections. | Core reference-semantics and the documented deliberate divergence from Python's live iterator can regress undetected. | Add `test_coll_aliasing_via_binding`, `test_coll_foreach_snapshot_on_mutation`, map key edge cases from `test-plan.md` §6.6. |
| 12 | Medium | `tests/test_collections.py:118-148`; `tests/test_formatter.py:181-192` | Exception coverage is one handler kind + else + always + unhandled. Missing: nested `expect`, several handlers, handler ordering, an exception raised inside a handler or `always`, generic `if a problem occurs`, `fail` from inside a function, interaction with `require`. | The exception subsystem — the newest core feature — has thin edge coverage. | Add the §9.1 cases from `test-plan.md`, plus at least one nested/`always`-failure case. |
| 13 | Medium | `tests/test_collections.py:80-115`; `tests/test_language_additions.py:21-26`; `docs/research/test-plan.md:504-527` | No table-driven `test_builtins.py`; only a handful of the registered builtins are exercised, and mostly on happy paths. Missing per-builtin error cases (`split` empty delimiter, `sort` mixed types, `read_file`/`write_file` round-trip, `to_number` failure, empty-list `minimum`/`maximum`) and registration assertions. | Builtin contracts and their wrapped error messages are under-tested. | Add the 20-row builtin table from `test-plan.md` §6.7 with type/error variants. |
| 14 | Medium | `tests/test_linter.py` (whole file, e.g. 78-127, 130-164, 206-225); `docs/research/test-plan.md:656-676` | Linter tests cover undefined names, duplicates, unreachable code, shadowing and `require`. Missing planned diagnostics: duplicate `set` in one block, duplicate argument label, `stop the loop` outside a loop, reserved-word identifier, ambiguous collection-literal argument list, no-false-positive sibling functions. | Static-analysis diagnostics can regress or produce false positives unnoticed. | Add the §11 diagnostic cases with exact code/severity/position assertions. |
| 15 | Medium | `tests/test_modules.py` (whole file); `docs/research/test-plan.md:628-629` | Module tests cover load, aliases, unknown names/exports and double load. Missing: import side effects/order, export isolation between modules, cyclic imports, path resolution failures, and the documented `take x from m` snapshot semantics if implemented. | Module-system edge behavior is unverified. | Add targeted module fixtures (temp library dirs) for cycles, shadowing and snapshot semantics. |
| 16 | Medium | `tests/test_formatter.py:15-36`, `51-55`, `203-228`, `244-250` | Round-trip tests compare ASTs after stripping positions but never execute original vs formatted source (the documented `test_format_preserves_semantics` is absent). `ALL_NODE_TYPES` is derived from `vars(ast_nodes)` only (`obj.__module__ == ast_nodes.__name__`), so class-node dataclasses in `class_nodes.py` are not part of the "covers every node type" gate (they have a separate round-trip in `test_classes.py:398-411`). | A formatter change that preserves AST shape but changes rendered semantics would pass; the node-type gate gives false confidence. | Add `run(original) == run(formatted)` over the corpus; build the node-type registry from both `ast_nodes` and `class_nodes`. |
| 17 | Medium | `tools/compare_json.py:110`; `compare_shlex.py:106`; `compare_re.py:354-355`; `tests/test_json_native.py:78,82`; `tests/test_lsp.py:99` | Failure paths print non-ASCII case data (`"café au lait"`, emoji, CJK) with `print(repr(...))`. On Windows, a child process whose stdout is a pipe uses the locale encoding (cp1252); printing a mismatch containing an emoji can raise `UnicodeEncodeError` in the harness and mask the real diff. unittest failure reports containing emoji source lines are exposed to the same risk. `compare_humanize.py:498` already uses `ascii()` correctly — the practice is inconsistent. | Exactly when a differential check fails on Unicode, the failure report can crash; matches the cp1252 problem the project has already seen. | Set `PYTHONIOENCODING=utf-8` in child environments (or `sys.stdout.reconfigure(...)` in harness entry points), and use `ascii()`/backslashreplace for all failure messages; add a Windows CI job (finding 3). |
| 18 | Medium | `tests/test_compiler.py:20`, `22-33`, `109-121`; `tools/compare_wasm.py:34-37`, `54-63` | Gating is inconsistent: compiler unit tests silently skip when Node is missing, while `compare_wasm.py` hard-fails. The corpus is 10 small programs; there is no unsupported-construct matrix beyond one case; subprocesses have no timeout (finding 4). `compare_wasm.py:60-63` maps any wasm `1`/`0` to the expected boolean, so a "truthy int" regression would be accepted. | Compiler coverage depends on the runner image; a broken compiler can be entirely unverified in some environments; narrow differential semantics. | Provision Node explicitly in CI, align skip/fail policy, add `timeout=`, and add cases for each supported operator plus a table of unsupported constructs. Verify wasm booleans are exactly 0/1 independently of the expected value. |
| 19 | Medium | `tools/compare_ml.py:261-263`; `tests/test_machinelearning.py:3` | The ML oracle hard-fails unless scikit-learn is exactly `1.8.0`, while the dependency is undeclared (finding 1). Any other installed version fails `check.py` with a version message. | Reproducibility is an accident of the local environment; upgrades require editing the harness. | Pin the version in the test extra (finding 1) or accept a documented compatible range with per-version oracle deltas. |
| 20 | Medium | `tests/test_converter.py:41-148`, `133-148`, `150-153` | Converter tests cover ~12 constructs but not nested functions, default args, negative-step slicing, comprehensions (beyond "unsupported"), or dict/list edge cases. `test_unsupported_report` accepts either a "slice steps" or generic "slicing" reason (`or`), and `test_coverage_is_reported` pins `covered == 100.0` for a trivial program. | Mapping regressions and coverage-metric changes are not distinguished; one lenient assertion accepts two different diagnostics. | Add mapping cases from a documented conversion table; assert the specific reason string per unsupported node type; assert `covered > 0` rather than an exact percentage unless the formula is specified. |
| 21 | Medium | `tests/test_shell.py:19-84`; `tests/test_end_to_end.py:44-57`; `src/llang/foreign.py:34-52`, `103-105` | Shell tests rely on external `echo` and assume POSIX rendering (`"hello\n"`), plus a magic nonexistent command name. The bridge's documented `timeout` and `directory` parameters (and numeric-timeout validation) have no tests; non-ASCII command output is untested. | Platform-dependent behavior (CI is Linux-only) and the safety-relevant timeout path are unverified; a future Windows job would see CRLF/quoting differences. | Drive commands with `sys.executable -c ...` for deterministic cross-platform output; add tests for `timeout`, `directory`, invalid timeout types, and UTF-8 output. |
| 22 | Low | `tests/test_end_to_end.py:71-76` | `test_rubiks` writes `rubiks.html` into the repository root and asserts only that the file *exists*. The file is already present in the tree (and is gitignored), so the assertion passes even if the program wrote nothing or wrote wrong content. The test also mutates the working tree. | A vacuous assertion plus a side effect in a "read-only" suite; stale artifact can mask a broken generator. | Run the example in a temp directory, remove any pre-existing artifact, and assert exact file contents (not just existence). |
| 23 | Low | `tools/check.py:18-31`, `33-52` | `run()` prints only the last 12 merged stdout/stderr lines, which can hide the first/root error. `check_links()` applies a raw regex to every `.md` file including vendored docs and fenced code blocks, does not resolve fragments/anchors, and would flag legitimate relative links containing parentheses. | Harder diagnosis of failures; false positives/negatives in link verification. | Keep full output on failure (or write it to a log), skip fenced code blocks, and use a small markdown-link parser that handles fragments and parentheses. |
| 24 | Low | `tools/fixtures/sample.ll`, `tools/fixtures/sample.py`, `tools/selfhost/*.report.txt` | Fixtures/reports are not referenced by any test or harness (only mentioned in `docs/research/self-hosting-plan.md:448`); `check.py` does not regenerate or validate them. | Dead artifacts can rot unnoticed; conversion regressions in those paths are invisible. | Either wire them into a converter smoke test or delete them / document them as inert samples. |
| 25 | Low | `compare_shlex.py:41`, `compare_fnmatch.py:59`, `compare_textwrap.py:63`, `compare_csv.py:100`, `compare_json.py:53`, `compare_re.py:319`, `compare_pylev.py:41`, `compare_math.py:300`, `compare_humanize.py:457`, `compare_ml.py:265`, `compare_box2d.py:328` | Harnesses create temp directories with `tempfile.mkdtemp(...)` and never remove them (the few using `TemporaryDirectory` are fine). | Disk accumulation on repeated local/CI runs; no functional failure. | Use `tempfile.TemporaryDirectory()` or register cleanup in `finally`. |
| 26 | Low | `.github/workflows/ci.yml:19-23` | CLI smoke test covers only `llang` (run/lint/format). The `llang-port` and `llang-compile` console scripts declared in `pyproject.toml:27-29` are never exercised. | Broken entry points ship undetected. | Add smoke invocations for both scripts using `tools/fixtures/sample.py` and a small `.ll` file. |
| 27 | Low | `tools/compare_re.py:347-351`; `compare_wasm.py:60-63`; `compare_pylev.py:99-107` | Three deliberate normalizations weaken checks in narrow ways: invalid-pattern reason text is ignored; wasm `1`/`0` is coerced to the expected boolean; both `dameraulevenshtein` and `osadistance` are compared against the same reference function, so swapping the two implementations would pass. | Small but real classes of mismatch are invisible to the differential harnesses. | Compare error *kind plus reason category*; validate wasm integers independently of expectation; use distinct oracles (or cross-check properties) for the two edit-distance variants. |

## 3. Coverage matrix

| Feature area | Tests exist? | Quality / gaps |
|---|---|---|
| Lexer escapes | Partial | `test_formatter.py:64` parses `\n \t \" \\` in a round-trip; `ll_string` helpers escape literals. No token-level or evaluated-value tests for `\r`, unknown escapes, unterminated string/escape, single quotes. **F10** |
| Parser errors | Spot checks only | `test_core.py:71-73`, `test_core.py:123-125`, missing `end class`/`end method` in `test_classes.py:352-362`. Documented 34-message catalog and hint/position assertions absent. **F10** |
| Reserved words | Minimal | Only `set end to 5` (`test_core.py:123`). No table over `RESERVED`, no operator-word-as-identifier pin, no reserved label/param tests. **F10** |
| Mutation aliasing | Partial | Single-variable mutation and class-instance aliasing tested; list/map aliasing and snapshot-iteration cases absent. **F11** |
| Exceptions (`expect`) | Yes, narrow | Handler/else/always/unhandled plus formatter corpus; no nesting, multiple handlers, handler failure, generic `if a problem occurs`. **F12** |
| Modules | Yes, core | Native/foreign/alias/unknown cases solid; no cycles, side effects, export isolation, snapshot imports. **F15** |
| Builtins | Partial | A few happy paths in `test_collections.py`; no full 20-builtin table, weak type/error coverage. **F13** |
| Formatter round-trip | Strong, one gap | AST/idempotence/synonym-canonicalization over a large corpus; no semantics-preservation check; class nodes outside the node-type gate. **F16** |
| Linter diagnostics | Good core, thin edges | Undefined/duplicate/unreachable/shadowing/`require`/positions covered; planned diagnostics missing. **F14** |
| Compiler WASM | Yes, environment-dependent | 10 differential programs + smoke tests; skips without Node, no timeouts, boolean normalization, no unsupported matrix. **F18** |
| Converter mappings | Partial + risky normalization | ~12 constructs; blind string replacement in oracle normalization, lenient unsupported reason, exact coverage pin. **F7, F20** |
| Shell bridge | Core yes, safety params no | `echo`-based POSIX assumptions; `timeout`, `directory`, encoding untested. **F21** |
| Collections / iteration | Good | Lists, maps, indexing, for-each, break/continue, predicates covered; aliasing/snapshot gaps. **F11** |
| Classes | Strong | Construction, methods, aliasing, scope, errors, formatter, linter all covered. No inheritance expected by design. |
| Packages | Strong | Version specs, manifest validation, registry discovery/resolve/dependencies all table-driven. |
| LSP | Good except UTF-16 | Lifecycle, diagnostics, completion, hover, definition well asserted; UTF-16 test vacuous. **F9** |
| Stdlib rewrites (11 harnesses) | Broad corpora, weak plumbing | Good case variety; 8 harnesses lack result-count checks, several lack timeouts, brittle exact-count assertions. **F4, F5, F6, F17** |
| Differential fuzz | Useful but narrow | Seeded, reproducible int/bool expression fuzzing with a positive negative-control test; tautological skip assertion, single seed, no strings/collections. **F8** |
| CI / `tools/check.py` wiring | Present, not reproducible | All harnesses are wired, but dependencies/oracle/platform gaps make the green result local-only. **F1-F4, F19, F23** |

## 4. Prioritized remediation list

**P0 — make the green result reproducible (before trusting CI again)**
1. F1: declare and install pinned test dependencies in `pyproject.toml` and `ci.yml`.
2. F2: vendor the pypybox2d oracle as ordinary tracked files or add a pinned fetch step.
3. F3: add the OS × Python matrix, explicit Node setup, and `timeout-minutes`.
4. F4: add subprocess timeouts everywhere and label timeouts as failures.

**P1 — stop tests from passing when verification is broken**

5. F5: add result-count assertions before every `zip` in a harness.
6. F6: remove exact corpus-size assertions; rely on harness count checks.
7. F7: replace blind string normalization in `test_converter.py` with typed comparison plus a negative control.
8. F9: make the UTF-16 LSP test assert real offsets.
9. F8: fix the tautological fuzz assertion; run multiple seeds; catch all exceptions as mismatches.
10. F22: remove the vacuous rubiks existence assertion and its working-tree side effect.

**P2 — close documented coverage gaps**

11. F10: implement the lexer/parser/diagnostic suites from `test-plan.md` (escapes, reserved words, exact messages).
12. F11-F14: add aliasing, exception, builtin and linter edge cases from §6.6, §9.1, §6.7 and §11 of the plan.
13. F16-F21: formatter semantics check, Windows encoding hardening, compiler gating/corpus, converter mapping table, shell timeout/directory tests.

**P3 — hygiene**

14. F15, F23-F27: module edge cases, better `check.py` diagnostics/link checking, fixture wiring, temp cleanup, CLI entry-point smoke tests, tighter harness normalizations.

Suggested exit criterion: `python tools/check.py` passes from a fresh clone on at least Linux + Windows with Python 3.10 and 3.11, and every differential harness both (a) asserts how many cases it compared and (b) has a negative-control test proving a wrong result is detected.


## Remediation status

Reviewed and addressed where applicable. Verified with `python tools/check.py` (17/17 checks passing, 456 tests). Outstanding low-severity items are tracked in `docs/ROADMAP.md`.

