"""Formatter tests. Run with: python -m unittest discover -s tests -v"""

import sys
import unittest
from dataclasses import fields, is_dataclass, replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import llang.ast_nodes as ast_nodes  # noqa: E402
from llang import Lexer, Parser  # noqa: E402
from llang.formatter import format_program, format_source  # noqa: E402


def parse(source):
    return Parser(Lexer(source).tokenize()).parse_program()


def without_positions(node):
    """Strip SourcePos values so equality compares AST structure only.

    SourcePos is a plain frozen dataclass (its fields compare by value), and
    reformatting necessarily moves lines around, so positions are decorative
    for these tests just as indentation is decorative in the language.
    """
    if isinstance(node, (list, tuple)):
        return type(node)(without_positions(item) for item in node)
    if is_dataclass(node) and not isinstance(node, type):
        updates = {}
        for field in fields(node):
            if field.name == "pos":
                updates[field.name] = None
            else:
                updates[field.name] = without_positions(getattr(node, field.name))
        return replace(node, **updates)
    return node


def collect_types(node, found):
    if isinstance(node, (list, tuple)):
        for item in node:
            collect_types(item, found)
        return
    if is_dataclass(node) and not isinstance(node, type):
        found.add(type(node).__name__)
        for field in fields(node):
            if field.name != "pos":
                collect_types(getattr(node, field.name), found)


ALL_NODE_TYPES = {
    name for name, obj in vars(ast_nodes).items()
    if isinstance(obj, type) and is_dataclass(obj)
    and obj.__module__ == ast_nodes.__name__
}


# A source corpus covering every construct and every surface synonym.
CORPUS = [
    # --- literals, variables, calls -------------------------------------
    "show 1",
    "show 2.5",
    'show "hello"',
    r'display "a\nb\tc\"d\\e"',
    "show true",
    "show false",
    "show nothing",
    "show name",
    "call greet with name = \"Ada\"",
    "call uppercase of with text = \"hi\"",
    "call noop",
    # nested calls / greedy composites inside comma-separated argument lists
    "set present to call contains with collection = (call keys of with collection = scores), value = name",
    "show call outer with a = (call inner with x = 1), b = (a list of 2, 3), c = (item 0 of xs)",
    "set m to a map with (call key of with x = 1) mapped to (call val of with y = 2)",
    # --- binary operators / comparison synonyms -------------------------
    "show 1 plus 2",
    "show 5 minus 3",
    "show 4 times 2",
    "show 10 divided by 2",
    "show 10 modulo 3",
    "show 2 to the power of 8",
    "show 5 is greater than 3",
    "show 5 is more than 3",
    "show 5 exceeds 3",
    "show 3 is less than 5",
    "show 5 is at least 5",
    "show 5 is at most 5",
    "show 5 equals 5",
    "show 5 is equal to 5",
    "show 5 does not equal 3",
    "show 5 is not equal to 3",
    "show 5 differs from 3",
    "show true and false",
    "show true or false",
    # --- associativity / parentheses ------------------------------------
    "show 2 plus 3 times 4",
    "show 2 plus (3 times 4)",
    "show ((1 plus 2))",
    "show (1 plus 2) is empty",
    "show not (1 plus 2)",
    "show (call f with a = 1) is empty",
    "show (call f with a = 1) plus 2",
    "show not (call f with a = 1)",
    "show not (a list of 1, 2)",
    "show (a map with \"k\" mapped to 1) is a map",
    "show (item 0 of xs) is a number",
    "show (the length of xs) plus 1",
    # --- unary prefixes and postfix predicates --------------------------
    "show not true",
    "show xs is empty",
    "show xs is not empty",
    "show xs is nothing",
    "show xs is a number",
    "show xs is text",
    "show xs is a list",
    "show xs is a map",
    "show not xs is empty",
    "show (not xs) is empty",
    "show xs is empty is not empty",
    # --- collections, indexing, length ----------------------------------
    "set xs to an empty list",
    "set xs to a list of 1, 2 plus 3",
    "set m to an empty map",
    "set m to a map with \"a\" mapped to 1, \"b\" mapped to 2",
    "show item 0 of xs",
    "show item (1 plus 2) of xs",
    "show the length of xs",
    "show the length of a list of 1, 2",
    # --- simple statements ----------------------------------------------
    "set x to 5",
    "let y be 5",
    "show 1",
    "display 1",
    "print 1",
    'require x is greater than 0, "positive"',
    "require x is greater than 0",
    "add 1 to total",
    "add call f with a = 1 to total",
    "set item 0 of xs to 9",
    "set item (1 plus 2) of xs to call f with a = 1",
    "stop the loop",
    "skip to the next item",
    "fail with Trouble",
    'fail with Trouble, "bad"',
    "return 1",
    "give back 1",
    # --- structured statements ------------------------------------------
    """if x is greater than 10 then
    show "big"
otherwise if x equals 5 then
    show "five"
otherwise
    show "small"
end if""",
    """if true then
    if false then
        show "a"
    end if
end if""",
    """while x is less than 3
    show x
    set x to x plus 1
end repeat""",
    """repeat while x is less than 3
    if x equals 2 then
        skip to the next item
    end if
    show x
end repeat""",
    """repeat for each v in xs
    show v
end repeat""",
    """define function greet taking name
also known as say_hello, welcome
    give back "Hello, " plus name
end function""",
    """define a function noop
    return nothing
end function""",
    """expect
    fail with Trouble, "boom"
if a problem of kind Trouble occurs then
    show "caught"
if nothing went wrong then
    show "fine"
always
    show "done"
end expect""",
    """expect
    show "ok"
end expect""",
    # --- negatives and floats that Python renders with an exponent -----
    "show (0 minus 5)",
    "show (0 minus 0.5)",


    "show 0.0000000001",
    "show 100000000000000000000.0",
    "show 0 minus 0.0000000001",

    # --- modules --------------------------------------------------------
    "use the math module",
    "use the foreign json module",
    "use the foreign math module as hostmath",
    "use the math module\ncall sqrt from math with value = 9",
    # --- comments and blank lines are ignored ---------------------------
    '# leading comment\n\nset x to 1   # trailing comment\n\nshow x\n',
]


