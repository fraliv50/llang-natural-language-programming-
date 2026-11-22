"""Compare a small JavaScript corpus with its ported llang equivalent.

Usage: python tools/compare_js_port.py [--timeout 5]

For every snippet the JavaScript adapter produces llang, which is executed and
compared with the expected output lines.  When Node.js is installed the original
JavaScript is executed as an independent reference check.  External processes
are always run with a timeout; if Node is unavailable its checks are skipped
gracefully and only the llang side is verified.
"""

import argparse
import io
import re
import shutil
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang import run_source  # noqa: E402
from llang.portapp.adapters.javascript import JavaScriptAdapter  # noqa: E402

ADAPTER = JavaScriptAdapter()

CORPUS = [
    ("arithmetic", """
const a = 2 + 3 * 4;
console.log(a);
console.log(10 - 4);
console.log(7 % 4);
""", ["14", "6", "3"]),
    ("conditionals", """
let x = 4;
if (x > 5) {
    console.log("big");
} else if (x == 4) {
    console.log("four");
} else {
    console.log("other");
}
""", ["four"]),
    ("loops", """
let total = 0;
for (let i = 1; i <= 3; i = i + 1) {
    total = total + i;
}
console.log(total);
let j = 0;
while (j < 2) {
    console.log(j);
    j = j + 1;
}
""", ["6", "0", "1"]),
    ("functions", """
function double(n) {
    return n * 2;
}
console.log(double(7));
""", ["14"]),
    ("arrays", """
const xs = [5, 6, 7];
console.log(xs[0]);
console.log(xs[2]);
""", ["5", "7"]),
    ("strings_and_booleans", """
const name = "Ada";
const happy = true;
console.log(name);
console.log(happy);
console.log("ok");
""", ["Ada", "true", "ok"]),
]


def normalize(line: str) -> str:
    """Ignore cosmetic differences between JS and llang rendering."""
    text = "".join(line.split())
    if re.fullmatch(r"-?\d+\.0", text):
        text = text[:-2]  # llang prints 4.0 where JS prints 4
    return text


def compare(name: str, actual: list[str], expected: list[str]) -> bool:
    ok = [normalize(line) for line in actual] == [normalize(line)
                                                   for line in expected]
    if not ok:
        print(f"    expected: {expected!r}")
        print(f"    actual:   {actual!r}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare JS snippets with their ported llang output")
    parser.add_argument("--timeout", type=float, default=5.0,
                        help="timeout in seconds for each Node.js run")
    args = parser.parse_args()

    node = shutil.which("node")
    if node is None:
        print("Node.js not found - skipping JavaScript reference checks.")

    failures = 0
    for name, source, expected in CORPUS:
        result = ADAPTER.convert(source, f"{name}.js")
        if result.gaps:
            print(f"[FAIL] {name}: adapter reported gaps:")
            for gap in result.gaps:
                print(f"    - {gap}")
            failures += 1
            continue

        try:
            with redirect_stdout(io.StringIO()):
                interpreter = run_source(result.source)
            llang_output = list(interpreter.output)
        except Exception as exc:  # parse/runtime problems are failures
            print(f"[FAIL] {name}: llang error: {exc}")
            failures += 1
            continue

        llang_ok = compare(name, llang_output, expected)

        js_ok = True
        if node is not None:
            try:
                completed = subprocess.run(
                    [node, "-e", source], capture_output=True, text=True,
                    timeout=args.timeout, check=False)
            except subprocess.TimeoutExpired:
                print(f"[FAIL] {name}: Node timed out after {args.timeout}s")
                failures += 1
                continue
            if completed.returncode != 0:
                print(f"[FAIL] {name}: Node exited with "
                      f"{completed.returncode}: {completed.stderr.strip()}")
                failures += 1
                continue
            js_ok = compare(name, completed.stdout.splitlines(), expected)

        if llang_ok and js_ok:
            reference = " (Node reference OK)" if node is not None else ""
            print(f"[ OK ] {name}{reference}")
        else:
            failures += 1

    total = len(CORPUS)
    print(f"\n{total - failures}/{total} cases passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
