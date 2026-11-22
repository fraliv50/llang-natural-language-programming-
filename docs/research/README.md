# Grounding research

These documents are the authority behind llang's design. Each was produced by
reading the official documentation of an existing system, then recording the
semantics and edge cases before any syntax was designed. See
[`../METHOD.md`](../METHOD.md) for the repeatable process.

| Document | Authority | What it grounds |
|---|---|---|
| `python-semantics.md` | Official Python 3.15 reference, tutorial, built-in types/exceptions, FAQ | The core language: values, evaluation order, truthiness, scope, iteration, exceptions |
| `natural-language-precedents.md` | Official docs and community reports for COBOL, SQL, HyperTalk, AppleScript, Inform 7, Gherkin, NL-programming research, LLM DSLs | Which natural-language ideas work, which failed, and why |
| `stdlib-design.md` | Official Python docs + current llang source | The builtin/namespace design and vocabulary |
| `demo-design.md` | Current llang grammar and interpreter | The flagship report-card program and its quality rubric |
| `test-plan.md` | Current llang source and tests | Test categories, exact diagnostics, planned-feature coverage |
| `terminal-semantics.md` | Official Nushell book (MIT) | The shell/command layer: structured pipelines, exit codes, safety model |
| `math-library-design.md` | Official Python `math` and `statistics` docs | The advanced math library: numeric invariants, API table, QoL improvements, differential harness |
| `datascience-library-design.md` | Official NumPy and pandas docs | The data science library: Dataset representation, API table, QoL improvements, differential harness |
| `ml-library-design.md` | Official scikit-learn User Guide | The ML library: model maps, estimator invariants, API table, QoL improvements, differential harness |
| `wasm-semantics.md` | W3C WebAssembly spec + WABT/Node | Full WASM value coverage and verification |
| `self-hosting-plan.md` | Our own interpreter source | Staged self-hosting and bootstrap sequence |
| `regex-semantics.md` | Official Python `re` docs + CPython source | Native regex subset |
| `classes-semantics.md` | Official Python data model | Minimal classes with explicit `this` |
| `lsp-spec.md` | Official LSP 3.17 specification | Language server conformance |
| `engine-rewrite-target.md` | GitHub survey of pure-Python engines | Selection and staged port plan for the physics-engine rewrite (pypybox2d) |
| `c-like-surface-design.md` | C11 / cppreference | The `c-ll` second language surface and L2/L3 IR mapping |

**Rule:** when a design document and the implementation disagree, the code wins.
Update the design documents after each change.
