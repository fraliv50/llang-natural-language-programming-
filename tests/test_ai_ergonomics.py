"""Ergonomics for AI authors: phrase-named definitions and the @ escape sigil."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llang import run_source  # noqa: E402
from llang.formatter import format_source  # noqa: E402
from llang.parser import Parser  # noqa: E402
from llang.lexer import Lexer  # noqa: E402


def program(source):
    return Parser(Lexer(source).tokenize()).parse_program()


def normalize(node):
    if hasattr(node, "__dict__"):
        items = {k: normalize(v) for k, v in vars(node).items() if k != "pos"}
        return (type(node).__name__, tuple(sorted(items.items())))
    if isinstance(node, (list, tuple)):
        return tuple(normalize(item) for item in node)
    return node


class AiErgonomicsTests(unittest.TestCase):
    def test_phrase_named_function(self):
        out = run_source("""
define function find all taking xs, target
    set found to an empty list
    repeat for each x in xs
        if x equals target then
            add x to found
        end if
    end repeat
    give back found
end function

show call find all with xs = (a list of 1, 2, 1, 3), target = 1
""").output
        self.assertEqual(out, ["[1, 1]"])

    def test_phrase_named_method(self):
        out = run_source("""
define class Point taking x
define method get value taking this
    give back item "x" of this
end method
end class

set p to call new Point with x = 7
show ask p to get value
""").output
        self.assertEqual(out, ["7"])

    def test_at_escape_for_reserved_label(self):
        out = run_source("""
define function total taking @end
    give back @end plus 1
end function

show call total with @end = 41
""").output
        self.assertEqual(out, ["42"])

    def test_at_escape_for_reserved_variable(self):
        out = run_source("""
set @end to 5
set @function to 37
show @end plus @function
""").output
        self.assertEqual(out, ["42"])

    def test_at_escape_round_trips_through_formatter(self):
        source = "define function total taking @end\n    give back @end plus 1\nend function\n"
        formatted = format_source(source)
        self.assertIn("taking @end", formatted)
        self.assertEqual(normalize(program(formatted)), normalize(program(source)))

    def test_phrase_name_round_trips_through_formatter(self):
        source = "define function find all taking xs\n    give back xs\nend function\n"
        formatted = format_source(source)
        self.assertIn("define function find all taking xs", formatted)
        self.assertEqual(normalize(program(formatted)), normalize(program(source)))

    def test_reserved_word_still_rejected_without_escape(self):
        with self.assertRaises(Exception):
            program("define function f taking end\n    give back end\nend function\n")


if __name__ == "__main__":
    unittest.main()
