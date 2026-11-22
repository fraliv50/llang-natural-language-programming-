"""Compiler tests: compile llang to WebAssembly and execute it in Node."""

import base64
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang.compiler import compile_source  # noqa: E402

NODE = shutil.which("node")
RUNNER = ROOT / "tools" / "run_wasm.js"


@unittest.skipUnless(NODE, "Node.js is required to execute WebAssembly")
class CompilerTests(unittest.TestCase):
    def execute(self, source, export, *args):
        result = compile_source(source)
        self.assertEqual(result.unsupported, [])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "module.wasm"
            path.write_bytes(result.wasm)
            completed = subprocess.run(
                [NODE, str(RUNNER), str(path), export, *[str(arg) for arg in args]],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
            timeout=300)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            return int(completed.stdout.strip())

    def test_arithmetic(self):
        source = """
define function sum_two taking a, b
    give back a plus b
end function
"""
        self.assertEqual(self.execute(source, "sum_two", 20, 22), 42)

    def test_factorial_with_while(self):
        source = """
define function fact taking n
    set result to 1
    set i to 1
    repeat while i is at most n
        set result to result times i
        set i to i plus 1
    end repeat
    give back result
end function
"""
        self.assertEqual(self.execute(source, "fact", 5), 120)

    def test_if_else(self):
        source = """
define function choose taking n
    if n is at least 10 then
        give back 1
    otherwise
        give back 0
    end if
end function
"""
        self.assertEqual(self.execute(source, "choose", 10), 1)
        self.assertEqual(self.execute(source, "choose", 3), 0)

    def test_global(self):
        source = """
set base to 10

define function use_base taking extra
    give back base plus extra
end function
"""
        self.assertEqual(self.execute(source, "use_base", 5), 15)

    def test_break_and_continue(self):
        source = """
define function first_big taking n
    set i to 0
    repeat while i is less than n
        set i to i plus 1
        if i equals 3 then
            stop the loop
        end if
    end repeat
    give back i
end function

define function skip_even taking n
    set total to 0
    set i to 0
    repeat while i is less than n
        set i to i plus 1
        if (i modulo 2) equals 0 then
            skip to the next item
        end if
        set total to total plus i
    end repeat
    give back total
end function
"""
        self.assertEqual(self.execute(source, "first_big", 10), 3)
        self.assertEqual(self.execute(source, "skip_even", 5), 9)

    def test_binary_output_is_valid_wasm(self):
        result = compile_source("define function f taking x\n    give back x\nend function\n")
        self.assertTrue(result.wasm.startswith(b"\x00asm\x01\x00\x00\x00"))
        self.assertGreater(result.stats["bytes"], 8)

    def test_call_arity_mismatch_is_reported(self):
        result = compile_source("""
define function f taking a, b
    give back a plus b
end function
define function g taking x
    give back call f with b = x
end function
""")
        self.assertTrue(result.unsupported)
        self.assertTrue(any("expected" in item.reason for item in result.unsupported))

    def test_unsupported_is_reported(self):
        result = compile_source('define function f taking x\n    show "text"\nend function\n')
        self.assertTrue(result.unsupported)
        self.assertTrue(any("integer literals" in item.reason for item in result.unsupported))

    def test_wasm_can_be_base64_encoded(self):
        result = compile_source("define function f taking x\n    give back x\nend function\n")
        self.assertIsInstance(base64.b64encode(result.wasm), bytes)


if __name__ == "__main__":
    unittest.main()
