"""Compare lib/machinelearning.ll against scikit-learn 1.8.0.

Corpus-driven: a JSON corpus is read by a generated llang harness through the
foreign json module, every result is computed by the native module, and the
results are diffed in Python against the oracle. Seeded cases are run twice in
fresh subprocesses to gate determinism.
"""

import json
import math
import re
import subprocess
import sys
import atexit
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

import sklearn  # noqa: E402
from sklearn.cluster import KMeans  # noqa: E402
from sklearn.linear_model import LinearRegression  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score, adjusted_rand_score, confusion_matrix, f1_score,
    mean_absolute_error, mean_squared_error, precision_score, r2_score,
    recall_score, root_mean_squared_error,
)
from sklearn.model_selection import train_test_split  # noqa: E402
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

ML = "machinelearning"


def lit(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if value < 0:
            return "0 minus " + lit(-value)
        return repr(value) if isinstance(value, float) else str(value)
    if isinstance(value, str):
        return '"' + value + '"'
    if isinstance(value, (list, tuple)):
        return "(a list of " + ", ".join(lit(item) for item in value) + ")" if value else "(an empty list)"
    if isinstance(value, dict):
        return "(a map with " + ", ".join(
            f"{lit(key)} mapped to {lit(item)}" for key, item in value.items()
        ) + ")" if value else "(an empty map)"
    raise TypeError(f"cannot literal {value!r}")


VALUES = list(range(10))
LINEAR_A = [[1, 2], [2, 3], [3, 1], [4, 5]]
LINEAR_B = [[1, 2, 3], [2, 1, 4], [3, 3, 1], [4, 2, 2], [5, 5, 5]]
CLUSTER_A = [[0, 0], [1, 1], [8, 8], [9, 9], [1, 0], [9, 8]]
CLUSTER_B = [[0, 0, 0], [1, 1, 0], [8, 8, 1], [9, 9, 1], [0, 1, 0], [9, 8, 1]]

CORPUS = {
    "split": [
        {"features": [[v] for v in VALUES], "labels": VALUES,
         "test_size": fraction, "seed": seed}
        for fraction in (0.1, 0.25, 0.5) for seed in (0, 1, 42)
    ] + [
        {"features": [[v] for v in VALUES], "labels": VALUES,
         "test_size": 0.3, "seed": 0},  # repeated for the determinism gate
        {"features": [[v] for v in VALUES], "labels": VALUES,
         "test_size": 0.3, "seed": 0},
    ],
    "standardize": [
        {"features": [[1, -1, 2], [2, 0, 0], [0, 1, -1]],
         "with_mean": True, "with_std": True},
        {"features": [[5, 2], [5, 4], [5, -2]],
         "with_mean": True, "with_std": True},
        {"features": [[-3, 1.5], [0, 2.5], [4, -0.5]],
         "with_mean": True, "with_std": True},
        {"features": [[1, 2], [3, 4], [5, 6]],
         "with_mean": False, "with_std": False},
    ],
    "linear": [
        {"features": LINEAR_A, "targets": [1, 2, 3, 6],
         "fit_intercept": True, "queries": [[2, 1], [0, 4]]},
        {"features": LINEAR_A, "targets": [1, 2, 3, 6],
         "fit_intercept": False, "queries": [[2, 1], [0, 4]]},
        {"features": LINEAR_B, "targets": [2, 3, 5, 4, 9],
         "fit_intercept": True, "queries": [[2, 1, 4], [1, 3, 2]]},
        {"features": [[-1, 2], [0, -3], [2, 1], [4, 0]],
         "targets": [-2, 1, 5, 7], "fit_intercept": True,
         "queries": [[1, 1], [-2, 3]]},
    ],
    "neighbors": [
        {"features": [[0, 0], [1, 1], [2, 0], [5, 5], [6, 4], [7, 6]],
         "labels": [0, 0, 1, 1, 2, 2], "k": k, "task": "classify",
         "weights": weights, "seed": 0, "queries": [[1, 0], [4, 4], [6, 5]]}
        for k in (1, 3) for weights in ("uniform", "distance")
    ] + [
        {"features": [[0], [1], [2], [3]], "labels": [0, 10, 20, 30],
         "k": 2, "task": "regress", "weights": "uniform", "seed": 0,
         "queries": [[1.5], [2.5]]},
        {"features": [[0], [2]], "labels": [1, 0], "k": 2,
         "task": "classify", "weights": "uniform", "seed": 0,
         "queries": [[1]]},
        {"features": [[0], [2], [4]], "labels": [1, 0, 1], "k": 2,
         "task": "classify", "weights": "distance", "seed": 0,
         "queries": [[0]]},
    ],
    "cluster": [
        {"features": CLUSTER_A, "clusters": 2, "seed": seed,
         "restarts": 10, "init": "kmeans_plus_plus"}
        for seed in (0, 1, 42)
    ] + [
        {"features": CLUSTER_B, "clusters": 3, "seed": 42,
         "restarts": 10, "init": "kmeans_plus_plus"},
        {"features": CLUSTER_A, "clusters": 2, "seed": 1,
         "restarts": 10, "init": "first_rows"},
    ],
    "regression_metrics": [
        {"actual": [3, -0.5, 2, 7], "predicted": [2.5, 0, 2, 8]},
        {"actual": [1, 2, 3, 4], "predicted": [1, 2, 3, 4]},
        {"actual": [0, 0, 0, 0], "predicted": [1, 2, 3, 4]},
    ],
    "metrics": [
        {"actual": [0, 0, 1, 1], "predicted": [0, 1, 1, 1],
         "positive": 1, "classes": [0, 1]},
        {"actual": [0, 1, 2], "predicted": [0, 2, 1],
         "positive": 2, "classes": [0, 1, 2]},
        {"actual": [0, 0, 0, 0], "predicted": [1, 2, 3, 4],
         "positive": 1, "classes": [0, 1, 2, 3, 4]},
    ],
}

ERROR_CASES = [
    ("call split from machinelearning with features = (a list of (a list of 1), (a list of 2)), labels = (a list of 1, 2), test_size = 1.5, seed = 0", "bad_test_size"),
    ("call split from machinelearning with features = (a list of (a list of 1)), labels = (a list of 1), test_size = 0.5, seed = 0", "too_few_samples"),
    ("call standardize from machinelearning with features = (a list of (a list of 1), (a list of 2, 3)), with_mean = true, with_std = true", "inconsistent_width"),
    ("call standardize from machinelearning with features = (a list of (a list of \"x\")), with_mean = true, with_std = true", "non_numeric_feature"),
    ("call neighbours from machinelearning with features = (a list of (a list of 1)), labels = (a list of 0), k = 3, task = \"classify\", weights = \"uniform\", seed = 0", "too_many_neighbors"),
    ("call kmeans from machinelearning with features = (a list of (a list of 1), (a list of 2)), clusters = 3, seed = 0, restarts = 2, init = \"first_rows\"", "too_many_clusters"),
    ("call mse from machinelearning with actual = (an empty list), predicted = (an empty list)", "bad_metric_input"),
    ("set m to call fit_linear from machinelearning with features = (a list of (a list of 1)), targets = (a list of 1), fit_intercept = true\nset item \"fitted\" of m to false\nshow call predict with model = m, features = (a list of (a list of 1))", "not_fitted"),
]


def close(left, right, abs_tol=1e-9, rel_tol=1e-7):
    if isinstance(left, (list, tuple)):
        return (len(left) == len(right)
                and all(close(a, b, abs_tol, rel_tol)
                        for a, b in zip(left, right)))
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    try:
        return math.isclose(float(left), float(right),
                            abs_tol=abs_tol, rel_tol=rel_tol)
    except (TypeError, ValueError):
        return left == right


def harness_source(cases_path, results_path):
    def path(p):
        return str(p).replace("\\", "/")

    return f"""use the {ML} module
use the foreign json module

set data to call loads from json with text = (call read_file with path = "{path(cases_path)}")
set out to an empty map

set split_results to an empty list
repeat for each case in item "split" of data
    set parts to call split from {ML} with features = (item "features" of case), labels = (item "labels" of case), test_size = (item "test_size" of case), seed = (item "seed" of case)
    add parts to split_results
end repeat
set item "split" of out to split_results

set scale_results to an empty list
repeat for each case in item "standardize" of data
    set scaler to call standardize from {ML} with features = (item "features" of case), with_mean = (item "with_mean" of case), with_std = (item "with_std" of case)
    set state to item "state" of scaler
    set entry to a map with "mean" mapped to (item "mean" of state), "scale" mapped to (item "scale" of state), "transformed" mapped to (call transform from {ML} with model = scaler, features = (item "features" of case))
    add entry to scale_results
end repeat
set item "standardize" of out to scale_results

set linear_results to an empty list
repeat for each case in item "linear" of data
    set model to call fit_linear from {ML} with features = (item "features" of case), targets = (item "targets" of case), fit_intercept = (item "fit_intercept" of case)
    set state to item "state" of model
    set entry to a map with "coefficients" mapped to (item "coefficients" of state), "intercept" mapped to (item "intercept" of state), "predictions" mapped to (call predict with model = model, features = (item "queries" of case)), "kind" mapped to (item "kind" of model)
    add entry to linear_results
end repeat
set item "linear" of out to linear_results

set neighbor_results to an empty list
repeat for each case in item "neighbors" of data
    set model to call neighbours from {ML} with features = (item "features" of case), labels = (item "labels" of case), k = (item "k" of case), task = (item "task" of case), weights = (item "weights" of case), seed = (item "seed" of case)
    set entry to a map with "predictions" mapped to (call predict with model = model, features = (item "queries" of case)), "classes" mapped to (item "classes" of (item "state" of model))
    add entry to neighbor_results
end repeat
set item "neighbors" of out to neighbor_results

set cluster_results to an empty list
repeat for each case in item "cluster" of data
    set model to call kmeans from {ML} with features = (item "features" of case), clusters = (item "clusters" of case), seed = (item "seed" of case), restarts = (item "restarts" of case), init = (item "init" of case)
    set state to item "state" of model
    set entry to a map with "centers" mapped to (item "centers" of state), "labels" mapped to (item "labels" of state), "inertia" mapped to (item "inertia" of state), "predictions" mapped to (call predict with model = model, features = (item "features" of case))
    add entry to cluster_results
end repeat
set item "cluster" of out to cluster_results

set regression_results to an empty list
repeat for each case in item "regression_metrics" of data
    set truth to item "actual" of case
    set guess to item "predicted" of case
    set entry to a map with "mse" mapped to (call mse from {ML} with actual = truth, predicted = guess), "rmse" mapped to (call rmse from {ML} with actual = truth, predicted = guess), "mae" mapped to (call mae from {ML} with actual = truth, predicted = guess), "r2" mapped to (call r2 from {ML} with actual = truth, predicted = guess)
    add entry to regression_results
end repeat
set item "regression_metrics" of out to regression_results

set metric_results to an empty list
repeat for each case in item "metrics" of data
    set truth to item "actual" of case
    set guess to item "predicted" of case
    set entry to a map with "accuracy" mapped to (call accuracy from {ML} with actual = truth, predicted = guess), "precision" mapped to (call precision from {ML} with actual = truth, predicted = guess, positive = (item "positive" of case)), "recall" mapped to (call recall from {ML} with actual = truth, predicted = guess, positive = (item "positive" of case)), "f1" mapped to (call f1 from {ML} with actual = truth, predicted = guess, positive = (item "positive" of case)), "f1_macro" mapped to (call f1_macro from {ML} with actual = truth, predicted = guess), "f1_micro" mapped to (call f1_micro from {ML} with actual = truth, predicted = guess), "f1_weighted" mapped to (call f1_weighted from {ML} with actual = truth, predicted = guess), "confusion" mapped to (call confusion from {ML} with actual = truth, predicted = guess, classes = (item "classes" of case))
    add entry to metric_results
end repeat
set item "metrics" of out to metric_results

call write_file with path = "{path(results_path)}", content = (call dumps from json with value = out)
"""


def run_harness(work):
    cases_path = work / "cases.json"
    results_path = work / "results.json"
    harness_path = work / "harness.ll"
    cases_path.write_text(json.dumps(CORPUS), encoding="utf-8")
    harness_path.write_text(harness_source(cases_path, results_path), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(ROOT / "run.py"), str(harness_path)],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
    timeout=300)
    if completed.returncode != 0:
        print("llang harness failed:")
        print(completed.stdout)
        print(completed.stderr)
        sys.exit(1)
    return completed.stdout, results_path.read_text(encoding="utf-8"), json.loads(results_path.read_text(encoding="utf-8"))


