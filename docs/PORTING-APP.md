# The universal porting application

The porting application converts a *repository* of source files into readable
llang. It is deliberately conservative: a file is translated only by an
adapter that claims its extension, and every construct the adapter cannot map
is reported as a gap rather than silently guessed. Gaps become an explicit
hand-off queue for AI cleanup.

## Architecture

```
src/llang/portapp/
  models.py            Adapter, ConversionResult, Gap  (shared contract)
  adapters/            registry + one adapter per source language
  scanner.py           repo walk, exclusions, language detection
  cleanup.py           JSONL cleanup queue + Markdown report
  verifier.py          parse check + `python run.py --lint <file>`
  pipeline.py          scan -> convert -> write -> verify -> report
  cli.py               `python -m llang.portapp.cli`
```

The data flow is one-way:

1. `scanner.scan_repo(root)` returns `(relative_path, absolute_path,
   adapter_name)` triples. It prunes `.git`, `node_modules`, `__pycache__`,
   virtual environments, vendored/rewritten trees (`vendor`, `third_party`,
   `rewrites`, ...), build outputs (`build`, `dist`, `out`, ...), and the
   configured output directory.
2. `pipeline.run_pipeline` reads each source file and calls
   `adapter.convert(source, absolute_path)`. Converted text is written to the
   output directory under the same relative path with a `.ll` suffix.
3. `verifier` checks each converted file in two ways: an in-process
   lexer/parser check, and the canonical `python run.py --lint <file>`
   subprocess with a timeout. Source files are never modified.
4. `cleanup` turns every gap into an independent cleanup item. The pipeline
   emits `report.json` (machine-readable), `REPORT.md` (human-readable, with
   the cleanup report embedded), and `cleanup_queue.jsonl`.

## Usage

```powershell
python -m llang.portapp.cli <repo-dir> -o <output-dir>
python -m llang.portapp.cli <repo-dir> -o out --include py --include zzz
python -m llang.portapp.cli <repo-dir> -o out --no-verify
python -m llang.portapp.cli <repo-dir> -o out --cleanup C:\work\queue.jsonl
```

Options:

- `-o/--output` (required): destination directory; created if missing.
- `--cleanup PATH`: where to write `cleanup_queue.jsonl`. By default it goes
  into the output directory.
- `--verify/--no-verify`: enable or skip lint/parse verification (default:
  verify). Each lint subprocess has a 30-second timeout.
- `--include EXT`: restrict scanning to the given extension(s); repeatable.
  Leading dots are optional and matching is case-insensitive.

From Python:

```python
from llang.portapp.pipeline import run_pipeline

summary = run_pipeline("path/to/repo", "path/to/out", verify=True)
print(summary.files_converted, summary.total_gaps, summary.reports)
```

`run_pipeline` never raises for per-file failures: unreadable files, adapter
exceptions and missing runners are recorded as errors in `report.json` and
counted in `summary.files_failed`.

## Adapter contract

An adapter is any object with these attributes and method:

```python
class Adapter(Protocol):
    name: str                 # unique registry key, e.g. "python"
    extensions: tuple[str, ...]  # suffixes without dots, e.g. ("py", "pyw")

    def convert(self, source: str, path: str) -> ConversionResult: ...
```

- `source` is the file text (UTF-8); `path` is the absolute source path.
- `ConversionResult.source` is the partially converted llang text, written
  verbatim to the target `.ll` file.
- `ConversionResult.gaps` is a list of `Gap(node_type, reason, line,
  source_snippet)`. **Report every untranslated construct**; never emit a
  plausible but wrong translation.
- `ConversionResult.notes` records handled transformations for auditing.
- `ConversionResult.stats` may include a `nodes` count used to compute
  `covered` (percentage of nodes translated).
- `ConversionResult.source_language` labels the output in reports.

Register an adapter by importing `register` from
`llang.portapp.adapters` and calling `register(MyAdapter())` (see
`adapters/python.py`). Registration is global; `adapter_for(path)` resolves a
path to the first adapter whose extensions match. Extension detection is the
only language detection the scanner performs — there is no content sniffing.

## Cleanup queue format

`cleanup_queue.jsonl` contains one JSON object per line, one per gap:

```json
{"gap": {"description": "line 12: ClassDef - classes are unsupported",
         "line": 12, "node_type": "ClassDef", "reason": "classes are unsupported"},
 "partial_llang": "show \"part\"\n",
 "prompt": "Finish the mechanical port of this python source to llang ...",
 "source_language": "python",
 "source_path": "pkg/models.py",
 "source_snippet": "10: ...\n11: class Foo:\n12:     pass\n13: ...",
 "target_path": "pkg/models.ll"}
```

Field meanings:

- `source_path`, `target_path`: repository-relative source path and its
  output-relative `.ll` destination.
- `source_language`: adapter label for the source language.
- `gap`: structured description including a line number when available.
- `source_snippet`: the original source lines around the gap (±2 lines),
  numbered; this is what the adapter could not translate.
- `partial_llang`: everything the adapter *did* translate, unchanged.
- `prompt`: a self-contained instruction to finish the translation in llang,
  using explicit block terminators and parenthesized expressions.

`REPORT.md` renders the same items as readable sections; when there are no
gaps it says so explicitly.

## Limitations

- **AI cleanup is manual/agent-driven, not automatic.** The pipeline writes a
  queue; it never calls a model, edits the partial llang, or fills in gaps
  itself. An agent or human reads each entry, produces the finished `.ll`
  file, and writes it to `target_path`. Re-run the verifier afterwards.
- Extension-based detection can mislabel files (e.g. a generator template
  with a `.py` suffix). The scanner's exclusion list is a heuristic; add
  project-specific names via `skip_dirs` if needed.
- Mechanical translation is one-way and lossy by design: unsupported
  constructs are reported, not preserved as comments or executed as a
  fallback. `covered` is a count-based estimate, not a semantic proof.
- Verification checks syntax and the linter's static rules; it does not prove
  behavioural equivalence with the original source. Differential testing
  against the source language remains a separate activity.
- A failed lint subprocess (missing `run.py`, timeout, crash) is reported as
  a verification failure; it does not stop the rest of the port.
