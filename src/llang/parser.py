"""Recursive-descent parser. Produces canonical AST nodes directly.

Synonym resolution lives in synonyms.py; this module is the desugaring point.
"""

from .ast_nodes import (Program, Block, Literal, Variable, Unary, Binary, Call,
                        Set, Show, Require, If, RepeatWhile, FunctionDef, Return,
                        ListLiteral, MapLiteral, Index, Length, AddTo, SetItem,
                        ForEach, Break, Continue, Fail, Expect, Use,
                         ClassDef, MethodDef, MethodCall)
from .errors import ParseError
from .synonyms import OPERATOR_PHRASES, RESERVED, SHOW_WORDS, SET_WORDS


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.i = 0

    # --- token helpers -------------------------------------------------
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

    # --- program / statements ------------------------------------------
    def parse_program(self) -> Program:
        start = self._tok().pos
        statements = []
        self._skip_newlines()
        while self._tok().kind != "EOF":
            t = self._tok()
            if t.kind == "WORD" and t.text in ("end", "otherwise"):
                raise ParseError(f"Unexpected '{t.text}' — no matching block opener", t.pos)
            statements.append(self.parse_statement())
            self._skip_newlines()
        return Program(statements, pos=start)

    def parse_statement(self):
        t = self._tok()
        word = t.text if t.kind == "WORD" else ""
        if word in SET_WORDS:
            return self._parse_set()
        if word in SHOW_WORDS:
            return self._parse_show()
        if word == "require":
            return self._parse_require()
        if word == "if":
            return self._parse_if()
        if word in ("repeat", "while"):
            return self._parse_repeat()
        if word == "define":
            return self._parse_definition()
        if word == "ask":
            expr = self.parse_ask_expr()
            self._end_statement()
            return expr
        if word in ("give", "return"):
            return self._parse_return()
        if word == "call":
            expr = self.parse_call_expr()
            self._end_statement()
            return expr
        if word == "add":
            return self._parse_add()
        if word == "stop":
            return self._parse_break()
        if word == "skip":
            return self._parse_continue()
        if word == "fail":
            return self._parse_fail()
        if word == "expect":
            return self._parse_expect()
        if word == "use":
            return self._parse_use()
        raise ParseError(f"Unknown statement starting with {word or t.text!r}", t.pos,
                         ["set", "show", "require", "if", "repeat", "define",
                          "give back", "call", "add", "stop the loop",
                          "skip to the next item"])

    def _parse_fail(self) -> Fail:
        start = self._tok().pos
        self._expect_word("fail")
        self._expect_word("with")
        kind = self._expect_name()
        message = None
        if self._accept_punct(","):
            token = self._tok()
            if token.kind != "STRING":
                raise ParseError("Expected a message text after ','", token.pos, ["string"])
            self.i += 1
            message = token.value
        self._end_statement()
        return Fail(kind, message, pos=start)

    def _is_expect_boundary(self) -> bool:
        token = self._tok()
        if token.kind != "WORD":
            return False
        if token.text in ("always", "end"):
            return True
        return (token.text == "if" and
                (self._at_word("nothing", 1) or
                 (self._at_word("a", 1) and self._at_word("problem", 2))))

    def _parse_expect_block(self) -> Block:
        statements = []
        self._skip_newlines()
        while True:
            token = self._tok()
            if token.kind == "EOF":
                raise ParseError("Unexpected end of input — missing 'end expect'",
                                 token.pos)
            if self._is_expect_boundary():
                break
            statements.append(self.parse_statement())
            self._skip_newlines()
        return Block(statements, pos=token.pos)

    def _parse_expect(self) -> Expect:
        start = self._tok().pos
        self._expect_word("expect")
        self._end_statement()
        body = self._parse_expect_block()

        handlers = []
        while (self._at_word("if") and self._at_word("a", 1) and
               self._at_word("problem", 2)):
            self.i += 3
            if self._at_word("occurs"):
                kind = "any"          # catch-all: if a problem occurs then
            else:
                self._expect_word("of")
                self._expect_word("kind")
                kind = self._expect_name()
            self._expect_word("occurs")
            self._expect_word("then")
            self._end_statement()
            handlers.append((kind, self._parse_expect_block()))

        else_body = None
        if self._at_word("if") and self._at_word("nothing", 1):
            self.i += 2
            self._expect_word("went")
            self._expect_word("wrong")
            self._expect_word("then")
            self._end_statement()
            else_body = self._parse_expect_block()

        always_body = None
        if self._accept_word("always"):
            self._end_statement()
            always_body = self._parse_block(("end",))

        self._expect_word("end")
        self._expect_word("expect")
        self._end_statement()
        return Expect(body, handlers, else_body, always_body, pos=start)

    def _parse_use(self) -> Use:
        start = self._tok().pos
        self._expect_word("use")
        self._expect_word("the")
        foreign = self._accept_word("foreign")
        name = self._expect_name()
        self._expect_word("module")
        alias = name
        if self._accept_word("as"):
            alias = self._expect_name()
        self._end_statement()
        return Use(name, foreign, alias, pos=start)

    def _parse_set(self):
        start = self._tok().pos
        if self._accept_word("set"):
            if self._at_word("item"):
                # set item KEY of COLLECTION to VALUE
                self.i += 1
                key = self.parse_expr()
                self._expect_word("of")
                target = self.parse_expr()
                self._expect_word("to")
                value = self.parse_expr()
                self._end_statement()
                return SetItem(target, key, value, pos=start)
            name = self._expect_name()
            self._expect_word("to")
        else:
            self._expect_word("let")
            name = self._expect_name()
            self._expect_word("be")
        expr = self.parse_expr()
        self._end_statement()
        return Set(name, expr, pos=start)

    def _parse_add(self) -> AddTo:
        start = self._tok().pos
        self._expect_word("add")
        value = self.parse_expr()
        self._expect_word("to")
        target = self.parse_expr()
        self._end_statement()
        return AddTo(value, target, pos=start)

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

    def _parse_show(self) -> Show:
        start = self._tok().pos
        self.i += 1  # show / display / print
        expr = self.parse_expr()
        self._end_statement()
        return Show(expr, pos=start)

    def _parse_require(self) -> Require:
        start = self._tok().pos
        self._expect_word("require")
        cond = self.parse_expr()
        message = None
        if self._accept_punct(","):
            t = self._tok()
            if t.kind != "STRING":
                raise ParseError("Expected a string message after ','", t.pos, ["string"])
            self.i += 1
            message = t.value
        self._end_statement()
        return Require(cond, message, pos=start)

    def _parse_if(self) -> If:
        start = self._tok().pos
        self._expect_word("if")
        cond = self.parse_expr()
        self._expect_word("then")
        self._end_statement()
        body = self._parse_block(("end", "otherwise"))
        branches = [(cond, body)]
        while self._at_word("otherwise") and self._at_word("if", 1):
            self.i += 2
            c = self.parse_expr()
            self._expect_word("then")
            self._end_statement()
            b = self._parse_block(("end", "otherwise"))
            branches.append((c, b))
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
        if self._accept_word("repeat"):
            if self._accept_word("for"):
                self._expect_word("each")
                name = self._expect_name()
                self._expect_word("in")
                iterable = self.parse_expr()
                self._end_statement()
                body = self._parse_block(("end",))
                self._expect_word("end")
                self._expect_word("repeat")
                self._end_statement()
                return ForEach(name, iterable, body, pos=start)
            self._expect_word("while")
        else:
            self._expect_word("while")
        cond = self.parse_expr()
        self._end_statement()
        body = self._parse_block(("end",))
        self._expect_word("end")
        self._expect_word("repeat")
        self._end_statement()
        return RepeatWhile(cond, body, pos=start)

    def _parse_definition(self):
        """Dispatch ``define [a] function|class|method`` to the right parser."""
        j = self.i
        if self._at_word("define"):
            j += 1
        if j < len(self.tokens) and self.tokens[j].kind == "WORD" \
                and self.tokens[j].text == "a":
            j += 1
        kind = ""
        if j < len(self.tokens) and self.tokens[j].kind == "WORD":
            kind = self.tokens[j].text
        if kind == "class":
            return self._parse_class_def()
        if kind == "method":
            return self._parse_method_def()
        return self._parse_function_def()

    def _parse_class_def(self) -> ClassDef:
        start = self._tok().pos
        self._expect_word("define")
        self._accept_word("a")
        self._expect_word("class")
        name = self._expect_name()
        fields = []
        if self._accept_word("taking"):
            fields = self._parse_name_list()
        self._end_statement()

        methods = []
        while True:
            self._skip_newlines()
            token = self._tok()
            if token.kind == "EOF":
                raise ParseError("Unexpected end of input — missing 'end class'",
                                 token.pos)
            if token.kind == "WORD" and token.text == "end":
                break
            statement = self.parse_statement()
            if not isinstance(statement, MethodDef):
                raise ParseError("Only method definitions are allowed in a class body",
                                 getattr(statement, "pos", token.pos))
            methods.append(statement)

        self._expect_word("end")
        self._expect_word("class")
        self._end_statement()
        return ClassDef(name, fields, methods, pos=start)

    def _parse_method_def(self) -> MethodDef:
        start = self._tok().pos
        self._expect_word("define")
        self._accept_word("a")
        self._expect_word("method")
        name = self._expect_name()
        self._expect_word("taking")
        # The receiver is explicit: 'this' must be the first parameter.
        token = self._tok()
        if token.kind != "WORD" or token.text != "this":
            raise ParseError("A method's first parameter must be 'this'",
                             token.pos, ["this"])
        self.i += 1
        params = ["this"]
        while self._accept_punct(","):
            params.append(self._expect_name())
        self._end_statement()
        body = self._parse_block(("end",))
        self._expect_word("end")
        self._expect_word("method")
        self._end_statement()
        return MethodDef(name, params, body, pos=start)

    def parse_ask_expr(self) -> MethodCall:
        start = self._tok().pos
        self._expect_word("ask")
        receiver = self.parse_expr()
        self._expect_word("to")
        method = self._expect_name()
        args = []
        if self._accept_word("with"):
            token = self._tok()
            if token.kind == "WORD" and token.text == "this":
                raise ParseError(
                    "'this' is supplied automatically and cannot be a call label",
                    token.pos)
            args = self._parse_arg_list()
        return MethodCall(receiver, method, args, pos=start)

    def _parse_function_def(self) -> FunctionDef:
        start = self._tok().pos
        self._expect_word("define")
        self._accept_word("a")
        self._expect_word("function")
        name = self._expect_name()
        params = []
        if self._accept_word("taking"):
            params = self._parse_name_list()
        self._end_statement()
        self._skip_newlines()
        aliases = []
        if self._accept_word("also"):
            if self._accept_word("known"):
                self._expect_word("as")
            elif self._accept_word("called"):
                self._accept_word("as")   # optional: `also called f, g`
            else:
                t = self._tok()
                raise ParseError("Expected 'known' or 'called' after 'also'", t.pos,
                                 ["known", "called"])
            aliases = self._parse_name_list()
            self._end_statement()
            self._skip_newlines()
        body = self._parse_block(("end",))
        self._expect_word("end")
        self._expect_word("function")
        self._end_statement()
        return FunctionDef(name, aliases, params, body, pos=start)

    def _parse_return(self) -> Return:
        start = self._tok().pos
        if self._accept_word("give"):
            self._expect_word("back")
        else:
            self._expect_word("return")
        expr = self.parse_expr()
        self._end_statement()
        return Return(expr, pos=start)

    def _parse_name_list(self) -> list:
        names = [self._expect_name()]
        while self._accept_punct(","):
            names.append(self._expect_name())
        return names

    def _parse_arg_list(self) -> list:
        args = []
        while True:
            label = self._expect_name()
            self._expect_punct("=")
            value = self.parse_expr()
            args.append((label, value))
            if not self._accept_punct(","):
                break
        return args

    def _parse_block(self, terminators) -> Block:
        statements = []
        self._skip_newlines()
        while True:
            t = self._tok()
            if t.kind == "EOF":
                raise ParseError("Unexpected end of input — missing matching 'end'", t.pos)
            if t.kind == "WORD" and t.text in terminators:
                break
            statements.append(self.parse_statement())
            self._skip_newlines()
        return Block(statements, pos=t.pos)

    # --- expressions ----------------------------------------------------
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
        for phrase, code in OPERATOR_PHRASES:
            if tuple(words[:len(phrase)]) == tuple(phrase):
                self.i += len(phrase)
                return code
        return None

    POSTFIX_PREDICATES = [
        (("is", "not", "empty"), "IS_NOT_EMPTY"),
        (("is", "nothing"), "IS_NOTHING"),
        (("is", "empty"), "IS_EMPTY"),
        (("is", "a", "number"), "IS_NUMBER"),
        (("is", "text"), "IS_TEXT"),
        (("is", "a", "list"), "IS_LIST"),
        (("is", "a", "map"), "IS_MAP"),
    ]

    def _parse_unary(self):
        if self._at_word("not"):
            pos = self._tok().pos
            self.i += 1
            return Unary("NOT", self._parse_unary(), pos=pos)
        node = self._parse_primary()
        while True:
            matched = False
            for phrase, code in self.POSTFIX_PREDICATES:
                if all(self._at_word(word, offset) for offset, word in enumerate(phrase)):
                    self.i += len(phrase)
                    node = Unary(code, node, pos=node.pos)
                    matched = True
                    break
            if not matched:
                break
        return node

    def _parse_call_name(self) -> str:
        """A call name is the run of words between 'call' and 'with' (or EOL).

        This allows English phrase names such as `call uppercase of with ...`.
        """
        # The name is every word up to 'with', end of line, or punctuation.
        # Operator words are allowed inside names (e.g. `rounded to places`).
        words = []
        while True:
            token = self._tok()
            if token.kind == "WORD" and token.text != "with":
                words.append(token.text)
                self.i += 1
            else:
                break
        if not words:
            token = self._tok()
            raise ParseError("Expected a function or built-in name after 'call'",
                             token.pos, ["a name"])
        return " ".join(words)

    def parse_call_expr(self) -> Call:
        start = self._tok().pos
        self._expect_word("call")
        name = self._parse_call_name()
        args = []
        if self._accept_word("with"):
            args = self._parse_arg_list()
        return Call(name, args, pos=start)

    def _parse_primary(self):
        t = self._tok()
        if t.kind in ("NUMBER", "STRING"):
            self.i += 1
            return Literal(t.value, pos=t.pos)
        if t.kind == "WORD":
            if t.text == "true":
                self.i += 1
                return Literal(True, pos=t.pos)
            if t.text == "false":
                self.i += 1
                return Literal(False, pos=t.pos)
            if t.text == "nothing":
                self.i += 1
                return Literal(None, pos=t.pos)
            if t.text == "call":
                return self.parse_call_expr()
            if t.text == "ask":
                return self.parse_ask_expr()
            if t.text == "this":
                self.i += 1
                return Variable(t.text, pos=t.pos)
            if t.text in ("a", "an") and self._at_word("list", 1) or \
                    t.text in ("a", "an") and self._at_word("map", 1) or \
                    t.text in ("a", "an") and self._at_word("empty", 1):
                return self._parse_collection_literal()
            if t.text == "item":
                return self._parse_index()
            if t.text == "the" and self._at_word("length", 1):
                return self._parse_length()
            if t.text in RESERVED:
                raise ParseError(f"Reserved word {t.text!r} cannot be used here", t.pos)
            self.i += 1
            return Variable(t.text, pos=t.pos)
        if t.kind == "PUNCT" and t.text == "(":
            self.i += 1
            expr = self.parse_expr()
            self._expect_punct(")")
            return expr
        raise ParseError(f"Unexpected token {t.text!r} in expression", t.pos)

    def _parse_collection_literal(self):
        start = self._tok().pos
        self.i += 1  # a / an
        if self._accept_word("empty"):
            if self._accept_word("list"):
                return ListLiteral([], pos=start)
            self._expect_word("map")
            return MapLiteral([], pos=start)
        if self._accept_word("list"):
            self._expect_word("of")
            elements = [self.parse_expr()]
            while self._accept_punct(","):
                elements.append(self.parse_expr())
            return ListLiteral(elements, pos=start)
        self._expect_word("map")
        self._expect_word("with")
        entries = []
        while True:
            key = self.parse_expr()
            self._expect_word("mapped")
            self._expect_word("to")
            value = self.parse_expr()
            entries.append((key, value))
            if not self._accept_punct(","):
                break
        return MapLiteral(entries, pos=start)

    def _parse_index(self) -> Index:
        start = self._tok().pos
        self._expect_word("item")
        key = self.parse_expr()
        self._expect_word("of")
        collection = self.parse_expr()
        return Index(collection, key, pos=start)

    def _parse_length(self) -> Length:
        start = self._tok().pos
        self._expect_word("the")
        self._expect_word("length")
        self._expect_word("of")
        collection = self.parse_expr()
        return Length(collection, pos=start)
