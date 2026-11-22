"""The llang rewrite of CPython's csv (excel dialect), verified against stdlib."""

import csv
import io
import json
import subprocess
from contextlib import redirect_stdout
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang import LangError, Lexer, Parser, Interpreter  # noqa: E402


def run(source):
    interpreter = Interpreter(library_paths=[ROOT / "lib"])
    with redirect_stdout(io.StringIO()):  # `show` also prints; keep tests quiet
        interpreter.run(Parser(Lexer(source).tokenize()).parse_program())
    return interpreter.output


def to_llang(value):
    """Render a Python str / list / list-of-lists as an llang literal."""
    if isinstance(value, str):
        escaped = (value.replace("\\", "\\\\")
                        .replace('"', '\\"')
                        .replace("\n", "\\n")
                        .replace("\t", "\\t"))
        return '"' + escaped + '"'
    if isinstance(value, list):
        if not value:
            return "an empty list"
        return "a list of " + ", ".join("(" + to_llang(v) + ")" for v in value)
    raise TypeError(f"cannot render {value!r} as an llang literal")


def llang_read(text):
    source = (
        "use the csv module\n"
        "use the foreign json module\n"
        "show call dumps from json with value = "
        "(call read_rows from csv with text = " + to_llang(text) + ")"
    )
    return json.loads(run(source)[0])


def llang_write(rows):
    source = (
        "use the csv module\n"
        "use the foreign json module\n"
        "show call dumps from json with value = "
        "(call write_rows from csv with rows = (" + to_llang(rows) + "))"
    )
    return json.loads(run(source)[0])


def stdlib_read(text):
    return list(csv.reader(io.StringIO(text, newline="")))


def stdlib_write(rows):
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    for row in rows:
        writer.writerow(row)
    return out.getvalue()


READ_CASES = [
    "", "a", "a,b,c\n", "a,b", "\n", "\r\n", "\n\n", "a\n\nb",
    "a,b\r\nc,d\r\n", "a\rb", '"a,b",c', '"a","b,c"', '"a""b"',
    '"""a"""', '"a"",""b"', "a,,b", ",", ",,", '"","",""',
    '"a\nb",c', '"a\r\nb"\nx', '"line1\nline2\nline3"', '"a"b',
    '"a" b', 'a"b', ' "a" ', '"a', '"a""', "a,\n", "\n,",
    '"multi\nline",plain,"x""y"\nlast', "\r\n\na", "a\r\r\nb",
]

WRITE_CASES = [
    [], [[]], [[""]], [["a"]], [["a", "b"]], [["a,b"]], [['a"b']],
    [["a\nb"]], [["a\rb"]], [["a\r\nb"]], [["", ""]],
    [["a", "b"], ["c", "d"]], [[" a ", " b"]],
    [["a,b", 'c"d', "e\nf"]], [['"']], [[","]], [["\n"]], [["\r"]],
    [["a"], [], ["b"]], [[""], [""]], [["tab\there"]],
    [["a", "", "b"]], [['x"y,z\nw']], [["", "a,b"]],
]


class CsvRewriteTests(unittest.TestCase):
    # --- focused reader tests ------------------------------------------
    def test_read_plain_fields(self):
        self.assertEqual(llang_read("a,b,c\n"), [["a", "b", "c"]])

    def test_read_quoted_comma(self):
        self.assertEqual(llang_read('"a,b",c'), [["a,b", "c"]])

    def test_read_doubled_quotes(self):
        self.assertEqual(llang_read('"a""b"'), [['a"b']])

    def test_read_embedded_newline(self):
        self.assertEqual(llang_read('"a\nb",c'), [["a\nb", "c"]])

    def test_read_crlf_rows(self):
        self.assertEqual(llang_read("a,b\r\nc,d\r\n"), [["a", "b"], ["c", "d"]])

    def test_read_empty_fields_and_rows(self):
        self.assertEqual(llang_read("a,,b\n\nc,"), [["a", "", "b"], [], ["c", ""]])

    def test_read_empty_text_has_no_rows(self):
        self.assertEqual(llang_read(""), [])

    # --- focused writer tests ------------------------------------------
    def test_write_plain_fields(self):
        self.assertEqual(llang_write([["a", "b"]]), "a,b\r\n")

    def test_write_quotes_only_when_needed(self):
        self.assertEqual(llang_write([["a,b", 'c"d', "e"]]), '"a,b","c""d",e\r\n')

    def test_write_lone_empty_field_is_quoted(self):
        self.assertEqual(llang_write([[""]]), '""\r\n')

    def test_write_empty_row(self):
        self.assertEqual(llang_write([[]]), "\r\n")

    def test_write_multiline_field(self):
        self.assertEqual(llang_write([["a\nb"]]), '"a\nb"\r\n')

    # --- differential tests against the stdlib -------------------------
    def test_reader_matches_stdlib(self):
        self.assertGreaterEqual(len(READ_CASES), 20)
        for case in READ_CASES:
            with self.subTest(case=case):
                self.assertEqual(llang_read(case), stdlib_read(case))

    def test_writer_matches_stdlib(self):
        self.assertGreaterEqual(len(WRITE_CASES), 20)
        for rows in WRITE_CASES:
            with self.subTest(rows=rows):
                self.assertEqual(llang_write(rows), stdlib_write(rows))

    def test_round_trip(self):
        for text in READ_CASES:
            with self.subTest(text=text):
                rows = stdlib_read(text)
                self.assertEqual(llang_read(llang_write(rows)), rows)

    def test_matches_cpython_corpus(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "compare_csv.py")],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        timeout=300)
        self.assertEqual(completed.returncode, 0,
                         f"{completed.stdout}\n{completed.stderr}")
        self.assertIn("0 mismatches", completed.stdout)


if __name__ == "__main__":
    unittest.main()
