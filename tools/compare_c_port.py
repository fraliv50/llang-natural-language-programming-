"""Optional differential harness for the C porting adapter.

Usage: python tools/compare_c_port.py

For every case the harness ports C to canonical English llang with
``CAdapter``, executes the generated llang through ``run.py`` and compares the
output with pinned expected values.  If ``tools/cc.py`` finds a C compiler the
same C source is compiled and executed too, and native stdout must agree with
the port.  Without a compiler the harness degrades to the pinned values.

Every subprocess call has a timeout; a failing case is reported but does not
abort the corpus.  Exit status is 1 if any case failed.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang.portapp.adapters.c import CAdapter  # noqa: E402

CC_WRAPPER = ROOT / "tools" / "cc.py"
LLANG_RUNNER = ROOT / "run.py"
TIMEOUT = 60

CASES = [
    ("arithmetic", r"""
int main(void) {
    int a = 12;
    unsigned int b = 5;
    printf("%d\n", a + b);
    printf("%d\n", a - b);
    printf("%d\n", a * b);
    printf("%d\n", a / b);
    printf("%d\n", a % b);
    return 0;
}
""", ["17", "7", "60", "2", "2"]),
    ("control_flow_and_arrays", r"""
int main(void) {
    int xs[4] = {1, 2, 3, 4};
    int total = 0;
    for (int i = 0; i < 4; i++) { total = total + xs[i]; }
    printf("%d\n", total);
    int n = 0;
    while (n < 3) { n = n + 1; }
    printf("%d\n", n);
    if (total > 9) { printf("%d\n", 1); } else { printf("%d\n", 0); }
    return 0;
}
""", ["10", "3", "1"]),
    ("recursive_function", r"""
int fact(int n) {
    if (n <= 1) { return 1; }
    return n * fact(n - 1);
}
int main(void) { printf("%d\n", fact(6)); return 0; }
""", ["720"]),
    ("negative_division", r"""
int main(void) {
    printf("%d %d\n", -7 / 2, -7 % 2);
    printf("%d %d\n", 7 / -2, 7 % -2);
    return 0;
}
""", ["-3 -1", "-3 1"]),
    ("floating_point", r"""
int main(void) {
    double d = 5.0;
    printf("%g\n", d / 2.0);
    if (d > 2.0) { printf("%d\n", 1); }
    return 0;
}
""", ["2.5", "1"]),
]


def compiler_available():
    try:
        completed = subprocess.run(
            [sys.executable, str(CC_WRAPPER), "--version"],
            cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", timeout=TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0 and "gcc" in completed.stdout.lower()


def native_output(c_source, work):
    """Compile and run one case; return stdout or ``None`` when unavailable."""
    source_path = work / "case.c"
    binary_path = work / "case.exe"
    source_path.write_text("#include <stdio.h>\n" + c_source, encoding="utf-8")
    build = subprocess.run(
        [sys.executable, str(CC_WRAPPER), str(source_path),
         "-std=c11", "-O0", "-o", str(binary_path)],
        cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", timeout=TIMEOUT,
    )
    if build.returncode != 0:
        return None
    run = subprocess.run(
        [str(binary_path)], cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", timeout=TIMEOUT,
    )
    return run.stdout.splitlines() if run.returncode == 0 else None


def llang_output(llang_source, work, index):
    path = work / f"case{index}.ll"
    path.write_text(llang_source, encoding="utf-8")
    run = subprocess.run(
        [sys.executable, str(LLANG_RUNNER), str(path)],
        cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", timeout=TIMEOUT,
    )
    if run.returncode != 0:
        return None, run.stdout + run.stderr
    return run.stdout.splitlines(), ""


def main():
    adapter = CAdapter()
    use_compiler = compiler_available()
    if not use_compiler:
        print("note: no C compiler found (tools/cc.py); comparing pinned values only")
    failures = []

    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        for index, (name, c_source, expected) in enumerate(CASES):
            result = adapter.convert(c_source, f"{name}.c")
            problems = []
            if result.gaps:
                problems.append("gaps: " + "; ".join(str(gap) for gap in result.gaps))
            try:
                actual, error = llang_output(result.source, work, index)
            except (OSError, subprocess.TimeoutExpired) as exc:
                actual, error = None, f"llang run failed: {exc}"
            if actual is None:
                problems.append("llang execution failed: " + error.strip())
            elif actual != expected:
                problems.append(f"llang output {actual!r} != expected {expected!r}")

            native = None
            if use_compiler:
                try:
                    native = native_output(c_source, work)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    problems.append(f"C execution failed: {exc}")
                if native is not None and native != expected:
                    problems.append(f"C output {native!r} != expected {expected!r}")

            status = "PASS" if not problems else "FAIL"
            print(f"{status} {name}: expected={expected} llang={actual}"
                  + (f" native={native}" if native is not None else ""))
            for problem in problems:
                print("    " + problem)
            if problems:
                failures.append(name)

    print(f"\n{len(CASES) - len(failures)}/{len(CASES)} cases passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