def run_error_case(work, expression, index):
    path = work / f"error_{index}.ll"
    body = expression if "\n" in expression else f"show {expression}"
    path.write_text(f"use the {ML} module\n{body}\n", encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(ROOT / "run.py"), str(path)],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
    timeout=300)


def main():
    if sklearn.__version__ != "1.8.0":
        print(f"oracle version drift: expected 1.8.0, got {sklearn.__version__}")
        sys.exit(1)

    work = Path(tempfile.mkdtemp(prefix="llang_ml_"))

    atexit.register(shutil.rmtree, work, ignore_errors=True)
    stdout_a, raw_a, results = run_harness(work)
    stdout_b, raw_b, _ = run_harness(work)

    mismatches = 0

    def fail(label, got, want):
        nonlocal mismatches
        mismatches += 1
        print(f"{label}: got {got!r}, want {want!r}")

    # Seeded determinism: identical bytes in fresh subprocesses.
    if stdout_a != stdout_b or raw_a != raw_b:
        fail("DETERMINISM", "different runs differ", "byte-identical output")

    for case, actual in zip(CORPUS["split"], results["split"]):
        values = case["labels"]
        n_test = math.ceil(len(values) * case["test_size"])
        train, test = actual["train_labels"], actual["test_labels"]
        _, sklearn_test = train_test_split(
            values, test_size=case["test_size"], random_state=case["seed"])
        if (len(test) != n_test or len(train) != len(values) - n_test
                or len(sklearn_test) != n_test
                or sorted(train + test) != sorted(values)
                or set(train) & set(test)):
            fail("SPLIT", actual, f"disjoint partition with {n_test} test rows")

    repeated = results["split"][-1]
    if repeated != results["split"][-2]:
        fail("SPLIT-SEED", repeated, results["split"][-2])

    for case, actual in zip(CORPUS["standardize"], results["standardize"]):
        expected = StandardScaler(
            with_mean=case["with_mean"], with_std=case["with_std"]
        ).fit(case["features"])
        want_mean = (expected.mean_.tolist() if expected.mean_ is not None
                     else [0.0] * len(case["features"][0]))
        want_scale = (expected.scale_.tolist() if expected.scale_ is not None
                      else [1.0] * len(case["features"][0]))
        if not close(actual["mean"], want_mean):
            fail("SCALE mean", actual["mean"], want_mean)
        if not close(actual["scale"], want_scale):
            fail("SCALE scale", actual["scale"], want_scale)
        if not close(actual["transformed"],
                     expected.transform(case["features"]).tolist()):
            fail("SCALE transform", actual["transformed"],
                 expected.transform(case["features"]).tolist())

    for case, actual in zip(CORPUS["linear"], results["linear"]):
        expected = LinearRegression(fit_intercept=case["fit_intercept"]).fit(
            case["features"], case["targets"])
        if not close(actual["coefficients"], expected.coef_.tolist()):
            fail("LINEAR coef", actual["coefficients"], expected.coef_.tolist())
        if not close(actual["intercept"], float(expected.intercept_)):
            fail("LINEAR intercept", actual["intercept"], float(expected.intercept_))
        if not close(actual["predictions"],
                     expected.predict(case["queries"]).tolist()):
            fail("LINEAR predict", actual["predictions"],
                 expected.predict(case["queries"]).tolist())
        if actual["kind"] != "linear_regression":
            fail("LINEAR kind", actual["kind"], "linear_regression")

    for case, actual in zip(CORPUS["neighbors"], results["neighbors"]):
        if case["task"] == "classify":
            expected = KNeighborsClassifier(n_neighbors=case["k"],
                                            weights=case["weights"]).fit(
                case["features"], case["labels"])
        else:
            expected = KNeighborsRegressor(n_neighbors=case["k"],
                                           weights=case["weights"]).fit(
                case["features"], case["labels"])
        want = expected.predict(case["queries"]).tolist()
        if case["task"] == "classify" and actual["predictions"] != want:
            fail("KNN classify", actual["predictions"], want)
        if case["task"] == "regress" and not close(actual["predictions"], want):
            fail("KNN regress", actual["predictions"], want)

    for case, actual in zip(CORPUS["cluster"], results["cluster"]):
        expected = KMeans(n_clusters=case["clusters"], random_state=case["seed"],
                          n_init=10).fit(case["features"])
        if not close(actual["inertia"], float(expected.inertia_),
                     abs_tol=1e-6, rel_tol=1e-7):
            fail("KMEANS inertia", actual["inertia"], float(expected.inertia_))
        if adjusted_rand_score(actual["labels"], expected.labels_) != 1.0:
            fail("KMEANS partition", actual["labels"], expected.labels_.tolist())
        if actual["predictions"] != actual["labels"]:
            fail("KMEANS predict", actual["predictions"], actual["labels"])

    for case, actual in zip(CORPUS["regression_metrics"],
                            results["regression_metrics"]):
        truth, guess = case["actual"], case["predicted"]
        expected = {
            "mse": float(mean_squared_error(truth, guess)),
            "rmse": float(root_mean_squared_error(truth, guess)),
            "mae": float(mean_absolute_error(truth, guess)),
            "r2": float(r2_score(truth, guess)),
        }
        for name, want in expected.items():
            if not close(actual[name], want):
                fail(f"REGRESSION {name}", actual[name], want)

    for case, actual in zip(CORPUS["metrics"], results["metrics"]):
        truth, guess = case["actual"], case["predicted"]
        positive = case["positive"]
        expected = {
            "accuracy": float(accuracy_score(truth, guess)),
            "f1_macro": float(f1_score(truth, guess, average="macro",
                                       zero_division=0)),
            "f1_micro": float(f1_score(truth, guess, average="micro",
                                       zero_division=0)),
            "f1_weighted": float(f1_score(truth, guess, average="weighted",
                                          zero_division=0)),
        }
        if len(set(truth + guess)) <= 2:
            expected["precision"] = float(precision_score(
                truth, guess, zero_division=0))
            expected["recall"] = float(recall_score(truth, guess, zero_division=0))
            expected["f1"] = float(f1_score(truth, guess, zero_division=0))
        for name, want in expected.items():
            if not close(actual[name], want):
                fail(f"METRIC {name}", actual[name], want)
        matrix = confusion_matrix(truth, guess, labels=case["classes"]).tolist()
        want_matrix = {str(label): row for label, row in
                       zip(case["classes"], matrix)}
        got_matrix = {str(key): value for key, value in actual["confusion"].items()}
        if got_matrix != want_matrix:
            fail("METRIC confusion", got_matrix, want_matrix)

    for index, (expression, kind) in enumerate(ERROR_CASES):
        completed = run_error_case(work, expression, index)
        text = completed.stdout + completed.stderr
        if completed.returncode == 0 or not re.search(
                r"Unhandled problem '" + re.escape(kind) + r"'", text):
            fail(f"ERROR {kind}", text.strip()[-200:], f"problem '{kind}'")

    total = sum(len(group) for group in CORPUS.values()) + len(ERROR_CASES) + 1
    print(f"compared {total} cases, {mismatches} mismatches")
    if mismatches:
        sys.exit(1)
    print(f"lib/machinelearning.ll matches scikit-learn {sklearn.__version__}")


if __name__ == "__main__":
    main()
