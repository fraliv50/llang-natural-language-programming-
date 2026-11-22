"""Compare lib/fnmatch.ll against CPython's stdlib fnmatch.

This is the verification harness for the fnmatch rewrite. It generates a
corpus of (name, pattern) pairs, runs the llang implementation through the
interpreter, and diffs every boolean against stdlib fnmatch.fnmatchcase.
"""

import fnmatch
import json
import subprocess
import sys
import atexit
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

# (name, pattern) pairs covering literal text, empty strings, '*', '?',
# [seq], [!seq], ranges, leading ']' / '!', unclosed brackets and mixtures.
CASES = [
    # literal text and empty strings
    ("", ""), ("abc", "abc"), ("abc", "abcd"), ("abcd", "abc"),
    ("a.b", "a.b"), ("a.b", "axb"), ("file.txt", "file.txt"),
    ("foo*bar", "foo*bar"), ("a+b", "a+b"), ("x^y", "x^y"),
    ("a|b", "a|b"), ("a(b)", "a(b)"), ("a\\b", "a\\b"),
    # stars
    ("anything", "*"), ("", "*"), ("abc", "a*"), ("abc", "*c"),
    ("abc", "*b*"), ("abc", "a*c"), ("abc", "a**c"), ("abc", "***"),
    ("abc", "*a*b*c*"), ("aaa", "a*a"), ("", "a*"), ("abcabc", "*abc*"),
    ("hello world.txt", "*.txt"), ("a\nb", "a*b"), ("x\ny", "x*z"),
    # question marks
    ("a", "?"), ("", "?"), ("ab", "??"), ("abc", "???"),
    ("abcd", "??"), ("a5b", "a?b"), ("cat", "c?t"), ("cat", "c??"),
    ("\n", "?"),
    # classes and ranges
    ("a", "[abc]"), ("b", "[abc]"), ("d", "[abc]"), ("", "[abc]"),
    ("5", "[0-9]"), ("x", "[0-9]"), ("m", "[a-z]"), ("M", "[a-z]"),
    ("M", "[a-zA-Z]"), ("7", "[a-zA-Z0-9]"), ("_", "[a-z0-9_]"),
    ("c", "[a-c]"), ("d", "[a-c]"), ("-", "[-a]"), ("a", "[a-]"),
    ("]", "[]]"), ("a", "[]a]"), ("[", "[[]"), ("^", "[^a]"),
    ("a", "[^a]"),
    # negation
    ("d", "[!abc]"), ("a", "[!abc]"), ("5", "[!a-z]"), ("m", "[!a-z]"),
    ("x", "[!0-9]"), ("5", "[!0-9]"), ("a", "[!]]"), ("]", "[!]]"),
    ("!", "[!!]"), ("a", "[!!]"),
    # unclosed brackets are literal
    ("[abc", "[abc"), ("[", "["), ("a", "[abc"), ("[]", "[]"),
    ("[!]", "[!]"), ("a[b", "a[b"),
    # mixtures
    ("file1.txt", "file[0-9].txt"), ("filex.txt", "file[0-9].txt"),
    ("a5b6c", "a[0-9]b[0-9]c"), ("abc.txt", "*.[ch]"),
    ("abc.h", "*.[ch]"), ("abc.py", "*.[ch]"), ("AbC", "[a-zA-Z]*"),
    ("fooX123", "foo[!0-9]*"), ("foo123", "foo[!0-9]*"),
    ("a.css", "*.css"), ("style.css", "*.css"), ("b", "[a-c]*"),
]


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="llang_fnmatch_"))
    atexit.register(shutil.rmtree, work, ignore_errors=True)
    cases_path = work / "cases.json"
    results_path = work / "results.json"
    harness_path = work / "harness.ll"

    cases_path.write_text(
        json.dumps([[name, pattern] for name, pattern in CASES],
                   ensure_ascii=False),
        encoding="utf-8",
    )

    def esc(path: Path) -> str:
        return str(path).replace("\\", "/")

    harness = f"""use the fnmatch module
use the foreign json module

set cases to call loads from json with text = (call read text from with path = "{esc(cases_path)}")
set results to an empty list

repeat for each case in cases
    set candidate to item 0 of case
    set pattern to item 1 of case
    add (call fnmatchcase from fnmatch with name = candidate, pattern = pattern) to results
end repeat

call write text to with path = "{esc(results_path)}", content = (call dumps from json with value = results)
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
    for (name, pattern), actual in zip(CASES, results):
        expected = fnmatch.fnmatchcase(name, pattern)
        if actual != expected:
            failures += 1
            print(f"CASE name={name!r} pattern={pattern!r}: got {actual!r}, want {expected!r}")

    total = len(CASES)
    print(f"compared {total} cases, {failures} mismatches")
    if failures:
        sys.exit(1)
    print("lib/fnmatch.ll matches CPython fnmatch.fnmatchcase")


if __name__ == "__main__":
    main()
