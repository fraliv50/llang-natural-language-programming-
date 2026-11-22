"""Recursive-descent parser for the c-ll v1 subset.

Every synonym maps to exactly one node (there are deliberately almost no
synonyms in C).  Expressions have ONE precedence level and are evaluated
left-to-right; grouping is always explicit in the source.  Multi-word keywords
are matched here, longest phrase first, from the token stream produced by
:mod:`llang.cll.lexer`.
"""

from .ast import (
    CType, INT, FLOAT, VOID, TEXT, pointer_to, array_of, struct_type,
    Program, Block, Literal, Null, Variable, Unary, Binary, Cast, AddressOf,
    Deref, Index, MemberAccess, SizeOf, Alloc, Free, Call, TypedDecl, Set,
    Show, StructDef, FunctionDef, Return, If, RepeatWhile, CountedLoop, Break,
    Continue,
)
from .lexer import RESERVED
from ..errors import ParseError


# Longest phrases first.  ``does not equal`` must win over any shorter match,
# and ``is at least``/``is at most`` must be tried as complete phrases.
OPERATORS = [
    (("does", "not", "equal"), "NE"),
    (("is", "less", "than"), "LT"),
    (("is", "greater", "than"), "GT"),
    (("is", "at", "most"), "LE"),
    (("is", "at", "least"), "GE"),
    (("divided", "by"), "DIV"),
    (("equals",), "EQ"),
    (("plus",), "ADD"),
    (("minus",), "SUB"),
    (("times",), "MUL"),
    (("remainder",), "REM"),
    (("and",), "LAND"),
    (("or",), "LOR"),
]

_TIER3_NODES = (AddressOf, Deref, Index, MemberAccess, Alloc, Free, SizeOf)


