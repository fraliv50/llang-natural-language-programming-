# llang v1 Grammar (compact — fits in a prompt)

Indentation is decoration only. One statement per line. Reserved structural words cannot be identifiers (except `a`/`an`, which are valid identifiers when not followed by a collection keyword). The class-system words `class`, `method`, `ask`, and `this` are reserved; `this` is written explicitly as the first parameter of every method.

## Lexical
```
line     := statement NEWLINE
comment  := "#" ... NEWLINE          # ignored entirely
word     := [A-Za-z_][A-Za-z0-9_]*
number   := [0-9]+ ("." [0-9]+)?    # ASCII digits only
string   := '"' (escape | char)* '"'
escape   := "\" ("n" | "t" | '"' | "\")
punct    := "(" | ")" | "," | "="
```

## Program and statements
```
program      := (statement | blank | comment)*
statement    := set | show | require | add | set_item
              | if | repeat | stop | skip
              | function_def | return | call | fail | expect | use
               | class_def | method_def | ask_expr

set          := ("set" name "to" expr) | ("let" name "be" expr)
set_item     := "set item" expr "of" expr "to" expr
show         := ("show" | "display" | "print") expr
require      := "require" expr ["," string]
add          := "add" expr "to" expr

if           := "if" expr "then" NEWLINE block
                 ("otherwise if" expr "then" NEWLINE block)*
                 ["otherwise" NEWLINE block]
                 "end if"

repeat       := ("repeat while" expr | "while" expr) NEWLINE block "end repeat"
              | "repeat for each" name "in" expr NEWLINE block "end repeat"
stop         := "stop the loop"
skip         := "skip to the next item"

function_def := "define" ["a"] "function" name ["taking" name_list] NEWLINE
                 [alias_line] block "end function"
alias_line   := "also known as" name_list NEWLINE
              | "also called" ["as"] name_list NEWLINE
class_def    := "define" ["a"] "class" name ["taking" name_list] NEWLINE
                 method_def* "end class" NEWLINE
method_def   := "define" ["a"] "method" name "taking" name_list NEWLINE
                 block "end method" NEWLINE
               (* the first parameter of every method must be `this` *)
ask_expr     := "ask" expr "to" name ["with" arg_list]

return       := ("give back" expr) | ("return" expr)

call         := "call" call_name ["with" arg_list]
call_name    := word+             # stops at 'with' or EOL
qualified    := fn_name " from " module_name   # resolved through loaded modules
arg_list     := name "=" expr ("," name "=" expr)*

use          := "use the" ["foreign"] name "module" ["as" name]

fail         := "fail with" name ["," string]
expect       := "expect" NEWLINE block
                 ("if a problem of kind" name "occurs then" NEWLINE block)*
                 ["if nothing went wrong then" NEWLINE block]
                 ["always" NEWLINE block]
                 "end expect"

name_list    := name ("," name)*
block        := statement*
```

## Expressions — one precedence, left-associative, parentheses group
```
expr     := unary (op unary)*
unary    := ("not" unary) | postfix_expr
postfix_expr := primary (postfix)*
postfix  := "is empty" | "is not empty" | "is nothing"
          | "is a number" | "is text" | "is a list" | "is a map"
primary  := number | string | "true" | "false" | "nothing"
          | name | "(" expr ")" | call_expr | list_literal | map_literal
          | "item" expr "of" expr | "the length of" expr | ask_expr
call_expr := call
list_literal := ("a" | "an") "list of" expr ("," expr)* | ("a" | "an") "empty list"
map_literal  := ("a" | "an") "map with" expr "mapped to" expr
                ("," expr "mapped to" expr)* | ("a" | "an") "empty map"
```

## Canonical vocabulary (all synonyms normalize to these)
| Concept | Surface forms | Canonical |
|---|---|---|
| add / subtract / multiply | `plus`, `minus`, `times` | ADD / SUB / MUL |
| divide / floor divide / modulo / power | `divided by`, `floor divided by`, `modulo`, `to the power of` | DIV / FLOORDIV / MOD / POW |
| greater | `is greater than`, `is more than`, `exceeds` | GT |
| less / bounds | `is less than`, `is at most`, `is at least` | LT / LE / GE |
| equal / not equal | `equals`, `is equal to`; `does not equal`, `is not equal to`, `differs from` | EQ / NE |
| logic | `and`, `or`, `not` | AND / OR / NOT |
| assign | `set ... to ...`, `let ... be ...` | Set |
| output | `show`, `display`, `print` | Show |
| loop | `repeat while`, `while` | RepeatWhile |
| function | `define function`, `define a function` | FunctionDef |
| alias | `also known as`, `also called` | Alias |
| return | `give back`, `return` | Return |
| class | `define class`, `define a class` | ClassDef |
| method | `define method`, `define a method` | MethodDef |
| method call | `ask ... to ...` | MethodCall |

## Function aliases
Every alias binds to the *same* implementation. Calling any alias is identical.
```
define function greet taking name
also known as say_hello, welcome
    give back "Hello, " plus name
end function

call greet with name = "Ada"
call say_hello with name = "Ada"
```

## Builtins (phrase names and aliases)
`text of` / `to text` / `to_text`; `number from text` / `to number`; `number` / `is number`; `text` / `is text`; `list` / `is list`; `map` / `is map`; `keys of` / `keys`; `values of` / `values`; `contains` / `does contain`; `join` / `join items`; `split` / `split text`; `sort` / `sorted`; `sum` / `sum of`; `minimum` / `minimum of`; `maximum` / `maximum of`; `reverse of` / `reverse`; `absolute` / `absolute value of`; `rounded` / `rounded to places`; `uppercase of` / `uppercase`; `lowercase of` / `lowercase`; `trim`; `find in text`; `replace in text`; `insert into` (labels `collection`, `index`, `value`); `slice` (labels `collection`, optional `start`/`finish` — Python-style clipping, `nothing` means omitted); `apply` (labels `fn`, `args` — calls a function with positional values); `predict` (labels `model`, `features` — calls the model map's stored `predict` function with the model and features); `read text from` / `read_file`; `write text to` / `write_file`.

## Example
```
set greeting to "Hello"
display greeting plus ", Ada"

if name equals "Ada" then
    show "recognised"
otherwise
    show "unknown"
end if

set scores to a map with "Ada" mapped to 91
show item "Ada" of scores

expect
    show item "Nobody" of scores
if a problem occurs then
    show "missing"
end expect
```

## Classes and methods (minimal system)

```
define class Point taking x, y
define method move taking this, dx, dy
    set item "x" of this to (item "x" of this) plus dx
    set item "y" of this to (item "y" of this) plus dy
    give back this
end method
end class

set p to call new Point with x = 1, y = 2
show item "x" of p
ask p to move with dx = 3, dy = 4
show ask p to move with dx = 0, dy = 0    # a method may be an expression
```

`new NAME` is a call name like any other phrase name. Instances are values with
declared fields; `item "field" of instance` reads a field and
`set item "field" of instance to value` writes it. `ask` supplies `this`
automatically, so callers never pass it. Single inheritance, class variables,
name mangling, descriptors, and operator overloading are deliberately absent.
