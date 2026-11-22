# llang Test Plan

*Status: design proposal. Grounded by reading `src/llang/*`, `tests/test_core.py`, `examples/hello.ll`, and all of `docs/` including `docs/research/python-semantics.md`. Re-synced against the implementation on 2026-11-22 after collections, iteration, and builtins landed in `parser.py`/`interpreter.py`/`ast_nodes.py`. **The codebase is changing in parallel; regenerate the exact-message table (§7) from source whenever it changes.** Where source and docs disagree, this plan follows the source and records the mismatch in §13.*

## 0. Purpose, scope, and conventions

This document is the executable specification of how llang is tested. Every entry is a **concrete case**: input source plus expected observable behavior (AST shape, `Interpreter.output`, or exact diagnostic string), ready to be turned into a `unittest` method.

### 0.1 Testing principles (from `DESIGN.md` §5)

1. **Test the canonical core, then the sugar.** Every canonical node in `ast_nodes.py` gets a node-level test; every entry in `synonyms.py` gets an equivalence test.
2. **Synonym tests prove *identical* ASTs**, not just identical output. Because `pos` fields legitimately differ between spellings, AST comparison uses a position-stripping normalizer (§1.3).
3. **Errors are part of the spec.** Diagnostics tests assert the *exact rendered string*, including line/column and expected-token hints (§7).
4. **No undefined behavior.** Every construct has a defined result or a defined, loud error; tests pin both sides.
5. **Tests pin divergences from Python** deliberately (`SEMANTIC-DECISIONS.md`): no precedence, no chaining, no loop-else, strict types, no coercion, snapshot iteration. Where the implementation diverges from the *decisions*, it is recorded in §13 rather than silently accepted.

### 0.2 Observable surfaces

| Surface | Used for | Notes |
|---|---|---|
| `Lexer(src).tokenize()` | Lexical tests | Assert `(kind, text, value, pos.line, pos.column)`. |
| `Parser(tokens).parse_program()` | Parser / AST / synonym tests | Compare normalized ASTs. |
| `run_source(src).output` | Evaluator / E2E tests | **Always assert on `.output`**, not stdout. `Show` appends *and* `print()`s, so stdout tests double-count. |
| `str(exc)` on `LangError` | Diagnostics tests | `LangError.__init__` calls `super().__init__(self.render())`, so `str(exc)` is the rendered message with ` at line L, column C` and optional `\n  expected one of: …`. |
| `Interpreter(max_iterations=N)` | Loop guard | Avoid running 100 000 iterations in a test. |
| `run_source(src).global_env.get(name)` | Alias identity / builtin registration | Assert `is` identity for aliases; assert `Builtin` instances present. |

### 0.3 Rendering rules the tests rely on

- `_render(None) == "nothing"`, `True → "true"`, `False → "false"`.
- `_render(list)` → `"[" + ", ".join(_render(x) …) + "]"`; `_render(dict)` → `"{" + ", ".join(f"{_render(k)}: {_render(v)}" …) + "}"`. Keys render *unquoted*: `{"a":1}` shows as `{a: 1}`.
- Otherwise `str(value)` — so `4 divided by 2` renders `"2.0"`.
- Binary nodes take `pos=left.pos`; `Index`/`Length`/`AddTo`/`SetItem`/`ForEach` take the pos of their leading keyword (`item`, `the`, `add`, `set`, `repeat`); `Call` takes the pos of `call`. Diagnostics assert these exact positions.
- Two parser messages contain an em dash (`—`): `Unexpected 'X' — no matching block opener` and `Unexpected end of input — missing matching 'end'`.

---

## 1. Test infrastructure, layout, and naming

### 1.1 Directory layout

```
tests/
  _helpers.py                 # shared helpers (run, parse, normalize, assert_error)
  test_lexer.py               # category 1
  test_parser.py              # category 2
  test_synonyms.py            # category 3
  test_evaluator.py           # category 4
  test_collections.py         # collections + iteration now implemented (§6.6, §9)
  test_builtins.py            # 20 registered builtins (§6.7)
  test_diagnostics.py         # category 5
  test_edge_cases.py          # category 6 (grounded semantic decisions)
  test_end_to_end.py          # category 10
  test_formatter_roundtrip.py # category 8  -- @unittest.skip until formatter exists
  test_linter.py              # category 9  -- @unittest.skip until linter exists
  test_planned_features.py    # truly unimplemented: exceptions, classes, modules, defaults
  fixtures/
    hello.ll                  # copy/ref of examples/hello.ll
    all_synonyms.ll
    nested_blocks.ll
    recursion.ll
    collections.ll
    crlf_program.ll           # intentionally CRLF line endings
    unicode_identifiers.ll
    type_errors.ll
    diagnostics.ll
```

Keep `unittest` (existing runner: `python -m unittest discover -s tests -v`); do not introduce pytest. Use `subTest` for synonym/operator/builtin tables. Unimplemented suites are checked in **skipped** with a reason naming the phase, e.g. `@unittest.skip("Exceptions phase")`, so they become active the moment the feature lands.

### 1.2 Naming convention

- Files: `test_<area>.py` as above.
- Classes: `LexerTests`, `ParserTests`, `SynonymEquivalenceTests`, `EvaluatorTests`, `CollectionsTests`, `BuiltinTests`, `DiagnosticTests`, `EdgeCaseTests`, `EndToEndTests`, `FormatterTests`, `LinterTests`, `PlannedFeatureTests`.
- Methods: `test_<behavior>_<condition>`, e.g. `test_string_unknown_escape_drops_backslash`, `test_call_missing_argument_names_expected`. Prefix skipped placeholders with `test_todo_` so they are greppable.

### 1.3 Required helpers (`tests/_helpers.py`)

```python
from dataclasses import fields, is_dataclass, replace
from llang import Lexer, Parser, run_source

def tokens(src):            return Lexer(src).tokenize()
def parse(src):             return Parser(tokens(src)).parse_program()
def run(src):               return run_source(src).output

def normalize(node):
    """Strip SourcePos from an AST so synonym ASTs compare for structural equality."""
    if isinstance(node, (list, tuple)):
        return type(node)(normalize(n) for n in node)
    if is_dataclass(node) and not hasattr(node, "line"):   # skip SourcePos itself
        kw = {f.name: normalize(getattr(node, f.name))
              for f in fields(node) if f.name != "pos"}
        return replace(node, pos=None, **kw)
    return node

def ast(src):               return normalize(parse(src))

def run_bounded(src, n):
    from llang import Interpreter
    it = Interpreter(max_iterations=n)
    it.run(parse(src))
    return it.output

def assert_error(testcase, src, expected_text=None):
    with testcase.assertRaises(LangError) as ctx:
        run_source(src)
    if expected_text is not None:
        testcase.assertEqual(str(ctx.exception), expected_text)
    return ctx.exception
```

Note `SourcePos` is a frozen dataclass with `line`/`column` but no `pos` field; the `hasattr(node, "line")` guard keeps the normalizer from trying to `replace` it.

---

## 2. Coverage map (must be complete before a release)

### 2.1 Canonical nodes — all 23 in `ast_nodes.py`

| Node | Primary tests |
|---|---|
| `Program`, `Block` | `test_parser_program_*`, `test_parser_empty_block_*`, `test_parser_nested_*` |
| `Literal`, `Variable` | §3, `test_eval_literal_*`, `test_eval_variable_undefined` |
| `Unary` (NOT) | `test_eval_not_*`, `test_parser_not_binds_tighter_than_comparison` |
| `Binary` (ADD/SUB/MUL/DIV/MOD/POW/GT/LT/GE/LE/EQ/NE/AND/OR) | §5.1 table + §6.1–6.3 |
| `Call` | `test_parser_labeled_args_*`, `test_eval_call_*`, §6.7 |
| `Set`, `Show`, `Require` | §4.1, §6.4 |
| `If`, `RepeatWhile` | §4.1–4.3, §6.2, §6.4 |
| `FunctionDef`, `Return` | §4.1–4.2, §6.5 |
| `ListLiteral`, `MapLiteral`, `Index`, `Length` | §4.5, §6.6 |
| `AddTo`, `SetItem` | §4.1, §6.6 |
| `ForEach`, `Break`, `Continue` | §4.1, §6.6 |

