# First-class math library — design research

*Status: design proposal grounded in `docs/METHOD.md`, `docs/GRAMMAR.md`, `docs/REFERENCE.md`, `lib/math.ll`, `tests/test_core.py`, `src/llang/synonyms.py`, and local experiments. Fetched 2026-11-22: the official docs render as Python **3.15.2**; the local oracle at verification time was **CPython 3.11.8** (`MSC v.1937 64 bit (AMD64)`). Version-sensitive rows are flagged below.*

---

## 1. Why Python `math`/`statistics` are the authority

**The oracle principle.** `docs/METHOD.md` §"oracle principle" records the empirical rule for this codebase: surfaces with an authoritative spec **plus a running stdlib implementation** (`shlex`, `fnmatch`, `textwrap`, `csv`, `json`) reached 0 mismatches quickly; surfaces without one required guesswork. `math` and `statistics` are pure stdlib: official reference **and** an executable CPython oracle are both available. We copy behavior mechanically; we do not invent numerical semantics.

- `math` authority: <https://docs.python.org/3/library/math.html> — "This module provides access to common mathematical functions and constants, including those defined by the C standard"; "Except when explicitly noted otherwise, all return values are floats."
- `statistics` authority: <https://docs.python.org/3/library/statistics.html> — "This module provides functions for calculating mathematical statistics of numeric (`Real`-valued) data"; aimed "at the level of graphing and scientific calculators," explicitly *not* a NumPy/SciPy competitor.
- Error/overflow policy authority: the "CPython implementation detail" paragraph of the `math` page: invalid operations raise `ValueError`, overflow raises `OverflowError`, and NaNs are not returned from inputs that were not NaN (with documented exceptions). The `statistics` page defines the single `StatisticsError` as a `ValueError` subclass.

