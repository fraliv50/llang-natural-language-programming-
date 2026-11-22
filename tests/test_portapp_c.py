"""C source -> canonical English llang adapter tests.

Every snippet is ported with :class:`~llang.portapp.adapters.c.CAdapter`, the
generated llang is parsed and executed with ``run_source`` and the output is
compared with the value a C compiler would produce.  Unsupported constructs are
checked as explicit gaps with line numbers and source snippets.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang import run_source  # noqa: E402
from llang.portapp.adapters import adapter_for  # noqa: E402
from llang.portapp.adapters.c import CAdapter  # noqa: E402
from llang.portapp.models import ConversionResult  # noqa: E402


def port(source, path="example.c"):
    return CAdapter().convert(source, path)


def output(result):
    """Parse and run generated llang; return its recorded output lines."""
    return run_source(result.source).output


class CAdapterRegistrationTests(unittest.TestCase):
    def test_registered_for_c_and_h(self):
        self.assertIsInstance(adapter_for("program.c"), CAdapter)
        self.assertIsInstance(adapter_for("header.h"), CAdapter)
        self.assertEqual(adapter_for("program.py").__class__.__name__, "PythonAdapter")

    def test_adapter_metadata_and_result_shape(self):
        adapter = CAdapter()
        self.assertEqual(adapter.name, "c")
        self.assertEqual(adapter.extensions, ("c", "h"))
        result = adapter.convert("int main(void) { return 0; }", "empty.c")
        self.assertIsInstance(result, ConversionResult)
        self.assertEqual(result.source_language, "c")
        self.assertEqual(result.gaps, [])
        self.assertTrue(result.complete)
        self.assertEqual(result.covered, 100.0)
        self.assertGreater(result.stats["nodes"], 0)


class CTranslationTests(unittest.TestCase):
    def test_variables_arithmetic_and_printf(self):
        result = port("""
#include <stdio.h>
int main(void) {
    int a = 7;
    unsigned int u = 3;
    double d = 2.5;
    printf("%d\\n", a + u);
    printf("%d\\n", a - u);
    printf("%d\\n", a * u);
    printf("%d\\n", a / 2);
    printf("%d\\n", a % 4);
    printf("%g\\n", d / 2.0);
    return 0;
}
""")
        self.assertEqual(result.gaps, [])
        self.assertIn("(a plus u)", result.source)
        self.assertIn("call main", result.source)
        self.assertEqual(output(result),
                         ["10", "4", "21", "3", "3", "1.25"])

    def test_comparisons_if_else_if_and_while(self):
        result = port("""
int sign(int n) {
    if (n > 0) { return 1; }
    else if (n < 0) { return -1; }
    else { return 0; }
}
int main(void) {
    int i = 3;
    while (i > 0) { printf("%d", i); i--; }
    printf("\\n");
    printf("%d %d %d\\n", sign(-2), sign(0), sign(5));
    return 0;
}
""")
        self.assertEqual(result.gaps, [])
        self.assertIn("otherwise if", result.source)
        self.assertIn("repeat while", result.source)
        self.assertIn("end repeat", result.source)
        self.assertIn("end if", result.source)
        self.assertEqual(output(result), ["3", "2", "1", "\n", "-1 0 1"])

    def test_functions_use_single_word_names_and_labeled_calls(self):
        result = port("""
int combine(int a, int b) { return a + b; }
int square(int x) { return combine(x, x); }
int main(void) { printf("%d\\n", square(6)); return 0; }
""")
        self.assertEqual(result.gaps, [])
        self.assertIn("define function combine taking a, b", result.source)
        self.assertIn("give back (a plus b)", result.source)
        self.assertIn("call combine with a = x, b = x", result.source)
        self.assertIn("end function", result.source)
        self.assertEqual(output(result), ["12"])

    def test_simple_arrays_and_for_loops(self):
        result = port("""
int main(void) {
    int xs[4] = {4, 5};
    for (int i = 0; i < 4; i++) { xs[i] = xs[i] + 1; }
    for (int j = 0; j < 4; j++) { printf("%d\\n", xs[j]); }
    return 0;
}
""")
        self.assertEqual(result.gaps, [])
        self.assertIn("set xs to (a list of 4, 5, 0, 0)", result.source)
        self.assertIn("set item i of xs to ((item i of xs) plus 1)", result.source)
        self.assertEqual(output(result), ["5", "6", "1", "1"])

    def test_integer_division_and_remainder_follow_c(self):
        result = port("""