class FormatterRoundTripTests(unittest.TestCase):
    def test_corpus_preserves_ast(self):
        found = set()
        for source in CORPUS:
            with self.subTest(source=source):
                ast = parse(source)
                collect_types(ast, found)
                formatted = format_program(ast)
                reparsed = parse(formatted)
                self.assertEqual(without_positions(reparsed), without_positions(ast),
                                 f"AST changed for source:\n{source}\n"
                                 f"formatted as:\n{formatted}")

    def test_corpus_covers_every_node_type(self):
        found = set()
        for source in CORPUS:
            collect_types(parse(source), found)
        self.assertEqual(ALL_NODE_TYPES, found,
                         f"missing: {sorted(ALL_NODE_TYPES - found)}")

    def test_formatting_is_idempotent(self):
        for source in CORPUS:
            with self.subTest(source=source):
                once = format_program(parse(source))
                twice = format_program(parse(once))
                self.assertEqual(twice, once)

    def test_synonym_groups_share_one_canonical_form(self):
        groups = [
            ["show 1", "display 1", "print 1"],
            ["set x to 1", "let x be 1"],
            ["show 2 is greater than 1", "show 2 is more than 1", "show 2 exceeds 1"],
            ["show 2 equals 2", "show 2 is equal to 2"],
            ["show 2 does not equal 1", "show 2 is not equal to 1",
             "show 2 differs from 1"],
            ["return 1", "give back 1"],
            [
                "define function f\nalso known as g, h\n    return 1\nend function",
                "define function f\nalso called g, h\n    return 1\nend function",
                "define a function f\nalso called g, h\n    return 1\nend function",
            ],
            ["repeat while x is less than 1\n    show x\nend repeat",
             "while x is less than 1\n    show x\nend repeat"],
        ]
        for group in groups:
            with self.subTest(group=group):
                forms = {format_source(source) for source in group}
                self.assertEqual(len(forms), 1, f"synonyms formatted differently: {forms}")


class CanonicalSpellingTests(unittest.TestCase):
    def test_canonical_phrases_appear_and_synonyms_do_not(self):
        cases = [
            ('display "Hi"', ['show "Hi"'], ["display", "print"]),
            ('print "Hi"', ['show "Hi"'], ["display", "print"]),
            ("let x be 2", ["set x to 2"], ["let "]),
            ("show 4 is more than 3", ["is greater than"], ["is more than"]),
            ("show 4 exceeds 3", ["is greater than"], ["exceeds"]),
            ("show 4 is equal to 4", ["equals"], ["is equal to"]),
            ("show 4 is not equal to 3", ["does not equal"], ["is not equal to"]),
            ("show 4 differs from 3", ["does not equal"], ["differs from"]),
            ("give back 2", ["return 2"], ["give back"]),
            (
                "define function f\nalso called g\n    return 1\nend function",
                ["also known as g"],
                ["also called"],
            ),
            ("define a function f\n    return 1\nend function",
             ["define function f"], ["define a function"]),
            ("show 8 divided by 2", ["divided by"], []),
            ("show 8 is at least 8", ["is at least"], []),
            ("show 8 is at most 8", ["is at most"], []),
        ]
        for source, required, forbidden in cases:
            with self.subTest(source=source):
                formatted = format_source(source)
                for phrase in required:
                    self.assertIn(phrase, formatted)
                for phrase in forbidden:
                    self.assertNotIn(phrase, formatted)

    def test_while_normalizes_to_repeat_while(self):
        formatted = format_source("while x is less than 3\n    show x\nend repeat")
        self.assertIn("repeat while x is less than 3", formatted)
        self.assertFalse(
            any(line.startswith("while ") for line in formatted.splitlines()),
            formatted,
        )

    def test_explicit_block_delimiters(self):
        formatted = format_source(
            'if x is greater than 10 then\n'
            '    show "big"\n'
            'otherwise if x equals 5 then\n'
            '    show "five"\n'
            'otherwise\n'
            '    show "small"\n'
            'end if'
        )
        self.assertIn("end if", formatted)
        self.assertIn("otherwise if", formatted)
        self.assertIn("    ", formatted)  # four-space indentation

        formatted = format_source(
            "if true then\n    if false then\n        show \"a\"\n    end if\nend if"
        )
        self.assertEqual(formatted.count("end if"), 2)
        self.assertIn("        ", formatted)  # two levels of indentation


if __name__ == "__main__":
    unittest.main()
