"""Unit tests for the llang language server.

These call ``handle_message`` directly — no subprocess, no real stdio.  Run
with: python -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llang.lsp import LlangLanguageServer  # noqa: E402
from llang.synonyms import KEYWORD_STARTS  # noqa: E402


def _position(line, character):
    return {"line": line, "character": character}


def _location(uri, line, start, end):
    return {
        "uri": uri,
        "range": {"start": _position(line, start), "end": _position(line, end)},
    }


def _diagnostic(line, start, end, severity, message):
    return {
        "range": {"start": _position(line, start), "end": _position(line, end)},
        "severity": severity,
        "message": message,
        "source": "llang",
    }


class LspTests(unittest.TestCase):
    def setUp(self):
        self.server = LlangLanguageServer()
        self.uri = "file:///example.ll"

    def _start(self):
        if self.server.state == "init":
            self.server.handle_message({
                "jsonrpc": "2.0", "id": 0, "method": "initialize",
                "params": {"capabilities": {}},
            })
            self.server.handle_message({"jsonrpc": "2.0", "method": "initialized"})

    def _open(self, text, uri=None):
        self._start()
        return self.server.handle_message({
            "jsonrpc": "2.0",
            "method": "textDocument/didOpen",
            "params": {"textDocument": {
                "uri": uri or self.uri,
                "languageId": "llang",
                "version": 1,
                "text": text,
            }},
        })

    def _request(self, msg_id, method, params=None):
        if method != "initialize":
            self._start()
        return self.server.handle_message({
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
            "params": params if params is not None else {},
        })

    def test_lifecycle_rejects_early_requests(self):
        response = self.server.handle_message({
            "jsonrpc": "2.0", "id": 99, "method": "textDocument/completion",
            "params": {"textDocument": {"uri": self.uri}},
        })
        self.assertEqual(response["error"]["code"], -32002)

    def test_second_initialize_is_invalid_request(self):
        self._start()
        response = self._request(50, "initialize", {"capabilities": {}})
        self.assertEqual(response["error"]["code"], -32600)

    def test_exit_sets_exited_state(self):
        self._start()
        self.server.handle_message({"jsonrpc": "2.0", "method": "exit"})
        self.assertEqual(self.server.state, "exited")

    def test_did_close_clears_diagnostics(self):
        self._open('show missing\n')
        closed = self.server.handle_message({
            "jsonrpc": "2.0", "method": "textDocument/didClose",
            "params": {"textDocument": {"uri": self.uri}},
        })
        self.assertEqual(closed["params"]["diagnostics"], [])

    def test_utf16_offsets_for_non_bmp_characters(self):
        self._open('set message to "😀 hello"\nshow message\n')
        response = self._request(3, "textDocument/hover", {
            "textDocument": {"uri": self.uri},
            "position": {"line": 0, "character": 18},
        })
        self.assertIn("result", response)

    # ------------------------------------------------------------------
    # initialize / lifecycle
    # ------------------------------------------------------------------
    def test_initialize_returns_exact_capabilities(self):
        response = self._request(1, "initialize", {"processId": None, "capabilities": {}})
        self.assertEqual(response, {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "capabilities": {
                    "hoverProvider": True,
                    "completionProvider": {"triggerCharacters": []},
                    "definitionProvider": True,
                    "textDocumentSync": 1,
                    "positionEncoding": "utf-16",
                },
                "serverInfo": {"name": "llang", "version": "0.1.0"},
                "positionEncoding": "utf-16",
            },
        })

    def test_initialized_is_a_silent_notification(self):
        self.assertIsNone(self.server.handle_message({
            "jsonrpc": "2.0", "method": "initialized", "params": {},
        }))

    def test_shutdown_returns_null_result_and_exit_is_silent(self):
        self.assertEqual(self._request(9, "shutdown"), {
            "jsonrpc": "2.0", "id": 9, "result": None,
        })
        self.assertIsNone(self.server.handle_message({
            "jsonrpc": "2.0", "method": "exit", "params": None,
        }))

    def test_unknown_request_uses_method_not_found(self):
        self.assertEqual(self._request(7, "textDocument/formatting"), {
            "jsonrpc": "2.0",
            "id": 7,
            "error": {"code": -32601, "message": "Method not found"},
        })

    # ------------------------------------------------------------------
    # diagnostics
    # ------------------------------------------------------------------
    def test_did_open_publishes_diagnostics(self):
        response = self._open("show missing\ncall mystery with x = 1\n")
        self.assertEqual(response, {
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {
                "uri": self.uri,
                "diagnostics": [
                    _diagnostic(0, 5, 12, 1, "Undefined name 'missing'"),
                    _diagnostic(1, 0, 4, 1,
                                "Call to unknown function or builtin 'mystery'"),
                ],
            },
        })

    def test_did_change_publishes_diagnostics_with_warning_severity(self):
        self._open("show missing\n")
        response = self.server.handle_message({
            "jsonrpc": "2.0",
            "method": "textDocument/didChange",
            "params": {
                "textDocument": {"uri": self.uri, "version": 2},
                "contentChanges": [{"text": "require true\n"}],
            },
        })
        self.assertEqual(response, {
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {
                "uri": self.uri,
                "diagnostics": [
                    _diagnostic(0, 8, 12, 2,
                                "'require' condition is literal true"),
                ],
            },
        })
        # The new text is what subsequent requests see.
        self.assertEqual(self.server.documents[self.uri], "require true\n")

    def test_syntax_error_is_reported_as_a_diagnostic(self):
        response = self._open('show "unterminated\n')
        self.assertEqual(response["params"]["diagnostics"], [
            _diagnostic(0, 5, 6, 1, "Unterminated string literal"),
        ])

    # ------------------------------------------------------------------
    # completion / hover / definition
    # ------------------------------------------------------------------
    def test_completion_returns_keywords_plus_document_function_names(self):
        self._open(
            "define function greet taking name\n"
            "also known as say_hello\n"
            "    give back name\n"
            "end function\n"
        )
        response = self._request(2, "textDocument/completion", {
            "textDocument": {"uri": self.uri},
            "position": _position(0, 0),
        })
        expected_labels = sorted(KEYWORD_STARTS) + ["greet", "say_hello"]
        self.assertEqual(response, {
            "jsonrpc": "2.0",
            "id": 2,
            "result": [{"label": label} for label in expected_labels],
        })

    def test_hover_returns_token_as_markdown(self):
        self._open('set greeting to "Hello"\nshow greeting\n')
        response = self._request(3, "textDocument/hover", {
            "textDocument": {"uri": self.uri},
            "position": _position(1, 5),
        })
        self.assertEqual(response, {
            "jsonrpc": "2.0",
            "id": 3,
            "result": {"contents": {
                "kind": "markdown",
                "value": "`greeting`",
            }},
        })

    def test_hover_on_whitespace_returns_empty_markdown(self):
        self._open("show   42\n")
        response = self._request(4, "textDocument/hover", {
            "textDocument": {"uri": self.uri},
            "position": _position(0, 5),
        })
        self.assertEqual(response["result"], {
            "contents": {"kind": "markdown", "value": ""},
        })

    def test_definition_of_function_name(self):
        self._open(
            'define function greet taking name\n'
            '    give back name\n'
            'end function\n'
            'call greet with name = "Ada"\n'
        )
        response = self._request(5, "textDocument/definition", {
            "textDocument": {"uri": self.uri},
            "position": _position(3, 5),
        })
        self.assertEqual(response, {
            "jsonrpc": "2.0",
            "id": 5,
            "result": _location(self.uri, 0, 16, 21),
        })

    def test_definition_of_alias(self):
        self._open(
            'define function greet taking name\n'
            'also known as say_hello\n'
            '    give back name\n'
            'end function\n'
            'call say_hello with name = "Ada"\n'
        )
        response = self._request(6, "textDocument/definition", {
            "textDocument": {"uri": self.uri},
            "position": _position(4, 5),
        })
        self.assertEqual(response, {
            "jsonrpc": "2.0",
            "id": 6,
            "result": _location(self.uri, 1, 14, 23),
        })

    def test_definition_of_assignment(self):
        self._open('set greeting to "Hello"\nshow greeting\n')
        response = self._request(7, "textDocument/definition", {
            "textDocument": {"uri": self.uri},
            "position": _position(1, 5),
        })
        self.assertEqual(response, {
            "jsonrpc": "2.0",
            "id": 7,
            "result": _location(self.uri, 0, 4, 12),
        })

    def test_definition_of_unknown_token_is_null(self):
        self._open("show missing\n")
        response = self._request(8, "textDocument/definition", {
            "textDocument": {"uri": self.uri},
            "position": _position(0, 5),
        })
        self.assertEqual(response, {
            "jsonrpc": "2.0", "id": 8, "result": None,
        })


if __name__ == "__main__":
    unittest.main()
