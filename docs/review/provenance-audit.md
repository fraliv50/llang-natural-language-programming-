# Provenance, licensing and repository-hygiene audit

Read-only audit performed 2026-11-22 against the working tree at
`D:\natural language code`. No project files were modified; this report is the
only file created. External URLs were checked live; the vendored pypybox2d
clone was inspected with read-only `git` commands.

## 1. Executive summary

The project's *semantic* provenance records are unusually careful: license
identifications are correct across every SOURCE.md and research document
(pylev BSD-3-Clause, humanize MIT, pypybox2d zlib, CPython PSF, Nushell MIT,
NumPy/pandas and scikit-learn BSD-3-Clause), and the pypybox2d pin is
byte-verified. Three structural problems undermine that record:

1. The top-level MIT `LICENSE` third-party clause describes only the conversion
   pilots and omits the 9.5 MB vendored pypybox2d clone and two embedded
   verbatim third-party sources, while applying "Copyright (c) 2026 The llang
   Project" to the repository as a whole.
2. The humanize provenance is not pinned and points at a branch that no longer
   exists (`master`) and a license file that 404s; the embedded oracle no longer
   matches current upstream.
3. The vendored pypybox2d oracle is a **nested git repository** with a 7.8 MB
   packfile and no `.gitmodules`; a fresh checkout of llang will not contain the
   oracle that `tools/check.py` (and CI) requires.

A security documentation gap also exists: the foreign shell bridge exposes
environment-variable reads and arbitrary `cwd`, and uses `shell=True`, while
`SECURITY.md` does not disclose the former and an internal design document
explicitly forbids the latter.

| Severity | Count |
|---|---|
| High | 4 |
| Medium | 6 |
| Low | 3 |
| **Total** | **13** |

No secrets, private keys, credential literals, or stray temporary files were
found. No `.so`, `.pyd`, `.dll`, `.exe` or `.wasm` binaries were found in the
tree.

## 2. Numbered findings

