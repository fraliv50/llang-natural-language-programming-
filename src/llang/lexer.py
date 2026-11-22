"""Tokenizer. Indentation is insignificant; newlines are statement terminators."""

from dataclasses import dataclass

from .errors import SourcePos, LangError
from .synonyms import RESERVED


@dataclass
class Token:
    kind: str          # WORD, NUMBER, STRING, PUNCT, NEWLINE, EOF
    text: str
    pos: SourcePos
    value: object = None

    def __repr__(self) -> str:
        return f"{self.kind}({self.text!r})@{self.pos.line}:{self.pos.column}"


class Lexer:
    def __init__(self, source: str):
        self.src = source
        self.i = 0
        self.line = 1
        self.col = 1

    def _pos(self) -> SourcePos:
        return SourcePos(self.line, self.col)

    def _peek(self) -> str:
        return self.src[self.i] if self.i < len(self.src) else ""

    def _advance(self) -> str:
        ch = self.src[self.i]
        self.i += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []
        while self.i < len(self.src):
            ch = self._peek()
            if ch in " \t\r\ufeff":
                self._advance()
            elif ch == "#":
                while self._peek() and self._peek() != "\n":
                    self._advance()
            elif ch == "\n":
                pos = self._pos()
                tokens.append(Token("NEWLINE", "\n", pos))
                self._advance()
            elif ch == '"':
                tokens.append(self._string())
            elif ch.isdigit():
                tokens.append(self._number())
            elif ch.isalpha() or ch == "_":
                tokens.append(self._word())
            elif ch in "(),=":
                pos = self._pos()
                text = self._advance()
                tokens.append(Token("PUNCT", text, pos))
            else:
                raise LangError(f"Unexpected character {ch!r}", self._pos())
        tokens.append(Token("EOF", "", self._pos()))
        return tokens

    def _word(self) -> Token:
        pos = self._pos()
        chars = []
        while self._peek().isalnum() or self._peek() == "_":
            chars.append(self._advance())
        text = "".join(chars)
        return Token("WORD", text, pos, text)

    @staticmethod
    def _ascii_digit(ch: str) -> bool:
        return "0" <= ch <= "9"

    def _number(self) -> Token:
        pos = self._pos()
        chars = []
        while self._ascii_digit(self._peek()):
            chars.append(self._advance())
        if (self._peek() == "." and self.i + 1 < len(self.src)
                and self._ascii_digit(self.src[self.i + 1])):
            chars.append(self._advance())
            while self._ascii_digit(self._peek()):
                chars.append(self._advance())
        text = "".join(chars)
        value = float(text) if "." in text else int(text)
        return Token("NUMBER", text, pos, value)

    def _string(self) -> Token:
        pos = self._pos()
        self._advance()  # opening quote
        chars = []
        escapes = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}
        while True:
            ch = self._peek()
            if not ch:
                raise LangError("Unterminated string literal", pos)
            if ch == '"':
                self._advance()
                return Token("STRING", "".join(chars), pos, "".join(chars))
            if ch == "\n":
                raise LangError("Unterminated string literal", pos)
            if ch == "\\":
                self._advance()
                nxt = self._peek()
                if not nxt:
                    raise LangError("Unterminated escape sequence", pos)
                ch = self._advance()
                chars.append(escapes.get(ch, ch))
            else:
                chars.append(self._advance())
