# Editor support for llang

Two static assets ship with the language and require no changes to the interpreter:

| Asset | Path | What it provides |
|---|---|---|
| TextMate grammar | `editors/vscode/llang.tmLanguage.json` | Syntax highlighting in VS Code (and any editor that reads TextMate grammars) |
| tree-sitter grammar | `editors/tree-sitter/grammar.js` | A parse grammar for tree-sitter-aware editors and tooling |

The VS Code grammar covers line comments (including `# === Section ===` headers), double-quoted strings with `\n`, `\t`, `\"` and `\\` escapes, numbers, every reserved word from `src/llang/synonyms.py`, all word operator phrases and postfix predicates, builtin call names (including phrase and `_`-suffixed aliases), block openers/closers (`define function`, `end if`, `always`, …), call argument labels and the `()` `,` `=` punctuation.

---

## 1. VS Code

### Option A — install as a local extension (simplest)

1. Copy the whole folder `editors/vscode` into your VS Code extensions directory:
   - Windows: `%USERPROFILE%\.vscode\extensions\llang-vscode`
   - macOS / Linux: `~/.vscode/extensions/llang-vscode`
2. Restart VS Code (or run **Developer: Reload Window** from the command palette).
3. Open any `.ll` file. The status bar should show **llang** as the language mode. If it does not, click the language mode indicator and choose **llang**.

The folder contains:

- `package.json` — declares language id `llang`, extension `.ll`, and binds the grammar to scope `source.llang`.
- `llang.tmLanguage.json` — the TextMate grammar itself.
- `language-configuration.json` — `#` line comments, bracket matching and auto-closing pairs for `(` and `"`.

No compiled code or activation events are needed; the contribution is purely declarative.

### Option B — development host

Launch a separate VS Code window with the grammar loaded directly, without copying anything:

```powershell
code --extensionDevelopmentPath="D:\natural language code\editors\vscode"
```

Open `examples/hello.ll` in the new window to check the colours.

### Option C — package a VSIX

For sharing with a team, install the vsce CLI and package the folder:

```powershell
npm install -g @vscode/vsce
cd "D:\natural language code\editors\vscode"
vsce package
code --install-extension llang-vscode-0.1.0.vsix
```

---

## 2. tree-sitter

The grammar file is a skeleton covering the full v1 grammar (program, all statements, one-precedence expressions, literals, blocks, modules/`use`, and `expect` with problem handlers). It is plain JavaScript and can be generated with the tree-sitter CLI.

### Generate and test a parser

```powershell
npm install -g tree-sitter-cli
cd "D:\natural language code\editors\tree-sitter"
tree-sitter generate        # writes src/parser.c and src/node-types.json
tree-sitter build           # builds a shared library for local use
tree-sitter parse ..\..\examples\hello.ll
```

`tree-sitter parse` should print a parse tree with no `(ERROR)` nodes. Because the surface language is made of multi-word English phrases, if your CLI reports lexical conflicts, resolve them by adding `conflicts:` entries or `prec()` annotations in `grammar.js` — the node names there are the ones to use.

### Neovim (nvim-treesitter)

Point nvim-treesitter at the local grammar and register a filetype:

```lua
require("nvim-treesitter.configs").setup({
  parser_install_dir = vim.fn.stdpath("data") .. "/site",
  ensure_installed = {},
})
vim.filetype.add({ extension = { ll = "llang" } })
```

Then install the parser from the grammar directory with `:TSInstallFromGrammar llang` (or place the generated `parser.so` under `parser/llang.so` in the runtime path). Highlighting queries (`queries/highlights.scm`, `queries/locals.scm`) are not shipped with this skeleton; add them if you want semantic captures rather than plain TextMate colours.

### Helix

Add (or merge) an entry in `languages.toml`:

```toml
[[language]]
name = "llang"
scope = "source.llang"
file-types = ["ll"]
comment-token = "#"
roots = []

[[grammar]]
name = "llang"
source = { path = "/path/to/llang/editors/tree-sitter" }
```

Then run `hx --grammar build` and `hx --grammar fetch` as needed.

### Emacs (tree-sitter major mode)

With Emacs 29+ and a `tree-sitter-llang` package or a locally built grammar:

```elisp
(add-to-list 'auto-mode-alist '("\\.ll\\'" . llang-ts-mode))
;; point tree-sitter-language-map at the grammar built from editors/tree-sitter
```

---

## 3. Syntax-highlighting smoke test

Save the following as `smoke.ll` and open it in the configured editor. Comments must be dim, strings green, numbers and escapes distinct, keyword phrases coloured, section openers/closers visually marked, argument labels highlighted, and builtin call names coloured:

```ll
# === llang syntax smoke test ===
# A comment should be dimmed; the header above should read as a section.

set greeting to "Hello\nAda"      # string with an escape sequence
display greeting plus "!"         # operator phrase: plus
set xs to a list of 1, 2, 3       # collection literal; number literals

show call join with items = (a list of "a", "b"), separator = ","

if greeting is not empty then     # postfix predicate + section opener
    show "non-empty"
otherwise
    show "empty"
end if                            # section closer

repeat for each x in xs
    print x
end repeat

define function double taking n
also known as twice
    give back n times 2
end function

show call double with n = 21
require greeting equals "Hello\nAda", "greeting should match"

expect
    show item 99 of xs
if a problem of kind index_out_of_range occurs then
    show "caught"
end expect

use the foreign json module        # module keywords
```

Expected highlighting checks:

1. `# === ... ===` reads as a section header; the other `#` lines are plain comments.
2. `"Hello\nAda"` is one string with `\n` as an escape.
3. `plus`, `times`, `is not empty` and `equals` use the operator/predicate colour.
4. `end if`, `end repeat`, `end function`, `end expect`, `define function`, `otherwise` and `always` use the section colour.
5. `join`, `double` and module names are highlighted as calls/builtins; `items =`, `separator =` and `n =` highlight their labels.
6. `true`/`false`/`nothing`/`empty`, `a list of` and the punctuation `()` `,` `=` are all distinct from ordinary names.

You can validate the program itself with `python run.py smoke.ll`; highlighting alone is not a parser check.
