"""Console entry point for the Python-to-llang converter.

Install with `pip install -e .`, then use
`llang-port file.py -o ported.ll --report report.txt`.
"""

import argparse
from pathlib import Path

from .converter import convert_source
from .formatter import format_source


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Port Python source to llang")
    parser.add_argument("source", help="Python source file")
    parser.add_argument("-o", "--output", help="output .ll file")
    parser.add_argument("--report", help="write the coverage report here")
    args = parser.parse_args(argv)

    source_path = Path(args.source)
    source = source_path.read_text(encoding="utf-8")
    result = convert_source(source)

    try:
        formatted = format_source(result.source)
    except Exception as exc:  # keep raw output for diagnosis
        formatted = result.source
        print(f"WARNING: formatter rejected generated source: {exc}")

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
