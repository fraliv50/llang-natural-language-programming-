"""End-to-end tests: every shipped example must keep producing its exact output."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang import run_file  # noqa: E402


class ExampleTests(unittest.TestCase):
    def _output(self, name):
        from llang import Interpreter
        from llang.lexer import Lexer
        from llang.parser import Parser

        source = (ROOT / "examples" / name).read_text(encoding="utf-8")
        interpreter = Interpreter()
        interpreter.run(Parser(Lexer(source).tokenize()).parse_program())
        return interpreter.output

    def test_hello(self):
        self.assertEqual(self._output("hello.ll"), [
            "Hello, Ada", "recognised", "0", "1", "2",
            "Welcome, Grace", "Welcome, Linus", "all good",
        ])

    def test_collections(self):
        self.assertEqual(self._output("collections.ll"), [
            "[3, 1, 2]", "3", "3", "[7, 1, 2, 9]",
            "7", "1", "2", "9", "7", "1",
            "{Ada: 10, Grace: 20}", "20", "[Ada, Grace]",
            "[1, 2, 7, 9]", "19", "7 | 1 | 2 | 9", "[a, b, c]",
        ])

    def test_problems(self):
        self.assertEqual(self._output("problems.ll"), [
            "91", "handled: unknown student", "lookup attempt finished",
            "98", "found Grace", "done",
        ])

    def test_shell(self):
        self.assertEqual(self._output("shell.ll"), [
            "--- command results are maps ---",
            "echo llang says hello", "llang says hello\n", "0",
            "--- text and predicates ---", "captured text\n", "true", "false",
            "--- structured output ---", "[first line]",
            "--- a sequence of commands ---",
            "one (code 0)", "two (code 0)", "three (code 0)",
            "--- must succeed fails loudly ---", "trusted",
            "--- environment lookup ---", "nothing",
            "--- safe command construction (llang shlex rewrite) ---",
            "echo 'hello world' 'it'\"'\"'s fine'",
            "'hello world' 'it'\"'\"'s fine'",
        ])

    def test_maxims(self):
        self.assertEqual(self._output("maxims.ll"), [
            "  ada lovelace  ", "ada lovelace", "ADA LOVELACE", "6",
            "two fish", "false", "true", "false", "true", "true", "true",
            "true", "true", "[3, 2, 1]",
        ])

    def test_classes(self):
        self.assertEqual(self._output("classes.ll"), [
            "Point(x: 1, y: 2)", "1, 2", "4, 6", "5, 7", "5",
        ])

    def test_box2d_visual(self):
        self.assertEqual(self._output("box2d_visual.ll"), [
            "Wrote physics.html with 180 computed frames",
        ])
        self.assertTrue((ROOT / "physics.html").exists())

    def test_box2d(self):
        self.assertEqual(self._output("box2d.ll"), [
            "steps: 60",
            "position y: -5.083333333333334",
            "velocity y: -9.999999999999998",
        ])

    def test_modules(self):
        self.assertEqual(self._output("modules.ll"), [
            "--- native modules ---",
            "9.0", "1.41421", "100", "4.0", "3.14159265358979",
            "gnall", "G.H.", "true",
            "[1, 2, 3]", "[1, 2, 3, 4]", "[3, 4, 1, 2]",
            "--- foreign modules (host interop, explicitly marked) ---",
            '{"name": "Ada", "score": 91}',
            "{name: Ada, score: 91}",
            "1.41421", "3.141592653589793",
        ])

    def test_rubiks(self):
        self.assertEqual(self._output("rubiks.ll"), [
            "Cube solved after 10 reverse moves",
            "Wrote rubiks.html",
        ])
        self.assertTrue((ROOT / "rubiks.html").exists())

    def test_report_card(self):
        self.assertEqual(self._output("report_card.ll"), [
            "Ada: 91.5 (A)",
            "Grace: 98.7 (A)",
            "Linus: 78.0 (C)",
            "Barbara: 80.0 (B)",
            "Dieter: 58.5 (F)",
            "Hana: 66.0 (D)",
            "Class mean of student means: 78.8",
            "Top student: Grace",
            "Handled: no marks were recorded for that name",
            "All checks passed.",
        ])


if __name__ == "__main__":
    unittest.main()
