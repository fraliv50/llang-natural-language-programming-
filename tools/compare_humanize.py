"""Compare lib/humanize.ll against the humanize Python source.

The oracle is the fetched master source of ``humanize/number.py`` and
``humanize/filesize.py`` (MIT license), embedded below with the gettext calls
replaced by identity functions for the English/default locale.  It is loaded
through importlib so the comparison uses the exact semantics that were ported,
not a possibly older installed release.  When an installed ``humanize`` is
present its version is reported and a second, informational agreement check is
run; version drift is documented in tools/rewrites/humanize/SOURCE.md.

The corpus is JSON-driven, exactly like tools/compare_shlex.py: write cases,
run a generated llang harness through run.py, read results, diff, report
"compared N cases, M mismatches" and exit nonzero on any mismatch.
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

# The fetched master source, trimmed to the ported functions and with i18n
# resolved to English.  Function bodies are otherwise verbatim.
REFERENCE_SOURCE = r'''
import bisect
import math

_ = lambda text: text
N_ = lambda text: text
NS_ = lambda singular, plural: (singular, plural)
P_ = lambda context, text: text
_ngettext = lambda singular, plural, n: singular if n == 1 else plural
decimal_separator = lambda: "."
thousands_separator = lambda: ","

_SUPERSCRIPT_MAP = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
    "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹", "-": "⁻",
}
_SUPERSCRIPT_TRANS = str.maketrans(_SUPERSCRIPT_MAP)
_ORDINAL_SUFFIXES = ("th", "st", "nd", "rd", "th", "th", "th", "th", "th", "th")
_APNUMBER_WORDS = (
    "zero", "one", "two", "three", "four",
    "five", "six", "seven", "eight", "nine",
)


def _format_not_finite(value):
    if math.isnan(value):
        return "NaN"
    if math.isinf(value) and value < 0:
        return "-Inf"
    if math.isinf(value) and value > 0:
        return "+Inf"
    return ""


def ordinal(value, gender="male"):
    try:
        if not math.isfinite(float(value)):
            return _format_not_finite(float(value))
        value = int(value)
    except (TypeError, ValueError):
        return str(value)
    gender = "male" if gender == "male" else "female"
    digit = 0 if value % 100 in (11, 12, 13) else value % 10
    return f"{value}{_ORDINAL_SUFFIXES[digit]}"


def intcomma(value, ndigits=None):
    thousands_sep = thousands_separator()
    decimal_sep = decimal_separator()
    try:
        if isinstance(value, str):
            value = value.replace(thousands_sep, "").replace(decimal_sep, ".")
            if not math.isfinite(float(value)):
                return _format_not_finite(float(value))
            if "." in value:
                value = float(value)
            else:
                value = int(value)
        elif not isinstance(value, int):
            if not math.isfinite(float(value)):
                return _format_not_finite(float(value))
            float(value)
    except (TypeError, ValueError):
        return str(value)

    if ndigits is not None:
        result = f"{value:,.{ndigits}f}"
    else:
        result = f"{value:,}"
    if thousands_sep != "," or decimal_sep != ".":
        result = result.translate(str.maketrans(",.", thousands_sep + decimal_sep))
    return result


powers = [10**x for x in (3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 100)]
human_powers = tuple(
    (name, name) for name in (
        "thousand", "million", "billion", "trillion", "quadrillion",
        "quintillion", "sextillion", "septillion", "octillion",
        "nonillion", "decillion", "googol",
    )
)


def intword(value, format="%.1f"):
    try:
        if not math.isfinite(float(value)):
            return _format_not_finite(float(value))
        value = int(value)
    except (TypeError, ValueError):
        return str(value)

    if value < 0:
        value *= -1
        negative_prefix = "-"
    else:
        negative_prefix = ""

    if value < powers[0]:
        return f"{negative_prefix}{value}"

    ordinal = bisect.bisect_right(powers, value)
    largest_ordinal = ordinal == len(powers)

    ordinal -= 1
    power = powers[ordinal]
    chopped = value / power
    rounded_value = float(format % chopped)

    if not largest_ordinal and rounded_value == powers[ordinal + 1] // power:
        ordinal += 1
        rounded_value = 1.0

    singular, plural = human_powers[ordinal]
    unit = _ngettext(singular, plural, math.ceil(rounded_value))
    decimal_sep = decimal_separator()
    number = (format % rounded_value).replace(".", decimal_sep)
    return f"{negative_prefix}{number} {unit}"


def apnumber(value):
    try:
        if not math.isfinite(float(value)):
            return _format_not_finite(float(value))
        value = int(value)
    except (TypeError, ValueError):
        return str(value)
    if not 0 <= value < 10:
        return str(value)
    return _(_APNUMBER_WORDS[value])


def scientific(value, precision=2):
    try:
        value = float(value)
        if not math.isfinite(value):
            return _format_not_finite(value)
    except (ValueError, TypeError):
        return str(value)
    fmt = f"{{:.{int(precision)}e}}"
    n = fmt.format(value)
    part1, part2 = n.split("e")
    return part1 + " x 10" + str(int(part2)).translate(_SUPERSCRIPT_TRANS)


def metric(value, unit="", precision=3):
    if not math.isfinite(value):
        return _format_not_finite(value)
    exponent = math.floor(math.log10(abs(value))) if value != 0 else 0

    if exponent >= 33 or exponent < -30:
        return scientific(value, precision - 1) + unit

    old_bucket = exponent // 3 * 3
    value /= 10**old_bucket
    digits = int(max(0, precision - exponent % 3 - 1))
    if exponent < 30 and round(abs(value), digits) >= 10 ** (exponent % 3 + 1):
        exponent += 1
        new_bucket = exponent // 3 * 3
        value /= 10 ** (new_bucket - old_bucket)
        digits = int(max(0, precision - exponent % 3 - 1))

    if exponent >= 3:
        ordinal_ = "kMGTPEZYRQ"[exponent // 3 - 1]
    elif exponent < 0:
        ordinal_ = "mμnpfazyrq"[(-exponent - 1) // 3]
    else:
        ordinal_ = ""
    value_ = format(value, f".{digits}f")
    if not (unit or ordinal_) or unit in ("°", "′", "″"):
        space = ""
    else:
        space = " "

    return f"{value_}{space}{ordinal_}{unit}"


suffixes = {
    "decimal": ("kB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB", "RB", "QB"),
    "binary": ("KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB", "RiB", "QiB"),
    "gnu": "KMGTPEZYRQ",
}


def naturalsize(value, binary=False, gnu=False, format="%.1f"):
    if gnu:
        suffix = suffixes["gnu"]
    elif binary:
        suffix = suffixes["binary"]
    else:
        suffix = suffixes["decimal"]

    base = 1024 if (gnu or binary) else 1000
    bytes_ = float(value)
    abs_bytes = abs(bytes_)

    if abs_bytes == 1 and not gnu:
        return "%d Byte" % int(bytes_)

    if abs_bytes < base:
        return f"{int(bytes_)}B" if gnu else "%d Bytes" % int(bytes_)

    from math import log

    exp = int(min(log(abs_bytes, base), len(suffix)))
    if exp < len(suffix) and abs(float(format % (abs_bytes / (base**exp)))) >= base:
        exp += 1
    space = "" if gnu else " "
    ret = format % (bytes_ / (base**exp)) + space + suffix[exp - 1]
    return ret
'''

# Label names used by the generated llang harness for each function.
SPECS = {
    "intcomma": ("intcomma", ("value", "ndigits")),
    "intword": ("intword", ("value", "fmt")),
    "apnumber": ("apnumber", ("value",)),
    "ordinal": ("ordinal", ("value", "gender")),
    "scientific": ("scientific", ("value", "precision")),
    "naturalsize": ("naturalsize", ("value", "binary", "gnu", "fmt")),
    "metric": ("metric", ("value", "unit", "precision")),
}

DEFAULTS = {
    "intcomma": {"ndigits": None},
    "intword": {"fmt": "%.1f"},
    "apnumber": {},
    "ordinal": {"gender": "male"},
    "scientific": {"precision": 2},
    "naturalsize": {"binary": False, "gnu": False, "fmt": "%.1f"},
    "metric": {"unit": "", "precision": 3},
}


def case(fn, value, **kwargs):
    args = {"value": value}
    args.update(DEFAULTS[fn])
    args.update(kwargs)
    return {"fn": fn, "args": args}


def error_case(fn, value, **kwargs):
    entry = case(fn, value, **kwargs)
    entry["error"] = "format_error"
    return entry


def build_corpus():
    cases = []
    add = cases.append

    # intcomma: signed ints, large ints, floats, text with punctuation,
    # exponent-form floats and rounding boundaries.
    for value in (0, 1, 12, 999, 1000, 1001, 9999, 10000, 12345, 1000000,
                  1234567, 10**9, 10**28, 10**100, -1, -12, -999, -1000,
                  -1234567, -(10**28)):
        add(case("intcomma", value))
    for value in (0.0, 0.5, 1.0, 12.5, 1234.5, 1234567.25, -1234.56,
                  1e20, 1e-8, 1e100, -0.0):
        add(case("intcomma", value))
    for value in ("100", "1000", "1,000", "1,234,567.25", "14308.40", "foo",
                  "", "nan", "NaN", "inf", "-Inf", "1.2.3", "  42  ", "+7",
                  "1e3", "0.5"):
        add(case("intcomma", value))
    for value, ndigits in ((1234.5454545, 2), (14308.40, 1), ("14308.40", 1),
                           (100, 2), (100.0, 0), (999999, 1), (0, 3),
                           (-1234.5, 1), (1e20, 2), (1234567.25, 3),
                           (10**28, 0), (0.5, 0), (1.5, 0)):
        add(case("intcomma", value, ndigits=ndigits))

    # apnumber: 0-9 words, outside range, float/text coercion, odd text.
    for value in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, -1, -2, 100, 1000000,
                  1234567.25, 7.9, -0.5):
        add(case("apnumber", value))
    for value in ("0", "7", "10", "foo", "3.0", "", "1,000", "nan", "inf",
                  "-Inf"):
        add(case("apnumber", value))

    # ordinal: teens, hundreds, thousands, negatives, floats and bad text.
    for value in (0, 1, 2, 3, 4, 10, 11, 12, 13, 20, 21, 22, 23, 100, 101,
                  102, 103, 110, 111, 112, 113, 1001, 1002, 1003, 1011,
                  111, -1, -2, -11, -21, 1000000, 10**12):
        add(case("ordinal", value))
    for value in (1.9, -3.7, 1e6, 0.5, 2.9999):
        add(case("ordinal", value))
    for value in ("1", "103", "foo", "7.0", "nan", "-Inf", "  42  "):
        add(case("ordinal", value))
    add(case("ordinal", 1, gender="female"))
    add(case("ordinal", 103, gender="other"))

    # intword: below a thousand, each power, the rounding-carry boundary,
    # negatives, custom precision formats and uncoercible text.
    for value, fmt in (
        ("100", "%.1f"), ("12400", "%.1f"), (12400, "%.1f"),
        ("1000000", "%.1f"), (1000000, "%.1f"), (1200000, "%.1f"),
        (1200000000, "%.1f"), (10**12, "%.1f"), (10**24 - 1, "%.1f"),
        (10**33, "%.1f"), (10**100, "%.1f"), (1e40, "%.1f"),
        (-1200000, "%.1f"), (999, "%.1f"), (999999, "%.1f"),
        ("foo", "%.1f"), ("1234000", "%0.3f"), (12400, "%.0f"),
        (10**27, "%.2f"), ("1000000000000", "%.1f"),
    ):
        add(case("intword", value, fmt=fmt))

    # scientific: fractions, powers of ten, zero, negatives, carry and text.
    for value, precision in (
        (0.3, 2), (500, 2), (-1000, 2), (1000, 2), (99.0, 2), (0, 2),
        (0.0001, 2), (-0.0001, 2), (1e40, 2), (1e-14, 2), ("99", 2),
        ("foo", 2), (1000, 1), (1000, 3), (9.99, 2), (9.999, 2),
        (-0.0, 2), (999.9, 2),
    ):
        add(case("scientific", value, precision=precision))

    # naturalsize: units, boundaries, the master rounding carry, binary/GNU
    # modes, custom formats and text input.
    for value, binary, gnu, fmt in (
        (0, False, False, "%.1f"), (1, False, False, "%.1f"),
        (-1, False, False, "%.1f"), (300, False, False, "%.1f"),
        (999, False, False, "%.1f"), (1000, False, False, "%.1f"),
        (3000, False, False, "%.1f"), (999999, False, False, "%.1f"),
        (3000000, False, False, "%.1f"), (10**28, False, False, "%.1f"),
        (10**34 * 3, False, False, "%.1f"), (-4096, False, False, "%.1f"),
        (3000, True, False, "%.1f"), (3000, False, True, "%.1f"),
        (300, False, True, "%.1f"), (-4096, True, False, "%.1f"),
        (1048576, True, False, "%.1f"), (3000, False, False, "%.3f"),
        (3000, False, True, "%.3f"), ("3000", False, False, "%.1f"),
        (0, False, True, "%.1f"), (1, False, True, "%.1f"),
        (1023, True, False, "%.1f"), (1024, True, False, "%.1f"),
        (1234567, False, False, "%.1f"),
    ):
        add(case("naturalsize", value, binary=binary, gnu=gnu, fmt=fmt))

    # metric: SI prefixes both directions, rounding carry, scientific
    # fallback, special units, non-finite values and degree symbols.
    for value, unit, precision in (
        (1500, "V", 3), (2e8, "W", 3), (220e-6, "F", 3), (1e-14, "", 4),
        (123000, "", 3), (1230000, "", 3), (1e40, "", 3), (0, "", 3),
        (1, "", 3), (1e-6, "", 3), (1e-30, "", 3), (-1500, "V", 3),
        (999999, "", 3), (10**33, "", 3), (1, "°", 3), (1, "′", 3),
        (999.9, "", 3), (999999.9, "", 3), (1e30, "", 3), (-0.0, "", 3),
        (float("nan"), "", 3), (float("inf"), "", 3), (float("-inf"), "", 3),
    ):
        add(case("metric", value, unit=unit, precision=precision))

    # Loud validation: wrong types are rejected with a format_error problem.
    add(error_case("intcomma", None))
    add(error_case("intcomma", [1, 2]))
    add(error_case("apnumber", {"a": 1}))
    add(error_case("ordinal", 1, gender=123))
    add(error_case("scientific", 1, precision=-1))
    add(error_case("naturalsize", 1, binary="yes"))
    add(error_case("metric", "1500"))
    return cases


def load_reference():
    """Load the embedded master source through importlib."""
    work = Path(tempfile.mkdtemp(prefix="llang_humanize_ref_"))
    atexit.register(shutil.rmtree, work, ignore_errors=True)
    path = work / "humanize_reference.py"
    path.write_text(REFERENCE_SOURCE, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("humanize_reference", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def installed_version():
    try:
        import humanize
        return humanize.__version__
    except ImportError:
        return None


def oracle_value(reference, entry):
    fn = entry["fn"]
    args = dict(entry["args"])
    if fn in ("intword", "naturalsize"):
        args["format"] = args.pop("fmt")
    return getattr(reference, fn)(**args)


def installed_value(entry):
    import humanize
    fn = entry["fn"]
    args = dict(entry["args"])
    if fn in ("intword", "naturalsize"):
        args["format"] = args.pop("fmt")
    return getattr(humanize, fn)(**args)


def make_harness(cases_path, results_path):
    def esc(path):
        return str(path).replace("\\", "/")

    branches = []
    for position, (fn, (target, labels)) in enumerate(SPECS.items()):
        keyword = "if" if position == 0 else "otherwise if"
        args = ", ".join(
            f'{label} = item "{label}" of arguments' for label in labels)
        branches.append(
            f'        {keyword} fname equals "{fn}" then\n'
            f'            set outcome to call {target} from humanize with {args}')
    chain = "\n".join(branches) + "\n        end if"

    return f"""use the humanize module
