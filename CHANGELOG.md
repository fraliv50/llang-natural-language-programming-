# Changelog

All notable changes to llang are recorded here. Dates follow the development session.

## 2026-11-22 — initial language

- Lexer, recursive-descent parser, canonical AST, tree-walking interpreter in Python
- Dynamic values, strict operations, no implicit coercion, source-located diagnostics
- Word operators with closed synonym vocabulary, explicit `end ...` block terminators
- `if`/`otherwise`, `repeat while`, functions with aliases, labeled call arguments, `require`
- Canonical formatter and pre-run linter
- Grounded research: Python semantics, natural-language precedents, stdlib design, demo design, test plan
- Flagship `examples/report_card.ll` with pinned hand-verifiable output

## 2026-11-22 — collections, predicates, problems

- List/map literals, indexing, in-place mutation, `repeat for each`, `stop the loop`, `skip to the next item`
- Postfix predicates (`is empty`, `is nothing`, `is a number`, …)
- Phrase-named builtins (53 spellings) with strict labeled-argument validation
- `expect` / `fail` problem handling with handlers, else, and always clauses
- `examples/rubiks.ll`: Rubik's cube simulator generating a browser viewer

## 2026-11-22 — modules and terminal layer

- `use the X module`, qualified calls (`call f from m with ...`), aliases
- Native llang libraries: `math`, `text`, `lists`
- Explicitly labeled foreign bridge: `json`, `math`, then `shell`
- Nushell-grounded shell layer in `lib/shell.ll`; `examples/shell.ll`
- `docs/METHOD.md` and `docs/FAMILY-PLAN.md` record the repeatable process and tiered IR plan

## 2026-11-22 — open-source rewrites and converter

- `lib/shlex.ll`: CPython `shlex` rewritten in llang, verified against stdlib on 59 cases
- `src/llang/converter.py` + `tools/port.py`: automated Python AST → llang translation with coverage reports
- Differential tests that run converted code against Python
- Pilot coverage: `bisect` 92.0%, `fnmatch` 85.6%, `humanize/filesize` 75.5%
- Fixed lexer `\r` escape, no-precedence parenthesization, reserved-word collisions, and greedy zero-argument calls

## 2026-11-22 — full ecosystem round

- Three more CPython modules rewritten in llang and verified against the stdlib: `fnmatch` (85 cases), `textwrap` (240 cases), `csv` (57 cases) — all with 0 mismatches
- Language additions to unblock the `bisect` port: `floor divided by` operator, `insert into` builtin, and `apply` for calling function values with positional arguments
- `bisect` converter coverage raised from 92.0% to 97.3%; handled transformations now reported separately from unsupported constructs
- Packaging: `src/llang/cli.py` and `src/llang/convert_cli.py` with `llang` / `llang-port` console entry points
- `tools/check.py` runs every verification in one command; `.github/workflows/ci.yml` runs it on push/PR
- Repository organized for GitHub: `docs/research/`, provenance for third-party pilots, MIT license, contributing guide, project metadata

## 2026-11-22 — toolchain and ecosystem

- WebAssembly backend (`src/llang/compiler.py`) for the integer/function subset, with `llang-compile` entry point and Node-verified tests
- Browser playground (`tools/playground/`) that compiles llang to WASM
- LSP language server (`src/llang/lsp.py`) with diagnostics, completion, hover and definition
- Native `json` module (95 differential cases, 0 mismatches)
- Package manifests and local registry (`src/llang/packages.py`)
- Editor grammars for VS Code and tree-sitter; documentation site guide
- Property-based differential fuzzer (`tools/fuzz_semantics.py`) — 407 generated expressions, 0 mismatches
- Language additions: `slice` builtin, list-comprehension desugaring in the converter
- Project hygiene: `SECURITY.md`, `CODE_OF_CONDUCT.md`, issue templates, `RELEASE.md`

## 2026-11-22 — grounding-driven completion round

- Grounding documents added for full WASM coverage, self-hosting, regex, classes, and LSP conformance (`docs/research/`)
- Native `lib/re.ll` regex subset verified against Python `re` on 118 cases
- Minimal class/record system: `define class`, `call new`, `ask instance to method` with explicit `this`
- Self-hosting stage 0: `lib/ast_contract.ll` for token/AST maps, plus first-draft conversion artifacts in `tools/selfhost/`
- LSP conformance fixes: explicit lifecycle state machine, `exit` termination, `didClose`, JSON-RPC error codes, UTF-16 offsets
- WASM differential corpus (`tools/compare_wasm.py`) and regex harness added to `tools/check.py`

## 2026-11-22 — math / data science / ML foundations

- Grounding documents for the three requested domains, each pinned against an installed oracle: `math-library-design.md` (Python math/statistics), `datascience-library-design.md` (NumPy/pandas), `ml-library-design.md` (scikit-learn)
- Language additions for these domains: `predict` builtin for self-describing model maps; `slice` builtin; localized overflow and complex-result errors for power operations
- Research index in `docs/research/README.md` extended with all grounding documents

## 2026-11-22 — domain libraries and external repo rewrites

- `lib/advanced_math.ll` — math/statistics grounded in Python `math`/`statistics`; 167 differential cases, 0 mismatches
- `lib/datascience.ll` — Dataset maps and tabular operations grounded in NumPy/pandas; 117 cases, 0 mismatches
- `lib/machinelearning.ll` — self-describing model maps grounded in scikit-learn; 46 cases, 0 mismatches
- `lib/pylev.ll` — external BSD-3-Clause repo rewritten; 222 cases, 0 mismatches
- `lib/humanize.ll` — external MIT repo rewritten; 227 cases, 0 mismatches
- `predict` builtin added so model maps can be used directly
- All six new differential harnesses wired into `tools/check.py`

## 2026-11-22 — engine rewrite and second language surface

- Cloned and pinned `pypybox2d` (zlib, 10.5k lines) and rewrote a headless physics subset in `lib/box2d.ll`: Vec2/Mat22/Transform/AABB math, circle collision, gravity, and a semi-implicit Euler world step; 1,113 differential cases, 0 mismatches, and a runnable 60-step simulation matching the original byte-for-byte
- Research documents for the engine target (`engine-rewrite-target.md`) and the next language surface (`c-like-surface-design.md`)
- Installed MinGW-w64 GCC via `tools/cc.py` so the C-like surface can be verified against a real compiler
- `c-ll` v1 implementation in progress in `src/llang/cll/`

## 2026-11-22 — AI ergonomics

- Function, class and method definitions may now use **multi-word phrase names**, called with the matching phrase
- Added the `@` escape sigil: any reserved word can be used as an identifier, label, parameter, or definition name (`@end`, `@function`), and the formatter emits it automatically so round-trips are stable
- `this` removed from the reserved set (the method receiver is still positional and explicit)
- 7 new tests in `tests/test_ai_ergonomics.py`

## Known limitations

See `docs/ROADMAP.md`. The primary execution path is the interpreter; a WASM backend exists for the integer/function subset.
