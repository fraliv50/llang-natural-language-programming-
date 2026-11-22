"""The grounded shell layer and its opt-in host bridge."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang import LangError, Lexer, Parser, Interpreter, lint_source  # noqa: E402


def run(source):
    interpreter = Interpreter(library_paths=[ROOT / "lib"])
    interpreter.run(Parser(Lexer(source).tokenize()).parse_program())
    return interpreter


class ForeignShellTests(unittest.TestCase):
    def test_command_result_is_a_map(self):
        result = run("""
use the foreign shell module
set r to call run command from shell with command = "echo hello"
show item "command" of r
show item "code" of r
""")
        self.assertEqual(result.output, ["echo hello", "0"])

    def test_failure_is_reported_not_raised(self):
        result = run("""
use the foreign shell module
set r to call run command from shell with command = "llang_missing_command_xyz"
show item "code" of r
show call command succeeds from shell with command = "echo ok"
""")
        self.assertEqual(result.output[1], "true")
        self.assertNotEqual(result.output[0], "0")

    def test_output_call_fails_loudly_on_error(self):
        with self.assertRaises(LangError):
            run("""
use the foreign shell module
show call output of command from shell with command = "llang_missing_command_xyz"
""")

    def test_shell_is_labeled_foreign(self):
        result = run('use the foreign shell module\nshow "ok"')
        self.assertEqual(result.foreign_modules, {"shell"})


class NativeShellTests(unittest.TestCase):
    def test_native_layer(self):
        result = run("""
use the shell module
show call capture from shell with command = "echo hello"
show call succeeds from shell with command = "echo ok"
show call lines from shell with command = "echo first line"
""")
        self.assertEqual(result.output, ["hello\n", "true", "[first line]"])

    def test_must_succeed(self):
        result = run("""
use the shell module
show (call trim with text = call must_succeed from shell with command = "echo trusted")
""")
        self.assertEqual(result.output, ["trusted"])

    def test_must_succeed_rejects_failure(self):
        with self.assertRaises(LangError):
            run("""
use the shell module
call must_succeed from shell with command = "llang_missing_command_xyz"
""")

    def test_run_each(self):
        result = run("""
use the shell module
set steps to a list of "echo one", "echo two"
set results to call run_each from shell with commands = steps
repeat for each r in results
    show (call trim with text = item "output" of r)
end repeat
""")
        self.assertEqual(result.output, ["one", "two"])

    def test_example_lints_clean(self):
        source = (ROOT / "examples" / "shell.ll").read_text(encoding="utf-8")
        self.assertEqual(lint_source(source), [])


if __name__ == "__main__":
    unittest.main()
