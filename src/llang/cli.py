"""Console entry point for llang.

Install with `pip install -e .`, then use `llang <file.ll>`,
`llang --lint <file.ll>` or `llang --format <file.ll>`.
"""

import argparse
import sys
from pathlib import Path

from . import LangError, Lexer, Parser, Interpreter, lint_source, run_file
from .formatter import format_source


USAGE = """llang — run, lint, or format llang programs

  llang file.ll          run the program
  llang --lint file.ll   report static diagnostics without running
  llang --format file.ll print the canonical form
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="llang command line interface",
                                     add_help=True)
    parser.add_argument("file", nargs="?", help="path to a .ll source file")
    parser.add_argument("--lint", action="store_true", help="report diagnostics only")
    parser.add_argument("--format", action="store_true", help="print canonical source")
    args = parser.parse_args(argv)

    if not args.file:
        print(USAGE, end="")
        return 2

    path = Path(args.file)
    try:
        source = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        print(f"ERROR: cannot read {path}: {exc}")
        return 1

    try:
        if args.lint:
            diagnostics = lint_source(source)
            for diagnostic in diagnostics:
                print(diagnostic)
            return 1 if any(item.severity == "error" for item in diagnostics) else 0
        if args.format:
            print(format_source(source), end="")
            return 0
        run_file(path)
        return 0
    except LangError as exc:
        print(f"ERROR: {exc.render()}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
