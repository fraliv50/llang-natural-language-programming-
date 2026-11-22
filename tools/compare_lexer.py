"""Differential test: llang's self-hosted lexer vs the Python bootstrap lexer.

Compares token kind, text and source position for every token, including EOF.
"""

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang import Lexer, run_source  # noqa: E402

CORPUS = [
    "",
    "set x to 5\nshow x\n",
    "# comment\nshow 1",
    'show "hello"',
    'show "a\\nb\\tc\\"d\\\\e"',
    "show 3.14",
    "show 0.0001 plus 100",
    "set xs to a list of 1, 2, 3",
    "if x is greater than 5 then\n    show \"yes\"\nend if",
    "call f with a = 1, b = 2",
    "show item 0 of xs",
    "  \t show 1  \r\n",
    "# trailing comment\n",
    'show "unterminated',
    "show @end + 1",
    "set @function to 5",
]


def llang_tokens(source):
    literal = json.dumps(source, ensure_ascii=False)
    program = (
        "use the llang_lexer module\n"
        "use the json module\n"
        f"set toks to call tokenize from llang_lexer with text = {literal}\n"
        "show call stringify from json with value = "
        "(call token_digests from llang_lexer with tokens = toks)\n"
    )
    with redirect_stdout(io.StringIO()):
        interpreter = run_source(program)
    return json.loads(interpreter.output[-1])


def python_tokens(source):
    return [[token.kind, token.text, token.pos.line, token.pos.column]
            for token in Lexer(source).tokenize()]


def main():
    failures = 0
    compared = 0
    for source in CORPUS:
        try:
            expected_py = python_tokens(source)
        except Exception:
            # Both lexers must reject malformed input.
            try:
                llang_tokens(source)
                print(f"SOURCE {source!r}: python rejected but llang accepted")
                failures += 1
            except Exception:
                pass
            continue
        try:
            actual = llang_tokens(source)
        except Exception as exc:
            print(f"SOURCE {source!r}: llang lexer error: {exc}")
            failures += 1
            continue
        if expected_py != actual:
            failures += 1
            print(f"SOURCE {source!r}:\n  python: {expected_py}\n  llang:  {actual}")
        compared += 1
    print(f"compared {compared} sources, {failures} mismatches")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
