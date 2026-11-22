"""JavaScript adapter tests: JS source -> canonical llang -> runtime output."""

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang import run_source  # noqa: E402
from llang.portapp.adapters import JavaScriptAdapter, adapter_for  # noqa: E402
from llang.portapp.models import Adapter  # noqa: E402

ADAPTER = JavaScriptAdapter()


def convert(source, path="sample.js"):
    """Convert a JS snippet and return (result, runtime output lines)."""
    result = ADAPTER.convert(source, path)
    with redirect_stdout(io.StringIO()):
        interpreter = run_source(result.source)
    return result, interpreter.output


class JavaScriptAdapterTests(unittest.TestCase):
    def test_registration_and_extensions(self):
        self.assertIsInstance(ADAPTER, Adapter)
        self.assertEqual(ADAPTER.name, "javascript")
        self.assertEqual(ADAPTER.extensions, ("js", "jsx", "mjs", "cjs"))
        for extension in ADAPTER.extensions:
            registered = adapter_for(f"module.{extension}")
            self.assertIsInstance(registered, JavaScriptAdapter)
            self.assertEqual(registered.name, "javascript")

    def test_declarations_literals_and_arithmetic(self):
        result, output = convert("""
        const a = 1 + 2 * 3;
        const b = 7 - 2;
        const c = 8 / 2;
        const d = 7 % 4;
        const s = "hello";
        const ok = true;
        const no = false;
        console.log(a);
        console.log(b);
        console.log(c);
        console.log(d);
        console.log(s);
        console.log(ok);
        console.log(no);
        """)
        self.assertEqual(result.gaps, [])
        self.assertTrue(result.complete)
        self.assertEqual(output,
                         ["7", "5", "4.0", "3", "hello", "true", "false"])
        # JS precedence is preserved by fully parenthesizing compound forms.
        self.assertIn("(1 plus (2 times 3))", result.source)

    def test_comparison_and_logic(self):
        result, output = convert("""
        const x = 3;
        console.log(x > 2);
        console.log(x <= 3);
        console.log(x == 3);
        console.log(x != 4);
        console.log(!(x > 5));
        console.log(x > 1 && x < 5);
        """)
        self.assertEqual(result.gaps, [])
        self.assertEqual(output, ["true"] * 6)
        self.assertIn("is greater than", result.source)
        self.assertIn("does not equal", result.source)
        self.assertIn("not ", result.source)

    def test_if_else_and_elseif(self):
        result, output = convert("""
        let x = 7;
        if (x > 10) {
            console.log("high");
        } else if (x > 5) {
            console.log("mid");
        } else {
            console.log("low");
        }
        """)
        self.assertEqual(result.gaps, [])
        self.assertEqual(output, ["mid"])
        self.assertIn("otherwise if", result.source)
        self.assertIn("end if", result.source)

    def test_while_and_for_loops(self):
        result, output = convert("""
        let i = 0;
        while (i < 2) {
            console.log(i);
            i = i + 1;
        }
        for (let j = 0; j < 3; j = j + 1) {
            console.log(j);
        }
        for (let k = 0; k < 2; k++) {
            console.log(k);
        }
        """)
        self.assertEqual(result.gaps, [])
        self.assertEqual(output, ["0", "1", "0", "1", "2", "0", "1"])
        self.assertEqual(result.source.count("repeat while"), 3)
        self.assertEqual(result.source.count("end repeat"), 3)

    def test_function_parameters_return_and_labeled_call(self):
        result, output = convert("""
        function add(a, b) {
            return a + b;
        }
        console.log(add(2, 3));
        """)
        self.assertEqual(result.gaps, [])
        self.assertEqual(output, ["5"])
        self.assertIn("define function", result.source)
        self.assertIn("taking a, b", result.source)
        # `add` is reserved in llang, so the emitted name is escaped.
        self.assertIn("with a = 2, b = 3", result.source)
        self.assertIn("give back (a plus b)", result.source)

    def test_array_literals_and_indexing(self):
        result, output = convert("""
        const xs = [10, 20, 30];
        console.log(xs[0]);
        console.log(xs[2]);
        const empty = [];
        console.log(empty);
        """)
        self.assertEqual(result.gaps, [])
        self.assertEqual(output, ["10", "30", "[]"])
        self.assertIn("(a list of 10, 20, 30)", result.source)
        self.assertIn("(an empty list)", result.source)
        self.assertIn("(item 0 of xs)", result.source)

    def test_reserved_word_identifiers_are_escaped(self):
        result, output = convert("""
        const set = "safe";
        console.log(set);
        """)
        self.assertEqual(result.gaps, [])
        self.assertEqual(output, ["safe"])
        self.assertIn("set set_ to", result.source)
        self.assertIn("show set_", result.source)

    def test_gaps_for_unsupported_constructs(self):
        result = ADAPTER.convert("""
        class A {}
        const f = (x) => x + 1;
        async function g() {}
        const s = `hi ${name}`;
        """, "unsupported.js")
        node_types = [gap.node_type for gap in result.gaps]
        self.assertIn("class_declaration", node_types)
        self.assertIn("arrow_function", node_types)
        self.assertIn("function_declaration", node_types)  # the async function
        self.assertIn("template_string", node_types)
        self.assertFalse(result.complete)
        async_gap = next(g for g in result.gaps if "async" in g.reason)
        self.assertIn("async", async_gap.reason)
        for gap in result.gaps:
            self.assertIsInstance(gap.line, int)
            self.assertGreater(gap.line, 0)
            self.assertTrue(gap.source_snippet.strip())
        # Gaps are visible in the emitted llang rather than silently dropped.
        self.assertIn("# GAP", result.source)
        self.assertIn("class A {}", result.source)

    def test_unsupported_statement_still_yields_parseable_llang(self):
        result = ADAPTER.convert(
            "for (const x of xs) { console.log(x); }\n", "loop.js")
        self.assertTrue(result.gaps)
        self.assertTrue(any(g.node_type == "for_in_statement"
                            for g in result.gaps))
        # The comment-only output must still be valid llang.
        with redirect_stdout(io.StringIO()):
            run_source(result.source)


if __name__ == "__main__":
    unittest.main()