### 2.2 Synonyms (`synonyms.py` / `GRAMMAR.md`)

| Family | Test |
|---|---|
| `show` / `display` / `print` | `test_syn_show_words_identical_ast` |
| `set … to` / `let … be` | `test_syn_set_words_identical_ast` |
| `define function` / `define a function` | `test_syn_define_function_a_optional` |
| `give back` / `return` | `test_syn_return_words_identical_ast` |
| `also known as` / `also called as` | `test_syn_alias_words_identical_ast` (§13.2 mismatch) |
| `repeat while` / `while` | `test_syn_repeat_words_identical_ast` |
| `repeat for each` (single spelling) / `for each … in` (documented primary) | `test_syn_foreach_spelling` (§13.8) |
| all 19 `OPERATOR_PHRASES` entries | `test_syn_operator_phrases_table` |

### 2.3 Builtins (20 registered in `BUILTINS`)

`to_text`, `to_number`, `is_number`, `is_text`, `is_list`, `is_map`, `keys`, `values`, `contains`, `join`, `split`, `sort`, `sum`, `minimum`, `maximum`, `absolute`, `rounded`, `read_file`, `write_file` — §6.7 gives one test each.

---

## 3. Category 1 — Lexical tests (`test_lexer.py`)

Assertions on token tuples via `tk = [(t.kind, t.text, t.value, t.pos.line, t.pos.column) for t in tokens(src)]`.

### 3.1 Whitespace, newlines, blank lines, comments

| Test | Source | Expected |
|---|---|---|
| `test_lex_spaces_tabs_ignored` | `"  set\tx\tto\t1"` | WORD(set)@1:3, WORD(x)@1:7, WORD(to)@1:9, NUMBER(1)@1:12, EOF. No whitespace tokens. |
| `test_lex_newline_is_token` | `"show 1\nshow 2"` | NEWLINE at line 1 col 7; EOF at line 2 col 7. |
| `test_lex_blank_lines_produce_consecutive_newlines` | `"\n\nshow 1\n"` | Two leading NEWLINEs skipped by parser; `.output == ["1"]`. |
| `test_lex_comment_ignored_entirely` | `"# full line comment\nshow 1 # trailing"` | No WORD tokens from comments; output `["1"]`. |
| `test_lex_hash_inside_string_is_literal` | `'show "# not a comment"'` | STRING value `"# not a comment"`. |
| `test_lex_comment_at_eof_without_newline` | `"show 1 # end"` | No trailing NEWLINE; output `["1"]`. |
| `test_lex_empty_source_is_empty_program` | `""` | `[EOF@1:1]`; `ast(src) == normalize(Program([]))`; `.output == []`. |

### 3.2 CRLF

| Test | Source | Expected |
|---|---|---|
| `test_lex_crlf_treated_as_newline` | `"show 1\r\nshow 2\r\n"` | `\r` skipped (advances column, never line); two Show statements; output `["1","2"]`. |
| `test_lex_crlf_error_line_column` | `"show 1\r\nshow @"` | `LangError("Unexpected character '@' at line 2, column 6")`. |
| `test_lex_bare_cr_is_whitespace` | `"show\r1"` | CR skipped; `show 1` as one statement. |

### 3.3 Strings and escapes

| Test | Source | Expected STRING value / error |
|---|---|---|
| `test_lex_empty_string` | `'show ""'` | `""`; output `[""]` |
| `test_lex_escape_n` | `r'show "a\nb"'` | `"a\nb"` (real newline) |
| `test_lex_escape_t` | `r'show "a\tb"'` | `"a\tb"` |
| `test_lex_escape_quote` | `r'show "say \"hi\""'` | `say "hi"` |
| `test_lex_escape_backslash` | `r'show "a\\b"'` | `a\b` |
| `test_lex_unknown_escape_drops_backslash` | `r'show "a\qb"'` | `aqb` — pins `escapes.get(ch, ch)` fallback (§13.9) |
| `test_lex_unterminated_string_at_eof` | `r'show "abc'` | `Unterminated string literal at line 1, column 6` (pos = opening quote) |
| `test_lex_unterminated_string_newline` | `'show "abc\ndef"'` | Same error at line 1 col 6; newline in string illegal |
| `test_lex_trailing_backslash_is_escape_error` | `r'show "abc\'` | `Unterminated escape sequence at line 1, column 6` |
| `test_lex_single_quotes_rejected` | `"show 'hi'"` | `Unexpected character "'" at line 1, column 6` |

### 3.4 Numbers

| Test | Source | Expected |
|---|---|---|
| `test_lex_integer` | `"show 42"` | NUMBER("42", 42)@1:6 |
| `test_lex_float` | `"show 3.14"` | NUMBER("3.14", 3.14)@1:6 |
| `test_lex_large_integer_no_overflow` | 30-digit integer | Rendered exactly (arbitrary precision) |
| `test_lex_trailing_dot_is_error` | `"show 3."` | NUMBER 3 then `Unexpected character '.' at line 1, column 7` |
| `test_lex_leading_dot_is_error` | `"show .5"` | `Unexpected character '.' at line 1, column 6` |
| `test_lex_no_exponent_notation` | `"show 1e3"` | NUMBER 1, WORD `e3`, then `Expected end of line, found 'e3'` |
| `test_lex_no_negative_literal` | `"show -3"` | `Unexpected character '-' at line 1, column 6`; use `0 minus 3` |
| `test_lex_unicode_nd_digit` | `"show ٣"` (Arabic-Indic 3) | Accepted: `int("٣") == 3`, output `["3"]` (§13.1) |
| `test_lex_unicode_nondecimal_digit_raises_valueerror` | `"show ²"` | `str.isdigit()` true but `int("²")` raises bare `ValueError` — **bug**, pin with `assertRaises(ValueError)` |

### 3.5 Words, reserved words, unexpected characters

| Test | Source | Expected |
|---|---|---|
| `test_lex_identifier_shape` | `"set _a1_b2 to 3"` | WORD `_a1_b2`; output `["3"]` via show |
| `test_lex_unicode_identifier_accepted` | `"set café to 3\nshow café"` | Accepted (`isalpha()`), output `["3"]`; grammar says ASCII (§13.1) |
| `test_lex_greek_identifier_accepted` | `"set δ to 4\nshow δ"` | Accepted, output `["4"]` |
| `test_lex_reserved_words_are_just_words_to_lexer` | `"show end"` | WORD(end) from lexer; parser rejects: `Reserved word 'end' cannot be used here at line 1, column 6` |
| `test_lex_symbolic_operators_rejected` | `"show 1 + 2"` | `Unexpected character '+' at line 1, column 8` |
| `test_lex_bad_punctuation_table` | `show 1 <ch> 2` for `[ ] { } : ! ; @ '` | `Unexpected character <repr>` at correct column (subTest per char) |
| `test_lex_punctuation_set` | `"call f with a = (1), b = 2"` | PUNCT `(`, `=`, `)`, `,`, `=` |

---

## 4. Category 2 — Parser tests (`test_parser.py`)

### 4.1 Every statement form

| Test | Source | Expected AST |
|---|---|---|
| `test_parser_set_to` / `test_parser_let_be` | `set x to 1` / `let x be 1` | `Set("x", Literal(1))` for both |
| `test_parser_show_expr` | `show 1 plus 2` | `Show(Binary("ADD", 1, 2))` |
| `test_parser_require_no_message` | `require true` | `Require(Literal(True), None)` |
| `test_parser_require_with_message` | `'require true, "ok"'` | `Require(Literal(True), "ok")` |
| `test_parser_if_single_branch` | `if true then\n show 1\nend if` | `If([(True, Block([Show 1]))], None)` |
| `test_parser_if_chain` | core `test_if_otherwise_if_otherwise` | 3 branches when two `otherwise if` present |
| `test_parser_if_otherwise` | `if false then … otherwise … end if` | `otherwise=Block([Show(2)])` |
| `test_parser_repeat_while` | `repeat while false … end repeat` | `RepeatWhile(False, Block)` |
| `test_parser_while_alias` | `while false … end repeat` | Identical AST; `end repeat` still required |
| `test_parser_repeat_for_each` | `repeat for each x in xs\n show x\nend repeat` | `ForEach("x", Variable("xs"), Block([Show x]))` |
| `test_parser_add_to` | `add 3 to xs` | `AddTo(Literal(3), Variable("xs"))` |
| `test_parser_set_item` | `set item k of m to v` | `SetItem(Variable("m"), Variable("k"), Variable("v"))` |
| `test_parser_stop_loop` | `stop the loop` | `Break` |
| `test_parser_skip_next` | `skip to the next item` | `Continue` |
| `test_parser_function_no_params` | `define function f\n give back 1\nend function` | `FunctionDef("f", [], [], Block([Return(1)]))` |
| `test_parser_function_with_params` | `define function f taking x, y\n …` | `params == ["x","y"]` |
| `test_parser_function_aliases` | `define a function f taking x\nalso known as g, h\n …` | `aliases == ["g","h"]` |
| `test_parser_give_back` / `test_parser_return` | both spellings | `Return(Literal(1))` |
| `test_parser_call_statement` | `call f with a = 1` | Top-level `Call` node, result discarded |
| `test_parser_call_expression` | `show call f with a = 1` | `Show(Call(...))` |

