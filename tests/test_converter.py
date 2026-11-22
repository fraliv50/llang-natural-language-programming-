"""Converter tests: Python source -> llang -> runtime output, diffed against Python."""

import io
import re
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang import run_source  # noqa: E402
from llang.converter import convert_source  # noqa: E402
from llang.formatter import format_source  # noqa: E402


def roundtrip(python_source):
    result = convert_source(python_source)
    llang_source = format_source(result.source)
    interpreter = run_source(llang_source)

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exec(python_source, {})
    python_output = []
    for line in buffer.getvalue().splitlines():
        line = line.replace("True", "true").replace("False", "false")
        line = re.sub(r"'([^']*)'", r"\1", line)
        python_output.append(line)
    return interpreter.output, python_output, result


class ConverterTests(unittest.TestCase):
    def assertSame(self, source):
        llang_output, python_output, result = roundtrip(source)
        self.assertEqual(result.unsupported, [])
        self.assertEqual(llang_output, python_output)
        return result

    def test_arithmetic_and_prints(self):
        self.assertSame("""
print(1 + 2)
print(10 - 4)
print(3 * 5)
print(8 / 2)
print(7 % 4)
print(2 ** 3)
""")

    def test_variables_and_while(self):
        self.assertSame("""
i = 0
while i < 4:
    print(i)
    i += 1
""")

    def test_functions_and_for(self):
        self.assertSame("""
def total(values):
    result = 0
    for value in values:
        result += value
    return result

print(total([1, 2, 3]))
""")

    def test_if_elif_else(self):
        self.assertSame("""
def grade(n):
    if n >= 90:
        return "A"
    elif n >= 80:
        return "B"
    else:
        return "C"

print(grade(95))
print(grade(85))
print(grade(10))
""")

    def test_comparisons_and_logic(self):
        self.assertSame("""
print(1 < 2 and 3 > 2)
print(1 == 2 or 2 == 2)
print(not False)
print(2 in [1, 2, 3])
""")

    def test_strings_and_methods(self):
        self.assertSame("""
s = "  Hello World  "
print(s.strip())
print(s.strip().lower())
print(s.strip().upper())
print(s.strip().split(" "))
print("-".join(["a", "b"]))
""")

    def test_dicts_and_indexing(self):
        self.assertSame("""
scores = {"Ada": 10, "Grace": 20}
print(scores["Ada"])
print(len(scores))
""")

    def test_fstring(self):
        self.assertSame("""
name = "Ada"
print(f"Hello {name}!")
""")

    def test_exceptions(self):
        llang_output, python_output, result = roundtrip("""
def risky(flag):
    if flag:
        raise ValueError("boom")
    return "ok"

try:
    print(risky(True))
except ValueError:
    print("caught")
finally:
    print("cleanup")
""")
        self.assertEqual(llang_output, ["caught", "cleanup"])
        self.assertEqual(python_output, ["caught", "cleanup"])

    def test_unsupported_report(self):
        source = """
class Foo:
    pass

xs = [1, 2, 3]
print(xs[0:2:1])
print([x * 2 for x in xs])
"""
        result = convert_source(source)
        self.assertTrue(result.unsupported)
        kinds = {item.node_type for item in result.unsupported}
        self.assertIn("ClassDef", kinds)
        self.assertIn("ListComp", kinds)
        self.assertTrue(any("slice steps" in item.reason for item in result.unsupported)
                        or any("slicing" in item.reason for item in result.unsupported))

    def test_coverage_is_reported(self):
        result = convert_source("print(1 + 2)")
        self.assertEqual(result.covered, 100.0)
        self.assertEqual(result.stats["nodes"] > 0, True)


if __name__ == "__main__":
    unittest.main()
