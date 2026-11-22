# Self-hosting experiment

These files are **first-draft automatic conversions** of the interpreter's own
Python source, produced with `tools/port.py`. They are diagnostic artifacts,
not working llang programs. They show exactly where llang cannot yet express
its own implementation.

Regenerate with:

```powershell
foreach ($f in @('lexer.py','errors.py','synonyms.py','ast_nodes.py','parser.py','interpreter.py','formatter.py','linter.py')) {
  python tools/port.py "src/llang/$f" -o "tools/selfhost/$($f -replace '\.py$','.ll')" --report "tools/selfhost/$($f -replace '\.py$','.report.txt')"
}
```

Observed coverage (node-based, before recent converter fixes):

| Module | Coverage | Main blockers |
|---|---|---|
| `lexer.py` | 16.7% | regex usage, classes, `is` identity |
| `errors.py` | 16.7% | dataclasses, f-strings, `__str__` |
| `synonyms.py` | 64.1% | module-level data structures |
| `ast_nodes.py` | 3.4% | dataclasses |
| `parser.py` | 20.0% | classes, recursion patterns |
| `interpreter.py` | 82.3% | classes, generators, `is`, comprehensions |
| `formatter.py` | 86.5% | f-strings, classes |
| `linter.py` | 81.7% | dataclasses, class methods |

The `.ll` and `.report.txt` files are gitignored. The analysis is captured in
`docs/research/self-hosting-plan.md`.
