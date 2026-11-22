"""Compare lib/re.ll against Python's stdlib re.

A JSON-driven corpus of documented regex cases is fed to the native llang
engine through the interpreter.  Every result is normalized to the match-map
shape from docs/research/regex-semantics.md and diffed against Python re.
Prints ``compared N cases, M mismatches`` and exits nonzero on any mismatch.
"""

import json
import re
import subprocess
import sys
import atexit
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FLAG_BITS = {
    "ignore case": re.I,
    "multiline": re.M,
    "dot all": re.S,
    "verbose": re.X,
    "ascii": re.A,
}


def case(op, pattern=None, text=None, **kw):
    item = {"op": op, "pattern": pattern, "text": text}
    item.update(kw)
    return item


# Every entry is (llang case, expected error kind or None).  When expected is
# None the oracle is computed with Python re; when it is a string the llang
# engine must fail with that problem kind.
CORPUS = [
    # --- literals and concatenation -------------------------------------
    (case("search", "abc", "xxabcyy"), None),
    (case("match", "abc", "abcxyz"), None),
    (case("match", "c", "abcdef"), None),
    (case("find_all", "last", "last last"), None),
    (case("full_match", "abc", "abc"), None),
    (case("full_match", "abc", "abcd"), None),
    (case("matches", "cat", "concatenate"), None),
    (case("matches", "^cat", "concatenate"), None),

    # --- dot, greedy and lazy quantifiers -------------------------------
    (case("search", "c.t", "cat cot"), None),
    (case("find_all", ".", "ab\nc"), None),
    (case("search", "a.b", "a\nb", flags=["dot all"]), None),
    (case("search", "a.b", "a\nb"), None),
    (case("search", "ab*", "a"), None),
    (case("search", "ab*", "ab"), None),
    (case("search", "ab*", "abbb"), None),
    (case("find_all", "ab*", "a ab abbb"), None),
    (case("search", ".*", "<a> b <c>"), None),
    (case("search", "<.*?>", "<a> b <c>"), None),
    (case("search", "a+?", "aaa"), None),
    (case("search", "a??", "aaa"), None),
    (case("find_all", "x*", "abxd"), None),
    (case("search", "(a+)(b*)", "aaabbb"), None),
    (case("search", "(a+?)(a*)", "aaaa"), None),

    # --- character classes ---------------------------------------------
    (case("find_all", "[0-5][0-9]", "56 42 99 07"), None),
    (case("search", "[a-z]+", "ABCdef"), None),
    (case("search", "[^5]+", "555abc5"), None),
    (case("search", "[-a]", "-a"), None),
    (case("search", "[a-]", "-a"), None),
    (case("search", "[(+*)]", "(x"), None),
    (case("search", "[]a]", "]a"), None),
    (case("search", "[^]]+", "]ab]"), None),
    (case("search", "[\\d]+", "ab123cd"), None),
    (case("search", "[^\\d\\s]+", "12 ab!"), None),
    (case("search", "[a\\-c]+", "a-cb"), None),
    (case("search", "[\\b]", "\b"), None),
    (case("search", "[\\w]+", "éx"), None),

    # --- anchors and boundaries ----------------------------------------
    (case("search", "^abc", "abc xyz"), None),
    (case("search", "^abc", "xabc"), None),
    (case("find_all", "abc$", "xyzabc"), None),
    (case("search", "foo$", "foo\n"), None),
    (case("search", "\\Aabc", "xabc"), None),
    (case("search", "abc\\Z", "abc\n"), None),
    (case("search", "^X", "A\nB\nX", flags=["multiline"]), None),
    (case("search", "^X", "A\nB\nX"), None),
    (case("find_all", "X$", "X\nY\nX", flags=["multiline"]), None),
    (case("find_all", "\\bcat\\b", "cat, scatter, at"), None),
    (case("find_all", "\\Bcat", "cat scatter"), None),
    (case("search", "\\bat", "at."), None),
    (case("search", "\\bat", "(at)"), None),
    (case("search", "\\bat", "attempt"), None),

    # --- groups, captures, backreferences and alternation --------------
    (case("search", "(..)+", "a1b2c3"), None),
    (case("find_all", "(\\w+)=(\\d+)", "x key=42 end"), None),
    (case("search", "(a)?b", "b"), None),
    (case("search", "(a)|(b)", "b"), None),
    (case("search", "(?:ab)+", "abab"), None),
    (case("search", "(a(b))", "ab"), None),
    (case("search", "(\\w+)\\s+\\1", "go go now"), None),
    (case("search", "(a)(b)?(c)", "ac"), None),
    (case("search", "a|ab", "ab"), None),
    (case("search", "ab|a", "ab"), None),
    (case("find_all", "cat|dog", "dog cat dog"), None),
    (case("search", "(a|ab)b", "abb"), None),

    # --- escapes --------------------------------------------------------
    (case("search", "a\\nb", "a\nb"), None),
    (case("search", "a\\tb", "a\tb"), None),
    (case("search", "a\\.b", "a.b axb"), None),
    (case("search", "a\\*b", "a*b"), None),
    (case("search", "a\\\\b", "a\\b"), None),
    (case("search", "\\d\\w\\s", "1a "), None),
    (case("search", "\\D\\W\\S", "a !"), None),
    (case("search", "\\d+", "١٢٣"), None),
    (case("search", "\\d+", "١٢٣", flags=["ascii"]), None),
    (case("search", "\\w+", "élan"), None),
    (case("search", "\\s+", "\t\n "), None),

    # --- flags ----------------------------------------------------------
    (case("search", "abc", "ABC", flags=["ignore case"]), None),
    (case("search", "[a-z]+", "AbC", flags=["ignore case"]), None),
    (case("search", "İ", "i", flags=["ignore case"]), None),
    (case("search", "ſ", "s", flags=["ignore case"]), None),
    (case("search", "a.b", "a\nb", flags=["dot all", "ignore case"]), None),
    (case("search", "a b # note\n c", "abc", flags=["verbose"]), None),
    (case("search", "^x", "A\nx", flags=["multiline", "ignore case"]), None),
    (case("search", "ABC", "abc", flags=["ignore case", "ascii"]), None),
    (case("search", "abc", "abc", flags=["bogus flag"]), "invalid_flag"),

    # --- replace --------------------------------------------------------
    (case("replace", "x*", "abxd", replacement="-"), None),
    (case("replace", "\\d+", "ab12cd3", replacement="#"), None),
    (case("replace", "(\\w+)=(\\d+)", "key=42 x=7", replacement="\\2:\\1"), None),
    (case("replace", "a", "a,a,a", replacement="X", count=1), None),
    (case("replace", "a", "a,a,a", replacement="X", count=2), None),
    (case("replace", "a", "a,a,a", replacement="X", count=0), None),
    (case("replace", "(a)?b", "b", replacement="[\\1]"), None),
    (case("replace", "b", "b", replacement="\\\\"), None),
    (case("replace", "b", "b", replacement="\\q"), "invalid_pattern"),
    (case("replace", "abc", "ABC", replacement="X", flags=["ignore case"]), None),

    # --- split ----------------------------------------------------------
    (case("split", ",", "a,b,c"), None),
    (case("split", "x*", "abxd"), None),
    (case("split", "a*", "baac"), None),
    (case("split", "x*", "abc"), None),
    (case("split", "", "abc"), None),
    (case("split", ",", "a,b,c", limit=1), None),
    (case("split", ",", "a,b,c", limit=2), None),
    (case("split", "A", "a,B,c", flags=["ignore case"]), None),

    # --- escape ---------------------------------------------------------
    (case("escape", None, "https://www.python.org"), None),
    (case("escape", None, "a+b(c)[d]{e}.f*g?h|i^j$k\\l"), None),
    (case("escape", None, ""), None),
    (case("escape", None, "a b\tc\nd"), None),

    # --- invalid patterns ------------------------------------------------
    (case("search", "(", "abc"), "invalid_pattern"),
    (case("search", "[a", "abc"), "invalid_pattern"),
    (case("search", "a**", "aaa"), "invalid_pattern"),
    (case("search", "\\q", "abc"), "invalid_pattern"),
    (case("search", "a{3,2}", "aaa"), "invalid_pattern"),
    (case("search", "(?=x)", "x"), "invalid_pattern"),
    (case("search", "(?P<n>x)", "x"), "invalid_pattern"),
    (case("search", ")", "x"), "invalid_pattern"),
    (case("search", "a{2}", "aa"), "invalid_pattern"),
    (case("search", "*a", "a"), "invalid_pattern"),
    (case("search", "[z-a]", "a"), "invalid_pattern"),
    (case("search", "\\1", "a"), "invalid_pattern"),
    (case("search", "\\x41", "A"), "invalid_pattern"),
    (case("search", "a*+", "aaa"), "invalid_pattern"),
]