use the foreign json module

set cases to call loads from json with text = (call read text from with path = "{esc(cases_path)}")
set results to an empty list

repeat for each case in cases
    set fname to item "fn" of case
    set arguments to item "args" of case
    set outcome to "NO_RESULT"
    expect
{chain}
    if a problem of kind format_error occurs then
        set outcome to "FORMAT_ERROR"
    if a problem occurs then
        set outcome to "OTHER_ERROR"
    end expect
    add outcome to results
end repeat

call write text to with path = "{esc(results_path)}", content = (call dumps from json with value = results)
"""


def main():
    work = Path(tempfile.mkdtemp(prefix="llang_humanize_"))
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

    reference = load_reference()
    failures = 0
    installed_drift = 0
    version = installed_version()
    for entry, actual in zip(cases, results):
        fn, args = entry["fn"], entry["args"]
        if entry.get("error"):
            expected = "FORMAT_ERROR"
        else:
            try:
                expected = oracle_value(reference, entry)
            except Exception as exc:  # oracle failure is a corpus bug
                failures += 1
                print(f"{fn} {ascii(args)}: oracle raised {exc!r}")
                continue
        if actual != expected:
            failures += 1
            print(f"{fn.upper():12s} {ascii(args)}: got {ascii(actual)}, want {ascii(expected)}")
            continue
        if version is not None and not entry.get("error"):
            try:
                installed_expected = installed_value(entry)
                if installed_expected != expected:
                    installed_drift += 1
            except Exception:
                installed_drift += 1

    print(f"compared {len(cases)} cases, {failures} mismatches")
    if version is not None:
        print(f"installed humanize {version}: {installed_drift} version-drift cases "
              "(oracle is the fetched master source)")
    if failures:
        sys.exit(1)
    print("lib/humanize.ll matches the fetched humanize master (English locale)")


if __name__ == "__main__":
    main()
