"""The llang rewrite of CPython's fnmatch, verified against the stdlib."""

import fnmatch
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang import Lexer, Parser, Interpreter  # noqa: E402


def run(source):
    interpreter = Interpreter(library_paths=[ROOT / "lib"])
    interpreter.run(Parser(Lexer(source).tokenize()).parse_program())
    return interpreter.output


def ll_string(value):
    """Render a Python string as a double-quoted llang string literal."""
    escaped = (value.replace("\\", "\\\\").replace('"', '\\"')
                    .replace("\n", "\\n").replace("\t", "\\t"))
    return f'"{escaped}"'


def matches(name, pattern, case_sensitive=True):
    fn = "fnmatchcase" if case_sensitive else "fnmatch"
    source = (
        'use the fnmatch module\n'
        f'show call {fn} from fnmatch with name = {ll_string(name)}, '
        f'pattern = {ll_string(pattern)}'
    )
    return run(source)[0] == "true"


class FnmatchRewriteTests(unittest.TestCase):
    def test_literal_text(self):
        self.assertTrue(matches("abc", "abc"))
        self.assertFalse(matches("abc", "abcd"))
        self.assertFalse(matches("a.b", "axb"))
        self.assertTrue(matches("a+b", "a+b"))

    def test_empty_strings(self):
        self.assertTrue(matches("", ""))
        self.assertFalse(matches("abc", ""))
        self.assertTrue(matches("", "*"))
        self.assertFalse(matches("", "?"))

    def test_star(self):
        self.assertTrue(matches("anything", "*"))
        self.assertTrue(matches("abc", "a*c"))
        self.assertTrue(matches("abc", "*b*"))
        self.assertTrue(matches("abc", "a**c"))
        self.assertTrue(matches("abcabc", "*abc*"))
        self.assertFalse(matches("abc", "a*d"))

    def test_question_mark(self):
        self.assertTrue(matches("a", "?"))
        self.assertTrue(matches("cat", "c?t"))
        self.assertFalse(matches("abcd", "??"))
        self.assertFalse(matches("a", "??"))

    def test_classes(self):
        self.assertTrue(matches("b", "[abc]"))
        self.assertFalse(matches("d", "[abc]"))
        self.assertTrue(matches("[", "[[]"))
        self.assertTrue(matches("]", "[]]"))

    def test_negation(self):
        self.assertTrue(matches("d", "[!abc]"))
        self.assertFalse(matches("a", "[!abc]"))
        self.assertFalse(matches("]", "[!]]"))
        self.assertTrue(matches("a", "[!]]"))

    def test_ranges(self):
        self.assertTrue(matches("m", "[a-z]"))
        self.assertFalse(matches("M", "[a-z]"))
        self.assertTrue(matches("M", "[a-zA-Z]"))
        self.assertTrue(matches("7", "[a-zA-Z0-9]"))
        self.assertTrue(matches("file1.txt", "file[0-9].txt"))
        self.assertFalse(matches("filex.txt", "file[0-9].txt"))

    def test_unclosed_bracket_is_literal(self):
        self.assertTrue(matches("[abc", "[abc"))
        self.assertFalse(matches("a", "[abc"))
        self.assertTrue(matches("[]", "[]"))

    def test_case_insensitive_fnmatch(self):
        self.assertTrue(matches("Hello.TXT", "*.txt", case_sensitive=False))
        self.assertTrue(matches("AbC", "a?c", case_sensitive=False))
        self.assertFalse(matches("Hello.TXT", "*.txt", case_sensitive=True))

    def test_agrees_with_stdlib_on_examples(self):
        for name, pattern in [
            ("hello.txt", "*.txt"), ("a5b", "a[0-9]b"),
            ("q", "[!a-z]"), ("", "*"), ("abc", ""),
        ]:
            with self.subTest(name=name, pattern=pattern):
                self.assertEqual(matches(name, pattern),
                                 fnmatch.fnmatchcase(name, pattern))

    def test_matches_cpython_corpus(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "compare_fnmatch.py")],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        timeout=300)
        self.assertEqual(completed.returncode, 0,
                         f"{completed.stdout}\n{completed.stderr}")
        self.assertIn("0 mismatches", completed.stdout)
        self.assertIn("85 cases", completed.stdout)


if __name__ == "__main__":
    unittest.main()
