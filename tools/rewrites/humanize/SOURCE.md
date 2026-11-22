# Provenance — `lib/humanize.ll`

## Source

| Item | Value |
|---|---|
| Project | `python-humanize/humanize` |
| License | MIT License — copyright (c) 2010-2020 Jason Moiron and Contributors (https://raw.githubusercontent.com/python-humanize/humanize/main/LICENCE) |
| Retrieved | 2026-11-22 as a frozen snapshot of upstream `main`; the upstream repository has no `master` branch |
| Pin | upstream `main` HEAD at audit time: `a95004512dde4e8f0269946bb4af754382347441` (the embedded oracle is a frozen snapshot, not regenerated from later commits) |
| Number formatting | https://raw.githubusercontent.com/python-humanize/humanize/a95004512dde4e8f0269946bb4af754382347441/src/humanize/number.py |
| File sizes | https://raw.githubusercontent.com/python-humanize/humanize/a95004512dde4e8f0269946bb4af754382347441/src/humanize/filesize.py |
| Oracle | `tools/compare_humanize.py` embeds that fetched Python source with i18n calls resolved to identity and loads it through `importlib`; the embedded copyright/MIT notice is reproduced in `NOTICE` |

Python 3.11.8 on Windows. An installed `humanize` 4.15.0 is present; the harness
reports informational version drift against it but uses the frozen upstream
snapshot as the authoritative oracle, because the port follows that snapshot
(details below).

## Ported exactly (English/default locale)

`lib/humanize.ll` implements these single-word exports with labeled parameters:

| Function | Source function | Notes |
|---|---|---|
| `intcomma` | `number.intcomma` | `ndigits = nothing` selects the default grouping; separators fixed to `,`/`.` |
| `intword` | `number.intword` | all twelve powers through googol, including the snapshot rounding-carry fix; `fmt` is a `%.Nf`/`%0.Nf`/`%d` subset |
| `apnumber` | `number.apnumber` | AP words zero–nine, str fallback otherwise |
| `ordinal` | `number.ordinal` | teen rule, negative ints, `gender` map retained (identical tables in English) |
| `scientific` | `number.scientific` | mantissa rounding and exponent carry, Unicode superscript translation |
| `naturalsize` | `filesize.naturalsize` | decimal/binary/GNU tables, base 1000/1024, snapshot rounding-carry fix |
| `metric` | `number.metric` | SI prefixes `q`–`Q`, bucket carry, scientific fallback, special-unit spacing |

Also exported: `describe`, an llang quality-of-life call that returns a
self-describing map with every English formatting of one value.

Supporting design choices:

- All parameters are labeled and mandatory (llang has no defaults); the
  documented default is passed explicitly by each caller and by the harness.
- Wrong input *types* (nothing, list, map, boolean where a flag is expected,
  text for `metric`) raise a loud `fail with format_error, "..."`. Validation
  uses the postfix predicates `is a number`, `is text`, `is nothing` plus
  boolean equality. Unconvertible *text* still falls back to the raw text,
  matching humanize.
- Python's `int()`/`float()` parsing and `%f`/`,` formatting are re-expressed
  in llang (digit scanning, fixed-decimal construction, comma grouping), not
  regex and not host `printf`. The allow-listed foreign math module supplies
  only `floor`, `ceil` and `log`, exactly as `lib/advanced_math.ll` does.
- Non-finite inputs return `"NaN"`, `"+Inf"`, `"-Inf"` like humanize's
  `_format_not_finite`. Negative zero is preserved in `fixed`/`scientific`.

## Deliberately omitted

1. **i18n / gettext.** Every `_`, `N_`, `NS_`, `P_`, `_ngettext`,
   `_pgettext`, `decimal_separator()` and `thousands_separator()` call is
   resolved to its English/default-locale value. No catalog loading, locale
   activation, translation files, or alternate decimal/thousands separators.
2. **Other functions in `number.py`.** `fractional` (needs `fractions.Fraction`
   and `limit_denominator`) and `clamp` (needs format strings/callables and
   `None` returns) were not ported; they are candidates for a later rewrite.
3. **Other `humanize` modules** (time, filesize helpers beyond `naturalsize`,
   etc.) are out of scope.
4. **Python-specific permissiveness.** `None`/list/map inputs fail with
   `format_error` instead of returning `str(value)`; `metric` rejects text
   where Python raises `TypeError`. These are documented QoL divergences,
   exercised in `tests/test_humanize.py`, and excluded from the value corpus.
5. **Format-string generality.** `intword`/`naturalsize` accept printf-like
   `%.Nf`, `%0.Nf` and `%d`; Python's full `%`-format mini-language and
   `str.format` specs are not implemented. `format` is parsed for its decimal
   digit count only.
6. **Regexes** — none used, per the rewrite rules.

## Version differences observed (snapshot vs installed 4.15.0)

The harness found 5 corpus cases where the installed 4.15.0 disagrees with the
frozen upstream snapshot. These are real upstream changes, not port defects:

- `naturalsize`: the snapshot adds a rounding-carry step (999999 bytes is
  `"1.0 MB"`); 4.15.0 emits `"1000.0 kB"`. the snapshot also stores suffixes without
  a leading space and inserts the space separately; 4.15.0 bakes it into the
  suffix strings. English output is otherwise identical.
- `metric`: the snapshot computes digits with `max(0, precision - exponent % 3 - 1)`
  and fixes the rounding carry by recomputing the bucket; e.g.
  `metric(1e-14, precision=4)` is `"10.00 f"` in the snapshot but `"10.0 f"` in
  4.15.0.
- `intword`: the snapshot compares the rounded mantissa against the *integer*
  ratio between powers, fixing the carry for values above ~1e22; `10**24 - 1`
  is `"1.0 septillion"` in the snapshot but `"1000.0 sextillion"` in 4.15.0.
- `number.py` in the snapshot has extra no-op i18n scaffolding (`N_`, `PS_`, `NS_`,
  `P_`); the English results are unchanged.

## Verification

```
python run.py --lint lib/humanize.ll                 # no diagnostics
python tools/compare_humanize.py                     # compared 227 cases, 0 mismatches
python tests/test_humanize.py                        # 13 tests, OK
```

The corpus covers negative/positive integers, large integers (through
`10**100`), floats, zero and negative zero, punctuation-bearing text,
non-finite inputs, rounding boundaries for `intcomma`/`intword`/`ordinal`/
`naturalsize`/`metric`, and seven loud-validation error cases.
