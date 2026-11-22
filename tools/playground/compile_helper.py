"""Read llang source from stdin, print JSON with compiled WASM and reports."""

import base64
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from llang.compiler import compile_source  # noqa: E402

source = sys.stdin.read()
result = compile_source(source)
print(json.dumps({
    "wasm": base64.b64encode(result.wasm).decode("ascii"),
    "unsupported": [str(item) for item in result.unsupported],
    "notes": [str(item) for item in result.notes] if hasattr(result, "notes") else [],
    "stats": result.stats,
}))
