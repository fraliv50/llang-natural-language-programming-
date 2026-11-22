"""Collections, iteration, predicates, builtins, and problems."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llang import LangError, run_source  # noqa: E402


class CollectionTests(unittest.TestCase):
    def test_list_literal_and_indexing(self):
        out = run_source(
            'set xs to a list of 3, 1, 2\nshow item 0 of xs\nshow the length of xs'
        ).output
        self.assertEqual(out, ["3", "3"])

    def test_empty_collections(self):
        out = run_source(
            'show an empty list\nshow an empty map\nshow the length of an empty map'
        ).output
        self.assertEqual(out, ["[]", "{}", "0"])

    def test_map_literal_and_lookup(self):
        out = run_source(
            'set m to a map with "a" mapped to 1, "b" mapped to 2\n'
            'show item "b" of m\nshow call keys with collection = m'
        ).output
        self.assertEqual(out, ["2", "[a, b]"])

    def test_mutation(self):
        out = run_source(
            'set xs to a list of 1\nadd 2 to xs\nset item 0 of xs to 9\nshow xs'
        ).output
        self.assertEqual(out, ["[9, 2]"])

    def test_for_each(self):
        out = run_source(
            'repeat for each n in a list of 1, 2, 3\n    show n\nend repeat'
        ).output
        self.assertEqual(out, ["1", "2", "3"])

    def test_break_and_continue(self):
        out = run_source("""
repeat for each n in a list of 1, 2, 3, 4
    if n equals 2 then
        skip to the next item
    end if
    if n equals 4 then
        stop the loop
    end if
    show n
end repeat
""").output
        self.assertEqual(out, ["1", "3"])

    def test_out_of_range(self):
        with self.assertRaises(LangError):
            run_source('show item 9 of a list of 1')


class PredicateTests(unittest.TestCase):
    def test_postfix_predicates(self):
        out = run_source("""
show (an empty list) is empty
show (a list of 1) is not empty
show nothing is nothing
show 1 is a number
show "x" is text
show (an empty map) is a map
""").output
        self.assertEqual(out, ["true", "true", "true", "true", "true", "true"])

    def test_zero_and_false_are_not_empty(self):
        out = run_source('show 0 is empty\nshow false is empty').output
        self.assertEqual(out, ["false", "false"])


class BuiltinTests(unittest.TestCase):
    def test_phrase_and_alias_are_identical(self):
        phrase = run_source('show call uppercase of with text = "hi"').output
        alias = run_source('show call uppercase with text = "hi"').output
        self.assertEqual(phrase, alias)
        self.assertEqual(phrase, ["HI"])

    def test_text_builtins(self):
        out = run_source("""
show call trim with text = "  hi  "
show call find in text with text = "hello", piece = "ll"
show call replace in text with text = "a-b", old = "-", new = "+"
""").output
        self.assertEqual(out, ["hi", "2", "a+b"])

    def test_collection_builtins(self):
        out = run_source("""
show call sum with items = a list of 1, 2, 3
show call sort with items = a list of 3, 1, 2
show call reverse of with items = a list of 1, 2
""").output
        self.assertEqual(out, ["6", "[1, 2, 3]", "[2, 1]"])

    def test_unknown_builtin(self):
        with self.assertRaises(LangError):
            run_source('call nonexistent thing with text = "x"')

    def test_unknown_builtin_label_is_rejected(self):
        with self.assertRaises(LangError) as ctx:
            run_source('call trim with text = "x", bogus = 1')
        self.assertIn("bogus", str(ctx.exception))

    def test_missing_builtin_label_is_rejected(self):
        with self.assertRaises(LangError) as ctx:
            run_source('call trim with other = "x"')
        self.assertIn("text", str(ctx.exception))


class ProblemTests(unittest.TestCase):
    def test_handler_and_else_and_always(self):
        out = run_source("""
expect
    fail with missing, "nope"
if a problem of kind missing occurs then
    show "handled"
if nothing went wrong then
    show "wrong"
always
    show "cleanup"
end expect
""").output
        self.assertEqual(out, ["handled", "cleanup"])

    def test_no_problem_runs_else(self):
        out = run_source("""
expect
    show "ok"
if a problem of kind missing occurs then
    show "bad"
if nothing went wrong then
    show "else"
end expect
""").output
        self.assertEqual(out, ["ok", "else"])

    def test_unhandled_problem_is_localized(self):
        with self.assertRaises(LangError) as ctx:
            run_source('fail with oops, "broken"')
        self.assertIn("oops", str(ctx.exception))

    def test_alias_syntax_variants(self):
        out = run_source("""
define function f taking x
also called g
    give back x
end function
show call g with x = 7
""").output
        self.assertEqual(out, ["7"])

    def test_identifier_named_a(self):
        out = run_source('set a to 5\nshow a').output
        self.assertEqual(out, ["5"])


if __name__ == "__main__":
    unittest.main()
