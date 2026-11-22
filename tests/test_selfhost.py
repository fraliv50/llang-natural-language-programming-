"""Self-hosting Stage 2: llang's lexer written in llang."""

import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang import run_source  # noqa: E402


def tokens(source):
    program = (
        "use the llang_lexer module\n"
        "use the json module\n"
        f"set toks to call tokenize from llang_lexer with text = {json.dumps(source, ensure_ascii=False)}\n"
        "show call stringify from json with value = "
        "(call token_digests from llang_lexer with tokens = toks)\n"
    )
    with redirect_stdout(io.StringIO()):
        interpreter = run_source(program)
    return json.loads(interpreter.output[-1])


class SelfHostedLexerTests(unittest.TestCase):
    def test_basic_tokens(self):
        self.assertEqual(tokens("set x to 5"), [
            ["WORD", "set", 1, 1], ["WORD", "x", 1, 5], ["WORD", "to", 1, 7],
            ["NUMBER", "5", 1, 10], ["EOF", "", 1, 11],
        ])

    def test_string_escapes_and_positions(self):
        result = tokens('show "a\\nb"')
        self.assertEqual(result[1], ["STRING", "a\nb", 1, 6])
        self.assertEqual(result[-1][0], "EOF")

    def test_comment_is_skipped_and_newline_kept(self):
        result = tokens("# hi\nshow 1")
        self.assertEqual(result[0], ["NEWLINE", "\n", 1, 5])
        self.assertEqual(result[1], ["WORD", "show", 2, 1])

    def test_error_kind_is_catchable(self):
        with self.assertRaises(Exception):
            tokens('show "unterminated')

    def test_harness_passes(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "compare_lexer.py")],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
            timeout=300,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("0 mismatches", completed.stdout)


if __name__ == "__main__":
    unittest.main()