### 4.2 Missing delimiters and malformed headers

| Test | Source | Expected exact error |
|---|---|---|
| `test_parser_missing_end_if_at_eof` | `if true then\n show 1` | `Unexpected end of input — missing matching 'end'` |
| `test_parser_missing_end_if_before_statement` | `if true then\n show 1\nshow 2` | `Expected 'end', found 'show' … expected one of: 'end'` |
| `test_parser_missing_end_repeat` / `_end_function` | analogous | `Unexpected end of input — missing matching 'end'` |
| `test_parser_missing_then` | `if true\nend if` | `Expected 'then', found '\n' … expected one of: 'then'` |
| `test_parser_missing_to_in_set` | `set x 5` | `Expected 'to', found '5' … expected one of: 'to'` |
| `test_parser_missing_be_in_let` | `let x 5` | `Expected 'be', found '5' … expected one of: 'be'` |
| `test_parser_missing_equals_in_args` | `call f with a 1` | `Expected '=', found '1' … expected one of: '='` |
| `test_parser_missing_paren` | `show (1 plus 2` | `Expected ')', found '\n' … expected one of: ')'` |
| `test_parser_end_statement_extra_token` | `show 1 2` | `Expected end of line, found '2' at line 1, column 8` (no hint) |
| `test_parser_define_missing_name` | `define function\nend function` | `Expected a name, found '\n' … expected one of: 'a non-reserved identifier'` |
| `test_parser_alias_bad_word` | `define function f\nalso weird as g\nend function` | `Expected 'known' or 'called' after 'also' … expected one of: 'known', 'called'` |
| `test_parser_alias_missing_as` | `define function f\nalso called g\nend function` | `Expected 'as', found 'g' … expected one of: 'as'` (§13.2) |
| `test_parser_dangling_otherwise_top_level` | `otherwise` | `Unexpected 'otherwise' — no matching block opener at line 1, column 1` |
| `test_parser_dangling_end_top_level` | `end if` | `Unexpected 'end' — no matching block opener at line 1, column 1` |
| `test_parser_otherwise_inside_repeat` | `repeat while true\n otherwise\nend repeat` | `Unknown statement starting with 'otherwise' …` (hint list now includes `add`, `stop the loop`, `skip to the next item` — §7.1 row 7) |
| `test_parser_break_missing_the` | `stop loop` | `Expected 'the', found 'loop' … expected one of: 'the'` |
| `test_parser_continue_missing_item` | `skip to the next` | `Expected 'item', found '\n' … expected one of: 'item'` |
| `test_parser_add_missing_to` | `add 1 xs` | `Expected 'to', found 'xs' … expected one of: 'to'` |
| `test_parser_set_item_missing_of` | `set item 1 xs to 2` | `Expected 'of', found 'xs' … expected one of: 'of'` |
| `test_parser_for_each_missing_in` | `repeat for each x xs\nend repeat` | `Expected 'in', found 'xs' … expected one of: 'in'` |
| `test_parser_unknown_statement_hint_list` | `foo 1` | Exact hint list from §7.1 row 7 — assert verbatim so additions are deliberate |

### 4.3 Blocks: nesting, empty blocks, order

| Test | Source | Expected |
|---|---|---|
| `test_parser_empty_block_if` | `if true then\nend if` | `If([(True, Block([]))], None)`; runtime `.output == []` |
| `test_parser_empty_block_repeat` | `repeat while false\nend repeat` | `RepeatWhile(cond, Block([]))`; output `[]` |
| `test_parser_empty_block_foreach` | `repeat for each x in (a list of 1)\nend repeat` | `ForEach` with empty body; output `[]` |
| `test_parser_empty_block_function` | `define function f\nend function\nshow call f` | Call returns nothing → `["nothing"]` |
| `test_parser_empty_program` | `"\n# comment\n\n"` | `Program([])`; output `[]` |
| `test_parser_nested_if_in_repeat_in_function` | three-level fixture | `FunctionDef.body.stmts[0]` is `RepeatWhile`, whose body contains `If`, whose body contains `Show`; a `Return` inside crosses nested blocks |
| `test_parser_deeply_nested_parentheses` | `show (((1)))` | AST is just `Literal(1)` — no `Group` node (§10) |
| `test_parser_indentation_insignificant` | nested block at col 1 vs col 8 | Identical normalized AST |
| `test_parser_one_statement_per_line` | `show 1 show 2` | `Expected end of line, found 'show'` |

### 4.4 Names, labeled args, aliases

| Test | Source | Expected |
|---|---|---|
| `test_parser_reserved_word_as_assignment_target` | `set end to 5` | `Expected a name, found 'end' … a non-reserved identifier` |
| `test_parser_reserved_word_as_param` | `define function f taking if\nend function` | Same |
| `test_parser_reserved_word_as_alias` | `also known as end` | Same |
| `test_parser_reserved_word_in_expression` | `show print` | `Reserved word 'print' cannot be used here` |
| `test_parser_reserved_a_as_param` | `define function f taking a\nend function` | **Currently fails**: `Expected a name, found 'a'` — §13.10 |
| `test_parser_operator_word_as_identifier` | `set equals to 5\nshow equals` | Currently accepted (`equals` not in `RESERVED`) → `["5"]` — §13.3 |
| `test_parser_labeled_args_multiple` | `call f with a = 1, b = 2, c = 3` | args list in order; left-to-right eval in §6.5 |
| `test_parser_arg_label_reserved` | `call f with end = 1` | `Expected a name, found 'end' …` |
| `test_parser_arg_value_is_full_expr` | `call f with a = 1 plus 2, b = 3` | First value `Binary(ADD,1,2)`; comma terminates `parse_expr` |
| `test_parser_collection_literal_swallows_following_labeled_arg` | `call join with items = a list of "a", "b", separator = "-"` | Currently **fails** with `Expected end of line, found '='` because the list literal consumes `separator` as an element; parenthesized form works. Pin both in §13.11. |
| `test_parser_parenthesized_collection_as_arg` | `call join with items = (a list of "a", "b"), separator = "-"` | Valid; output `["a-b"]` |
| `test_parser_call_without_with` | `call f` | `Call("f", [])` |
| `test_parser_alias_both_spellings` | `also known as g` vs `also called as g` | Identical AST |

### 4.5 Collection / index / length expression forms

| Test | Source | Expected AST |
|---|---|---|
| `test_parser_list_literal` | `show a list of 1, 2, 3` | `Show(ListLiteral([1,2,3]))`; output `["[1, 2, 3]"]` |
| `test_parser_empty_list` | `show an empty list` | `ListLiteral([])`; output `["[]"]` |
| `test_parser_map_literal` | `set m to a map with "a" mapped to 1, "b" mapped to 2` | `MapLiteral([(Literal("a"), Literal(1)), …])` |
| `test_parser_empty_map` | `show an empty map` | `MapLiteral([])`; output `["{}"]` |
| `test_parser_map_duplicate_key` | `a map with "a" mapped to 1, "a" mapped to 2` | Parses both entries; runtime keeps last (Python rule) |
| `test_parser_index` | `show item 1 of xs` | `Index(Variable("xs"), Literal(1))` |
| `test_parser_index_key_is_expr` | `show item n plus 1 of xs` | key is `Binary(ADD,n,1)` — `parse_expr` stops at `of` (a RESERVED word no operator matches) |
| `test_parser_length` | `show the length of xs` | `Length(Variable("xs"))` |
| `test_parser_collection_synonyms_a_an` | `a list of 1` vs `an list of 1` | Identical AST (both accepted by `_parse_collection_literal`) |
| `test_parser_show_list_concat_rejected` | `show a list of 1, 2 plus a list of 3` | Parses as `ListLiteral([1, Binary(ADD,2,ListLiteral([3]))])` → runtime `Operator 'ADD' requires numbers … got 2 and [3]`; document as known limitation (§13.12) |

