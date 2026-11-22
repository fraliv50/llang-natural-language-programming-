# llang Tutorial — From Zero to Confident

llang is a small programming language that reads like structured English and behaves like Python. This tutorial is written for two readers at once:

- a **newcomer** who wants to learn by copying runnable examples, and
- an **AI code generator** that needs exact spellings, exact outputs, and exact error messages.

Everything below has been checked against the current interpreter (`src/llang/parser.py` and `src/llang/interpreter.py`). Copy the examples literally. llang's vocabulary is **closed**: if a word is not listed here, it is not part of the language yet.

### How to run an example

From the workspace root (`D:\natural language code`):

```sh
python run.py examples/hello.ll
```

Save any example into a file (for example `try.ll`) and run `python run.py try.ll`. Every chapter shows the **exact** output you should see.

Two ground rules before we start:

1. **One statement per line.** Indentation is decoration only; blocks are closed with explicit words such as `end if`, `end repeat`, and `end function`.
2. **Errors are part of the language.** Each error carries a source location (`line X, column Y`) and often lists the tokens that were expected. The error blocks in this tutorial show exactly what `python run.py` prints (its `ERROR: ` prefix included).

---

## Chapter 1 — Hello and output

**Concept.** The simplest llang statement prints a value. Three interchangeable words do the same job: `show`, `display`, and `print`. They all become one canonical "show this" action, so the choice is purely about readability. Text is written with **double quotes**; numbers are written bare.

### Example

```llang
show "Hello, world!"
display "Same message, different word."
print 42
```

**Expected output:**

```text
Hello, world!
Same message, different word.
42
```

Each output statement produces exactly one line. `show`, `display`, and `print` are perfect synonyms — the tests prove all three produce the same output.

### Common mistake

Using Python/Shell-style single quotes:

```llang-bad
show 'hello'
```

The interpreter stops with:

```text
ERROR: Unexpected character "'" at line 1, column 6
```

The lexer only recognises `"..."` for text. The other escape sequences that work inside strings are `\n`, `\t`, `\"`, and `\\`.

---

## Chapter 2 — Variables

**Concept.** A variable is a name bound to a value. Use `set name to value` or the synonym `let name be value`. Assign again to replace the value; there is no separate declaration step, and types are dynamic. Names are case-sensitive and may not be reserved words (for example `end`, `set`, `if`, `a`, `add`, `list`).

### Example

```llang
set greeting to "Hello"
let person be "Ada"
set count to 2
set count to count plus 1
show greeting
show person
show count
```

**Expected output:**

```text
Hello
Ada
3
```

`set count to count plus 1` means "evaluate the right side, then bind the result to `count`". The old value of `count` is used in the expression before it is replaced.

### Common mistake

Reading a name that was never bound:

```llang-bad
show total
```

The interpreter stops with:

```text
ERROR: Undefined name 'total' at line 1, column 6
```

This is a runtime error with a precise location, so a typo is never silently treated as `0` or empty text. A reserved word used as a name is caught even earlier:

```llang-bad
set end to 5
```

```text
ERROR: Expected a name, found 'end' at line 1, column 5
  expected one of: 'a non-reserved identifier'
```

---

## Chapter 3 — Expressions, left-to-right evaluation, and parentheses

**Concept.** Arithmetic uses English operator phrases: `plus`, `minus`, `times`, `divided by`, `modulo`, and `to the power of`. There is **no precedence table**: every operator has the same precedence and evaluation is strictly **left to right**. Parentheses `(` `)` group subexpressions and are the only way to override that order. Subtraction is written `0 minus 5` for a negative number — there is no unary `-` sign in v1.

### Example

```llang
set plain to 2 plus 3 times 4
show plain
set grouped to 2 plus (3 times 4)
show grouped
show "llang" plus " rules"
show 7 divided by 2
show 7 modulo 3
show 2 to the power of 3
show 0 minus 5
```

**Expected output:**

```text
20
14
llang rules
3.5
1
8
-5
```

The first two lines are the heart of this chapter:

- `2 plus 3 times 4` is read as `(2 plus 3) times 4` → `5 times 4` → `20`.
- `2 plus (3 times 4)` is read as `2 plus 12` → `14`.

`plus` also joins two texts ("llang rules"). `divided by` always produces a decimal (`7 divided by 2` is `3.5`). Mixing incompatible types is a loud error: there is **no implicit conversion** (`"5" plus 5` does not mean `10`).

### Common mistake

