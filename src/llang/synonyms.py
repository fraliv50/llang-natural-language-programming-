"""The closed surface vocabulary.

This is the ONLY place synonyms are defined. Every phrase maps to one canonical
operator code, so flexibility never leaks into the interpreter. Additions must be
documented in docs/GRAMMAR.md.
"""

# Longest phrases first so prefix phrases ("is") don't shadow longer ones.
OPERATOR_PHRASES = [
    (("does", "not", "equal"), "NE"),
    (("is", "not", "equal", "to"), "NE"),
    (("is", "greater", "than"), "GT"),
    (("is", "more", "than"), "GT"),
    (("is", "less", "than"), "LT"),
    (("is", "at", "least"), "GE"),
    (("is", "at", "most"), "LE"),
    (("is", "equal", "to"), "EQ"),
    (("differs", "from"), "NE"),
    (("floor", "divided", "by"), "FLOORDIV"),
    (("divided", "by"), "DIV"),
    (("to", "the", "power", "of"), "POW"),
    (("equals",), "EQ"),
    (("exceeds",), "GT"),
    (("plus",), "ADD"),
    (("minus",), "SUB"),
    (("times",), "MUL"),
    (("modulo",), "MOD"),
    (("and",), "AND"),
    (("or",), "OR"),
]

OPERATOR_PHRASES.sort(key=lambda pair: -len(pair[0]))

SHOW_WORDS = ("show", "display", "print")
SET_WORDS = ("set", "let")
RETURN_WORDS = ("give", "return")
ALIAS_WORDS = ("also",)

RESERVED = {
    # core statements
    "set", "let", "to", "be", "show", "display", "print", "require",
    "if", "then", "otherwise", "end", "repeat", "while", "define",
    "function", "taking", "also", "known", "called", "as", "give", "back",
    "return", "call", "with", "not", "and", "or", "true", "false", "nothing",
    # collections and iteration
    "list", "map", "empty", "mapped", "of", "item", "the", "length",
    "each", "in", "add", "remove", "from", "stop", "next", "loop", "skip",
    # problems (exceptions)
    "expect", "problem", "kind", "occurs", "went", "wrong", "always", "fail",
    # modules and libraries
    "use", "module", "foreign",
    # classes / records (the minimal class system)
    "class", "method", "ask", "this",
}

KEYWORD_STARTS = RESERVED | set(SHOW_WORDS) | set(SET_WORDS) | set(RETURN_WORDS) | set(ALIAS_WORDS)
