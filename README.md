# llang

A programming language that reads like structured English and behaves like Python.

It was designed with one unusual constraint: **the primary author and reader is an AI**. Human-era compromises (terse syntax, abbreviations, operator soup, clever implicit behavior) are pure downside for a model, so llang trades them for verbose, explicit, regular constructs. Natural-language phrasing is the point, not a novelty — llang is structured pseudocode you can actually run.

```
set scores to a map with "Ada" mapped to 91, "Grace" mapped to 98

repeat for each student in (call keys of with collection = scores)
    show student plus ": " plus (call text of with value = item student of scores)
end repeat
```

## Status

The language is implemented and usable. The primary execution path is the
interpreter; a WebAssembly backend exists for the integer/function subset and is
verified by executing its output in Node. For rewrites, "compiles" means the
program parses, lints clean, and produces output identical to the original.

- **Values:** numbers, text, booleans, `nothing`, lists, maps, functions
- **Statements:** `set`/`let`, `show`/`display`/`print`, `require`, `add`, `set item`, `if`/`otherwise`, `repeat while`, `repeat for each`, `stop the loop`, `skip to the next item`, functions with aliases, labeled `call`, `fail`/`expect` problem handling, `use` modules
- **Expressions:** strictly left-to-right with parentheses for grouping, word operators with closed synonyms (`floor divided by` included), postfix predicates, collection literals, indexing, phrase-named builtins, `apply` for calling function values
- **AI ergonomics:** definitions may use phrase names (`define function find all ...`), and `@` escapes reserved words anywhere a name is expected (`taking @end`, `call f with @end = 1`)
- **Domain libraries:** `advanced_math` (math/statistics), `datascience` (NumPy/pandas semantics), `machinelearning` (scikit-learn semantics) — all native llang, with self-describing results and loud validation
- **Libraries:** native llang modules in `lib/` (`math`, `text`, `lists`, `shell`, `shlex`, `fnmatch`, `textwrap`, `csv`, `json`, `re`, `ast_contract`, `pylev`, `humanize`), plus an explicitly labeled opt-in foreign bridge (`json`, `math`, `shell`)
- **Objects:** minimal classes with explicit `this`, single inheritance-free construction via `call new ...`, and `ask instance to method ...`
- **Compiler:** a WebAssembly backend for the integer/function subset — `llang-compile file.ll -o file.wasm`, verified by executing the output in Node
- **Tooling:** source-located diagnostics, canonical formatter, pre-run linter, LSP language server, Python-to-llang converter, property-based differential fuzzer, single-command verification, GitHub Actions CI
- **Ecosystem:** native `json` module, JSON package manifests with a registry, editor grammars for VS Code and tree-sitter, and a browser playground

## Quickstart

The interpreter needs Python 3.10+ only. The full verification suite additionally
uses Node.js (for WebAssembly checks) and the Python data libraries used as
oracles: `numpy`, `pandas`, `scikit-learn`. Install them with
`pip install -e '.[dev]'` before running `tools/check.py`.

```powershell
python run.py examples/hello.ll          # run a program
python repl.py                           # interactive shell
python tools/check.py                    # every check: tests, lint, rewrites, links
python tools/port.py my.py -o ported.ll --report report.txt
python run.py --lint examples/hello.ll
python run.py --format examples/hello.ll
node tools/playground/server.js           # browser playground at localhost:8080
```

Or install the package for console commands:

```powershell
pip install -e .
llang examples/hello.ll
llang-port my.py -o ported.ll
llang-compile my.ll -o my.wasm
python -m llang.lsp            # language server over stdio
```

## Core design

**Surface flexibility, canonical precision.** The surface language has a closed vocabulary of synonyms; the parser normalizes every spelling to one canonical AST node, and the interpreter only ever sees that node. Synonyms add readability without adding ambiguity — the failure mode that sank AppleScript and Inform 7.

| Decision | Rule |
|---|---|
| Semantics | Grounded in authoritative docs of existing languages — re-express, never invent |
| Blocks | Explicit `end if` / `end repeat` / `end function` / `end expect`; indentation ignored |
| Evaluation | Strictly left-to-right; parentheses for grouping |
| Types | Dynamic; strict operations, no implicit coercion |
| Arguments | Labeled roles (`call f with name = x`), never bare position |
| Extension | Libraries extend values and types, never syntax |
| Diagnostics | Source line/column and expected-token hints are part of the spec |

## Documentation

Start here:

- [Tutorial](docs/TUTORIAL.md) — learn the language from zero
- [Reference](docs/REFERENCE.md) — complete authoritative reference
- [Grammar](docs/GRAMMAR.md) — compact grammar that fits in an LLM prompt
- [Examples](examples/) — runnable programs with pinned output

Design and process:

- [Design](docs/DESIGN.md) — decisions and rationale
- [Semantic decisions](docs/SEMANTIC-DECISIONS.md) — tricky choices and why
- [Method](docs/METHOD.md) — the repeatable process for adding a language surface
- [Family plan](docs/FAMILY-PLAN.md) — tiered IR, converter, libraries, build order
- [Roadmap](docs/ROADMAP.md) — honest scope and deferred features
- [Rewrites](docs/REWRITES.md) — open-source Python software rewritten and verified in llang
- [Research](docs/research/) — grounded matrices: Python semantics, precedents, stdlib, demo, terminal, test plan

Project:

- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)
- [License](LICENSE) — MIT

## Highlights

- `examples/report_card.ll` — flagship program: a graded report card that checks its own result
- `examples/rubiks.ll` — Rubik's cube simulator that writes a browser viewer (`rubiks.html`)
- `lib/shlex.ll`, `lib/fnmatch.ll`, `lib/textwrap.ll`, `lib/csv.ll`, `lib/json.ll`, `lib/re.ll` — CPython modules rewritten in llang and verified against the stdlib
- `lib/pylev.ll`, `lib/humanize.ll`, `lib/box2d.ll` — external open-source repos cloned and rewritten, verified against the originals (1,562 cases); `box2d` is a headless physics engine subset with a working 60-step simulation
- `examples/box2d_visual.ll` — writes `physics.html`, a live browser animation of that simulation (all frames computed in llang)
- `lib/advanced_math.ll`, `lib/datascience.ll`, `lib/machinelearning.ll` — domain libraries grounded in Python math/statistics, NumPy/pandas and scikit-learn (330 cases)
- **2,546 differential cases total, 0 mismatches**
- `src/llang/compiler.py` — WebAssembly backend; `tools/playground/` — browser playground
- `src/llang/lsp.py` — language server; `src/llang/packages.py` — package manifests and registry
- `editors/` — VS Code and tree-sitter grammars; `docs/SITE.md` — documentation site guide
- `tools/port.py` — automated Python → llang converter with an honest coverage report
- `tools/check.py` — one command for tests, lint, rewrite verification, and link checks

## Layout

```
src/llang/    lexer, parser, canonical AST, interpreter, synonyms, errors,
              formatter, linter, converter, WASM compiler, LSP, packages,
              CLI entry points, foreign allowlist
lib/          standard library written in llang
examples/     runnable programs
tests/        unit, differential, diagnostics, end-to-end, compiler
docs/         reference and design documentation
docs/research/ grounding documents from authoritative external sources
tools/        port.py, check.py, compare_*.py, fuzz_semantics.py, playground,
              fixtures, pilots
editors/      VS Code TextMate grammar and tree-sitter grammar
.github/      CI workflow and issue templates
run.py        development CLI entry point
repl.py       interactive shell
```
