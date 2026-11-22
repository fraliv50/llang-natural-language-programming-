"""Lint-pass tests. Run with: python -m unittest discover -s tests -v"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llang import Lexer, Parser, lint_program, lint_source  # noqa: E402
from llang.linter import Diagnostic  # noqa: E402


def _messages(diagnostics):
    return [d.message for d in diagnostics]


class CleanProgramTests(unittest.TestCase):
    def test_clean_program_has_no_diagnostics(self):
        source = """
define function double taking n
    give back n plus n
end function
set x to 5
show call double with n = x
require x is greater than 0
repeat for each counter in a list of 1, 2
    show counter
end repeat
"""
        self.assertEqual(lint_source(source), [])

    def test_forward_function_reference_is_clean(self):
        source = """
show call later with n = 1
define function later taking n
    give back n
end function
"""
        self.assertEqual(lint_source(source), [])

    def test_global_defined_after_function_is_clean(self):
        # A function body is checked where it is defined, but globals may be
        # assigned later — that must not be reported as an undefined name.
        source = """
define function f taking x
    show g
    give back x
end function
set g to 9
show call f with x = 1
"""
        self.assertEqual(lint_source(source), [])

    def test_lint_program_matches_lint_source(self):
        source = 'set x to 1\nshow x\nshow missing'
        program = Parser(Lexer(source).tokenize()).parse_program()
        self.assertEqual(_messages(lint_program(program)),
                         _messages(lint_source(source)))


class UndefinedNameTests(unittest.TestCase):
    def test_undefined_variable(self):
        diagnostics = lint_source("show missing")
        self.assertTrue(any("Undefined name 'missing'" in m
                            for m in _messages(diagnostics)))
        self.assertTrue(all(isinstance(d, Diagnostic) for d in diagnostics))
        self.assertTrue(all(d.severity == "error" for d in diagnostics))

    def test_use_before_global_assignment(self):
        diagnostics = lint_source("show x\nset x to 5")
        self.assertIn("Undefined name 'x'", _messages(diagnostics))

    def test_undefined_name_inside_expression(self):
        diagnostics = lint_source("set x to y plus 1")
        self.assertIn("Undefined name 'y'", _messages(diagnostics))


class DuplicateDefinitionTests(unittest.TestCase):
    def test_duplicate_function_name(self):
        source = """
define function f taking x
    give back x
end function
define function f taking y
    give back y
end function
"""
        messages = _messages(lint_source(source))
        self.assertTrue(any("Function 'f' is defined more than once" in m
                            for m in messages), messages)

    def test_duplicate_alias_across_functions(self):
        source = """
define function f taking x
also known as g
    give back x
end function
define function g taking y
    give back y
end function
"""
        messages = _messages(lint_source(source))
        self.assertTrue(any("Function 'g' is defined more than once" in m
                            for m in messages), messages)

    def test_local_binding_shadows_function(self):
        source = """
define function f taking x
    give back x
end function
set f to 3
"""
        messages = _messages(lint_source(source))
        self.assertTrue(any("shadows function" in m for m in messages), messages)

    def test_parameter_shadows_function(self):
        source = """
define function f taking x
    give back x
end function
define function g taking f
    give back f
end function
"""
        messages = _messages(lint_source(source))
        self.assertTrue(any("shadows function 'f'" in m for m in messages),
                        messages)


class UnreachableCodeTests(unittest.TestCase):
    def test_after_return(self):
        source = """
define function f taking x
    give back x
    show "dead"
end function
"""
        self.assertTrue(any("Unreachable code after 'give back'" in m
                            for m in _messages(lint_source(source))))

    def test_after_fail(self):
        diagnostics = lint_source('fail with oops, "bad"\nshow "dead"')
        self.assertTrue(any("Unreachable code after 'fail'" in m
                            for m in _messages(diagnostics)))

    def test_after_stop_the_loop(self):
        source = """
repeat while true
    stop the loop
    show "dead"
end repeat
"""
        self.assertTrue(any("Unreachable code after 'stop the loop'" in m
                            for m in _messages(lint_source(source))))

    def test_after_skip_to_next_item(self):
        source = """
repeat while true
    skip to the next item
    show "dead"
end repeat
"""
        self.assertTrue(any("Unreachable code after 'skip to the next item'" in m
                            for m in _messages(lint_source(source))))

    def test_terminator_in_branch_does_not_mark_later_statements(self):
        source = """
set x to 1
if x equals 1 then
    give back x
end if
show x
"""
        self.assertEqual(lint_source(source), [])


class CallTests(unittest.TestCase):
    def test_unknown_call(self):
        diagnostics = lint_source("call mystery with x = 1")
        self.assertTrue(any("unknown function or builtin 'mystery'" in m
                            for m in _messages(diagnostics)),
                        _messages(diagnostics))
        self.assertTrue(any(d.severity == "error" for d in diagnostics))

    def test_known_builtin_and_function_calls(self):
        source = """
define function f taking x
    give back x
end function
show call sum with items = a list of 1, 2
show call f with x = 1
"""
        self.assertEqual(lint_source(source), [])


class RequireTests(unittest.TestCase):
    def test_literal_true_warning(self):
        diagnostics = lint_source("require true")
        self.assertTrue(any("literal true" in m for m in _messages(diagnostics)))
        self.assertTrue(all(d.severity == "warning" for d in diagnostics))

    def test_non_literal_condition_is_clean(self):
        self.assertEqual(lint_source("require 1 is a number"), [])


class ShadowBuiltinTests(unittest.TestCase):
    def test_assignment_shadows_builtin(self):
        diagnostics = lint_source("set sum to 5\nshow sum")
        self.assertTrue(any("shadows a builtin" in m
                            for m in _messages(diagnostics)),
                        _messages(diagnostics))
        self.assertTrue(all(d.severity == "warning" for d in diagnostics))

    def test_function_param_and_loop_var_shadow_builtins(self):
        source = """
define function sum taking text
    give back text
end function
repeat for each keys in a list of 1
    show keys
end repeat
"""
        messages = _messages(lint_source(source))
        self.assertEqual(sum("shadows a builtin" in m for m in messages), 3,
                         messages)


class DiagnosticShapeTests(unittest.TestCase):
    def test_positions_come_from_ast(self):
        diagnostics = lint_source("# a comment\nshow missing")
        self.assertEqual(len(diagnostics), 1)
        self.assertIsNotNone(diagnostics[0].pos)
        self.assertEqual(diagnostics[0].pos.line, 2)

    def test_severities_are_limited_and_messages_nonempty(self):
        source = """
set sum to 1
require true
call unknown_thing with x = 1
show missing
fail with oops
show "dead"
"""
        diagnostics = lint_source(source)
        self.assertTrue(diagnostics)
        for d in diagnostics:
            self.assertIn(d.severity, ("error", "warning"))
            self.assertTrue(d.message)


if __name__ == "__main__":
    unittest.main()
