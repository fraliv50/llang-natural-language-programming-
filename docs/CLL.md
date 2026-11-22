# c-ll — a checked C-like surface for llang

c-ll ("see-ell") is the second language surface of the llang family. It shares
the family's design rules — one precedence level, left-to-right evaluation,
explicit block closers, a closed vocabulary, and one canonical AST per
construct — but adds the C-like semantics the English surface deliberately
omits: static types, addressable objects, layouts, call-by-value, and a defined
boundary around undefined behaviour.

The English surface is **not modified**: c-ll lives entirely in
`src/llang/cll/`, and all 368 pre-existing tests still pass.

> Authority for the copied semantics: ISO/IEC 9899:2011 (C11). The full design
> rationale, source citations, and tier mapping are in
> [`research/c-like-surface-design.md`](research/c-like-surface-design.md).

---

## 1. The v1 subset (exact)

| Area | In v1 | Not in v1 |
|---|---|---|
| Types | `int` (signed 32-bit), `float` (binary64, i.e. C `double`), `void` (return only), `pointer to T`, `array[N] of T`, `struct T` | `char`, `short`, `long`, unsigned, `_Bool`, complex, unions, bit-fields, VLA, `void*` |
| Declarations | `let NAME as TYPE be EXPR` — **initializer mandatory** | uninitialized objects |
| Assignment | `set LVALUE to EXPR` | assignment inside expressions, `++`/`--`, comma operator |
| Arithmetic | `plus minus times divided by remainder` | bitwise/shift operators, exponentiation |
| Comparison | `equals does not equal is less than is at most is greater than is at least` | chained comparisons |
| Logic | `and or not` (operands are scalars, result `int` 0/1, short-circuit) | `&&`/`||` spelling, operand-returning semantics |
| Conversion | explicit `cast EXPR as TYPE` (int ↔ float only) + the null-pointer literal | implicit int/float mixing, pointer casts, integer↔pointer punning |
| Addresses | `address of`, `value at`, `item I of`, `member F of`, `member F via`, `null pointer`, bounds-checked pointer `plus`/`minus` | raw bytes, arbitrary pointer casts, pointer/integer arithmetic |
| Heap | `call allocate with type = T, count = N` (zero-filled), `call free with pointer = P` | `malloc`/`free` from libc, `realloc`, user allocators |
| Aggregates | `define struct T with F as TYPE, …` / `end struct`; fixed typed fields, self-reference via pointer | anonymous members, flexible arrays, by-value recursion |
| Functions | top-level typed functions, positional call-by-value arguments, recursion, `give back` | nested functions, function pointers, variadics, default arguments |
| Control flow | `if` / `otherwise if` / `otherwise` / `end if`, `repeat while`, `repeat for NAME from A below B [by S]`, `stop the loop`, `skip to the next item` | `goto`, `switch`, `do`, `?:` |
| Output | `show EXPR (, EXPR)*` — space-separated on one line | `printf`, format strings, file I/O, locale |
| Library | exactly `allocate`, `free`, `size of TYPE`, `show` | everything else in libc |
| Comments | `# …` to end of line | `/* … */`, `//`, preprocessor |

Punctuation is limited to `( ) , = [ ]`; all other structure is words. One
statement per line; indentation is decorative.

---

## 2. Lexical rules

* `NUMBER` is decimal digits, or digits `.` digits (no sign, suffix, hex, or
  exponent). Negative values are written `0 minus N`. An int literal outside
  −2147483648…2147483647 is rejected; write `((0 minus 2147483647) minus 1)`
  for the int minimum.
* `STRING` is double-quoted with the escapes `\n`, `\t`, `\r`, `\"`, `\\`.
  Strings are for `show` only (an output-only internal type); there is no
  declared text type in v1.
* Reserved words cannot be used as identifiers. The closed keyword set is the
  vocabulary of the grammar below, including `type`, `count`, `value`, `item`,
  `member`, `via`, `next`, `through`-style clause words, etc.
