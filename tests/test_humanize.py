"""The llang rewrite of humanize's number formatters, verified against Python."""

import io
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang import LangError, Lexer, Parser, Interpreter  # noqa: E402


def run(source):
    interpreter = Interpreter(library_paths=[ROOT / "lib"])
    with redirect_stdout(io.StringIO()):
        interpreter.run(Parser(Lexer(source).tokenize()).parse_program())
    return interpreter.output


def call_line(expression):
    return run("use the humanize module\nshow " + expression)


class HumanizeRewriteTests(unittest.TestCase):
    def test_intcomma(self):
        self.assertEqual(call_line('call intcomma from humanize with value = 1234567, ndigits = nothing'), ["1,234,567"])
        self.assertEqual(call_line('call intcomma from humanize with value = "1,000", ndigits = nothing'), ["1,000"])
        self.assertEqual(call_line('call intcomma from humanize with value = (0 minus 4096), ndigits = nothing'),
                         ["-4,096"])

    def test_intcomma_precision(self):
        self.assertEqual(
            call_line('call intcomma from humanize with value = 1234.5454545, ndigits = 2'),
            ["1,234.55"],
        )
        self.assertEqual(
            call_line('call intcomma from humanize with value = 100, ndigits = 2'),
            ["100.00"],
        )

    def test_apnumber(self):
        self.assertEqual(call_line('call apnumber from humanize with value = 7'), ["seven"])
        self.assertEqual(call_line('call apnumber from humanize with value = 10'), ["10"])
        self.assertEqual(call_line('call apnumber from humanize with value = "foo"'), ["foo"])

    def test_ordinal(self):
        for value, expected in ((1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"),
                                (12, "12th"), (101, "101st"), (111, "111th"),
                                (1002, "1002nd"), (103, "103rd")):
            with self.subTest(value=value):
                self.assertEqual(
                    call_line(f'call ordinal from humanize with value = {value}, gender = "male"'),
                    [expected],
                )

    def test_intword(self):
        self.assertEqual(call_line('call intword from humanize with value = "12400", fmt = "%.1f"'),
                         ["12.4 thousand"])
        self.assertEqual(call_line('call intword from humanize with value = 1000000, fmt = "%.1f"'),
                         ["1.0 million"])
        self.assertEqual(
            call_line('call intword from humanize with value = (1000000000000000000000000 minus 1), fmt = "%.1f"'),
            ["1.0 septillion"],
        )

    def test_scientific(self):
        self.assertEqual(call_line('call scientific from humanize with value = 0.3, precision = 2'),
                         ["3.00 x 10⁻¹"])
        self.assertEqual(call_line('call scientific from humanize with value = (0 minus 1000), precision = 2'),
                         ["-1.00 x 10³"])
        self.assertEqual(call_line('call scientific from humanize with value = 0, precision = 2'),
                         ["0.00 x 10⁰"])

    def test_naturalsize(self):
        self.assertEqual(call_line('call naturalsize from humanize with value = 3000000, binary = false, gnu = false, fmt = "%.1f"'),
                         ["3.0 MB"])
        self.assertEqual(call_line('call naturalsize from humanize with value = 999999, binary = false, gnu = false, fmt = "%.1f"'),
                         ["1.0 MB"])
        self.assertEqual(call_line('call naturalsize from humanize with value = 3000, binary = true, gnu = false, fmt = "%.1f"'),
                         ["2.9 KiB"])
        self.assertEqual(call_line('call naturalsize from humanize with value = 3000, binary = false, gnu = true, fmt = "%.1f"'),
                         ["2.9K"])

    def test_metric(self):
        self.assertEqual(call_line('call metric from humanize with value = 1500, unit = "V", precision = 3'),
                         ["1.50 kV"])
        self.assertEqual(call_line('call metric from humanize with value = (220 divided by 1000000), unit = "F", precision = 3'),
                         ["220 μF"])
        self.assertEqual(call_line('call metric from humanize with value = (1 divided by (10 to the power of 14)), unit = "", precision = 4'),
                         ["10.00 f"])
        self.assertEqual(call_line('call metric from humanize with value = (10 to the power of 40), unit = "", precision = 3'),
                         ["1.00 x 10⁴⁰"])

    def test_describe_is_a_self_describing_map(self):
        self.assertEqual(
            run('use the humanize module\nshow item "apnumber" of (call describe from humanize with value = 7)'),
            ["seven"],
        )

    def test_invalid_types_fail_loudly(self):
        for expression in (
            'call intcomma from humanize with value = nothing, ndigits = nothing',
            'call apnumber from humanize with value = (a list of 1, 2)',
            'call ordinal from humanize with value = 1, gender = 123',
            'call scientific from humanize with value = 1, precision = (0 minus 1)',
            'call naturalsize from humanize with value = 1, binary = "yes", gnu = false, fmt = "%.1f"',
            'call metric from humanize with value = "1500", unit = "", precision = 3',
        ):
            with self.subTest(expression=expression):
                with self.assertRaises(LangError) as ctx:
                    run("use the humanize module\nshow " + expression)
                self.assertIn("format_error", str(ctx.exception))

    def test_nonfinite_inputs_match_humanize(self):
        self.assertEqual(call_line('call intcomma from humanize with value = "nan", ndigits = nothing'),
                         ["NaN"])
        self.assertEqual(call_line('call apnumber from humanize with value = "-Inf"'),
                         ["-Inf"])
        self.assertEqual(call_line('call scientific from humanize with value = "inf", precision = 2'),
                         ["+Inf"])

    def test_lint_has_no_errors(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "run.py"), "--lint", str(ROOT / "lib" / "humanize.ll")],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        timeout=300)
        self.assertEqual(completed.returncode, 0, f"{completed.stdout}\n{completed.stderr}")
        self.assertEqual(completed.stdout.strip(), "")

    def test_matches_python_corpus(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "compare_humanize.py")],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        timeout=300)
        self.assertEqual(completed.returncode, 0,
                         f"{completed.stdout}\n{completed.stderr}")
        self.assertIn("227 cases, 0 mismatches", completed.stdout)


if __name__ == "__main__":
    unittest.main()