def expected_for(entry):
    item, error = entry
    if error is not None:
        return {"error": error}
    op = item["op"]
    pattern = item["pattern"] or ""
    flags = 0
    for name in item.get("flags", []):
        flags |= FLAG_BITS[name]
    if op == "escape":
        return re.escape(item["text"])
    regex = re.compile(pattern, flags)
    text = item["text"]
    if op in ("match", "full_match", "search"):
        m = (regex.match(text) if op == "match" else
             regex.fullmatch(text) if op == "full_match" else regex.search(text))
        return normalize_match(m)
    if op == "find_all":
        return [normalize_match(m) for m in regex.finditer(text)]
    if op == "matches":
        return regex.search(text) is not None
    if op == "replace":
        return regex.sub(item["replacement"], text, item.get("count", 0))
    if op == "split":
        return regex.split(text, item.get("limit", 0))
    raise AssertionError(op)


def normalize_match(m):
    if m is None:
        return None
    return {
        "matched": m.group(0),
        "start": m.start(),
        "end": m.end(),
        "groups": list(m.groups()),
        "named": dict(m.groupdict()),
    }


def esc(path):
    return str(path).replace("\\", "/")


def harness_source(cases_path, results_path):
    return f"""use the re module
use the foreign json module

set data to call loads from json with text = (call read text from with path = "{esc(cases_path)}")
set results to an empty list

repeat for each case in data
    set op to item "op" of case
    set flags to an empty list
    if (call contains with collection = case, value = "flags") then
        set flags to item "flags" of case
    end if
    set res to nothing
    expect
        if op equals "escape" then
            set res to call escape from re with text = (item "text" of case)
        otherwise if op equals "match" then
            if (the length of flags) equals 0 then
                set res to call match from re with pattern = (item "pattern" of case), text = (item "text" of case)
            otherwise
                set res to call match_flags from re with pattern = (item "pattern" of case), text = (item "text" of case), flags = flags
            end if
        otherwise if op equals "full_match" then
            if (the length of flags) equals 0 then
                set res to call full_match from re with pattern = (item "pattern" of case), text = (item "text" of case)
            otherwise
                set res to call full_match_flags from re with pattern = (item "pattern" of case), text = (item "text" of case), flags = flags
            end if
        otherwise if op equals "search" then
            if (the length of flags) equals 0 then
                set res to call search from re with pattern = (item "pattern" of case), text = (item "text" of case)
            otherwise
                set res to call search_flags from re with pattern = (item "pattern" of case), text = (item "text" of case), flags = flags
            end if
        otherwise if op equals "matches" then
            if (the length of flags) equals 0 then
                set res to call matches from re with pattern = (item "pattern" of case), text = (item "text" of case)
            otherwise
                set res to call matches_flags from re with pattern = (item "pattern" of case), text = (item "text" of case), flags = flags
            end if
        otherwise if op equals "find_all" then
            if (the length of flags) equals 0 then
                set res to call find_all from re with pattern = (item "pattern" of case), text = (item "text" of case)
            otherwise
                set res to call find_all_flags from re with pattern = (item "pattern" of case), text = (item "text" of case), flags = flags
            end if
        otherwise if op equals "replace" then
            set rep to item "replacement" of case
            if (call contains with collection = case, value = "count") then
                if (the length of flags) equals 0 then
                    set res to call replace_count from re with pattern = (item "pattern" of case), text = (item "text" of case), replacement = rep, count = (item "count" of case)
                otherwise
                    set res to call replace_count_flags from re with pattern = (item "pattern" of case), text = (item "text" of case), replacement = rep, count = (item "count" of case), flags = flags
                end if
            otherwise
                if (the length of flags) equals 0 then
                    set res to call replace from re with pattern = (item "pattern" of case), text = (item "text" of case), replacement = rep
                otherwise
                    set res to call replace_flags from re with pattern = (item "pattern" of case), text = (item "text" of case), replacement = rep, flags = flags
                end if
            end if
        otherwise if op equals "split" then
            if (call contains with collection = case, value = "limit") then
                if (the length of flags) equals 0 then
                    set res to call split_limit from re with pattern = (item "pattern" of case), text = (item "text" of case), limit = (item "limit" of case)
                otherwise
                    set res to call split_limit_flags from re with pattern = (item "pattern" of case), text = (item "text" of case), limit = (item "limit" of case), flags = flags
                end if
            otherwise
                if (the length of flags) equals 0 then
                    set res to call split from re with pattern = (item "pattern" of case), text = (item "text" of case)
                otherwise
                    set res to call split_flags from re with pattern = (item "pattern" of case), text = (item "text" of case), flags = flags
                end if
            end if
        end if
    if a problem of kind invalid_pattern occurs then
        set res to a map with "error" mapped to "invalid_pattern"
    if a problem of kind invalid_flag occurs then
        set res to a map with "error" mapped to "invalid_flag"
    if a problem of kind bad_argument occurs then
        set res to a map with "error" mapped to "bad_argument"
    if a problem occurs then
        set res to a map with "error" mapped to "other"
    end expect
    add res to results
end repeat

call write text to with path = "{esc(results_path)}", content = (call dumps from json with value = results)
"""


