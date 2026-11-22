"""Compare lib/pylev.ll against the original Python pylev 1.3.0 source.

Like tools/compare_shlex.py: build a corpus, run the llang implementation via
the interpreter, and diff every result against the reference module. The
reference source is embedded in tests/test_pylev.py and loaded via importlib,
so no network access or installed pylev package is required.
"""

import importlib.util
import json
import subprocess
import sys
import atexit
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Reuse the curated corpus and the verbatim embedded pylev source. Loading the
# test module only defines helpers/cases; it does not run unittest.main().
_TEST_PATH = ROOT / "tests" / "test_pylev.py"
_spec = importlib.util.spec_from_file_location("pylev_test_helpers", _TEST_PATH)
_tests = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_tests)

CASES = _tests.CASES
# Non-text inputs: pylev raises TypeError, llang raises an edit_error problem.
INVALID_CASES = [
    [None, "abc"],
    ["abc", None],
    [42, "abc"],
    ["abc", 42],
]


def esc(path: Path) -> str:
    return str(path).replace("\\", "/")


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="llang_pylev_"))
    atexit.register(shutil.rmtree, work, ignore_errors=True)
    cases_path = work / "cases.json"
    results_path = work / "results.json"
    harness_path = work / "harness.ll"

    pairs = [list(case) for case in CASES] + INVALID_CASES
    cases_path.write_text(json.dumps({"pairs": pairs}, ensure_ascii=False),
                          encoding="utf-8")

    harness = f"""use the pylev module
use the foreign json module

set data to call loads from json with text = (call read text from with path = "{esc(cases_path)}")
set lev_results to an empty list
set dam_results to an empty list
set osa_results to an empty list

repeat for each pair in item "pairs" of data
    expect
        set result to call levenshtein from pylev with left = (item 0 of pair), right = (item 1 of pair)
    if a problem of kind edit_error occurs then
        set result to "ERROR"
    end expect
    add result to lev_results

    expect
        set result to call dameraulevenshtein from pylev with left = (item 0 of pair), right = (item 1 of pair)
    if a problem of kind edit_error occurs then
        set result to "ERROR"
    end expect
    add result to dam_results

    expect
        set result to call osadistance from pylev with left = (item 0 of pair), right = (item 1 of pair)
    if a problem of kind edit_error occurs then
        set result to "ERROR"
    end expect
    add result to osa_results
end repeat

set payload to a map with "lev" mapped to lev_results, "dam" mapped to dam_results, "osa" mapped to osa_results
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
    reference = _tests.load_pylev()

    def expected(name, left, right):
        try:
            if name == "lev":
                return reference.levenshtein(left, right)
            # pylev's damerau_levenshtein is the restricted (optimal string
            # alignment) variant, which is what osadistance computes too.
            return reference.damerau_levenshtein(left, right)
        except TypeError:
            return "ERROR"

    failures = 0
    for index, (left, right) in enumerate(pairs):
        for name, key in (("LEV", "lev"), ("DAM", "dam"), ("OSA", "osa")):
            actual = results[key][index]
            want = expected(key, left, right)
            if actual != want:
                failures += 1
                print(f"{name}  {(left, right)!r}: got {actual!r}, want {want!r}")

    total = len(pairs) * 3
    print(f"compared {total} cases, {failures} mismatches")
    if failures:
        sys.exit(1)
    print("lib/pylev.ll matches pylev 1.3.0")


if __name__ == "__main__":
    main()
