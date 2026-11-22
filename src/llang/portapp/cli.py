"""Command-line entry point for the universal porting application.

    python -m llang.portapp.cli <repo-dir> -o <output-dir> [--cleanup PATH]
        [--verify/--no-verify] [--include EXT ...]
"""

from __future__ import annotations

import argparse
from typing import Sequence

from .pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m llang.portapp.cli",
        description="Port a source repository to readable llang.",
    )
    parser.add_argument("repo_dir", help="source repository to read (never modified)")
    parser.add_argument("-o", "--output", required=True,
                        help="directory for converted .ll files and reports")
    parser.add_argument("--cleanup", metavar="PATH",
                        help="where to write cleanup_queue.jsonl "
                             "(default: inside the output directory)")
    parser.add_argument("--verify", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="lint/parse-check converted files (default: on)")
    parser.add_argument("--include", action="append", default=[], metavar="EXT",
                        help="only port this extension; repeat for several")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_pipeline(
        args.repo_dir,
        args.output,
        cleanup_path=args.cleanup,
        verify=args.verify,
        include=args.include or None,
    )

    print(f"Ported {summary.files_converted}/{summary.files_scanned} file(s) "
          f"from {summary.repository} -> {summary.output}")
    if summary.files_failed:
        print(f"  errors: {summary.files_failed}")
    print(f"  gaps: {summary.total_gaps} across {summary.files_with_gaps} file(s)")
    if summary.verification_enabled:
        print(f"  verification: {summary.verification_passed} passed, "
              f"{summary.verification_failed} failed")
    else:
        print("  verification: skipped")
    print(f"  cleanup queue: {summary.reports['cleanup_queue']}")
    print(f"  reports: {summary.reports['json']}, {summary.reports['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
