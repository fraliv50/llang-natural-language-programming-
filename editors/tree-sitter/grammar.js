/**
 * tree-sitter grammar skeleton for llang v1.
 *
 * Derived from docs/GRAMMAR.md and docs/REFERENCE.md (section 8, compact EBNF).
 * Notes on the mapping:
 *   - Indentation is insignificant, so it lives in `extras`. NEWLINE is a real
 *     token because statements terminate at end of line.
 *   - Reserved words from src/llang/synonyms.py win over `identifier` via
 *     lexical precedence; multi-word phrases are explicit `seq` tokens.
 *   - Call names are a maximal run of words (including reserved words except
 *     `with`), which is why `call_word` below re-admits the reserved set.
 *   - `qualified` calls ("fn from module") are naturally covered because
 *     `from` and the module name are words inside `call_name`.
 */

// All reserved words except `with`, which terminates a call name.
const CALL_RESERVED = [
  'add', 'also', 'always', 'and', 'as', 'back', 'be', 'call', 'called',
  'define', 'display', 'each', 'empty', 'end', 'expect', 'fail', 'false',
  'from', 'function', 'give', 'if', 'in', 'item', 'kind', 'known', 'length',
  'let', 'list', 'loop', 'map', 'mapped', 'next', 'not', 'nothing', 'occurs',
  'of', 'or', 'otherwise', 'print', 'problem', 'remove', 'repeat', 'require',
  'return', 'set', 'show', 'skip', 'stop', 'taking', 'the', 'then', 'to',
  'true', 'went', 'while', 'wrong', 'use', 'module', 'foreign',
  'class', 'method', 'ask', 'this',
];

const WORD = /[A-Za-z_][A-Za-z0-9_]*/; // Unicode letters are accepted by the lexer.

