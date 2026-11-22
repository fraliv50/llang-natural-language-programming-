# The grounding method — how to add another language surface

This is the reproducible process that produced llang in a short time. It works because we never invent semantics; we *re-express* a language whose semantics are already authoritative. Keep this checklist for every new surface.

## Why it worked

Python's official reference settled every hard question before we wrote a parser: evaluation order, truthiness, mutation, scope, closures, iteration protocol, exception termination. We spent our effort on *phrasing*, not on guessing behavior. Two subagents did the documentation research in parallel while the engine was built. The result was auditable rather than intuitive.

## The steps

1. **Pick one reference language and one authoritative source.** Official language reference + built-in types + tutorial. Fetch it with a subagent; require inline citations. Never use blog posts as the spec.
2. **Produce a semantic reference matrix.** For each construct: (a) exact semantics and evaluation order, (b) documented edge cases and gotchas, (c) candidate natural-language phrasings. The "cross-cutting invariants" section (object model, evaluation order, truthiness, scoping, iteration, exceptions, mutability) is the most valuable part — write it first.
3. **Choose canonical core nodes.** One node per concept, no overlaps. The interpreter only ever sees these. Write them down before implementing.
4. **Define the closed surface vocabulary in ONE module.** Synonym tables, reserved words, operator phrases. Flexibility lives here; it never leaks into evaluation. Every synonym must produce an identical AST — that is a test, not a promise.
5. **Implement lexer → parser → canonical AST.** Desugaring happens at parse time. Keep the grammar regular and left-to-right; no contextual keywords, no precedence table, explicit block terminators.
6. **Implement the evaluator strictly.** Dynamic values, no implicit coercion, loud source-located errors, deterministic evaluation order. Prefer rejecting to guessing.
7. **Write three kinds of tests simultaneously.** Synonym-equivalence (identical AST), semantic edge cases (from the matrix), and end-to-end examples with pinned output.
8. **Publish a compact grammar.** It must fit in one LLM prompt and be regular enough to drive constrained decoding later.
9. **Add the formatter and linter.** The formatter collapses all synonyms to one canonical spelling, which makes the synonym decision safe for diffs. The linter catches model mistakes before execution.
10. **Write the reference against the source.** Verify every claim by reading the implementation; when an older design doc disagrees, the code wins.

## Artifacts required per surface

- `docs/research/<language>-semantics.md` — the grounded matrix
- a synonym/vocabulary table in `synonyms.py` (or its per-surface equivalent)
- canonical AST nodes plus equivalence tests
- an updated compact grammar
- an updated reference manual
- at least one runnable end-to-end example

## Pitfalls observed

| Pitfall | Consequence | Guard |
|---|---|---|
| Documentation drift after parallel edits | Docs promise syntax the parser rejects | Reference says "code wins"; re-verify docs after each phase |
| Reserved-word collisions (`with`, `a`, operator words) | Unparseable names or confusing calls | One reserved list, tested; avoid `with` in phrase names |
| Too many synonyms | Writer cannot predict validity | Closed vocabulary, formatter normalization |
| Syntactic sugar hiding control flow | Unmaintainable, unreadable | Keep `end if`/`end repeat` visible |
| Multi-line expressions | Parser complexity and ambiguity | One statement per line; require parentheses |
| Silent acceptance of extra arguments | Wrong programs look right | Validate every label against a registry |

## The oracle principle (why some work was faster than other work)

The rewrites (`shlex`, `fnmatch`, `textwrap`, `csv`, `json`) went quickly and ended
with zero mismatches. The WASM compiler, LSP server and package system took
noticeably more effort. The difference was not difficulty — it was the presence
of a **side-by-side oracle**:

| Component | Oracle available | Result |
|---|---|---|
| `shlex`, `fnmatch`, `textwrap`, `csv`, `json` | Official docs **plus a running stdlib implementation** to diff against | 0 mismatches, fast |
| WASM compiler | Spec only at first; recovered by using Node's WebAssembly runtime as an executable oracle | Correct, but slower and bug-prone |
| LSP server | Official spec exists but was not fetched first | More guessing about exact LSP shapes |
| Package system | No direct oracle; compared conceptually with npm/pip manifests | Most design decisions were judgement calls |

An oracle gives three things at once:

1. **Settled semantics** — you do not have to guess what "correct" means.
2. **A differential test** — every change can be checked mechanically against the reference.
3. **A completeness checklist** — the reference's feature list tells you what remains.

**Rule: before building anything from scratch, find an authoritative spec AND an
executable oracle.** If no implementation exists to copy semantics from, use a
runtime as the oracle (Node for WASM, a reference LSP client for the server) or
build a tiny one. A wrong answer discovered by an oracle is worth more than a
confident guess.

## Scaling the method

The same checklist applies to every surface in the planned family (see `FAMILY-PLAN.md`). What changes is the reference language and the IR tier it targets — not the process. The mapping registry produced in step 4 is also the foundation of the source-code converter: it is the auditable record of "this source construct means this canonical node."
