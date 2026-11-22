# Conversion pilots

These are **unmodified third-party Python source files** used only as inputs to
`tools/port.py`. They are not part of llang and are never imported by the
interpreter. Generated `.ll` outputs are ignored by git.

| File | Origin | License |
|---|---|---|
| `bisect.py` | CPython 3.11 `Lib/bisect.py` | Python Software Foundation License |
| `fnmatch.py` | CPython 3.11 `Lib/fnmatch.py` | Python Software Foundation License |
| `filesize.py` | python-humanize/humanize (see source URL below) | MIT |

Source URLs:

- https://raw.githubusercontent.com/python/cpython/3.11/Lib/bisect.py
- https://raw.githubusercontent.com/python/cpython/3.11/Lib/fnmatch.py
- https://raw.githubusercontent.com/python-humanize/humanize/master/src/humanize/filesize.py

Regenerate a conversion report:

```powershell
python tools/port.py tools/pilots/bisect.py -o tools/pilots/bisect.ll --report tools/pilots/bisect.report.txt
```

Coverage results are recorded in `docs/REWRITES.md`.
