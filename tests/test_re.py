"""Unit and differential tests for the native lib/re.ll engine."""

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang import LangError, Lexer, Parser, Interpreter  # noqa: E402


def run(source):
    interpreter = Interpreter(library_paths=[ROOT / "lib"])
    interpreter.run(Parser(Lexer(source).tokenize()).parse_program())
    return interpreter.output


def call_source(call, setup="use the re module\n"):
    return setup + "show " + call + "\n"


class ReModuleTests(unittest.TestCase):
    def test_match_is_prefix_only(self):
        self.assertEqual(
            run(call_source('call match from re with pattern = "cat", text = "concatenate"')),
            ["nothing"],
        )
        self.assertEqual(
            run(call_source('call search from re with pattern = "cat", text = "concatenate"')),
            ["{matched: cat, start: 3, end: 6, groups: [], named: {}}"],
        )

    def test_result_map_shape(self):
        output = run(call_source(
            'call find_all from re with pattern = "(\\\\w+)=(\\\\d+)", text = "x key=42 end"'
        ))
        self.assertEqual(
            output,
            ["[{matched: key=42, start: 2, end: 8, groups: [key, 42], named: {}}]"],
        )

    def test_nonparticipating_group_is_nothing(self):
        output = run(call_source(
            'call search from re with pattern = "(a)?b", text = "b"'
        ))
        self.assertEqual(
            output,
            ["{matched: b, start: 0, end: 1, groups: [nothing], named: {}}"],
        )

    def test_replace_with_backreferences(self):
        output = run(call_source(
            'call replace from re with pattern = "(\\\\w+)=(\\\\d+)", '
            'text = "key=42", replacement = "\\\\2:\\\\1"'
        ))
        self.assertEqual(output, ["42:key"])

    def test_replace_count_and_split_limit(self):
        output = run("""
use the re module
show call replace_count from re with pattern = "a", text = "a,a,a", replacement = "X", count = 1
show call split_limit from re with pattern = ",", text = "a,b,c", limit = 1
""")
        self.assertEqual(output, ["X,a,a", "[a, b,c]"])

    def test_flags_variants(self):
        output = run("""
use the re module
show call search_flags from re with pattern = "abc", text = "ABC", flags = (a list of "ignore case")
show call split_flags from re with pattern = "A", text = "a,b", flags = (a list of "ignore case")
""")
        self.assertEqual(output,
                         ["{matched: ABC, start: 0, end: 3, groups: [], named: {}}",
                          "[, ,b]"])

    def test_lazy_and_greedy(self):
        greedy = run(call_source(
            'call search from re with pattern = "<.*>", text = "<a> b <c>"'
        ))
        lazy = run(call_source(
            'call search from re with pattern = "<.*?>", text = "<a> b <c>"'
        ))
        self.assertEqual(greedy,
                         ["{matched: <a> b <c>, start: 0, end: 9, groups: [], named: {}}"])
        self.assertEqual(lazy,
                         ["{matched: <a>, start: 0, end: 3, groups: [], named: {}}"])

    def test_alternation_is_first_success(self):
        output = run(call_source(
            'call search from re with pattern = "a|ab", text = "ab"'
        ))
        self.assertEqual(output,
                         ["{matched: a, start: 0, end: 1, groups: [], named: {}}"])

    def test_empty_matches_are_reported(self):
        output = run(call_source(
            'call replace from re with pattern = "x*", text = "abxd", replacement = "-"'
        ))
        self.assertEqual(output, ["-a-b--d-"])

    # --- escape handling -------------------------------------------------

    def test_escape_matches_python(self):
        for text in ("https://www.python.org", "a+b(c)[d]{e}.f", "a b\tc\nd", ""):
            with self.subTest(text=text):
                source = call_source("call escape from re with text = " + repr(text))
                # Python repr uses single quotes; llang needs double quotes.
                source = source.replace(repr(text), '"' + text.replace("\\", "\\\\")
                                        .replace('"', '\\"').replace("\n", "\\n")
                                        .replace("\t", "\\t") + '"')
                self.assertEqual(run(source), [re.escape(text)])

    def test_doubled_backslash_reaches_engine(self):
        # llang source "\\d+" (written here as "\\\\d+") becomes the regex \d+.
        output = run(call_source(
            'call search from re with pattern = "\\\\d+", text = "a123"'
        ))
        self.assertEqual(output,
                         ["{matched: 123, start: 1, end: 4, groups: [], named: {}}"])

    def test_naive_backslash_is_dropped(self):
        # Documented trap: llang source "\d+" becomes the literal pattern d+.
        self.assertEqual(
            run(call_source('call search from re with pattern = "\\d+", text = "123"')),
            ["nothing"],
        )
        self.assertEqual(
            run(call_source('call search from re with pattern = "\\d+", text = "ddd"')),
            ["{matched: ddd, start: 0, end: 3, groups: [], named: {}}"],
        )

    def test_literal_backslash_escape(self):
        output = run(call_source(
            'call search from re with pattern = "a\\\\\\\\b", text = "a\\\\b"'
        ))
        self.assertEqual(output,
                         ["{matched: a\\b, start: 0, end: 3, groups: [], named: {}}"])

    # --- error kinds -----------------------------------------------------

    def test_invalid_patterns_are_catchable(self):
        for pattern in ("(", "[a", "a**", "\\q", "a{3,2}", "(?=x)",
                        "(?P<n>x)", "*a", "[z-a]", "\\1", "\\x41"):
            with self.subTest(pattern=pattern):
                source = 'use the re module\nexpect\n    show call search from re with pattern = "' + pattern.replace("\\", "\\\\") + '", text = "abc"\nif a problem of kind invalid_pattern occurs then\n    show "caught"\nend expect\n'
                self.assertEqual(run(source), ["caught"])

    def test_invalid_flag_is_catchable(self):
        source = """
use the re module
expect
    show call search_flags from re with pattern = "a", text = "a", flags = (a list of "bogus")
if a problem of kind invalid_flag occurs then
    show "caught invalid_flag"
end expect
"""
        self.assertEqual(run(source), ["caught invalid_flag"])

    def test_unhandled_problem_renders_with_kind(self):
        with self.assertRaises(LangError) as ctx:
            run(call_source('call search from re with pattern = "(", text = "a"'))
        self.assertIn("Unhandled problem 'invalid_pattern'", str(ctx.exception))

    # --- differential corpus --------------------------------------------

    def test_matches_cpython_corpus(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "compare_re.py")],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
            errors="replace",
        timeout=300)
        self.assertEqual(completed.returncode, 0,
                         f"{completed.stdout}\n{completed.stderr}")
        self.assertIn("118 cases, 0 mismatches", completed.stdout)


if __name__ == "__main__":
    unittest.main()
