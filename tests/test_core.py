"""Core tests. Run with: python -m unittest discover -s tests -v"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llang import LangError, run_source  # noqa: E402


class SynonymTests(unittest.TestCase):
    def test_output_synonyms_are_identical(self):
        outputs = []
        for word in ("show", "display", "print"):
            outputs.append(run_source(f'{word} "Hello"').output)
        self.assertEqual(outputs, [["Hello"]] * 3)

    def test_assignment_synonyms_are_identical(self):
        a = run_source('set x to 2\nlet y be 2\nshow x plus y').output
        self.assertEqual(a, ["4"])

    def test_comparison_synonyms_are_identical(self):
        results = []
        for phrase in ("is greater than", "is more than", "exceeds"):
            results.append(run_source(
                f'if 5 {phrase} 3 then\n  show "yes"\nend if').output)
        self.assertEqual(results, [["yes"]] * 3)


class ExpressionTests(unittest.TestCase):
    def test_left_to_right_no_precedence(self):
        self.assertEqual(run_source("set x to 2 plus 3 times 4\nshow x").output, ["20"])

    def test_parentheses_override(self):
        self.assertEqual(run_source("set x to 2 plus (3 times 4)\nshow x").output, ["14"])

    def test_strict_types(self):
        with self.assertRaises(LangError):
            run_source('show "a" minus "b"')

    def test_no_implicit_coercion(self):
        with self.assertRaises(LangError):
            run_source('show "5" plus 5')


class ControlFlowTests(unittest.TestCase):
    def test_if_otherwise_if_otherwise(self):
        source = """
set x to 5
if x is greater than 10 then
    show "big"
otherwise if x equals 5 then
    show "five"
otherwise
    show "small"
end if
"""
        self.assertEqual(run_source(source).output, ["five"])

    def test_repeat_while(self):
        source = """
set counter to 0
repeat while counter is less than 3
    show counter
    set counter to counter plus 1
end repeat
"""
        self.assertEqual(run_source(source).output, ["0", "1", "2"])

    def test_explicit_delimiters_required(self):
        with self.assertRaises(LangError):
            run_source("if true then\nshow \"yes\"")


class FunctionTests(unittest.TestCase):
    def test_function_aliases(self):
        source = """
define function greet taking name
also known as say_hello, welcome
    give back "Hello, " plus name
end function

call greet with name = "Ada"
call say_hello with name = "Grace"
show call welcome with name = "Linus"
"""
        self.assertEqual(run_source(source).output, ["Hello, Linus"])

    def test_labeled_arguments_are_required(self):
        source = """
define function add taking a, b
    give back a plus b
end function
show call add with a = 1
"""
        with self.assertRaises(LangError):
            run_source(source)

    def test_alias_collision_rejected(self):
        source = """
set welcome to 1
define function greet taking name
also known as welcome
    give back name
end function
"""
        with self.assertRaises(LangError):
            run_source(source)


class DiagnosticTests(unittest.TestCase):
    def test_undefined_name_has_message(self):
        with self.assertRaises(LangError) as ctx:
            run_source("show missing")
        self.assertIn("Undefined name 'missing'", str(ctx.exception))

    def test_error_has_source_location(self):
        with self.assertRaises(LangError) as ctx:
            run_source("# comment\nshow (\"x\" minus 1)")
        self.assertIn("line 2", str(ctx.exception))

    def test_reserved_word_cannot_be_identifier(self):
        with self.assertRaises(LangError):
            run_source("set end to 5")

    def test_reserved_word_error_suggests_escape(self):
        for source in ("set next to 5", "show list", "set item map of xs to 1"):
            with self.subTest(source=source), self.assertRaises(LangError) as ctx:
                run_source(source)
            self.assertIn("is a reserved word; write @", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
