"""Turn a cleanup-queue item into a ready-to-paste prompt for an AI agent.

Usage:
    python tools/cleanup_prompt.py <cleanup_queue.jsonl> <index>
    python tools/cleanup_prompt.py <cleanup_queue.jsonl> --all

The emitted prompt contains everything an AI needs to finish a port: the
original source, the partial llang, the explicit gaps, and the rules of the
target language.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

INSTRUCTIONS = """You are finishing an automated source-to-llang port.

Rules:
- Read docs/GRAMMAR.md and docs/REFERENCE.md before writing code.
- Keep every construct EXPLICIT: no implicit coercion, no operator precedence,
  always parenthesize compound expressions, and close every block with
  `end if` / `end repeat` / `end function` / `end expect`.
- Calls use labeled roles: `call NAME with label = value`. Definitions may use
  phrase names. A leading `@` escapes any reserved word used as a name.
- Preserve the original program's observable behaviour. Do not "improve" it.
- Replace every GAP listed below with correct llang. Do not drop code silently.
- When done, write the complete file to the stated output path and verify with
  `python run.py --lint <output>`; fix any diagnostics before finishing.
"""


def render(item: dict) -> str:
    gaps = item.get("gaps", [])
    if not gaps and item.get("gap"):
        gaps = [item["gap"]]
    gap_text = "\n".join(
        f"- {gap if isinstance(gap, str) else json.dumps(gap, ensure_ascii=False)}"
        for gap in gaps
    ) or "(none reported)"
    source = item.get("source", item.get("source_snippet", ""))
    partial = item.get("converted_source",
                       item.get("partial_llang", item.get("partial_source", "")))
    return (
        INSTRUCTIONS
        + "\n## Source file\n\n" + str(item.get("source_path", "unknown"))
        + "\n\n## Source language\n\n" + str(item.get("source_language", "unknown"))
        + "\n\n## Target file\n\n" + str(item.get("target_path", "ported.ll"))
        + "\n\n## Gaps to resolve\n\n" + gap_text
        + "\n\n## Original source\n\n```\n" + source + "\n```"
        + "\n\n## Partial llang (may be invalid)\n\n```llang\n" + partial + "\n```"
        + "\n\n## Task\n\nProduce the complete, lint-clean llang file for the target path."
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Render AI cleanup prompts")
    parser.add_argument("queue", help="cleanup_queue.jsonl")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("index", nargs="?", type=int, help="zero-based item index")
    group.add_argument("--all", action="store_true", help="print all prompts")
    args = parser.parse_args(argv)

    items = []
    for line in Path(args.queue).read_text(encoding="utf-8").splitlines():
        if line.strip():
            items.append(json.loads(line))
    if args.all:
        for index, item in enumerate(items):
            print(f"\n===== ITEM {index} =====\n")
            print(render(item))
        return 0
    if args.index < 0 or args.index >= len(items):
        print(f"index out of range (0..{len(items) - 1})")
        return 1
    print(render(items[args.index]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
