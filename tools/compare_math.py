"""Compare lib/advanced_math.ll against CPython's math and statistics.

JSON-driven corpus -> generated llang harness -> results.json -> diff with the
stdlib using the four tolerance tiers from docs/research/math-library-design.md.
Mirrors tools/compare_shlex.py.
"""

import json
import math
import statistics
import subprocess
import sys
import atexit
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Stable dispatch table used both to build the llang `if` chain and to compute
# the oracle value on the Python side.  Labels are the exact design labels.
CALL_SPECS = {
    "squareroot": ("squareroot", ("value",)),
    "exponential": ("exponential", ("power",)),
    "logarithm": ("logarithm", ("value",)),
    "logbase": ("logbase", ("value", "base")),
    "logtwo": ("logtwo", ("value",)),
    "logten": ("logten", ("value",)),
    "gcd": ("gcd", ("values",)),
    "lcm": ("lcm", ("values",)),
    "factorial": ("factorial", ("number",)),
    "floor": ("floor", ("value",)),
    "ceil": ("ceil", ("value",)),
    "trunc": ("trunc", ("value",)),
    "hypot": ("hypot", ("coordinates",)),
    "distance": ("distance", ("frompoint", "topoint")),
    "approxequal": ("approxequal", ("left", "right", "reltol", "abstol")),
    "precisesum": ("precisesum", ("values",)),
    "mean": ("mean", ("values",)),
    "median": ("median", ("values",)),
    "mode": ("mode", ("values",)),
    "variance": ("variance", ("values",)),
    "stdev": ("stdev", ("values",)),
    "pvariance": ("pvariance", ("values",)),
    "pstdev": ("pstdev", ("values",)),
    "sine": ("sine", ("angle",)),
    "cosine": ("cosine", ("angle",)),
}


def _case(fn, args, tier, kind=None):
    entry = {"fn": fn, "args": args, "tier": tier}
    if kind is not None:
        entry["kind"] = kind
    return entry


