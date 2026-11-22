"""Compare lib/shlex.ll against CPython's stdlib shlex.

This is the verification harness for rewriting an open-source Python module in
llang. It generates a corpus, runs the llang implementation via the interpreter,
and diffs every result against the stdlib.
"""

import json
import shlex
import subprocess
import sys
import atexit
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

SPLIT_CASES = [
    "", " ", "a b", "  a   b  ", "a\tb\nc", "'a b'", '"a b"', "a\\ b",
    "a\\b", "'a'\"b\"", "a'b", '"a\\"b"', "#comment", "a # comment", "a#b",
    "''", '""', "\\", "'", '"', "a\\\\b", "hello world", "  leading",
    "trailing  ", "a=b", "/path/to/file", "user@host:/x", "a'b'c", "x='y z'",
    "echo 'hi there'", "ls -l /tmp", "café au lait", "a  'b c'  d",
    "\\$HOME", "a\\\nb", "'unclosed", '"unclosed', "a\\", "x='a b' y=\"c d\"",
]

QUOTE_CASES = [
    "", "a b", "a'b", "a;b", "a|b", "safe-string", "a$b", "a&b", 'a"b',
    "user@host:/path", "a+b=c", "a,b", "a%b", "a_b", "a.b/c", "a'b\"c",
]

JOIN_CASES = [
    ["echo", "hello world"],
    ["ls", "-l", "/tmp/my dir"],
    ["echo", "a'b"],
    ["python", "-c", "print(1)"],
]


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="llang_shlex_"))
    atexit.register(shutil.rmtree, work, ignore_errors=True)
    cases_path = work / "cases.json"
    results_path = work / "results.json"
    harness_path = work / "harness.ll"

    cases_path.write_text(json.dumps({
        "split": SPLIT_CASES,
        "quote": QUOTE_CASES,
        "join": JOIN_CASES,
    }, ensure_ascii=False), encoding="utf-8")

    def esc(path: Path) -> str:
        return str(path).replace("\\", "/")

    harness = f"""use the shlex module
use the foreign json module

set data to call loads from json with text = (call read text from with path = "{esc(cases_path)}")
set split_results to an empty list
set quote_results to an empty list
set join_results to an empty list

repeat for each case in item "split" of data
    set words to an empty list
    expect
        set words to call shell_words from shlex with input = case
    if a problem occurs then
        set words to a list of "ERROR"
    end expect
    add words to split_results
end repeat

repeat for each case in item "quote" of data
    add call shell_quote from shlex with value = case to quote_results
end repeat

repeat for each case in item "join" of data
    add call shell_join from shlex with words = case to join_results
end repeat

set payload to a map with "split" mapped to split_results, "quote" mapped to quote_results, "join" mapped to join_results
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
    for case, actual in zip(SPLIT_CASES, results["split"]):
        try:
            expected = shlex.split(case, posix=True)
        except ValueError:
            expected = ["ERROR"]
        if actual != expected:
            failures += 1
            print(f"SPLIT  {case!r}: got {actual!r}, want {expected!r}")

    for case, actual in zip(QUOTE_CASES, results["quote"]):
        expected = shlex.quote(case)
        if actual != expected:
            failures += 1
            print(f"QUOTE  {case!r}: got {actual!r}, want {expected!r}")

    for case, actual in zip(JOIN_CASES, results["join"]):
        expected = shlex.join(case)
        if actual != expected:
            failures += 1
            print(f"JOIN   {case!r}: got {actual!r}, want {expected!r}")

    total = len(SPLIT_CASES) + len(QUOTE_CASES) + len(JOIN_CASES)
    print(f"compared {total} cases, {failures} mismatches")
    if failures:
        sys.exit(1)
    print("lib/shlex.ll matches CPython shlex")


if __name__ == "__main__":
    main()
