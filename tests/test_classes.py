"""Tests for the minimal class/record system.

Run with: python -m unittest discover -s tests
"""

import sys
import unittest
from dataclasses import fields, is_dataclass, replace
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

import llang.ast_nodes as ast_nodes  # noqa: E402
from llang import (Interpreter, LangError, Lexer, Parser, lint_source,  # noqa: E402
                   run_source)
from llang.formatter import format_program, format_source  # noqa: E402
from llang.interpreter import ClassValue, Instance, ProblemSignal  # noqa: E402


def _output(source):
    return run_source(source).output


def without_positions(node):
    """Strip SourcePos so AST comparison ignores line/column changes."""
    if isinstance(node, (list, tuple)):
        return type(node)(without_positions(item) for item in node)
    if is_dataclass(node) and not isinstance(node, type):
        updates = {}
        for field in fields(node):
            updates[field.name] = (None if field.name == "pos"
                                   else without_positions(getattr(node, field.name)))
        return replace(node, **updates)
    return node


def parse(source):
    return Parser(Lexer(source).tokenize()).parse_program()


POINT_CLASS = """define class Point taking x, y
define method get_x taking this
    give back item "x" of this
end method
define method move taking this, dx, dy
    set item "x" of this to (item "x" of this) plus dx
    set item "y" of this to (item "y" of this) plus dy
    give back this
end method
define method total taking this
    give back (item "x" of this) plus (item "y" of this)
end method
define method both taking this
    give back (ask this to get_x) plus (ask this to total)
end method
end class
"""


class ConstructionTests(unittest.TestCase):
    def test_construct_and_read_fields(self):
        source = POINT_CLASS + """
set p to call new Point with x = 1, y = 2
show item "x" of p
show item "y" of p
"""
        self.assertEqual(_output(source), ["1", "2"])

    def test_field_write(self):
        source = POINT_CLASS + """
set p to call new Point with x = 1, y = 2
set item "y" of p to 9
show ask p to total
"""
        self.assertEqual(_output(source), ["10"])

    def test_instances_are_rendered(self):
        source = POINT_CLASS + """
set p to call new Point with x = 3, y = 4
show p
"""
        self.assertEqual(_output(source), ["Point(x: 3, y: 4)"])

    def test_each_instance_gets_fresh_fields(self):
        source = POINT_CLASS + """
set a to call new Point with x = 1, y = 2
set b to call new Point with x = 10, y = 20
set item "x" of a to 99
show ask a to total
show ask b to total
"""
        self.assertEqual(_output(source), ["101", "30"])

    def test_class_definition_binds_a_value_at_execution_time(self):
        # A class is an executable statement, not a parse-time macro.
        with self.assertRaises(LangError) as ctx:
            _output("set p to call new Point with x = 1\n" + POINT_CLASS)
        self.assertIn("Unknown class 'Point'", str(ctx.exception))

    def test_define_class_synonyms(self):
        short = "define class P taking x\nend class\nset p to call new P with x = 1\nshow item \"x\" of p"
        long = "define a class P taking x\nend class\nset p to call new P with x = 1\nshow item \"x\" of p"
        self.assertEqual(_output(short), _output(long))
        self.assertEqual(format_source(short), format_source(long))

    def test_no_fields_is_allowed(self):
        source = "define class Marker\nend class\nset m to call new Marker\nshow m\n"
        self.assertEqual(_output(source), ["Marker()"])