module.exports = grammar({
  name: 'llang',

  extras: $ => [/[ \t\r]/, $.comment],

  rules: {
    source_file: $ => repeat(choice($._statement, $._newline)),

    // ---------------------------------------------------------------- lexical
    comment: $ => token(seq('#', /[^\n]*/)),
    _newline: $ => /\n/,
    identifier: $ => token(prec(-1, WORD)),
    name: $ => $.identifier,
    number: $ => token(seq(/[0-9]+/, optional(seq('.', /[0-9]+/)))),
    string: $ => token(seq(
      '"',
      repeat(choice(/[^"\\\n]/, seq('\\', /[nt"\\]/))),
      '"',
    )),

    // ----------------------------------------------------------- statements
    _statement: $ => choice(
      $.set_statement,
      $.set_item_statement,
      $.show_statement,
      $.require_statement,
      $.add_statement,
      $.use_statement,
      $.if_statement,
      $.repeat_statement,
      $.stop_statement,
      $.skip_statement,
      $.function_def,
      $.class_def,
      $.method_def,
      $.ask_statement,
      $.return_statement,
      $.call_statement,
      $.fail_statement,
      $.expect_statement,
    ),

    set_statement: $ => choice(
      seq('set', $.name, 'to', $._expression),
      seq('let', $.name, 'be', $._expression),
    ),

    set_item_statement: $ => seq(
      'set', 'item', $._expression, 'of', $._expression, 'to', $._expression,
    ),

    show_statement: $ => seq(choice('show', 'display', 'print'), $._expression),

    require_statement: $ => seq(
      'require', $._expression, optional(seq(',', $.string)),
    ),

    add_statement: $ => seq('add', $._expression, 'to', $._expression),

    // Modules are native (`use the math module`) or explicitly opt-in foreign
    // (`use the foreign json module as hostmath`).
    use_statement: $ => seq(
      'use', 'the', optional('foreign'), $.name, 'module',
      optional(seq('as', $.name)),
    ),

    if_statement: $ => seq(
      'if', $._expression, 'then', $._newline, $.block,
      repeat($.otherwise_if_clause),
      optional($.otherwise_clause),
      $.end_if,
    ),
    otherwise_if_clause: $ => seq(
      'otherwise', 'if', $._expression, 'then', $._newline, $.block,
    ),
    otherwise_clause: $ => seq('otherwise', $._newline, $.block),
    end_if: $ => seq('end', 'if'),

    repeat_statement: $ => choice(
      seq(
        choice(seq('repeat', 'while'), 'while'),
        $._expression, $._newline, $.block, $.end_repeat,
      ),
      seq(
        'repeat', 'for', 'each', $.name, 'in', $._expression,
        $._newline, $.block, $.end_repeat,
      ),
    ),
    end_repeat: $ => seq('end', 'repeat'),

    stop_statement: $ => seq('stop', 'the', 'loop'),
    skip_statement: $ => seq('skip', 'to', 'the', 'next', 'item'),

    function_def: $ => seq(
      'define', optional('a'), 'function', $.name,
      optional(seq('taking', $.name_list)),
      $._newline,
      optional($.alias_line),
      $.block,
      $.end_function,
    ),
    alias_line: $ => seq(
      'also',
      choice(seq('known', 'as'), seq('called', optional('as'))),
      $.name_list,
      $._newline,
    ),
    end_function: $ => seq('end', 'function'),

    class_def: $ => seq(
      'define', optional('a'), 'class', $.name,
      optional(seq('taking', $.name_list)),
      $._newline,
      repeat($.method_def),
      $.end_class,
    ),
    end_class: $ => seq('end', 'class'),

    method_def: $ => seq(
      'define', optional('a'), 'method', $.name,
      'taking', $.name_list,
      $._newline,
      $.block,
      $.end_method,
    ),
    end_method: $ => seq('end', 'method'),

    ask_statement: $ => seq(
      'ask', $._expression, 'to', $.name,
      optional(seq('with', $.argument_list)),
    ),

    return_statement: $ => seq(choice(seq('give', 'back'), 'return'), $._expression),

    call_statement: $ => $.call,

    fail_statement: $ => seq(
      'fail', 'with', $.name, optional(seq(',', $.string)),
    ),

    expect_statement: $ => seq(
      'expect', $._newline, $.block,
      repeat($.problem_handler),
      optional($.nothing_went_wrong_clause),
      optional($.always_clause),
      $.end_expect,
    ),
    problem_handler: $ => seq(
      'if', 'a', 'problem',
      optional(seq('of', 'kind', $.name)),
      'occurs', 'then', $._newline, $.block,
    ),
    nothing_went_wrong_clause: $ => seq(
      'if', 'nothing', 'went', 'wrong', 'then', $._newline, $.block,
    ),
    always_clause: $ => seq('always', $._newline, $.block),
    end_expect: $ => seq('end', 'expect'),

    block: $ => repeat(choice($._statement, $._newline)),
    name_list: $ => seq($.name, repeat(seq(',', $.name))),

    // ----------------------------------------------------------- expressions
    // One precedence level, left-associative: expr ::= unary (op unary)*.
    _expression: $ => choice($.unary, $.binary_expression),
    binary_expression: $ => seq(
      field('left', $._expression),
      field('operator', $.operator),
      field('right', $.unary),
    ),

    unary: $ => choice($.not_expression, $._postfix),
    not_expression: $ => seq('not', $.unary),
    _postfix: $ => seq($._primary, repeat($.predicate)),

    _primary: $ => choice(
      $.number,
      $.string,
      $.boolean_literal,
      $.nothing_literal,
      $.identifier,
      $.parenthesized_expression,
      $.call,
      $.list_literal,
      $.map_literal,
      $.item_expression,
      $.length_expression,
    ),

    boolean_literal: $ => choice('true', 'false'),
    nothing_literal: $ => 'nothing',
    parenthesized_expression: $ => seq('(', $._expression, ')'),

    list_literal: $ => choice(
      seq(choice('a', 'an'), 'list', 'of', $.expression_list),
      seq(choice('a', 'an'), 'empty', 'list'),
    ),
    expression_list: $ => seq($._expression, repeat(seq(',', $._expression))),

    map_literal: $ => choice(
      seq(choice('a', 'an'), 'map', 'with', $.map_entry, repeat(seq(',', $.map_entry))),
      seq(choice('a', 'an'), 'empty', 'map'),
    ),
    map_entry: $ => seq($._expression, 'mapped', 'to', $._expression),

    item_expression: $ => seq('item', $._expression, 'of', $._expression),
    length_expression: $ => seq('the', 'length', 'of', $._expression),

    // A bare `call` is a statement; nested in an expression it is a primary.
    call: $ => seq('call', $.call_name, optional(seq('with', $.arg_list))),
    call_word: $ => choice($.identifier, ...CALL_RESERVED),
    call_name: $ => repeat1($.call_word),
    arg_list: $ => seq($.argument, repeat(seq(',', $.argument))),
    argument: $ => seq($.name, '=', $._expression),

    // --------------------------------------------------------------- phrases
    operator: $ => choice(
      seq('does', 'not', 'equal'),
      seq('is', 'not', 'equal', 'to'),
      seq('is', 'greater', 'than'),
      seq('is', 'more', 'than'),
      seq('is', 'less', 'than'),
      seq('is', 'at', 'least'),
      seq('is', 'at', 'most'),
      seq('is', 'equal', 'to'),
      seq('differs', 'from'),
      seq('floor', 'divided', 'by'),
      seq('divided', 'by'),
      seq('to', 'the', 'power', 'of'),
      'equals', 'exceeds', 'plus', 'minus', 'times', 'modulo', 'and', 'or',
    ),

    predicate: $ => choice(
      seq('is', 'empty'),
      seq('is', 'not', 'empty'),
      seq('is', 'nothing'),
      seq('is', 'a', 'number'),
      seq('is', 'text'),
      seq('is', 'a', 'list'),
      seq('is', 'a', 'map'),
    ),
  },
});
