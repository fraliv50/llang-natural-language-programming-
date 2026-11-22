# Publishing the llang documentation site

This guide explains how to publish the existing `docs/` tree as a static documentation site. The recommendation is **MkDocs with the Material theme**: it is Python-based (matching llang's own toolchain), needs no JavaScript build step, and renders the Markdown already in this repository without rewriting it.

Nothing in this guide has been applied to the repository. In particular, `mkdocs.yml` is **not** present — copy the block below to create it when you are ready.

---

## 1. Why MkDocs + Material

- The docs are already plain Markdown with fenced code blocks and tables; Material handles both (via `pymdownx.superfences` and the built-in tables extension).
- `mkdocs build --strict` turns broken internal links into build failures, which matters because this docs set cross-references research notes.
- GitHub Pages deployment is a single command (`mkdocs gh-deploy`), and GitHub Actions can run the same build in CI.
- No modification of existing Markdown files is required.

---

## 2. Proposed `mkdocs.yml`

Create this file at the repository root (it is intentionally not created here):

```yaml
site_name: llang
site_description: A structured-English programming language with Python semantics
site_url: https://YOUR_ORG.github.io/llang/
repo_url: https://github.com/YOUR_ORG/llang
repo_name: YOUR_ORG/llang
edit_uri: edit/main/docs/

docs_dir: docs
site_dir: site

theme:
  name: material
  features:
    - navigation.tabs
    - navigation.sections
    - navigation.top
    - content.code.copy
    - content.action.edit
  palette:
    - media: "(prefers-color-scheme: light)"
      scheme: default
      primary: deep purple
      accent: amber
      toggle:
        icon: material/brightness-7
        name: Switch to dark mode
    - media: "(prefers-color-scheme: dark)"
      scheme: slate
      primary: deep purple
      accent: amber
      toggle:
        icon: material/brightness-4
        name: Switch to light mode

markdown_extensions:
  - admonition
  - tables
  - toc:
      permalink: true
  - pymdownx.superfences
  - pymdownx.tabbed:
      alternate_style: true

plugins:
  - search

validation:
  links:
    not_found: warn       # promote to `fail` once all links are verified
```

Replace `YOUR_ORG` with the real GitHub owner. If you publish under a custom domain, set `site_url` accordingly.

---

## 3. Nav tree

This nav links **every** existing document in `docs/` and `docs/research/`, plus the two tooling pages added for editor support. Paths are relative to `docs_dir: docs`. Add this `nav:` block to the `mkdocs.yml` above:

```yaml
nav:
  - Getting started:
      - Tutorial: TUTORIAL.md
      - Language reference: REFERENCE.md
      - Grammar (v1): GRAMMAR.md
  - Design and method:
      - Language design: DESIGN.md
      - Semantic decisions: SEMANTIC-DECISIONS.md
      - Grounding method: METHOD.md
      - Family plan: FAMILY-PLAN.md
      - Roadmap: ROADMAP.md
      - Open-source rewrites: REWRITES.md
  - Tooling:
      - Editor support: EDITOR-SUPPORT.md
      - Publishing this site: SITE.md
  - Research:
      - Overview: research/README.md
      - Natural-language precedents: research/natural-language-precedents.md
      - Python semantics matrix: research/python-semantics.md
      - Standard library design: research/stdlib-design.md
      - Terminal / shell semantics: research/terminal-semantics.md
      - Test plan: research/test-plan.md
      - Flagship demo design: research/demo-design.md
```

Notes:

- The repository-level `README.md` sits outside `docs_dir` and therefore cannot be a nav target. Either leave the Tutorial as the landing page, or add a small `docs/index.md` that links back to the README and set `- Home: index.md` as the first nav entry.
- `docs/EDITOR-SUPPORT.md` and `docs/SITE.md` are new pages shipped with the editor tooling; they are included in the nav above.
- If a document is added later, add it here too; MkDocs omits unlisted pages from the nav (they are still built unless `not_in_nav: error` is configured).

---

## 4. Setup commands

From the repository root, on Windows PowerShell (the same commands work in a POSIX shell):

```powershell
python -m pip install mkdocs mkdocs-material
python -m mkdocs serve          # local preview at http://127.0.0.1:8000
python -m mkdocs build --strict # production build into ./site
python -m mkdocs gh-deploy      # publish ./site to the gh-pages branch
```

For reproducible builds, pin the tools in a dedicated requirements file (for example `docs/requirements.txt` containing `mkdocs` and `mkdocs-material`) and use `pip install -r docs/requirements.txt`. Do not add these as runtime dependencies of llang itself — the site toolchain is documentation-only.

---

## 5. Optional GitHub Actions workflow

If publishing from CI instead of a local `gh-deploy`, add a workflow that installs the pinned docs requirements and runs the strict build:

```yaml
name: docs
on:
  push:
    branches: [main]
permissions:
  contents: write
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install mkdocs mkdocs-material
      - run: mkdocs build --strict
      - run: mkdocs gh-deploy --force
```

---

## 6. Link hygiene

- Existing docs reference source files such as `src/llang/synonyms.py` in backticks; these are code references, not links, and need no change.
- Convert any relative link that points outside `docs/` (for example `../src/llang/lexer.py`) into a full `https://github.com/YOUR_ORG/llang/blob/main/...` URL, because files outside `docs_dir` are not copied into the built site.
- Run `mkdocs build --strict` before publishing; it reports broken anchors and missing nav targets.
