# LSP 3.17 conformance research — grounding `src/llang/lsp.py`

Authoritative source: **LSP 3.17 specification**, <https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/>. Every claim below is footnoted with that URL plus the section anchor. Local evidence: `src/llang/lsp.py` (abbrev. `lsp.py`), `tests/test_lsp.py` (abbrev. `test_lsp.py`), `docs/METHOD.md`.

> Scope: only the methods we implement, plus the cross-cutting rules that decide whether their messages are legal. All line references are to the files as of this research commit.

---

## 1. Authoritative message shapes and lifecycle rules

### 1.1 Base protocol (framing, JSON-RPC 2.0, errors)

- Wire format = HTTP-like header + content separated by `\r\n`. Header fields are `Name: value\r\n`, ASCII encoded; **at least one header is mandatory** and two consecutive `\r\n` precede the body. Required: `Content-Length` (a **number of bytes**, not characters); optional `Content-Type`, default `application/vscode-jsonrpc; charset=utf-8`. Only UTF-8 content is supported; a different charset should be answered with an error. For backwards compatibility treat `utf8` as `utf-8`. [#headerPart], [#contentPart].
- JSON-RPC version is always `"2.0"`. Params, if present, **should be an object** in LSP (arrays allowed only for custom messages). [#abstractMessage] / [#languageServerProtocol].
- **Request** (`#requestMessage`): `jsonrpc: "2.0"` (required), `id: integer | string` (required), `method: string` (required), `params?: array | object`. *Every processed request must send a response.*
- **Response** (`#responseMessage`): `jsonrpc`, `id: integer | string | null`, and **exactly one** of `result` (REQUIRED on success, set to `null` when there is no value) or `error: {code: integer, message: string, data?: LSPAny}`. `result` MUST NOT exist on error. This is why `shutdown` returns `{"result": null}` and why returning nothing for a request is a violation.
- **Notification** (`#notificationMessage`): `jsonrpc`, `method`, optional `params`, **no `id`**, and **must not** receive a response. `textDocument/publishDiagnostics` is a *server→client* notification.
- Error codes of interest: `ParseError -32700`, `InvalidRequest -32600`, `MethodNotFound -32601`, `InvalidParams -32602`, `InternalError -32603`, `ServerNotInitialized -32002` (message/request received before `initialize`), `RequestCancelled -32800`, `RequestFailed -32803`. LSP reserves −32099..−32000 and −32899..−32800. [#errorCodes].
- `methods` beginning `$/` may be ignored as notifications; as requests they must error with `-32601`. [#dollarRequests].
- An `id` has no meaning on a notification; treating a message with `id` as a notification is wrong, and vice versa.

### 1.2 Positions, ranges, EOLs, encodings — the subtle part

- A `Position` is **zero-based line** (`uinteger`) and **zero-based character** (`uinteger`). It denotes a point *between* two characters (like a cursor); negative sentinels such as `-1` are illegal. **If `character` exceeds the line length it defaults to the line length.** [#position].
- A `Range` has `start: Position` and `end: Position`; **`end` is exclusive**. To cover a line including its terminator, use `end = {line: nextLine, character: 0}`. [#range].
- The only EOL sequences are `\n`, `\r\n`, `\r`. Positions are line-ending agnostic: you cannot point at `\r|\n` or `\n|`. [#textDocuments].
- **3.17 changed the default character unit.** Before 3.17 offsets counted UTF-16 code units (`a𐐀b` → offsets 0, 1, 3). In 3.17 the client announces `general.positionEncodings: PositionEncodingKind[]` (decreasing preference; `utf-16` mandatory — if `utf-16` is absent the server may still assume UTF-16), and the server picks one and echoes it as `capabilities.positionEncoding`. If omitted, the encoding **defaults to `utf-16`**. Values: `'utf-8' | 'utf-16' | 'utf-32'`. [#textDocuments], [#positionEncodingKind], [#serverCapabilities], [#clientCapabilities].
  **Consequence:** all character offsets we emit/consume must be UTF-16 code-unit counts unless we negotiate otherwise. Python string indices are Unicode code points; they diverge from UTF-16 for non-BMP characters (emoji, some CJK).

### 1.3 Lifecycle

`initialize` → (result) → `initialized` → … requests/notifications … → `shutdown` (result `null`) → `exit`. [#lifeCycleMessages].

**`initialize`** [#initialize]:
- First request from client, **may only be sent once**. Before it is received: requests → error `-32002`; notifications → dropped **except `exit`** (so an uninitialized server can still be terminated).
- Until the server responds with `InitializeResult`, the client must send nothing else, and the server may send nothing to the client, except during `initialize` the notifications `window/showMessage`, `window/logMessage`, `telemetry/event` and the request `window/showMessageRequest`; a provided `workDoneToken` may be used with `$/progress`.
- Method: `initialize`. Params `InitializeParams` (extends `WorkDoneProgressParams`): **required** `processId: integer | null`, `rootUri: DocumentUri | null`, `capabilities: ClientCapabilities`; **optional** `clientInfo? {name, version?}`, `locale?`, `rootPath?` (deprecated), `initializationOptions?: LSPAny`, `trace?: TraceValue`, `workspaceFolders?: WorkspaceFolder[] | null`.
- Result `InitializeResult`: **required** `capabilities: ServerCapabilities`; **optional** `serverInfo? {name: string, version?: string}`.
- Relevant `ServerCapabilities` fields: `positionEncoding?`; `textDocumentSync?: TextDocumentSyncOptions | TextDocumentSyncKind` (default `None = 0`; the numeric form is the backwards-compatible shorthand); `completionProvider?: CompletionOptions {triggerCharacters?: string[], allCommitCharacters?, resolveProvider?, completionItem?: {labelDetailsSupport?}}`; `hoverProvider?: boolean | HoverOptions`; `definitionProvider?: boolean | DefinitionOptions`. Unknown capabilities must be ignored by clients, not cause failure. [#serverCapabilities].

**`initialized`** [#initialized]: notification, method `initialized`, `params: InitializedParams = {}` (empty). May only be sent once, after the `initialize` result and before any other message. No response.

**`shutdown`** [#shutdown]: request, method `shutdown`, **params: none**, **result: `null`**. The server must **not** exit yet. The client must send no further notifications except `exit` and no further requests; the server should reject any later request with `InvalidRequest` (`-32600`).

**`exit`** [#exit]: notification, method `exit`, **params: none**, no response. Exit with code **0 if `shutdown` was received, 1 otherwise**.

### 1.4 Document synchronization

- Support for `didOpen`/`didChange`/`didClose` is mandatory and a server **must implement all three or none**; `textDocumentSync` controls all of them together. [#textDocument_synchronization].
- `TextDocumentSyncKind`: `None = 0`, `Full = 1` (every change event carries the whole document), `Incremental = 2` (full text on open, then deltas). `TextDocumentSyncOptions {openClose?: boolean, change?: TextDocumentSyncKind, …}`. [#textDocumentSyncKind].

**`textDocument/didOpen`** [#textDocument_didOpen]: notification; params `DidOpenTextDocumentParams {textDocument: TextDocumentItem}`, where `TextDocumentItem` has **all required** fields `uri: DocumentUri`, `languageId: string`, `version: integer`, `text: string`. The client owns the content; the server must not read it from the URI. At most one open per URI (open/close must balance). A language-id change requires `didClose` + `didOpen`.

**`textDocument/didChange`** [#textDocument_didChange]: notification; params `DidChangeTextDocumentParams {textDocument: VersionedTextDocumentIdentifier /* uri + version */, contentChanges: TextDocumentContentChangeEvent[]}` — both fields required. Requires a preceding `didOpen`. Events are applied **in array order** (c1 takes S→S′, c2 takes S′→S″). Before any request, the client must have synchronized state. A content change event is either the incremental form `{range: Range, rangeLength?: uinteger /* deprecated */, text: string}` or the full form `{text: string}` (only `text` ⇒ whole document). [#textDocumentContentChangeEvent].

**`textDocument/didClose`** [#textDocument_didClose] and `didSave`/`willSave` exist; diagnostics ownership rules below make `didClose` the natural place to clear diagnostics for single-file languages.

### 1.5 Diagnostics (server→client)

**`textDocument/publishDiagnostics`** [#textDocument_publishDiagnostics]: notification; method as named; params `PublishDiagnosticsParams {uri: DocumentUri /* required */, version?: integer /* since 3.15 */, diagnostics: Diagnostic[] /* required */}`. Diagnostics are owned by the server: on each change it must recompute and **push the full new array**; an empty array **must** be pushed to clear; new diagnostics **replace**, never merge, previous ones.

`Diagnostic` [#diagnostic]: **required** `range: Range`, `message: string`; **optional but highly recommended** `severity`, plus `code?: integer | string`, `codeDescription?`, `source?: string`, `tags?: DiagnosticTag[]`, `relatedInformation?`, `data?`. `DiagnosticSeverity`: **1 = Error, 2 = Warning, 3 = Information, 4 = Hint**; if omitted clients should treat it as Error. `DiagnosticTag`: 1 = Unnecessary, 2 = Deprecated. `source` is a human-readable origin string (e.g. `'super lint'`).

### 1.6 Language features we implement

All three are **requests** and extend `TextDocumentPositionParams {textDocument: TextDocumentIdentifier /* {uri} */, position: Position}`; a `null` result means "no result" and does not tell the client to retry. [#textDocumentPositionParams], [#languageServerProtocol].

- **`textDocument/hover`** [#textDocument_hover]: params `HoverParams extends TextDocumentPositionParams, WorkDoneProgressParams`. Result `Hover | null`, where `Hover {contents: MarkedString | MarkedString[] | MarkupContent, range?: Range}`. `MarkupContent {kind: 'plaintext' | 'markdown', value: string}`; `MarkedString = string | {language, value}` is deprecated. The hover position is typically immediately to the **left** of the hovered character (offset `n` for character at `n`).
- **`textDocument/definition`** [#textDocument_definition]: params `DefinitionParams extends TextDocumentPositionParams, WorkDoneProgressParams, PartialResultParams`. Result `Location | Location[] | LocationLink[] | null`; `Location {uri: DocumentUri, range: Range}`; `LocationLink` requires `targetUri`, `targetRange`, `targetSelectionRange` plus optional `originSelectionRange` and is returned only when the client sets `textDocument.definition.linkSupport`. Server capability `definitionProvider: boolean | DefinitionOptions`.
- **`textDocument/completion`** [#textDocument_completion]: params `CompletionParams extends TextDocumentPositionParams, WorkDoneProgressParams, PartialResultParams` plus optional `context?: CompletionContext`. Result `CompletionItem[] | CompletionList | null`; an array means "complete" (identical to `{isIncomplete: false, items}`). `CompletionItem` has **required `label: string`**; everything else (`kind`, `detail`, `documentation`, `sortText`, `filterText`, `insertText`, `textEdit`, …) is optional. `CompletionList {isIncomplete: boolean, itemDefaults? /* 3.17 */}`. Client normally does filtering/sorting; returning a complete list is legal. `completionProvider.triggerCharacters` are extra characters beyond the client's defaults.

### 1.7 Request/notification semantics summary

| Message | Direction | Kind | `params` | Result on success |
|---|---|---|---|---|
| `initialize` | C→S | request | `InitializeParams` (3 required fields) | `InitializeResult` |
| `initialized` | C→S | notification | `{}` | — (no response) |
| `shutdown` | C→S | request | none | `null` |
| `exit` | C→S | notification | none | — (then process exits 0/1) |
| `textDocument/didOpen` | C→S | notification | `DidOpenTextDocumentParams` | — |
| `textDocument/didChange` | C→S | notification | `DidChangeTextDocumentParams` | — |
| `textDocument/publishDiagnostics` | S→C | notification | `PublishDiagnosticsParams` | — |
| `textDocument/completion` | C→S | request | `CompletionParams` | `CompletionItem[] \| CompletionList \| null` |
| `textDocument/hover` | C→S | request | `HoverParams` | `Hover \| null` |
| `textDocument/definition` | C→S | request | `DefinitionParams` | `Location \| Location[] \| LocationLink[] \| null` |

---

## 2. Conformance checklist: implemented code vs spec

Statuses: **C** = conformant, **P** = partial, **M** = missing. "Fix" is concrete and should be read as a change request, not as work done.

| # | Method / aspect | Status | Evidence in `lsp.py` | Gap vs spec | Concrete fix |
|---|---|---|---|---|---|
| 1 | `initialize` | **P** | `lsp.py:75-77` returns correct `{"capabilities": {...}}` inside a valid response; capabilities at `lsp.py:122-128` are legal shapes (`textDocumentSync: 1`, `hoverProvider: true`, `definitionProvider: true`, `completionProvider.triggerCharacters: []`) | Ignores all `InitializeParams` (`processId`, `rootUri`, `capabilities`); no single-use guard; no `serverInfo`; no `positionEncoding`; sets `initialized = True` at `lsp.py:76` *before* replying, so the pre-init window rule is inverted | Validate required params (return `-32602` if missing); reject a 2nd `initialize` with `-32600`; toggle state only in `serve()` after the response is written; echo `positionEncoding: 'utf-16'`; consider `serverInfo` |
| 2 | `initialized` | **C** | `lsp.py:78-79` returns `None` → no response, correct for a notification; params `{}` per spec | None beyond not enforcing "may only be sent once" (covered by item 13) | — |
| 3 | `shutdown` | **P** | `lsp.py:80-82` returns `{"result": None}` and records the flag | Does **not** reject requests received after shutdown with `InvalidRequest` (`-32600`); later `completion`/`hover` etc. still execute | At top of `handle_message`, if `self.shutdown_received and method != "exit"`: return error `-32600` (or drop non-`exit` notifications) |
| 4 | `exit` | **P** | `lsp.py:83-84` returns `None` (correct notification semantics); `test_lsp.py:83-89` asserts only that | The process does **not** exit. `serve()` (`lsp.py:316-318`) treats `None` as "continue reading", so the server hangs until stdin EOF; required exit code 0/1 is never produced | Handle `exit` in `serve()` (not just `handle_message`): break the loop and `sys.exit(0 if self.shutdown_received else 1)` |
| 5 | `textDocument/didOpen` | **P** | `lsp.py:86-90` stores `uri → text`; diagnostics published in valid shape | Reads only `uri` and `text`; discards required `languageId` and `version`; no balance/duplicate check; no validation of `TextDocumentItem` | Store `{uri: {text, version, languageId}}`; validate the 4 required fields; on `didClose` delete and publish `diagnostics: []` |
| 6 | `textDocument/didChange` | **P** | `lsp.py:92-99`; with advertised `Full` sync, `changes[-1]["text"]` is the whole document, so last-wins is acceptable | Ignores `textDocument.version` (required), ignores all but the last change event (no in-order application), no `didOpen` precondition, publishes diagnostics even when `contentChanges` is empty; if a client sends incremental events (range+text) they are silently misread as full text | Require prior `didOpen`; track and validate `version`; apply events in order; either implement both content-change variants or keep `Full` and explicitly reject ranged events; only republish on an actual change |
| 7 | `textDocument/publishDiagnostics` | **C** | `lsp.py:185-210`; notification with no `id`, `params {uri, diagnostics}`; `Diagnostic` has `range`, `severity`, `message`, `source` (`lsp.py:219-226`); `_SEVERITY` map `1..4` (`lsp.py:31`) is exactly the spec enum; empty findings push an empty array (`lsp.py:186, 197-210`) clears correctly | `version` omitted (optional so legal) | — |
| 8 | `textDocument/completion` | **P** | `lsp.py:231-242` returns `CompletionItem[]` with required `label`; legal result type; `test_lsp.py:149-165` pins it | Ignores `params.position` and `params.context` entirely — always returns the same global list; no `CompletionList`/`isIncomplete`; no `kind`/`textEdit`; no `completionItem/resolve` (advertised `resolveProvider` absent, so no lie) | Filter by the word under `position` (reuse `_token_at`); pass through `context.triggerKind`; return a `CompletionList` with `isIncomplete: false` if you want explicit incompleteness semantics |
| 9 | `textDocument/hover` | **P** | `lsp.py:244-247` returns `Hover {contents: MarkupContent{kind:'markdown', value}}`, a legal `Hover` | Returns an **empty-string** Hover instead of `null` when there is no token (`lsp.py:246`); no optional `range`; `_token_at` uses `match.start() <= char <= match.end()` (`lsp.py:155`) with an **inclusive** end, so the position just after a word wrongly hits it, while the spec says the hover position is the point immediately left of the character | Return `None` → `result: null` when no token; use `match.start() <= char < match.end()`; add `range` from `_range` when available |
| 10 | `textDocument/definition` | **P** | `lsp.py:249-264` returns a single `Location {uri, range}` or `null` — both legal result alternatives; the 1-based→0-based conversion (`pos.line - 1`, `pos.column - 1`, e.g. `lsp.py:171-180, 193-200`) is correct because the lexer emits 1-based `SourcePos` (`lexer.py:24-28`) | `_name_range` (`lsp.py:166-180`) **guesses** the location by regex search over the next 6 lines from the definition's `SourcePos`; it can return the wrong occurrence (aliases, repeated names, same name in body), and falls back to a fabricated position when no match is found. No `LocationLink` even if client supports `linkSupport` | Record the exact byte/char span of the defining identifier in the AST (or search from the token that produced the `FunctionDef`/`Set` node) and return that range; only synthesize `LocationLink` when `linkSupport` is announced |
| 11 | Base protocol framing (`#headerPart`, `#contentPart`) | **C** | `lsp.py:274-328`: parses ASCII headers case-insensitively, honors `Content-Length` in **bytes** (`len(raw)` at `lsp.py:319-321`), writes `\r\n\r\n` separators, decodes UTF-8 | Missing/negative `Content-Length` is silently skipped rather than answered with `-32700`/`-32600`; `Content-Type` other than UTF-8 is ignored rather than errored (spec says "should respond with an error") | Return a JSON-RPC error response for malformed headers/content type |
| 12 | Positions, ranges, EOL, encoding (`#position`, `#range`, `#textDocuments`) | **P** | Zero-based output in `_range` (`lsp.py:159-164`); 1-based parser positions converted correctly; full-sync text from didOpen/didChange | Offsets are **Python code-point indices**, not UTF-16 code units — non-BMP characters shift every later column (`_token_at` `lsp.py:146-157`, `_name_range` `lsp.py:166-180`, `_token_length` `lsp.py:212-217`, diagnostics `lsp.py:192-205`). `_lines` uses `str.splitlines()` (`lsp.py:137`), which splits on many more boundaries than the spec's `\n`, `\r\n`, `\r` (e.g. `\v`, `\x1c`, U+2028), corrupting line numbers. No `positionEncoding` negotiation; out-of-range `character` is not clamped to line length per spec | Split with `re.split(r'\r\n|\r|\n', text)`; add `utf16_offset`/`utf16_to_py` helpers for every column; advertise `positionEncoding: 'utf-16'` and validate/negotiate `general.positionEncodings`; clamp `character` to `len(line)` |
| 13 | Lifecycle state machine (`#initialize`, `#shutdown`) | **M** | Single booleans `initialized`, `shutdown_received` (`lsp.py:52-54`), no transition checks | Requests/notifications before `initialize` are **not** rejected with `-32002` (they are processed); a second `initialize` is accepted; `initialized` twice is accepted; messages after `shutdown` are accepted | Add an explicit state enum (`INITIAL → INITIALIZED → SHUTDOWN → EXITED`); gate dispatch on it; implement the `-32002` / `-32600` rules |
| 14 | `textDocument/didClose` + diagnostics clearing (#textDocument_synchronization) | **M** | No handler; no URI removal anywhere | Spec requires all of didOpen/didChange/didClose or none; server advertises `textDocumentSync: 1` but cannot honor `didClose`, and stale diagnostics are never cleared on close | Add `didClose` handler: drop `documents[uri]` and emit `publishDiagnostics` with `diagnostics: []` |
| 15 | `positionEncoding` negotiation (`#serverCapabilities`, `#positionEncodingKind`) | **M** | `lsp.py:122-128` omits it | 3.17 capability is absent; relying on the implicit `utf-16` default while computing code-point offsets is a concrete mismatch for non-BMP text | Read `capabilities.general.positionEncodings`, pick `utf-16` (or `utf-8` if we implement code-point/byte math), return it, and implement conversion accordingly |
| 16 | JSON-RPC error handling (`#errorCodes`, `#responseMessage`) | **M** | Malformed JSON is silently ignored (`lsp.py:311-314`); `params` missing fields default to `{}`/`""` (`lsp.py:71-73, 87-95, 266-269`); unknown requests use `-32601` correctly (`lsp.py:108-115`) | No `ParseError -32700`, no `InvalidRequest -32600`, no `InvalidParams -32602`, no `InternalError -32603`; exceptions in feature handlers would crash the server instead of producing an error response | Add a top-level `try/except` producing proper error responses; validate params per method before dispatch |

**Totals: 3 conformant (2, 7, 11) · 9 partial (1, 3, 4, 5, 6, 8, 9, 10, 12) · 4 missing (13, 14, 15, 16).**

Note on tests: `test_lsp.py` calls `handle_message` in-process (`test_lsp.py:1-4, 42-60`) and therefore **cannot** detect the transport-level and lifecycle gaps (items 4, 11, 13, 16). Its assertions also *pin* two non-conformant behaviors as "expected": the empty-string hover (`test_lsp.py:182-190`) and the always-global completion list (`test_lsp.py:149-165`). Those tests must be updated when fixing items 8/9.

---

## 3. Oracle / verification plan

The spec defines no official certification suite. Use three layered oracles; run them in this order. [#metaModel] (the spec's normative type model) is the ultimate reference for every assertion.

### 3.1 Layer A — refine the unit suite (fastest, already wired)

```
cd "D:\natural language code"
python -m unittest discover -s tests -v
```

Add table-driven cases to `tests/test_lsp.py` that assert the *shape invariants* of §1 rather than current outputs: every response has exactly one of `result`/`error`; `result: null` for `shutdown`; every notification reply has no `id`; `DiagnosticSeverity ∈ {1,2,3,4}`; every `Position.{line,character}` is a non-negative integer; `Range.end >= Range.start`. This catches items 7–10 regressions without a client.

### 3.2 Layer B — stdlib-only JSON-RPC oracle harness (recommended; no dependencies)

This is the executable oracle `docs/METHOD.md:42-66` asks for. Create `tools/lsp_oracle.py` (proposed, not part of this research deliverable):

```python
import json, os, subprocess, sys

def frame(obj):
    body = json.dumps(obj).encode("utf-8")
    return b"Content-Length: %d\r\n\r\n" % len(body) + body

def read(stream):
    headers = {}
    while True:
        line = stream.readline()
        if line in (b"\r\n", b"\n", b""):
            break
        k, _, v = line.decode("ascii").partition(":")
        headers[k.strip().lower()] = v.strip()
    return json.loads(stream.read(int(headers["content-length"])).decode("utf-8"))

env = dict(os.environ, PYTHONPATH=os.path.join(os.getcwd(), "src"),
           PYTHONIOENCODING="utf-8")
p = subprocess.Popen([sys.executable, "-m", "llang.lsp"],
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)

def send(obj):
    p.stdin.write(frame(obj)); p.stdin.flush()

send({"jsonrpc":"2.0","id":1,"method":"initialize",
      "params":{"processId":None,"rootUri":None,"capabilities":{
          "general":{"positionEncodings":["utf-16"]}},"clientInfo":{"name":"oracle"}}})
init = read(p.stdout)
assert set(init) == {"jsonrpc","id","result"} and init["result"]["capabilities"]

send({"jsonrpc":"2.0","method":"initialized","params":{}})
send({"jsonrpc":"2.0","method":"textDocument/didOpen","params":{"textDocument":{
      "uri":"file:///t.ll","languageId":"llang","version":1,
      "text":"set greeting to \"Hi\"\nshow greeting\n"}}})
diag = read(p.stdout)
assert diag["method"] == "textDocument/publishDiagnostics" and "id" not in diag
assert diag["params"]["uri"] == "file:///t.ll"

send({"jsonrpc":"2.0","id":2,"method":"textDocument/hover","params":{
      "textDocument":{"uri":"file:///t.ll"},"position":{"line":1,"character":5}}})
h = read(p.stdout)["result"]
assert h is None or (set(h) <= {"contents","range"} and "kind" in h["contents"])

send({"jsonrpc":"2.0","id":3,"method":"shutdown","params":None})
assert read(p.stdout)["result"] is None
send({"jsonrpc":"2.0","method":"exit","params":None})
print("exit code:", p.wait(timeout=5))   # expect 0; current server TIMES OUT -> item 4
```

Run:

```
cd "D:\natural language code"
python tools/lsp_oracle.py
```

The `p.wait(timeout=5)` is the mechanical proof of item 4; a fixed server returns `0`. Add negative cases: send `textDocument/hover` as the **first** message and assert `-32002` (item 13), send a second `initialize` and assert failure, send a request after `shutdown` and assert `-32600`, send an unframed body and assert `-32700` instead of silence.

### 3.3 Layer C — reference client stack (cross-check framing/capabilities against a real LSP implementation)

Microsoft's official 3.17 node implementation is linked from the spec itself (<https://github.com/Microsoft/vscode-languageserver-node>); use it, not a blog, as the behavioural oracle. A pure Node client needs no VS Code process:

```
cd "D:\natural language code"
npm init -y
npm i vscode-jsonrpc
node tools/lsp_oracle.mjs
```

```js
// tools/lsp_oracle.mjs (proposed)
import { createMessageConnection, StreamMessageReader, StreamMessageWriter }
  from 'vscode-jsonrpc/node.js';
import { spawn } from 'node:child_process';

const child = spawn(process.execPath, ['-m', 'llang.lsp'], {
  cwd: process.cwd(), env: { ...process.env, PYTHONPATH: 'src' } });
const conn = createMessageConnection(new StreamMessageReader(child.stdout),
                                     new StreamMessageWriter(child.stdin));
conn.onNotification('textDocument/publishDiagnostics', p =>
  console.log('DIAG', p.uri, p.diagnostics.length));
conn.onError(e => console.error('PROTOCOL ERROR', e));
conn.listen();

const init = await conn.sendRequest('initialize', {
  processId: null, rootUri: null, capabilities: {} });
console.log('CAPS', JSON.stringify(init.capabilities));
conn.sendNotification('initialized', {});
conn.sendNotification('textDocument/didOpen', { textDocument: {
  uri: 'file:///t.ll', languageId: 'llang', version: 1, text: 'show missing\n' }});
console.log('HOVER', await conn.sendRequest('textDocument/hover', {
  textDocument: { uri: 'file:///t.ll' }, position: { line: 0, character: 5 }}));
await conn.sendRequest('shutdown', null);
conn.sendNotification('exit', null);
```

`vscode-jsonrpc`'s `StreamMessageReader` is strict about `Content-Length` and JSON-RPC 2.0, so any framing/response-shape defect (items 11, 16) surfaces as `PROTOCOL ERROR`. For an editor-level check, the same server can be wired to `vscode-languageclient` (`npm i vscode-languageclient`) in a small extension host.

### 3.4 Layer D — schema validation against the spec's type model

Generate JSON Schemas from the normative TypeScript interfaces in §1 (`RequestMessage`, `ResponseMessage`, `InitializeParams/Result`, `ServerCapabilities`, `DidOpenTextDocumentParams`, `DidChangeTextDocumentParams`, `PublishDiagnosticsParams`, `Diagnostic`, `Hover`, `Location`, `CompletionItem/List`), remembering that the spec uses **strict mode**: a non-optional property must be listed even when falsy. Validate every captured message with `ajv`:

```
npm i ajv
node tools/validate_against_lsp_schema.mjs
```

A cheaper spec-only variant: grep the captured JSON for the exact invariants of §1 (`"jsonrpc":"2.0"`, no `id` on notifications, `result` and `error` mutually exclusive, severity ∈ 1..4, non-negative integers for line/character). The schema layer mainly guards against *silent* shape drift as we add features.

---

## 4. LSP features deliberately not implemented (and why)

Design principle: this is a **tiny, stdlib-only, single-file server** whose purpose is to validate llang semantics, not to be a full IDE backend. Everything below is intentionally out of scope. Items 14–16 in §2 are *not* in this list — those are unintentional gaps against methods we do implement.

| Not implemented | Why |
|---|---|
| `textDocument/didSave`, `willSave`, `willSaveWaitUntil`, `didRename` | llang has no on-disk build step; syncing in-memory buffers is sufficient |
| Incremental sync (`TextDocumentSyncKind.Incremental`) and ranged `TextDocumentContentChangeEvent` | Full sync is simpler and O(n) text size is tiny; we advertise `1` honestly |
| Pull diagnostics (`textDocument/diagnostic`, `workspace/diagnostic`) | Push diagnostics on didOpen/didChange cover the single-file use case; 3.17 pull model needs client capability negotiation and workspace state |
| `textDocument/codeAction`, `codeAction/resolve` | Would require representing linter fixes as `WorkspaceEdit`s; linter currently only produces messages |
| `textDocument/formatting`, `rangeFormatting`, `onTypeFormatting`, `documentFormatting` | The canonical formatter is a separate CLI (`llang` formatter); wiring it through LSP edits is future work |
| `textDocument/references`, `documentHighlight`, `rename`, `prepareRename`, `linkedEditingRange` | Need a real symbol table / index; current AST walk is single-document and heuristic |
| `textDocument/documentSymbol`, `semanticTokens`, `foldingRange`, `selectionRange`, `codeLens`, `inlayHint`, `inlineValue`, `documentLink`, `moniker`, `typeHierarchy`, `callHierarchy` | Presentation-layer enrichment; no llang client consumes them yet |
| `textDocument/signatureHelp`, `completionItem/resolve`, snippet/`textEdit` completions | Completion items are plain labels; no expensive metadata to defer, no signature model in AST |
| `textDocument/declaration`, `typeDefinition`, `implementation` | llang is dynamically typed with no separate declaration/implementation concept; `definition` covers the useful case |
| Workspace features (`workspace/symbol`, folders, file operations, configuration, executeCommand, applyEdit) | Single document per URI, no workspace model, no write capability in the server |
| Window/trace/progress (`window/showMessage`, `logMessage`, `showDocument`, `$/progress`, `setTrace`) | No UI channel; diagnostics are the only server→client messages used |
| Dynamic capability registration (`client/registerCapability`, `unregisterCapability`) | Capabilities are static and advertised in `initialize`; simpler and sufficient |
| `$/cancelRequest`, stale-request support, partial results | Requests are short and synchronous; single-threaded stdlib loop cannot react to cancellation mid-request (spec explicitly permits ignoring `$/` notifications in such servers) |
| 3.17 position-encoding negotiation beyond the implicit UTF-16 default | Deliberate *temporary* simplification — but see items 12/15: because our offsets are actually code points, this must be fixed rather than left implicit for non-ASCII input |
| Notebook document synchronization (3.17) | llang has no notebook surface |
| Multi-root / multiple document ownership, content ownership checks | One server, one buffer set; URI-keyed dict is the whole model |

**Bottom line:** the wire shapes we do emit are largely legal (3 conformant rows), but lifecycle enforcement (items 1, 3, 4, 13), the mandated `didClose` trio (item 14), and the UTF-16/offset semantics (items 12, 15) are where a real client would first reject us. Fix those before adding any new feature.

## Implementation status (post-audit)

The audit gaps above were addressed in `src/llang/lsp.py`:

- **Lifecycle:** explicit state machine `init → initialized → running → shutdown → exited`; second `initialize` returns `-32600`; feature requests before initialization return `-32002`.
- **`exit`:** sets the exited state and terminates the stdio serve loop.
- **`didClose`:** removes the document and publishes empty diagnostics, as the spec requires.
- **JSON-RPC errors:** `-32700` for malformed JSON in the transport, `-32603` for handler exceptions, plus the earlier `-32601` and `-32602` paths.
- **UTF-16 offsets:** positions are converted between LSP code units and Python string indices, including surrogate pairs for non-BMP characters.

`tests/test_lsp.py` now has 19 tests, including conformance cases for each fix. The checklist's status column describes the pre-fix snapshot; the items above are the applied changes.
