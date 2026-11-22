"""Port a Python file to llang and print a coverage report.

Usage: python tools/port.py <file.py> [-o output.ll] [--report report.txt]

The converter never guesses: every construct it cannot map appears in the
report with a line number. The generated .ll file is passed through the
canonical formatter before being written.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang.converter import convert_source  # noqa: E402
from llang.formatter import format_source  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Port Python source to llang")
    parser.add_argument("source", help="Python source file")
    parser.add_argument("-o", "--output", help="output .ll file")
    parser.add_argument("--report", help="write the coverage report here")
    args = parser.parse_args()

    source_path = Path(args.source)
    source = source_path.read_text(encoding="utf-8")
    result = convert_source(source)

    try:
        formatted = format_source(result.source)
    except Exception as exc:  # keep the raw output for diagnosis
        formatted = result.source
        print(f"WARNING: formatter rejected generated source: {exc}", file=sys.stderr)

    output_path = Path(args.output) if args.output else source_path.with_suffix(".ll")
    output_path.write_text(formatted, encoding="utf-8")

    lines = [
        f"source: {source_path}",
        f"output: {output_path}",
        f"nodes counted: {result.stats['nodes']}",
        f"coverage: {result.covered}%",
        f"unsupported constructs: {len(result.unsupported)}",
    ]
    for item in result.unsupported:
        lines.append(f"  - {item}")
    if result.notes:
        lines.append(f"handled transformations: {len(result.notes)}")
        for item in result.notes:
            lines.append(f"  - {item}")
    report = "\n".join(lines) + "\n"

    if args.report:
        Path(args.report).write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
