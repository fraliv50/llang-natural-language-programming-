"""Property-based differential fuzz tests for llang expression semantics.

Run with: python -m unittest discover -s tests -v

The fuzzer itself lives in tools/fuzz_semantics.py; these tests exercise its
core comparison function on small deterministic corpora and verify that a
deliberately broken comparison is reported rather than silently passing.
"""

import importlib.util
import random
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))


def _load_fuzzer():
    path = ROOT / "tools" / "fuzz_semantics.py"
    spec = importlib.util.spec_from_file_location("fuzz_semantics", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fuzz_semantics = _load_fuzzer()


class FuzzSemanticsTests(unittest.TestCase):
    def test_fixed_corpus_has_no_mismatches(self):
        report = fuzz_semantics.fuzz(seed=2026, count=50)
        self.assertGreater(report.compared, 0)
        self.assertEqual(report.mismatches, 0,
                         [item.reason for item in report.examples])

    def test_seed_is_reproducible(self):
        first = fuzz_semantics.fuzz(seed=99, count=50)
        second = fuzz_semantics.fuzz(seed=99, count=50)
        self.assertEqual(
            (first.compared, first.mismatches, first.skipped),
            (second.compared, second.mismatches, second.skipped),
        )

        def cases(seed):
            rng = random.Random(seed)
            return [fuzz_semantics.generate_case(rng) for _ in range(20)]

        self.assertEqual(cases(1234), cases(1234))

    def test_boolean_normalization(self):
        match = fuzz_semantics.values_match
        self.assertTrue(match(True, ["true"]))
        self.assertTrue(match(False, ["false"]))
        self.assertTrue(match(7, ["7"]))
        self.assertTrue(match(-3, ["-3"]))
        self.assertFalse(match(True, ["1"]))
        self.assertFalse(match(7, ["8"]))
        self.assertFalse(match(True, ["True"]))

    def test_division_by_zero_is_skipped(self):
        case = fuzz_semantics.ExpressionCase("(5 % 0)", "(5 modulo 0)", "int")
        result = fuzz_semantics.evaluate_case(case)
        self.assertTrue(result.skipped)
        self.assertIn("division by zero", result.reason)

        report = fuzz_semantics.fuzz(seed=1729, count=100)
        self.assertGreaterEqual(report.skipped, 0)
        self.assertEqual(report.count, 100)

    def test_deliberately_broken_comparison_is_detected(self):
        # A case whose llang source does not match its Python source must be
        # flagged as a mismatch, exercising the real evaluation pipeline.
        broken = fuzz_semantics.ExpressionCase("(1 + 2)", "(1 minus 2)", "int")
        result = fuzz_semantics.evaluate_case(broken)
        self.assertFalse(result.match)
        self.assertFalse(result.skipped)
        self.assertEqual(result.python_value, 3)
        self.assertEqual(result.llang_output, ["-1"])
        self.assertIn("python", result.reason)

        # The comparison helper must also reject a wrong expected value.
        self.assertFalse(fuzz_semantics.values_match(3, ["-1"]))

    def test_mismatches_are_counted_by_fuzz(self):
        def always_wrong(case):
            return fuzz_semantics.Comparison(
                case, python_value=1, llang_output=["2"], match=False
            )

        with mock.patch.object(fuzz_semantics, "evaluate_case",
                               side_effect=always_wrong):
            report = fuzz_semantics.fuzz(seed=7, count=5)

        self.assertEqual(report.compared, 5)
        self.assertEqual(report.mismatches, 5)
        self.assertEqual(report.skipped, 0)
        self.assertEqual(len(report.examples), 5)


if __name__ == "__main__":
    unittest.main()
