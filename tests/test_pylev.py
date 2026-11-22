"""The llang rewrite of pylev, verified against the original Python module.

The reference is pylev 1.3.0's single-file ``pylev.py``. It is embedded
verbatim below and loaded through importlib, so the differential tests need
no network access and no installed pylev package.
"""

import importlib.util
import subprocess
import sys
import atexit
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang import LangError, Lexer, Parser, Interpreter  # noqa: E402


# Exact bytes of https://raw.githubusercontent.com/toastdriven/pylev/v1.3.0/pylev.py
PYLEV_SOURCE = r'''
"""
pylev
=====

A pure Python Levenshtein implementation that's not freaking GPL'd.

Based off the Wikipedia code samples at
http://en.wikipedia.org/wiki/Levenshtein_distance.

Usage
-----

Usage is fairly straightforward.::

    import pylev
    distance = pylev.levenshtein('kitten', 'sitting')
    assert(distance, 3)

"""
__author__ = 'Daniel Lindsley'
__version__ = (1, 3, 0)
__license__ = 'New BSD'


import sys
PY2 = sys.version_info[0] == 2

if PY2:
    range = xrange


def classic_levenshtein(string_1, string_2):
    """
    Calculates the Levenshtein distance between two strings.

    This version is easier to read, but significantly slower than the version
    below (up to several orders of magnitude). Useful for learning, less so
    otherwise.

    Usage::

        >>> classic_levenshtein('kitten', 'sitting')
        3
        >>> classic_levenshtein('kitten', 'kitten')
        0
        >>> classic_levenshtein('', '')
        0

    """
    len_1 = len(string_1)
    len_2 = len(string_2)
    cost = 0

    if len_1 and len_2 and string_1[0] != string_2[0]:
        cost = 1

    if len_1 == 0:
        return len_2
    elif len_2 == 0:
        return len_1
    else:
        return min(
            classic_levenshtein(string_1[1:], string_2) + 1,
            classic_levenshtein(string_1, string_2[1:]) + 1,
            classic_levenshtein(string_1[1:], string_2[1:]) + cost,
        )


def recursive_levenshtein(string_1, string_2, len_1=None, len_2=None, offset_1=0, offset_2=0, memo=None):
    """
    Calculates the Levenshtein distance between two strings.

    Usage::

        >>> recursive_levenshtein('kitten', 'sitting')
        3
        >>> recursive_levenshtein('kitten', 'kitten')
        0
        >>> recursive_levenshtein('', '')
        0

    """
    if len_1 is None:
        len_1 = len(string_1)

    if len_2 is None:
        len_2 = len(string_2)

    if memo is None:
        memo = {}

    key = ','.join([str(offset_1), str(len_1), str(offset_2), str(len_2)])

    if memo.get(key) is not None:
        return memo[key]

    if len_1 == 0:
        return len_2
    elif len_2 == 0:
        return len_1

    cost = 0

    if string_1[offset_1] != string_2[offset_2]:
        cost = 1

    dist = min(
        recursive_levenshtein(string_1, string_2, len_1 - 1, len_2, offset_1 + 1, offset_2, memo) + 1,
        recursive_levenshtein(string_1, string_2, len_1, len_2 - 1, offset_1, offset_2 + 1, memo) + 1,
        recursive_levenshtein(string_1, string_2, len_1 - 1, len_2 - 1, offset_1 + 1, offset_2 + 1, memo) + cost,
    )
    memo[key] = dist
    return dist


def wf_levenshtein(string_1, string_2):
    """
    Calculates the Levenshtein distance between two strings.

    This version uses the Wagner-Fischer algorithm.

    Usage::

        >>> wf_levenshtein('kitten', 'sitting')
        3
        >>> wf_levenshtein('kitten', 'kitten')
        0
        >>> wf_levenshtein('', '')
        0

    """
    len_1 = len(string_1) + 1
    len_2 = len(string_2) + 1

    d = [0] * (len_1 * len_2)

    for i in range(len_1):
        d[i] = i
    for j in range(len_2):
        d[j * len_1] = j

    for j in range(1, len_2):
        for i in range(1, len_1):
            if string_1[i - 1] == string_2[j - 1]:
                d[i + j * len_1] = d[i - 1 + (j - 1) * len_1]
            else:
                d[i + j * len_1] = min(
                   d[i - 1 + j * len_1] + 1,        # deletion
                   d[i + (j - 1) * len_1] + 1,      # insertion
                   d[i - 1 + (j - 1) * len_1] + 1,  # substitution
                )

    return d[-1]


def wfi_levenshtein(string_1, string_2):
    """
    Calculates the Levenshtein distance between two strings.

    This version uses an iterative version of the Wagner-Fischer algorithm.

    Usage::

        >>> wfi_levenshtein('kitten', 'sitting')
        3
        >>> wfi_levenshtein('kitten', 'kitten')
        0
        >>> wfi_levenshtein('', '')
        0

    """
    if string_1 == string_2:
        return 0

    len_1 = len(string_1)
    len_2 = len(string_2)

    if len_1 == 0:
        return len_2
    if len_2 == 0:
        return len_1

    if len_1 > len_2:
        string_2, string_1 = string_1, string_2
        len_2, len_1 = len_1, len_2

    d0 = [i for i in range(len_2 + 1)]
    d1 = [j for j in range(len_2 + 1)]

    for i in range(len_1):
        d1[0] = i + 1
        for j in range(len_2):
            cost = d0[j]

            if string_1[i] != string_2[j]:
                # substitution
                cost += 1

                # insertion
                x_cost = d1[j] + 1
                if x_cost < cost:
                    cost = x_cost

                # deletion
                y_cost = d0[j + 1] + 1
                if y_cost < cost:
                    cost = y_cost

            d1[j + 1] = cost

        d0, d1 = d1, d0

    return d0[-1]


def damerau_levenshtein(string_1, string_2):
    """
    Calculates the Damerau-Levenshtein distance between two strings.

    In addition to insertions, deletions and substitutions,
    Damerau-Levenshtein considers adjacent transpositions.

    This version is based on an iterative version of the Wagner-Fischer algorithm.

    Usage::

        >>> damerau_levenshtein('kitten', 'sitting')
        3
        >>> damerau_levenshtein('kitten', 'kittne')
        1
        >>> damerau_levenshtein('', '')
        0

    """
    if string_1 == string_2:
        return 0

    len_1 = len(string_1)
    len_2 = len(string_2)

    if len_1 == 0:
        return len_2
    if len_2 == 0:
        return len_1

    if len_1 > len_2:
        string_2, string_1 = string_1, string_2
        len_2, len_1 = len_1, len_2

    prev_cost = 0
    d0 = [i for i in range(len_2 + 1)]
    d1 = [j for j in range(len_2 + 1)]
    dprev = d0[:]

    s1 = string_1
    s2 = string_2

    for i in range(len_1):
        d1[0] = i + 1
        for j in range(len_2):
            cost = d0[j]

            if s1[i] != s2[j]:
                # substitution
                cost += 1

                # insertion
                x_cost = d1[j] + 1
                if x_cost < cost:
                    cost = x_cost

                # deletion
                y_cost = d0[j + 1] + 1
                if y_cost < cost:
                    cost = y_cost

                # transposition
                if i > 0 and j > 0 and s1[i] == s2[j - 1] and s1[i - 1] == s2[j]:
                    transp_cost = dprev[j - 1] + 1
                    if transp_cost < cost:
                        cost = transp_cost
            d1[j + 1] = cost

        dprev, d0, d1 = d0, d1, dprev

    return d0[-1]


levenshtein = wfi_levenshtein

# Backward-compatibilty because I misspelled.
classic_levenschtein = classic_levenshtein
levenschtein = levenshtein
'''


