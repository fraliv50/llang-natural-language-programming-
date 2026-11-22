"""Console entry point for the WebAssembly compiler.

Install with `pip install -e .`, then use
`llang-compile file.ll -o file.wasm`.
"""

import argparse
from pathlib import Path

from .compiler import compile_source


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compile llang to WebAssembly")
    parser.add_argument("source", help="llang source file")
    parser.add_argument("-o", "--output", help="output .wasm file")
    parser.add_argument("--report", help="write unsupported constructs here")
    args = parser.parse_args(argv)

    source_path = Path(args.source)
    source = source_path.read_text(encoding="utf-8-sig")
    result = compile_source(source)

    output_path = Path(args.output) if args.output else source_path.with_suffix(".wasm")
    output_path.write_bytes(result.wasm)

    lines = [f"source: {source_path}", f"output: {output_path}",
             f"bytes: {result.stats['bytes']}",
             f"functions: {result.stats['functions']}",
             f"unsupported: {len(result.unsupported)}",
             f"notes: {result.stats['notes']}"]
    for item in result.unsupported:
        lines.append(f"  - {item}")
    report = "\n".join(lines) + "\n"
    if args.report:
        Path(args.report).write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