---

## 5. Category 3 — Canonicalization / synonym equivalence (`test_synonyms.py`)

The parser *is* the desugarer (`parser.py` docstring); equivalence compares `ast(src)` from §1.3 plus `.output`.

### 5.1 Operator phrase table (19 phrases → 12 canonical codes)

`test_syn_operator_phrases_table` iterates with `subTest(phrase=…)`: parse `set r to 6 <phrase> 3`, assert `Binary.op` and runtime output.

| Surface phrase | Code | `6 <phrase> 3` → output |
|---|---|---|
| `does not equal` | NE | `false` |
| `is not equal to` | NE | `false` |
| `is greater than` | GT | `true` |
| `is more than` | GT | `true` |
| `is less than` | LT | `false` |
| `is at least` | GE | `true` |
| `is at most` | LE | `false` |
| `is equal to` | EQ | `false` |
| `differs from` | NE | `true` |
| `divided by` | DIV | `2.0` |
| `to the power of` | POW | `216` |
| `equals` | EQ | `false` |
| `exceeds` | GT | `true` |
| `plus` | ADD | `9` |
| `minus` | SUB | `3` |
| `times` | MUL | `18` |
| `modulo` | MOD | `0` |
| `and` | AND | `3` (operand-returning) |
| `or` | OR | `6` (operand-returning) |

### 5.2 Equivalence families (assert `ast(a) == ast(b)` **and** `run(a) == run(b)`)

| Test | Variant A | Variant B | Canonical shape |
|---|---|---|---|
| `test_syn_output_words` | `show 1` | `display 1` / `print 1` | `Show(Literal(1))` |
| `test_syn_assignment_words` | `set x to 1` | `let x be 1` | `Set("x", 1)` |
| `test_syn_define_a_optional` | `define function f …` | `define a function f …` | `FunctionDef` |
| `test_syn_return_words` | `give back 1` | `return 1` | `Return(1)` |
| `test_syn_alias_words` | `also known as g, h` | `also called as g, h` | `aliases == ["g","h"]` |
| `test_syn_repeat_words` | `repeat while false …` | `while false …` | `RepeatWhile` |
| `test_syn_greater_than_set` | `is greater than` | `is more than` / `exceeds` | `Binary("GT", …)` |
| `test_syn_equal_set` | `equals` | `is equal to` | `Binary("EQ", …)` |
| `test_syn_not_equal_set` | `does not equal` | `is not equal to` / `differs from` | `Binary("NE", …)` |
| `test_syn_collection_article` | `a list of 1` | `an list of 1` | `ListLiteral([1])` |

### 5.3 Program-level equivalence

| Test | Source pair | Expected |
|---|---|---|
| `test_syn_hello_all_spellings` | `examples/hello.ll` vs. a fixture permuting every output/comparison synonym | identical `.output` (§12.1) and normalized AST |
| `test_syn_redundant_parentheses_invisible` | `show 1 plus 2` vs `show (1 plus 2)` | identical AST — no `Group` node |
| `test_syn_alias_calls_identical` | `greet` + aliases `say_hello, welcome`, called 3× with same arg | three identical outputs; `global_env.get(name) is` the same `Function` object |
| `test_syn_whitespace_comments_invisible` | compact vs. blank lines/comments/tabs/indent | identical AST and output |
| `test_syn_foreach_vs_manual_loop` | `repeat for each x in a list of 1, 2, 3\n show x\nend repeat` vs. explicit `set i to 0` + `repeat while i is less than 3` + `item i of xs` | identical output `["1","2","3"]` |

---

## 6. Category 4 — Evaluator semantics (`test_evaluator.py`, `test_collections.py`, `test_builtins.py`)

### 6.1 Left-to-right, no precedence, parentheses

| Test | Source | Expected output |
|---|---|---|
| `test_eval_no_precedence_plus_times` | `set x to 2 plus 3 times 4\nshow x` | `["20"]` |
| `test_eval_left_assoc_subtraction` | `show 10 minus 3 minus 2` | `["5"]` — not `9` |
| `test_eval_left_assoc_division` | `show 8 divided by 2 times 2` | `["8.0"]` |
| `test_eval_left_assoc_power_diverges_from_python` | `show 2 to the power of 3 to the power of 2` | `["64"]` — Python gives `512` |
| `test_eval_parentheses_override` | `show 2 plus (3 times 4)` | `["14"]` |
| `test_eval_nested_parentheses` | `show (1 plus 2) times (3 plus 4)` | `["21"]` |
| `test_eval_not_binds_tighter_than_comparison` | `show not 1 equals 2` | `["false"]` — `(not 1) equals 2`; Python gives `true`. Pin divergence. |
| `test_eval_all_operators_numeric` | separate shows for `5 plus 2`, `5 minus 4`, `3 times 4`, `4 divided by 2`, `7 modulo 3`, `2 to the power of 3` | `["7","1","12","2.0","1","8"]` |
| `test_eval_string_concatenation_only_for_plus` | `'show "a" plus "b"'` | `["ab"]` |
| `test_eval_zero_division` / `_modulo` | `show 1 divided by 0` / `show 7 modulo 0` | `Division by zero` / `Modulo by zero` |

### 6.2 Short-circuit `and`/`or`, operand-returning, truthiness

| Test | Source | Expected |
|---|---|---|
| `test_eval_or_returns_first_truthy_operand` | `show nothing or "default"\nshow 0 or 5\nshow 3 or 2` | `["default","5","3"]` |
| `test_eval_and_returns_last_operand_when_truthy` | `show 1 and 2\nshow nothing and 2` | `["2","nothing"]` |
| `test_eval_not_returns_bool` | `show not 0\nshow not ""\nshow not 1` | `["true","true","false"]` |
| `test_eval_or_short_circuits_second_operand` | `noisy` function that shows `"evaluated"`; `show false and call noisy with x = 1` and `show true or call noisy with x = 1` | no `"evaluated"` lines |
| `test_eval_and_evaluates_right_when_left_truthy` | `show nothing or call noisy with x = "fallback"` | `["evaluated","fallback"]` |
| `test_eval_left_operand_evaluated_once` | `show call noisy with x = 1 or 2` | `["evaluated","1"]` |
| `test_eval_truthiness_table` | `if <value> then show "T" otherwise show "F" end if` for `nothing`, `false`, `true`, `0`, `0.0`, `1`, `""`, `"x"`, `an empty list`, `an empty map`, `a list of 1` | `F,F,T,F,F,T,F,T,F,F,T` (empty containers are falsy) |
| `test_eval_if_conditions_lazy` | later branches call `noisy` but first is true | only `"T"`, no `"evaluated"` |

### 6.3 Strict types, no coercion

| Test | Source | Expected |
|---|---|---|
| `test_eval_no_string_number_coercion_add` | `'show "5" plus 5'` | `Operator 'ADD' requires numbers (or two texts for plus), got 5 and 5 at line 1, column 6` (both render as `5`; §13.9) |
| `test_eval_no_string_number_coercion_compare` | `'show "5" is greater than 4'` | `Comparison requires two numbers or two texts, got 5 and 4 …` |
| `test_eval_bool_not_number` | `show true plus 1` | `Operator 'ADD' requires numbers (or two texts for plus), got true and 1 …` |
| `test_eval_bool_bool_arithmetic_rejected` | `show true minus false` | `Operator 'SUB' requires numbers, got true and false …` |
| `test_eval_bool_equality_is_strict` | `show true equals 1`, `show false equals 0`, `show true equals true`, `show 1 equals 1.0` | `["false","false","true","true"]` |
| `test_eval_nothing_equality` | `show nothing equals nothing`, `… equals 0`, `… equals false` | `["true","false","false"]` |
| `test_eval_mixed_numeric_types_ok` | `show 1 plus 2.5`, `show 1 equals 1.0` | `["3.5","true"]` |
| `test_eval_string_order_is_unicode_codepoint` | `'show "a" is less than "b"'` | `["true"]` |
| `test_eval_list_plus_rejected` | `show a list of 1, 2 plus a list of 3` | `Operator 'ADD' requires numbers … got 2 and [3] at line 1, column 19` (§13.12) |