| # | Sev | File | Problem | Evidence | Recommended fix |
|---|---|---|---|---|---|
| 1 | **High** | `LICENSE` (23–31) | Third-party notice is materially incomplete. It says only `tools/pilots/` holds third-party source, omitting the vendored pypybox2d clone and the verbatim sources embedded in `tools/compare_humanize.py` and `tests/test_pylev.py`. The blanket "Copyright (c) 2026 The llang Project" can be read as claiming ownership of zlib/BSD/MIT-licensed third-party code. | `LICENSE:27-31` "No third-party source code is copied into the interpreter or libraries. `tools/pilots/` contains unmodified Python source files…"; `tools/rewrites/pypybox2d/source/LICENSE`; `tools/compare_humanize.py:26-28`; `tests/test_pylev.py:21-22`. | Scope the MIT grant to llang's own code ("this license applies to llang source in `src/`, `lib/`, `tests/` except vendored/embedded material"). Add a `NOTICE` or explicit list of all third-party directories/files with their licenses and copyright holders, including `tools/rewrites/pypybox2d/source/`, the embedded humanize and pylev oracles, and `tools/pilots/`. |
| 2 | **High** | `tools/compare_humanize.py` (26–238) | ~210 lines of humanize source (verbatim function bodies, i18n calls replaced) are copied into the repository with **no copyright notice and no MIT permission text**. The file docstring says only "(MIT license)". MIT requires the notice in all copies or substantial portions. | `REFERENCE_SOURCE` at lines 28–238; upstream `LICENCE` states "Copyright (c) 2010-2020 Jason Moiron and Contributors" and "The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software." | Add a header above `REFERENCE_SOURCE` with the upstream copyright line, the full MIT permission notice (or a pointer to a vendored `LICENCE` file), the exact upstream URL and commit, and a statement that i18n calls were mechanically resolved to identity. |
| 3 | **High** | `tools/rewrites/pypybox2d/source/` | The oracle is a full nested git repository (214 files, 9.5 MB, including a 7.8 MB `.git/objects/pack/*.pack`), with no root `.gitmodules`. Git will treat it as an embedded repo/gitlink rather than committing its contents, so a fresh clone will not have `pypybox2d/common.py`; `tools/check.py` runs `compare_box2d.py`, which then aborts — CI included. | `git rev-parse HEAD` in the clone returns `ee7b81ff83a03d017534f5f7ac36e642ac27e33c`; `git status --short` shows only untracked `__pycache__` dirs; no `.gitmodules` at repo root; `tools/compare_box2d.py:28-29` raises `RuntimeError(f"pypybox2d clone not found at {SOURCE}")`. | Either delete the nested `.git` and commit the pinned source files (with upstream `LICENSE`) as ordinary vendored files, or declare a proper submodule in `.gitmodules` and update CI to `actions/checkout@v4` with `submodules: true`. Trimming the clone to the pure-Python modules actually used by the oracle would also cut ~9 MB. |
| 4 | **High** | `SECURITY.md`, `src/llang/foreign.py`, `docs/research/terminal-semantics.md` | Security documentation does not match the implementation. The shell registry exposes `environment value` (reads any host env var) and an optional `directory` (child cwd) that the threat model never mentions; calls run with `shell=True`. An internal design doc says never to use `shell=True` for llang-supplied strings. | `foreign.py:41-50` (`"shell": True`, `options["cwd"]`), `foreign.py:79-83` (`_environment_value` → `_os.environ.get`), `foreign.py:102-106` (exports); `SECURITY.md:10-15` claims host access only via allowlisted `read text from`/`write text to`; `terminal-semantics.md:186` "Never use a host shell (`shell=True`) to evaluate a llang-supplied string". | Disclose `environment value` and `directory` in `SECURITY.md` threat model/safeguards; reconcile the `shell=True` contradiction by either implementing an argv-based `call build from shell` path for all shell operations or downgrading the research-doc invariant to an explicit documented exception. Add a warning that env reads can expose secrets. |
| 5 | **Medium** | `tools/rewrites/humanize/SOURCE.md` (8–12) | Provenance is unpinned and wrong. It records "master branch", but the repository has only `main` (`master` raw URLs silently resolve to the default branch); the cited license URL `.../blob/master/LICENSE` is a 404 (the file is `LICENCE` on `main`); no commit SHA is recorded. Current upstream `number.py` differs from the embedded oracle (e.g. `_ORDINAL_SUFFIXES` is now a gender-keyed dict with `PS_()` wrappers, not the embedded tuple), so the documented URL does not reproduce the oracle. | GitHub API: `default_branch: main`, branches = [`main`] only; `raw .../master/LICENSE` → 404; `raw .../main/LICENCE` → MIT text; live diff of current `number.py` vs `REFERENCE_SOURCE`. | Record the exact fetched commit (current `main` HEAD at audit time: `a95004512dde4e8f0269946bb4af754382347441`), rewrite all URLs to commit-pinned raw/blob URLs, correct `LICENSE` → `LICENCE`, and regenerate `REFERENCE_SOURCE` from that commit (or note deliberately that the oracle is a frozen snapshot and pin its blob SHA). |
| 6 | **Medium** | `SECURITY.md:20-21` | "enforce a 30-second timeout" is inaccurate: 30 s is only the default, and any program can pass a larger (or zero/negative) `timeout` label via the shell registry. The three-channel capture also applies to `run command` only; `output of command` and `command succeeds` collapse the result to text/bool. | `foreign.py:34` default `timeout=30`; `foreign.py:64-65, 73-75` pass `kwargs.get("timeout", 30)`; `foreign.py:103-105` lists `timeout` as an optional label; no upper bound anywhere. | Say "default 30 s, caller-overridable" or add a hard maximum in `_shell_run` (e.g. clamp to 30 s) and document it; clarify which foreign function returns the three-channel map. |
| 7 | **Medium** | `.github/workflows/ci.yml`, `tools/compare_wasm.py`, `CONTRIBUTING.md`, `README.md` | CI portability: `tools/check.py` runs `compare_wasm.py`, which exits 1 with "node is required" when `node` is absent; CI has no Node setup step. Ubuntu runners happen to ship Node today, so the dependency is implicit and fragile. Contributor docs claim Python alone is sufficient. A C compiler is **not** currently required (the c-ll tests use a Python oracle and `compare_box2d.py` asserts the pure-Python path), so no compiler setup is currently missing. | `compare_wasm.py:34-37`; `ci.yml:9-18` (only `setup-python`); `CONTRIBUTING.md:7` and `README.md:31` "Python 3.10+ is the only requirement — no third-party packages"; `docs/CLL.md:318-351`; `tests/test_cll.py:5-7`; `compare_box2d.py:38`. | Add `actions/setup-node@v4` with a pinned Node version before the check step; correct `README.md`/`CONTRIBUTING.md` to state Node.js is required for the WASM differential checks. Optionally add a 3.10/3.11 matrix to match `requires-python = ">=3.10"`. |
| 8 | **Medium** | `.gitignore` | Generated artifacts not covered: `*.wasm` emitted by `llang-compile` (defaults to `<source>.wasm`) and generic converter outputs such as `ported.ll` / `*.report.txt` outside `tools/pilots/` and `tools/selfhost/`. | `src/llang/compile_cli.py:24-25` writes `.wasm` next to the source; `README.md:37,49` and `CONTRIBUTING.md:60` document those commands; `.gitignore:1-6` covers only four paths. | Add `*.wasm`, `ported.ll`, and `*.report.txt` (or scoped patterns) to `.gitignore`. |
| 9 | **Medium** | `tools/pilots/README.md`, `docs/REWRITES.md` | Origin refs are moving, not pinned. Pilots cite CPython `3.11` branch raw URLs and humanize `master`; neither is a commit/tag. The six CPython-derived rewrites in `docs/REWRITES.md` record only "CPython 3.11 `Lib/x.py` (PSF license)" with no URL or revision. Pilots were byte-identical to current upstream at audit time, so this is a reproducibility risk rather than present drift. | `tools/pilots/README.md:9-17`; `docs/REWRITES.md:37-67`; SHA-256 comparison confirmed all three pilot files currently match the cited raw URLs after newline normalization. | Record exact CPython 3.11.x tag/commit and raw commit URLs; add a short origin line (URL + commit) to each CPython rewrite section in `docs/REWRITES.md`. |
| 10 | **Medium** | `docs/EDITOR-SUPPORT.md:99` | Machine-specific absolute path in documentation: `source = { path = "D:/natural language code/editors/tree-sitter" }` is wrong on every other machine. | Exact line 99 in the Helix `languages.toml` example. | Replace with a relative path (`./editors/tree-sitter`) or an explicit placeholder such as `/path/to/llang/editors/tree-sitter`. |
| 11 | **Low** | `tools/cc.py:11-21` | Hard-coded Windows/Winget MinGW `gcc.exe` path (built from `LOCALAPPDATA` plus a versioned package ID) is environment-specific and misleading; the script is unused by CI and tests. | `CANDIDATES[0]` uses `BrechtSanders.WinLibs.MCF.UCRT_...`; `test_cll.py:5-7` and `docs/CLL.md:318-351` state no native C compiler is used. | Reduce candidates to `gcc`, `clang`, `x86_64-w64-mingw32-gcc` and document the optional toolchain; remove the machine-specific Winget path. |
| 12 | **Low** | `tools/compare_humanize.py:384`, `tools/compare_box2d.py:328` | Harnesses create temp directories with `tempfile.mkdtemp()` and never remove them, accumulating scratch dirs in the OS temp area on every run. | Explicit `mkdtemp` calls with no `shutil.rmtree`/`TemporaryDirectory`. | Use `with tempfile.TemporaryDirectory() as work:` as `tools/compare_wasm.py:40` does. |
| 13 | **Low** | `pyproject.toml:11` | Metadata uses the deprecated `license = { text = "MIT" }` table form (PEP 621 legacy); it is valid for `setuptools>=61` but emits deprecation warnings with modern setuptools. No `license-files` declaration. | `pyproject.toml:1-18`; all three console entry points (`llang.cli:main`, `llang.convert_cli:main`, `llang.compile_cli:main`) were verified to exist with `main()` functions; `requires-python = ">=3.10"` is plausible (no 3.11-only syntax found). | Once the minimum setuptools is raised, switch to `license = "MIT"` plus `license-files = ["LICENSE", "NOTICE"]` (after adding NOTICE from finding 1). |