Expecting text to be converted to a number:

```llang-bad
show "5" plus 5
```

The interpreter stops with:

```text
ERROR: Operator 'ADD' requires numbers (or two texts for plus), got 5 and 5 at line 1, column 6
```

Two other frequently seen arithmetic errors:

```text
ERROR: Division by zero at line 1, column 6
ERROR: Modulo by zero at line 1, column 6
```

---

## Chapter 4 — Comparison and logic

**Concept.** Comparisons also use English phrases. `true`, `false`, and `nothing` are built-in literal values; comparisons produce `true` or `false`.

| Meaning | Spellings that work |
|---|---|
| greater than | `is greater than`, `is more than`, `exceeds` |
| less than | `is less than` |
| at least | `is at least` |
| at most | `is at most` |
| equal | `equals`, `is equal to` |
| not equal | `does not equal`, `is not equal to`, `differs from` |

`and`, `or`, and `not` combine conditions. Two Python-like details matter:

- `and`/`or` **short-circuit** and **return an operand**, not necessarily `true`/`false`. `0 or "fallback"` gives `"fallback"`; `"kept" and "second"` gives `"second"`.
- `not` is the only unary operator: `not condition`.

Because every operator has the same precedence, **parenthesise each comparison** when combining comparisons with `and`/`or`. Writing `x is greater than 0 and x is at most 10` would group as `((x is greater than 0) and x) is at most 10`. Chained comparisons such as `0 < x < 10` do not exist in v1.

### Example

```llang
set temperature to 24
show temperature is greater than 20
show temperature exceeds 20
show temperature is at least 24
show temperature is at most 30
show temperature equals 24
show temperature does not equal 25
show (temperature is greater than 20) and (temperature is at most 30)
show not (temperature equals 25)
show 0 or "fallback"
show "kept" and "second"
```

**Expected output:**

```text
true
true
true
true
true
true
true
true
fallback
second
```

`exceeds` is a synonym of `is greater than`, so lines 2 and 3 agree. The two parentheses examples show the recommended way to express a range and a negation.

### Common mistake

Writing English "is" where llang requires a full equality phrase:

```llang-bad
set score to 5
if score is 5 then
    show "five"
end if
```

The interpreter stops with:

```text
ERROR: Expected 'then', found 'is' at line 2, column 10
  expected one of: 'then'
```

`is` alone is not an operator. Use `equals` or `is equal to`. Comparison also refuses mixed types: `show 5 is greater than "x"` produces `Comparison requires two numbers or two texts, got 5 and x at line 1, column 6`.

---

## Chapter 5 — Decisions: `if`, `otherwise if`, `otherwise`

**Concept.** An `if` block starts with `if condition then`, ends with `end if`, and may contain any number of `otherwise if condition then` branches plus one final `otherwise`. Branches are checked top to bottom; the first true one runs, and the rest are skipped. The final `otherwise` is optional.

### Example

```llang
set score to 72
if score is at least 90 then
    show "A"
otherwise if score is at least 70 then
    show "B"
otherwise
    show "keep going"
end if
```

**Expected output:**

```text
B
```

`score is at least 90` is false, `score is at least 70` is true, so `"B"` is shown. Indentation makes this easy to read, but the interpreter is relying on the word `end if`, not on the spaces.

### Common mistake

Forgetting the closing delimiter:

```llang-bad
set score to 72
if score is at least 70 then
    show "B"
```

The interpreter stops with:

```text
ERROR: Unexpected end of input — missing matching 'end' at line 3, column 13
```

A stray closer is diagnosed just as clearly: `otherwise` with no matching `if` gives `Unexpected 'otherwise' — no matching block opener at line 1, column 1`.

---

## Chapter 6 — Repetition: `repeat while`

**Concept.** A `repeat while` loop re-evaluates its condition before each pass and runs its body while the condition is truthy. `while condition` is an accepted synonym, but **both forms close with `end repeat`**. The loop body must change something the condition depends on, or the interpreter stops it with an iteration-limit error.

### Example

```llang
set counter to 0
repeat while counter is less than 3
    show counter
    set counter to counter plus 1
end repeat
show "done"
```

**Expected output:**

```text
0
1
2
done
```

The condition is checked at the top: when `counter` reaches `3`, the loop ends and execution continues after `end repeat`.

### Common mistake

Closing a `while` loop with `end while`:

```llang-bad
set counter to 0
while counter is less than 3
    show counter
    set counter to counter plus 1
end while
```