### 6.4 Loops and `require`

| Test | Source | Expected |
|---|---|---|
| `test_eval_repeat_counts` | core fixture | `["0","1","2"]` |
| `test_eval_while_alias_counts` | same with `while` | identical output |
| `test_eval_loop_condition_reevaluated` | `noisy` as loop condition with counter | marker each iteration (`while` re-evaluates; `for` does not — §6.6) |
| `test_eval_loop_never_enters` | `repeat while false … end repeat` | `[]` |
| `test_eval_loop_guard` | `run_bounded("repeat while true\nend repeat", 3)` | `Loop exceeded 3 iterations (possible infinite loop) at line 1, column 1`; 3 bodies run, 4th test raises |
| `test_eval_loop_guard_custom_high_no_error` | loop that runs exactly 3 times, `max_iterations=3` | no error; 3 lines |
| `test_eval_require_pass` | `'require 1 equals 1, "bad"\nshow "ok"'` | `["ok"]` |
| `test_eval_require_fail_default_message` | `require false` | `Requirement failed at line 1, column 1` |
| `test_eval_require_fail_custom_message` | `'require false, "boom"'` | `boom at line 1, column 1` |
| `test_eval_require_empty_message_falls_back` | `'require false, ""'` | `Requirement failed …` (`node.message or …`; §13.13) |

### 6.5 Functions, scope, aliases, recursion

| Test | Source | Expected |
|---|---|---|
| `test_eval_function_returns_value` | core `greet` fixture | `"Hello, Linus"` |
| `test_eval_fall_off_end_returns_nothing` | `define function f\n set x to 1\nend function\nshow call f` | `["nothing"]` |
| `test_eval_alias_identity` | greet + 3 aliases | all four `global_env.get(name) is` same object; identical outputs |
| `test_eval_alias_collision_local` | core test | `Name 'welcome' is already defined; a function alias cannot shadow it …` |
| `test_eval_duplicate_alias_in_same_list` | `also known as a, a` | same collision error at FunctionDef pos |
| `test_eval_function_redefinition_rejected` | define `f` twice | collision error — pin behavior (§13.4) |
| `test_eval_alias_may_shadow_outer_name` | global `x`, alias `x` | allowed (`has_local` only) |
| `test_eval_labeled_args_required` | core test | `Missing argument(s) for 'add': b …` |
| `test_eval_unknown_arg` | `call add with a = 1, q = 2` | `Unknown argument 'q' for function 'add'; expected: a, b …` |
| `test_eval_unknown_arg_no_params` | `call f with a = 1`, f takes none | `…expected: (none)` |
| `test_eval_duplicate_arg` | `call f with a = 1, a = 2` | `Argument 'a' supplied twice …` |
| `test_eval_args_evaluated_left_to_right_in_caller` | two `noisy` args with distinct markers | markers in source order, before body runs |
| `test_eval_callable_resolved_before_args` | `call missing with a = call noisy` | `Undefined name 'missing'`; no `"evaluated"` |
| `test_eval_not_a_function` | `set x to 1\ncall x` | `'x' is not a function …` |
| `test_eval_global_read_from_function` | global `g`, body `show g` | sees `g` |
| `test_eval_function_local_does_not_leak` | function sets local `x`; global `x` shown after | global unchanged |
| `test_eval_recursive_factorial` | factorial fixture | `["120"]` |
| `test_eval_call_result_as_operand` | `show 1 plus call f with x = 2` | Call is a `primary`; result participates in arithmetic |
| `test_eval_return_from_nested_block` | Return inside `if` inside function | returns immediately |
| `test_eval_top_level_return_escapes` | `give back 1` at top level | `ReturnSignal` escapes (§13.5); assert with `assertRaises(ReturnSignal)` |
| `test_eval_break_outside_loop_escapes` | `stop the loop` at top level | `BreakSignal` escapes (§13.5) |
| `test_eval_continue_outside_loop_escapes` | `skip to the next item` at top level | `ContinueSignal` escapes (§13.5) |
| `test_eval_break_inside_function_call_in_loop` | `stop the loop` inside a function called from a loop | `_call` converts to `RuntimeErrorLang("'stop the loop' used outside a loop")` — pin |

### 6.6 Collections and iteration (`test_collections.py`) — now implemented

| Test | Source | Expected |
|---|---|---|
| `test_coll_list_render` | `show a list of 1, 2, 3` | `["[1, 2, 3]"]` |
| `test_coll_map_render_insertion_order` | `set m to a map with "b" mapped to 1, "a" mapped to 2\nshow m` | `["{b: 1, a: 2}"]` — insertion order preserved (decision §9) |
| `test_coll_map_duplicate_key_last_wins` | `show a map with "a" mapped to 1, "a" mapped to 2` | `["{a: 2}"]` |
| `test_coll_empty_containers` | `show an empty list\nshow an empty map` | `["[]","{}"]` |
| `test_coll_index_list` | `show item 1 of (a list of 1, 2, 3)` | `["2"]` |
| `test_coll_index_text` | `show item 1 of "abc"` | `["b"]` |
| `test_coll_index_map` | `show item "a" of (a map with "a" mapped to 1)` | `["1"]` |
| `test_coll_index_out_of_range` | `show item 5 of a list of 1, 2` | `List index 5 is out of range at line 1, column 6` |
| `test_coll_index_text_out_of_range` | `show item 9 of "ab"` | `Text index 9 is out of range at line 1, column 6` |
| `test_coll_index_wrong_type` | `show item true of a list of 1, 2` | `List index must be a whole number at line 1, column 6` |
| `test_coll_index_missing_key` | `show item "z" of a map with "a" mapped to 1` | `Map has no key z at line 1, column 6` |
| `test_coll_index_unsupported` | `show item 0 of 5` | `Indexing requires a list, map, or text …` |
| `test_coll_length` | `show the length of a list of 1, 2, 3` | `["3"]`; also text and map |
| `test_coll_length_type_error` | `show the length of 5` | `Length requires a list, map, or text at line 1, column 6` |
| `test_coll_add_appends_and_returns_nothing` | `set xs to a list of 1, 2\nadd 3 to xs\nshow xs` | `["[1, 2, 3]"]`; `add` mutates in place, result not a value |
| `test_coll_add_wrong_target` | `add 1 to 5` | `'add ... to ...' requires a list at line 1, column 1` |
| `test_coll_set_item_list` | `set xs to a list of 1, 2\nset item 0 of xs to 9\nshow xs` | `["[9, 2]"]` |
| `test_coll_set_item_map` | `set m to an empty map\nset item "a" of m to 1\nshow m` | `["{a: 1}"]` |
| `test_coll_set_item_out_of_range` | `set item 5 of (a list of 1, 2) to 9` | `List index 5 is out of range at line 1, column 1` (pos = `set`) |
| `test_coll_set_item_unhashable_key` | `set item (a list of 1) of an empty map to 2` | `Map key must be a hashable value …` |
| `test_coll_map_literal_unhashable_key` | `a map with (a list of 1) mapped to 2` | `Map key must be a hashable value …` |
| `test_coll_aliasing_via_binding` | `set a to a list of 1\nset b to a\nadd 2 to a\nshow b` | `["[1, 2]"]` — names bind objects; mutation visible through alias (reference §0.1) |
| `test_coll_foreach_list` | `repeat for each x in a list of 1, 2, 3\n show x\nend repeat` | `["1","2","3"]` |
| `test_coll_foreach_map_yields_keys` | `repeat for each k in a map with "a" mapped to 1, "b" mapped to 2\n show k\nend repeat` | `["a","b"]` (Python rule) |
| `test_coll_foreach_text` | `repeat for each c in "ab"\n show c\nend repeat` | `["a","b"]` |
| `test_coll_foreach_iterable_evaluated_once` | `noisy` returns a list; used as iterable in a 3-item loop | marker printed exactly once — contrasts with `while` (§6.4) |
| `test_coll_foreach_snapshot_on_mutation` | `set xs to a list of 1, 2\nrepeat for each x in xs\n add 9 to xs\n show x\nend repeat\nshow xs` | `["1","2","[1, 2, 9, 9]"]` — implementation snapshots; **diverges from Python's live iterator** (§13.14) |
| `test_coll_foreach_break` | loop with `stop the loop` before `show x` | no iteration output; following statement still runs |
| `test_coll_foreach_continue` | loop with `skip to the next item` before `show x` | no output from body; following statement runs |
| `test_coll_break_in_while` | `repeat while true\n stop the loop\nend repeat\nshow "done"` | `["done"]` |
| `test_coll_loop_variable_rebound_and_kept` | after loop, `show x` | last item (not deleted) — Python rule |
| `test_coll_foreach_type_error` | `repeat for each x in 5\nend repeat` | `Iteration requires a list, map, or text at line 1, column 1` |

