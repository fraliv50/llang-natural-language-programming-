"""Unit and differential tests for lib/machinelearning.ll.

scikit-learn 1.8.0 is the oracle. llang runs natively through the interpreter;
no host-language bridge is used inside the module.
"""

import ast
import contextlib
import io
import math
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang import LangError, Lexer, Parser, Interpreter  # noqa: E402

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
    """Render a Python value as an llang literal (no negative literals in llang)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if value < 0:
            return "0 minus " + lit(-value)
        if isinstance(value, float):
            return repr(value)
        return str(value)
    if isinstance(value, str):
        return '"' + value + '"'
    if isinstance(value, (list, tuple)):
        if not value:
            return "(an empty list)"
        return "(a list of " + ", ".join(lit(item) for item in value) + ")"
    if isinstance(value, dict):
        if not value:
            return "(an empty map)"
        entries = ", ".join(f"{lit(key)} mapped to {lit(item)}"
                            for key, item in value.items())
        return "(a map with " + entries + ")"
    raise TypeError(f"cannot literal {value!r}")


def run(source):
    interpreter = Interpreter(library_paths=[ROOT / "lib"])
    with contextlib.redirect_stdout(io.StringIO()):
        interpreter.run(Parser(Lexer(source).tokenize()).parse_program())
    return interpreter.output


def program(body):
    return f"use the {ML} module\n{body}\n"


def show(expr):
    return run(program("show " + expr))[0]


def call(fn, **kwargs):
    args = ", ".join(f"{key} = {lit(value)}" for key, value in kwargs.items())
    return f"call {fn} from {ML} with {args}"


def numeric(text):
    """Parse a rendered llang number or list of numbers."""
    return ast.literal_eval(text)


def text_list(text):
    """Parse a rendered llang list of text values (rendered without quotes)."""
    if text == "[]":
        return []
    return text[1:-1].split(", ")


def almost(a, b, abs_tol=1e-9, rel_tol=1e-7):
    if isinstance(a, (list, tuple)):
        assert len(a) == len(b)
        for left, right in zip(a, b):
            almost(left, right, abs_tol, rel_tol)
        return
    if isinstance(a, bool) or isinstance(b, bool):
        assert a == b
        return
    assert math.isclose(float(a), float(b), abs_tol=abs_tol, rel_tol=rel_tol), (
        f"{a!r} != {b!r}")


def model_state(body, field):
    return numeric(show(f"item \"{field}\" of (item \"state\" of ({body}))"))


class MachineLearningTests(unittest.TestCase):
    # --- envelope, builtin predict, regression ---------------------------

    def test_model_envelope_and_builtin_predict(self):
        body = call("fit_linear", features=[[0, 0], [1, 1], [2, 2]],
                    targets=[0, 1, 2], fit_intercept=True)
        keys = text_list(show(f"call keys of with collection = ({body})"))
        self.assertEqual(keys, ["version", "kind", "fitted", "predict",
                                "parameters", "state"])
        self.assertEqual(show(f"item \"kind\" of ({body})"), "linear_regression")
        self.assertEqual(show(f"item \"version\" of ({body})"), "1")
        self.assertEqual(show(f"item \"fitted\" of ({body})"), "true")
        builtin = run(program(
            f"set m to {body}\n"
            "show call predict with model = m, features = (a list of (a list of 1, 1))"))
        qualified = run(program(
            f"set m to {body}\n"
            f"show call predict from {ML} with model = m, "
            "features = (a list of (a list of 1, 1))"))
        self.assertEqual(builtin, qualified)
        almost(numeric(builtin[0]), [1.0])

    def test_fit_linear_pinned_collinear_example(self):
        body = call("fit_linear", features=[[0, 0], [1, 1], [2, 2]],
                    targets=[0, 1, 2], fit_intercept=True)
        almost(model_state(body, "coefficients"), [0.5, 0.5])
        almost(model_state(body, "intercept"), 0.0)
        pred = show(f"call predict with model = ({body}), "
                    "features = (a list of (a list of 1, 1))")
        almost(numeric(pred), [1.0])

    def test_fit_linear_matches_sklearn(self):
        cases = [
            ([[1, 2], [2, 3], [3, 1], [4, 5]], [1, 2, 3, 6], True),
            ([[1, 2], [2, 3], [3, 1], [4, 5]], [1, 2, 3, 6], False),
            ([[1, 2, 3], [2, 1, 4], [3, 3, 1], [4, 2, 2], [5, 5, 5]],
             [2, 3, 5, 4, 9], True),
            ([[-1, 2], [0, -3], [2, 1], [4, 0]], [-2, 1, 5, 7], True),
        ]
        for features, targets, intercept in cases:
            sklearn_model = LinearRegression(fit_intercept=intercept).fit(
                features, targets)
            body = call("fit_linear", features=features, targets=targets,
                        fit_intercept=intercept)
            almost(model_state(body, "coefficients"), sklearn_model.coef_)
            almost(model_state(body, "intercept"), float(sklearn_model.intercept_))
            queries = [[2, 1], [0, 4]] if len(features[0]) == 2 else [[2, 1, 4]]
            predictions = show(f"call predict with model = ({body}), "
                               f"features = {lit(queries)}")
            almost(numeric(predictions), sklearn_model.predict(queries).tolist())

    def test_gradient_approaches_closed_form(self):
        features = [[0], [1], [2], [3]]
        targets = [1, 3, 5, 7]
        body = call("gradient", features=features, targets=targets,
                    rate=0.1, steps=1000, fit_intercept=True)
        almost(model_state(body, "coefficients"), [2.0], abs_tol=1e-3, rel_tol=1e-3)
        almost(model_state(body, "intercept"), 1.0, abs_tol=1e-3, rel_tol=1e-3)
        no_intercept = call("gradient", features=features, targets=targets,
                            rate=0.1, steps=10, fit_intercept=False)
        almost(model_state(no_intercept, "intercept"), 0.0)

    # --- split and scaling ------------------------------------------------

    def test_split_is_seeded_disjoint_and_sized(self):
        values = list(range(10))
        body = call("split", features=[[v] for v in values], labels=values,
                    test_size=0.3, seed=0)
        train = numeric(show(f"item \"train_labels\" of ({body})"))
        test = numeric(show(f"item \"test_labels\" of ({body})"))
        self.assertEqual(len(train), 7)
        self.assertEqual(len(test), 3)
        self.assertEqual(sorted(train + test), values)
        self.assertFalse(set(train) & set(test))
        again = numeric(show(f"item \"test_labels\" of ({call('split', features=[[v] for v in values], labels=values, test_size=0.3, seed=0)})"))
        self.assertEqual(again, test)
        different = numeric(show(f"item \"test_labels\" of ({call('split', features=[[v] for v in values], labels=values, test_size=0.3, seed=1)})"))
        self.assertNotEqual(different, test)
        for fraction in (0.1, 0.25, 0.5):
            sklearn_train, sklearn_test = train_test_split(
                values, test_size=fraction, random_state=0)
            parts = call("split", features=[[v] for v in values], labels=values,
                         test_size=fraction, seed=0)
            train_part = numeric(show(f"item \"train_labels\" of ({parts})"))
            test_part = numeric(show(f"item \"test_labels\" of ({parts})"))
            self.assertEqual(len(test_part), len(sklearn_test))
            self.assertEqual(len(train_part), len(sklearn_train))
            self.assertEqual(sorted(train_part + test_part), values)

    def test_standardize_matches_sklearn(self):
        cases = [
            [[1, -1, 2], [2, 0, 0], [0, 1, -1]],
            [[5, 2], [5, 4], [5, -2]],
            [[-3, 1.5], [0, 2.5], [4, -0.5]],
        ]
        for features in cases:
            expected = StandardScaler().fit(features)
            body = call("standardize", features=features,
                        with_mean=True, with_std=True)
            almost(model_state(body, "mean"), expected.mean_.tolist())
            almost(model_state(body, "scale"), expected.scale_.tolist())
            transformed = show(f"call transform from {ML} with model = ({body}), "
                               f"features = {lit(features)}")
            almost(numeric(transformed), expected.transform(features).tolist())
            builtin = show(f"call predict with model = ({body}), "
                           f"features = {lit(features)}")
            self.assertEqual(builtin, transformed)

    def test_standardize_flags(self):
        features = [[1, 2], [3, 4], [5, 6]]
        expected = StandardScaler(with_mean=False, with_std=False).fit(features)
        body = call("standardize", features=features,
                    with_mean=False, with_std=False)
        almost(model_state(body, "mean"), [0.0, 0.0])
        almost(model_state(body, "scale"), [1.0, 1.0])

    # --- neighbours -------------------------------------------------------

    def test_neighbours_classification_tie_goes_to_lowest_label(self):
        body = call("neighbours", features=[[0], [2]], labels=[1, 0], k=2,
                    task="classify", weights="uniform", seed=0)
        predictions = show(f"call predict with model = ({body}), "
                           "features = (a list of (a list of 1))")
        self.assertEqual(numeric(predictions), [0])
        sklearn_model = KNeighborsClassifier(n_neighbors=2).fit(
            [[0], [2]], [1, 0])
        self.assertEqual(sklearn_model.predict([[1]]).tolist(), [0])

    def test_neighbours_distance_weights_exact_match(self):
        body = call("neighbours", features=[[0], [2], [4]], labels=[1, 0, 1],
                    k=2, task="classify", weights="distance", seed=0)
        predictions = show(f"call predict with model = ({body}), "
                           "features = (a list of (a list of 0))")
        self.assertEqual(numeric(predictions), [1])
        sklearn_model = KNeighborsClassifier(
            n_neighbors=2, weights="distance").fit([[0], [2], [4]], [1, 0, 1])
        self.assertEqual(sklearn_model.predict([[0]]).tolist(), [1])

    def test_neighbours_matches_sklearn(self):
        features = [[0, 0], [1, 1], [2, 0], [5, 5], [6, 4], [7, 6]]
        queries = [[1, 0], [4, 4], [6, 5]]
        for k in (1, 3):
            for weights in ("uniform", "distance"):
                sklearn_model = KNeighborsClassifier(
                    n_neighbors=k, weights=weights).fit(features, [0, 0, 1, 1, 2, 2])
                body = call("neighbours", features=features,
                            labels=[0, 0, 1, 1, 2, 2], k=k, task="classify",
                            weights=weights, seed=0)
                predictions = show(f"call predict with model = ({body}), "
                                   f"features = {lit(queries)}")
                self.assertEqual(numeric(predictions),
                                 sklearn_model.predict(queries).tolist())
        regression = KNeighborsRegressor(n_neighbors=2).fit(
            [[0], [1], [2], [3]], [0, 10, 20, 30])
        body = call("neighbours", features=[[0], [1], [2], [3]],
                    labels=[0, 10, 20, 30], k=2, task="regress",
                    weights="uniform", seed=0)
        predictions = show(f"call predict with model = ({body}), "
                           "features = (a list of (a list of 1.5))")
        almost(numeric(predictions), regression.predict([[1.5]]).tolist())

    # --- clustering -------------------------------------------------------

    def test_cluster_matches_sklearn(self):
        cases = [
            ([[0, 0], [1, 1], [8, 8], [9, 9], [1, 0], [9, 8]], 2, 0),
            ([[0, 0], [1, 1], [8, 8], [9, 9], [1, 0], [9, 8]], 2, 1),
            ([[0, 0, 0], [1, 1, 0], [8, 8, 1], [9, 9, 1], [0, 1, 0], [9, 8, 1]],
             3, 42),
        ]
        for features, clusters, seed in cases:
            sklearn_model = KMeans(n_clusters=clusters, random_state=seed,
                                   n_init=10).fit(features)
            body = call("kmeans", features=features, clusters=clusters,
                        seed=seed, restarts=10, init="kmeans_plus_plus")
            state_inertia = numeric(show(f"item \"inertia\" of (item \"state\" of ({body}))"))
            state_labels = numeric(show(f"item \"labels\" of (item \"state\" of ({body}))"))
            almost(state_inertia, float(sklearn_model.inertia_), abs_tol=1e-6,
                   rel_tol=1e-7)
            self.assertEqual(adjusted_rand_score(state_labels,
                                                 sklearn_model.labels_), 1.0)
            assigned = numeric(show(f"call predict with model = ({body}), "
                                    f"features = {lit(features)}"))
            self.assertEqual(assigned, state_labels)

    # --- metrics ----------------------------------------------------------

    def test_metric_pins(self):
        self.assertEqual(show(call("accuracy", actual=[0, 2, 1, 3],
                                   predicted=[0, 1, 2, 3])), "0.5")
        self.assertEqual(show(call("accuracy_count", actual=[0, 2, 1, 3],
                                   predicted=[0, 1, 2, 3])), "2.0")
        actual, predicted = [3, -0.5, 2, 7], [2.5, 0, 2, 8]
        almost(numeric(show(call("mse", actual=actual, predicted=predicted))), 0.375)
        almost(numeric(show(call("rmse", actual=actual, predicted=predicted))),
               math.sqrt(0.375))
        almost(numeric(show(call("mae", actual=actual, predicted=predicted))), 0.5)
        almost(numeric(show(call("r2", actual=actual, predicted=predicted))),
               0.9486081370449679)

    def test_metrics_match_sklearn(self):
        actual, predicted = [3, -0.5, 2, 7], [2.5, 0, 2, 8]
        cases = [(actual, predicted), ([1, 2, 3, 4], [1, 2, 3, 4]),
                 ([0, 0, 0, 0], [1, 2, 3, 4]), ([0, 0, 0, 0], [0, 0, 0, 0])]
        for truth, guess in cases:
            almost(numeric(show(call("mse", actual=truth, predicted=guess))),
                   float(mean_squared_error(truth, guess)))
            almost(numeric(show(call("rmse", actual=truth, predicted=guess))),
                   float(root_mean_squared_error(truth, guess)))
            almost(numeric(show(call("mae", actual=truth, predicted=guess))),
                   float(mean_absolute_error(truth, guess)))
            almost(numeric(show(call("r2", actual=truth, predicted=guess))),
                   float(r2_score(truth, guess)))

    def test_classification_metrics_match_sklearn(self):
        cases = [
            ([0, 0, 1, 1], [0, 1, 1, 1], 1),
            ([0, 0, 0, 1], [0, 0, 1, 1], 1),
            ([1, 1, 1, 1], [1, 1, 1, 1], 1),
            ([0, 0, 0, 0], [1, 1, 1, 1], 1),
        ]
        for truth, guess, positive in cases:
            almost(numeric(show(call("precision", actual=truth, predicted=guess,
                                     positive=positive))),
                   float(precision_score(truth, guess, zero_division=0)))
            almost(numeric(show(call("recall", actual=truth, predicted=guess,
                                     positive=positive))),
                   float(recall_score(truth, guess, zero_division=0)))
            almost(numeric(show(call("f1", actual=truth, predicted=guess,
                                     positive=positive))),
                   float(f1_score(truth, guess, zero_division=0)))
            almost(numeric(show(call("accuracy", actual=truth, predicted=guess))),
                   float(accuracy_score(truth, guess)))
        truth, guess = [0, 0, 1, 1], [0, 1, 1, 1]
        matrix = numeric(show(call("confusion", actual=truth, predicted=guess,
                                   classes=[0, 1])))
        self.assertEqual(matrix, {0: [1, 1], 1: [0, 2]})
        self.assertEqual(confusion_matrix(truth, guess).ravel().tolist(),
                         [1, 1, 0, 2])

    def test_multiclass_f1_averages(self):
        truth, guess = [0, 1, 2], [0, 2, 1]
        for fn, average in (("f1_macro", "macro"), ("f1_micro", "micro"),
                            ("f1_weighted", "weighted")):
            almost(numeric(show(call(fn, actual=truth, predicted=guess))),
                   float(f1_score(truth, guess, average=average)), abs_tol=1e-9)
            self.assertAlmostEqual(
                f1_score(truth, guess, average=average), 1 / 3, places=9)

    def test_distance_and_column(self):
        almost(numeric(show(call("distance", left=[0, 0], right=[3, 4]))), 5.0)
        self.assertEqual(numeric(show(call("column", rows=[[1, 2], [3, 4]],
                                           index=1))), [2, 4])

    # --- workflows and failures -------------------------------------------

    def test_evaluate_and_report(self):
        fitted = call("fit_linear", features=[[1], [2], [3], [4]],
                      targets=[2, 4, 6, 8], fit_intercept=True)
        scores = (f"call evaluate from {ML} with model = ({fitted}), "
                  f"features = {lit([[1], [2], [3], [4]])}, "
                  f"actual = {lit([2, 4, 6, 8])}")
        keys = text_list(show(f"call keys of with collection = ({scores})"))
        self.assertEqual(keys, ["mse", "rmse", "mae", "r2"])
        text = show(f"call report from {ML} with scores = ({scores})")
        self.assertIn("mse=", text)
        self.assertIn("r2=1.0", text)

    def test_problem_kinds_are_loud(self):
        cases = [
            (call("split", features=[[1], [2]], labels=[1, 2],
                  test_size=1.5, seed=0), "bad_test_size"),
            (call("split", features=[[1]], labels=[1],
                  test_size=0.5, seed=0), "too_few_samples"),
            (call("standardize", features=[[1], [2, 3]],
                  with_mean=True, with_std=True), "inconsistent_width"),
            (call("standardize", features=[["x"]], with_mean=True,
                  with_std=True), "non_numeric_feature"),
            (call("neighbours", features=[[1]], labels=[0], k=3,
                  task="classify", weights="uniform", seed=0),
             "too_many_neighbors"),
            (call("kmeans", features=[[1], [2]], clusters=3, seed=0,
                  restarts=2, init="first_rows"), "too_many_clusters"),
            (call("mse", actual=[], predicted=[]), "bad_metric_input"),
            ("set m to " + call("fit_linear", features=[[1]], targets=[1],
                                fit_intercept=True) + "\n"
             + "set item \"fitted\" of m to false\n"
             + "show call predict with model = m, features = (a list of (a list of 1))",
             "not_fitted"),
        ]
        for expression, kind in cases:
            with self.subTest(kind=kind):
                with self.assertRaises(LangError) as context:
                    run(program(expression if "\n" in expression
                                else "show " + expression))
                self.assertIn(kind, str(context.exception))
                self.assertIn("ml_error/", str(context.exception))

    def test_differential_harness(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "compare_ml.py")],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        timeout=300)
        self.assertEqual(completed.returncode, 0,
                         f"{completed.stdout}\n{completed.stderr}")
        self.assertIn("0 mismatches", completed.stdout)


if __name__ == "__main__":
    unittest.main()
