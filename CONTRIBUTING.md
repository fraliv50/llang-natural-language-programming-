# Contributing to llang

Thanks for helping build a language that is easy for both people and AI to read.

## Setup

Python 3.10+ runs the interpreter. The full verification suite also needs
Node.js and the oracle libraries: `pip install -e '.[dev]'`.

```powershell
python -m unittest discover -s tests -v
python run.py examples/hello.ll
```

## Repository layout

- `src/llang/` — the interpreter, lexer, parser, canonical AST, formatter, linter, converter, foreign-module allowlist
- `lib/` — standard library written in llang itself
- `examples/` — runnable programs; every example has a pinned-output regression test
- `docs/` — design, reference, methodology, roadmap, and rewrite records
- `docs/research/` — grounding documents produced from authoritative external docs
- `tools/` — CLI helpers and conversion pilots
- `tests/` — unit, differential, and end-to-end tests

## How we build things

Follow `docs/METHOD.md`: ground every semantic decision in authoritative
documentation, define canonical nodes before syntax, keep the vocabulary closed,
and verify with three kinds of tests (synonym equivalence, semantic edge cases,
end-to-end output).

When adding a feature, update all of these together:

1. `src/llang/` implementation
2. `docs/GRAMMAR.md` (compact grammar)
3. `docs/REFERENCE.md` (authoritative reference)
4. `tests/` (including `tests/test_end_to_end.py` if output changes)
5. `docs/SEMANTIC-DECISIONS.md` if the feature introduces a semantic choice
6. `docs/ROADMAP.md` status

## Style

- New language constructs must be verbose, regular, and unambiguous.
- No implicit behavior: no coercion, no context-dependent parsing, no hidden control flow.
- Synonyms are a closed set in `src/llang/synonyms.py` and must normalize to one canonical node.
- Libraries extend values and types, never syntax.
- Every diagnostic carries a source position and, where possible, expected-token hints.

## Testing before a pull request

```powershell
python tools/check.py
```

That single command runs the unit suite, lints every shipped `.ll` file, verifies
all four stdlib rewrites against Python, and checks documentation links. All
checks must pass. The same command runs in GitHub Actions on every push and PR.

## Adding a ported Python module

Use `python tools/port.py file.py -o ported.ll --report report.txt`. Commit the
converted `.ll` file only when the coverage report is reviewed and the remaining
unsupported constructs are documented in `docs/REWRITES.md`.