class MethodTests(unittest.TestCase):
    def test_method_uses_this_and_extra_args(self):
        source = POINT_CLASS + """
set p to call new Point with x = 1, y = 2
show ask p to move with dx = 4, dy = 5
show ask p to total
"""
        self.assertEqual(_output(source), ["Point(x: 5, y: 7)", "12"])

    def test_explicit_this_binding_is_receiver(self):
        source = POINT_CLASS + """
set p to call new Point with x = 7, y = 0
show ask p to get_x
"""
        self.assertEqual(_output(source), ["7"])

    def test_method_can_call_another_method_on_this(self):
        source = POINT_CLASS + """
set p to call new Point with x = 4, y = 6
show ask p to both
"""
        self.assertEqual(_output(source), ["14"])

    def test_ask_is_an_expression(self):
        source = POINT_CLASS + """
set p to call new Point with x = 3, y = 3
show (ask p to total) plus 1
show call text of with value = (ask p to total)
"""
        self.assertEqual(_output(source), ["7", "6"])

    def test_method_define_synonyms(self):
        a = ("define class P taking x\n"
             "define method f taking this\n give back item \"x\" of this\n"
             "end method\nend class\n"
             "set p to call new P with x = 5\nshow ask p to f")
        b = a.replace("define method", "define a method")
        self.assertEqual(_output(a), _output(b))
        self.assertEqual(format_source(a), format_source(b))

    def test_class_body_is_not_an_enclosing_scope(self):
        # A sibling method is not a bare name inside another method.
        source = POINT_CLASS + """
set p to call new Point with x = 1, y = 2
show ask p to missing
"""
        with self.assertRaises(LangError) as ctx:
            _output(source)
        self.assertIn("no such method 'missing' on Point", str(ctx.exception))

        source = """define class P taking x
define method f taking this
    give back g
end method
define method g taking this
    give back 1
end method
end class
set p to call new P with x = 1
show ask p to f
"""
        with self.assertRaises(LangError) as ctx:
            _output(source)
        self.assertIn("Undefined name 'g'", str(ctx.exception))

    def test_loop_guard_applies_inside_methods(self):
        source = """define class P taking x
define method spin taking this
    repeat while true
        show 1
    end repeat
end method
end class
set p to call new P with x = 1
ask p to spin
"""
        interpreter = Interpreter(max_iterations=2)
        program = parse(source)
        with self.assertRaises(LangError) as ctx:
            interpreter.run(program)
        self.assertIn("Loop exceeded 2 iterations", str(ctx.exception))


class AliasingTests(unittest.TestCase):
    def test_alias_sees_mutations(self):
        source = POINT_CLASS + """
set p to call new Point with x = 1, y = 2
set q to p
set item "x" of q to 9
show item "x" of p
ask q to move with dx = 0, dy = 1
show ask p to total
"""
        self.assertEqual(_output(source), ["9", "12"])

    def test_rebinding_a_name_does_not_affect_other_aliases(self):
        source = POINT_CLASS + """
set p to call new Point with x = 1, y = 2
set q to p
set q to call new Point with x = 7, y = 8
show ask p to total
show ask q to total
"""
        self.assertEqual(_output(source), ["3", "15"])


class ProblemTests(unittest.TestCase):
    def test_unknown_field_is_catchable(self):
        source = POINT_CLASS + """
set p to call new Point with x = 1, y = 2
expect
    show item "z" of p
if a problem of kind unknown_field occurs then
    show "caught"
end expect
"""
        self.assertEqual(_output(source), ["caught"])

    def test_unknown_field_write_is_catchable(self):
        source = POINT_CLASS + """
set p to call new Point with x = 1, y = 2
expect
    set item "z" of p to 5
if a problem of kind unknown_field occurs then
    show "caught"
end expect
show item "x" of p
"""
        self.assertEqual(_output(source), ["caught", "1"])

    def test_missing_field_problem_is_defined(self):
        # Construction always initializes every declared field, so this is
        # reached only by hand-building a partially initialized instance.
        source = POINT_CLASS + "set p to call new Point with x = 1, y = 2\n"
        interpreter = run_source(source)
        class_obj = interpreter.global_env.get("Point")
        partial = Instance(class_obj, {"x": 1})
        index = Parser(Lexer('show item "y" of p').tokenize()).parse_program().statements[0].expr
        interpreter.global_env.set("p", partial)
        with self.assertRaises(ProblemSignal) as ctx:
            interpreter._eval_index(index, interpreter.global_env)
        self.assertEqual(ctx.exception.kind, "missing_field")

    def test_missing_field_key_must_be_text(self):
        source = POINT_CLASS + """
set p to call new Point with x = 1, y = 2
show item 0 of p
"""
        with self.assertRaises(LangError) as ctx:
            _output(source)
        self.assertIn("Field name must be text", str(ctx.exception))


