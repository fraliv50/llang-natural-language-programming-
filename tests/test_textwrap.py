"""The llang rewrite of CPython's textwrap core, verified against the stdlib."""

import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang import Lexer, Parser, Interpreter  # noqa: E402


def run(source):
    interpreter = Interpreter(library_paths=[ROOT / "lib"])
    interpreter.run(Parser(Lexer(source).tokenize()).parse_program())
    return interpreter.output


def call(kind, text, width):
    """Run one qualified call to the llang module and return the rendered line."""
    escaped = (text.replace("\\", "\\\\")
                   .replace('"', '\\"')
                   .replace("\n", "\\n")
                   .replace("\t", "\\t"))
    source = (
        'use the textwrap module\n'
        f'show call {kind} from textwrap with text = "{escaped}", width = {width}'
    )
    return run(source)[0]


class TextwrapRewriteTests(unittest.TestCase):
    def test_wrap_greedy_fill(self):
        self.assertEqual(
            call("wrap", "The quick brown fox jumps over the lazy dog", 10),
            "[The quick, brown fox, jumps over, the lazy, dog]",
        )

    def test_fill_joins_with_newline(self):
        self.assertEqual(call("fill", "hello world", 5), "hello\nworld")
        self.assertEqual(
            call("fill", "hello world", 5),
            textwrap.fill("hello world", width=5),
        )

    def test_break_long_word(self):
        self.assertEqual(
            call("wrap", "supercalifragilisticexpialidocious", 10),
            "[supercalif, ragilistic, expialidoc, ious]",
        )
        self.assertEqual(
            call("wrap", "abcdef", 3),
            "[abc, def]",
        )

    def test_multiple_spaces_are_preserved_on_a_line(self):
        self.assertEqual(call("wrap", "a   b", 5), "[a   b]")
        self.assertEqual(call("wrap", "a   b", 4), "[a, b]")

    def test_leading_and_trailing_whitespace(self):
        self.assertEqual(call("wrap", "  hi  ", 4), "[  hi]")
        self.assertEqual(call("wrap", "  leading", 3), "[  l, ead, ing]")

    def test_empty_text(self):
        self.assertEqual(call("wrap", "", 5), "[]")
        self.assertEqual(call("fill", "", 5), "")

    def test_single_word(self):
        self.assertEqual(call("wrap", "hello", 3), "[hel, lo]")
        self.assertEqual(call("wrap", "single", 10), "[single]")

    def test_small_differential_set(self):
        cases = [
            ("", 5), ("word", 2), ("two words", 4),
            ("a  b  c", 6), ("abcdefghij", 3),
            ("  padded text  ", 7), ("one two three four", 5),
        ]
        for text, width in cases:
            with self.subTest(text=text, width=width):
                expected = "[" + ", ".join(textwrap.wrap(text, width=width)) + "]"
                self.assertEqual(call("wrap", text, width), expected)

    def test_matches_cpython_corpus(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "compare_textwrap.py")],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        timeout=300)
        self.assertEqual(completed.returncode, 0,
                         f"{completed.stdout}\n{completed.stderr}")
        self.assertIn("0 mismatches", completed.stdout)


if __name__ == "__main__":
    unittest.main()