### 6.7 Builtins (`test_builtins.py`)

All errors from builtins are wrapped as `RuntimeErrorLang(f"In call to '{name}': {exc}", node.pos)`. Assert exact strings using the `call` position (column 6 in `show call …`).

| Builtin | Source | Expected |
|---|---|---|
| `to_text` | `show call to_text with value = (a list of 1, 2)` | `["[1, 2]"]` |
| `to_number` | `show call to_number with text = "42"` | `["42"]`; also `"3.5"` → `["3.5"]`; `"abc"` → `In call to 'to_number': 'abc' is not a number` |
| `is_number` / `is_text` / `is_list` / `is_map` | each with matching/mismatching `value` | `["true"]` / `["false"]` |
| `keys` | `show call keys with collection = (a map with "a" mapped to 1)` | `["[a]"]`; wrong type → `In call to 'keys': keys requires a map` |
| `values` | analogous | `["[1]"]` |
| `contains` | `show call contains with collection = (a list of 1, 2), value = 2` | `["true"]`; also works for text (substring) and map (keys) |
| `join` | `show call join with items = (a list of "a", "b"), separator = "-"` | `["a-b"]` |
| `split` | `show call split with text = "a,b", by = ","` | `["[a, b]"]`; empty delimiter → `In call to 'split': split delimiter cannot be empty` |
| `sort` | `show call sort with items = (a list of 3, 1, 2)` | `["[1, 2, 3]"]`; mixed types → `sort requires all numbers or all text` |
| `sum` | `show call sum with items = (a list of 1, 2, 3)` | `["6"]`; mixed → `In call to 'sum': sum requires a list of numbers at line 1, column 6` |
| `minimum` / `maximum` | list of numbers and list of text | correct extremes; empty list → `non-empty list` error; mixed → `cannot mix text and numbers` |
| `absolute` | `show call absolute with value = (0 minus 5)` | `["5"]`; text → `absolute requires a number` |
| `rounded` | `show call rounded with value = 1.6` | `["2.0"]`; with `places = 2`; non-int places → error |
| `read_file` / `write_file` | write then read a temp UTF-8 file | round-trip content; `write_file` returns nothing |
| `test_builtin_missing_arg` | `show call to_text` | `In call to 'to_text': missing argument 'value' at line 1, column 6` |
| `test_builtin_unknown_name` | `show call no_such_builtin with x = 1` | `Undefined name 'no_such_builtin' at line 1, column 6` |
| `test_builtin_registration` | `run_source("show 1").global_env` | all 20 names bound to `Builtin` instances; user `set` can shadow them (document) |

---

## 7. Category 5 — Diagnostics (`test_diagnostics.py`)

`assert_error(src, EXACT_STRING)` for every row. Keep a `diagnostics.ll` fixture with fixed line numbers. Regenerate this table from source if messages change.

### 7.1 Exact message catalog

| # | Source | Exact `str(exc)` |
|---|---|---|
| 1 | `show @` | `Unexpected character '@' at line 1, column 6` |
| 2 | `show "abc` | `Unterminated string literal at line 1, column 6` |
| 3 | `show "abc\` | `Unterminated escape sequence at line 1, column 6` |
| 4 | `set x 5` | `Expected 'to', found '5' at line 1, column 7\n  expected one of: 'to'` |
| 5 | `set end to 5` | `Expected a name, found 'end' at line 1, column 5\n  expected one of: 'a non-reserved identifier'` |
| 6 | `show print` | `Reserved word 'print' cannot be used here at line 1, column 6` |
| 7 | `foo 1` | `Unknown statement starting with 'foo' at line 1, column 1\n  expected one of: 'set', 'show', 'require', 'if', 'repeat', 'define', 'give back', 'call', 'add', 'stop the loop', 'skip to the next item'` |
| 8 | `show 1 2` | `Expected end of line, found '2' at line 1, column 8` (no hint) |
| 9 | `require true, 5` | `Expected a string message after ',' at line 1, column 15\n  expected one of: 'string'` |
| 10 | `if true\nend if` | `Expected 'then', found '\n' at line 1, column 8\n  expected one of: 'then'` |
| 11 | `if true then\n show 1` | `Unexpected end of input — missing matching 'end' at line 3, column 1` |
| 12 | `end if` | `Unexpected 'end' — no matching block opener at line 1, column 1` |
| 13 | `otherwise` | `Unexpected 'otherwise' — no matching block opener at line 1, column 1` |
| 14 | `define function f\nalso x as g\nend function` | `Expected 'known' or 'called' after 'also' at line 2, column 6\n  expected one of: 'known', 'called'` |
| 15 | `call f with a 1` | `Expected '=', found '1' at line 1, column 15\n  expected one of: '='` |
| 16 | `show ()` | `Unexpected token ')' in expression at line 1, column 7` |
| 17 | `show missing` | `Undefined name 'missing' at line 1, column 6` |
| 18 | `# comment\nshow ("x" minus 1)` | contains `line 2`; full string `Operator 'SUB' requires numbers, got x and 1 at line 2, column 7` |
| 19 | `show "a" minus "b"` | `Operator 'SUB' requires numbers, got a and b at line 1, column 6` |
| 20 | `show 5 divided by 0` | `Division by zero at line 1, column 6` |
| 21 | `show 5 modulo 0` | `Modulo by zero at line 1, column 6` |
| 22 | `require false, "boom"` | `boom at line 1, column 1` |
| 23 | `set x to 1\ncall x` | `'x' is not a function at line 2, column 1` |
| 24 | `call f with a = 1, a = 2` (f defined) | `Argument 'a' supplied twice at line L, column 1` |
| 25 | `call f with b = 1` (f taking a) | `Unknown argument 'b' for function 'f'; expected: a at line L, column 1` |
| 26 | `call f` (f taking a, b) | `Missing argument(s) for 'f': a, b at line L, column 1` |
| 27 | `show item 5 of a list of 1, 2` | `List index 5 is out of range at line 1, column 6` |
| 28 | `show item true of a list of 1, 2` | `List index must be a whole number at line 1, column 6` |
| 29 | `show item "z" of a map with "a" mapped to 1` | `Map has no key z at line 1, column 6` |
| 30 | `show the length of 5` | `Length requires a list, map, or text at line 1, column 6` |
| 31 | `add 1 to 5` | `'add ... to ...' requires a list at line 1, column 1` |
| 32 | `repeat for each x in 5\nend repeat` | `Iteration requires a list, map, or text at line 1, column 1` |
| 33 | `show call sum with items = a list of 1, "a"` | `In call to 'sum': sum requires a list of numbers at line 1, column 6` |
| 34 | `show 1 is less than 2 is less than 3` | `Comparison requires two numbers or two texts, got true and 3 at line 1, column 6` (chained comparison — decision §3) |

### 7.2 Diagnostic-quality assertions

