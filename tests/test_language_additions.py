"""Tests for the language additions that unblocked the bisect port."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llang import LangError, run_source  # noqa: E402


class LanguageAdditionTests(unittest.TestCase):
    def test_slice(self):
        out = run_source("""
set xs to a list of 1, 2, 3, 4
show call slice with collection = xs, start = 1, finish = 3
show call slice with collection = "hello", start = 1, finish = nothing
""").output
        self.assertEqual(out, ["[2, 3]", "ello"])

    def test_all_builtin_labels_are_writable(self):
        from llang.interpreter import BUILTIN_SPECS
        from llang.synonyms import RESERVED
        for name, (required, optional) in BUILTIN_SPECS.items():
            for label in required + optional:
                self.assertNotIn(label, RESERVED, f"{name} uses reserved label {label}")

    def test_floor_division(self):
        out = run_source("""
show 7 floor divided by 2
show 0 minus 7 floor divided by 2
show 8 floor divided by 2
""").output
        self.assertEqual(out, ["3", "-4", "4"])

    def test_power_by_zero_is_localized(self):
        with self.assertRaises(LangError) as ctx:
            run_source("show 0 to the power of (0 minus 1)")
        self.assertIn("Power by zero", str(ctx.exception))

    def test_unbounded_recursion_is_localized(self):
        with self.assertRaises(LangError) as ctx:
            run_source("""
define function forever taking n
    give back call forever with n = n
end function
show call forever with n = 1
""")
        self.assertIn("recursion", str(ctx.exception).lower())

    def test_complex_power_is_rejected(self):
        with self.assertRaises(LangError) as ctx:
            run_source("show 0 minus 8 to the power of (1 divided by 3)")
        self.assertIn("no real result", str(ctx.exception))

    def test_power_overflow_is_localized(self):
        with self.assertRaises(LangError) as ctx:
            run_source("show 10.0 to the power of 1000")
        self.assertIn("overflow", str(ctx.exception).lower())

    def test_floor_division_by_zero(self):
        with self.assertRaises(LangError):
            run_source("show 7 floor divided by 0")

    def test_insert_into(self):
        out = run_source("""
set xs to a list of 1, 3
call insert into with collection = xs, index = 1, value = 2
show xs
call insert into with collection = xs, index = 0, value = 0
show xs
""").output
        self.assertEqual(out, ["[1, 2, 3]", "[0, 1, 2, 3]"])

    def test_insert_out_of_range(self):
        with self.assertRaises(LangError):
            run_source("""
set xs to a list of 1
call insert into with collection = xs, index = 5, value = 2
""")

    def test_apply_calls_function_value(self):
        out = run_source("""
define function double taking value
    give back value times 2
end function
show call apply with fn = double, args = (a list of 21)
""").output
        self.assertEqual(out, ["42"])

    def test_predict_calls_model_function(self):
        out = run_source("""
define function predict_doubler taking model, features
    set factor to item "factor" of model
    give back features times factor
end function
set model to an empty map
set item "factor" of model to 3
set item "predict" of model to predict_doubler
show call predict with model = model, features = 7
""").output
        self.assertEqual(out, ["21"])

    def test_apply_arity_error(self):
        with self.assertRaises(LangError):
            run_source("""
define function double taking value
    give back value times 2
end function
show call apply with fn = double, args = (a list of 1, 2)
""")

    def test_apply_requires_function(self):
        with self.assertRaises(LangError):
            run_source("call apply with fn = 5, args = (a list of 1)")


if __name__ == "__main__":
    unittest.main()
