"""End-to-end repository porting orchestration.

scan -> convert -> write -> verify -> report.  Source files are only ever
read.  Converted ``.ll`` files and all reports are written to a separate
output directory, preserving the repository's relative structure.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from . import cleanup, verifier
from .adapters import ADAPTERS
from .scanner import scan_repo


@dataclass
class PipelineSummary:
    """Counts and artifact paths returned by :func:`run_pipeline`."""

    repository: str
    output: str
    files_scanned: int = 0
    files_converted: int = 0
    files_failed: int = 0
    files_with_gaps: int = 0
    total_gaps: int = 0
    verification_enabled: bool = False
    files_verified: int = 0
    verification_passed: int = 0
    verification_failed: int = 0
    reports: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _render_report(
    summary: PipelineSummary,
    records: list[dict],
    cleanup_items: list[cleanup.CleanupItem],
    verifications: list[verifier.FileVerification],
) -> str:
    lines = [
        "# Porting report",
        "",
        f"- Repository: `{summary.repository}`",
        f"- Output: `{summary.output}`",
        f"- Files scanned: {summary.files_scanned}",
        f"- Files converted: {summary.files_converted}",
        f"- Files failed: {summary.files_failed}",
        f"- Files with gaps: {summary.files_with_gaps}",
        f"- Total gaps: {summary.total_gaps}",
        f"- Verification: {'enabled' if summary.verification_enabled else 'disabled'}"
        + (f" ({summary.verification_passed} passed, "
           f"{summary.verification_failed} failed)"
           if summary.verification_enabled else ""),
        "",
        "## Files",
        "",
        "| Source | Target | Language | Coverage | Gaps | Verification |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for record in records:
        verification = record.get("verification") or {}
        status = verification.get("passed")
        label = "skipped" if status is None else ("pass" if status else "FAIL")
        if record.get("error"):
            label = "ERROR"
        lines.append(
            f"| {record['source']} | {record['target'] or '-'} | "
            f"{record['source_language']} | {record['coverage']}% | "
            f"{record['gap_count']} | {label} |"
        )
    lines.append("")
    for record in records:
        if record.get("error"):
            lines.extend([f"**{record['source']}** — error: {record['error']}", ""])
    lines.append(cleanup.render_report(cleanup_items))
    return "\n".join(lines).rstrip() + "\n"


def run_pipeline(
    repo_dir: str | Path,
    output_dir: str | Path,
    cleanup_path: str | Path | None = None,
    verify: bool = True,
    include: Iterable[str] | None = None,
    project_root: str | Path | None = None,
    timeout: float = verifier.DEFAULT_TIMEOUT,
) -> PipelineSummary:
    """Port every scannable file in ``repo_dir`` and return a summary.

    Args:
        repo_dir: source repository to read.  Never modified.
        output_dir: destination for converted files and reports.
        cleanup_path: optional override for the cleanup JSONL file.
        verify: run the linter/parser checks on converted files.
        include: optional extension filter (with or without a leading dot).
        project_root: llang root containing ``run.py`` (for verification).
        timeout: per-file lint subprocess timeout, in seconds.
    """
    repo = Path(repo_dir).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)

    queue_path = Path(cleanup_path).resolve() if cleanup_path else output / "cleanup_queue.jsonl"
    report_json_path = output / "report.json"
    report_md_path = output / "REPORT.md"

    adapters_by_name = {adapter.name: adapter for adapter in ADAPTERS}
    entries = scan_repo(repo, output_dir=output, include=include)

    summary = PipelineSummary(
        repository=str(repo),
        output=str(output),
        files_scanned=len(entries),
        verification_enabled=verify,
    )
    records: list[dict] = []
    cleanup_items: list[cleanup.CleanupItem] = []
    converted_paths: list[Path] = []

    for relative, absolute, adapter_name in entries:
        target_relative = Path(relative).with_suffix(".ll").as_posix()
        record = {
            "source": relative,
            "target": target_relative,
            "source_language": adapter_name,
            "adapter": adapter_name,
            "coverage": 0.0,
            "complete": False,
            "gap_count": 0,
            "notes_count": 0,
            "stats": {},
            "gaps": [],
            "error": None,
            "verification": None,
        }
        adapter = adapters_by_name.get(adapter_name)
        if adapter is None:
            record["error"] = f"no adapter registered as '{adapter_name}'"
            records.append(record)
            summary.files_failed += 1
            continue

        try:
            source_text = Path(absolute).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            record["error"] = f"cannot read source: {exc}"
            records.append(record)
            summary.files_failed += 1
            continue

        try:
            result = adapter.convert(source_text, absolute)
        except Exception as exc:  # one bad file must not abort the port
            record["error"] = f"adapter failed: {type(exc).__name__}: {exc}"
            records.append(record)
            summary.files_failed += 1
            continue

        target = output / target_relative
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(result.source, encoding="utf-8")
        except OSError as exc:
            record["error"] = f"cannot write output: {exc}"
            records.append(record)
            summary.files_failed += 1
            continue

        converted_paths.append(target)
        language = result.source_language or adapter_name
        record.update({
            "source_language": language,
            "coverage": result.covered,
            "complete": result.complete,
            "gap_count": len(result.gaps),
            "notes_count": len(result.notes),
            "stats": result.stats,
            "gaps": [
                {
                    "line": gap.line,
                    "node_type": gap.node_type,
                    "reason": gap.reason,
                    "description": cleanup.describe_gap(gap),
                }
                for gap in result.gaps
            ],
        })
        records.append(record)
        summary.files_converted += 1
        if result.gaps:
            summary.files_with_gaps += 1
            summary.total_gaps += len(result.gaps)
            cleanup_items.extend(cleanup.build_items(
                relative, target_relative, result, source_text,
            ))

    verifications: list[verifier.FileVerification] = []
    if verify:
        verifications = verifier.verify_many(
            converted_paths, project_root=project_root, timeout=timeout,
        )
        by_path = {str(item.path): item.to_dict() for item in verifications}
        for record in records:
            target = output / record["target"]
            if record["target"] and str(target) in by_path:
                record["verification"] = by_path[str(target)]
        summary.files_verified = len(verifications)
        summary.verification_passed = sum(1 for item in verifications if item.passed)
        summary.verification_failed = sum(1 for item in verifications if not item.passed)

    summary.reports = {
        "json": str(report_json_path),
        "markdown": str(report_md_path),
        "cleanup_queue": str(queue_path),
    }

    cleanup.write_queue(cleanup_items, queue_path)
    report_json_path.write_text(
        json.dumps({
            "summary": summary.to_dict(),
            "files": records,
            "verification": [item.to_dict() for item in verifications],
            "cleanup": {
                "queue": str(queue_path),
                "items": len(cleanup_items),
            },
        }, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report_md_path.write_text(
        _render_report(summary, records, cleanup_items, verifications),
        encoding="utf-8",
    )
    return summary
