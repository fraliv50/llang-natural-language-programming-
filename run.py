"""Run, lint, or format an llang source file."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from llang import LangError, Lexer, Parser, lint_source, run_file  # noqa: E402


USAGE = """usage: python run.py [OPTION] <file.ll>

  (no option)  run the program
  --lint       report static diagnostics without running
  --format     print the canonical form (synonyms normalized)
"""


def main() -> None:
    args = sys.argv[1:]
    option = None
    if args and args[0] in ("--lint", "--format"):
        option = args.pop(0)
    if len(args) != 1:
        print(USAGE, end="")
        sys.exit(2)

    path = Path(args[0])
    try:
        source = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        print(f"ERROR: cannot read {path}: {exc}")
        sys.exit(1)

    try:
        if option == "--lint":
            diagnostics = lint_source(source)
            for diagnostic in diagnostics:
                print(diagnostic)
            if any(item.severity == "error" for item in diagnostics):
                sys.exit(1)
            return

        if option == "--format":
            from llang.formatter import format_source
            print(format_source(source), end="")
            return

        run_file(path)
    except LangError as exc:
        print(f"ERROR: {exc.render()}")
        sys.exit(1)


if __name__ == "__main__":
    main()
