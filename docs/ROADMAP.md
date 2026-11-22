# Roadmap / honest scope

llang is usable today, but it is not a clone of Python's entire runtime. This page records what exists, what is deliberately out of scope, and what would come next.

## Shipped

- Lexer, parser, canonical AST, tree-walking interpreter
- Literals: number, text, boolean, `nothing`, list, map
- Expressions: left-to-right word operators, parentheses, postfix predicates, indexing, phrase-named builtins
- Statements: assignment, output, `require`, collection mutation, `if`, both loop forms, `stop`, `skip`, functions with aliases, problem handling
- Closed synonym vocabulary with canonical normalization
- Source-located diagnostics with expected-token hints
- Canonicalizing formatter and pre-run linter
- Native modules (`use the X module`, qualified calls), standard library in `lib/`, and a labeled opt-in foreign bridge
- Nushell-grounded shell layer on top of the foreign `shell` module
- Four CPython modules rewritten in llang and verified against the stdlib (`shlex`, `fnmatch`, `textwrap`, `csv`)
- Language additions: `floor divided by`, `insert into`, and `apply`
- Minimal class/record system: `define class`, declared constructor fields, methods with an explicit `this`, `call new`, and `ask` (§5.4 of REFERENCE.md)
- Automated Python → llang converter with coverage reports (`bisect` now 97.3%)
- Console entry points (`llang`, `llang-port`, `llang-compile`), one-command verification, GitHub Actions CI
- WebAssembly backend and browser playground
- LSP language server, editor grammars, docs-site guide
- Native `json` and `re` modules, package manifests/registry, property-based differential fuzzer
- Minimal classes with explicit `self` (`this`), grounded in the Python data model
- Self-hosting stage 0 (token/AST data contract); LSP conformance fixes; WASM differential corpus
- Tutorial, reference, design documents, grounded research, flagship demos

## Deliberate divergences from Python

Recorded in `SEMANTIC-DECISIONS.md`: no operator precedence, no chained comparisons, no loop-`else`, no implicit coercion, iteration snapshots the collection, explicit block terminators, no operator overloading or macros. The class system is record-style: `this` is explicit, the class body is not an enclosing scope, and there is no inheritance, class variables, name mangling, descriptors, or monkey-patching (§9 of REFERENCE.md).

## Not implemented (and why)

| Feature | Status | Notes |
|---|---|---|
| Minimal classes / records | Shipped | `define class ... taking ...`, methods with explicit `this`, `call new C with ...`, `ask obj to method with ...`. Class scope is non-enclosing (decision #12) |
| Inheritance / full Python OO | Not planned | No `inherits`, C3/MRO, `super()`, class variables, name mangling, descriptors, metaclasses, privacy, or monkey-patching; functions + maps still cover most scripting needs |
| Module packaging | Partial | `use` and qualified calls work; manifests, versioning and a lock file are not implemented |
| Comprehensions | Not yet | Plain loops are more explicit and easier for an LLM to generate correctly |
| Generators / lazy sequences | Not yet | Requires an `on demand` marker in the grammar to avoid hiding memory/time behavior |
| Default/keyword-only parameters | Not yet | Every labeled argument is currently required; phrase variants work around this |
| Tuples, sets, slices | Not yet | Lists and maps cover the common cases |
| Exceptions with `as` binding | Partial | `fail` and `expect` work; the raised problem's value is not bound to a name in the handler |
| Signals in `always` | Shipped (Python `finally` behaviour) | `give back`/`stop` propagate like Python `finally`; matched by the differential tests |
| Efficient backend | Partial | A WASM backend exists for the integer/function subset; text, collections, builtins and foreign calls are still interpreter-only |
| Full Python porting | In progress | Converter plus seven rewrites exist; C extensions, inheritance-heavy classes, generators, and Python-specific quirks remain outside the supported subset |

## Guiding rule for future work

Every addition must either (a) increase readability without adding ambiguity, or (b) increase capability without adding special cases. If an addition requires a new reserved word, a context-dependent parse, or a hidden rewrite, it needs a written decision in `SEMANTIC-DECISIONS.md` first.
