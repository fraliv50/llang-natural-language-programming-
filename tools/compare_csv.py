"""Compare lib/csv.ll against CPython's stdlib csv (default excel dialect).

This is the verification harness for rewriting an open-source Python module in
llang. It generates a corpus, runs the llang implementation via the interpreter,
and diffs every result against the stdlib.
"""

import csv
import io
import json
import subprocess
import sys
import atexit
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Text fed to csv.reader().  Quoted fields, embedded commas/quotes/newlines,
# empty fields, empty rows, CRLF/LF endings and non-strict oddities included.
READ_CASES = [
    "",
    "a",
    "a,b,c\n",
    "a,b",
    "\n",
    "\r\n",
    "\n\n",
    "a\n\nb",
    "a,b\r\nc,d\r\n",
    "a\rb",
    '"a,b",c',
    '"a","b,c"',
    '"a""b"',
    '"""a"""',
    '"a"",""b"',
    "a,,b",
    ",",
    ",,",
    '"","",""',
    '"a\nb",c',
    '"a\r\nb"\nx',
    '"line1\nline2\nline3"',
    '"a"b',
    '"a" b',
    'a"b',
    ' "a" ',
    '"a',
    '"a""',
    "a,\n",
    "\n,",
    '"multi\nline",plain,"x""y"\nlast',
    "\r\n\na",
    "a\r\r\nb",
]

# Rows fed to csv.writer().  CPython renders each field with str(); llang uses
# `text of`, which agrees for the strings in this corpus.
WRITE_CASES = [
    [],
    [[]],
    [[""]],
    [["a"]],
    [["a", "b"]],
    [["a,b"]],
    [['a"b']],
    [["a\nb"]],
    [["a\rb"]],
    [["a\r\nb"]],
    [["", ""]],
    [["a", "b"], ["c", "d"]],
    [[" a ", " b"]],
    [["a,b", 'c"d', "e\nf"]],
    [['"']],
    [[","]],
    [["\n"]],
    [["\r"]],
    [["a"], [], ["b"]],
    [[""], [""]],
    [["tab\there"]],
    [["a", "", "b"]],
    [['x"y,z\nw']],
    [["", "a,b"]],
]


def expected_read(text: str):
    return list(csv.reader(io.StringIO(text, newline="")))


def expected_write(rows):
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    for row in rows:
        writer.writerow(row)
    return out.getvalue()


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="llang_csv_"))
    atexit.register(shutil.rmtree, work, ignore_errors=True)
    cases_path = work / "cases.json"
    results_path = work / "results.json"
    harness_path = work / "harness.ll"

    cases_path.write_text(json.dumps({
        "read": READ_CASES,
        "write": WRITE_CASES,
    }, ensure_ascii=False), encoding="utf-8")

    def esc(path: Path) -> str:
        return str(path).replace("\\", "/")

    harness = f"""use the csv module
use the foreign json module

set data to call loads from json with text = (call read text from with path = "{esc(cases_path)}")
set read_results to an empty list
set write_results to an empty list

repeat for each case in item "read" of data
    add (call read_rows from csv with text = case) to read_results
end repeat

repeat for each case in item "write" of data
    add (call write_rows from csv with rows = case) to write_results
end repeat

set payload to a map with "read" mapped to read_results, "write" mapped to write_results
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
    for case, actual in zip(READ_CASES, results["read"]):
        want = expected_read(case)
        if actual != want:
            failures += 1
            print(f"READ  {case!r}: got {actual!r}, want {want!r}")

    for case, actual in zip(WRITE_CASES, results["write"]):
        want = expected_write(case)
        if actual != want:
            failures += 1
            print(f"WRITE {case!r}: got {actual!r}, want {want!r}")

    total = len(READ_CASES) + len(WRITE_CASES)
    print(f"compared {total} cases, {failures} mismatches")
    if failures:
        sys.exit(1)
    print("lib/csv.ll matches CPython csv")


if __name__ == "__main__":
    main()
