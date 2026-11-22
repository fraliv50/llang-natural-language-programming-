"""Unit and differential tests for the native lib/json.ll module."""

import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang import LangError, Lexer, Parser, Interpreter  # noqa: E402


def run(source):
    interpreter = Interpreter(library_paths=[ROOT / "lib"])
    with redirect_stdout(io.StringIO()):
        interpreter.run(Parser(Lexer(source).tokenize()).parse_program())
    return interpreter.output


def ll_string(value):
    """Quote a Python string as an llang string literal."""
    escaped = (value.replace("\\", "\\\\").replace('"', '\\"')
                    .replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r"))
    return '"' + escaped + '"'


def roundtrip(text):
    """Parse a JSON text with the native parser, then stringify the value."""
    program = (
        "use the json module\n"
        f"set value to call parse from json with text = {ll_string(text)}\n"
        "show call stringify from json with value = value\n"
    )
    return run(program)[0]


class NativeJsonTests(unittest.TestCase):
    def test_parse_scalars(self):
        for text, expected in [
            ("null", "null"),
            ("true", "true"),
            ("false", "false"),
            ("0", "0"),
            ("-17", "-17"),
            ("3.5", "3.5"),
            ("-0.0", "-0.0"),
            ("1e20", "1e+20"),
            ("1E-7", "1e-07"),
            ('"hello"', '"hello"'),
        ]:
            with self.subTest(text=text):
                self.assertEqual(roundtrip(text), expected)

    def test_parse_nested_containers(self):
        for text in [
            "[]", "{}", "[1, 2, 3]", '{"a": 1}',
            '{"b": 2, "a": [true, false, null, {"c": []}]}',
            '[[[[1]]], {"x": {"y": {"z": "end"}}}]',
            '  { "spaced" : [ 1 , 2 ] }  ',
        ]:
            with self.subTest(text=text):
                self.assertEqual(roundtrip(text),
                                 json.dumps(json.loads(text), ensure_ascii=False))

    def test_parse_string_escapes(self):
        cases = {
            '"a\\"b"': '"a\\"b"',
            '"a\\\\b"': '"a\\\\b"',
            '"a\\/b"': '"a/b"',
            '"\\b\\f\\n\\r\\t"': '"\\b\\f\\n\\r\\t"',
            '"\\u00e9"': '"é"',
            '"\\u4e2d\\u6587"': '"中文"',
            '"\\u2603"': '"☃"',
            '"\\ud83d\\ude00"': '"😀"',
            '"\\u0000\\u001f"': '"\\u0000\\u001f"',
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(roundtrip(text), expected)
                self.assertEqual(roundtrip(text),
                                 json.dumps(json.loads(text), ensure_ascii=False))

    def test_stringify_matches_python(self):
        values = [
            None, True, False, 0, -5, 2.5, -0.0, 1e20,
            "café ☃ 😀", 'quote " slash \\ line\nbreak',
            "\u0000\u000b\u001f", [], {}, [1, "a", None, False],
            {"b": [1, 2], "a": {"x": True}},
        ]
        for value in values:
            with self.subTest(value=value):
                program = (
                    "use the json module\n"
                    f"set value to call parse from json with text = {ll_string(json.dumps(value, ensure_ascii=False))}\n"
                    "show call stringify from json with value = value\n"
                )
                self.assertEqual(run(program)[0],
                                 json.dumps(value, ensure_ascii=False))

    def test_malformed_input_fails_loudly(self):
        bad = [
            "", "  ", "{", "[1,", '{"a" 1}', '{"a":}', "01", "1.", "-", "1e",
            '"unterminated', '"bad\\q"', '"\\u12"', "[true false]",
            '{"a": 1} trailing', "nul", "\\u0041", "[1,,2]",
        ]
        for text in bad:
            with self.subTest(text=text):
                with self.assertRaises(LangError) as ctx:
                    roundtrip(text)
                self.assertIn("bad_json", str(ctx.exception))

    def test_differential_harness(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "compare_json.py")],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        timeout=300)
        self.assertEqual(completed.returncode, 0,
                         f"{completed.stdout}\n{completed.stderr}")
        self.assertIn("0 mismatches", completed.stdout)


if __name__ == "__main__":
    unittest.main()
