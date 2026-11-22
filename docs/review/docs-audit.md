# Documentation audit — llang

**Auditor:** documentation subagent
**Date:** 2026-11-22
**Mode:** read-only. No repository file was modified except this report. Verification snippets were executed from the OS temp directory via `python run.py`.

## Scope

Reviewed: `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `LICENSE`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `RELEASE.md`, `pyproject.toml`, all of `docs/` except `docs/CLL.md`, all of `docs/research/`, and `.github/`. Implementation in `src/llang/` and `lib/` was read as ground truth. `docs/review/` (other reviewers) was ignored.

Verification performed: imported `synonyms.RESERVED` and `interpreter.BUILTINS`; executed the README/TUTORIAL/GRAMMAR/REFERENCE/EDITOR-SUPPORT snippets and error cases; ran every differential harness in `tools/check.py`; checked all Python/Markdown links with the repository's own checker; exercised a clean venv with only `pip install -e .`; inspected editor grammars, CI workflow, provenance files, and the third-party clone under `tools/rewrites/pypybox2d/`.

---

## 1. Executive summary

| Severity | Count |
|---|---:|
| **High** | 8 |
| **Medium** | 12 |
| **Low** | 11 |
| **Total** | **31** |

The reference manual is broadly excellent and most runnable examples work exactly as documented (see §3). However, there are several **high-impact factual errors in core documents**: the builtin calling contract in `REFERENCE.md` is wrong in three independent bullets; the "no compiler backend" claim contradicts a shipped, verified WASM backend; the "return in `finally` is forbidden" claim contradicts both the reference and the interpreter; the `slice` builtin is missing from the authoritative builtin tables; a README quickstart command cannot run; the documented "no third-party packages" claim is false for the one verification command CI actually runs; and a claimed pinned-output test exists for only 7 of 10 examples.

Counts of differential cases (including the headline "2,546 cases") are **accurate and were reproduced exactly**.

---

## 2. Numbered findings

### High

| # | Severity | file:line | Claim | Reality | Recommended fix |
|---|---|---|---|---|---|
| H1 | High | `README.md:40` | `python tools/playground/server.js` starts the browser playground. | The file is JavaScript. `python tools/playground/server.js` exits with `SyntaxError: invalid syntax` at line 1 (`// Tiny playground server...`). | Change the quickstart line to `node tools/playground/server.js` and state Node.js as a tool-only prerequisite. |
| H2 | High | `README.md:31`, `CONTRIBUTING.md:7`, `CONTRIBUTING.md:54-56`, `.github/workflows/ci.yml:15-18` | "Python 3.10+ is the only requirement — no third-party packages." CI installs with `pip install -e .` only. | `tools/check.py` runs `compare_datascience.py` and `compare_ml.py`, which `import numpy, pandas` and `import sklearn`. A clean venv after `pip install -e .` has none of them, so `tools/check.py` and CI fail on a clean runner. WASM checks additionally need Node. | Add a `[project.optional-dependencies] dev = [...]` group (numpy, pandas, scikit-learn) and install it in CI; correct the README/CONTRIBUTING requirement wording to distinguish runtime (stdlib-only) from verification (extra packages + Node). |
| H3 | High | `docs/REFERENCE.md:304-305`, `docs/REFERENCE.md:509` | Missing required builtin labels raise ``In call to 'NAME': missing argument 'label'``; extra/unknown labels are "silently ignored (the implementations all accept `**kw`)". | All 57 builtins have `BUILTIN_SPECS`. Actual: `show call trim` → `Missing argument(s) for 'trim': text`; `show call trim with text = " hi ", bogus = 1` → `Unknown argument(s) for 'trim': bogus; expected: text`. The `_arg()` message at `interpreter.py:29` is unreachable through normal calls. | Replace both bullets and divergence #10 with the real validation behavior and exact messages; note that unknown labels are rejected, not ignored. |
| H4 | High | `docs/REFERENCE.md:307`, `docs/REFERENCE.md:513` (contradicted by `docs/REFERENCE.md:363`) | `OSError` from file I/O is "not caught and escapes as a raw Python exception"; "Python `OSError`s are not wrapped as llang errors." | `interpreter.py:1032` catches `OSError`. A missing file yields `ERROR: In call to 'read text from': [Errno 2] ... at line 1, column 6`. `SECURITY.md:31` already states the truth. | Delete the two stale claims; keep the accurate `§6.5` wording. |
| H5 | High | `README.md:17`, `CHANGELOG.md:94`, `docs/REWRITES.md:33` | "There is no compiler backend yet"; "there is no code generator yet"; "compiles" means only parse/lint/run. | `src/llang/compiler.py` emits valid WASM (`b'\x00asm\x01\x00\x00\x00'` verified), `llang-compile` exists, `tests/test_compiler.py` and `tools/compare_wasm.py` execute output in Node. `README.md:25`, `ROADMAP.md:21`, `FAMILY-PLAN.md:83` already say it is shipped — the same documents contradict themselves. | Rewrite the three lines as "the primary execution path is the interpreter; a WASM backend exists for the integer/function subset" and make `REWRITES.md:33` consistent with its own §6. |
| H6 | High | `docs/ROADMAP.md:44`, `docs/SEMANTIC-DECISIONS.md:34`, `docs/SEMANTIC-DECISIONS.md:108` | "finally returning — Forbidden by design"; decision #11 "Forbid `return`/`break`/`continue` inside the `always` block"; "a `return`/`stop` in `always` is not currently expressible". | Verified: `give back` inside `always` returns 2, and `stop the loop` inside `always` breaks the loop. `REFERENCE.md:296` and `:511` correctly say they are *not* forbidden and propagate like Python `finally` signals. | Mark decision #11 as **overruled/not implemented**, and change `ROADMAP.md:44` to "Signals in `always` propagate (Python `finally` behavior)." |
| H7 | High | `docs/REFERENCE.md:302`, `§6.1-§6.5` (`:320-362`), `§9:507` | "`Interpreter.__init__` preloads all 57 names below"; divergence #8 says "there is no slicing". | Code has 57 builtin names; the §6 tables enumerate only 56 — `slice` (shipped, with labels `collection`, optional `start`/`finish`) is absent. `GRAMMAR.md:119` documents it. Verified `call slice with collection = (a list of 1,2,3,4), start = 1, finish = 3` → `[2, 3]`. | Add a `slice` row to §6.2 (or §6.3), fix divergence #8 to say "no slicing *syntax*; use the `slice` builtin", and re-count the tables. |
| H8 | High | `CONTRIBUTING.md:18`, `tests/test_end_to_end.py:1` (claim quoted in docs) | "`examples/` — runnable programs; every example has a pinned-output regression test." | `tests/test_end_to_end.py` pins 7 of 10 examples. `examples/box2d.ll`, `examples/classes.ll`, `examples/maxims.ll` have no end-to-end assertions (all three do run correctly). | Add three pinned-output tests or soften the claim to "most examples". |

