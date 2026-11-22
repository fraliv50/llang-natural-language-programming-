"""Differential harness: llang interpreter vs compiled WebAssembly.

Compiles each corpus program, executes the exported function in Node's WASM
runtime, and compares the result with the interpreter's value.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang import run_source  # noqa: E402
from llang.compiler import compile_source  # noqa: E402

# (compilable source, export name, arguments, interpreter call line, expected)
CORPUS = [
    ("define function f taking a, b\n    give back a plus b\nend function\n", "f", [20, 22], "show call f with a = 20, b = 22", "42"),
    ("define function f taking a, b\n    give back a minus b\nend function\n", "f", [10, 3], "show call f with a = 10, b = 3", "7"),
    ("define function f taking a, b\n    give back a times b\nend function\n", "f", [6, 7], "show call f with a = 6, b = 7", "42"),
    ("define function f taking a, b\n    give back a floor divided by b\nend function\n", "f", [17, 5], "show call f with a = 17, b = 5", "3"),
    ("define function f taking a, b\n    give back a modulo b\nend function\n", "f", [17, 5], "show call f with a = 17, b = 5", "2"),
    ("define function f taking a, b\n    give back a is greater than b\nend function\n", "f", [5, 3], "show call f with a = 5, b = 3", "true"),
    ("define function f taking a, b\n    give back a is at most b\nend function\n", "f", [5, 3], "show call f with a = 5, b = 3", "false"),
    ("define function f taking n\n    set r to 1\n    set i to 1\n    repeat while i is at most n\n        set r to r times i\n        set i to i plus 1\n    end repeat\n    give back r\nend function\n", "f", [6], "show call f with n = 6", "720"),
    ("set base to 100\n\ndefine function f taking x\n    give back base minus x\nend function\n", "f", [37], "show call f with x = 37", "63"),
    ("define function f taking n\n    set i to 0\n    repeat while i is less than n\n        set i to i plus 1\n        if i equals 4 then\n            stop the loop\n        end if\n    end repeat\n    give back i\nend function\n", "f", [100], "show call f with n = 100", "4"),
]


def main() -> int:
    node = __import__("shutil").which("node")
    if not node:
        print("node is required")
        return 1

    failures = 0
    with tempfile.TemporaryDirectory() as directory:
        wasm_path = Path(directory) / "module.wasm"
        for index, (source, export, arguments, call_line, expected) in enumerate(CORPUS):
            interpreter = run_source(source + call_line + "\n")
            if interpreter.output != [expected]:
                failures += 1
                print(f"case {index}: interpreter mismatch {interpreter.output} != {expected}")
                continue
            result = compile_source(source)
            if result.unsupported:
                failures += 1
                print(f"case {index}: compiler reported {result.unsupported}")
                continue
            wasm_path.write_bytes(result.wasm)
            completed = subprocess.run(
                [node, str(ROOT / "tools" / "run_wasm.js"), str(wasm_path), export,
                 *[str(argument) for argument in arguments]],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
            timeout=300)
            actual = completed.stdout.strip()
            if expected == "true" and actual == "1":
                actual = "true"
            if expected == "false" and actual == "0":
                actual = "false"
            if completed.returncode != 0 or actual != expected:
                failures += 1
                print(f"case {index}: wasm returned {actual!r}, wanted {expected!r}")

    print(f"compared {len(CORPUS)} programs, {failures} mismatches")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