class ErrorTests(unittest.TestCase):
    def _assert_error(self, source, fragment):
        with self.assertRaises(LangError) as ctx:
            _output(source)
        self.assertIn(fragment, str(ctx.exception))

    def test_unknown_class(self):
        self._assert_error("set p to call new Ghost with x = 1",
                           "Unknown class 'Ghost'")

    def test_not_a_class(self):
        self._assert_error("set Point to 1\nset p to call new Point with x = 1",
                           "'Point' is not a class")

    def test_missing_constructor_field(self):
        source = "define class P taking x, y\nend class\nset p to call new P with x = 1"
        self._assert_error(source, "Missing argument(s) for 'P': y")

    def test_unknown_constructor_field(self):
        source = "define class P taking x\nend class\nset p to call new P with x = 1, z = 2"
        self._assert_error(source, "Unknown argument 'z' for class 'P'; expected: x")

    def test_duplicate_constructor_field(self):
        source = "define class P taking x\nend class\nset p to call new P with x = 1, x = 2"
        self._assert_error(source, "Argument 'x' supplied twice")

    def test_unknown_method(self):
        source = POINT_CLASS + """
set p to call new Point with x = 1, y = 2
ask p to nope
"""
        self._assert_error(source, "no such method 'nope' on Point")

    def test_ask_requires_an_instance(self):
        self._assert_error("ask 5 to nope", "'ask' requires an instance")

    def test_missing_method_argument(self):
        source = POINT_CLASS + """
set p to call new Point with x = 1, y = 2
show ask p to move with dx = 1
"""
        self._assert_error(source, "Missing argument(s) for 'move': dy")

    def test_unknown_method_argument(self):
        source = POINT_CLASS + """
set p to call new Point with x = 1, y = 2
ask p to move with dx = 1, dy = 2, zz = 3
"""
        self._assert_error(source, "Unknown argument 'zz' for method 'move'")

    def test_explicit_this_at_call_site_is_rejected(self):
        source = POINT_CLASS + """
set p to call new Point with x = 1, y = 2
ask p to move with this = p, dx = 1, dy = 2
"""
        self._assert_error(source,
                           "'this' is supplied automatically and cannot be a call label")

    def test_method_without_this_is_rejected(self):
        source = """define class P taking x
define method f taking y
    give back y
end method
end class
"""
        self._assert_error(source, "A method's first parameter must be 'this'")

    def test_duplicate_field_rejected(self):
        self._assert_error("define class P taking x, x\nend class",
                           "Duplicate field 'x' in class 'P'")

    def test_duplicate_method_rejected(self):
        source = """define class P taking x
define method f taking this
    give back 1
end method
define method f taking this
    give back 2
end method
end class
"""
        self._assert_error(source, "Duplicate method 'f' in class 'P'")

    def test_duplicate_class_name_rejected(self):
        source = "define class P taking x\nend class\ndefine class P taking y\nend class"
        self._assert_error(source, "Name 'P' is already defined")

    def test_missing_end_class(self):
        self._assert_error("define class P taking x\n",
                           "Unexpected end of input — missing 'end class'")

    def test_missing_end_method(self):
        source = "define class P taking x\ndefine method f taking this\n give back 1\nend class"
        self._assert_error(source, "Expected 'method', found 'class'")

    def test_only_methods_allowed_in_class_body(self):
        self._assert_error("define class P taking x\nshow 1\nend class",
                           "Only method definitions are allowed in a class body")

    def test_this_outside_a_method_is_undefined(self):
        self._assert_error("show this", "Undefined name 'this'")

    def test_inheritance_is_deliberately_omitted(self):
        # Phrase names allow the words "inherits from", but that grants no
        # inheritance behaviour: parent fields are not present on the instance.
        source = """
define class Animal taking name
end class
define class Dog inherits from Animal taking tricks
end class
set d to call new Dog inherits from Animal with tricks = (a list of 1)
show item "name" of d
"""
        with self.assertRaises(LangError):
            _output(source)


