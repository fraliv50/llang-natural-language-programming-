# Data-science library design for llang (grounded in NumPy + pandas)

*Research artifact for a first-class, LLM-readable data-science library. Follows the
grounding method in [`../METHOD.md`](../METHOD.md): one authoritative spec per
concept, an executable oracle, semantics copied, phrasing invented. Where this
document disagrees with `src/llang/`, the code wins.*

---

## 1. Why NumPy and pandas are the authorities; licenses; copy vs invent

**Why these two.** NumPy is the de-facto authority for array semantics — shape,
0-based indexing, slicing, broadcasting, elementwise ufuncs, and reductions on
homogeneous N-dimensional data ([NumPy absolute beginners](https://numpy.org/doc/stable/user/absolute_beginners.html),
[NumPy routines by topic](https://numpy.org/doc/stable/reference/routines.html)).
pandas is the authority for tabular/dataframe semantics — named columns, missing
data, selection, filtering, group-by, describe, and database-style joins
([pandas user guide](https://pandas.pydata.org/docs/user_guide/index.html),
[pandas DataFrame reference](https://pandas.pydata.org/docs/reference/frame.html)).
Together they settle every question a small data library must answer; we do not
guess. The oracle principle from `METHOD.md` §42–66 applies exactly: official docs
give us settled semantics *and* a completeness checklist; installed `numpy` and
`pandas` give us a differential test. Local probe versions: numpy 2.1.3, pandas
3.0.1 (online docs show NumPy 2.5 / pandas 3.1.1; the semantics relied on here are
stable across these releases).

**Licenses.** NumPy is BSD-3-Clause ([NumPy license](https://numpy.org/license.html));
pandas is BSD-3-Clause ([pandas GitHub](https://github.com/pandas-dev/pandas)).
CPython, which our existing `csv.ll`/`json.ll` re-express, is PSF-licensed. We
**re-implement behavior in llang**; we copy no source code, so we inherit no
copyleft obligation, but we record the attribution in module headers exactly as
`lib/csv.ll` and `lib/json.ll` already do.

**What we copy (semantics) vs invent (phrasing).** Copied: result of `sum`/`mean`
on empty and missing data, skip-NA defaults, stable-sort and first-occurrence
rules for duplicates, inner/left join row multiplication, column-order
preservation, transpose shape, dot-product dimensional rule, dtype upcast
(int column + float scalar -> float). Invented: the English names and labeled
arguments (`call average with values = ...`), the dataset map shape, the
`nothing` missing sentinel (instead of NaN/NA/pd.NA), the loud-error policy, and
self-describing metadata. Synonyms for a phrase must produce *identical* ASTs
(`METHOD.md` step 4; `synonyms.py`), so phrasing flexibility never leaks into
evaluation.

---

## 2. Cross-cutting invariants (write these first)

### 2.1 Shape, indexing, broadcasting
- NumPy: `a.shape` is a tuple; `ndim = len(shape)`, `size = prod(shape)`; axis 0
  is rows, axis 1 columns. Indexing is 0-based, negative indices allowed, slicing
  returns **views** that alias the original ([NumPy beginners, "Array
  fundamentals"/"Indexing and slicing"](https://numpy.org/doc/stable/user/absolute_beginners.html)).
  Broadcasting: dimensions are compatible when equal or one of them is 1, else
  `ValueError` (same source, "Broadcasting").
- pandas: `df.shape` is `(rows, columns)`; `df[name]` -> Series (1-D),
  `df[[a,b]]` -> DataFrame; `.iloc[i]` is positional, `.loc` is label-based
  ([pandas DataFrame reference](https://pandas.pydata.org/docs/reference/frame.html)).
- **llang mapping.** There are no arrays, no views, no negative indices, and no
  slicing (`REFERENCE` §9). A Dataset's *shape* is the map
  `{"rows": N, "columns": K}`; indexing is `item "name" of columns` (column) or
  `item i of a column list` (row, 0-based, negative rejected — `REFERENCE` §4.4).
  Because list/map assignment aliases (`REFERENCE` §3), every "copy" in this
  library is an explicit fresh build; helpers never mutate their input dataset.
  Broadcasting is reduced to two explicit cases: elementwise list-with-scalar
  (`scale`) and elementwise list-with-list (`combine`, equal lengths only, no
  NumPy shape coercion). Reductions always run down a column (NumPy `axis=0`);
  there is no general `axis` label.

### 2.2 Missing data: NaN vs nothing
- NumPy uses IEEE `nan`; it **propagates**: `np.array([1,np.nan,3]).mean() == nan`,
  `sum() == nan`, and `nanmean`/`nansum` skip it (probe: `nanmean -> 2.0`,
  `nansum -> 4.0`). `np.mean([]) -> nan` (with warning); `np.max([])` raises
  `ValueError: zero-size array to reduction operation maximum`.
- pandas treats `NaN`, `None`, and `pd.NA` as missing; reductions have
  `skipna=True` by default (`Series([1,None,3]).sum() == 4.0`,
  `.mean() == 2.0`, `.count() == 2`), `fillna`/`dropna` handle the rest
  ([pandas missing data](https://pandas.pydata.org/docs/user_guide/missing_data.html)).
- **llang mapping.** One canonical missing value: `nothing` (test with the
  postfix predicate `is nothing`, `REFERENCE` §4.2). A float `nan` can enter via
  `call to number with text = "NaN"` or `json.parse`, but its `equals` is always
  false, so it is normalized to `nothing` on dataset ingress. All library
  aggregation helpers default to pandas' skip-missing behavior and expose a
  `skip missing` boolean label (mandatory, pass `true`/`false` explicitly — no
  defaults exist in llang, `REFERENCE` §5.3). Comparisons against `nothing` are
  false (pandas NA-comparison rule), so `where` never selects a missing cell;
  `missing` and `fill` are the explicit tools.

### 2.3 Columnar vs row-oriented representation
NumPy is row-major (C order) by default; pandas DataFrames are columnar blocks
(`df.iloc[i]` materializes a row) ([pandas DataFrame reference](https://pandas.pydata.org/docs/reference/frame.html)).
We choose **columnar** because it maps directly onto a map of named lists,
avoids duplicating data, and makes `column`, `where`, `aggregate`, and `order`
simple loops over existing lists. Rows are derived: row *i* is the value at
index *i* of every column in `order`. Row-oriented helpers (`row`, `records`,
`load_csv`, `attach`, `distinct`) materialize row maps only as intermediate
values. Invariant: **all columns have equal length**; violations are a loud
error at build time (the llang analogue of NumPy's "shape must be rectangular"
rule, [NumPy beginners](https://numpy.org/doc/stable/user/absolute_beginners.html)).

### 2.4 Insertion order
llang maps are Python dicts: literal keys keep insertion order, duplicate keys
keep the last value but the first position, and `set item` on an existing key
keeps its position (`REFERENCE` §3, §4.3, §5.1). pandas column labels and
`drop_duplicates(keep="first")` are order-preserving in the same way. Therefore
`order` is a list of names, defaulting to the `columns` map's iteration order;
`select`, `distinct`, `where`, `order`, and `attach` preserve row order unless a
sort is explicitly requested. This is a deliberate contract: LLMs can predict
output order, and differential tests can compare structurally.

### 2.5 Dtype and coercion rules
NumPy upcasts on construction — probe: `np.array([1, 2.5, 3]).dtype == float64`
— and every ndarray is homogeneous ([NumPy beginners](https://numpy.org/doc/stable/user/absolute_beginners.html)).
pandas allows per-column dtypes and explicit `astype`; implicit coercion is
rare. llang has **no implicit coercion** (`REFERENCE` §1, §9): `"5" plus 5`
fails. Library rules:
- Each column is a list whose elements are all numbers (int/float mixed allowed
  and treated as float for arithmetic), all text, all booleans, or all
  `nothing`. A column mixing text and numbers is rejected unless built by
  `load_csv` (where every cell is text — pandas' `dtype=str` behavior).
- Conversion is **only** via `convert` with an explicit `kind` ("number" or
  "text"), mirroring `Series.astype`/`np.ndarray.astype` but failing loudly
  instead of producing NaN on bad input.
- Group/join keys should be text or whole numbers. Caveat: llang map keys are
  Python-hash-based, so `true` and `1` collide as keys while
  `true equals 1` is false (`REFERENCE` §3) — reject boolean keys in `group`
  and `attach` rather than guess.
- `to number` uses Python `int()` then `float()` semantics (`REFERENCE` §6.1),
  so it accepts signs and whitespace — use it inside `convert`.

### 2.6 Aggregation semantics (pinned by local probe)
| Operation | pandas / NumPy result | llang result |
|---|---|---|
| `sum` of `[1,2,3]` | 6 | 6 |
| `sum` of empty | NumPy `0.0`; pandas `0` | 0 |
| `mean` of `[1,2,3]` | 2.0 | 2.0 |
| `mean` of empty | `nan` (both) | `nothing` |
| `min`/`max` empty | NumPy raises `ValueError`; pandas `nan` | `nothing` (no exception — llang prefers a value + optional `require`) |
| skip missing | pandas default skipna=True; NumPy propagates | default skip missing; `skip missing = false` propagates `nothing` |
| `count` | pandas counts non-NA (probe: 2 of `[1,None,3]`) | count of non-`nothing` cells |
| `groupby` mean/sum/count | `{'a':85.0,'b':82.5}` / `{'a':170,'b':165}` / `{'a':2,'b':2}` | same map shape; NA keys dropped (pandas default) |
| `drop_duplicates` | first occurrence kept, order preserved | same |
| inner/left merge | inner keeps matched keys only; left fills unmatched right with NaN | inner/left with `nothing` fill |
| `describe` | count/mean/std/min/25%/50%/75%/max | count/missing/min/max/mean only (std/quantiles omitted in v1) |

---

## 3. Concrete data representation proposal

A **Dataset is an ordinary llang map** — no new type, no new syntax. It has three
required keys and optional metadata:

```
"kind"     -> "dataset"                  # discriminator, readable in `show`
"columns"  -> map: column name (text) -> list of cell values
"order"    -> list of column names (text), in display/serialization order
"source"   -> optional text (e.g. "people.csv"), set by loaders
"notes"    -> optional text
```

Exact llang shape (parentheses required around collection literals that appear
as values before another map entry — `REFERENCE` §4.4):

Expanded for reading (the grammar requires one statement per line, so the
actual assignment is the single expression below):

```
set people to a map with
    "kind" mapped to "dataset",
    "columns" mapped to (a map with
        "name" mapped to (a list of "Ada", "Grace", "Lin", "Ada"),
        "score" mapped to (a list of 90, 95, 80, 70),
        "group" mapped to (a list of "a", "b", "a", "b")),
    "order" mapped to (a list of "name", "score", "group"),
    "source" mapped to "people.csv"
```

As one valid expression per the grammar:

```
set people to a map with "kind" mapped to "dataset", "columns" mapped to (a map with "name" mapped to (a list of "Ada", "Grace", "Lin", "Ada"), "score" mapped to (a list of 90, 95, 80, 70), "group" mapped to (a list of "a", "b", "a", "b")), "order" mapped to (a list of "name", "score", "group"), "source" mapped to "people.csv"
```

Rendered by `show call overview with dataset = people`, this is self-describing:
`{kind: dataset, rows: 4, columns: 3, missing: 0, ...}`. Row *i* is derived:
`{"name": "Ada", "score": 90, "group": "a"}` for `i = 0`. Builders:

- `table` — from a map of equal-length lists (P0). `order = nothing` means
  `keys of columns` (insertion order). Validates equal lengths and non-empty
  column names.
- `records` — from a list of row maps (P0). Missing keys become `nothing`
  (pandas from-records behavior); column order = first row's key order, then
  newly seen keys appended.
- `load_csv` — wraps `lib/csv.ll`'s `read_rows` (P1); first row becomes `order`
  when `header = true`; every cell is text; duplicate header names are a loud
  error.
- `load_json` — wraps `lib/json.ll`'s `parse` (P1); accepts a list of maps
  (records) or a map of lists (columns); `null` maps to `nothing`.
- `harvest` — inverse: Dataset -> list of row maps, for `json.stringify` (P1).

All builders return a **fresh** map; no function mutates its input (llang has no
copy operation, `REFERENCE` §3, so fresh construction is the only safe policy).
The module is `lib/datascience.ll`, loaded with `use the datascience module`.

---

## 4. Prioritized API table

All names are single-word llang identifiers; every parameter is a **label** and
is mandatory — pass `nothing` (or `true`/`false`) for an option you would call
"optional" in Python. Every function validates its labels with `require` and
postfix predicates and fails loudly with `fail with KIND, "message"`.

| llang function (labels) | Semantics | NumPy / pandas equivalent | Edge cases | Priority |
|---|---|---|---|---|
| `table` (`columns`, `order`) | Build Dataset from map of equal-length lists; `order = nothing` -> map insertion order | `pd.DataFrame(dict)`; `np.array` from sequences | unequal lengths -> `bad_shape`; empty map -> 0×0 dataset | P0 |
| `records` (`rows`, `order`) | Build from list of row maps; missing keys -> `nothing` | `pd.DataFrame(list_of_dicts)`, `from_records` | non-map row -> `bad_row`; first-row key order + new keys appended | P0 |
| `column` (`dataset`, `name`) | Column as a list, missing values preserved | `df[name]` -> Series; `a[:, j]` | unknown name -> `unknown_column` | P0 |
| `select` (`dataset`, `names`) | New Dataset with named columns, in given order | `df[[...]]` | unknown/duplicate name -> loud error | P0 |
| `where` (`dataset`, `column`, `operator`, `value`) | Keep rows where `column operator value` is true; operators: `equals`, `does not equal`, `is greater than`, `is less than`, `is at least`, `is at most`, `contains` | `df[df[c] > v]`; boolean mask `a[a > v]` | `nothing` never matches; mixed types -> error; `contains` on text = substring, on list = membership | P0 |
| `order` (`dataset`, `column`, `descending`) | Stable sort rows by one column (new Dataset) | `df.sort_values(by, ascending=...)`; `np.sort` | `nothing` sorts last; equal keys keep original order | P0 |
| `aggregate` (`dataset`, `column`, `method`) | `method` in `sum`/`mean`/`min`/`max`/`count` -> number | `Series.sum/mean/min/max/count`; `np.sum/mean/min/max` | empty: sum 0, count 0, mean/min/max `nothing`; skip missing default | P0 |
| `group` (`dataset`, `key`, `column`, `method`) | Map key-value -> aggregate over one value column (one key only) | `df.groupby(key)[col].agg(method)` | NA keys dropped; boolean/duplicate keys rejected; key order = first appearance | P0 |
| `distinct` (`dataset`, `names`) | Datasets of first occurrences of named columns, order preserved | `df.drop_duplicates(subset=...)`; `np.unique(axis=0)` | first kept by default; `nothing` treated as a value | P0 |
| `fill` (`dataset`, `column`, `value`) | Replace `nothing` with `value` | `Series.fillna`, `df.fillna` | `value` type must match column type | P0 |
| `drop missing` -> `omit` (`dataset`, `names`) | Drop rows with `nothing` in any named column | `df.dropna(subset=names)` | all rows dropped -> valid empty Dataset | P0 |
| `missing` (`value`) | Boolean: true for `nothing` or normalized float NaN | `pd.isna`, `np.isnan` | `nothing is nothing` is the native test (`REFERENCE` §4.2) | P0 |
| `convert` (`dataset`, `column`, `kind`) | New Dataset with column cast to "number" or "text" | `Series.astype`, `ndarray.astype` | unparseable -> `bad_conversion` (no silent NaN) | P0 |
| `dimensions` (`dataset`) | Map `{"rows": N, "columns": K}` | `df.shape`, `a.shape` | 0-row/0-column datasets | P0 |
| `dot` (`left`, `right`) | Dot product of two equal-length numeric lists -> number | `np.dot`, `DataFrame.dot` | length mismatch -> `bad_shape`; missing propagates | P0 |
| `scale` (`values`, `factor`) | Elementwise list × scalar (broadcast scalar) | `a * scalar` | non-numeric factor -> error | P0 |
| `combine` (`left`, `right`, `operation`) | Elementwise `add`/`subtract`/`multiply`/`divided by` on equal-length lists | `np.add/subtract/multiply/divide`, Series arithmetic | unequal lengths -> error; division by zero -> llang `Division by zero` | P0 |
| `load_csv` (`text`, `header`) | Parse via `csv.read_rows`; header row names columns | `pd.read_csv(dtype=str)` | duplicate/blank headers -> error; CRLF and quoted cells supported | P1 |
| `load_json` (`text`) | Parse via `json.parse`; records or column-map shape | `pd.read_json`, `json_normalize` | other shapes -> `bad_json_shape` | P1 |
| `harvest` (`dataset`) | Dataset -> list of row maps (JSON-ready) | `df.to_dict("records")` | preserves `order` and row order | P1 |
| `row` (`dataset`, `index`) | Row as a map | `df.iloc[i]` | index out of range -> `index_out_of_range` | P1 |
| `overview` (`dataset`) | Self-describing map: kind, rows, columns, per-column kind + missing count | `df.info()` | — | P1 |
| `describe` (`dataset`, `columns`) | Map per numeric column: count/missing/min/max/mean | `df.describe()` | non-numeric columns skipped; std/quantiles deferred | P1 |
| `tally` (`dataset`, `column`) | Map distinct value -> frequency | `Series.value_counts()`; `np.unique(return_counts=True)` | `nothing` excluded (pandas default) | P1 |
| `filter` (`dataset`, `predicate`) | Rows where `predicate(row map)` is truthy | `df[df.apply(fn, axis=1)]` | predicate must be a function value; `apply` builtin supplies positional args | P1 |
| `transpose` (`dataset`) | Swap rows/columns into a new Dataset | `df.T`, `a.T` | only for all-numeric datasets; column names become first column | P1 |
| `attach` (`left`, `right`, `key`, `how`) | Join on one key column; `how` = `inner`/`left` | `df.merge(..., on=key, how=how)` | duplicate right keys multiply rows (pandas rule); left unmatched -> `nothing`; mixed key types -> error | P1 |
| `append` (`top`, `bottom`) | Vertical concatenation | `pd.concat([...])`, `np.concatenate(axis=0)` | column sets/order must match exactly | P1 |
| `rename` (`dataset`, `mapping`) | Rename columns, order preserved | `df.rename(columns=...)` | unknown old name -> error | P2 |
| `count value` -> `count` (`values`) | Count non-missing values in a plain list | `Series.count`, `np.count_nonzero(~isnan)` | — | P2 |

P0 is the first release: enough for select/filter/sort/aggregate/group/distinct,
missing handling, type conversion, shape, and 1-D math. P1 adds I/O composition,
joins, summaries, and matrix math. P2 is convenience.

---

## 5. Quality-of-life improvements NumPy/pandas lack (with llang examples)

NumPy/pandas optimize for compact expert notation; their errors are often
warnings, dtype coercion is implicit, and results carry no provenance. llang
can be verbose and explicit instead.

**Verbose self-documenting names + labeled args.** No `df[df.score > 80]`;
every operation reads as a sentence and argument order is irrelevant:

```
use the datascience module

set adults to call where with dataset = people, column = "score", operator = "is greater than", value = 80
set means to call group with dataset = people, key = "group", column = "score", method = "mean"
show call dimensions with dataset = adults          # {rows: 2, columns: 3}
```

**Self-describing dataset maps with metadata.** `show people` prints
`kind`, named columns, and `order`; `source` records provenance. `overview`
adds per-column kinds and missing counts — pandas needs `info()` + `describe()`
+ `.dtypes` to approximate this.

```
show call overview with dataset = people
# {kind: dataset, rows: 4, columns: 3, missing: 0, score: {kind: number, ...}}
```

**Validation with loud errors.** Unlike pandas, which silently creates NaN on a
bad `astype` or aligns mismatched indexes, every helper uses `require` with a
literal message and catchable `fail with` kinds (`bad_shape`, `unknown_column`,
`bad_type`, `bad_conversion`, `bad_join_key`). `require` messages must be string
literals (`REFERENCE` §5.2), which keeps diagnostics stable and source-located.

```
define function assert rectangular taking columns
    repeat for each name in (call keys with collection = columns)
        require (the length of (item name of columns)) equals (the length of (item (item 0 of (call keys with collection = columns)) of columns)), "all columns must have the same length"
    end repeat
end function
```

**Automatic type checks.** Postfix predicates (`is a map`, `is a list`, `is a
number`, `is text`, `is nothing` — `REFERENCE` §4.2) gate every public function;
this is stricter than NumPy's implicit upcast and pandas' object dtype. Because
user-defined functions and builtins both reject unknown labels and missing
labels at the call site (`REFERENCE` §5.3 and §6) — library functions get free
arity validation.

**Readable summaries.** `describe` returns a plain map with familiar keys
(`count`, `missing`, `min`, `max`, `mean`) rather than a floating-point Series
with a mixed index; `show` renders it recursively in insertion order.

**Composition with csv/json modules.** The data library never parses files
itself; it consumes the existing native modules, so there is one CSV state
machine and one JSON parser in the system:

```
use the csv module
use the json module
use the datascience module

set raw to call read text from with path = "people.csv"
set people to call load_csv with text = raw, header = true
set scored to call convert with dataset = people, column = "score", kind = "number"
set top to call order with dataset = scored, column = "score", descending = true
show call describe with dataset = top, columns = (a list of "score")
set records_out to call harvest with dataset = top
call write text to with path = "out.json", content = (call stringify with value = records_out)
```

`lib/json.ll` maps objects -> insertion-ordered maps, arrays -> lists, `null` ->
`nothing` and emits compact JSON matching `json.dumps(ensure_ascii=False)`;
`lib/csv.ll` emits the excel dialect with CRLF rows. Dataset -> `harvest` ->
`stringify` and `parse` -> `records` round-trip without loss of column order.

---

## 6. Verification plan (differential harnesses)

Follow the proven pattern of `tools/compare_csv.py`, `compare_json.py`,
`compare_shlex.py`, etc.: a Python script holds a curated corpus, emits it as
JSON to a temp dir, generates a `.ll` harness that loads the corpus via
`use the foreign json module` + `loads`, calls every library function, writes a
results JSON via `dumps`, then diffs against an oracle computed with numpy and
pandas. Add **`tools/compare_datascience.py`** plus two smaller harnesses if it
stays clearer: `compare_numpy_math.ll` and `compare_pandas_ops.ll`.

**Curated corpus** (small, hand-auditable, serialized as JSON):
1. Integer table (the `people` example above) with duplicate names and groups.
2. Float table with negatives, ties, and a float NaN cell (`json` `NaN` token).
3. Table with missing cells (`null`) in several columns; all-missing column.
4. Empty dataset (columns present, zero rows) and 0-column dataset.
5. Text-only table with unicode, embedded commas/quotes, and mixed case.
6. Join fixtures: duplicate right keys, unmatched left/right keys, null keys.
7. Sort fixtures: ties (stability), missing values, descending.
8. CSV/JSON round-trip fixtures including quoted newlines and CRLF.

For each case the Python side computes expected values with pinned numpy/pandas
calls (`Series.mean().tolist()`, `DataFrame.sort_values(...).to_dict("list")`,
`merge(..., how="inner").to_dict("list")`, `np.dot(...).tolist()`, etc.) and
compares structurally. Add three test families per `METHOD.md` step 7:
synonym-equivalence (new phrasing, if any, yields identical AST), semantic
edge cases (the table above in `tests/`), and pinned end-to-end output examples.

**Tolerance rules.**
- Integers, counts, shapes, column order, boolean flags, and all text: exact
  equality.
- Structurally compared maps/lists must have identical key order (llang maps and
  pandas column order are insertion-ordered); compare as ordered pairs, not
  unordered dicts.
- Floats: `math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-12)`. For
  `mean`/`dot`/`describe` use `rel_tol=1e-9`; for integer-valued float results
  from `sum` the same rule is sufficient. Normalize `-0.0` to `0.0`.
- NaN/missing: treat llang `nothing` and pandas NaN/NumPy nan as one "missing"
  class; assert `both missing` or `both non-missing and close`. Never compare NaN
  with `==` (llang `equals` on nan is false by design).
- Error cases: assert the llang `fail` kind and that a `require` message is
  present, not the exact host exception text; compare only that both sides
  reject the input.
- Float rendering: `show` uses Python `str()` on floats (`REFERENCE` §3), so
  compare `text of` output by parsing back to float with the tolerance above,
  not by raw string equality.

Target: zero mismatches, mirroring the stdlib rewrites recorded in `METHOD.md`
§42–55. Any divergence must be documented in `REFERENCE` §9 as an intentional
llang divergence rather than silently accepted.

---

## 7. Explicit omissions (v1 and likely always)

1. **DataFrames with labels/index objects.** No `Index`, `MultiIndex`,
   `.loc`/`.iloc`/`.at`, label alignment on arithmetic, `set_index`/`reset_index`,
   duplicate-label machinery, or reindexing. Rows are addressed by 0-based
   integer position only; columns by name from `order`. This follows llang's
   existing rejection of negative indices and slicing (`REFERENCE` §9).
2. **Vectorization and performance.** llang is a tree-walking interpreter with
   lists/maps, no `ndarray`, no ufuncs, no C/SIMD loops, no views, and a
   100 000-iteration loop guard (`REFERENCE` §5.2). Elementwise ops are ordinary
   looping functions; large data will be slow by design. No `.str` vectorized
   accessors, no sparse/categorical/Arrow dtypes, no memory_usage optimization.
3. **Datetime dtype.** llang has no date/time type; timestamps remain text and
   are never parsed, resampled, timezone-localized, or sorted chronologically.
   All `pandas` time-series, offset, and `Timedelta` APIs are out of scope.
4. **Groupby complexities beyond simple keys.** One key column and one value
   column with sum/mean/min/max/count only. No multi-key grouping, named
   aggregations of several columns, `transform`, `apply`, `filter` on groups,
   pivot tables, `crosstab`, rolling/expanding/ewm windows, or `dropna=False`
   NA-key grouping.
5. **Plotting and visualization.** No graphics, no `.plot`, no matplotlib
   bridge, no HTML/LaTeX/Styler output. Summaries are text maps only.
6. Additional deferred items: standard deviation/variance/quantiles in
   `describe`; left/right/outer/cross joins (only inner/left); column insertion
   in the middle; pivoting/melting; `pd.NA` nullable dtype semantics; NaN payload
   and signed-zero subtleties; expression engines (`df.eval`, `df.query`);
   Copy-on-Write/chained-assignment rules (llang side-effects are explicit).
