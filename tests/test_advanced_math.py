"""The native llang advanced math library, verified against math/statistics."""

import contextlib
import io
import math
import statistics
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang import LangError, Lexer, Parser, Interpreter  # noqa: E402


def run(source):
    interpreter = Interpreter(library_paths=[ROOT / "lib"])
    with contextlib.redirect_stdout(io.StringIO()):
        interpreter.run(Parser(Lexer(source).tokenize()).parse_program())
    return interpreter.output


def show(expression):
    return run("use the advanced_math module\nshow " + expression)


def caught(expression, kind):
    source = (
        "use the advanced_math module\n"
        "expect\n"
        f"    show {expression}\n"
        f"if a problem of kind {kind} occurs then\n"
        f'    show "{kind}"\n'
        "end expect\n"
    )
    return run(source)


class AdvancedMathTests(unittest.TestCase):
    # --- correctly rounded primitives -----------------------------------
    def test_squareroot_is_always_float_and_has_alias(self):
        self.assertEqual(show("call squareroot from advanced_math with value = 81"),
                         ["9.0"])
        self.assertEqual(show("call sqrt from advanced_math with value = 81"),
                         ["9.0"])
        self.assertEqual(show("call squareroot from advanced_math with value = 2")[:1],
                         [str(math.sqrt(2))])

    def test_exponential_and_logarithms(self):
        self.assertEqual(show("call exponential from advanced_math with power = 0"),
                         ["1.0"])
        self.assertEqual(show("call logarithm from advanced_math with value = 1"),
                         ["0.0"])
        self.assertEqual(show("call logtwo from advanced_math with value = 8"),
                         ["3.0"])
        self.assertAlmostEqual(
            float(show("call logten from advanced_math with value = 1000")[0]),
            3.0, places=12,
        )
        self.assertEqual(
            show("call logbase from advanced_math with value = 8, base = 2"),
            ["3.0"],
        )
        self.assertAlmostEqual(
            float(show("call exponential from advanced_math with power = 2.5")[0]),
            math.exp(2.5), places=12,
        )

    def test_overflow_is_caught_not_leaked(self):
        self.assertEqual(
            caught("call exponential from advanced_math with power = 1000",
                   "math_overflow"),
            ["math_overflow"],
        )

    # --- exact integers --------------------------------------------------
    def test_gcd_lcm_factorial(self):
        self.assertEqual(show("call gcd from advanced_math with values = (an empty list)"),
                         ["0"])
        self.assertEqual(show("call gcd from advanced_math with values = (a list of 12, 18, 30)"),
                         ["6"])
        self.assertEqual(show("call lcm from advanced_math with values = (an empty list)"),
                         ["1"])
        self.assertEqual(show("call lcm from advanced_math with values = (a list of (0 minus 4), 6)"),
                         ["12"])
        self.assertEqual(show("call factorial from advanced_math with number = 0"),
                         ["1"])
        self.assertEqual(show("call factorial from advanced_math with number = 20"),
                         [str(math.factorial(20))])
        self.assertEqual(show("call factorial from advanced_math with number = 100"),
                         [str(math.factorial(100))])

    def test_rounding(self):
        for name, expression, expected in (
            ("floor", "2.7", 2),
            ("floor", "(0 minus 2.7)", -3),
            ("ceil", "(0 minus 2.7)", -2),
            ("trunc", "(0 minus 2.7)", -2),
            ("trunc", "2.7", 2),
        ):
            with self.subTest(name=name, expression=expression):
                self.assertEqual(
                    show(f"call {name} from advanced_math with value = {expression}"),
                    [str(expected)],
                )

    # --- statistics ------------------------------------------------------
    def test_statistics_match_stdlib(self):
        cases = [
            ("mean", [1, 2, 3], 2),
            ("median", [1, 3, 5, 7], 4.0),
            ("median", [1, 3, 5], 3),
            ("mode", [1, 1, 2, 2], 1),
            ("variance", [1, 2, 3, 4], statistics.variance([1, 2, 3, 4])),
            ("stdev", [1, 2, 3, 4], statistics.stdev([1, 2, 3, 4])),
            ("pvariance", [1, 2, 3, 4], statistics.pvariance([1, 2, 3, 4])),
            ("pstdev", [1, 2, 3, 4], statistics.pstdev([1, 2, 3, 4])),
        ]
        for name, values, expected in cases:
            with self.subTest(name=name, values=values):
                literal = "(a list of " + ", ".join(map(str, values)) + ")"
                actual = show(f"call {name} from advanced_math with values = {literal}")
                self.assertEqual(float(actual[0]), float(expected))
                if isinstance(expected, int):
                    self.assertEqual(actual[0], str(expected))

    def test_mode_supports_text_and_first_tie(self):
        self.assertEqual(
            show('call mode from advanced_math with values = (a list of "a", "b", "a")'),
            ["a"],
        )

    def test_summarize_returns_stable_map(self):
        self.assertEqual(
            show("call summarize from advanced_math with values = (a list of 72, 88, 91, 65)"),
            ["{value: 79, median: 80.0, kind: summary, exact: false, "
             "count: 4, stdev: 12.516655570345725}"],
        )

    # --- distance, summation, predicates and trig -------------------------
    def test_hypot_distance_and_precisesum(self):
        self.assertEqual(show("call hypot from advanced_math with coordinates = (an empty list)"),
                         ["0.0"])
        self.assertEqual(show("call hypot from advanced_math with coordinates = (a list of 3, 4, 12)"),
                         ["13.0"])
        self.assertEqual(show("call distance from advanced_math with frompoint = (a list of 0, 0, 0), topoint = (a list of 3, 4, 12)"),
                         ["13.0"])
        self.assertEqual(
            show("call precisesum from advanced_math with values = "
                 "(a list of 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1)"),
            ["1.0"],
        )

    def test_approxequal(self):
        self.assertEqual(
            show("call approxequal from advanced_math with left = 1.0, "
                 "right = 1.0000000001, reltol = (0.000000001), abstol = 0.0"),
            ["true"],
        )
        self.assertEqual(
            show("call approxequal from advanced_math with left = 1.0, "
                 "right = 1.1, reltol = (0.000000001), abstol = 0.0"),
            ["false"],
        )
        self.assertEqual(
            show("call nearlyequal from advanced_math with left = 1.0, right = 1.0"),
            ["true"],
        )

    def test_trig(self):
        self.assertEqual(show("call sine from advanced_math with angle = 0"), ["0.0"])
        self.assertEqual(show("call cosine from advanced_math with angle = 0"), ["1.0"])
        self.assertAlmostEqual(
            float(show("call sine from advanced_math with angle = 1")[0]),
            math.sin(1), places=12,
        )
        self.assertAlmostEqual(
            float(show("call cosine from advanced_math with angle = 1")[0]),
            math.cos(1), places=12,
        )

    # --- loud, catchable problem kinds -----------------------------------
    def test_error_kinds(self):
        kind_cases = [
            ("call squareroot from advanced_math with value = (0 minus 4)",
             "math_domain"),
            ("call logarithm from advanced_math with value = 0", "math_domain"),
            ("call factorial from advanced_math with number = (0 minus 1)",
             "math_domain"),
            ("call factorial from advanced_math with number = 5.0", "math_type"),
            ("call gcd from advanced_math with values = (a list of 5.0)",
             "math_type"),
            ("call mean from advanced_math with values = (an empty list)",
             "math_empty"),
            ("call variance from advanced_math with values = (a list of 1)",
             "math_length"),
            ("call distance from advanced_math with frompoint = (a list of 1, 2), "
             "topoint = (a list of 1)", "math_length"),
            ("call hypot from advanced_math with coordinates = "
             "(a list of (call to number with text = \"nan\"))", "math_domain"),
        ]
        for expression, kind in kind_cases:
            with self.subTest(expression=expression, kind=kind):
                self.assertEqual(caught(expression, kind), [kind])

    def test_unhandled_problem_renders_kind(self):
        with self.assertRaises(LangError) as ctx:
            show("call squareroot from advanced_math with value = (0 minus 1)")
        self.assertIn("math_domain", str(ctx.exception))

    def test_unknown_label_fails_loudly(self):
        with self.assertRaises(LangError) as ctx:
            show("call squareroot from advanced_math with amount = 9")
        self.assertIn("Unknown argument", str(ctx.exception))

    # --- project gates ---------------------------------------------------
    def test_lint_has_no_errors(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "run.py"), "--lint",
             str(ROOT / "lib" / "advanced_math.ll")],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        timeout=300)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertNotIn("error:", completed.stdout)

    def test_matches_cpython_corpus(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "compare_math.py")],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        timeout=300)
        self.assertEqual(completed.returncode, 0,
                         f"{completed.stdout}\n{completed.stderr}")
        self.assertIn("0 mismatches", completed.stdout)
        self.assertIn("lib/advanced_math.ll matches CPython math/statistics",
                      completed.stdout)


if __name__ == "__main__":
    unittest.main()