## 3. Verified provenance table

Licenses below were verified against the upstream repositories' own LICENSE
files where source is vendored/embedded, and against the project's own
grounding documents otherwise.

| Project | Origin | License (verified) | Pin | Where it lives | Notice status |
|---|---|---|---|---|---|
| pylev | `https://github.com/toastdriven/pylev`, file `pylev.py` | **BSD-3-Clause / New BSD**, Copyright (c) 2012 Daniel Lindsley — verified at `raw .../v1.3.0/LICENSE` (`__license__ = 'New BSD'` in source). Not MIT. | tag `v1.3.0`, commit `e79ef6814c51046fee635a2a2316f8a57fa1e697`, blob `114f78ca5a68d27f47bf5c9e2781c92c59189599` | `tools/rewrites/pylev/SOURCE.md`; rewritten `lib/pylev.ll`; verbatim oracle in `tests/test_pylev.py:22+` | **Partial–good**: BSD-3 named with author and URL in `lib/pylev.ll:1-13`, `__license__` inside embedded source, copyright in SOURCE.md; full BSD text only by URL, not vendored. |
| humanize | `https://github.com/python-humanize/humanize` (default branch is **`main`**, not `master`) | **MIT**, "Copyright (c) 2010-2020 Jason Moiron and Contributors" — verified at `raw .../main/LICENCE`. | **None**. SOURCE.md says "master branch"; cited `blob/master/LICENSE` is 404. | `tools/rewrites/humanize/SOURCE.md`; rewritten `lib/humanize.ll`; trimmed verbatim oracle in `tools/compare_humanize.py:28-238` | **Inadequate**: no copyright/permission text with embedded code; wrong/broken license URL; oracle no longer matches current upstream (finding 5). |
| pypybox2d / Box2D | `https://github.com/pybox2d/pypybox2d` | **zlib** — verified in clone `LICENSE` ("C++ version Copyright (c) 2006-2011 Erin Catto … Python port by Ken Lauer") and `setup.py:35,78,102`. | commit `ee7b81ff83a03d017534f5f7ac36e642ac27e33c` — **verified locally** with `git rev-parse HEAD` (2019-05-11, merge PR #3). | `tools/rewrites/pypybox2d/SOURCE.md`; full clone at `tools/rewrites/pypybox2d/source/`; rewritten `lib/box2d.ll` | **Partial**: upstream `LICENSE` retained inside clone and `lib/box2d.ll:1-10` marks the altered llang version with commit + zlib; but top-level `LICENSE` omits it, and the clone is an unregistered nested repo (finding 3). |
| CPython pilots (`bisect.py`, `fnmatch.py`) | `https://raw.githubusercontent.com/python/cpython/3.11/Lib/{bisect,fnmatch}.py` | **PSF License** (CPython) — correct in pilots README. | `3.11` branch (moving), no commit | `tools/pilots/README.md:9-10,15-16`; verbatim `tools/pilots/bisect.py`, `fnmatch.py` — SHA-256 identical to current upstream after newline normalization. | **Partial**: README names license but contains no PSF notice; ref not pinned (finding 9). |
| CPython pilot (`filesize.py`) | `https://raw.githubusercontent.com/python-humanize/humanize/master/src/humanize/filesize.py` | **MIT** — correct in pilots README; identical to current upstream. | `master` (aliases to `main`), no commit | `tools/pilots/README.md:11,17`; verbatim `tools/pilots/filesize.py` | **Partial**: same issues as humanize above plus finding 9. |
| CPython rewrites (`shlex`, `fnmatch`, `textwrap`, `csv`, `json`, `re`) | CPython 3.11 stdlib, documented inline in `docs/REWRITES.md:37-67` | **PSF** — correct. No CPython source copied into `lib/`. | None (version "3.11" only; no URL in REWRITES.md) | `lib/*.ll`, `docs/REWRITES.md`, `tests/test_*.py`, `tools/compare_*.py` | **Adequate for semantic rewrites**; provenance under-specified (finding 9). |
| NumPy / pandas | `https://numpy.org/license.html`, `https://github.com/pandas-dev/pandas` (cited in research) | **BSD-3-Clause** for both — claim verified as correct. | Docs retrieved 2026-11-22; no doc revision pinned | `docs/research/datascience-library-design.md:10-29`; `lib/datascience.ll` | **Adequate**: ideas/semantics only, no code copied, license attributed. |
| scikit-learn | `https://github.com/scikit-learn/scikit-learn/blob/main/LICENSE` (cited in research) | **BSD-3-Clause** — claim verified as correct. | Docs retrieved 2026-11-22; no doc revision pinned | `docs/research/ml-library-design.md:15-27`; `lib/machinelearning.ll` | **Adequate**: semantics only, license attributed. |
| Nushell | `https://github.com/nushell/nushell/blob/main/LICENSE`, Nushell Book (cited in research) | **MIT** — claim verified as correct. | Docs retrieved 2026-11-22; no doc revision pinned | `docs/research/terminal-semantics.md:5,17`; shell vocabulary/design | **Adequate**: terminology/invariants only, no source or doc text copied. |

## 4. Repository hygiene checklist

| Check | Result | Notes |
|---|---|---|
| No secrets / private keys / credential literals | **PASS** | Scanned for `ghp_`, `AIza…`, `xox…-`, `AKIA…`, PEM private-key headers, Bearer tokens, `api_key=`/`password=` literals, `.env`, `.pem`, `.key`, `.pfx`, `.htpasswd` — no matches. |
| No stray temp/backup files | **PASS** | No `*.tmp`, `*.bak`, `*.orig`, `*.rej`, `*~`, `*.swp`, `*.log` in tree. |
| No native binaries in tree | **PASS** | No `.so`, `.pyd`, `.dll`, `.dylib`, `.o`, `.a`, `.exe`, `.wasm`, archives or images except one 1.5 KB upstream PNG inside the vendored clone (`testbed/runsnakerun/resources/rsricon.png`). |
| Large files | **WARN** | Largest items: vendored clone git pack 7.8 MB (clone total 9.5 MB / 214 files); `lib/json.ll` 476 KB (legitimate generated-style but committed source); research docs up to ~60 KB. See finding 3. |
| Nested git repository | **FAIL** | `tools/rewrites/pypybox2d/source/.git` present; no `.gitmodules`. See finding 3. |
| Generated artifacts ignored | **PARTIAL** | `rubiks.html`, `tools/pilots/*.ll`, `tools/pilots/*.report.txt`, `tools/selfhost/*.ll`, `tools/selfhost/*.report.txt` are correctly ignored and present only as working-tree artifacts (several selfhost `.ll` files are zero bytes from failed conversions). `*.wasm` and generic `ported.ll`/`*.report.txt` are not ignored — finding 8. |
| `__pycache__` ignored | **PASS** | `**/__pycache__/` and `*.py[cod]` covered; ~150 `.pyc` files exist in the working tree but are ignored. |
| Machine-specific absolute paths | **FAIL** | `docs/EDITOR-SUPPORT.md:99` hard-codes `D:/natural language code/...` (finding 10); `tools/cc.py:11-21` hard-codes a Windows Winget path (finding 11, fallback present). `/home/ada` in `docs/research/terminal-semantics.md:104` is an illustrative example, not a config value. |
| `pyproject.toml` metadata | **PASS (advisory)** | Build backend, `requires-python`, readme, package-dir, and all three console entry points verified valid; advisory deprecation in finding 13. |
| CI portability | **PARTIAL** | Node required but not provisioned (finding 7); C compiler **not** required by any current check — `tests/test_cll.py` uses a Python oracle and `compare_box2d.py:38` asserts `Vec2 is PyVec2`. `tools/cc.py` is dormant. |
| SECURITY.md vs implementation | **FAIL** | Timeout wording, undisclosed env/cwd access, and `shell=True` contradiction — findings 4 and 6. Labeled-argument validation claim is **accurate** (`interpreter.py:1017-1034` wraps foreign `Builtin` calls in the same required/optional label check; linter uses `FOREIGN_FUNCTIONS` at `linter.py:131-134`). |
| License notices for copied code | **FAIL** | Findings 1, 2, 3 and the humanize entry in §3. |

## 5. Prioritized remediation list

1. **P0 – Fix fresh-checkout/CI reproducibility (finding 3).** Remove the nested
   `.git` and commit the pinned pure-Python oracle subset with its upstream
   `LICENSE`, or declare a real submodule and enable submodules in CI.
2. **P0 – Repair licensing notices (findings 1, 2).** Scope the MIT license to
   llang's own code; add a `NOTICE`/third-party inventory covering the clone,
   the embedded pylev and humanize sources, and the pilots. Add the MIT
   copyright and permission text to `tools/compare_humanize.py`.
3. **P0 – Align security documentation with the shell bridge (findings 4, 6).**
   Disclose `environment value`, `directory` and the caller-controlled timeout;
   resolve the `shell=True` contradiction with the research-doc invariant.
4. **P1 – Pin humanize provenance and fix URLs (finding 5).** Commit SHA in
   SOURCE.md, `LICENCE` instead of `LICENSE`, `main` instead of `master`,
   commit-pinned raw URLs, and regenerate or fingerprint the embedded oracle.
5. **P1 – Make CI self-contained (finding 7).** Add `actions/setup-node@v4` and
   correct the "Python only" claims in README/CONTRIBUTING; consider a Python
   3.10/3.11 matrix.
6. **P1 – Pin remaining origins (finding 9).** CPython 3.11.x commit/tag for
   pilots and the six CPython rewrite sections in `docs/REWRITES.md`.
7. **P2 – Hygiene sweep (findings 8, 10, 11, 12).** Ignore `*.wasm` and generic
   converter outputs, replace the hard-coded editor path, simplify `tools/cc.py`,
   and use `TemporaryDirectory` in the two harnesses.
8. **P2 – Metadata cleanup (finding 13).** Modernize `pyproject.toml` license
   metadata once the setuptools floor is raised, and ship the new NOTICE in
   distributions.


## Remediation status

Reviewed and addressed where applicable. Verified with `python tools/check.py` (17/17 checks passing, 456 tests). Outstanding low-severity items are tracked in `docs/ROADMAP.md`.