### Medium

| # | Severity | file:line | Claim | Reality | Recommended fix |
|---|---|---|---|---|---|
| M1 | Medium | `docs/REFERENCE.md:34`, `docs/REFERENCE.md:522-535` | "one of the 61 reserved words (`synonyms.RESERVED`)" and a 61-word appendix. | `synonyms.RESERVED` contains **64** words; the appendix omits `use`, `module`, `foreign` (and the tree-sitter grammar at `editors/tree-sitter/grammar.js:24` includes them). | Change 61 → 64 and add the three module keywords; add an automated count assertion to `tools/check.py`. |
| M2 | Medium | `docs/TUTORIAL.md:69`, `docs/TUTORIAL.md:576` | `a`, `an` listed as reserved words. | `set a to 5` and `set an to 6` both run. `REFERENCE.md:34`, `GRAMMAR.md:3`, `SEMANTIC-DECISIONS.md:110` correctly say they are not reserved. The cheat sheet also omits all problem/module/class keywords. | Remove `a`/`an` from the examples and list the full 64-word set (or link to `REFERENCE.md` §10). |
| M3 | Medium | `docs/TUTORIAL.md:293` | Missing `end if` error is at "line 3, column 13". | Actual output is `Unexpected end of input — missing matching 'end' at line 4, column 1` (EOF position). All 16 other tutorial error messages checked match exactly. | Correct the line/column in the tutorial. |
| M4 | Medium | `docs/SITE.md:80`, `docs/SITE.md:98-106` | Nav "links **every** existing document in `docs/` and `docs/research/`". | 10 research docs are absent from the nav: `c-like-surface-design.md`, `classes-semantics.md`, `datascience-library-design.md`, `engine-rewrite-target.md`, `lsp-spec.md`, `math-library-design.md`, `ml-library-design.md`, `regex-semantics.md`, `self-hosting-plan.md`, `wasm-semantics.md`. | Add the missing nav entries (and decide explicitly whether in-progress `CLL.md` is included). |
| M5 | Medium | `docs/DESIGN.md:3`, `docs/DESIGN.md:68` | Status "agreed approach, pre-implementation"; phases deferred include "classes ... compiler backend". | The document itself says phases 0-6 shipped; classes (`REFERENCE.md` §5.4) and the WASM backend are implemented and tested. | Change status to "implemented; historical decisions retained" and remove classes/compiler from the deferred list. |
| M6 | Medium | `docs/GRAMMAR.md:121-140` | The "## Example" block is presented as a runnable program. | It fails after the first two lines: `ERROR: Undefined name 'name' at line 4, column 4` (`if name equals "Ada"`). | Add `set name to "Ada"` before the `if`, or state that the block is a fragment. |
| M7 | Medium | `LICENSE:27-31` | Third-party material is limited to `tools/pilots/`; "no third-party source code is copied into the interpreter or libraries". | `tools/rewrites/pypybox2d/source/` is a full vendored clone (zlib license, its own `LICENSE` and `.git`) of pypybox2d. The pilot claim is accurate; the disclosure is incomplete. | Add `tools/rewrites/pypybox2d/source/` (zlib, pinned commit) to the third-party material section and point to `tools/rewrites/pypybox2d/SOURCE.md`. |
| M8 | Medium | `docs/REWRITES.md:8-35`, `:107`, `:112` | Summary table has 9 rewrites; "the four native rewrites above"; next candidate "`humanize.number` — number formatting with the existing `rounded`/`to text` builtins". | `advanced_math` (167), `datascience` (117) and `machinelearning` (46) are shipped rewrites with harnesses but absent from the summary; `humanize` (including number formatting) is already shipped at row 8. | Add the three domain-library rows; update "four" → the current count; remove the stale next candidate. |
| M9 | Medium | `docs/ROADMAP.md:38` | Module packaging: "manifests, versioning and a lock file are not implemented". | `src/llang/packages.py` implements `llang.json` manifests, `parse_version`/`compare_versions`/`version_matches`, registry discovery/resolution and `check_dependencies`, all covered by 20 tests in `tests/test_packages.py`. Only a lock file is missing. | Change to "Versioning and dependency checks are implemented; a lock file is not." Add a short user-facing package section to `REFERENCE.md` (also relevant to `RELEASE.md:13`). |
| M10 | Medium | `docs/REFERENCE.md:38`, `docs/GRAMMAR.md:12`, `docs/TUTORIAL.md:63`, `docs/TUTORIAL.md:563` | Supported string escapes are `\n`, `\t`, `\"`, `\\` (four). | `lexer.py:101` also maps `\r` → carriage return; `CHANGELOG.md:37`, `REWRITES.md:97`, `self-hosting-plan.md:109` document the fix. Verified `"a\rb"` prints `a` then `b`. | Add `\r` to all four escape lists. |
| M11 | Medium | `docs/EDITOR-SUPPORT.md:10`, `editors/vscode/llang.tmLanguage.json:47,52,82` | Grammar covers builtin call names and the documented escapes. | `slice` and `predict` (both shipped) are missing from the `builtin` pattern; `\r` is classified `invalid.illegal.escape.llang` by the escape pattern. | Add `slice`/`predict` to the builtin regex and `r` to `string-escape` / exclude it from the illegal-escape pattern. |
| M12 | Medium | `docs/SEMANTIC-DECISIONS.md:25`, `:69`, `:75-77`, `:80`, `:91` | "Recommended primaries" table uses `the first truthy of`, `for each x in xs`, `if a problem of kind E occurs, handle it by ...`, `if nothing went wrong, then ...`, `always, whether it worked or not, ...`, `produce x`, and §3 cross-cutting rule 2 cites `increase x by ...`. | None of these spellings exist in the parser/reserved set: implemented forms are `repeat for each`, `... occurs then`, `if nothing went wrong then`, `always`, `give back`; no `produce`/`increase` construct. | Annotate the table as historical/proposal-only, or update it to the shipped surface so it cannot be copied into generated code. |