class FormatterAndLinterTests(unittest.TestCase):
    CLASS_SOURCES = [
        "define class Point taking x, y\nend class",
        'define class Point taking x, y\ndefine method get taking this\n give back item "x" of this\nend method\nend class',
        POINT_CLASS,
        POINT_CLASS + """
set p to call new Point with x = 1, y = 2
show ask p to total
ask p to move with dx = 1, dy = 1
show (ask p to get_x) plus 1
""",
        """define class A taking v
define method f taking this, other
    give back ask this to g
end method
define method g taking this
    give back item "v" of this
end method
end class
set a to call new A with v = 1
show ask a to f with other = 2
""",
    ]

    def test_round_trip_preserves_ast(self):
        for source in self.CLASS_SOURCES:
            with self.subTest(source=source):
                ast = parse(source)
                formatted = format_program(ast)
                reparsed = parse(formatted)
                self.assertEqual(without_positions(reparsed),
                                 without_positions(ast))

    def test_formatting_is_idempotent(self):
        for source in self.CLASS_SOURCES:
            with self.subTest(source=source):
                once = format_source(source)
                self.assertEqual(format_source(once), once)

    def test_new_nodes_have_canonical_spelling(self):
        formatted = format_source(
            "define a class P taking x\n"
            "define a method f taking this, y\n return y\nend method\nend class\n"
            "set p to call new P with x = 1\nask p to f with y = 2"
        )
        self.assertIn("define class P taking x", formatted)
        self.assertIn("define method f taking this, y", formatted)
        self.assertIn("call new P with x = 1", formatted)
        self.assertIn("ask p to f with y = 2", formatted)
        self.assertNotIn("define a class", formatted)
        self.assertNotIn("define a method", formatted)

    def test_example_is_lint_clean(self):
        source = (ROOT / "examples" / "classes.ll").read_text(encoding="utf-8")
        self.assertEqual(lint_source(source), [])

    def test_linter_knows_about_classes_and_new_calls(self):
        source = POINT_CLASS + """
set p to call new Point with x = 1, y = 2
show ask p to total
"""
        self.assertEqual(lint_source(source), [])

    def test_linter_warns_on_unknown_method_when_receiver_is_known(self):
        source = POINT_CLASS + """
set p to call new Point with x = 1, y = 2
ask p to nope
"""
        messages = [d.message for d in lint_source(source)]
        self.assertTrue(any("has no method 'nope'" in m for m in messages), messages)

    def test_linter_warns_on_unknown_field_when_receiver_is_known(self):
        source = POINT_CLASS + """
set p to call new Point with x = 1, y = 2
show item "z" of p
"""
        messages = [d.message for d in lint_source(source)]
        self.assertTrue(any("has no field 'z'" in m for m in messages), messages)


class ExampleTests(unittest.TestCase):
    def test_example_output(self):
        source = (ROOT / "examples" / "classes.ll").read_text(encoding="utf-8")
        self.assertEqual(_output(source), [
            "Point(x: 1, y: 2)", "1, 2", "4, 6", "5, 7", "5",
        ])


class RuntimeValueTests(unittest.TestCase):
    def test_runtime_representation(self):
        source = "define class P taking x\nend class\nset p to call new P with x = 1\n"
        interp = run_source(source)
        value = interp.global_env.get("p")
        self.assertIsInstance(value, Instance)
        self.assertIsInstance(interp.global_env.get("P"), ClassValue)
        self.assertEqual(value.fields, {"x": 1})
        self.assertEqual(value.class_obj.name, "P")

    def test_no_inheritance_state_in_first_version(self):
        source = "define class P taking x\nend class\n"
        interp = run_source(source)
        class_obj = interp.global_env.get("P")
        self.assertIsNone(class_obj.base)
        self.assertEqual(class_obj.all_fields(), ["x"])


if __name__ == "__main__":
    unittest.main()