def main():
    work = Path(tempfile.mkdtemp(prefix="llang_re_"))
    atexit.register(shutil.rmtree, work, ignore_errors=True)
    cases_path = work / "cases.json"
    results_path = work / "results.json"
    harness_path = work / "harness.ll"
    items = [entry[0] for entry in CORPUS]
    cases_path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    harness_path.write_text(harness_source(cases_path, results_path), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(ROOT / "run.py"), str(harness_path)],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        errors="replace",
    timeout=300)
    if completed.returncode != 0:
        print("llang run failed:")
        print(completed.stdout)
        print(completed.stderr)
        sys.exit(1)

    actual_results = json.loads(results_path.read_text(encoding="utf-8"))
    failures = 0
    for item, actual in zip(items, actual_results):
        try:
            expected = expected_for((item, next(e for c, e in CORPUS if c is item)))
        except re.error as exc:
            expected = {"error": "invalid_pattern", "reason": str(exc)}
        except (ValueError, KeyError) as exc:
            expected = {"error": "oracle_error", "reason": str(exc)}
        if isinstance(expected, dict) and expected.get("error") == "invalid_pattern":
            # The llang engine must fail loudly; the exact reason text need not
            # match because fail-with messages are static in llang.
            if isinstance(actual, dict) and actual.get("error") == "invalid_pattern":
                continue
        if actual != expected:
            failures += 1
            print(f"{item['op'].upper():10} {item['pattern']!r} on {item['text']!r}: "
                  f"got {actual!r}, want {expected!r}")
    print(f"compared {len(items)} cases, {failures} mismatches")
    if failures:
        sys.exit(1)
    print("lib/re.ll matches Python re")


if __name__ == "__main__":
    main()