### Low

| # | Severity | file:line | Claim | Reality | Recommended fix |
|---|---|---|---|---|---|
| L1 | Low | `docs/REFERENCE.md:431` | Native shell layer wraps "run, capture, succeeds, must_succeed, lines, run_each, and env". | `lib/shell.ll:55` also exports `build` (used by `SECURITY.md:28`). | Add `build` to the list. |
| L2 | Low | `docs/GRAMMAR.md:119` | Builtin alias inventory. | Omits `to_number`, `is_number`, `is_text`, `is_list`, `is_map`, all present in `interpreter.BUILTINS` and `REFERENCE.md` §6.1. | Add the missing aliases. |
| L3 | Low | `docs/ROADMAP.md:42` | "Tuples, sets, slices — Not yet". | A `slice` builtin is shipped; only slicing *syntax* (`a[1:3]`) is absent. | Rename the row "Slicing syntax / tuples / sets". |
| L4 | Low | `docs/TUTORIAL.md:579` | Grammar includes "collection and iteration forms still being added to the interpreter". | Collections and `repeat for each` are implemented and documented as shipped in `REFERENCE.md` §4.3/§5.2. | Remove "still being added". |
| L5 | Low | `docs/DESIGN.md:44` | Descriptors example `display(message="hi", times=2)`. | llang uses labeled `call`/`show`, never Python-style `name=` syntax. The section is a proposal but reads as language surface. | Mark as a rejected/never-implemented descriptor sketch. |
| L6 | Low | `docs/research/ml-library-design.md:3`, `:30`, `:45`, `:296`, `:339`, `:405` | Native module is `lib/ml.ll` with `tools/compare_ml*.py`. | Shipped module is `lib/machinelearning.ll` and harness `tools/compare_ml.py`. | Rename references (keep a note that the design used the short name). |
| L7 | Low | `docs/research/regex-semantics.md:234-237`, `:275` | "v1's foreign layer can call `re` directly"; proposed `tests/test_regex_module.py`. | `foreign.py` has no `re` module; regex is native `lib/re.ll` (118 verified cases) with `tests/test_re.py`. | Update the verification plan to the shipped native engine. |
| L8 | Low | `docs/research/self-hosting-plan.md:121` | `call slice with ..., end = ...`. | Actual optional labels are `start`/`finish` (`interpreter.py:303`, `GRAMMAR.md:119`). | Change `end` → `finish`. |
| L9 | Low | `docs/research/math-library-design.md:280` | Verification file `tests/test_math.py`. | Actual file is `tests/test_advanced_math.py`. | Correct the path. |
| L10 | Low | `docs/RELEASE.md:13` | Before 1.0 "a compiler backend, a language server, and a documented package system" should exist. | Compiler and LSP exist; package manifests/registry/versioning exist but have no user-facing documentation (only `packages.py` docstring and API tests). | Add a `docs/PACKAGES.md` (or `REFERENCE.md` section) before calling the package system documented. |
| L11 | Low | `README.md:26` | "pre-run linter" in the tooling list. | The linter is opt-in: `REFERENCE.md:365` correctly notes `run_source`/`run.py` do not lint automatically. | Say "opt-in linter (`--lint`)" to avoid implying automatic pre-run linting. |

