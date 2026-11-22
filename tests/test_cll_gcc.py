"""Real-compiler differential tests for the c-ll surface.

Skipped when no gcc/clang is available. The corpus avoids undefined behaviour
in C: all divisions have non-zero divisors, all arithmetic stays well within
32-bit range, and every expression is fully parenthesized in both languages.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang.cll import run_c_source  # noqa: E402

CC_WRAPPER = ROOT / "tools" / "cc.py"

CASES = [
    (
        "let x as int be 3\nlet y as int be 7\nshow x, y\n",
        "int main(void){int x=3; int y=7; printf(\"%d %d\\n\", x, y); return 0;}\n",
    ),
    (
        "let r as int be (2 plus (3 times 4))\nshow r\n",
        "int main(void){int r=(2+(3*4)); printf(\"%d\\n\", r); return 0;}\n",
    ),
    (
        "let q as int be ((0 minus 7) divided by 2)\nshow q\n",
        "int main(void){int q=((-7)/2); printf(\"%d\\n\", q); return 0;}\n",
    ),
    (
        "let m as int be ((0 minus 7) remainder 2)\nshow m\n",
        "int main(void){int m=((-7)%2); printf(\"%d\\n\", m); return 0;}\n",
    ),
    (
        """define function fact giving int taking n as int
    if n is at most 1 then
        give back 1
    otherwise
        give back (n times (call fact with (n minus 1)))
    end if
end function
show call fact with 6
""",
        """int fact(int n){if(n<=1){return 1;}else{return (n*(fact((n-1))));}}
int main(void){printf("%d\\n", fact(6)); return 0;}
""",
    ),
]


def compiler_available():
    completed = subprocess.run(
        [sys.executable, str(CC_WRAPPER), "--version"],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        timeout=60,
    )
    return completed.returncode == 0 and "gcc" in completed.stdout.lower()


@unittest.skipUnless(compiler_available(), "no C compiler available")
class ClIGccTests(unittest.TestCase):
    def test_matches_gcc(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            for index, (cll_source, c_source) in enumerate(CASES):
                with self.subTest(case=index):
                    expected_lines = run_c_source(cll_source).output

                    source_path = work / f"case{index}.c"
                    binary_path = work / f"case{index}.exe"
                    source_path.write_text(
                        "#include <stdio.h>\n" + c_source, encoding="utf-8")
                    build = subprocess.run(
                        [sys.executable, str(CC_WRAPPER), str(source_path),
                         "-std=c11", "-O0", "-o", str(binary_path)],
                        cwd=str(ROOT), capture_output=True, text=True,
                        encoding="utf-8", timeout=120,
                    )
                    self.assertEqual(build.returncode, 0, build.stderr)
                    run = subprocess.run(
                        [str(binary_path)], cwd=str(ROOT), capture_output=True,
                        text=True, encoding="utf-8", timeout=60,
                    )
                    self.assertEqual(run.returncode, 0, run.stderr)
                    self.assertEqual(expected_lines, run.stdout.splitlines())


if __name__ == "__main__":
    unittest.main()
