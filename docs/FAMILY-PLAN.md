# Family plan — one host, many surfaces

## The idea

We did not build "a language." We built a **canonical core plus an English surface**, and we built it fast because we grounded every semantic decision in Python's documentation. That same machinery can produce a family of surfaces that share one runtime. A user installs one interpreter and chooses the surface that fits the job — no separate toolchains.

## The hard truth to design around

A single language cannot simultaneously have Python's garbage-collected object model, Rust's ownership, C's raw pointers, and assembly's registers with one uniform semantics. If we try, we get the union of all their ambiguities and footguns. The answer is **tiers**: semantics are layered, and a surface opts into a tier.

```
  English/Py-like     JS-like        C-like         machine-like
   surface             surface        surface         surface
        \                 |              |               /
         \                |              |              /
          +-------- L1: high-level canonical IR --------+
                    (values, closures, GC, dynamic types)
                                 |
                                 v
                   L2: typed / ownership IR
              (explicit types, lifetime annotations)
                                 |
                                 v
                   L3: low-level IR
        (stack slots, explicit allocation, pointers, labels)
                                 |
                                 v
                    WASM or RISC-V backend + optional asm print
```

Surfaces are *syntax*. Tiers are *semantics*. A high-level surface cannot name a register; a low-level surface can, and the linter flags it as such. That is how we stay flexible without collapsing into incoherence.

## What each tier needs

| Tier | New semantics required | Surfaces that fit |
|---|---|---|
| L1 (shipped) | dynamic values, closures, exceptions, collections | Python-like, JavaScript-like |
| L2 | static types, generics, ownership/borrowing, trait-like interfaces | Rust-like, TypeScript-like |
| L3 | pointers, manual allocation, explicit layout, integer widths, calling convention | C-like, assembly-like |
| Backend | registers, stack, labels, jumps | emitted, not hand-written by default |

## Converter — the highest-value follow-on

The mapping registry from `METHOD.md` is the converter's specification. Design rules:

1. **Parse the source language with its real parser** (e.g. Python's `ast`, tree-sitter for others). No regex translation.
2. **Map source AST → canonical IR node** using the registry. Every mapping has a test proving equivalence.
3. **Never guess.** Unsupported constructs become an explicit marker in the output plus an entry in a conversion report with file/line and a suggested manual translation.
4. **Emit canonical llang** through the formatter, so converted code is already normalized.
5. **Verify by execution.** Run source and converted program on the same inputs and compare output on a corpus. Conversion is "correct" only for constructs with passing equivalence tests.
6. **Human/AI review the report.** The converter's job is to do the mechanical 80% and make the remaining 20% obvious, not to pretend it finished.

Realistic scope: a useful converter for a *subset* of a language is achievable; a perfect general converter for arbitrary legacy codebases is not. Say so in the docs.

Recommended converter order: **Python first** (we already have the semantic matrix and highest confidence), then JavaScript, then C.

## Libraries — the honest answer

Libraries are a first-class design problem, not an afterthought. Four layers:

1. **Registered native builtins (shipped).** Closed vocabulary, implemented in the host language, with labeled arguments and a spec table. Fast and fully documented, but limited to what we implement. Currently 53 spellings in `interpreter.BUILTINS`.

2. **llang-native modules (shipped).** A module is a `.ll` file that exports functions. It is loaded with `use the <name> module`. Because functions are first-class and maps already exist, a module can be represented as a map of functions — almost no new semantics needed. Qualified calls read naturally and need no lexer change:
   ```
   use the math module
   show call sqrt from math with value = 9
   ```
   The parser already collects word runs as call names, so `sqrt from math` is a valid name; `_call` resolves `NAME from MODULE` by looking up `MODULE` and reading the function from it.

3. **Interop bridge (shipped, opt-in escape hatch).** Expose selected host-language modules (e.g. `json`, `re`, `math`) through an explicit allowlist, with every value converted at the boundary. This buys enormous capability immediately, but it is explicitly *not* llang-native and must be labeled as such. Without it, "as capable as Python" would take years of library writing.

4. **Packaging.** A small manifest (`name`, `version`, `entry`, `exports`, `dependencies`) plus a lock file. Modules extend **values and types, never syntax** — that locked decision from `DESIGN.md` is what keeps the family coherent.

## Recommended build order

| Phase | Work | Why |
|---|---|---|
| 1 | Module system + llang-native libraries | **Shipped.** `use the X module`, qualified calls, `lib/math.ll`, `lib/text.ll`, `lib/lists.ll`, plus the labeled foreign bridge |
| 2 | Python → llang converter | **Shipped.** `src/llang/converter.py` + `tools/port.py` with coverage reports; see `docs/REWRITES.md` |
| 3 | C-like surface + L2/L3 IR | **In progress.** Grounded in `docs/research/c-like-surface-design.md` as `c-ll`; a MinGW-w64 GCC is available at `tools/cc.py` for differential verification |
| 4 | JavaScript-like surface | Web reach, very different semantics from Python |
| 5 | Interop bridge | Shipped with phase 1 as a labeled opt-in (`use the foreign X module`) |
| 6 | WASM backend | **Shipped for the integer/function subset.** `src/llang/compiler.py` + browser playground; assembly printing still future |
| 7 | Rust-like surface | Ownership is a big commitment; do it last |

Also shipped in this phase: LSP language server, editor grammars, native `json`, package manifests, property-based fuzzing, and one-command verification.

## Risks and guardrails

- **Semantic contradictions** → tier design above; never silently merge models.
- **Conversion overpromising** → report + confidence + execution tests; document supported subsets explicitly.
- **Library sprawl** → closed core vocabulary; libraries add values/types only; every module documented.
- **Surface drift** → formatter canonicalizes to one form; shared IR tests keep surfaces compatible.
- **Interop leak** → allowlist, explicit `foreign` marking, no implicit host-object access.

## Decisions locked

1. First new surface: **C-like**, which forces the L2/L3 memory-model design.
2. Opt-in interop bridge: **accepted**, explicitly labeled with `use the foreign ... module`.
3. Assembly: **backend target only**, with an optional machine-syntax mode later — not a primary readable surface.
4. Compiler architecture: **owner delegated optimization decisions to the implementation**; the chosen shape is many front-ends → one canonical IR → one shared back-end, staged as Python-written compiler → WASM/C backend → self-hosting.

## Terminal / shell layer

Grounded in **Nushell** (MIT), because it is deliberately both a shell and a structured programming language — the same bet llang makes. The full matrix is `docs/research/terminal-semantics.md`.

What was rebuilt: the **shell/command layer**, not a terminal emulator. `lib/shell.ll` is native llang; host command execution sits behind `use the foreign shell module` with visible command text, three-channel results (code/stdout/stderr), timeouts, and loud failures. A terminal emulator (PTY, ANSI parsing, event loop, graphics) is out of scope for llang today; `repl.py` covers the interactive-text case.

Nushell features deliberately omitted: line editor, theming, plugins/TUI/MCP, dataframes, background jobs, overlays, hooks, completions, dynamic `eval`, and broad codec matrices. We copy the *semantics* (structured values, pipelines as data flow, parse-before-eval, clear errors), not the syntax or Rust implementation.
