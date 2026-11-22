"""Compare lib/json.ll against CPython's stdlib json.

This is the verification harness for the native llang JSON module. It builds a
corpus of values, feeds their stdlib-encoded JSON to the llang parser, serializes
the results with the llang serializer, and diffs every result against the
stdlib. No foreign bridge is used by the llang side.
"""

import json
import subprocess
import sys
import atexit
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

CASES = [
    None, True, False,
    0, 1, -1, 42, 3.5, -3.5, 0.0, -0.0,
    1e20, 1e-7, 2.2250738585072014e-308, 12345678901234567890,
    float("nan"), float("inf"), float("-inf"),
    "", "hello", "a b c", "caf\u00e9 \u2603 \u4e2d\u6587", "\U0001f600 emoji",
    'quotes " and backslash \\ and slash /',
    "controls \b \f \n \r \t \u0000 \u001f \u007f",
    "tab\tnewline\nreturn\r", " leading and trailing ",
    [], [1, 2, 3], [True, False, None], ["a", "b"],
    [[1, 2], [3, [4, 5]]], [{"x": 1}, {"x": 2}],
    {}, {"a": 1}, {"b": 2, "a": 1},
    {"name": "Ada", "age": 36, "active": True, "nickname": None},
    {"inner": {"deep": {"value": [1, 2, {"deepest": True}]}}},
    {"\u00e9": "\u4e2d", "\U0001f600": "emoji key", "": "empty key"},
    {"list": [None, [], {}, "", 0, False]},
    [0.1, 0.2, 0.3, 1e100, 1e-100],
    {"a": [[], {}, [[]], {"b": {"c": []}}], "z": "last"},
    "x" * 300,
]

# Texts whose stdlib encoding uses literal \uXXXX escapes (ensure_ascii=True).
ESCAPE_TEXTS = [
    json.dumps(s) for s in [
        "caf\u00e9", "\u4e2d\u6587", "\u2603 \u263a \uffff",
        "\u0000\u0001\b\f\n\r\t\u001f", "\ud83d\ude00", "\U0001f4a9",
        "\\u0041 is not really an escape", '"quoted" \\ backslash / slash',
        "\u00a0\u2003\u2028\u2029",
    ]
]

TEXTS = [json.dumps(value, ensure_ascii=False) for value in CASES]


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="llang_json_"))
    atexit.register(shutil.rmtree, work, ignore_errors=True)
    corpus_path = work / "corpus.json"
    texts_path = work / "texts.json"
    escape_path = work / "escapes.json"
    results_path = work / "results.json"
    harness_path = work / "harness.ll"

    corpus_path.write_text(json.dumps(CASES, ensure_ascii=False), encoding="utf-8")
    texts_path.write_text(json.dumps(TEXTS, ensure_ascii=False), encoding="utf-8")
    escape_path.write_text(json.dumps(ESCAPE_TEXTS, ensure_ascii=False), encoding="utf-8")

    def esc(path: Path) -> str:
        return str(path).replace("\\", "/")

    harness = f"""use the json module

set corpus to call parse from json with text = (call read text from with path = "{esc(corpus_path)}")
set texts to call parse from json with text = (call read text from with path = "{esc(texts_path)}")
set escape_texts to call parse from json with text = (call read text from with path = "{esc(escape_path)}")

set serialized to an empty list
repeat for each value in corpus
    add (call stringify from json with value = value) to serialized
end repeat

set roundtrip to an empty list
repeat for each text in texts
    add (call stringify from json with value = (call parse from json with text = text)) to roundtrip
end repeat

set decoded to an empty list
repeat for each text in escape_texts
    add (call stringify from json with value = (call parse from json with text = text)) to decoded
end repeat

call write text to with path = "{esc(results_path)}", content = (call stringify from json with value = (a map with "serialized" mapped to serialized, "roundtrip" mapped to roundtrip, "decoded" mapped to decoded))
"""
    harness_path.write_text(harness, encoding="utf-8", newline="\n")

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

    def check(group, source, actual, expected):
        nonlocal failures
        if actual != expected:
            failures += 1
            print(f"{group} {source!r}: got {actual!r}, want {expected!r}")

    for case, actual in zip(CASES, results["serialized"]):
        check("STRINGIFY", case, actual, json.dumps(case, ensure_ascii=False))
    for text, actual in zip(TEXTS, results["roundtrip"]):
        check("ROUNDTRIP", text, actual, json.dumps(json.loads(text), ensure_ascii=False))
    for text, actual in zip(ESCAPE_TEXTS, results["decoded"]):
        check("ESCAPES", text, actual, json.dumps(json.loads(text), ensure_ascii=False))

    total = len(CASES) + len(TEXTS) + len(ESCAPE_TEXTS)
    print(f"compared {total} cases, {failures} mismatches")
    if failures:
        sys.exit(1)
    print("lib/json.ll matches Python json")


if __name__ == "__main__":
    main()
