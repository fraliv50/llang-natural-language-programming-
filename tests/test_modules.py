"""Module system and the labeled foreign bridge."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang import LangError, Lexer, Parser, Interpreter  # noqa: E402


def run(source):
    interpreter = Interpreter(library_paths=[ROOT / "lib"])
    interpreter.run(Parser(Lexer(source).tokenize()).parse_program())
    return interpreter


class ModuleTests(unittest.TestCase):
    def test_native_module(self):
        result = run("""
use the math module
show call sqrt from math with value = 81
show call clamp from math with value = 150, low = 0, high = 100
show item "pi" of math
""")
        self.assertEqual(result.output, ["9.0", "100", "3.14159265358979"])

    def test_module_functions_can_call_each_other(self):
        result = run("""
use the text module
show call is_palindrome from text with value ="Level"
""")
        self.assertEqual(result.output, ["true"])

    def test_several_native_modules(self):
        result = run("""
use the lists module
use the text module
show call unique from lists with items = a list of 1, 2, 2
show call initials from text with value ="alan turing"
""")
        self.assertEqual(result.output, ["[1, 2]", "A.T."])

    def test_foreign_module_is_labeled(self):
        result = run("""
use the foreign json module
show call dumps from json with value = (a map with "a" mapped to 1)
""")
        self.assertEqual(result.output, ['{"a": 1}'])
        self.assertEqual(result.foreign_modules, {"json"})

    def test_foreign_alias_avoids_name_collision(self):
        result = run("""
use the math module
use the foreign math module as hostmath
show call sqrt from math with value = 4
show item "pi" of hostmath
""")
        self.assertEqual(result.output[0], "2.0")
        self.assertEqual(result.foreign_modules, {"hostmath"})

    def test_unknown_module(self):
        with self.assertRaises(LangError) as ctx:
            run("use the missing module")
        self.assertIn("Cannot find module", str(ctx.exception))

    def test_unknown_export(self):
        with self.assertRaises(LangError) as ctx:
            run("""
use the math module
call nonsense from math with value = 1
""")
        self.assertIn("no export", str(ctx.exception))

    def test_unloaded_module_in_call(self):
        with self.assertRaises(LangError) as ctx:
            run("call sqrt from math with value = 4")
        self.assertIn("not loaded", str(ctx.exception))

    def test_module_loaded_once(self):
        result = run("""
use the math module
use the math module
show call sqrt from math with value = 9
""")
        self.assertEqual(result.output, ["3.0"])


if __name__ == "__main__":
    unittest.main()
