# ML library design for llang — grounded in scikit-learn

Status: design (research). Scope: a first-class, native `lib/ml.ll` written entirely in llang, plus
`tools/compare_ml*.py` differential harnesses. No host-language bridge.

Grounding sources read locally: `docs/METHOD.md`, `docs/GRAMMAR.md`, `docs/REFERENCE.md`,
`lib/math.ll`, `lib/lists.ll`, `tests/test_core.py`, `src/llang/synonyms.py`.
`docs/research/datascience-library-design.md` did not exist at authoring time and was skipped.
All scikit-learn numbers quoted below were re-verified against the installed oracle
(**scikit-learn 1.8.0**, Python 3.11) with small local scripts; where docs and oracle disagree,
the oracle wins (per `docs/METHOD.md` §"the code wins").

---

## 1. Why scikit-learn is the authority; license; copy vs invent

**Why this reference.** scikit-learn is the de-facto API standard for classical ML: its User Guide
(https://scikit-learn.org/stable/user_guide.html) states each estimator's objective, state
attributes, and edge cases in one auditable place, and — critically for the METHOD.md oracle
principle — there is an *executable* implementation installed locally. That gives us all three
oracle benefits at once: settled semantics, a mechanical differential test, and a completeness
checklist. The estimator API design itself is documented in the project's API-design paper, cited
at https://scikit-learn.org/stable/about.html#citing-scikit-learn.

**License.** scikit-learn is **BSD-3-Clause** ("BSD License" in the official docs footer,
https://scikit-learn.org/stable/user_guide.html and https://scikit-learn.org/stable/about.html;
canonical text at https://github.com/scikit-learn/scikit-learn/blob/main/LICENSE). This is
permissive enough that we may reproduce formulas, default conventions, and documented behavior
verbatim. **We do not copy scikit-learn source code**, binary artifacts, or its object model; we
re-express its *semantics* in llang. Attribution belongs in `lib/ml.ll`'s header comment and in
this document's citations, not in code copied from the project.

**What we copy (semantics).** Objective functions and update rules; numeric definitions of every
metric; `fit` learns state and `predict` consumes it; population (ddof=0) scaling statistics;
shuffled, seeded splits; seed-dependent but reproducible stochastic initialization; majority vote
and inverse-distance weighting; tie-breaking toward the lowest class label; validation failure on
non-numeric/missing input; the meaning of `inertia_`, `coef_`, `intercept_`, `mean_`, `scale_`.

**What we invent (phrasing and shape).** English phrase names and *single-word* function names;
labeled arguments only (no positional, no defaults — `docs/REFERENCE.md` §5.3); models and
scalers as **self-describing maps** instead of mutable estimator objects; result maps with named
keys instead of positional tuples; structured problem kinds for validation; wrappers that fold
the recommended defaults into named functions; integration with `lib/math.ll` (`sqrt`, `average`,
`clamp`) and `lib/lists.ll` (`unique`, `flatten`). Every synonym/alias must produce one canonical
AST; ML functions add *no grammar*, only names in `lib/ml.ll` (closed-vocabulary rule, METHOD.md
step 4 / `src/llang/synonyms.py`).

---

## 2. Cross-cutting invariants

### 2.1 `fit` / `predict` separation
scikit-learn's `fit(X, y)` **mutates** the estimator (`coef_`, `intercept_`, `labels_`,
`cluster_centers_`) and returns `self`; `predict(X)` is a read-only consumer
(https://scikit-learn.org/stable/modules/linear_model.html#ordinary-least-squares,
https://scikit-learn.org/stable/modules/clustering.html#k-means). llang has no classes with
mutable method state we want to expose here, so we split the two roles into two functions:

- `fit_*` / `cluster` / `standardize` **return a model map** and never mutate their inputs.
- `predict` / `transform` take `model = MAP, features = ROWS` and are pure: same inputs → same
  output, no writes to the model.

This is a deliberate improvement, not a semantic change: the map *is* the fitted estimator.

### 2.2 Estimator state
Every model map has the same five top-level keys: `version`, `kind`, `fitted`, `parameters`,
`state`. `parameters` echoes the caller's hyperparameters; `state` holds learned numbers.
`predict` first checks `fitted` and `kind`, raising problem `not_fitted` or `wrong_model_kind`
at the call site. scikit-learn's analogous guards are `NotFittedError` and attribute lookup on
the estimator; llang makes them explicit, source-located problems. State is *self-describing*:
the map can be shown to the user or serialized via `write text to` after `text of`.

Aliasing caveat: llang has no copy operation (`docs/REFERENCE.md` §3). `fit_*` must construct a
**fresh** map/list tree and never return a caller-owned list as state; otherwise a later
`add ... to ...` or `set item ...` through an alias silently changes the model. By convention
models are read-only after construction; the linter can flag `set item KEY of MODEL ...` where
`MODEL` came from a `fit_*` call.

### 2.3 Deterministic seeds
scikit-learn stochastic estimators take `random_state`; control of randomness is an explicit
recommended practice (https://scikit-learn.org/stable/common_pitfalls.html#controlling-randomness).
llang has no global RNG and no hidden mutable state, so every stochastic ML function takes a
mandatory `seed` label. Our PRNG is a small pure linear-congruential generator whose full state is passed
explicitly inside `parameters`; a given `(inputs, seed, algorithm version)` yields byte-identical
output forever. The oracle's exact random stream is **not** copied (different implementation),
so differential tests compare *properties* (partition up to relabeling, inertia) for K-means
rather than raw cluster IDs (see §6). Pinned oracle fact: with the 2-cluster toy data used below,
`random_state=0` gives labels `[1,1,1,0,0,0]` and `random_state=1` gives `[0,0,0,1,1,1]` —
cluster IDs are seed-dependent, while inertia is 16.0 either way.

### 2.4 Train/test splits
`train_test_split` returns `(X_train, X_test, y_train, y_test)` in that order and **shuffles by
default** (`shuffle=True`); `random_state` makes the shuffle reproducible
(https://scikit-learn.org/stable/modules/cross_validation.html#a-note-on-shuffling).
Oracle pin: values `0..9`, `test_size=0.3`, `random_state=0` → train `[9,1,6,7,3,0,5]`, test
`[2,8,4]` (not the last three). Our `split` returns a map with keys `train_features`,
`test_features`, `train_labels`, `test_labels` so order can never be confused. The shuffle
algorithm may differ; harnesses assert set-disjointness, sizes, and per-seed repeatability, not
the exact permutation. `test_size` is accepted as a fraction in `(0,1)`; integer counts are
rejected with `bad_test_size` to keep one meaning per label.

### 2.5 Metric definitions
All metrics are pure functions over two equal-length lists, `actual` and `predicted`
(scikit-learn's `y_true`, `y_pred`; https://scikit-learn.org/stable/modules/model_evaluation.html):

- `accuracy = (# correct) / n`; with `normalize=false` sklearn returns a float count — our
  `accuracy` always returns the fraction; `accuracy_count` is a P2 wrapper
  (https://scikit-learn.org/stable/modules/model_evaluation.html#accuracy-score).
- `mse = Σ(y−ŷ)² / n`; `rmse = sqrt(mse)`; `mae = Σ|y−ŷ| / n`
  (https://scikit-learn.org/stable/modules/model_evaluation.html#regression-metrics). Oracle pin:
  actual `[3,-0.5,2,7]`, predicted `[2.5,0,2,8]` → MSE `0.375`, RMSE `0.6123724356957945`,
  MAE `0.5`.
- `r2 = 1 − SS_res/SS_tot`, `SS_tot = Σ(y−ȳ)²`. Oracle pins: perfect predictions → `1.0`;
  constant `y_true` with wrong predictions → `0.0`, constant `y_true` with exact predictions →
  `1.0` (sklearn's force_finite convention); non-trivial case above → `0.9486081370449679`.
  R² may be negative when the model is worse than the mean.
- Classification: with binary defaults (`pos_label` = positive class, `average='binary'`),
  `precision = TP/(TP+FP)`, `recall = TP/(TP+FN)`, `f1 = 2PR/(P+R)`. Oracle pin: actual
  `[0,0,1,1]`, predicted `[0,1,1,1]` → precision `2/3`, recall `1.0`, F1 `0.8`; confusion matrix
  rows are `[[TN,FP],[FN,TP]]`, `.ravel()` = `[TN,FP,FN,TP] = [1,1,0,2]`
  (https://scikit-learn.org/stable/modules/model_evaluation.html#confusion-matrix).
  Multi-class averaging is `macro` (mean over classes), `micro` (pool counts), `weighted`
  (prevalence-weighted); oracle pin for `[0,1,2]` vs `[0,2,1]`: macro F1 = micro F1 = `1/3`.
  Undefined precision/recall (no predicted positives, or no positives in truth) returns `0.0`
  with a warning in sklearn 1.8.0; llang returns `0.0` and records no warning, documented as a
  harmless divergence
  (https://scikit-learn.org/stable/modules/model_evaluation.html#from-binary-to-multiclass-and-multilabel).
- Every metric rejects empty lists and length mismatch with `bad_metric_input` at the call site.

### 2.6 Feature scaling
`StandardScaler` computes `mean_ = mean(X, axis=0)` and `scale_ = std(X, axis=0)` with **ddof=0**
(population standard deviation), then `transform(x) = (x − mean_) / scale_`
(https://scikit-learn.org/stable/modules/preprocessing.html#standardization-or-mean-removal-and-variance-scaling).
Oracle pins for `[[1,-1,2],[2,0,0],[0,1,-1]]`: `mean_ = [1, 0, 1/3]`,
`scale_ = [0.81649658, 0.81649658, 1.24721913]` (equals `np.std(ddof=0)`, not `ddof=1`).
A constant feature gets `scale_ = 1`, not 0, and transforms to a column of zeros — never divide
by zero. Fit statistics must be learned on **training data only**; applying them to test data is
how leakage is avoided (https://scikit-learn.org/stable/common_pitfalls.html#data-leakage).
Our `standardize` returns a scaler map; `transform` reuses its `mean`/`scale` lists.

### 2.7 Missing and non-numeric values
scikit-learn estimators require finite numeric feature matrices; missing values need imputation
(https://scikit-learn.org/stable/modules/impute.html) and categorical features need ordinal or
one-hot encoding
(https://scikit-learn.org/stable/modules/preprocessing.html#encoding-categorical-features).
llang has no `NaN` literal (`docs/REFERENCE.md` §2, §3): numeric rows must be lists of numbers
(`is a number` excludes booleans). `nothing` is the only missing marker. `ml` functions validate
every row and raise source-located problems: `bad_features` (non-list row), `non_numeric_feature`
(text/boolean/nothing in a row), `missing_value` (`nothing` where a number is required),
`inconsistent_width` (rows of different lengths), `empty_features` (zero rows). Imputation and
encoding are **out of scope** for v1 (§7); the validator makes their absence loud rather than
silent. Labels may be numbers (regression) or numbers/text/booleans (classification); mixed-type
label lists raise `invalid_labels`, since equality/ordering in llang is strict
(`docs/REFERENCE.md` §4.1).

### 2.8 Mapping onto llang maps / lists / functions
| ML concept | llang value |
|---|---|
| design matrix `X` | list of rows; each row is a list of numbers, all the same length |
| target vector `y` | list of numbers (regression) or comparable scalar values (classification) |
| hyperparameters / learned state / metadata | maps with text keys |
| estimator methods | single-word functions called with labeled args, resolved via `use the ml module` |
| prediction vector | list in the same order as the input rows |
| scorer | list of maps, or a result map, depending on the function |

Call mechanics from `docs/REFERENCE.md` §4.4 / §7b apply unchanged: `call NAME from ml with
label = expr, ...`, labels are single identifiers, all labels mandatory, values evaluated left to
right, unknown/missing/duplicate labels are errors for user-defined library functions (unlike
builtins, which silently ignore extra labels — §6 of the reference). Compound collection literals
used as argument values must be parenthesized because expression parsing is greedy.

---

## 3. Concrete model representation

### 3.1 Universal envelope
```
keys:   version, kind, fitted, parameters, state
version: 1                       # bump when any state shape changes
kind:    "linear_regression" | "k_means" | "k_neighbors" | "gaussian_nb" | "standardizer"
fitted:  true / false
parameters: the exact labels the caller supplied (for reproducibility and display)
state:      learned numbers only; shape determined by kind
```
`predict` dispatches on `kind`. `transform` accepts `kind = "standardizer"`. Unknown kind →
`unknown_model_kind`. `fitted = false` never escapes a `fit_*` function.

### 3.2 Exact llang shapes (one statement per line — map literals must stay on one line)

Linear regression, fitted on `X = [[0,0],[1,1],[2,2]]`, `y = [0,1,2]` (oracle: `coef_=[0.5,0.5]`,
`intercept_≈0`):
```
set model to a map with "version" mapped to 1, "kind" mapped to "linear_regression", "fitted" mapped to true, "parameters" mapped to (a map with "fit_intercept" mapped to true), "state" mapped to (a map with "coefficients" mapped to (a list of 0.5, 0.5), "intercept" mapped to 0.0)
```
Read back with `item "state" of model`, then `item "coefficients" of (item "state" of model)`.

K-means, fitted on six 2-D points with `clusters = 2`, `seed = 0`, `restarts = 10` (oracle:
`inertia_ = 16.0`, centers `[10,2]` and `[1,2]`):
```
set model to a map with "version" mapped to 1, "kind" mapped to "k_means", "fitted" mapped to true, "parameters" mapped to (a map with "clusters" mapped to 2, "seed" mapped to 0, "restarts" mapped to 10), "state" mapped to (a map with "centers" mapped to (a list of (a list of 10.0, 2.0), (a list of 1.0, 2.0)), "labels" mapped to (a list of 1, 1, 1, 0, 0, 0), "inertia" mapped to 16.0)
```
`labels` are integers in `0 .. clusters-1`, in the same order as the training rows.

k-nearest neighbours is lazy: state stores the training set, not a fitted boundary
(https://scikit-learn.org/stable/modules/neighbors.html#nearest-neighbors-classification notes
KNN is instance-based / non-generalizing):
```
set model to a map with "version" mapped to 1, "kind" mapped to "k_neighbors", "fitted" mapped to true, "parameters" mapped to (a map with "k" mapped to 3, "task" mapped to "classify", "weights" mapped to "uniform", "seed" mapped to 0), "state" mapped to (a map with "examples" mapped to (a list of (a list of 0.0, 0.0), (a list of 1.0, 1.0)), "labels" mapped to (a list of 0, 1), "classes" mapped to (a list of 0, 1))
```
`classes` is the sorted list of distinct labels; ties resolve to its first entry (lowest label),
matching the oracle pin below.

Standardizer (a transformer, but same envelope):
```
set scaler to a map with "version" mapped to 1, "kind" mapped to "standardizer", "fitted" mapped to true, "parameters" mapped to (a map with "with_mean" mapped to true, "with_std" mapped to true), "state" mapped to (a map with "mean" mapped to (a list of 1.0, 0.0, 0.3333333333333333), "scale" mapped to (a list of 0.816496580927726, 0.816496580927726, 1.247219128924647))
```

Gaussian naive Bayes (P2): `state` holds `classes`, `means`, `variances`, `priors`, `epsilon`.

### 3.3 Using a model
```
set predictions to call predict from ml with model = model, features = test_features
set scores to call evaluate from ml with model = model, features = test_features, actual = test_labels
show call accuracy from ml with actual = test_labels, predicted = predictions
```
`predict` returns a list; `evaluate` returns a map of metric name → number, choosing the metric
set by `kind`. Models are ordinary values: they can be `show`n (rendered as readable text via
`_render`, `docs/REFERENCE.md` §3) or written to a file with `write text to`.

---

## 4. Prioritized API

All names are single words with no spaces and cannot contain `with` (call-name rule,
`docs/REFERENCE.md` §4.4). All labels are mandatory. P0 = implement first (end-to-end regression,
classification, clustering, metrics); P1 = completeness; P2 = optional.

| llang function | labels | semantics (oracle-pinned) | scikit-learn equivalent | edge cases / problems | P |
|---|---|---|---|---|---|
| `split` | `features`, `labels`, `test_size`, `seed` | Shuffle both lists in lockstep with seeded PRNG; return map `train_features`, `test_features`, `train_labels`, `test_labels`. `test_size` is a fraction in `(0,1)`. Shuffled by default, like sklearn. | `train_test_split(X, y, test_size=..., random_state=...)` (https://scikit-learn.org/stable/modules/cross_validation.html#a-note-on-shuffling) | fraction out of range → `bad_test_size`; empty/short input → `too_few_samples`; lengths differ → `length_mismatch` | P0 |
| `standardize` | `features`, `with_mean`, `with_std` | Learn `mean`/`scale` (ddof=0) per column over all rows; constant column → scale 1; return standardizer map. | `StandardScaler.fit` (https://scikit-learn.org/stable/modules/preprocessing.html#standardization-or-mean-removal-and-variance-scaling) | zero rows, ragged rows, non-numeric cells → `bad_features` family | P0 |
| `transform` | `model`, `features` | Apply stored `mean`/`scale` to each row: `(x−mean)/scale`; pure. | `StandardScaler.transform` | wrong kind → `wrong_model_kind`; differing width → `inconsistent_width` | P0 |
| `fit_linear` | `features`, `targets`, `fit_intercept` | Solve ordinary least squares by normal equations with partial pivoting. Pin: `X=[[0,0],[1,1],[2,2]]`, `y=[0,1,2]` → coefficients `[0.5,0.5]`, intercept `0.0`; prediction at `[1,1]` is `1.0`. | `LinearRegression(fit_intercept=...)` (https://scikit-learn.org/stable/modules/linear_model.html#ordinary-least-squares) | rank-deficient design → `singular_matrix` (sklearn returns a min-norm SVD solution `[1/3,1/3,1/3]`; documented divergence, §6 corpus asserts the problem) | P0 |
| `gradient` | `features`, `targets`, `rate`, `steps`, `fit_intercept` | Batch gradient descent for the same OLS objective; deterministic sweep order; returns a `linear_regression` model. Steps must be a positive whole number. | SGD/OLS objective (https://scikit-learn.org/stable/modules/linear_model.html#ordinary-least-squares, https://scikit-learn.org/stable/modules/sgd.html) | divergence if `rate` too large → `diverged`; compare to `fit_linear` within looser tolerance | P1 |
| `predict` | `model`, `features` | Dispatch on `kind`. Regression → dot(coefficients, row)+intercept. KNN → vote/mean of k nearest by Euclidean distance. NB → max log posterior. | `estimator.predict` | `fitted=false` → `not_fitted`; unknown kind → `unknown_model_kind`; empty features → `empty_features` | P0 |
| `cluster` | `features`, `clusters` | Convenience: k-means with k-means++ seeding, `seed=0`, `restarts=10`, tolerance on centroid movement; returns model with `centers`, `labels`, `inertia`. Oracle pin: six toy points, 2 clusters → inertia `16.0`. | `KMeans(n_clusters=...)` (https://scikit-learn.org/stable/modules/clustering.html#k-means, https://scikit-learn.org/stable/modules/clustering.html#overview-of-clustering-methods) | `clusters > rows` → `too_many_clusters` (sklearn raises `ValueError: n_samples should be >= n_clusters`); non-numeric rows → `bad_features` | P0 |
| `kmeans` | `features`, `clusters`, `seed`, `restarts`, `init` | Expert form: `init` is `"kmeans_plus_plus"` or `"first_rows"`; pick restart with lowest inertia; stable `clusters` IDs. | `KMeans(init='k-means++', n_init=..., random_state=...)` (https://scikit-learn.org/stable/modules/clustering.html#k-means) | seeds 0 and 1 permute cluster IDs but keep inertia 16.0 — harness compares partitions up to relabeling | P1 |
| `neighbours` | `features`, `labels`, `k`, `task`, `weights`, `seed` | Store training rows; predict class by majority vote or target by mean of k nearest (Euclidean). `task` = `"classify"` / `"regress"`. `weights` = `"uniform"` (default) or `"distance"` (1/d). Pin: tie between labels 0 and 1 → 0 (lowest label); exact-match with distance weights → that point's class. | `KNeighborsClassifier`, `KNeighborsRegressor` (https://scikit-learn.org/stable/modules/neighbors.html#nearest-neighbors-classification, https://scikit-learn.org/stable/modules/neighbors.html#nearest-neighbors-regression) | `k > training rows` → `too_many_neighbors` (sklearn raises `ValueError: Expected n_neighbors <= n_samples_fit`); zero-distance neighbors get weight 1 and other weights 0 | P0 |
| `bayes` | `features`, `labels` | Gaussian NB: per class `mean`, biased (ddof=0) variance, empirical prior; estimate `argmax_c [log prior_c − ½Σ((x−mean_c)²/var_c + log(2π·var_c))]`. Oracle: `epsilon_ = 1e-9 × max_j Var(X[:,j])` = `4.6667e-9` for the toy set; `var_ = sample var + epsilon`. | `GaussianNB` (https://scikit-learn.org/stable/modules/naive_bayes.html#gaussian-naive-bayes) | zero-variance class feature handled by epsilon; single-class input → `need_two_classes` | P2 |
| `accuracy` | `actual`, `predicted` | Fraction of equal positions, using llang boolean-guarded equality (`true` ≠ `1`). Pin: `[0,2,1,3]` vs `[0,1,2,3]` → `0.5`. | `accuracy_score` (https://scikit-learn.org/stable/modules/model_evaluation.html#accuracy-score) | empty lists → `bad_metric_input` | P0 |
| `accuracy_count` | `actual`, `predicted` | Number of equal positions as a float (the `normalize=false` form). Pin: `2.0` for `[0,2,1,3]` vs `[0,1,2,3]`. | `accuracy_score(..., normalize=False)` | empty lists → `bad_metric_input` | P2 |
| `mse` | `actual`, `predicted` | `Σ(y−ŷ)² / n`. Pin: `0.375` on the four-point example. | `mean_squared_error` | length mismatch → `bad_metric_input` | P0 |
| `rmse` | `actual`, `predicted` | `sqrt(mse)` via `call sqrt from math with value = ...`; pin `0.6123724356957945`. | `root_mean_squared_error` | as `mse` | P0 |
| `mae` | `actual`, `predicted` | `Σ|y−ŷ| / n`; pin `0.5`. | `mean_absolute_error` | as `mse` | P0 |
| `r2` | `actual`, `predicted` | `1 − SS_res/SS_tot`; constant truth → 1 if exact else 0. Pin `0.9486081370449679`. | `r2_score` (https://scikit-learn.org/stable/modules/model_evaluation.html#regression-metrics) | fewer than 2 rows → `bad_metric_input` | P0 |
| `precision` | `actual`, `predicted`, `positive` | `TP/(TP+FP)`; undefined → `0.0`; `positive` defaults conceptually to `1` (passed explicitly via wrapper). Pin `2/3`. | `precision_score` (https://scikit-learn.org/stable/modules/model_evaluation.html#classification-metrics) | non-binary labels with default averaging → `need_binary_labels`; use `average` wrapper for multi-class | P1 |
| `recall` | `actual`, `predicted`, `positive` | `TP/(TP+FN)`; pin `1.0`. | `recall_score` | as `precision` | P1 |
| `f1` | `actual`, `predicted`, `positive` | `2PR/(P+R)`; pin `0.8`. Multi-class wrappers `f1_macro`, `f1_micro`, `f1_weighted` implement sklearn's averaging rules. | `f1_score` (https://scikit-learn.org/stable/modules/model_evaluation.html#from-binary-to-multiclass-and-multilabel) | all-wrong binary case → `0.0` | P1 |
| `confusion` | `actual`, `predicted`, `classes` | Map of `"class → list of predicted counts"`; binary counts `[TN,FP]` / `[FN,TP]`. | `confusion_matrix` (https://scikit-learn.org/stable/modules/model_evaluation.html#confusion-matrix) | missing class in `classes` → `invalid_labels` | P1 |
| `evaluate` | `model`, `features`, `actual` | Predict, then return a map of metrics appropriate to `kind`: regression → `mse`, `rmse`, `mae`, `r2`; classify → `accuracy`, `precision`, `recall`, `f1`, `confusion`; cluster → `inertia`, `centers`. | `estimator.score` + `cross_validate` scoring (https://scikit-learn.org/stable/modules/model_evaluation.html#scoring-api-overview) | metrics that do not apply to the kind → `wrong_model_kind` | P1 |
| `report` | `scores` | Return a human-readable single text line from an `evaluate` map, with explicit names and rounded numbers (via `call rounded to places`). | `classification_report` (https://scikit-learn.org/stable/modules/model_evaluation.html#classification-metrics) | non-map input → `bad_scores` | P2 |
| `distance` | `left`, `right` | Euclidean distance of two numeric lists; shared by `neighbours` and `cluster`; `sqrt` from `lib/math.ll`. | `sklearn.metrics.pairwise_distances` | width mismatch → `inconsistent_width` | P1 |
| `column` | `rows`, `index` | Extract one column as a list; for `standardize`/`evaluate` composition with `lib/lists.ll`. | NumPy slicing (not an sklearn estimator) | out of range → `index_out_of_range` | P1 |

**Tie/weight details worth keeping in code comments.** Uniform-weight KNN classification is a
majority vote; sklearn breaks exact ties by lowest class label (oracle: training `[0],[2]` with
labels `[1],[0]`, query `[1]` → `0`, probabilities `[0.5,0.5]`). With `weights='distance'`, a query
that exactly equals a training row gives that row weight 1 and all others 0 (oracle: query `[0]`
→ class `1` with probability `[0,1]`). KNN regression with `k=2` on targets `[0,10,20,30]` and
query `1.5` → `15` (plain mean). K-means stops when centroid movement is below tolerance, not
when relative objective decrease is below tolerance
(https://scikit-learn.org/stable/modules/clustering.html#k-means).

---

## 5. Quality-of-life improvements scikit-learn lacks

1. **Verbose, self-documenting names.** No `KNeighborsClassifier(n_neighbors=3, weights='distance')`;
   the call reads as a sentence and every name is one word:
```
use the ml module
use the math module
set predictions to call predict from ml with model = knn_model, features = test_features
set err to call rmse from ml with actual = test_targets, predicted = predictions
show call rounded to places with value = err, places = 4
```
2. **Labeled arguments everywhere.** sklearn allows positional args and has dozens of optional
   keyword parameters with defaults; llang has none, so a call is auditable by reading it
   (`docs/REFERENCE.md` §9 divergence 10). Missing/duplicate/unknown labels are source-located
   errors for library functions.
3. **Models are readable maps with metadata.** `show model` prints all keys, the seed, and
   learned numbers; no `pickle`, `__dict__`, or opaque estimator repr (contrast sklearn's model
   persistence caveats, https://scikit-learn.org/stable/modules/model_persistence.html#security-maintainability-limitations).
   The `version` and `parameters` keys make a saved model self-explaining.
4. **Automatic input validation with source-located errors.** Implement one shared validator in
   `lib/ml.ll`; use `require` and `fail with KIND, "message"` so diagnostics point at the caller:
```
define function validate_features taking rows
    repeat for each row in rows
        require row is a list, "each row of features must be a list"
        repeat for each value in row
            require value is a number, "feature values must be numbers"
        end repeat
    end repeat
end function

define function fit_linear taking features, targets, fit_intercept
    call validate_features with rows = features
    require (the length of features) equals (the length of targets), "features and targets must align"
    show "fitting a linear model"     # observable, self-documenting progress
    ...
end function
```
   A malformed row raises `In call to 'fit_linear': ... at line X, column Y` with the call
   position — sklearn's stack traces are not localized to the offending call.
5. **Built-in train / evaluate / report helpers.** The entire workflow is three labeled calls,
   with no `Pipeline` object required:
```
set parts to call split from ml with features = data, labels = targets, test_size = 0.25, seed = 0
set model to call fit_linear from ml with features = (item "train_features" of parts), targets = (item "train_labels" of parts), fit_intercept = true
set scores to call evaluate from ml with model = model, features = (item "test_features" of parts), actual = (item "test_labels" of parts)
show call report from ml with scores = scores
```
6. **Deterministic defaults.** Because llang has no optional parameters, the recommended defaults
   are encoded in *named wrappers*: `cluster` fixes `seed = 0`, `restarts = 10`,
   `init = "kmeans_plus_plus"`; `neighbours` fixes `weights = "uniform"`, `task = "classify"`.
   Experts call `kmeans` or `neighbours` with every knob explicit. No global RNG, no hidden
   environment state, no `random_state=None` surprise
   (https://scikit-learn.org/stable/common_pitfalls.html#controlling-randomness).
7. **Composition with the data-science and math libraries.** ML outputs are ordinary
   numbers/lists/maps, so they feed existing native modules without adapters:
```
set err to call mse from ml with actual = actuals, predicted = predictions
show call sqrt from math with value = err                  # same as rmse
set centered to call rotate from lists with items = values, places = 1
set unique_classes to call unique from lists with items = labels
set clipped to call clamp from math with value = score, low = 0.0, high = 1.0
```
8. **One vocabulary, no special syntax.** `lib/ml.ll` defines functions only; the grammar,
   reserved-word set (`src/llang/synonyms.py`), and parser are untouched, so formatter and linter
   work unchanged (METHOD.md steps 4–9).

---

## 6. Verification plan

Follow `tools/compare_json.py` as the template: Python drives a corpus, generates a temporary
`.ll` harness with `run.py`-compatible syntax, executes it via `subprocess`, reads results through
the foreign `json` module, and diffs against the oracle. The llang side must stay native
(no sklearn inside llang); sklearn is used **only in the Python harness**.

**Harnesses to add** (all named `tools/compare_*.py`, all printing `compared N cases, M mismatches`
and exiting nonzero on mismatch):

- `tools/compare_ml_split.py` — fractions 0.1/0.25/0.5, seeds 0/1/42, repeated calls; assert
  disjoint train/test sets, union equals input, sizes match sklearn's counts, and identical seed
  reproduces byte-identical output.
- `tools/compare_ml_standardize.py` — fit/transform on the oracle example, constant columns,
  negative values; compare `mean`/`scale` lists to `StandardScaler.mean_`/`scale_`, check scaled
  columns have mean ≈0 and std ≈1 (ddof=0) for non-constant features, and constant columns are 0.
- `tools/compare_ml_linear.py` — full-rank problems (including a 3-feature case), `fit_intercept`
  true/false, predictions on a holdout; compare coefficients/intercept/predictions to
  `LinearRegression`. Separate case asserts `singular_matrix` is raised on the rank-deficient
  corpus row (documented divergence).
- `tools/compare_ml_kmeans.py` — 2-D and 3-D toy sets, seeds 0/1/42, clusters 2/3; compare
  inertia to `KMeans.inertia_`, compare partitions with `adjusted_rand_score == 1.0` (label
  permutation allowed), and check `clusters > rows` raises `too_many_clusters`.
- `tools/compare_ml_neighbors.py` — classification ties, regression means, `weights='uniform'`
  and `'distance'`, exact-match queries; compare predictions/probabilities to
  `KNeighborsClassifier`/`KNeighborsRegressor` and assert `too_many_neighbors` on oversized k.
- `tools/compare_ml_bayes.py` (P2) — compare `theta_`, `var_`, `class_prior_`, predictions to
  `GaussianNB` with epsilon included.
- `tools/compare_ml_metrics.py` — every metric on the pinned examples plus random vectors,
  binary and multi-class, perfect/constant/all-wrong cases; compare to `sklearn.metrics`.

**Curated corpus** (shared fixture written as JSON, mirroring `tools/compare_json.py`):
2-point and 6-point toy clusters; the oracle's `[[0,0],[1,1],[2,2]]` regression set; a
3-feature full-rank set; the constant-feature scaler set; the rank-deficient set; tied-distance
neighbors; imbalanced binary labels `[0,0,0,1]`; single-class label set; constant numeric targets;
and negative/zero values (`0.0`, `0 minus 1.0`) to exercise llang's lack of negative literals.
Corpus rows are also emitted as literal `.ll` text so the parser path is exercised, not just file I/O.

**Tolerance rules.**
- Integers, booleans, problem kinds, and map keys: **exact** equality.
- Floats for closed-form linear algebra, scaling, and metrics: `abs(a−b) <= 1e-9 + 1e-7·|b|`
  (absolute 1e-9, relative 1e-7). Oracle pins like intercept `1.1102230246251565e-16` vs our
  `0.0` pass.
- Iterative K-means centroids/distances: `1e-6` absolute; inertia: `1e-6` absolute or `1e-7`
  relative. Cluster IDs compared only up to permutation (ARI), never by raw integer equality.
- kNN distance-weighted probabilities: `1e-9`; vote-derived class labels: exact.
- Gaussian NB log-posteriors: `1e-8`; variances: `1e-9 + 1e-7·|b|`.
- NaN/inf inputs are not in the corpus (llang has no such literals); error-case rows compare
  the raised problem `KIND` only.

**Seeded determinism gate.** For every harness, run each seeded case twice in fresh subprocesses
and assert byte-identical stdout and result JSON. Pin the oracle version in harness output
(`assert sklearn.__version__ == "1.8.0"`, or record it in a `golden/` manifest and re-baseline
deliberately on upgrade). Add the harnesses to `tools/check.py` alongside the existing
`compare_*.py` suite; CI fails on any mismatch, and the counts are printed for auditability.

---

## 7. Explicit omissions

The following are deliberately **not** in `lib/ml.ll` v1. Each is a scope boundary, not a bug;
the validator in §2.7 makes unsupported input fail loudly rather than silently misbehave.

- **Neural networks** (MLP, RBM): no tensors, no autodiff, no batching primitives in llang;
  https://scikit-learn.org/stable/modules/neural_networks_supervised.html.
- **Gradient boosting / random forests / all ensembles**: tree construction and large model
  state are outside the map-shaped model envelope;
  https://scikit-learn.org/stable/modules/ensemble.html.
- **Support vector machines** (SVC/SVR, kernels, `LinearSVC`): kernel trick and hinge-loss QP
  solvers have no native analogue; https://scikit-learn.org/stable/modules/svm.html.
- **Sparse matrices and sparse-aware estimators**: llang has only dense lists; CSR/CSC/
  `sparse_output` concepts are absent; https://scikit-learn.org/stable/modules/preprocessing.html#scaling-sparse-data.
- **Pipelines beyond simple composition**: no `Pipeline`, `ColumnTransformer`, `FeatureUnion`,
  caching, or `set_output`; users chain plain calls as in §5 item 5
  (https://scikit-learn.org/stable/modules/compose.html).
- **Hyperparameter search / cross-validation**: no `GridSearchCV`, `RandomizedSearchCV`, k-fold
  helpers; a single `split` + manual loop is the supported workflow
  (https://scikit-learn.org/stable/modules/grid_search.html,
  https://scikit-learn.org/stable/modules/cross_validation.html).
- Also out of scope for v1: PCA and other matrix factorizations, decision trees, DBSCAN/hierarchical
  clustering, imputation, categorical encoders, probability calibration, ROC/AUC and
  precision/recall curves, sample weights, multi-output targets, and missing-value-aware
  estimators. Polynomial features beyond manual math-library composition are deferred.
