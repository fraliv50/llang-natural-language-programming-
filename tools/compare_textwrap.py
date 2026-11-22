"""Compare lib/textwrap.ll against CPython's stdlib textwrap.

This is the verification harness for rewriting the core of CPython's textwrap
module in llang. It generates a corpus of (text, width) pairs, runs the llang
implementation through the interpreter, and diffs both wrap() and fill()
against the stdlib for every case.

Only the documented subset is exercised: plain-space whitespace, no hyphens,
no tabs or newlines, and positive widths.
"""

import json
import subprocess
import sys
import atexit
import shutil
import tempfile
from pathlib import Path

import textwrap

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Texts deliberately contain only ordinary spaces (no tabs, newlines or
# hyphens) so they stay inside the subset implemented by lib/textwrap.ll.
TEXTS = [
    "",
    "x",
    "single",
    "hello world",
    "a b",
    "a b c d e f g h i j",
    "aa bb cc dd",
    "  leading whitespace",
    "trailing whitespace  ",
    "  both ends  ",
    "a   b",
    "one  two   three    four",
    "multiple     spaces     between     words",
    "supercalifragilisticexpialidocious",
    "short supercalifragilisticexpialidocious tail",
    "abcdefghijklmnopqrstuvwxyz",
    "The quick brown fox jumps over the lazy dog",
    "typical sentence with several words of different lengths",
    "punctuation! and, words. yes?",
    "1234567890 12345 123456789012345",
    "mixed CASE Words here",
    "tiny but mighty little words",
    " word ",
    "a  b",
]

# A spread of narrow and wide columns, including widths of 1 and 2 which
# force long words to be broken one character at a time.
WIDTH_SWEEP = [1, 2, 3, 4, 5, 7, 10, 15, 20, 40]

CASES = []
for text in TEXTS:
    for width in WIDTH_SWEEP:
        CASES.append({"text": text, "width": width})


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="llang_textwrap_"))
    atexit.register(shutil.rmtree, work, ignore_errors=True)
    cases_path = work / "cases.json"
    results_path = work / "results.json"
    harness_path = work / "harness.ll"

    cases_path.write_text(json.dumps(CASES, ensure_ascii=False), encoding="utf-8")

    def esc(path: Path) -> str:
        return str(path).replace("\\", "/")

    harness = f"""use the textwrap module
use the foreign json module

set data to call loads from json with text = (call read text from with path = "{esc(cases_path)}")
set wrap_results to an empty list
set fill_results to an empty list

repeat for each case in data
    set value to item "text" of case
    set columns to item "width" of case
    add (call wrap from textwrap with text = value, width = columns) to wrap_results
    add (call fill from textwrap with text = value, width = columns) to fill_results
end repeat

set payload to a map with "wrap" mapped to wrap_results, "fill" mapped to fill_results
call write text to with path = "{esc(results_path)}", content = (call dumps from json with value = payload)
"""
    harness_path.write_text(harness, encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(ROOT / "run.py"), str(harness_path)],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
    timeout=300)
    if completed.returncode != 0:
        print("llang run failed:")
        print(completed.stdout)
        print(completed.stderr)
        sys.exit(1)

    results = json.loads(results_path.read_text(encoding="utf-8"))

    failures = 0
    for case, actual_wrap, actual_fill in zip(CASES, results["wrap"], results["fill"]):
        text, width = case["text"], case["width"]
        expected_wrap = textwrap.wrap(text, width=width)
        expected_fill = textwrap.fill(text, width=width)
        if actual_wrap != expected_wrap:
            failures += 1
            print(f"WRAP  {text!r} width={width}: got {actual_wrap!r}, want {expected_wrap!r}")
        if actual_fill != expected_fill:
            failures += 1
            print(f"FILL  {text!r} width={width}: got {actual_fill!r}, want {expected_fill!r}")

    total = len(CASES)
    print(f"compared {total} cases, {failures} mismatches")
    if failures:
        sys.exit(1)
    print("lib/textwrap.ll matches CPython textwrap")


if __name__ == "__main__":
    main()
