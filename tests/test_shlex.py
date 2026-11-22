"""The llang rewrite of CPython's shlex, verified against the stdlib."""

import shlex
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


class ShlexRewriteTests(unittest.TestCase):
    def test_split(self):
        self.assertEqual(
            run('use the shlex module\nshow call shell_words from shlex with input = "echo \'hi there\'"'),
            ["[echo, hi there]"],
        )

    def test_quote(self):
        self.assertEqual(
            run('use the shlex module\nshow call shell_quote from shlex with value = "a b"'),
            ["'a b'"],
        )

    def test_join(self):
        self.assertEqual(
            run('use the shlex module\nshow call shell_join from shlex with words = (a list of "echo", "hi there")'),
            ["echo 'hi there'"],
        )

    def test_unclosed_quote_fails_loudly(self):
        with self.assertRaises(LangError) as ctx:
            run('use the shlex module\nshow call shell_words from shlex with input = "\'abc"')
        self.assertIn("unclosed_quote", str(ctx.exception))

    def test_matches_cpython_corpus(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "compare_shlex.py")],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        timeout=300)
        self.assertEqual(completed.returncode, 0,
                         f"{completed.stdout}\n{completed.stderr}")
        self.assertIn("0 mismatches", completed.stdout)

    def test_shell_build_uses_the_rewrite(self):
        output = run("""
use the shell module
set cmd to call build from shell with program = "echo", args = (a list of "hello world")
show cmd
""")
        self.assertEqual(output[0], "echo 'hello world'")
        self.assertEqual(output[0], shlex.join(["echo", "hello world"]))


if __name__ == "__main__":
    unittest.main()