def build_corpus():
    """Curated corpus: canonical values, boundaries, empty/singleton/two-item
    lists, ties, cancellation, huge ints and every documented error kind."""
    cases = []
    add = cases.append

    # --- exponentials and logarithms -------------------------------------
    for value in (81, 0, 2, 0.25, 1e-8, 1.5, 100):
        add(_case("squareroot", {"value": value}, "C"))
    for value in (-1, -0.5, math.inf, math.nan):
        add(_case("squareroot", {"value": value}, "X", "math_domain"))
    for power in (0, 1, -1, 0.5, 2.5, -2.5, 10, -10):
        add(_case("exponential", {"power": power}, "C"))
    add(_case("exponential", {"power": 1000}, "X", "math_overflow"))
    for power in (math.inf, math.nan):
        add(_case("exponential", {"power": power}, "X", "math_domain"))
    for value in (1, math.e, 10, 0.5, 100, 1e-8):
        add(_case("logarithm", {"value": value}, "C"))
    for value in (0, -1, math.inf, math.nan):
        add(_case("logarithm", {"value": value}, "X", "math_domain"))
    for value, base in ((100, 10), (8, 2), (2, 8), (1, 7)):
        add(_case("logbase", {"value": value, "base": base}, "C"))
    for value, base in ((10, 1), (10, 0), (0, 2), (10, -2)):
        add(_case("logbase", {"value": value, "base": base}, "X", "math_domain"))
    for value in (8, 1, 1024, 0.5):
        add(_case("logtwo", {"value": value}, "C"))
    for value in (1000, 1, 0.01, 3):
        add(_case("logten", {"value": value}, "C"))

    # --- number theory ---------------------------------------------------
    for values in ([], [12, 18, 30], [0, 5], [7], [-12, 18],
                   [10 ** 20, 10 ** 15]):
        add(_case("gcd", {"values": values}, "E"))
    for values in ([5.0], [True], [1, 2.5]):
        add(_case("gcd", {"values": values}, "X", "math_type"))
    for values in ([], [-4, 6], [4, 6, 8], [0, 5], [21, 6]):
        add(_case("lcm", {"values": values}, "E"))
    add(_case("lcm", {"values": [2.5]}, "X", "math_type"))
    for number in (0, 1, 5, 10, 20, 100):
        add(_case("factorial", {"number": number}, "E"))
    add(_case("factorial", {"number": -1}, "X", "math_domain"))
    add(_case("factorial", {"number": 5.0}, "X", "math_type"))

    # --- rounding, distance and predicates -------------------------------
    for value in (2.7, -2.7, 5, 0, 1e20):
        add(_case("floor", {"value": value}, "E"))
    for value in (2.1, -2.7, 5, 0):
        add(_case("ceil", {"value": value}, "E"))
    for value in (2.7, -2.7, 0, -0.5, 5):
        add(_case("trunc", {"value": value}, "E"))
    for value in (math.inf, math.nan):
        add(_case("floor", {"value": value}, "X", "math_domain"))
        add(_case("trunc", {"value": value}, "X", "math_domain"))
    for coordinates in ([], [3, 4], [3, 4, 12], [-3, -4],
                        [1e200, 1e200], [1e-200, 2e-200]):
        add(_case("hypot", {"coordinates": coordinates}, "C"))
    add(_case("hypot", {"coordinates": [math.nan]}, "X", "math_domain"))
    for frompoint, topoint in (([0, 0], [3, 4]), ([0, 0, 0], [3, 4, 12]),
                               ([], []), ([1, 2], [4, 6]), ([5], [5])):
        add(_case("distance", {"frompoint": frompoint, "topoint": topoint}, "C"))
    add(_case("distance", {"frompoint": [1, 2], "topoint": [1]},
              "X", "math_length"))
    for left, right, reltol, abstol in (
        (1.0, 1.0000000001, 1e-9, 0.0),
        (1.0, 1.1, 1e-9, 0.0),
        (0.0, 1e-10, 0.0, 1e-9),
        (1e9, 1e9 + 1, 1e-9, 0.0),
        (-3.0, -3.0, 1e-9, 0.0),
    ):
        add(_case("approxequal", {"left": left, "right": right,
                                  "reltol": reltol, "abstol": abstol}, "E"))
    add(_case("approxequal", {"left": math.nan, "right": math.nan,
                              "reltol": 1e-9, "abstol": 0.0},
              "X", "math_domain"))
    add(_case("approxequal", {"left": 1.0, "right": 2.0,
                              "reltol": -1e-9, "abstol": 0.0},
              "X", "math_domain"))
    add(_case("approxequal", {"left": 1.0, "right": 2.0,
                              "reltol": 1.5, "abstol": 0.0},
              "X", "math_domain"))
    for values in ([0.1] * 10, [1e16, 1, -1e16, 1], [],
                   [1, 2, 3], [0.1, 0.2, 0.3], [1e100, 1e100, -1e100]):
        add(_case("precisesum", {"values": values}, "C"))

    # --- descriptive statistics ------------------------------------------
    for values, tier in (([1, 2, 3], "E"), ([10, 20, 30], "E"),
                         ([1, 2], "S"), ([0.1, 0.2], "S"),
                         ([1, 1, 2, 2], "S"), ([7], "E")):
        add(_case("mean", {"values": values}, tier))
    add(_case("mean", {"values": []}, "X", "math_empty"))
    for values, tier in (([1, 3, 5], "E"), ([2, 2, 2], "E"),
                         ([1, 3, 5, 7], "S"), ([1, 2], "S"),
                         ([2.5, 3.5, 4.5], "S")):
        add(_case("median", {"values": values}, tier))
    add(_case("median", {"values": []}, "X", "math_empty"))
    add(_case("mode", {"values": [1, 1, 2, 2]}, "E"))
    add(_case("mode", {"values": ["a", "b", "a"]}, "E"))
    add(_case("mode", {"values": [3, 2, 3, 2, 3]}, "E"))
    add(_case("mode", {"values": []}, "X", "math_empty"))
    for fn in ("variance", "stdev"):
        for values in ([1, 2, 3, 4], [1, 2, 3], [2.5, 3.5, 4.5]):
            add(_case(fn, {"values": values}, "S"))
        add(_case(fn, {"values": [1]}, "X", "math_length"))
        add(_case(fn, {"values": []}, "X", "math_length"))
    for fn in ("pvariance", "pstdev"):
        for values in ([1, 2, 3, 4], [1, 2, 3], [7]):
            add(_case(fn, {"values": values}, "S"))
        add(_case(fn, {"values": []}, "X", "math_empty"))

    # --- trigonometry ----------------------------------------------------
    for angle in (0, math.pi / 2, 1, -1, 0.5, math.pi):
        add(_case("sine", {"angle": angle}, "C"))
        add(_case("cosine", {"angle": angle}, "C"))
    for angle in (math.inf, math.nan):
        add(_case("sine", {"angle": angle}, "X", "math_domain"))
        add(_case("cosine", {"angle": angle}, "X", "math_domain"))
    return cases


