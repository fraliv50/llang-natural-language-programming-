"""Run every verification check in the repository.

Usage: python tools/check.py

This is the single command for contributors and CI. It runs the unit suite,
lints every shipped .ll file, verifies each open-source rewrite against the
stdlib, and checks that documentation links resolve.
"""

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent.parent


def run(command, label):
    print(f"\n=== {label} ===", flush=True)
    completed = subprocess.run(command, cwd=str(ROOT), capture_output=True,
                               text=True, encoding="utf-8", timeout=600)
    output = (completed.stdout or "") + (completed.stderr or "")
    tail = "\n".join(output.strip().splitlines()[-12:])
    if tail:
        print(tail)
    if completed.returncode != 0:
        print(f"FAILED: {label}")
        return False
    print(f"passed: {label}")
    return True


def check_links():
    print("\n=== documentation links ===", flush=True)
    bad = []
    for path in ROOT.rglob("*.md"):
        if "__pycache__" in str(path):
            continue
        text = path.read_text(encoding="utf-8")
        for _label, target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            clean = target.split("#")[0]
            if clean and not (path.parent / clean).resolve().exists():
                bad.append(f"{path}: {target}")
    if bad:
        for item in bad:
            print(item)
        print("FAILED: documentation links")
        return False
    print("passed: documentation links")
    return True


def main() -> int:
    python = sys.executable
    checks = [
        run([python, "-m", "unittest", "discover", "-s", "tests"], "unit tests"),
    ]

    source_files = [p for folder in ("examples", "lib")
                    for p in sorted((ROOT / folder).glob("*.ll"))]
    lint_ok = True
    for source in source_files:
        result = subprocess.run([python, "run.py", "--lint", str(source)],
                                cwd=str(ROOT), capture_output=True,
                                text=True, encoding="utf-8", timeout=120)
        output = (result.stdout or "").strip()
        errors = [line for line in output.splitlines() if line.startswith("error:")]
        if output:
            print(f"lint output for {source}:\n{output}")
        if result.returncode != 0 or errors:
            lint_ok = False
    print(f"\npassed: {len(source_files)} .ll files lint clean" if lint_ok
          else "\nFAILED: lint")
    checks.append(lint_ok)

    for harness in ("compare_shlex.py", "compare_fnmatch.py",
                    "compare_textwrap.py", "compare_csv.py", "compare_json.py",
                    "compare_wasm.py", "compare_re.py", "compare_math.py",
                    "compare_datascience.py", "compare_ml.py", "compare_pylev.py",
                    "compare_humanize.py", "compare_box2d.py",
                    "compare_js_port.py", "compare_c_port.py",
                    "fuzz_semantics.py"):
        checks.append(run([python, f"tools/{harness}"], f"rewrite: {harness}"))

    checks.append(check_links())

    failed = checks.count(False)
    print(f"\n{len(checks) - failed}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
