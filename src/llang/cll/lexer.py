"""Tokenizer for the closed c-ll vocabulary.

The grammar is regular at the token level: identifiers, decimal numbers,
double-quoted strings, the six punctuation glyphs ``( ) , = [ ]``, newlines
and comments.  Multi-word phrases (``pointer to T``, ``does not equal``, ...)
are matched by the parser from these tokens, exactly as in the English surface.

Unknown *characters* are rejected here; unknown *words* cannot hide new syntax
because every statement and operator starter belongs to the closed keyword set
below and all other words are ordinary identifiers.
"""

from dataclasses import dataclass

from ..errors import SourcePos, ParseError


# Every spelling that appears in the c-ll grammar.  None of these may be used
# as a variable, parameter, field, struct or function name.
RESERVED = frozenset({
    # types
    "int", "float", "void", "pointer", "to", "array", "of", "struct",
    # declarations / assignment / output
    "let", "as", "be", "set", "show",
    # arithmetic
    "plus", "minus", "times", "divided", "by", "remainder",
    # cast / logic / comparison
    "cast", "and", "or", "not", "equals", "equal", "does", "is", "less",
    "than", "at", "most", "greater", "least",
    # addresses / members / index / null
    "address", "value", "item", "member", "via", "null",
    # calls and heap
    "call", "with", "allocate", "free", "type", "count", "size",
    # definitions
    "define", "function", "giving", "taking", "none", "end",
    # control flow
    "if", "then", "otherwise", "repeat", "while", "for", "from", "below",
    "stop", "the", "loop", "skip", "next", "give", "back",
})


@dataclass
class CLToken:
    kind: str          # WORD, NUMBER, STRING, PUNCT, NEWLINE, EOF
    text: str
    pos: SourcePos
    value: object = None

    def __repr__(self) -> str:
        return f"{self.kind}({self.text!r})@{self.pos.line}:{self.pos.column}"


class CLLexer:
    """Tokenize c-ll source text.  Newlines are statement terminators."""

    PUNCTUATION = "(),=[]"
    ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}

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

    @staticmethod
    def _is_digit(ch: str) -> bool:
        return "0" <= ch <= "9"

    def tokenize(self) -> list[CLToken]:
        tokens: list[CLToken] = []
        while self.i < len(self.src):
            ch = self._peek()
            if ch in " \t\r\ufeff":
                self._advance()
            elif ch == "#":
                while self._peek() and self._peek() != "\n":
                    self._advance()
            elif ch == "\n":
                pos = self._pos()
                tokens.append(CLToken("NEWLINE", "\n", pos))
                self._advance()
            elif ch == '"':
                tokens.append(self._string())
            elif self._is_digit(ch):
                tokens.append(self._number())
            elif ch.isalpha() or ch == "_":
                tokens.append(self._word())
            elif ch in self.PUNCTUATION:
                pos = self._pos()
                tokens.append(CLToken("PUNCT", self._advance(), pos))
            else:
                raise ParseError(f"Unexpected character {ch!r}", self._pos())
        tokens.append(CLToken("EOF", "", self._pos()))
        return tokens

    def _word(self) -> CLToken:
        pos = self._pos()
        chars = []
        while self._peek().isalnum() or self._peek() == "_":
            chars.append(self._advance())
        text = "".join(chars)
        return CLToken("WORD", text, pos, text)

    def _number(self) -> CLToken:
        pos = self._pos()
        chars = []
        while self._is_digit(self._peek()):
            chars.append(self._advance())
        if (self._peek() == "." and self.i + 1 < len(self.src)
                and self._is_digit(self.src[self.i + 1])):
            chars.append(self._advance())
            while self._is_digit(self._peek()):
                chars.append(self._advance())
        text = "".join(chars)
        value = float(text) if "." in text else int(text)
        return CLToken("NUMBER", text, pos, value)

    def _string(self) -> CLToken:
        pos = self._pos()
        self._advance()  # opening quote
        chars = []
        while True:
            ch = self._peek()
            if not ch or ch == "\n":
                raise ParseError("Unterminated string literal", pos)
            if ch == '"':
                self._advance()
                text = "".join(chars)
                return CLToken("STRING", text, pos, text)
            if ch == "\\":
                self._advance()
                nxt = self._peek()
                if not nxt:
                    raise ParseError("Unterminated escape sequence", pos)
                chars.append(self.ESCAPES.get(self._advance(), nxt))
            else:
                chars.append(self._advance())


def lex_c(source: str) -> list[CLToken]:
    return CLLexer(source).tokenize()