| Test | Requirement |
|---|---|
| `test_diag_every_error_has_source_position` | For all 34 sources, `exc.pos` is not `None` and `str(exc)` contains `line ` and `column ` |
| `test_diag_expected_hints_present_for_token_errors` | Rows 4,5,6,7,9,10,14,15 contain `\n  expected one of: `; rows 8,16 do not |
| `test_diag_binary_error_points_at_left_operand` | `set x to 1\nshow x is greater than "a"` reports column of `x`, not operator |
| `test_diag_multiple_errors_fail_fast` | First error aborts; `.output` contains only lines emitted before the error |
| `test_diag_cli_renders_error` | `python run.py <bad file>` prints `ERROR: <rendered>` to stdout and exits 1 |

---

## 8. Category 6 — Grounded edge cases from `SEMANTIC-DECISIONS.md`

| Decision | Test | Concrete source / expected |
|---|---|---|
| §0 `require` vs `expect` | `test_edge_require_is_assertion` / `test_todo_expect_is_try` | `require false, "x"` fails loudly; `expect` currently unknown statement. When exceptions land, `expect` becomes try-block and `require` unchanged. |
| §1 no identity operator | `test_edge_no_bare_is_operator` | `show 1 is 1` → `Expected end of line, found 'is'` — English `is` is not equality/identity. |
| §1 `nothing` singleton | `test_todo_is_nothing_check` | When implemented: `x is nothing` true only for `nothing`. Currently `is` is not an operator (§13.7). |
| §2 operand-returning `and`/`or` | `test_eval_or_returns_first_truthy_operand` | `set s to ""\nshow s or "default"` → `["default"]` |
| §3 no chained comparisons | `test_edge_chained_comparison_typed_error` | §7.1 row 34: left-assoc build then strict-type error. Decide whether to reject at parse time with clearer hint. |
| §4 no loop-else | `test_todo_loop_else_absent` | `repeat while false\nend repeat\notherwise\n…` → `Unexpected 'otherwise' — no matching block opener` |
| §5 mutable defaults evaluated once | `test_todo_mutable_default_shared` | No default-parameter syntax today; assert `define function f taking a defaulting to 1` is a parse error. When defaults + collections land: shared list across calls, plus lint warning. |
| §6 closure late binding | `test_edge_closure_late_binding` | `make` defines `inner` capturing `n`, then `set n to 100` before `give back inner`; `set f to call make with n = 1`; `show call f with x = 5` → `["105"]` (call-time lookup). |
| §7 comprehension scope | `test_todo_comprehension_scope` | Not implemented; `a list of … for each …` currently unsupported → parse/runtime error. Activate when comprehensions land. |
| §8 eager vs lazy | `test_todo_on_demand_marker` | No generator expressions; `on demand` is not a keyword. Pin as unsupported; activate when implemented. |
| §9 dict order / set order | `test_coll_map_render_insertion_order` | Dict insertion order verified. No set type in v1 — tests must not assert set order. |
| §10 `/` vs floor | `test_edge_division_is_float` / `test_todo_floor_division` | `show 4 divided by 2` → `["2.0"]`. `whole-number quotient of … by …` not in vocabulary → unsupported today. |
| §11 forbid return in `always` | `test_todo_no_return_in_always` | Exceptions not implemented. |
| §12 class scope | `test_todo_class_scope_not_enclosing` | Classes not implemented. |
| Cross-cutting #1 bindings, not boxes | `test_coll_aliasing_via_binding` | `set b to a` then mutate visible via `b` (§6.6). |
| Cross-cutting #2 evaluation order | `test_edge_set_evaluates_rhs_first`, `test_eval_args_evaluated_left_to_right_in_caller`, `test_coll_add_evaluates_target_before_value` | `set` RHS before binding; call args left-to-right; `add` target before value. |
| Cross-cutting #3 truthiness | `test_eval_truthiness_table` | Includes empty containers (§6.2). |
| Cross-cutting #4 static scoping / dynamic resolution | `test_edge_closure_late_binding`, `test_eval_global_read_from_function` | Free vars resolved via closure env at call time. |
| Cross-cutting #5 iteration protocol, once | `test_coll_foreach_iterable_evaluated_once` | Iterable evaluated once; **snapshot** diverges from Python's live iterator (§13.14). |
| Cross-cutting #6 no coercion | §6.3 suite | — |
| `DESIGN.md` §11 aliases | `test_eval_alias_identity` | one implementation, many names |
| `DESIGN.md` §11 explicit delimiters | §4.2 delimiter suite | indentation never closes a block |

---

## 9. Category 7 — Planned features (write skipped placeholders now)

Everything below is currently unimplemented; check in with `@unittest.skip("Phase/feature: …")`. (Collections, iteration, and builtins were in this list in the first draft but are now implemented and tested in §6.6–6.7.)

### 9.1 Exceptions phase
- `test_todo_expect_catches`: `expect …` with `if a problem of kind E occurs, handle it by …`; handler order (specific before base); at most one handler runs.
- `test_todo_expect_else`: `if nothing went wrong, then …` runs only on clean completion; exception raised in it not caught by preceding handlers.
- `test_todo_always_runs`: `always, whether it worked or not, …` runs on normal path, handled error, and unhandled error.
- `test_todo_no_return_in_always` (§8 §11): `give back` / `stop the loop` / `skip to the next item` inside `always` rejected by parser/linter.
- `test_todo_fail_with`: `fail with E("msg")` raises with source loc; `require` stays distinct from `expect`.

### 9.2 Classes phase
- `test_todo_class_methods`, `test_todo_class_scope_not_enclosing`, `test_todo_mutable_class_attribute_shared`.

### 9.3 Modules / imports phase
- `test_todo_use_math_module`, `test_todo_import_snapshot` (reference §11: `take x from m` binds a snapshot), `test_todo_module_cached`.

### 9.4 Other deferred syntax
- Default parameters (§8 §5), comprehensions/generators (§8 §7–8), floor division (§8 §10), `is nothing` (§13.7), `expect` try-block (§8 §0).

---

## 10. Category 8 — Formatter round-trip tests (planned, `test_formatter_roundtrip.py`)

Define `format(ast) -> source` using primaries from `SEMANTIC-DECISIONS.md` §2 (`set`, `equals`, `show`, `define a function`, `give back`, `also called as`, `repeat while`, `repeat for each`). Invariants over a corpus covering every synonym and all 23 node types:

| Test | Invariant |
|---|---|
| `test_todo_format_is_idempotent` | `fmt1 = format(parse(src)); assertEqual(format(parse(fmt1)), fmt1)` |
| `test_todo_format_preserves_ast` | `normalize(parse(format(parse(src)))) == normalize(parse(src))` |
| `test_todo_format_preserves_semantics` | `run(format(parse(src))) == run(src)` for all corpus files |
| `test_todo_format_collapses_synonyms` | `format(parse('display "x"')) == format(parse('show "x"')) == format(parse('print "x"'))`; same for every family in §5.2 |
| `test_todo_format_keeps_explicit_delimiters` | output always contains `end if` / `end repeat` / `end function` |
| `test_todo_format_drops_redundant_parens` | `format(parse("show (((1)))"))` emits no parens and still runs to `["1"]` (no `Group` node) |
| `test_todo_format_keeps_left_to_right` | `show 2 plus 3 times 4` formatted without inserted parens |
| `test_todo_format_parenthesizes_collections_as_args` | formatter must emit `items = (a list of "a", "b")` to avoid the comma ambiguity (§13.11) |
| `test_todo_format_comment_policy` | Decision needed: lexer strips comments, so formatter cannot preserve them without AST changes |

Corpus: `fixtures/all_synonyms.ll`, `fixtures/nested_blocks.ll`, `fixtures/recursion.ll`, `fixtures/collections.ll`, `examples/hello.ll`.

---

## 11. Category 9 — Linter tests (planned, `test_linter.py`)

Static pass before execution; assert `LintDiagnostic(code, message, pos)` list.