* `call NAME with …` uses a single identifier as the callee name (C-like, not
  the English surface's multi-word names). `call allocate`/`call free` are the
  two builtins with named arguments.

---

## 3. Types, widths, and layout (pinned)

| Type | Size | Alignment | Notes |
|---|---:|---:|---|
| `int` | 4 | 4 | signed 32-bit two's complement; range −2147483648…2147483647 |
| `float` | 8 | 8 | IEEE-754 binary64 (this is C `double`, **not** C `float`) |
| `pointer to T` | 8 | 8 | typed; `null pointer` is the null value |
| `array[N] of T` | `N × sizeof(T)` | alignment of `T` | length is preserved in the IR (no parameter decay) |
| `struct T` | rounded up to struct alignment | max member alignment | fields in declaration order, explicit padding |

`size of TYPE` is an expression returning an `int`. Struct layout example:

```
define struct Pair with a as int, b as float
end struct
# size of struct Pair == 16   (a at offset 0, b at offset 8)
```

Self-reference through a pointer is allowed; a struct containing itself by
value is a static error.

### No implicit conversions

Mixed `int`/`float` operands, mismatched initializer/argument/return types, and
assigning a `float` to an `int` are **static type errors**. Conversions are
visible in the AST:

```
give back (cast n as float) divided by 2.0    # C: return n / 2.0;
```

The one implicit conversion is the null-pointer literal: `null pointer` may
initialize or be passed to any `pointer to T`.

---

## 4. C ↔ c-ll examples

### 4.1 Swap through pointers (address-of / dereference / call-by-value)

```c
void swap(int *a, int *b) {
    int t = *a;
    *a = *b;
    *b = t;
}
int main(void) {
    int x = 3, y = 7;
    swap(&x, &y);
    printf("%d %d\n", x, y);   /* 7 3 */
}
```

```
define function swap giving void taking a as pointer to int, b as pointer to int
    let t as int be value at a
    set value at a to value at b
    set value at b to t
end function

define function main giving int taking none
    let x as int be 3
    let y as int be 7
    call swap with address of x, address of y
    show x, y                 # 7 3
    give back 0
end function

call main with
```

`value at a` is an lvalue: it can appear left of `set` and as the operand of
`address of`.

### 4.2 Struct and pointer traversal

```c
struct Point { int x; int y; };
int sum(const struct Point *ps, int n) {
    int total = 0;
    for (int i = 0; i < n; ++i)
        total += ps[i].x + ps[i].y;
    return total;
}
```

```
define struct Point with x as int, y as int
end struct

define function sum giving int taking ps as pointer to struct Point, n as int
    let total as int be 0
    repeat for i from 0 below n by 1
        set total to (total plus (member x via (ps plus i)))
        set total to (total plus (member y via (ps plus i)))
    end repeat
    give back total
end function
```

`member f via p` is `p->f`; `member f of s` is `s.f`. `item i of p` is
`p[i]`. Parentheses around nested expressions are mandatory.

### 4.3 Heap allocation, null check, free

```c
int fill(int n) {
    int *a = malloc((size_t)n * sizeof(int));
    if (a == NULL) return 1;
    a[0] = 42;
    int r = a[0];
    free(a);
    return r;
}
```

```
define function fill giving int taking n as int
    let a as pointer to int be call allocate with type = int, count = n
    if a equals null pointer then
        give back 1
    end if
    set item 0 of a to 42
    let r as int be item 0 of a
    call free with pointer = a
    give back r
end function
```

`allocate` zero-fills (unlike `malloc`), so there is no uninitialized read.
`free(null pointer)` is a no-op.

### 4.4 Precedence and division — deliberate differences from C

```c
int r = a + b * c;      /* b*c first in C */
int q = -7 / 2;         /* -3, truncation toward zero */
int m = -7 % 2;         /* -1, sign follows dividend */
```

```
let r as int be (a plus (b times c))          # grouping is explicit, single precedence
let q as int be ((0 minus 7) divided by 2)    # -3
let m as int be ((0 minus 7) remainder 2)     # -1
```

C operators are never available in source form; `+ - * / %` are rejected by
the lexer. A differential harness must emit **fully parenthesized C** so the
precedence difference cannot affect results.

---

## 5. Grammar (compact EBNF)

```ebnf
program     ::= (toplevel NEWLINE | NEWLINE)*
toplevel    ::= struct_def | function_def | statement
struct_def  ::= "define struct" NAME "with" field ("," field)* NEWLINE
                "end struct"
field       ::= NAME "as" type
function_def::= "define function" NAME "giving" type "taking"
                (param ("," param)* | "none") NEWLINE block "end function"
param       ::= NAME "as" type
type        ::= "int" | "float" | "void" | "pointer to" type
              | "array" "[" NUMBER "]" "of" type | "struct" NAME
declaration ::= "let" NAME "as" type "be" expr        (* initializer required *)
statement   ::= declaration | set_stmt | show
              | if_stmt | while_loop | counted_loop
              | "stop the loop" | "skip to the next item" | "give back" expr
              | "call" NAME ["with" arglist]
set_stmt    ::= "set" lvalue "to" expr
lvalue      ::= NAME | "value at" expr | "item" expr "of" expr
              | "member" NAME "of" expr | "member" NAME "via" expr
if_stmt     ::= "if" expr "then" NEWLINE block
                ("otherwise if" expr "then" NEWLINE block)*
                ["otherwise" NEWLINE block] "end if"
while_loop  ::= "repeat while" expr NEWLINE block "end repeat"
counted_loop::= "repeat for" NAME "from" expr "below" expr ["by" expr]
                NEWLINE block "end repeat"
arglist     ::= expr ("," expr)*
block       ::= (statement NEWLINE | NEWLINE)*

expr        ::= unary (op unary)*                (* ONE precedence, left-to-right *)
unary       ::= "not" unary | "address of" unary | primary
primary     ::= NUMBER | STRING | "null pointer" | NAME
              | "(" expr ")" | "cast" expr "as" type
              | "value at" expr | "item" expr "of" expr
              | "member" NAME "of" expr | "member" NAME "via" expr
              | "size of" type
              | "call" NAME ["with" arglist]
              | "call allocate with type = type, count = expr"
              | "call free with pointer = expr"
op          ::= "plus" | "minus" | "times" | "divided by" | "remainder"
              | "equals" | "does not equal" | "is less than"
              | "is at most" | "is greater than" | "is at least"
              | "and" | "or"
```

The prefix forms `value at expr`, `item … of expr`, and `member … of/via expr`
take a *full* expression as their operand, so nested uses must be parenthesized
(e.g. `member x of (member start via l)`).

---

## 6. Checked undefined behaviour

Every C UB case in the design becomes a source-located error via
`RuntimeErrorLang` (rendered as `message at line L, column C`):

| C undefined behaviour | c-ll diagnostic |
|---|---|
| signed overflow (`+`, `-`, `*`, `INT_MIN / -1`, `INT_MIN % -1`) | `integer overflow` |
| division/remainder by zero | `division by zero` |
| null dereference, null indexing | `null pointer dereference` |
| pointer arithmetic/index outside the allocated object | `pointer out of bounds` |
| one-past-end pointer dereference | `pointer out of bounds` |
| ordering pointers into different objects | `pointer ordering requires pointers into one object` |
| use after `free` | `use after free` |
| `free` twice / freeing an interior pointer | `double free` / `invalid free` |
| `float` → `int` outside int range | `invalid conversion` |
| non-positive allocation, size overflow | `invalid allocation` |
| falling off a non-void function | `function … ended without 'give back'` |
| uninitialized read | impossible: initializer mandatory, `allocate` zero-fills |
| unsequenced modification | impossible: no `++`, no comma operator, left-to-right eval |
| strict-aliasing / type-punned dereference | impossible: pointers are typed, no casts to pointer |

Static errors (before execution) cover type mismatches, undefined names,
unknown fields/functions, wrong arity, non-lvalue `address of`, `set` targets
that are not lvalues, by-value struct recursion, missing returns, and
`break`/`continue` outside loops.

Evaluated order is pinned left-to-right, including call arguments; there is an
explicit call-boundary sequence point. `allocate` returns distinct objects.

---

## 7. API

```python
from llang.cll import run_c_source, compile_c_source, check_c_source

interp = run_c_source(source)        # returns CInterpreter; .output holds lines
program, report = check_c_source(source)   # report.errors holds type errors
result = compile_c_source(source)    # WASM bytes via the shared backend
```

`compile_c_source` lowers the int-only, pointer-free subset to canonical llang
AST nodes and calls the existing WASM backend. Constructs that backend cannot
represent are reported in `result.unsupported` rather than silently dropped;
they still execute correctly under `run_c_source`. `inputs=` is accepted by
`run_c_source` for API parity but v1 has no input statement.

File extension: `.cll`.

---

## 8. Verification

### 8.1 Native C oracle

The design's preferred differential oracle is a native C compiler. A MinGW-w64
GCC 16.2 toolchain is now installed on the development host and is located by
`tools/cc.py` (override with the `CC` environment variable). `tests/test_cll_gcc.py`
compiles paired C programs with `-std=c11 -O0`, runs them, and compares stdout
against `run_c_source` for the integer subset: arithmetic, C truncation and
remainder rules, and factorial recursion. The test skips gracefully when no
compiler is available, so CI on other hosts is unaffected.

Future strengthening: add a `tests/c_corpus/` directory with `-pedantic -Wall
-Wextra -Werror` builds and a UBSan/ASan run
(`-fsanitize=undefined,address -fno-sanitize-recover=all`) at `-O0` and `-O2`.

### 8.2 Current oracle

`tests/test_cll.py` contains `DifferentialPythonReferenceTests`: a Python
reference implementation of the same C semantics (truncating `/`, dividend-signed
`%`, call-by-value swap, pointer/struct traversal, factorial) plus 200 seeded
random arithmetic cases rendered with explicit parentheses. These are
differential tests against a **Python reference**, not against gcc/clang; they
verify the semantics we pin but cannot detect a mistake in our reading of C11
itself. That is exactly the gap item 8.1.1–8.1.4 closes.

The rest of the suite covers canonical examples, layout offsets, pointer and
allocation behaviour, control flow, recursion, and negative UB cases with
pinned diagnostic text.

### 8.3 Regression contract

Run the full suite:

```
python -m unittest discover -s tests
```

The 368 pre-existing English-surface tests run unchanged alongside the c-ll
tests; no file under `src/llang/` outside `src/llang/cll/` is modified.

---

## 9. Explicit omissions

Preprocessor/macros, `printf`/libc beyond the four builtins, unsigned and
narrow integer types, unions/bit-fields/VLAs, `goto`/`switch`/`do`/`?:`,
assignment-in-expression, threading/atomics, function pointers, nested
functions, raw byte access, and pointer casts. Each is deliberate; see the
design document's §7 for the rationale.