int main(void) {
    printf("%d %d\\n", -7 / 2, -7 % 2);
    printf("%d %d\\n", 7 / -2, 7 % -2);
    printf("%d %d\\n", -7 / -2, -7 % -2);
    return 0;
}
""")
        self.assertEqual(result.gaps, [])
        self.assertEqual(output(result),
                         ["-3 -1", "-3 1", "3 -1"])

    def test_uninitialized_scalars_get_defaults(self):
        result = port("""
int main(void) {
    int a;
    double d;
    printf("%d %d\\n", a, 1);
    return 0;
}
""")
        self.assertEqual(result.gaps, [])
        self.assertIn("set a to 0", result.source)
        self.assertIn("set d to 0.0", result.source)
        self.assertEqual(output(result), ["0 1"])

    def test_reserved_identifiers_are_renamed(self):
        result = port("""
int main(void) {
    int end = 4;
    int call = 5;
    printf("%d\\n", end + call);
    return 0;
}
""")
        self.assertEqual(result.gaps, [])
        self.assertIn("set end_ to 4", result.source)
        self.assertIn("set call_ to 5", result.source)
        self.assertEqual(output(result), ["9"])

    def test_headers_are_notes_not_gaps(self):
        result = port("#include <stdio.h>\nint main(void) { return 0; }\n")
        self.assertEqual(result.gaps, [])
        self.assertTrue(any(item.node_type == "PreprocessorInclude"
                            for item in result.notes))


class CGapTests(unittest.TestCase):
    def test_pointers_structs_and_macros_are_gapped(self):
        result = port("""#define TWICE(x) ((x) + (x))
struct Point { int x; int y; };
int main(void) {
    int value = 3;
    int *p = &value;
    struct Point point;
    return *p;
}
""")
        kinds = {gap.node_type for gap in result.gaps}
        self.assertIn("PreprocessorDirective", kinds)
        self.assertTrue(any("pointer" in gap.reason.lower() for gap in result.gaps))
        self.assertTrue(any("struct" in gap.reason.lower() for gap in result.gaps))
        self.assertTrue(all(gap.line is not None for gap in result.gaps))
        self.assertTrue(all(gap.source_snippet for gap in result.gaps))
        snippets = [gap.source_snippet for gap in result.gaps]
        self.assertTrue(any("#define" in snippet for snippet in snippets))
        self.assertTrue(any("struct Point" in snippet for snippet in snippets))
        self.assertTrue(any("*p" in snippet for snippet in snippets))
        self.assertFalse(result.complete)
        self.assertLess(result.covered, 100.0)
        # The partial translation is still valid, runnable llang.
        self.assertEqual(output(result), [])

    def test_unsupported_operator_becomes_a_gap(self):
        result = port("int main(void) { int a = 6; return a & 3; }\n")
        self.assertEqual(len(result.gaps), 1)
        self.assertEqual(result.gaps[0].node_type, "BinaryOp")
        self.assertIn("&", result.gaps[0].reason)
        self.assertEqual(result.gaps[0].line, 1)
        self.assertIn("a & 3", result.gaps[0].source_snippet)
        self.assertEqual(output(result), [])

    def test_do_while_and_switch_are_gapped(self):
        result = port("""
int main(void) {
    int i = 0;
    do { i++; } while (i < 2);
    switch (i) { case 1: i = 2; break; default: i = 3; }
    return 0;
}
""")
        kinds = {gap.node_type for gap in result.gaps}
        self.assertIn("DoWhile", kinds)
        self.assertIn("Switch", kinds)
        self.assertTrue(all(gap.line and gap.source_snippet for gap in result.gaps))

    def test_parse_error_is_gapped_instead_of_raising(self):
        result = port("int main(void) { return @; }\n")
        self.assertEqual(len(result.gaps), 1)
        self.assertEqual(result.gaps[0].node_type, "ParseError")
        self.assertEqual(result.gaps[0].line, 1)
        self.assertIn("@", result.gaps[0].source_snippet)
        self.assertEqual(output(result), [])

    def test_unknown_function_call_is_gapped(self):
        result = port("int main(void) { mystery(1, 2); return 0; }\n")
        self.assertTrue(any("unknown function" in gap.reason
                            for gap in result.gaps))
        self.assertEqual(output(result), [])

    def test_function_pointers_and_casts_are_gapped(self):
        result = port("""
int main(void) {
    double d = 2.9;
    int n = (int)d;
    return n;
}
""")
        self.assertTrue(any(gap.node_type == "Cast" for gap in result.gaps))
        self.assertEqual(output(result), [])


if __name__ == "__main__":
    unittest.main()