def load_pylev():
    """Load the embedded, unmodified pylev 1.3.0 source as a Python module."""
    work = Path(tempfile.mkdtemp(prefix="pylev_reference_"))
    atexit.register(shutil.rmtree, work, ignore_errors=True)
    path = work / "pylev.py"
    path.write_text(PYLEV_SOURCE, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("pylev_reference", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(source):
    interpreter = Interpreter(library_paths=[ROOT / "lib"])
    interpreter.run(Parser(Lexer(source).tokenize()).parse_program())
    return interpreter.output


def llang_string(value):
    """Render a Python string as an llang double-quoted string literal."""
    escaped = (value.replace("\\", "\\\\")
                    .replace('"', '\\"')
                    .replace("\n", "\\n")
                    .replace("\t", "\\t")
                    .replace("\r", "\\r"))
    return '"' + escaped + '"'


# A curated corpus: empties, equality, insert/delete/substitute, adjacent
# transpositions, repeated characters, whitespace/newlines and Unicode.
CASES = [
    ("", ""),
    ("", "a"),
    ("a", ""),
    ("", "abc"),
    ("abc", ""),
    ("a", "a"),
    ("a", "b"),
    ("a", "ab"),
    ("ab", "a"),
    ("ab", "ba"),
    ("abc", "acb"),
    ("ca", "abc"),
    ("ba", "abc"),
    ("abca", "acab"),
    ("kitten", "sitting"),
    ("sitting", "kitten"),
    ("kitten", "kitten"),
    ("kitten", "kittne"),
    ("flaw", "lawn"),
    ("foobar", "foobra"),
    ("fee", "deed"),
    ("teh", "the"),
    ("meilenstein", "levenshtein"),
    ("levenshtein", "frankenstein"),
    ("confide", "deceit"),
    ("CUNsperrICY", "conspiracy"),
    ("aaa", "aa"),
    ("aaaa", "aaaa"),
    ("abab", "baba"),
    ("abcabc", "abcab"),
    ("abcd", "dcba"),
    ("correct", "chocolate"),
    ("intention", "execution"),
    ("abcdefghij", "abcdefghijk"),
    ("abcdefghij", "jihgfedcba"),
    ("a b", "a  b"),
    ("a\nb", "a b"),
    ("\t", " "),
    ('"', "'"),
    ("café", "cafe"),
    ("café", "caffè"),
    ("naïve", "naive"),
    ("résumé", "resume"),
    ("日本", "日本語"),
    ("日本語", "日本語"),
    ("🐱", "🐶"),
    ("🐱🐶", "🐶🐱"),
    ("Γειά", "Γεια"),
    ("e\u0301", "é"),
    ("straße", "strasse"),
    ("Ωμέγα", "ωμεγα"),
    ("hello world", "hello World"),
    ("Hello", "hello"),
    ("a_b_c", "a-b-c"),
    ("12345", "1234"),
    ("0", "1"),
    ("x", "xyx"),
    ("xyx", "x"),
    ("mississippi", "mississipi"),
    ("mississipi", "mississippi"),
    ("aaaaaa", "aaaaaa"),
    ("ab", "cd"),
    ("aab", "abb"),
    ("abc", "abcde"),
    ("abcde", "ace"),
    ("the quick brown fox", "the quick brown dog"),
    ("spaces  in   text", "spaces in text"),
    ("é", "e"),
    ("ü", "u"),
    ("中文测试", "中文測试"),
]


class PylevRewriteTests(unittest.TestCase):
    def test_levenshtein(self):
        self.assertEqual(
            run('use the pylev module\nshow call levenshtein from pylev with left = "kitten", right = "sitting"'),
            ["3"],
        )

    def test_dameraulevenshtein(self):
        self.assertEqual(
            run('use the pylev module\nshow call dameraulevenshtein from pylev with left = "kitten", right = "kittne"'),
            ["1"],
        )

    def test_osadistance(self):
        self.assertEqual(
            run('use the pylev module\nshow call osadistance from pylev with left = "ab", right = "ba"'),
            ["1"],
        )

    def test_aliases(self):
        output = run("""
use the pylev module
show call lev from pylev with left = "a", right = ""
show call damerau_levenshtein from pylev with left = "ca", right = "abc"
show call osa_distance from pylev with left = "ca", right = "abc"
""")
        self.assertEqual(output, ["1", "3", "3"])

    def test_invalid_input_fails_loudly(self):
        for name in ("levenshtein", "dameraulevenshtein", "osadistance"):
            with self.subTest(function=name):
                with self.assertRaises(LangError) as ctx:
                    run(f'use the pylev module\nshow call {name} from pylev with left = nothing, right = "abc"')
                self.assertIn("edit_error", str(ctx.exception))

    def test_matches_python_source_on_corpus(self):
        reference = load_pylev()
        checks = (
            ("levenshtein", reference.levenshtein),
            ("dameraulevenshtein", reference.damerau_levenshtein),
            ("osadistance", reference.damerau_levenshtein),
        )
        for left, right in CASES:
            for name, python_function in checks:
                with self.subTest(function=name, left=left, right=right):
                    source = (
                        "use the pylev module\n"
                        f"show call {name} from pylev with "
                        f"left = {llang_string(left)}, right = {llang_string(right)}"
                    )
                    self.assertEqual(run(source), [str(python_function(left, right))])

    def test_matches_python_source_on_reversed_corpus(self):
        """The algorithms are symmetric; check the other argument order too."""
        reference = load_pylev()
        for left, right in CASES:
            with self.subTest(left=left, right=right):
                source = (
                    "use the pylev module\n"
                    "show call levenshtein from pylev with "
                    f"left = {llang_string(right)}, right = {llang_string(left)}"
                )
                self.assertEqual(run(source), [str(reference.levenshtein(right, left))])

    def test_compare_harness_passes(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "compare_pylev.py")],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        timeout=300)
        self.assertEqual(completed.returncode, 0,
                         f"{completed.stdout}\n{completed.stderr}")
        self.assertIn("0 mismatches", completed.stdout)


if __name__ == "__main__":
    unittest.main()
