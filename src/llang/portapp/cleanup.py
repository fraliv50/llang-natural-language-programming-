"""The "clean remaining with AI" hand-off format.

An adapter reports every construct it cannot translate as a :class:`Gap`.
This module turns those gaps into a machine-readable JSONL queue and a
human-readable Markdown report.  Each queue entry carries everything an agent
needs to finish one translation: where the source came from, where the result
belongs, what exactly was missed, the original source context, the partial
llang produced so far, and a concrete prompt.

Nothing here calls an AI service.  The queue is an explicit interface: a human
or an agent reads it, performs the translation, and writes the finished ``.ll``
file back to the target path.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .models import ConversionResult, Gap

CONTEXT_LINES = 2


@dataclass
class CleanupItem:
    """One untranslated construct, ready for agent-driven cleanup."""

    source_path: str
    target_path: str
    source_language: str
    gap: dict
    source_snippet: str
    partial_llang: str
    prompt: str

    def to_dict(self) -> dict:
        return asdict(self)


def describe_gap(gap: Gap) -> str:
    """Human-readable gap description that always mentions the line."""
    where = f"line {gap.line}" if gap.line else "unknown line"
    return f"{where}: {gap.node_type} - {gap.reason}"


def source_snippet(
    source_text: str,
    line: int | None,
    fallback: str = "",
    context: int = CONTEXT_LINES,
) -> str:
    """Return source lines around ``line``, numbered for easy reference."""
    if not line:
        return fallback or source_text
    lines = source_text.splitlines()
    if not lines:
        return fallback
    start = max(0, line - 1 - context)
    end = min(len(lines), line + context)
    numbered = [f"{index + 1}: {lines[index]}" for index in range(start, end)]
    return "\n".join(numbered) if numbered else fallback


def build_prompt(
    source_path: str,
    source_language: str,
    description: str,
    snippet: str,
    partial_llang: str,
) -> str:
    """Compose a self-contained prompt for finishing one translation."""
    return (
        f"Finish the mechanical port of this {source_language} source to llang.\n"
        f"Source file: {source_path}\n"
        f"Untranslated construct: {description}\n\n"
        f"Original {source_language} source around the gap:\n"
        "---\n"
        f"{snippet}\n"
        "---\n\n"
        "Partially converted llang (already valid; keep it unchanged):\n"
        "---\n"
        f"{partial_llang.rstrip()}\n"
        "---\n\n"
        "Task: express ONLY the untranslated construct in correct, readable "
        "llang that preserves the original semantics exactly. Return the "
        "complete finished llang program as plain text (no Markdown fences, "
        "no commentary). Use explicit `end if`, `end repeat`, `end function` "
        "and `end expect` terminators, one statement per line, and fully "
        "parenthesized expressions. Do not guess semantics: if a construct "
        "genuinely has no llang equivalent, explain that in a final line "
        "starting with `#` instead of inventing behavior."
    )


def build_items(
    source_path: str,
    target_path: str,
    result: ConversionResult,
    source_text: str = "",
) -> list[CleanupItem]:
    """Build one cleanup item per gap in a conversion result."""
    language = result.source_language or "unknown"
    items = []
    for gap in result.gaps:
        description = describe_gap(gap)
        snippet = source_snippet(source_text, gap.line, gap.source_snippet)
        items.append(CleanupItem(
            source_path=source_path,
            target_path=target_path,
            source_language=language,
            gap={
                "line": gap.line,
                "node_type": gap.node_type,
                "reason": gap.reason,
                "description": description,
            },
            source_snippet=snippet,
            partial_llang=result.source,
            prompt=build_prompt(source_path, language, description, snippet,
                                result.source),
        ))
    return items


def render_queue(items: list[CleanupItem]) -> str:
    """Serialize cleanup items as JSON Lines (one JSON object per line)."""
    return "".join(
        json.dumps(item.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
        for item in items
    )


def write_queue(items: list[CleanupItem], path: str | Path) -> Path:
    """Write the machine-readable cleanup queue and return its path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_queue(items), encoding="utf-8")
    return path


def render_report(items: list[CleanupItem]) -> str:
    """Render the human-readable Markdown cleanup report."""
    if not items:
        return (
            "## Cleanup queue\n\n"
            "No gaps were reported: every scanned file was translated "
            "mechanically.\n"
        )
    files = len({item.source_path for item in items})
    lines = [
        "## Cleanup queue",
        "",
        f"{len(items)} construct(s) across {files} file(s) need AI cleanup. "
        "Each entry in `cleanup_queue.jsonl` is an independent prompt: an "
        "agent resolves one entry, writes the finished `.ll` file to its "
        "target path, and moves to the next.",
        "",
    ]
    for item in items:
        description = item.gap.get("description", describe_gap(Gap("", "")))
        lines.extend([
            f"### {item.source_path} — {description}",
            "",
            f"- **Source:** {item.source_path}",
            f"- **Target:** {item.target_path}",
            f"- **Source language:** {item.source_language}",
            f"- **Gap:** {description}",
            "",
            "**Original source around the gap:**",
            "",
            "```text",
            item.source_snippet,
            "```",
            "",
            "**Partially converted llang:**",
            "",
            "```text",
            item.partial_llang.rstrip(),
            "```",
            "",
            "**AI prompt:**",
            "",
            "```text",
            item.prompt,
            "```",
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def write_report(items: list[CleanupItem], path: str | Path) -> Path:
    """Write the Markdown cleanup report and return its path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(items), encoding="utf-8")
    return path
