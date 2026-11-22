# llang

A programming language that reads like structured English and behaves like Python.

> **Designed to be written by AI, and easy for humans to review.** llang is
> highly interpretable and direct: explicit blocks, labeled arguments, strict
> operations, and no hidden behavior. Nothing is cryptic on purpose — the point
> is code you can understand at a glance, whether a model wrote it or you did.

```llang
set scores to a map with "Ada" mapped to 91, "Grace" mapped to 98

repeat for each student in (call keys of with collection = scores)
    show student plus ": " plus (call text of with value = item student of scores)
end repeat
```

## Start here

- [Tutorial](TUTORIAL.md) — learn the language from zero
- [Language reference](REFERENCE.md) — the authoritative specification
- [Grammar](GRAMMAR.md) — the compact grammar, small enough for an LLM prompt
- [c-ll](CLL.md) — the C-like second surface in the language family

## What exists

- A tree-walking interpreter with dynamic values, strict operations, labeled calls,
  modules, problem handling, classes, and a canonical formatter/linter
- A WebAssembly backend for the integer/function subset
- Native libraries for math, data science, machine learning, text, regex,
  CSV/JSON, a shell layer, and a headless physics engine
- A Python→llang converter with honest coverage reports and differential tests
- An LSP language server and VS Code / tree-sitter grammars

## Design idea

**Surface flexibility, canonical precision.** Many English spellings normalize to
one canonical AST node. The interpreter never reasons about synonyms, so
readability never costs determinism. See [Language design](DESIGN.md) and the
[Grounding method](METHOD.md).

## Repository

The source, examples, libraries, and verification tooling live in the
[GitHub repository](https://github.com/YOUR_ORG/llang). Replace `YOUR_ORG` in
`mkdocs.yml` and this page after creating the repository.