---

## 3. Documentation verified accurate

- **All ten tutorial chapters' runnable examples** (`TUTORIAL.md` Chapters 1-10) reproduce their stated expected output byte-for-byte, including left-to-right arithmetic, operand-returning logic, aliases, and `require`.
- **16 of 17 documented tutorial error messages** match exactly (only M3 differs, by position).
- **Every differential harness count reproduced exactly**: `shlex` 59, `fnmatch` 85, `textwrap` 240, `csv` 57, `json` 95, `re` 118, `advanced_math` 167, `datascience` 117, `machinelearning` 46, `pylev` 222, `humanize` 227, `box2d` 1,113, fuzzer 407 generated expressions — all **0 mismatches**. README's "2,546 differential cases total" and "1,562 external-repo cases" / "330 domain cases" are arithmetically correct.
- **Provenance and license claims** in `REWRITES.md` match `tools/rewrites/{pylev,humanize,pypybox2d}/SOURCE.md` (BSD-3-Clause, MIT, zlib with pinned commits) and `tools/pilots/README.md` (PSF/MIT) — apart from the disclosure gap in M7.
- **CLI smoke commands** in `.github/workflows/ci.yml` (`llang`, `--lint`, `--format`) work; `llang-compile -o`, `python tools/port.py --report`, and `python -m llang.lsp` entry points exist and are wired correctly in `pyproject.toml`.
- **`bisect` converter coverage 97.3%** (`ROADMAP.md:19`, `REWRITES.md:90`) verified by regenerating the report.
- **README's opening program** runs and prints `Ada: 91` / `Grace: 98`; `EDITOR-SUPPORT.md:119-154` smoke program runs; `REFERENCE.md` class, module, and shell examples run; `GRAMMAR.md` class example runs.
- **`SECURITY.md`** claims (allowlist in `foreign.py`, 30-second timeout, code/stdout/stderr capture, no implicit execution) verified against `src/llang/foreign.py`.
- **Link hygiene**: the repository's own `check_links()` passes over all Markdown (no broken Markdown links in scope). `docs/research/README.md` lists 16 research documents and all 16 exist.
- **`SITE.md:5`** is correct that `mkdocs.yml` is not present; all nav targets that *are* listed resolve.
- **Lexer and interpreter core descriptions** in `REFERENCE.md` §§2-5 (token kinds, Unicode identifiers, ASCII numbers, left-to-right operators, predicates, classes, problems, 100,000-iteration guard, source positions) match the implementation; the 11 parser hint strings and 57 builtin name count in code were verified.

