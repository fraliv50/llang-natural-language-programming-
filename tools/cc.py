"""Locate and invoke a C compiler for optional c-ll differential testing.

Usage: python tools/cc.py <gcc arguments...>

Set the CC environment variable to override discovery. The Winget WinLibs
path is a last-resort fallback for the development machine where this project
was built; it is not required by CI or the test suite.
"""

import os
import shutil
import subprocess
import sys


def find_compiler():
    if os.environ.get("CC"):
        return os.environ["CC"]
    for candidate in ("gcc", "clang", "x86_64-w64-mingw32-gcc"):
        path = shutil.which(candidate)
        if path:
            return path
    winget = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Microsoft", "WinGet", "Packages",
        "BrechtSanders.WinLibs.MCF.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe",
        "mingw64", "bin", "gcc.exe",
    )
    return winget if os.path.isfile(winget) else None


def main():
    compiler = find_compiler()
    if not compiler:
        print("no C compiler found (set CC to a gcc/clang binary)")
        return 1
    return subprocess.run([compiler, *sys.argv[1:]], timeout=300).returncode


if __name__ == "__main__":
    raise SystemExit(main())