The interpreter stops with:

```text
ERROR: Expected 'repeat', found 'while' at line 5, column 5
  expected one of: 'repeat'
```

If the condition never becomes false, the guard trips after 100000 iterations with `Loop exceeded 100000 iterations (possible infinite loop) at line 1, column 1`.

---

## Chapter 7 — Functions, aliases, and labeled arguments

**Concept.** Define a function with `define function name taking p1, p2` (or `define a function ...`). The body runs in its own scope and sends a value back with `give back value` (or `return value`). A function may declare extra names on an `also known as` line; every alias calls the *same* implementation. Calls are always labeled: `call name with label = value`. Labels are required, can be written in any order, and positional arguments do not exist in v1.

Use `call name with ...` as a statement when you only want the side effect. Use `show call name with ...` when you want to print the returned value.

### Example

```llang
define function greet taking name
also known as say_hello, welcome
    give back "Welcome, " plus name
end function

call greet with name = "Ada"
call say_hello with name = "Grace"
show call welcome with name = "Linus"

define function sum_two taking first, second
    give back first plus second
end function
show call sum_two with first = 10, second = 5
```

**Expected output:**

```text
Welcome, Linus
15
```

The two bare `call` statements return values that are simply discarded, so they print nothing. `show call welcome ...` prints the result. All three names — `greet`, `say_hello`, and `welcome` — are aliases of one function. (`also called as ...` is also accepted; `also known as ...` is the canonical spelling.) A function without `give back` returns `nothing`.

### Common mistake

Omitting a labeled argument:

```llang-bad
define function sum_two taking first, second
    give back first plus second
end function
show call sum_two with first = 10
```

The interpreter stops with:

```text
ERROR: Missing argument(s) for 'sum_two': second at line 4, column 6
```

Related diagnostics you may see: `Unknown argument 'third' for function 'sum_two'; expected: first, second`, `Argument 'first' supplied twice`, and, if an alias collides with an existing name, `Name 'welcome' is already defined; a function alias cannot shadow it at line 2, column 1`.

---

## Chapter 8 — Assertions: `require`

**Concept.** `require condition` is a programmer-written runtime check. If the condition is truthy, nothing is printed and the program continues. If it is false, the program stops immediately with an error. Add a comma and a **double-quoted** string to give a custom message: `require condition, "message"`. Without one, the message is `Requirement failed`.

### Example

```llang
set age to 21
require age is at least 18, "age must be 18 or more"
show "entry allowed"
```

**Expected output:**

```text
entry allowed
```

The requirement passes silently; the only output comes from `show`. Assertions are ideal for checking assumptions before a calculation or a function body relies on them.

### Common mistake

Letting a requirement fail:

```llang-bad
set age to 12
require age is at least 18, "age must be 18 or more"
```

The interpreter stops with:

```text
ERROR: age must be 18 or more at line 2, column 1
```

Note the location points at the `require` statement itself. The message must be a string literal: `require false, 5` produces `Expected a string message after ',' at line 1, column 16` with the hint `expected one of: 'string'`.

---

## Chapter 9 — Comments

**Concept.** A `#` starts a comment that runs to the end of the line. Comments can occupy a whole line or follow a statement, and the lexer discards them entirely — they never affect output or scope. There are no `//` or `--` comments.

### Example

```llang
# Count down from three.
set countdown to 3
repeat while countdown is greater than 0
    show countdown # show the current value
    set countdown to countdown minus 1
end repeat
# finished
```

**Expected output:**

```text
3
2
1
```

The inline comment after `show countdown` belongs to that line only; the next line is still executed.

### Common mistake

Using a comment marker from another language:

```llang-bad
// this is not a comment
show "hi"
```

The interpreter stops with:

```text
ERROR: Unexpected character '/' at line 1, column 1
```

A `--` marker fails the same way with `Unexpected character '-'`. Only `#` is recognised.

---

## Chapter 10 — Why llang looks this way (design philosophy)

**Concept.** llang is *structured pseudocode*. Its surface is flexible English; its meaning is a tiny, unambiguous Python-founded core. Every synonym (`show`/`display`/`print`, `set ... to`/`let ... be`, `equals`/`is equal to`) is desugared to exactly one canonical node before execution. A synonym can never change behaviour. This matters especially for an AI writer: many natural phrasings are valid, but there is only one semantics per idea.

Other deliberate choices:

- **Explicit delimiters** (`end if`, `end repeat`, `end function`) instead of significant indentation, because prompts and diffs mangle whitespace.
- **One precedence, left to right**, with parentheses for grouping — no precedence table to memorise or mis-remember.
- **Closed vocabulary** — no user-defined syntax, macros, or operator overloading in v1.
- **Python semantics underneath** — truthiness, short-circuit `and`/`or`, operand-returning logic, and dynamic names — with documented divergences (no implicit coercion, no chained comparisons, no loop-else).
- **Localized, actionable errors** — typos and type mismatches stop loudly with a line and column, so a human or model can self-correct.

### Example

```llang
set greeting to "Hi"
show greeting
display greeting
print greeting
```

**Expected output:**

```text
Hi
Hi
Hi
```

Three surface spellings, one canonical action. The formatter could rewrite all three lines to `show greeting` without changing the program's meaning at all.

### Common mistake

Carrying Python's symbolic operators into llang:

```llang-bad
set value to 5
if value == 5 then
    show "yes"
end if
```

The interpreter stops with:

```text
ERROR: Expected 'then', found '=' at line 2, column 10
  expected one of: 'then'
```

Symbols such as `==`, `!=`, `+`, and `=` (outside labeled arguments) are not operators in llang. Write `equals`, `does not equal`, `plus`, and `set ... to`. A plain `=` is only used between a label and its value in a call, as in `with name = "Ada"`.

---

## Cheat sheet — every construct in this tutorial

### Statements

| Construct | Syntax | Notes |
|---|---|---|
| Output | `show expr`, `display expr`, `print expr` | One line per statement |
| Assign | `set name to expr`, `let name be expr` | Reassign freely; names are case-sensitive |
| Assert | `require expr`, `require expr, "message"` | Fails loudly with location |
| Conditional | `if expr then` … [`otherwise if expr then` …]\* [`otherwise` …] `end if` | First true branch wins |
| While loop | `repeat while expr` … `end repeat`, or `while expr` … `end repeat` | Both openers use `end repeat` |
| Function | `define function name [taking p1, p2]` … `end function` (also `define a function ...`) | Body has its own scope |
| Aliases | `also known as n1, n2` (`also called as n1, n2`) | Directly after the `define` line |
| Return | `give back expr`, `return expr` | Missing return yields `nothing` |
| Call (discard) | `call name [with label = expr, ...]` | Labels are required |
| Call (use value) | `show call name [with label = expr, ...]` | Can appear in any expression |
| Comment | `# ... to end of line` | Whole-line or trailing |

### Expressions and literals

| Kind | Forms |
|---|---|
| Number | `42`, `3.5` (negative: `0 minus 5`) |
| Text | `"..."` with escapes `\n`, `\t`, `\"`, `\\` |
| Boolean / empty | `true`, `false`, `nothing` |
| Name | Any non-reserved identifier; resolves local → enclosing → global |
| Grouping | `(expr)` |
| Arithmetic | `plus`, `minus`, `times`, `divided by`, `modulo`, `to the power of` |
| Comparison | `is greater than` / `is more than` / `exceeds`, `is less than`, `is at least`, `is at most`, `equals` / `is equal to`, `does not equal` / `is not equal to` / `differs from` |
| Logic | `and`, `or`, `not` (operand-returning, short-circuit) |

### Rules to memorise

- One statement per line; indentation is cosmetic; blocks need their `end ...` word.
- All operators have equal precedence and associate left to right; use parentheses.
- No implicit type conversion. No symbolic operators. No chained comparisons.
- Reserved words cannot be variable names: `set`, `let`, `to`, `be`, `show`, `display`, `print`, `require`, `if`, `then`, `otherwise`, `end`, `repeat`, `while`, `define`, `a`, `function`, `taking`, `also`, `known`, `called`, `as`, `give`, `back`, `return`, `call`, `with`, `not`, `and`, `or`, `true`, `false`, `nothing`, plus the collection words `an`, `list`, `map`, `empty`, `mapped`, `of`, `item`, `the`, `length`, `each`, `in`, `add`, `remove`, `from`, `stop`, `next`, `loop`, `skip`.
- Error format: `message at line X, column Y`, optionally followed by `expected one of: ...`.

This tutorial covers the core constructs above. The authoritative, always-current grammar — including collection and iteration forms still being added to the interpreter — lives in `docs/GRAMMAR.md`; the semantics behind it are recorded in `docs/DESIGN.md` and `docs/SEMANTIC-DECISIONS.md`.