---

## 4. Prioritized remediation list

**P0 — correctness of the authoritative reference and user-facing commands (do first)**
1. H1: fix the playground quickstart command (`node`, not `python`).
2. H2: declare/install verification dependencies; correct the "no third-party packages" claim and CI.
3. H3 + H4: rewrite `REFERENCE.md` §6 general contract (label validation and `OSError`) and divergence #10/#14.
4. H7: add the `slice` builtin to `REFERENCE.md` §6 and fix "no slicing".
5. H5: remove all "no compiler backend / no code generator" claims.
6. H6: mark the `finally`-return decision as overruled; fix `ROADMAP.md:44`.
7. H8: add pinned-output tests for the three untested examples, or correct the claim.

**P1 — consistency across documents**
8. M1/M2: fix reserved-word counts/lists in `REFERENCE.md` and `TUTORIAL.md`; add a count check to `tools/check.py`.
9. M3: correct the tutorial's error position.
10. M4/M5/M6: complete the `SITE.md` nav; refresh `DESIGN.md` status; repair the `GRAMMAR.md` example.
11. M7: disclose the vendored zlib clone in `LICENSE`.
12. M8/M9: complete `REWRITES.md`; correct module-packaging status and add package docs.
13. M10/M11/M12: add `\r` and the missing builtins to docs/grammars; reconcile proposed vs shipped surface forms.

**P2 — low-risk cleanups**
14. L1-L11: update stale aliases, paths, and wording listed in the low table; retire the stale "produce"/"increase" and `lib/ml.ll` references in research documents.

**Suggested preventive measure:** extend `tools/check.py` with small structural assertions (reserved-word count, builtin-name count vs documented table, every `examples/*.ll` referenced by a pinned test, every `docs/research/*.md` present in `SITE.md` nav) so these classes of drift fail in CI.


## Remediation status

Reviewed and addressed where applicable. Verified with `python tools/check.py` (17/17 checks passing, 456 tests). Outstanding low-severity items are tracked in `docs/ROADMAP.md`.

