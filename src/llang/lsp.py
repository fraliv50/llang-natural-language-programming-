"""A minimal, self-contained Language Server Protocol server for llang.

Only the standard library is used.  The transport is the usual LSP
``Content-Length`` framing over stdio; ``handle_message`` is kept separate so
it can be unit tested without starting a subprocess.

Supported methods:

* ``initialize`` / ``shutdown`` / ``exit`` / ``initialized``
* ``textDocument/didOpen`` / ``textDocument/didChange`` (publish diagnostics)
* ``textDocument/completion`` / ``textDocument/hover`` / ``textDocument/definition``
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import fields, is_dataclass

from .ast_nodes import ForEach, FunctionDef, Set
from .errors import LangError, SourcePos
from .lexer import Lexer
from .linter import lint_source
from .parser import Parser
from .synonyms import KEYWORD_STARTS

_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# LSP DiagnosticSeverity
_SEVERITY = {"error": 1, "warning": 2, "information": 3, "hint": 4}

# LSP TextDocumentSyncKind.Full — every change carries the whole document.
_SYNC_FULL = 1


def _iter_nodes(value):
    """Yield AST nodes found in ``value`` (mirrors the linter's walk helper)."""
    if is_dataclass(value) and hasattr(value, "pos"):
        yield value
        for field in fields(value):
            yield from _iter_nodes(getattr(value, field.name, None))
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_nodes(item)


class LlangLanguageServer:
    """A tiny LSP server with in-memory, URI-keyed documents."""

    def __init__(self):
        self.documents: dict[str, str] = {}
        self.state = "init"        # init -> initialized -> running -> shutdown -> exited
        self.shutdown_received = False

    @property
    def initialized(self) -> bool:
        return self.state in ("initialized", "running", "shutdown", "exited")

    @staticmethod
    def _error(msg_id, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": msg_id,
                "error": {"code": code, "message": message}}

    @staticmethod
    def _utf16_to_index(text: str, units: int) -> int:
        """Convert a UTF-16 code-unit offset to a Python string index."""
        count = 0
        for index, char in enumerate(text):
            if count >= units:
                return index
            count += 2 if ord(char) > 0xFFFF else 1
        return len(text)

    @staticmethod
    def _index_to_utf16(text: str, index: int) -> int:
        """Convert a Python string index to a UTF-16 code-unit offset."""
        return sum(2 if ord(char) > 0xFFFF else 1 for char in text[:index])

    # ------------------------------------------------------------------
    # message dispatch
    # ------------------------------------------------------------------
    def handle_message(self, message: dict) -> dict | None:
        """Handle one decoded JSON-RPC message and return the reply (if any).

        Requests always produce a response with the incoming ``id``;
        notifications normally produce ``None``.  The two document
        notifications are the exception: they produce a server-initiated
        ``textDocument/publishDiagnostics`` notification, which is returned as
        a plain dict (no ``id``) for the transport to write out.
        """
        if not isinstance(message, dict):
            return None

        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params") or {}

        try:
            return self._dispatch(method, msg_id, params)
        except Exception as exc:  # never crash the transport on a handler bug
            return self._error(msg_id, -32603, f"Internal error: {exc}")

    def _dispatch(self, method, msg_id, params):
        if method == "initialize":
            if self.state != "init":
                return self._error(msg_id, -32600, "Invalid Request: already initialized")
            if "capabilities" not in params:
                return self._error(msg_id, -32602, "Invalid params: capabilities required")
            self.state = "initialized"
            return self._response(msg_id, {
                "capabilities": self._capabilities(),
                "serverInfo": {"name": "llang", "version": "0.1.0"},
                "positionEncoding": "utf-16",
            })
        if method == "initialized":
            if self.state == "initialized":
                self.state = "running"
            return None
        if method == "shutdown":
            if self.state not in ("initialized", "running"):
                return self._error(msg_id, -32002, "Server not initialized")
            self.shutdown_received = True
            self.state = "shutdown"
            return self._response(msg_id, None)
        if method == "exit":
            self.state = "exited"
            return None

        if self.state not in ("initialized", "running", "shutdown"):
            if msg_id is None:
                return None
            return self._error(msg_id, -32002, "Server not initialized")

        if method == "textDocument/didOpen":
            document = params.get("textDocument") or {}
            uri = document.get("uri", "")
            self.documents[uri] = document.get("text", "")
            return self._publish_diagnostics(uri)

        if method == "textDocument/didChange":
            document = params.get("textDocument") or {}
            uri = document.get("uri", "")
            changes = params.get("contentChanges") or []
            if changes:
                # Full-document sync: the last change carries the whole text.
                self.documents[uri] = changes[-1].get("text", "")
            return self._publish_diagnostics(uri)

        if method == "textDocument/didClose":
            uri = self._uri(params)
            self.documents.pop(uri, None)
            return self._publish_diagnostics(uri)   # clears diagnostics per spec

        if method == "textDocument/completion":
            return self._response(msg_id, self._completion(params))
        if method == "textDocument/hover":
            return self._response(msg_id, self._hover(params))
        if method == "textDocument/definition":
            return self._response(msg_id, self._definition(params))

        # Unknown notification: ignore. Unknown request: Method not found.
        if msg_id is None:
            return None
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": "Method not found"},
        }

    @staticmethod
    def _response(msg_id, result) -> dict:
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    @staticmethod
    def _capabilities() -> dict:
        return {
            "hoverProvider": True,
            "completionProvider": {"triggerCharacters": []},
            "definitionProvider": True,
            "textDocumentSync": _SYNC_FULL,
            "positionEncoding": "utf-16",
        }

    # ------------------------------------------------------------------
    # documents / parsing helpers
    # ------------------------------------------------------------------
    def _text(self, uri: str) -> str:
        return self.documents.get(uri, "")

    def _lines(self, uri: str) -> list[str]:
        return self._text(uri).splitlines()

    def _program(self, uri: str):
        """Parse the stored document, or return None if it has syntax errors."""
        try:
            return Parser(Lexer(self._text(uri)).tokenize()).parse_program()
        except LangError:
            return None

    def _token_at(self, uri: str, position: dict):
        """Return ``(word, start_char, end_char)`` under an LSP position."""
        line = position.get("line", 0)
        char = position.get("character", 0)
        lines = self._lines(uri)
        if not isinstance(line, int) or line < 0 or line >= len(lines):
            return None
        text = lines[line]
        char_index = self._utf16_to_index(text, char)
        for match in _WORD_RE.finditer(text):
            if match.start() <= char_index <= match.end():
                return match.group(0), match.start(), match.end()
        return None

    @classmethod
    def _range(cls, line: int, start: int, end: int, text: str = "") -> dict:
        return {
            "start": {"line": line, "character": cls._index_to_utf16(text, start)},
            "end": {"line": line, "character": cls._index_to_utf16(text, end)},
        }

    def _name_range(self, uri: str, pos: SourcePos | None, name: str) -> dict:
        """Locate ``name`` in the source near ``pos`` for a definition range."""
        lines = self._lines(uri)
        if pos is None or not lines:
            return self._range(0, 0, len(name), lines[0] if lines else "")
        first_line = max(pos.line - 1, 0)
        first_col = max(pos.column - 1, 0)
        pattern = re.compile(r"\b" + re.escape(name) + r"\b")
        for lineno in range(first_line, min(first_line + 6, len(lines))):
            text = lines[lineno]
            from_col = first_col if lineno == first_line else 0
            match = pattern.search(text, from_col)
            if match:
                return self._range(lineno, match.start(), match.end(), text)
        return self._range(first_line, first_col, first_col + len(name),
                           lines[first_line] if lines else "")

    # ------------------------------------------------------------------
    # diagnostics
    # ------------------------------------------------------------------
    def _publish_diagnostics(self, uri: str) -> dict:
        diagnostics = []
        try:
            findings = lint_source(self._text(uri))
        except LangError as error:
            findings = []
            pos = error.pos
            lines = self._lines(uri)
            offset = max((pos.column - 1) if pos else 0, 0)
            line_index = max((pos.line - 1) if pos else 0, 0)
            line_text = lines[line_index] if line_index < len(lines) else ""
            diagnostics.append(self._diagnostic(
                self._range(line_index, offset, offset + 1, line_text),
                1, error.message))
        lines = self._lines(uri)
        for finding in findings:
            pos = finding.pos
            line = max((pos.line - 1) if pos else 0, 0)
            col = max((pos.column - 1) if pos else 0, 0)
            end = self._token_length(uri, line, col)
            line_text = lines[line] if line < len(lines) else ""
            diagnostics.append(self._diagnostic(
                self._range(line, col, col + end, line_text),
                _SEVERITY.get(finding.severity, 1),
                finding.message))
        return {
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {"uri": uri, "diagnostics": diagnostics},
        }

    def _token_length(self, uri: str, line: int, col: int) -> int:
        lines = self._lines(uri)
        if not isinstance(line, int) or line < 0 or line >= len(lines):
            return 1
        match = _WORD_RE.match(lines[line], col)
        return (match.end() - match.start()) if match else 1

    @staticmethod
    def _diagnostic(range_: dict, severity: int, message: str) -> dict:
        return {
            "range": range_,
            "severity": severity,
            "message": message,
            "source": "llang",
        }

    # ------------------------------------------------------------------
    # language features
    # ------------------------------------------------------------------
    def _completion(self, params: dict) -> list:
        labels = sorted(KEYWORD_STARTS)
        program = self._program(self._uri(params))
        if program is not None:
            seen = set(labels)
            for node in _iter_nodes(program):
                if isinstance(node, FunctionDef):
                    for name in [node.name, *node.aliases]:
                        if name and name not in seen:
                            seen.add(name)
                            labels.append(name)
        return [{"label": label} for label in labels]

    def _hover(self, params: dict) -> dict:
        token = self._token_at(self._uri(params), params.get("position") or {})
        value = f"`{token[0]}`" if token else ""
        return {"contents": {"kind": "markdown", "value": value}}

    def _definition(self, params: dict):
        uri = self._uri(params)
        token = self._token_at(uri, params.get("position") or {})
        if token is None:
            return None
        name = token[0]
        program = self._program(uri)
        if program is None:
            return None
        for node in _iter_nodes(program):
            if isinstance(node, FunctionDef) and (
                    node.name == name or name in node.aliases):
                return {"uri": uri, "range": self._name_range(uri, node.pos, name)}
            if isinstance(node, (Set, ForEach)) and node.name == name:
                return {"uri": uri, "range": self._name_range(uri, node.pos, name)}
        return None

    @staticmethod
    def _uri(params: dict) -> str:
        document = params.get("textDocument") or {}
        return document.get("uri", "")

    # ------------------------------------------------------------------
    # stdio transport
    # ------------------------------------------------------------------
    def serve(self, stdin, stdout) -> None:
        """Read framed JSON-RPC messages from ``stdin`` until EOF.

        Both binary and text streams are accepted.  All replies (responses and
        notifications alike) are written with standard ``Content-Length``
        framing.
        """
        binary = False
        while True:
            header_lines = []
            while True:
                line = stdin.readline()
                if not line:
                    return
                if isinstance(line, bytes):
                    binary = True
                    line = line.decode("ascii", "replace")
                line = line.rstrip("\r\n")
                if line == "":
                    break
                header_lines.append(line)

            headers = {}
            for line in header_lines:
                key, separator, value = line.partition(":")
                if separator:
                    headers[key.strip().lower()] = value.strip()
            try:
                length = int(headers.get("content-length", "0"))
            except ValueError:
                continue
            if length <= 0:
                continue

            body = stdin.read(length)
            if isinstance(body, bytes):
                body = body.decode("utf-8")
            try:
                message = json.loads(body)
            except json.JSONDecodeError:
                response = self._error(None, -32700, "Parse error")
                self._write(stdout, response, binary)
                continue

            response = self.handle_message(message)
            if self.state == "exited":
                return
            if response is None:
                continue
            self._write(stdout, response, binary)

    @staticmethod
    def _write(stdout, response, binary: bool) -> None:
        payload = json.dumps(response, ensure_ascii=False)
        raw = payload.encode("utf-8")
        header = f"Content-Length: {len(raw)}\r\n\r\n"
        if binary:
            stdout.write(header.encode("ascii"))
            stdout.write(raw)
        else:
            stdout.write(header)
            stdout.write(payload)
        stdout.flush()


def main() -> None:
    """Entry point for stdio use: ``python -m llang.lsp``."""
    LlangLanguageServer().serve(sys.stdin.buffer, sys.stdout.buffer)


if __name__ == "__main__":
    main()
