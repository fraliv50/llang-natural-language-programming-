# Language Design — Working Agreement

*Status: agreed approach, pre-implementation. Update as decisions change.*

## 1. Goals

- The most intuitive, easy-to-read, easy-to-write code we can make.
- Structured and orderly — not cryptic.
- Capable of anything Python is capable of (capability comes from the runtime/library layer over time, not from terse syntax).
- Workspace: "natural language code".

## 2. Decisions locked

| Decision | Choice | Reason |
|---|---|---|
| Implementation | Tree-walking interpreter written in Python | Full control over syntax and error messages; fast iteration; no toolchain friction |
| Syntax core | Python-like (familiar, minimal) | Reduce design complexity; readability via a surface synonym layer, not a bespoke grammar |
| Type system | Dynamic | Reduce design complexity; safety via the mechanisms in §5, not static typing |
| Methodology | Thin end-to-end vertical slice, then grow feature-by-feature with tests | Avoid "massive project" paralysis |

## 3. Central principle: surface flexibility, canonical precision

The surface language (what the writer types) is flexible and readable. The canonical core (the AST the interpreter executes) is tiny and unambiguous. A **desugaring pass** maps every surface form to exactly one canonical node.

- The interpreter only ever handles canonical nodes.
- Synonyms are pure sugar: they can never change semantics.
- Flexibility lives in one auditable place (the desugarer); reliability lives in one small place (the core).

### Example synonym sets (closed, documented vocabulary)

| Concept | Surface forms | Canonical node |
|---|---|---|
| Greater than | `>`, `is greater than`, `exceeds` | `GreaterThan(a, b)` |
| Equality | `==`, `is equal to`, `equals` | `Equal(a, b)` |
| Output | `print`, `display`, `show` | `Print(value)` |
| Definition | `def`, `define`, `function` | `FunctionDef(...)` |

Synonyms are a curated, closed set in v1 — no user-defined syntax, aliases, macros, or operator overloading.

## 4. Descriptors

Descriptors are optional, declarative annotations that document intent and may be checked at runtime. They are **not** a static type system; the core stays dynamic.

- **Named arguments** — `display(message="hi", times=2)` — self-documenting calls.
- **Optional assertions** — `expect age > 0`, `expect name is not empty` — loud, programmer-written runtime checks.
- **Descriptive identifiers** — the primary, always-available readability tool.

## 5. Bulletproofing mechanisms

1. Canonical AST is the single source of truth for semantics.
2. Desugaring is the only place synonyms are handled — one place to audit and test.
3. **No implicit type coercion** — incompatible operations raise clear errors, never silent wrong answers.
4. **Undefined-name / duplicate-definition lint pass** before execution — catches typos even in a dynamic language.
5. Deterministic, documented evaluation order (left-to-right).
6. Every error carries a source location and "did you mean …" suggestions where possible.
7. Test every canonical node; add desugaring-equivalence tests proving synonyms produce identical ASTs.
8. No undefined behavior: every construct has a defined result or a defined, loud error.

## 6. Guardrails (keep design complexity down)

- Closed synonym vocabulary in v1.
- No macros, user-defined syntax, operator overloading, or metaprogramming in v1.
- No implicit conversions.
- Small, small core AST.

## 7. Roadmap (status)

Phases 0–6 are shipped: scaffold/REPL, lexer/parser/canonical AST/evaluator, synonym desugaring + equivalence tests, control flow, functions with aliases and labeled arguments, collections/iteration/postfix predicates, problem handling, builtins, formatter, linter, modules, shell layer, open-source rewrites, and the Python-to-llang converter. See `docs/ROADMAP.md` for the honest current scope, deliberate divergences from Python, and explicitly deferred features (classes, comprehensions, generators, defaults, compiler backend).

## 8. AI-first design (primary consumer)

The primary author and consumer of this language is an AI (LLM), not a human. Design for that.

- No need to optimize for keystrokes — prefer verbose, descriptive keywords and identifiers.
- Regular, explicit grammar with clear delimiters; minimal special cases.
- Natural-language phrasing is an advantage, not a novelty: LLMs are trained on natural language and already write excellent pseudocode. This language should be *structured pseudocode*.
- Synonyms let the model choose the phrasing that fits the context; the canonical core (§3) guarantees determinism.
- Fast, precise diagnostics let the model self-correct.
- Risk: a natural-language surface can introduce ambiguity — mitigated by §3 (desugaring to a canonical core).

## 9. Grounding methodology (side-by-side with a reference language)

Do not invent semantics from scratch. Ground every construct side-by-side with a reference language's documentation, kept open at every step.

- **Reference language:** Python (matches the capability goal; authoritative docs available).
- **Artifact:** a semantic reference matrix mapping each Python construct → precise semantics / evaluation order / edge cases → our natural-language surface form → canonical AST node.
- This is "reverse engineering / decompiling": our language is a natural-language *re-expression* of a proven semantic core, not a new semantics. Guesswork is eliminated because Python's docs settle the hard cases.
- **Efficiency is a backend concern, not a surface concern.** Interpreter-in-Python is the first engine; keep the canonical core small and clean so a bytecode/native backend can be added later without changing the surface language.
- Use parallel sub-agents for research tasks (reference matrix, precedent studies) to reduce guesswork.

## 10. Open items

- Project name (placeholder: "the language").
- Exact synonym vocabulary — grow organically, document additions here.
- Final syntax details per phase — decided just before each phase is built.
- Final backend choice: interpreter-first (default) vs. efficient target from day one.

## 11. Revised decisions after precedent research (see §9 grounding)

- **Synonyms are a feature, not a bug.** Closed vocabulary only; every synonym normalizes to one canonical node. This gives the AI writer many phrasings while keeping the IR deterministic. A formatter will normalize surface spellings to one canonical form for stable diffs.
- **Function aliases:** a function may declare multiple names that all bind to one implementation — "more options to place into functions." Calling any alias is identical.
- **Bring back explicit delimiters:** `end if`, `end repeat`, `end function`. Indentation does not determine scope (prompts/diffs mangle whitespace).
- **One precedence, left-associative; parentheses for grouping.** No precedence table, no contextual keywords.
- **Labeled call arguments** (`call f with name = x`) instead of bare positional arguments.
- One statement per line; reserved structural words cannot be identifiers.
- Error messages with source location + expected-token lists are part of the spec, not an afterthought (the LLM self-correction loop depends on them).
- The full grammar is published in `docs/GRAMMAR.md` — compact enough to fit in a prompt and machine-readable enough to drive constrained decoding later.

## 12. Historical traps to avoid (from precedent research)

| Trap | Historical failure | Our containment |
|---|---|---|
| Unbounded grammatical variation | AppleScript, Inform 7 | Closed vocabulary, one canonical form, synonyms normalize |
| Reserved-word collisions with identifiers | AppleScript `yes` | Reserved words rejected as identifiers with a suggestion |
| Contextual name resolution (`me`, `target`) | HyperTalk | No implicit context; all names explicit and globally resolvable |
| Keywords ignored during binding | Gherkin | Structural words participate in resolution; ambiguous bindings rejected |
| Syntactic sugar hides control flow | Inform 7 | Keep structure visible (`end if` etc.) |
| Per-library vocabulary drift | AppleScript dictionaries | Libraries extend values/types, never syntax |
| "Valid but wrong" generation | All LLM DSL work | Semantic validator + tests + localized errors; reject-and-repair, never guess-and-continue |