**License.** Both fetched pages end with: "This page is licensed under the Python Software Foundation License Version 2. Examples, recipes, and other code in the documentation are additionally licensed under the Zero Clause BSD License" (see <https://docs.python.org/license.html>). Consequence: the *semantic matrix* (function lists, edge-case tables, documented formulas) may be reproduced with attribution; **we copy no CPython source code**. `lib/math.ll` and the proposed harnesses are original llang/Python written for this project. Keep a `Grounded in: <URL>` header in the module and in generated reference pages, as `docs/research/stdlib-design.md` already prescribes.

**Copy semantics / invent phrasing.** The split is strict:

| Copy from Python (do not re-decide) | Invent in llang (the only free variable) |
|---|---|
| Domains, return types, exact-vs-float distinction, Bessel `N-1` vs population `N`, quantile interpolation (`i/(m+1)` vs `(i-1)/(m-1)`), `mode` first-encountered tie, `gcd() == 0`, `lcm() == 1`, `comb(k>n) == 0`, `factorial` strict integral input, `dist` equal-dimension rule, `hypot` n-d rule, `isclose` formula, ties-to-even rounding, C99/IEEE-754 exceptional cases | One-word function ids, labeled parameter names, verbose aliases, descriptive result maps with metadata, problem-kind tags and message wording, unit/clamp/validation helpers, documentation examples |

Every alias must desugar to the **identical** canonical call/AST node (`docs/METHOD.md` step 4; `synonyms.py` header; `REFERENCE` §1). That is a test, not a promise.

---

## 2. Cross-cutting invariants

### 2.1 Numeric types

- llang `number` = Python `int` or `float`, **excluding `bool`** (`interpreter.py:482-483`). `true is a number` is false. Every math parameter labeled `value`/`values` must enforce this with `_is_number`-equivalent validation; booleans are rejected loudly.
- Integers are the arbitrary-precision Python `int`. Verified: `show 2 to the power of 100` → `1267650600228229401496703205376`. No overflow for integer-only paths (`gcd`, `lcm`, `factorial`, `comb`, `perm`, `isqrt`).
- Floats are IEEE-754 binary64 (Python `float`). `divided by` is **always** float division (`7 divided by 2 → 3.5`); `floor divided by` rounds toward −∞ (verified `0 minus 7 floor divided by 2 → -4`). There is no truncation-toward-zero operator — supply `trunc` in the library.
- `Decimal`, `Fraction`, tuples, sets, bytes are not llang value types (`REFERENCE` §3). Statistics docs support them, but llang cannot represent or return them, so they are out of scope (§6).
- **Sharp edge, must fix or guard:** `POW` can leak a Python `complex` into a language that claims none. Verified: `(0 minus 8) to the power of (1 divided by 3)` → `(1.0000000000000002+1.7320508075688772j)`. That value fails `is a number` and all arithmetic operators. The math library must reject complex inputs with a loud `math_type` problem; the interpreter should also reject complex results from `POW` rather than rendering them.
- **Sharp edge, must wrap:** float overflow in `POW` escapes as a raw Python `OverflowError`. Verified: `2.0 to the power of 2000` → uncaught `OverflowError: (34, 'Result too large')`. Math-library calls must never leak a raw Python exception; wrap as a source-located problem (§2.3).

### 2.2 Exact vs approximate results

| Category | Functions | Result rule |
|---|---|---|
| Exact | `gcd`, `lcm`, `factorial`, `combinations`, `permutations`, `integersqrt`, `floor`, `ceil`, `trunc`, `sum` over ints | Python `int`; require byte-equal results from the oracle |
| Correctly rounded primitive | `squareroot`, `exponential`, `logarithm`, `logbase`, `sine`/`cosine`/`tangent` and inverses, `degrees`/`radians`, `hypot`, `distance` | `float`, even for integral input (`math.sqrt(81) → 9.0`; native `lib/math.ll` `sqrt` also returns `9.0`). Platform libm may differ by ≤ a few ulp |
| Compound / accumulated | `mean`, `variance`, `stdev`, `pvariance`, `pstdev`, `quantiles`, `correlation`, `covariance`, `fsum`, `linearregression` | `float` (except `statistics.mean` on ints returns an `int` when the exact rational divides evenly, e.g. `mean([1,2,3]) → 2`; `median` on odd-length input returns an actual datum, on even-length input an interpolated `float`: `median([1,3,5,7]) → 4.0`; `mode` returns an actual datum) |

`math.fsum([0.1]*10) → 1.0` while `sum([0.1]*10) → 0.9999999999999999`. Do **not** replace `fsum` with the existing `sum` builtin in a differential test; they must be separate rows with different tolerances. The existing `lib/math.ll` `average` uses `sum/len` and is therefore a `sum`-accuracy function, not an `fmean` equivalent — document that or migrate it.

### 2.3 Domain errors and how Python reports them

Observed oracle behavior (CPython 3.11.8; 3.15 docs agree on the classes):

| Python exception | Triggers | llang mapping |
|---|---|---|
| `ValueError` / `math domain error` | `sqrt(-1)`, `log(0)`, `factorial(-1)`, `perm(4,-1)` | catchable problem `math_domain`, message names the function and the offending value |
| `OverflowError` / `math range error` | `exp(1000)`, `2.0 ** 2000` | catchable problem `math_overflow` |
| `TypeError` | `factorial(5.0)` (integral floats rejected since 3.10) | catchable problem `math_type` |
| `ZeroDivisionError` | `1/0` at the operator level | existing `Division by zero` error at the operator's source position |
| `StatisticsError` (ValueError subclass) | `mean([])`, `median([])`, `variance([1])`, `pvariance([])`, `correlation([1,2],[1,1])`, `geometric_mean([1,-2])`, `quantiles([1], n=4)` on 3.11 | `math_empty`, `math_length`, `math_domain`, `math_constant` as appropriate |

llang mechanics: builtins wrap `TypeError`/`ValueError` as `In call to 'NAME': <reason>` at the call position (`REFERENCE` §6); `OSError` is *not* wrapped. Module functions use user-function label validation — unknown/missing/duplicate labels are loud (`REFERENCE` §5.3), unlike builtins which silently ignore extra labels. **Therefore ship the math library as a module (user functions), not as global builtins**, so misspelled labels fail loudly. Every native call must be wrapped: `ValueError → math_domain`/`math_empty`/`math_length`/`math_constant`, `OverflowError → math_overflow`, `TypeError → math_type`; never leak a traceback. Problem tags are string tags with optional message (`REFERENCE` §5.5); include the call site's line/column in the rendered error (llang already does) and the Python exception class in the message for auditability.

### 2.4 Rounding

- `rounded` / `rounded to places` already maps to `round(value, places)` with default `places = 0` (`interpreter.py:153-158`). Ties-to-even: `round(2.5, 0) → 2.0`. Negative `places` rounds tens/hundreds. `places` must be a non-boolean whole number.
- Because llang always supplies `ndigits`, the Python `round(x)` (no ndigits) path is not used: verified `call rounded with value = nan` → `nan`, `... inf` → `inf` (CPython `round(nan,0) → nan`, `round(inf,0) → inf`, whereas `round(nan)` raises `ValueError` and `round(inf)` raises `OverflowError`). Document this explicitly; it is a divergence from bare Python `round()`.
- `floor`, `ceil`, `trunc` return `int` for float input. Large floats (`abs(x) >= 2**52`) are already exact integers (`math` page, floor/trunc section). `trunc` rounds toward zero: `trunc(-2.7) → -2`, `floor(-2.7) → -3`.
- Float-representation surprises (`round(2.675, 2) → 2.67`) are Python's, not bugs; the reference must say so.

### 2.5 NaN / infinity policy — what llang can actually represent

Empirical results from small llang programs (`run_source`):

| Probe | Result |
|---|---|
| `show 3.14` | `3.14` (float literal works) |
| `show 1e3` | lexer/parser error `Expected end of line, found 'e3'` — **no exponent literals** (`REFERENCE` §2: `DIGIT+ ('.' DIGIT+)?`) |
| `call to number with text = "inf"` / `"nan"` | `inf` / `nan` floats — **reachable via conversion** |
| `inf plus 1`, `0 minus inf`, `inf minus inf`, `nan plus 1` | `inf`, `-inf`, `nan`, `nan` — propagate by Python rules |
| `nan equals nan` | `false` (Python `!=` semantics for NaN) |
| `call is number with value = 5.0` | `true`; the same predicate on `nan`/`inf` is also true |
| `1 divided by 0`, `0 divided by 0` | `Division by zero` error (no IEEE inf from division) |
| `2.0 to the power of 2000` | uncaught `OverflowError` (see §2.1) |

Policy: NaN and infinities are **representable but quarantined**. The library provides `isnan`, `isinf`, `isfinite` classification functions (they accept the values), but every statistic or numeric function that receives NaN/inf fails loudly with `math_domain` *before* computation. Rationale: the `statistics` page devotes a paragraph to "surprising or undefined behaviors" from NaN in `median`, `mode`, `quantiles`, etc. (e.g. `median([20.7, nan, 19.2, 18.3, nan, 14.4]) → 16.35`); reproducing that is hostile to an LLM author. Signed zero is reachable by arithmetic but not by literal; bit-level inspection (`copysign`, `signbit`) is version-gated/P2. `math.nan`/`math.inf` constants are not exposed as bare names; use the conversion idiom or the named helpers.

Also note `lib/math.ll` currently exports `pi = 3.14159265358979` and `e = 2.71828182845905` (14–15 significant digits, truncated). Replace with full binary64-precision values (17 significant digits: `3.141592653589793`, `2.718281828459045`) or host-backed constants; keep the old names as aliases.

### 2.6 Determinism

- No randomness, clocks, or I/O in the math library; all functions are pure maps from values to values. `statistics.kde_random`, `NormalDist.samples`, and `random.*` are therefore excluded (§6).
- Result maps must declare a **fixed key order** (llang maps are insertion-ordered, `REFERENCE` §3) and a fixed schema: `value`, `kind`, `exact`, `count`, plus `method`/`unit` where applicable. Rendered output is then byte-stable.
- Floating summation order is fixed and documented (left-to-right for `sum`; compensated for `fsum`). No dependence on hash iteration order: `repeat for each` over a map yields insertion-ordered keys, but statistics take lists only.
- Transcendental results depend on the platform C math library (see the `math` page's CPython implementation detail); the differential harness pins `sys.version` and uses ulp-based tolerances (§5). `fsum` may be 1 ulp different on some builds — another reason for the tolerance tiers.
- Diagnostics are deterministic strings at deterministic 1-based source positions (`REFERENCE` §7). Two runs of the same corpus must produce byte-identical JSON and stderr.

---

## 3. Prioritized API table

All ids are **single-word identifiers** valid as `WORD` (no reserved words, no `with`). Canonical call form: `call <id> from math with <label> = <expr>, ...`. Optional verbose surface aliases (e.g. `standard deviation of`) live in the same spec and produce the identical canonical call; they are a phrasing layer only. `values`/`coordinates`/`x`/`y` denote lists of numbers; `number` = int/float, not bool. "Domain errors" below use the §2.3 problem tags. Priorities: **P0** = first release, **P1** = next, **P2** = later/version-gated.

### 3.1 Trigonometry and angles

| Function | Labeled parameters | Semantics | Python equivalent | Edge cases | Priority |
|---|---|---|---|---|---|
| `sine` | `angle: number` | Sine, radians in → float | `math.sin(angle)` | Huge angles lose precision; NaN/inf → `math_domain` | P1 |
| `cosine` | `angle: number` | Cosine, radians in → float | `math.cos(angle)` | As above | P1 |
| `tangent` | `angle: number` | Tangent, radians in → float | `math.tan(angle)` | Poles near π/2; no domain error from Python | P2 |
| `arcsine` | `value: number` | Inverse sine in radians, `[−π/2, π/2]` | `math.asin(value)` | `value < -1` or `> 1` → `math_domain` | P1 |
| `arccosine` | `value: number` | Inverse cosine in radians, `[0, π]` | `math.acos(value)` | Same domain | P1 |
| `arctangent` | `value: number` | Inverse tangent in radians, `[−π/2, π/2]` | `math.atan(value)` | All finite reals; inf accepted by Python but quarantined here | P2 |
| `atan2` | `y: number`, `x: number` | Quadrant-correct angle in `(−π, π]` | `math.atan2(y, x)` | `atan2(0,0) → 0.0`; signs of both args matter | P2 |
| `radians` | `degrees: number` | Degrees → radians, exact scale by π/180 | `math.radians(degrees)` | No validation of angle range | P1 |
| `degrees` | `angle: number` | Radians → degrees | `math.degrees(angle)` | No validation of angle range | P1 |
| `hyperbolicsine`, `hyperboliccosine`, `hyperbolictangent` | `value: number` | Hyperbolic trig | `math.sinh/cosh/tanh` | `cosh` overflows for large input → `math_overflow` | P2 |
| `inversesinh`, `inverseacosh`, `inverseatanh` | `value: number` | Inverse hyperbolic | `math.asinh/acosh/atanh` | `acosh(x<1)`, `atanh(|x|>1)` → `math_domain` | P2 |

### 3.2 Exponentials and logarithms

| Function | Labeled parameters | Semantics | Python equivalent | Edge cases | Priority |
|---|---|---|---|---|---|
| `squareroot` | `value: number` | Principal square root, float | `math.sqrt(value)` | `value < 0` → `math_domain`; keep `sqrt` alias for `lib/math.ll` compatibility | **P0** |
| `exponential` | `power: number` | `e ** power`, float | `math.exp(power)` | `exp(1000)` → `math_overflow` | P1 |
| `logarithm` | `value: number` | Natural log, float | `math.log(value)` | `value <= 0` → `math_domain` | **P0** |
| `logbase` | `value: number`, `base: number` | Log to given base | `math.log(value, base)` | `base <= 0` or `base == 1` → `math_domain`; computed as `log(x)/log(base)` | P1 |
| `logtwo` | `value: number` | Base-2 log (more accurate than `logbase`) | `math.log2(value)` | `value <= 0` → `math_domain` | P1 |
| `logten` | `value: number` | Base-10 log | `math.log10(value)` | Same | P1 |
| `logonep` | `value: number` | `log(1+value)`, accurate near zero | `math.log1p(value)` | `value <= -1` → `math_domain` | P2 |
| `expmonep` | `power: number` | `exp(power)-1`, accurate near zero | `math.expm1(power)` | Overflow → `math_overflow` | P2 |
| `cuberoot` | `value: number` | Cube root; accepts negatives, float | `math.cbrt(value)` (3.11+) | Exact negatives: `cuberoot(-8) → -2.0`, unlike `(-8) ** (1/3)` (verified complex leak) | P2 |
| `realpower` | `base: number`, `exponent: number` | Float power, rejects complex results | `math.pow(base, exponent)` | `pow(1, nan) → 1.0` in Python; we quarantine NaN; negative fractional exponent → `math_domain`, not a complex | P2 |
| `exp2` | `power: number` | `2 ** power` | `math.exp2(power)` (3.11+) | Overflow → `math_overflow` | P2 |

Constants (values, not calls): `pi`, `e`, `tau` with full binary64 precision. `tau = 2*pi` (3.6+). `inf`/`nan` are deliberately **not** exported (§2.5).

### 3.3 Number theory (exact integers)

| Function | Labeled parameters | Semantics | Python equivalent | Edge cases | Priority |
|---|---|---|---|---|---|
| `gcd` | `values: list of whole numbers` | Greatest common divisor, non-negative | `math.gcd(*values)` | `gcd([]) → 0`; negatives → non-negative; floats (even `5.0`) → `math_type` | **P0** |
| `lcm` | `values: list of whole numbers` | Least common multiple, non-negative | `math.lcm(*values)` | `lcm([]) → 1`; any zero → 0; `lcm([-4,6]) → 12` | P1 |
| `factorial` | `number: whole number` | `n!`, exact int | `math.factorial(number)` | `factorial(0) → 1`; negative → `math_domain`; `factorial(5.0)` → `math_type` (3.10+ strictness) | P1 |
| `combinations` | `n: whole number`, `k: whole number` | Unordered selections | `math.comb(n, k)` | `k > n → 0`; negative → `math_domain`; exact int | P2 |
| `permutations` | `n: whole number`, `k: whole number` | Ordered selections | `math.perm(n, k)` | `k > n → 0`; negative `k` → `math_domain` | P2 |
| `integersqrt` | `value: whole number` | `floor(sqrt(value))`, exact int | `math.isqrt(value)` | negative → `math_domain` | P2 |

Note: `math` 3.15 soft-deprecates these in favor of `math.integer` aliases; keep the stable `math.*` names for the oracle until the minimum supported CPython is ≥3.15.

### 3.4 Rounding and distance

| Function | Labeled parameters | Semantics | Python equivalent | Edge cases | Priority |
|---|---|---|---|---|---|
| `floor` | `value: number` | Largest int ≤ value | `math.floor(value)` | Already-integral float → same int; always `int` | **P0** |
| `ceil` | `value: number` | Smallest int ≥ value | `math.ceil(value)` | As above | **P0** |
| `trunc` | `value: number` | Toward zero | `math.trunc(value)` | `trunc(-2.7) → -2`; not otherwise available in llang | **P0** |
| `rounded` (existing builtin) | `value: number`, `places: whole number = 0` | Ties-to-even, `round(value, places)` | `round(value, places)` | `nan`/`inf` pass through (§2.4); negative places; float artifacts | **P0** |
| `hypot` | `coordinates: list of numbers` | Euclidean norm, n-d | `math.hypot(*coordinates)` | `hypot([]) → 0.0`; handles overflow/underflow better than manual `sqrt(sum(x*x))` | P1 |
| `distance` | `frompoint: list of numbers`, `topoint: list of numbers` | Euclidean distance | `math.dist(p, q)` | Unequal dimensions → `math_length` (Python `ValueError`); `0-d` → `0.0` | P1 |
| `approxequal` | `left: number`, `right: number`, `reltol: number = 1e-9`, `abstol: number = 0` | `abs(a-b) <= max(rel_tol*max(|a|,|b|), abs_tol)` | `math.isclose(a, b, rel_tol=..., abs_tol=...)` | NaN never close; inf close only to itself; `reltol` must be `< 1`, both tolerances non-negative | P1 |
| `precisesum` | `values: list of numbers` | Compensated floating-point sum (not plain `sum`) | `math.fsum(values)` | `fsum([0.1]*10) → 1.0` vs `sum → 0.9999999999999999`; empty → `0`; may differ 1 ulp across builds | P1 |

### 3.5 Descriptive statistics (all list-taking; reject NaN/inf before computing)

| Function | Labeled parameters | Semantics | Python equivalent | Edge cases | Priority |
|---|---|---|---|---|---|
| `mean` | `values: list of numbers` | Arithmetic mean | `statistics.mean(values)` | Empty → `math_empty`; exact int result stays int, else float | **P0** |
| `median` | `values: list of numbers` | Middle value; mean of middle two | `statistics.median(values)` | Empty → `math_empty`; even length → interpolated float; odd length → datum | **P0** |
| `mode` | `values: list` | Most common datum; ties → first encountered | `statistics.mode(values)` | Empty → `math_empty`; supports text (the only statistic that does) | P1 |
| `variance` | `values: list of numbers` | Sample variance, Bessel `N-1` | `statistics.variance(values)` | Fewer than 2 → `math_length`; float result | **P0** |
| `stdev` | `values: list of numbers` | `sqrt(sample variance)` | `statistics.stdev(values)` | Fewer than 2 → `math_length` | **P0** |
| `pvariance` | `values: list of numbers` | Population variance, `N` | `statistics.pvariance(values)` | Empty → `math_empty`; `mu`/`xbar` optional args deferred (no defaults in llang functions) | P1 |
| `pstdev` | `values: list of numbers` | `sqrt(population variance)` | `statistics.pstdev(values)` | Empty → `math_empty` | P1 |
| `modes` | `values: list` | All most-common values, first-seen order | `statistics.multimode(values)` | Empty → `[]` (Python behavior) | P2 |
| `lowmedian`, `highmedian` | `values: list of numbers` | Median that is an actual datum | `statistics.median_low/high` | Empty → `math_empty` | P2 |
| `quantiles` | `values: list of numbers`, `count: whole number = 4`, `method: text = "exclusive"` | `count-1` cut points; exclusive `i/(m+1)`, inclusive `(i-1)/(m-1)` | `statistics.quantiles(values, n=count, method=method)` | `count < 1` → `math_domain`; empty → `math_empty`; 3.13+ allows a single point (3.11 raises — pin or implement locally) | P2 |
| `covariance` | `x: list`, `y: list` | Sample covariance | `statistics.covariance(x, y)` | Unequal lengths or `< 2` → `math_length` | P2 |
| `correlation` | `x: list`, `y: list`, `method: text = "linear"` | Pearson `r ∈ [-1,1]`; `method = "ranked"` → Spearman | `statistics.correlation(x, y, method=...)` | Constant input → `math_constant`; `ranked` needs 3.12+, verify version before shipping | P2 |
| `geometricmean` | `values: list of numbers` | Product-based mean | `statistics.geometric_mean(values)` | Empty/zero/negative → `math_domain`; always float | P2 |
| `harmonicmean` | `values: list of numbers` | Reciprocal of mean of reciprocals | `statistics.harmonic_mean(values)` | Empty/negative → `math_domain`; zero datum → `0` | P2 |
| `linearregression` | `x: list`, `y: list`, `proportional: boolean = false` | Least-squares slope/intercept as map | `statistics.linear_regression(x, y, proportional=...)` | Constant `x` → `math_constant`; returns named-tuple in Python → map in llang | P2 |

llang functions have **no default parameters** (`REFERENCE` §5.3), so the `= value` defaults in the table are documentation of intent: either provide phrase variants (`logbase` vs `logarithm`, `pvariance` vs `variance`, `quantiles` plus `quartiles`) or pass all labels explicitly. Do not silently add a defaults feature to the grammar for this library.

---

## 4. Quality-of-life improvements (llang's advantages)

Plain `math`/`statistics` return bare scalars, use terse names, accept positional args, and report `ValueError: math domain error` with no data context. The math library should exploit llang's strengths instead:

**4.1 Verbose self-documenting names + aliases.** Keep one single-word canonical id per row; register long synonyms in the same spec (one-line alias declaration, identical canonical node — `REFERENCE` §5.3, `tests/test_core.py::SynonymTests`):

```
use the math module

set scores to a list of 72, 88, 91, 65
set spread to call stdev from math with values = scores
set also_spread to call standarddeviation from math with values = scores
show spread
```

Both names hit the same function; the formatter collapses them to one spelling for stable diffs (`docs/METHOD.md` step 9).

**4.2 Labeled arguments — impossible to transpose.** Python's `math.atan2(1, 2)` is easy to misread; `distance((0,0),(3,4))` hides which point is which:

```
set d to call distance from math with frompoint = (a list of 0, 0), topoint = (a list of 3, 4)
set a to call atan2 from math with y = 3, x = 4
```

Parentheses around the list literal are required because argument expressions are greedy (`REFERENCE` §4.4). Module functions reject unknown labels (unlike builtins), so `with from_point = ...` fails loudly instead of being ignored.

**4.3 Descriptive maps with metadata.** A `report` family returns a map, not a bare number. Fixed key order makes output byte-stable:

```
define function summarize taking values
    require values is not empty, "summarize needs at least one number"
    set avg to call mean from math with values = values
    set mid to call median from math with values = values
    give back a map with "value" mapped to avg,
                       "median" mapped to mid,
                       "kind" mapped to "summary",
                       "exact" mapped to false,
                       "count" mapped to (the length of values)
end function

show call summarize with values = scores
```

```
{value: 79.0, median: 80.0, kind: summary, exact: false, count: 4}
```

(Keys render in insertion order — `REFERENCE` §3.)

For a single statistic, `describe` returns `"value"`, `"kind"`, `"exact"` (true for gcd/factorial, false for float results), `"inputs"` and `"method"` where relevant (e.g. `"exclusive"` for quantiles). This is invented *presentation*, not invented semantics: the `value` field equals the Python oracle exactly/tolerantly per §5.

**4.4 Loud, source-located errors with actionable kinds.** Validation is explicit at the library boundary, and failures are catchable with stable tags:

```
expect
    show call squareroot from math with value = 0 minus 4
if a problem of kind math_domain occurs then
    show "square root needs a non-negative number"
end expect
```

The underlying native call raises `fail with math_domain, "squareroot: value must be non-negative, got -4 (math sqrt domain)"` at the call site. Tags: `math_type`, `math_domain`, `math_empty`, `math_length`, `math_constant`, `math_overflow`. Include the Python exception class in the message so an LLM can map back to the docs. Never return `nothing`, `nan`, or a sentinel on error.

**4.5 Validation helpers and unit/clamp helpers.**

```
require (the length of scores) is greater than 1, "stdev needs at least two scores"
repeat for each score in scores
    require score is a number, "scores must contain only numbers"
end repeat

set bounded to call clamp from math with value = raw, low = 0, high = 1
set inrange to call within from math with value = raw, low = 0, high = 1
set theta to call radians from math with degrees = 90
set back to call degrees from math with angle = theta
```

`clamp` already exists in `lib/math.ll` (keeps its semantics: `low > high` → loud error); `within` is a new inclusive-inclusive predicate returning a boolean (a safe replacement for the absent chained comparison — `REFERENCE` §9.2). `radians`/`degrees` are the unit helpers; angles are **always radians** in trig functions, stated in every signature. Keep `fresh` input validation at the module edge rather than relying on Python's partial checks (e.g. `statistics.harmonic_mean` early-outs on zero and skips later validation — documented as "may change in the future" on the statistics page).

**4.6 Composability.** Every function works as a nested expression and returns a plain llang value that can be fed straight into another call, the builtins, or a result map:

```
set norm to call hypot from math with coordinates = (a list of 3, 4, 12)
set rounded_norm to call rounded with value = norm, places = 2
show call distance from math with frompoint = (a list of 0, 0, 0), topoint = (a list of 3, 4, 12)
show text of norm
```

Statistics compose with the existing `sum`/`minimum`/`maximum` builtins and with `repeat for each`; no new syntax is needed. `lib/math.ll`'s existing `sqrt`, `clamp`, and `average` stay as compatibility aliases so old programs keep running.

---

## 5. Verification plan

**Harness.** Add `tools/compare_math.py` mirroring `tools/compare_shlex.py`: write a curated corpus to a temp `cases.json`; emit a generated `harness.ll` that does `use the math module`, loops over cases, catches each problem with `expect`, and writes `results.json` via `use the foreign json module` + `call write text to`; run it with `python run.py harness.ll`; compute expected values with `math`/`statistics` and diff. Print `compared N cases, M mismatches`, exit 1 on any mismatch, end with `lib/math.ll matches CPython math/statistics`. Mirror it as `tests/test_math.py` with the three test kinds from `docs/METHOD.md` step 7: alias-equivalence (same native spec/AST), semantic edge cases (every row of §2 and §3), end-to-end pinned output.

**Corpus curation.** For each function include: canonical example, `0`, `1`, negative, boundary (`asin(±1)`, `log(1)`, `acos(1)`), just-outside-domain (`asin(1.1)`, `log(0)`), empty/singleton/two-element lists, ties (`mode([1,1,2,2]) → 1`), `k > n` (`comb(4,5)`, `perm(4,5) → 0`), `gcd([]) → 0`, `lcm([]) → 1`, `hypot([]) → 0.0`, uneven `dist` dimensions, cancellation (`fsum([1e16, 1, -1e16, 1])`), huge ints beyond float range (`factorial(200)`), NaN/inf via text conversion, and a complex-producing `POW` case to prove it is rejected. Record `sys.version` and platform in the report; skip 3.13/3.15-only oracles (`kde`, `correlation(method=)`, `fmax`, `signbit`, 3.13 single-point `quantiles`) unless that CPython is present — this matters because the fetched docs are 3.15.2 but the local oracle is 3.11.8.

**Exact-vs-approximate tolerance rules** (applied by name, not guessed per case):

| Tier | Applies to | Rule |
|---|---|---|
| **E — exact** | `gcd`, `lcm`, `factorial`, `combinations`, `permutations`, `integersqrt`, `floor`, `ceil`, `trunc`, `rounded` on integral results, integral `mean`/`median`, all problem-kind strings | `type(actual) is type(expected)` **and** `actual == expected`; int vs float mismatch is a failure (`sqrt(81) → 9.0` must be float) |
| **C — correctly rounded primitive** | `squareroot`, `exponential`, `logarithm`, `logbase`, `logtwo`, `logten`, `logonep`, `expmonep`, `exp2`, `cuberoot`, trig/inverse trig, `degrees`, `radians`, `hypot`, `distance`, `fsum`, `approxequal` | `math.isclose(actual, expected, rel_tol=1e-14, abs_tol=1e-300)` **or** `abs(actual-expected) <= 4 * math.ulp(expected)`, whichever passes; platform libm may differ by ≤ a few ulp; special-case exact `0.0` and signed zero |
| **S — statistics/compound** | `mean` (float case), `variance`, `stdev`, `pvariance`, `pstdev`, `quantiles`, `covariance`, `correlation`, `geometricmean`, `harmonicmean`, `linearregression` | `math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12)`; compare list lengths elementwise for `quantiles` |
| **X — exceptional/non-finite** | all domain, overflow, empty, length, constant, NaN/inf cases | Compare problem kind exactly and message substring; compare NaN with `math.isnan` and infinities by sign, never with `==`; assert the error is a catchable llang problem and that **no raw Python exception** (`OverflowError`, `TypeError`, `ValueError`) escapes |

Additional gates:

1. **Result-schema check:** every map-returning call has exactly the documented keys in the documented order; `exact` matches the tier (E → true, C/S → false).
2. **Run-to-run determinism:** execute the harness twice; `results.json` must be byte-identical.
3. **Alias equivalence:** for each alias, assert the canonical id appears in a single registry and the produced AST/native spec is identical (`tests/test_core.py::SynonymTests` pattern).
4. **Version matrix:** CI on CPython 3.11+; mark version-gated rows P2 and skip their oracle calls when unavailable; never treat a missing 3.15 function as an implementation bug.
5. **Leak regression:** explicitly assert the two observed leaks are gone — negative-base fractional `POW` never yields a complex, and float `POW` overflow becomes `math_overflow`, not a raw `OverflowError`.

---

## 6. Explicit omissions and why

1. **Complex numbers.** The `math` page opens by excluding them and redirecting to `cmath` ("These functions cannot be used with complex numbers... Receiving an exception instead of a complex result allows earlier detection"). llang's value model has no complex type (`REFERENCE` §3; `_is_number` excludes it). The observed complex from `POW` is a leak to **reject**, not a feature to embrace. Consequence: `sqrt(negative)`, `log(nonpositive)`, `realpower` with negative fractional exponent → `math_domain`; no `cmath` surface.
2. **Arbitrary precision beyond Python `int` (no `Decimal`/`Fraction`).** Python `int` is already arbitrary precision and covers all exact integer functions here. `statistics` supports `Decimal`/`Fraction`, but llang has neither type, and mixing numeric types is "undefined and implementation-dependent" per the statistics page. Adding them would change the closed value model and grammar (`REFERENCE` §1, §9) — out of scope. Use `math.fsum` (tier C) when float cancellation matters; it is the documented CPython remedy.
3. **Special functions requiring SciPy.** CPython's `math` exposes only `erf`, `erfc`, `gamma`, `lgamma` (its "Special functions" section), and we defer even those to P2 because there is no stdlib oracle for alternative implementations and they need different accuracy reasoning. Beta functions, Bessel functions, integration/optimization, distributions beyond `NormalDist`, and anything matrix/array-based need SciPy/NumPy; they are omitted because there is no array value type, no complex type, no executable stdlib oracle, and the surface would dwarf the language. Cite <https://docs.python.org/3/library/math.html> (special functions) and <https://docs.python.org/3/library/statistics.html> ("not intended to be a competitor to ... NumPy, SciPy ...").
4. **Stochastic/stateful statistics.** `statistics.kde_random`, `NormalDist.samples`, and all `random.*` are non-deterministic and violate §2.6; `kde`/`NormalDist` also require returning higher-order callable objects, which llang has (functions are values) but cannot verify with a simple scalar diff, and they are 3.13+ (absent from the local 3.11.8 oracle — verified `AttributeError`). Omit the whole family.
5. **Bit-level float manipulation.** `frexp`, `ldexp`, `nextafter`, `ulp`, `signbit`, `copysign`, `modf`, `fma`, `fmod`, `remainder`, `isfinite`, `isnormal`, `issubnormal`, `fmax`, `fmin` are either 3.9/3.13/3.15-only, expose host IEEE representation, or are covered by existing operators (`modulo`, `absolute`, `minimum`, `maximum`). Keep `isnan`/`isinf`/`isfinite` classification (needed for §2.5) in P2; omit the rest for v1.
6. **Convenience functions that duplicate llang builtins.** `prod`, `sum`, `min`/`max`, `abs`, `round` are already builtins or operators (`README`/`REFERENCE` §6); adding aliases would create two sources of truth. `fsum` is the one exception (different accuracy contract, §2.2).
7. **Mixed-type statistics and unweighted/weighted variants.** Python supports `weights` for `fmean`/`harmonic_mean` and `mu`/`xbar` precomputed means; llang functions have no defaults or `*args`, so these variants are deferred rather than added as special grammar (§3 note). Mixed int/text data remains a loud `math_type` error, matching Python's "mixed types are undefined" warning.
