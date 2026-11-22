# pylev — rewrite provenance

## Source fetched

| Item | Value |
|---|---|
| Project | [toastdriven/pylev](https://github.com/toastdriven/pylev) — "A pure Python Levenshtein implementation that's not freaking GPL'd." |
| File fetched | `pylev.py` (single-module release), 6824 bytes |
| URL | https://raw.githubusercontent.com/toastdriven/pylev/v1.3.0/pylev.py |
| Branch / tag | tag `v1.3.0` (the default branch is `main`) |
| Exact commit | `e79ef6814c51046fee635a2a2316f8a57fa1e697` |
| Blob SHA | `114f78ca5a68d27f47bf5c9e2781c92c59189599` |
| Fetched on | 2026-11-22 |

The URLs suggested in the task (`.../master/pylev.py` and `.../main/pylev.py`)
both return **404**: from 1.4.0 onward the code moved into a `pylev/` package
(`classic.py`, `recursive.py`, `wf.py`, `wfi.py`, `damerau.py`), and `master`
no longer exists. The last release with a root-level `pylev.py` is `v1.3.0`,
which is also the release that defines the `levenshtein` and
`damerau_levenshtein` functions the task asks us to mirror. That tag is the
oracle used here. The current `main` HEAD at fetch time was
`700700ec1b3f637ef1a59bb46f1b2176def2886d` (1.5.0 alpha); its algorithms
are unchanged in substance, and `levenshtein = wfi_levenshtein` there too.

## License

The task description called pylev MIT; the repository's `LICENSE` is actually
the **New BSD / 3-clause BSD license**, Copyright (c) 2012, Daniel Lindsley.

- https://raw.githubusercontent.com/toastdriven/pylev/v1.3.0/LICENSE
- `__license__ = 'New BSD'` in the fetched `pylev.py`

No Python source code was copied into `lib/pylev.ll`. The verbatim Python
source is embedded as a Python string in `tests/test_pylev.py` solely as an
executable differential oracle (loaded with `importlib`), with the copyright
and license preserved above and in the file header of the llang module.

## Semantics copied (re-expressed in llang)

- `wfi_levenshtein` → `levenshtein` (`lib/pylev.ll`). Iterative Wagner–Fischer
  with two rolling rows `d0`/`d1`, the shorter string used as the inner
  iterator, substitution/insertion/deletion minima, and the early exits for
  equal strings and empty strings. This is what pylev 1.3.0 exports as
  `levenshtein`.
- `damerau_levenshtein` → `dameraulevenshtein` (alias
  `damerau_levenshtein`). Same rolling DP plus the third row `dprev` and the
  adjacent-transposition case `s1[i] == s2[j-1] and s1[i-1] == s2[j]` with
  cost `dprev[j-1] + 1`. The rotation `dprev, d0, d1 = d0, d1, dprev` is
  reproduced exactly.
- The optimal-string-alignment (OSA) recurrence → `osadistance` (alias
  `osa_distance`). **pylev has no function by this name** (that name comes
  from other edit-distance libraries). Its semantics are the classic OSA DP,
  and exhaustive checks over all strings of length ≤ 3 on the alphabet
  `abc` confirmed that pylev's `damerau_levenshtein` is exactly this
  restricted/O variant — so pylev's function doubles as the oracle for both
  transposition-aware functions.
- Index-by-index character access, Unicode code-point semantics (Python `str`
  and llang `text` both index code points), and pylev's exact tie-breaking
  (strict `<` comparisons, so earlier candidates win).
- Input validation: pylev raises `TypeError` on non-text input; the llang
  module raises a catchable `edit_error` problem with a clear message instead
  (the harness maps both to `"ERROR"` when diffing).

## Omitted / not applicable

- `classic_levenshtein`, `recursive_levenshtein`, `wf_levenshtein` — all
  compute the same plain Levenshtein distance as the exported `levenshtein`;
  they are alternative implementations, not extra semantics. (The recursive
  variants also rely on Python slicing and memo dicts.)
- The misspelled compatibility aliases `levenschtein` and
  `classic_levenschtein` (single-word llang aliases `lev`,
  `damerau_levenshtein` and `osa_distance` are provided instead).
- `sys.version_info` / `xrange` Python 2 shim, docstrings, benchmarks,
  packaging, setup files and the upstream `tests.py` (its curated cases were
  folded into `tests/test_pylev.py` along with extra Unicode/transposition
  cases).
- No performance optimization beyond the two/three rolling rows already used
  by pylev; no banded or early-abort variants.

## Verification

- `python run.py --lint lib/pylev.ll` — no diagnostics.
- `python -m unittest discover -s tests -p test_pylev.py` — 8 tests pass,
  including per-case differential checks in both argument orders.
- `python tools/compare_pylev.py` — **compared 222 cases, 0 mismatches**
  (70 string pairs + 4 rejected non-text pairs, across 3 functions).
- An additional one-off randomized differential (400 pairs of length 0–12
  over `abcABCé日🐱`, whitespace and newlines) reported **compared 1212 cases,
  0 mismatches**.