class CLParser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.i = 0

    # --- token helpers ---------------------------------------------------
    def _tok(self, off: int = 0):
        j = self.i + off
        return self.tokens[j] if j < len(self.tokens) else self.tokens[-1]

    def _at_word(self, word: str, off: int = 0) -> bool:
        t = self._tok(off)
        return t.kind == "WORD" and t.text == word

    def _accept_word(self, word: str) -> bool:
        if self._at_word(word):
            self.i += 1
            return True
        return False

    def _expect_word(self, word: str):
        if not self._accept_word(word):
            t = self._tok()
            raise ParseError(f"Expected '{word}', found {t.text!r}", t.pos, [word])

    def _at_phrase(self, phrase) -> bool:
        return all(self._at_word(word, offset) for offset, word in enumerate(phrase))

    def _accept_phrase(self, phrase) -> bool:
        if self._at_phrase(phrase):
            self.i += len(phrase)
            return True
        return False

    def _accept_punct(self, punct: str) -> bool:
        t = self._tok()
        if t.kind == "PUNCT" and t.text == punct:
            self.i += 1
            return True
        return False

    def _expect_punct(self, punct: str):
        if not self._accept_punct(punct):
            t = self._tok()
            raise ParseError(f"Expected '{punct}', found {t.text!r}", t.pos, [punct])

    def _expect_name(self) -> str:
        t = self._tok()
        if t.kind != "WORD" or t.text in RESERVED:
            raise ParseError(f"Expected a name, found {t.text!r}", t.pos,
                             ["a non-reserved identifier"])
        self.i += 1
        return t.text

    def _skip_newlines(self):
        while self._tok().kind == "NEWLINE":
            self.i += 1

    def _end_statement(self):
        t = self._tok()
        if t.kind == "NEWLINE":
            self.i += 1
        elif t.kind != "EOF":
            raise ParseError(f"Expected end of line, found {t.text!r}", t.pos)

    # --- program ---------------------------------------------------------
    def parse_program(self) -> Program:
        start = self._tok().pos
        statements = []
        self._skip_newlines()
        while self._tok().kind != "EOF":
            t = self._tok()
            if t.kind == "WORD" and t.text in ("end", "otherwise"):
                raise ParseError(f"Unexpected '{t.text}' — no matching block opener",
                                 t.pos)
            statements.append(self.parse_statement())
            self._skip_newlines()
        return Program(statements, tier=self._infer_tier(statements), pos=start)

    @staticmethod
    def _infer_tier(statements) -> int:
        seen = set()

        def walk(node):
            if node is None or id(node) in seen:
                return False
            seen.add(id(node))
            if isinstance(node, _TIER3_NODES):
                return True
            if isinstance(node, TypedDecl) and node.ctype is not None \
                    and _type_has_pointer(node.ctype):
                return True
            result = False
            for value in getattr(node, "__dict__", {}).values():
                if isinstance(value, (list, tuple)):
                    for item in value:
                        if hasattr(item, "__dict__") and walk(item):
                            result = True
                elif isinstance(value, CType):
                    if _type_has_pointer(value):
                        result = True
                elif hasattr(value, "__dict__") and walk(value):
                    result = True
            return result

        return 3 if any(walk(stmt) for stmt in statements) else 2

    def parse_statement(self):
        t = self._tok()
        word = t.text if t.kind == "WORD" else ""
        if word == "define":
            if self._at_word("struct", 1):
                return self._parse_struct_def()
            if self._at_word("function", 1):
                return self._parse_function_def()
            raise ParseError("Expected 'struct' or 'function' after 'define'",
                             self._tok(1).pos, ["struct", "function"])
        if word == "let":
            return self._parse_decl()
        if word == "set":
            return self._parse_set()
        if word == "show":
            return self._parse_show()
        if word == "if":
            return self._parse_if()
        if word == "repeat":
            return self._parse_repeat()
        if word == "stop":
            return self._parse_break()
        if word == "skip":
            return self._parse_continue()
        if word == "give":
            return self._parse_return()
        if word == "call":
            node = self.parse_call_expr()
            self._end_statement()
            return node
        raise ParseError(f"Unknown statement starting with {word or t.text!r}",
                         t.pos, ["define", "let", "set", "show", "if", "repeat",
                                 "stop the loop", "skip to the next item",
                                 "give back", "call"])

    def _parse_struct_def(self) -> StructDef:
        start = self._tok().pos
        self._expect_word("define")
        self._expect_word("struct")
        name = self._expect_name()
        self._expect_word("with")
        fields = [self._parse_field()]
        while self._accept_punct(","):
            fields.append(self._parse_field())
        self._end_statement()
        body = self._parse_block(("end",))
        if body.statements:
            raise ParseError("A struct body must be empty", body.pos)
        self._expect_word("end")
        self._expect_word("struct")
        self._end_statement()
        return StructDef(name, fields, pos=start)

    def _parse_field(self):
        name = self._expect_name()
        self._expect_word("as")
        return (name, self.parse_type())

    def _parse_function_def(self) -> FunctionDef:
        start = self._tok().pos
        self._expect_word("define")
        self._expect_word("function")
        name = self._expect_name()
        self._expect_word("giving")
        return_type = self.parse_type()
        self._expect_word("taking")
        params = []
        if not self._accept_word("none"):
            params.append(self._parse_field())
            while self._accept_punct(","):
                params.append(self._parse_field())
        self._end_statement()
        body = self._parse_block(("end",))
        self._expect_word("end")
        self._expect_word("function")
        self._end_statement()
        return FunctionDef(name, return_type, params, body, pos=start)

    def _parse_block(self, terminators) -> Block:
        statements = []
        self._skip_newlines()
        while True:
            t = self._tok()
            if t.kind == "EOF":
                raise ParseError("Unexpected end of input — missing matching 'end'",
                                 t.pos)
            if t.kind == "WORD" and t.text in terminators:
                break
            statements.append(self.parse_statement())
            self._skip_newlines()
        return Block(statements, pos=t.pos)

    # --- statements ------------------------------------------------------
    def _parse_decl(self) -> TypedDecl:
        start = self._tok().pos
        self._expect_word("let")
        name = self._expect_name()
        self._expect_word("as")
        ctype = self.parse_type()
        self._expect_word("be")       # initializer is mandatory in v1
        init = self.parse_expr()
        self._end_statement()
        return TypedDecl(name, ctype, init, pos=start)

    def _parse_set(self) -> Set:
        start = self._tok().pos
        self._expect_word("set")
        target = self._parse_lvalue()
        self._expect_word("to")
        value = self.parse_expr()
        self._end_statement()
        return Set(target, value, pos=start)

    def _parse_lvalue(self):
        start = self._tok().pos
        if self._at_phrase(("value", "at")):
            self.i += 2
            return Deref(self.parse_expr(), pos=start)
        if self._at_word("item"):
            self.i += 1
            index = self.parse_expr()
            self._expect_word("of")
            base = self.parse_expr()
            return Index(base, index, pos=start)
        if self._at_word("member"):
            self.i += 1
            field = self._expect_name()
            if self._accept_word("of"):
                via_pointer = False
            elif self._accept_word("via"):
                via_pointer = True
            else:
                t = self._tok()
                raise ParseError("Expected 'of' or 'via' after member name", t.pos,
                                 ["of", "via"])
            base = self.parse_expr()
            return MemberAccess(base, field, via_pointer, pos=start)
        return Variable(self._expect_name(), pos=start)

    def _parse_show(self) -> Show:
        start = self._tok().pos
        self._expect_word("show")
        exprs = [self.parse_expr()]
        while self._accept_punct(","):
            exprs.append(self.parse_expr())
        self._end_statement()
        return Show(exprs, pos=start)

    def _parse_if(self) -> If:
        start = self._tok().pos
        self._expect_word("if")
        cond = self.parse_expr()
        self._expect_word("then")
        self._end_statement()
        body = self._parse_block(("end", "otherwise"))
        branches = [(cond, body)]
        while self._at_phrase(("otherwise", "if")):
            self.i += 2
            cond = self.parse_expr()
            self._expect_word("then")
            self._end_statement()
            branches.append((cond, self._parse_block(("end", "otherwise"))))
        otherwise = None
        if self._accept_word("otherwise"):
            self._end_statement()
            otherwise = self._parse_block(("end",))
        self._expect_word("end")
        self._expect_word("if")
        self._end_statement()
        return If(branches, otherwise, pos=start)

    def _parse_repeat(self):
        start = self._tok().pos
        self._expect_word("repeat")
        if self._accept_word("while"):
            cond = self.parse_expr()
            self._end_statement()
            body = self._parse_block(("end",))
            self._expect_word("end")
            self._expect_word("repeat")
            self._end_statement()
            return RepeatWhile(cond, body, pos=start)
        if self._accept_word("for"):
            name = self._expect_name()
            self._expect_word("from")
            begin = self.parse_expr()
            self._expect_word("below")
            limit = self.parse_expr()
            step = None
            if self._accept_word("by"):
                step = self.parse_expr()
            self._end_statement()
            body = self._parse_block(("end",))
            self._expect_word("end")
            self._expect_word("repeat")
            self._end_statement()
            if step is None:
                step = Literal(1, INT, pos=start)
            return CountedLoop(name, begin, limit, step, body, pos=start)
        t = self._tok()
        raise ParseError("Expected 'while' or 'for' after 'repeat'", t.pos,
                         ["while", "for"])

    def _parse_break(self) -> Break:
        start = self._tok().pos
        self._expect_word("stop")
        self._expect_word("the")
        self._expect_word("loop")
        self._end_statement()
        return Break(pos=start)

    def _parse_continue(self) -> Continue:
        start = self._tok().pos
        self._expect_word("skip")
        self._expect_word("to")
        self._expect_word("the")
        self._expect_word("next")
        self._expect_word("item")
        self._end_statement()
        return Continue(pos=start)

    def _parse_return(self) -> Return:
        start = self._tok().pos
        self._expect_word("give")
        self._expect_word("back")
        expr = self.parse_expr()
        self._end_statement()
        return Return(expr, pos=start)

    # --- types -----------------------------------------------------------
    def parse_type(self) -> CType:
        t = self._tok()
        if t.kind != "WORD":
            raise ParseError(f"Expected a type, found {t.text!r}", t.pos)
        if t.text in ("int", "float", "void"):
            self.i += 1
            return {"int": INT, "float": FLOAT, "void": VOID}[t.text]
        if self._at_phrase(("pointer", "to")):
            self.i += 2
            return pointer_to(self.parse_type())
        if self._at_word("array"):
            self.i += 1
            self._expect_punct("[")
            size = self._tok()
            if size.kind != "NUMBER" or not isinstance(size.value, int):
                raise ParseError("Array size must be a whole number literal",
                                 size.pos, ["a non-negative integer"])
            self.i += 1
            self._expect_punct("]")
            self._expect_word("of")
            return array_of(self.parse_type(), size.value)
        if self._at_word("struct"):
            self.i += 1
            return struct_type(self._expect_name())
        raise ParseError(f"Expected a type, found {t.text!r}", t.pos,
                         ["int", "float", "void", "pointer to", "array", "struct"])

    # --- expressions -----------------------------------------------------
    def parse_expr(self):
        left = self._parse_unary()
        while True:
            op = self._match_operator()
            if op is None:
                break
            right = self._parse_unary()
            left = Binary(op, left, right, pos=left.pos)
        return left

    def _match_operator(self):
        words = []
        j = self.i
        while j < len(self.tokens) and self.tokens[j].kind == "WORD":
            words.append(self.tokens[j].text)
            j += 1
        for phrase, code in OPERATORS:
            if tuple(words[:len(phrase)]) == tuple(phrase):
                self.i += len(phrase)
                return code
        return None

    def _parse_unary(self):
        start = self._tok().pos
        if self._accept_word("not"):
            return Unary("LNOT", self._parse_unary(), pos=start)
        if self._accept_phrase(("address", "of")):
            return AddressOf(self._parse_unary(), pos=start)
        return self._parse_primary()

    def _parse_primary(self):
        t = self._tok()
        if t.kind == "NUMBER":
            self.i += 1
            ctype = FLOAT if isinstance(t.value, float) else INT
            return Literal(t.value, ctype, pos=t.pos)
        if t.kind == "STRING":
            self.i += 1
            return Literal(t.value, TEXT, pos=t.pos)
        if t.kind == "PUNCT" and t.text == "(":
            self.i += 1
            expr = self.parse_expr()
            self._expect_punct(")")
            return expr
        if t.kind != "WORD":
            raise ParseError(f"Unexpected token {t.text!r} in expression", t.pos)

        if self._at_phrase(("null", "pointer")):
            self.i += 2
            return Null(pos=t.pos)
        if self._at_word("call"):
            return self.parse_call_expr()
        if self._at_word("cast"):
            self.i += 1
            expr = self.parse_expr()
            self._expect_word("as")
            return Cast(expr, self.parse_type(), pos=t.pos)
        if self._at_phrase(("size", "of")):
            self.i += 2
            return SizeOf(self.parse_type(), pos=t.pos)
        if self._at_phrase(("value", "at")):
            self.i += 2
            return Deref(self.parse_expr(), pos=t.pos)
        if self._at_word("item"):
            self.i += 1
            index = self.parse_expr()
            self._expect_word("of")
            return Index(self.parse_expr(), index, pos=t.pos)
        if self._at_word("member"):
            self.i += 1
            field = self._expect_name()
            if self._accept_word("of"):
                via = False
            elif self._accept_word("via"):
                via = True
            else:
                raise ParseError("Expected 'of' or 'via' after member name",
                                 self._tok().pos, ["of", "via"])
            return MemberAccess(self.parse_expr(), field, via, pos=t.pos)
        if t.text in RESERVED:
            raise ParseError(f"Reserved word {t.text!r} cannot be used here", t.pos)
        self.i += 1
        return Variable(t.text, pos=t.pos)

    def parse_call_expr(self):
        start = self._tok().pos
        self._expect_word("call")
        t = self._tok()
        if t.kind == "WORD" and t.text in ("allocate", "free"):
            name = t.text
            self.i += 1
        else:
            name = self._expect_name()
        if name == "allocate":
            return self._parse_allocate(start)
        if name == "free":
            return self._parse_free(start)
        args = []
        if self._accept_word("with"):
            t = self._tok()
            if t.kind not in ("NEWLINE", "EOF"):
                args.append(self.parse_expr())
                while self._accept_punct(","):
                    args.append(self.parse_expr())
        return Call(name, args, pos=start)

    def _parse_allocate(self, start) -> Alloc:
        self._expect_word("with")
        element = None
        count = None
        while True:
            token = self._tok()
            if token.kind != "WORD":
                raise ParseError("Expected an argument label", token.pos,
                                 ["type", "count"])
            label = token.text
            self.i += 1
            self._expect_punct("=")
            if label == "type":
                element = self.parse_type()
            elif label == "count":
                count = self.parse_expr()
            else:
                raise ParseError("allocate takes 'type' and 'count'", self._tok().pos,
                                 ["type", "count"])
            if not self._accept_punct(","):
                break
        if element is None or count is None:
            raise ParseError("allocate requires both 'type =' and 'count ='", start)
        return Alloc(element, count, pos=start)

    def _parse_free(self, start) -> Free:
        self._expect_word("with")
        self._expect_word("pointer")
        self._expect_punct("=")
        expr = self.parse_expr()
        return Free(expr, pos=start)


def _type_has_pointer(ctype: CType) -> bool:
    if ctype is None:
        return False
    if ctype.kind == "pointer":
        return True
    if ctype.kind == "array":
        return _type_has_pointer(ctype.element)
    return False


def parse_c(tokens) -> Program:
    return CLParser(tokens).parse_program()