def stdlib_value(fn, args):
    if fn == "squareroot":
        return math.sqrt(args["value"])
    if fn == "exponential":
        return math.exp(args["power"])
    if fn == "logarithm":
        return math.log(args["value"])
    if fn == "logbase":
        return math.log(args["value"], args["base"])
    if fn == "logtwo":
        return math.log2(args["value"])
    if fn == "logten":
        return math.log10(args["value"])
    if fn == "gcd":
        return math.gcd(*args["values"])
    if fn == "lcm":
        return math.lcm(*args["values"])
    if fn == "factorial":
        return math.factorial(args["number"])
    if fn == "floor":
        return math.floor(args["value"])
    if fn == "ceil":
        return math.ceil(args["value"])
    if fn == "trunc":
        return math.trunc(args["value"])
    if fn == "hypot":
        return math.hypot(*args["coordinates"])
    if fn == "distance":
        return math.dist(args["frompoint"], args["topoint"])
    if fn == "approxequal":
        return math.isclose(args["left"], args["right"],
                            rel_tol=args["reltol"], abs_tol=args["abstol"])
    if fn == "precisesum":
        return math.fsum(args["values"])
    if fn == "mean":
        return statistics.mean(args["values"])
    if fn == "median":
        return statistics.median(args["values"])
    if fn == "mode":
        return statistics.mode(args["values"])
    if fn == "variance":
        return statistics.variance(args["values"])
    if fn == "stdev":
        return statistics.stdev(args["values"])
    if fn == "pvariance":
        return statistics.pvariance(args["values"])
    if fn == "pstdev":
        return statistics.pstdev(args["values"])
    if fn == "sine":
        return math.sin(args["angle"])
    if fn == "cosine":
        return math.cos(args["angle"])
    raise AssertionError(f"no oracle for {fn}")


def matches(tier, actual, expected):
    if tier == "E":
        return type(actual) is type(expected) and actual == expected
    if tier == "C":
        try:
            if (math.isclose(actual, expected, rel_tol=1e-14, abs_tol=1e-300)
                    or abs(actual - expected) <= 4 * math.ulp(expected)):
                return True
        except (TypeError, ValueError, OverflowError):
            pass
        return False
    if tier == "S":
        try:
            return math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12)
        except (TypeError, ValueError, OverflowError):
            return False
    raise AssertionError(f"unknown tier {tier}")


def make_harness(cases_path, results_path):
    def esc(path):
        return str(path).replace("\\", "/")

    branches = []
    for position, (fn, (target, labels)) in enumerate(CALL_SPECS.items()):
        keyword = "if" if position == 0 else "otherwise if"
        args = ", ".join(
            f'{label} = item "{label}" of arguments' for label in labels)
        branches.append(
            f'        {keyword} fname equals "{fn}" then\n'
            f'            set result_value to call {target} from advanced_math with {args}')
    chain = "\n".join(branches) + "\n        end if"

    return f"""use the advanced_math module
use the foreign json module

set cases to call loads from json with text = (call read text from with path = "{esc(cases_path)}")
set results to an empty list

repeat for each case in cases
    set fname to item "fn" of case
    set arguments to item "args" of case
    set result_value to nothing
    set problem_kind to "none"
    expect
{chain}
    if a problem of kind math_domain occurs then
        set problem_kind to "math_domain"
    if a problem of kind math_type occurs then
        set problem_kind to "math_type"
    if a problem of kind math_empty occurs then
        set problem_kind to "math_empty"
    if a problem of kind math_length occurs then
        set problem_kind to "math_length"
    if a problem of kind math_overflow occurs then
        set problem_kind to "math_overflow"
    if a problem of kind math_constant occurs then
        set problem_kind to "math_constant"
    if a problem occurs then
        set problem_kind to "other"
    end expect
    add (a map with "kind" mapped to problem_kind, "value" mapped to result_value) to results
end repeat

call write text to with path = "{esc(results_path)}", content = (call dumps from json with value = results)
"""


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="llang_math_"))
    atexit.register(shutil.rmtree, work, ignore_errors=True)
    cases_path = work / "cases.json"
    results_path = work / "results.json"
    harness_path = work / "harness.ll"

    cases = build_corpus()
    cases_path.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
    harness_path.write_text(make_harness(cases_path, results_path), encoding="utf-8")

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
    if len(results) != len(cases):
        print(f"result count {len(results)} != case count {len(cases)}")
        sys.exit(1)

    failures = 0
    for case, outcome in zip(cases, results):
        fn, args, tier = case["fn"], case["args"], case["tier"]
        if "kind" in case:
            ok = outcome["kind"] == case["kind"]
            if not ok:
                failures += 1
                print(f"{fn} {args!r}: problem kind {outcome['kind']!r}, "
                      f"want {case['kind']!r} (value={outcome['value']!r})")
        else:
            if outcome["kind"] != "none":
                failures += 1
                print(f"{fn} {args!r}: unexpected problem {outcome['kind']!r}")
                continue
            expected = stdlib_value(fn, args)
            actual = outcome["value"]
            if not matches(tier, actual, expected):
                failures += 1
                print(f"{fn} {args!r} [{tier}]: got {actual!r}, want {expected!r}")

    print(f"compared {len(cases)} cases, {failures} mismatches")
    print(f"CPython {sys.version.split()[0]} on {sys.platform}")
    if failures:
        sys.exit(1)
    print("lib/advanced_math.ll matches CPython math/statistics")


if __name__ == "__main__":
    main()