| Test | Input | Expected finding |
|---|---|---|
| `test_todo_undefined_name_in_unexecuted_branch` | `if false then\n show missing\nend if` | `undefined-name: missing` at `Show` pos — today runtime emits nothing |
| `test_todo_undefined_name_in_function_body` | function body uses `nope` | `undefined-name`, resolved local → enclosing → global → builtin |
| `test_todo_no_false_positive_forward_function` | call `f` before its `define`, executed after | no finding (defs execute top-to-bottom; recursion allowed) |
| `test_todo_duplicate_definition_same_scope` | two `set x to …` in one block | `duplicate-definition: x` |
| `test_todo_duplicate_function_alias` | `also known as a, a` or alias == name | `duplicate-definition` |
| `test_todo_duplicate_argument_label` | `call f with a = 1, a = 2` | `duplicate-argument: a` at call site |
| `test_todo_unreachable_after_return` | `give back 1` then `show 2` in function | `unreachable-code` on `show 2` |
| `test_todo_unreachable_after_infinite_loop` | `repeat while true\nend repeat\nshow 1` | `unreachable-code` on `show 1` |
| `test_todo_break_outside_loop` | `stop the loop` at top level | `break-outside-loop` (currently leaks `BreakSignal`, §13.5) |
| `test_todo_reserved_word_identifier` | `set end to 5` | `reserved-word: end` |
| `test_todo_reserved_a_as_parameter` | `define function f taking a` | `reserved-word: a` with suggestion (§13.10) |
| `test_todo_collection_ambiguity` | list literal followed by another labeled arg without parens | `ambiguous-argument-list` hint (§13.11) |
| `test_todo_shadowing_warning` | parameter named same as global | warning — decide severity |
| `test_todo_no_false_positive_shadowing_sibling` | same name in two sibling functions | no duplicate finding |

---

## 12. Category 10 — End-to-end example tests (`test_end_to_end.py`)

### 12.1 `examples/hello.ll` (verified against current interpreter)

`test_e2e_hello_output`: output equals exactly:

```
["Hello, Ada", "recognised", "0", "1", "2",
 "Welcome, Grace", "Welcome, Linus", "all good"]
```

This exercises comments, blank lines, all three output synonyms, `equals`, `if/otherwise/end if`, `repeat while/end repeat`, string concatenation, function definition with aliases, labeled calls as expressions, and `require` with a custom message.

### 12.2 Other E2E programs

| Test | Program | Expected output |
|---|---|---|
| `test_e2e_factorial_recursion` | §6.5 factorial | `["120"]` |
| `test_e2e_collections_program` | list + map + `add` + `set item` + `repeat for each` + `stop the loop` fixture | pinned output from `fixtures/collections.ll` |
| `test_e2e_builtins_program` | `to_number`, `split`, `join`, `sort`, `sum`, `keys` fixture | pinned output |
| `test_e2e_all_synonyms_program` | every synonym family used at least once | same output as canonical-spelling twin (§5.3) |
| `test_e2e_crlf_file_via_run_file` | `fixtures/crlf_program.ll` | output identical to LF twin |
| `test_e2e_unicode_program` | `fixtures/unicode_identifiers.ll` | output preserves Unicode (§13.1) |
| `test_e2e_cli_success` | subprocess `python run.py examples/hello.ll` | exit 0; stdout contains exactly the 8 lines |
| `test_e2e_cli_bad_file` | subprocess with `show @` file | exit 1; stdout starts with `ERROR: ` and contains `Unexpected character '@' at line …` |
| `test_e2e_cli_usage` | subprocess `python run.py` | exit 2; stdout `usage: python run.py <file.ll>` |
| `test_e2e_error_stops_execution` | `show "before"\nshow @\nshow "after"` | `["before"]`; error contains line 2 |

---

## 13. Known spec/implementation mismatches to resolve (write a test for each outcome)

Found by reading the current code; tests pin current behavior **and** flag where a decision is needed. Resolve each, then flip the expectation.

1. **Unicode lexing vs grammar.** `lexer.py` uses Unicode-aware `isalpha()/isalnum()/isdigit()`; `GRAMMAR.md` says ASCII only. Decide to update grammar or restrict lexer. `isdigit()` also accepts superscript digits that `int()` rejects with bare `ValueError` (§3.4).
2. **`also called` vs `also called as`.** `GRAMMAR.md` line 29 omits `as`; `parser.py:247-252` always requires it. Fix grammar or parser (§4.2, §5.2).
3. **Operator words are not reserved.** `plus`, `equals`, `times`, `modulo`, `exceeds`, `differs`, `divided` etc. are absent from `RESERVED`, so `set equals to 5` works (§4.4). Decide whether to reserve all vocabulary.
4. **Function redefinition rejected** via `has_local` (§6.5). Decide intended vs. lint-warning.
5. **Control-flow signals leak at top level.** `ReturnSignal`, `BreakSignal`, `ContinueSignal` escape `Interpreter.run` when used outside their context (§6.5). CLI would print a traceback, not `ERROR:`. Must be caught/rendered as localized errors or statically rejected.
6. **`is nothing` documented but not implemented** (`SEMANTIC-DECISIONS.md` §1 vs. `OPERATOR_PHRASES`). Implement or remove from docs (§8).
7. **Docs lag the implementation.** `GRAMMAR.md` documents only the original statement/expression set; it does **not** include `add … to …`, `stop the loop`, `skip to the next item`, `repeat for each … in …`, list/map literals, `item … of …`, `the length of …`, or the builtin vocabulary, even though all are implemented/tested (§4.1, §4.5, §6.6–6.7). Update the grammar and synonym table promptly — prompt fidelity depends on it.
8. **Iteration phrasing mismatch.** `SEMANTIC-DECISIONS.md` §2 gives `for each x in xs` as primary, but the implemented surface is `repeat for each x in xs … end repeat`. Document the actual spelling and decide whether `for each` should be an alias.
9. **Poor/quirky diagnostics.** `"5" plus 5` renders both operands as `5`; unknown escapes silently drop the backslash; `require false, ""` falls back to the default message. Improve messages while keeping positions pinned.
10. **`a` is reserved, breaking parameters named `a`.** `define function f taking a` fails because `a` is in `RESERVED` (used by `define a function`, `a list of`). Same for `an`, `list`, `map`, `item`, `the`, `length`, etc. Decide: context-sensitive allowance for parameter names, or document and lint with a suggestion (§4.4).
11. **List literal comma swallows following labeled arguments.** `call join with items = a list of "a", "b", separator = "-"` fails at `=`; callers must parenthesize collection literals used as arguments (§4.4, §13.10 in linter). Decide: parenthesize in grammar/docs, or make `_parse_arg_list` stop at a label `WORD =` lookahead.
12. **No list arithmetic / concatenation.** `a list of 1, 2 plus a list of 3` parses into a nested element expression rather than adding lists, yielding a strict-type error (§4.5, §6.3). Decide whether to support `plus` for lists (Python `+`) or reject explicitly.
13. **"local for whole block" rule not implemented.** `Env.get` falls back to parent even when a name is assigned later in the function, so no `UnboundLocalError` analogue exists. `SEMANTIC-DECISIONS.md` cross-cutting #4 says it should. Implement (needs static binding analysis) or document divergence.
14. **`ForEach` snapshots the collection**, so mutation during iteration does not affect what is visited (§6.6) — diverges from Python's live iterator (reference §5/§12). This is a *deliberate safety choice* in the implementation; document it in `SEMANTIC-DECISIONS.md` and keep the test that pins it.
15. **`not` binds tighter than comparisons** (`_parse_unary` + flat expression loop) — diverges from Python's `not a == b == not (a==b)`. Pin in §6.1 and document in grammar.
16. **Builtins use underscore names** (`to_text`, `read_file`, …) while the rest of the surface is natural-language; decide whether to add English aliases (`as text`, `read the file at …`) and keep canonical names.
17. **No test runner config.** Add `python -m unittest discover -s tests -v` to README/Makefile/CI; tests must stay runnable from repo root (keep the `sys.path.insert(0, …/src)` pattern).

---

## 14. Exit criteria

- All 23 canonical node types have ≥1 direct test; all 19 operator phrases have equivalence + runtime tests; all 20 builtins have a test.
- Every exact-message row in §7.1 is asserted verbatim with line/column.
- All skipped `test_todo_*` tests are implemented alongside their feature or explicitly retired with a documented decision.
- `python -m unittest discover -s tests -v` is green; `examples/hello.ll` E2E output matches §12.1 exactly.
- Each §13 mismatch has a resolution recorded in `DESIGN.md`/`GRAMMAR.md`/`SEMANTIC-DECISIONS.md` and a corresponding test expectation updated.
