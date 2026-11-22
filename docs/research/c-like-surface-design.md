# C-like surface — grounding, invariants, and minimal design

*Status: research + proposal for the second family surface. No implementation exists yet.
Authority: ISO/IEC 9899:2011 (C11) as summarized by cppreference's C language reference,
cross-checked against the GNU C Reference Manual. Syntax below is a proposal only.
Follows the method in [`../METHOD.md`](../METHOD.md); the locked decision is #1 in
[`../FAMILY-PLAN.md`](../FAMILY-PLAN.md). Where a design statement and the implementation
disagree, the code wins.*

## Sources

- **[C11-DRAFT]** ISO/IEC 9899:2011, public WG14 draft N1570 — <https://www.open-std.org/jtc1/sc22/wg14/www/docs/n1570.pdf> (fetched as text: unsupported MIME `application/pdf`; section/page numbers below are the N1570 numbers reproduced by cppreference's "References" blocks).
- **[LANG]** cppreference — C language index (standard versions, feature set): <https://en.cppreference.com/w/c/language>
- **[PREC]** cppreference — C operator precedence (C11 Annex A.2.1): <https://en.cppreference.com/w/c/language/operator_precedence>
- **[TYPES]** cppreference — arithmetic types, widths, data models, value ranges: <https://en.cppreference.com/w/c/language/arithmetic_types>
- **[CONV]** cppreference — implicit conversions, promotions, usual arithmetic conversions, pointer conversions: <https://en.cppreference.com/w/c/language/conversion>
- **[EVAL]** cppreference — order of evaluation, sequence points, unsequenced UB: <https://en.cppreference.com/w/c/language/eval_order>
- **[ARITH]** cppreference — arithmetic operators, signed overflow, pointer arithmetic, division/remainder: <https://en.cppreference.com/w/c/language/operator_arithmetic>
- **[PTR]** cppreference — pointer declaration, null pointers, aliasing note: <https://en.cppreference.com/w/c/language/pointer>
- **[STRUCT]** cppreference — struct declaration, padding, order, self-reference: <https://en.cppreference.com/w/c/language/struct>
- **[OBJ]** cppreference — objects, effective type, strict aliasing, alignment: <https://en.cppreference.com/w/c/language/object>
- **[STMT]** cppreference — statements and blocks (C11 §6.8, pp. 146–154): <https://en.cppreference.com/w/c/language/statements>
- **[CALL]** cppreference — function call semantics, call-by-value, unsequenced arguments: <https://en.cppreference.com/w/c/language/operator_other>
- **[ARRAY]** cppreference — arrays, array-to-pointer decay, parameter decay: <https://en.cppreference.com/w/c/language/array>
- **[UB]** cppreference — undefined/unspecified/implementation-defined/locale-specific behavior: <https://en.cppreference.com/w/c/language/behavior>
- **[GNU]** GNU C Reference Manual (C89 baseline + C99/GNU extensions, GFDL-licensed): <https://www.gnu.org/software/gnu-c-manual/gnu-c-manual.html>
- Local: [`../FAMILY-PLAN.md`](../FAMILY-PLAN.md), [`../METHOD.md`](../METHOD.md), [`../GRAMMAR.md`](../GRAMMAR.md), [`../REFERENCE.md`](../REFERENCE.md), `src/llang/ast_nodes.py`, `src/llang/compiler.py`.

---

## 1. Why C is the right next surface; what we copy vs invent

### 1.1 Why C, and why now

1. **It is the locked decision.** `FAMILY-PLAN.md` §"Decisions locked" #1: "First new surface: C-like, which forces the L2/L3 memory-model design." The plan's build order (Phase 3) explicitly says C "forces the hard memory-model decisions while the core is still small" (`FAMILY-PLAN.md` lines 80–82).
2. **It is the only choice that forces the whole tier stack.** A JS-like surface would stay at L1; a Rust-like surface adds ownership on top of an already-solved pointer model. C requires integer widths, addressable objects, layout, call-by-value, and a defined UB boundary — i.e. all of L2 and L3 ([LANG], [OBJ], [PTR]).
3. **The oracle principle is satisfied.** C has (a) an authoritative, freely available draft standard [C11-DRAFT], (b) a complete secondary reference with exact section/page cites [LANG], and (c) an executable oracle in gcc/clang — the cheapest, most mature differential-testing target available. `METHOD.md` §"The oracle principle" makes this a precondition, not a nice-to-have. (Shell check on 2026-11-22: no native gcc/clang on this host — see §6.1.)
4. **It lines up with the existing backend.** `src/llang/compiler.py` already emits WebAssembly `i32` arithmetic (lines 84–102), maps `DIV`/`FLOORDIV` to `i32.div_s` (opcode `0x6D`, truncating toward zero — C's `/` rule, *not* llang's float `divided by`; see §4.3), and reports unsupported constructs instead of guessing. A WASM memory section + `i32.load`/`i32.store` is the natural L3 backend step, and the C surface becomes the first human-readable front-end that can target it.
5. **Small core, bounded work.** C89 has 32 keywords ([GNU] §1.2); C11 adds only a handful (`_Bool`, `_Complex`, `_Alignas`, `_Atomic`, …). A typed, pointer-capable subset fits in one prompt-sized grammar, which is a hard requirement (`METHOD.md` step 8).

### 1.2 Standard and license context

- The language is **ISO/IEC 9899**, editions C89/C90, C99, C11, C17, C23 ([LANG]; [GNU] preface documents GCC's C89 baseline + C99). We target **C11** semantics (N1570) because it is the edition with fully specified sequence points/atomics and the one cited by the available references; C17 is a bug-fix edition, C23 changes signed-representation rules (two's complement only) and operator spellings.
- The **standard text is copyrighted**; the WG14 public draft N1570 is freely available for study [C11-DRAFT]. We copy **semantics**, never text.
- **[GNU]** is published under the **GNU Free Documentation License** (its ToC includes "GNU Free Documentation License"); cppreference is a community wiki under CC BY-SA. We cite them; we do not embed their prose. Our surface text, grammar, and AST nodes are original.
- GCC's dialect is "C89 plus GNU extensions" by default ([GNU] preface); we deliberately target **strict standard C11** (`-std=c11 -pedantic`) and reject GNU extensions in the surface. The preprocessor is documented in a *separate* GNU manual ([GNU] preface) — another reason to omit it (§7).

### 1.3 Copy semantics, invent phrasing

| We copy from C (settled semantics) | We invent (readable phrasing / deliberate safety rules) | We do **not** copy |
|---|---|---|
| `int` ≈ signed 32-bit, `float` ≈ binary64; rank, widths, data models [TYPES] | type words: `int`, `float`, `pointer to T`, `array[N] of T`, `struct T` | declarator syntax (`int *p[3]`, `int (*fp)(int)`) |
| integer `/` truncates toward zero; `%` sign follows dividend [ARITH] | operator words `plus`, `minus`, `times`, `divided by`, `remainder` | symbolic operators `+ - * / % & | ^ << >> ?:`, `++`/`--` |
| signed overflow, null deref, OOB, unsequenced writes are UB [UB] | **no UB**: checked overflow, mandatory init, bounds checks, loud errors | UB itself, `-fwrapv` dependence, trap representations |
| sequence points at full expressions, `&&`, `||`, `,`, before call [EVAL] | `end if` / `end repeat` / `end function`; one statement per line | `{}`, `;`, dangling-`else`, fallthrough |
| call-by-value, argument conversions, sequence point before body [CALL] | `call NAME with a, b` (positional, typed), `give back` | implicit argument conversion (we require explicit `cast`) |
| pointer address model, `&`/`*`, pointer arithmetic within one array [PTR], [ARITH] | `address of`, `value at`, `item i of p`, `member f via p` | arbitrary pointer casts, pointer/integer punning |
| struct member order, padding, alignment, self-reference via pointer [STRUCT], [OBJ] | `define struct T with f as int, … end struct` | unions, bit-fields, flexible array members |
| UB taxonomy: undefined / unspecified / implementation-defined / locale-specific [UB] | tier flag + linter rejects unsound mixing | implementation-defined choices (we pin widths/endianness-independent behavior) |

**Non-negotiable inherited from llang** (`../REFERENCE.md` §1, `../GRAMMAR.md`): one precedence level, left-to-right; explicit block closers; closed vocabulary; no hidden control flow; no user syntax; every synonym normalizes to one canonical AST. The C-like surface keeps all five, even where C does not.

---

## 2. Cross-cutting invariants from C11 the surface must respect

Every row below is a *constraint on the design*, not a feature to copy. "Respect" means: implement the rule, or restrict the surface so the rule cannot be violated, and document the divergence.

### 2.1 Integer types and widths

- C's minimum widths are `char ≥ 8`, `short ≥ 16`, `int ≥ 16`, `long ≥ 32`, `long long ≥ 64` bits, with `1 == sizeof(char) ≤ sizeof(short) ≤ sizeof(int) ≤ sizeof(long) ≤ sizeof(long long)` [TYPES] §"Integer types"; C11 §5.2.4.2.1, §6.2.5. Exact-width `intN_t`/`uintN_t` are optional C99 additions in `<stdint.h>` [TYPES].
- Four mainstream data models exist: LP32, ILP32, LLP64 (Windows: `long` 32, pointer 64), LP64 (Unix: `long` 64) [TYPES] §"Data models". **Width is implementation-defined** — a surface that says "int" without pinning a model has no portable semantics.
- Pre-C23 C permits sign-and-magnitude/one's-complement; guaranteed signed minimum for N bits is `−(2^(N−1)−1) … +(2^(N−1)−1)`; C23 mandates two's complement (`−2^(N−1) … 2^(N−1)−1`) [TYPES] §"Range of values".
- Floating: `float` ≈ IEEE-754 binary32, `double` ≈ binary64, `long double` implementation-defined; NaNs, ±∞, −0.0 exist; `NaN != NaN`; rounding may exceed the declared type per `FLT_EVAL_METHOD` [TYPES] §"Real floating types".
- **Design rule:** v1 exposes exactly two arithmetic types: `int` = **signed 32-bit two's complement** (range `−2147483648…2147483647`, matching WASM `i32` and the "int = 32" rows of ILP32/LP64 [TYPES]) and `float` = **IEEE-754 binary64** (Python `float`, C's `double`). `float` in the surface therefore means C `double`; document this explicitly. No `char`, `short`, `long`, `unsigned`, `_Bool`, or `_Complex` in v1 (§7).

### 2.2 Signed overflow and UB-adjacent arithmetic

- **Unsigned** arithmetic is modulo 2^n; **signed** overflow is UB: it may wrap, trap (`-ftrapv`), or be optimized away entirely [ARITH] §"Overflows"; [UB] §"Signed overflow" shows `x + 1 > x` compiling to `return 1`.
- Unary `-` on `INT_MIN`/`LONG_MIN`/`LLONG_MIN` is signed-overflow UB [ARITH] §"Unary arithmetic" notes.
- `/` and `%` with a zero divisor are UB; `INT_MIN % -1` is UB (quotient not representable) [ARITH] §"Division", §"Remainder". Integer `/` is implementation-defined before C99, **truncated toward zero since C99** [ARITH]. Remainder satisfies `(a/b)*b + a%b == a` when the quotient is representable, so the sign follows the dividend [ARITH].
- Shifts: UB if the shift count is negative or ≥ the promoted width; left shift of a positive signed value that is not representable is UB; right shift of a negative signed value is implementation-defined [ARITH] §"Shift operators".
- **Design rule:** the surface has no shift/bitwise operators in v1 (§7). Every `int` operation is range-checked; overflow, division by zero, and `%` by zero raise a source-located `integer overflow` / `division by zero` error. This is a strict subset of C's defined behavior, so differential tests never depend on UB (§6.3).

### 2.3 Conversions and promotions

- C converts on assignment, scalar initialization, prototyped call arguments, and `return` ("as if by assignment") [CONV] §"Conversion as if by assignment". Arguments to unprototyped/variadic calls get **default argument promotions**: integer promotion and `float → double` [CONV] §"Default argument promotions"; [CALL].
- **Integer promotions**: any integer type of rank ≤ `int` (including bit-fields and `_Bool`) becomes `int` if `int` can represent all its values, else `unsigned int`; rank order is `bool < char < short < int < long < long long` [CONV] §"Integer promotions". Applied only in usual arithmetic conversions, default argument promotions, unary `+`/`-`/`~`, and shift operands [CONV].
- **Usual arithmetic conversions** for `* / % + -`, comparisons, `& ^ |`, `?:`: rank ladder `long double > double > float > integer`, then for integers: same sign → lower rank converts up; mixed sign → unsigned rank ≥ signed rank wins, else signed wins if it represents all unsigned values, else both convert to the unsigned counterpart of the signed type [CONV] §"Usual arithmetic conversions" (its `2u - 10` example yields `4294967288` on 32-bit `unsigned int`).
- Integer→integer: if the target cannot represent the value, unsigned targets wrap modulo 2^b, signed targets are implementation-defined [CONV] §"Integer conversions". Float→integer truncates toward zero and is **UB if unrepresentable**; integer→float rounds implementation-defined/IEEE-nearest, UB if out of range [CONV] §"Real floating-integer conversions". Pointer→integer (except null constant) and object↔function pointer conversions require an explicit cast; there are no conversions between function and object pointers [CONV] §"Pointer conversions", §"Notes".
- `NULL` is any integer constant expression with value 0 (or `(void*)0`); it converts to any pointer type and is guaranteed unequal to any non-null pointer [PTR] §"Null pointers", [CONV].
- **Design rule:** because v1 has no narrow types and no unsigned types, promotions are *vacuous*; all operands are already `int(32)` or `float(64)`. We therefore adopt llang's "no implicit coercion" rule as the surface rule: mixed `int`/`float` operands are a **static type error**; conversion requires `cast EXPR as TYPE`. Pointer conversions other than `null pointer` assignment require an explicit cast node (not in v1). This is a documented divergence from C's UAC, kept safe and predictable.

### 2.4 Sequence points and evaluation order

- Operand evaluation order (including function arguments) is **unspecified**; associativity is not evaluation order: `f1() + f2() + f3()` parses left-associative but may call `f3()` first [EVAL] intro.
- Sequence points exist: (1) after all function arguments/designator, before the call; (2) after the left operand of `&&`, `||`, `,`; (3) after the condition of `?:`; (4) after each full expression (semicolon or controlling expression of `if`/`while`/…); (5) end of full declarator; (6) before return from a library function; (7) after each formatted-I/O conversion; (8) around `qsort`/`bsearch` comparators [EVAL] §"Rules". C11 adds *sequenced-before*, *indeterminately sequenced*, and *unsequenced* terminology, and rules 9–14 (value computations precede result value computation; assignment side effect follows both operands' value computations; post-increment value computation precedes its side effect; unsequenced function calls are indeterminately sequenced) [EVAL].
- UB: a side effect on a scalar unsequenced relative to another side effect on the same scalar, or relative to a value computation using that scalar — e.g. `i = i++ + 1`, `f(++i, ++i)`, `f(i, i++)`, `a[i] = i++` [EVAL] §"Undefined behavior".
- **Design rule:** the surface specifies **left-to-right evaluation** everywhere (already llang's rule, `../REFERENCE.md` §1) and has no `++`/`--`, no comma operator, no assignment-in-expression, no `?:`. Therefore no unsequenced modification can be written. Argument evaluation is left-to-right and there is a call-boundary sequence point, matching C's *defined* subset; the differential harness simply avoids the UB cases.

### 2.5 Pointer and address model

- A pointer refers to an object/function or the null value; `&` yields a pointer to an object, `*` yields the lvalue identifying the pointed-to object; `int *p = &n; *p = 7;` then reads `n` as 7 [PTR] §"Pointers to objects".
- Pointer arithmetic `P ± N` is defined only when both original and result point into the **same array** or one past its end; `P1-P2` is `ptrdiff_t`; a non-array object is treated as an array of size 1; `p-1` before the first element is UB [ARITH] §"Pointer arithmetic". Arrays decay to `&a[0]` in most contexts (not under `&`, `sizeof`, `_Alignof`, or as an array initializer string) [ARRAY] §"Array to pointer conversion"; parameter arrays decay to pointers, so length is *not* carried ([ARRAY], example `void f(int a[], int sz)`).
- Comparisons: equality for same address / two nulls; ordering only within one array or for struct members in declaration order [PTR] §"Pointers to objects". Strict aliasing: reading an object of effective type T1 through an lvalue of a different T2 is UB unless T2 is compatible, a qualified/signed variant, an aggregate containing T1, or a character type [OBJ] §"Strict aliasing". Dereferencing a type-punned pointer is "almost always UB" [PTR] §"Notes".
- **Design rule:** v1 pointers are **typed** (`pointer to T`), can only be formed by `address of` an lvalue, `allocate`, or `null pointer`, and are always dereferenced at the declared type — no casts, no `void*`, no pointer/integer arithmetic (pointer `plus`/`minus` with an integer *is* allowed and is bounds-checked against the allocated array length). Array parameters keep their length in the IR (we do **not** decay silently; a `pointer to array[N] of T` is distinct from `pointer to T`). This removes strict-aliasing and out-of-bounds UB by construction.

### 2.6 Struct layout and alignment

- Members are stored in **declaration order**; addresses increase in that order; a pointer to a struct and a pointer to its first member are interconvertible; unnamed padding may occur between members or after the last, never before the first; `sizeof(struct)` ≥ sum of member sizes [STRUCT] §"Explanation". The reference example shows `struct A {char a; double b; char c;}` with offsets 0/8/16 and size 24, versus `struct B {char a; char b; double c;}` with offsets 0/1/8 and size 16 [STRUCT] example — layout is not just the sum of fields.
- A struct may not contain itself but may contain a pointer to itself; a tag used before definition is an incomplete type; forward declarations `struct y;` enable mutual references [STRUCT] §"Forward declaration", §"Notes". Anonymous structs/unions (C11) and flexible array members (C99) exist [STRUCT].
- Every object has size, alignment requirement (non-negative power of two), storage duration, lifetime, effective type, and possibly indeterminate value [OBJ] intro. Alignment of a struct is driven by its most-aligned member; padding is inserted to satisfy it [OBJ] §"Alignment" (`struct X {int n; char c;}` → size 8, align 4).
- **Design rule:** v1 structs are fixed, non-recursive-by-value records of typed fields. The type checker computes an explicit layout (offset = round-up to member alignment, size = round-up to struct alignment) with a **pinned model** (`int` align 4, `float` align 8, pointers align 8 — LP64-like; independent of host endianness because the surface never exposes raw bytes). Self-reference via `pointer to struct T` is allowed. No anonymous members, no bit-fields, no flexible arrays, no packed layouts.

### 2.7 Control flow

- C statements: compound, expression, selection (`if`, `switch`), iteration (`while`, `do`, `for`), jump (`break`, `continue`, `return`, `goto`); each compound statement introduces a block scope; labels have function scope; automatic initializers and VLA declarators execute when control passes over them [STMT]. C11 §6.8, pp. 146–154.
- There is a sequence point after each full expression and after controlling expressions of `if`/`switch`/`while`/`do` [EVAL] rule 4. `switch` fallthrough and `goto` are explicit but unstructured; `?:` and `,` hide control flow/sequencing inside expressions [CALL].
- **Design rule:** keep llang's visible closers and no hidden flow: `if … then / otherwise if … then / otherwise / end if`, `repeat while … / end repeat`, `repeat for NAME from A below B [by STEP] / end repeat`, `stop the loop`, `skip to the next item`, `give back`, `call`. No `goto`, `switch`, `do`, `?:`, `,`, or assignment-in-condition in v1; block scoping is *introduced* for typed locals (a deliberate change from llang where "blocks do not create a new scope", `../REFERENCE.md` §5) so that lifetimes are explicit — document it as an L2/L3 rule, not an English-surface change.

### 2.8 Function calls

- A call requires a pointer-to-function expression; with a prototype, arity must match and each argument must be implicitly convertible "as if by assignment" to its parameter type; arguments are evaluated in **unspecified order without sequencing**; values are **copied** (C calls are call-by-value only); a sequence point occurs before the body; the return value is converted to the declared return type [CALL] §"Call to a function with a prototype", §"Notes"; C11 §6.5.2.2, pp. 81–82.
- Calls without a prototype trigger default argument promotions and are UB on type mismatch; `printf`-style variadic functions must have a prototype in scope [CALL]; implicit function declarations were removed after C89 [CALL].
- **Design rule:** every function has a prototype (`giving TYPE taking NAME as TYPE, …`); calls are checked for arity and types statically; arguments are evaluated left-to-right; parameters are copied; arrays are passed as `pointer to array[N] of T` with length preserved; no variadics, no implicit declarations, no function pointers in v1.

### 2.9 Undefined / unspecified / implementation-defined behavior categories

| Category | Meaning (C11 §3.4, pp. 3–4; §4/2, p. 8) [UB] | Our stance |
|---|---|---|
| **undefined (UB)** | No restrictions; compiler need not diagnose; program need not do anything meaningful. Examples: OOB access, signed overflow, null deref, double modification without sequence point, type-punned access. | **Forbidden by construction** (checked ops, mandatory init, bounds checks, no unsequenced writes) or rejected at compile time. Never a silent runtime behavior. |
| **unspecified** | Two or more permitted behaviors, undocumented; may differ between runs (e.g. evaluation order, distinctness of identical string literals) [UB]. | We **pin** one: left-to-right evaluation, distinct allocations. |
| **implementation-defined** | Unspecified but documented by the implementation (e.g. bits per byte, signed `>>` direction) [UB]. | We **pin** widths, signed representation, alignment, and `/`, `%` rules in the surface spec. |
| **locale-specific** | Implementation-defined behavior depending on the current locale [UB]. | No locale-dependent operations in v1. |

Compilers must diagnose violations of **syntax rules and semantic constraints** even when the behavior is undefined [UB] intro. Our type checker is that diagnostic layer, emitted with source positions like every other llang error (`../REFERENCE.md` §7).

---

## 3. Concrete proposal: the `c-ll` surface

Name: **c-ll** ("see-ell"), a C-like surface for the same canonical IR. It reads like structured English, is C-like in *structure* (explicit types, addressable objects, call-by-value), and keeps llang's visible delimiters, single precedence, and closed vocabulary. Surface glyphs beyond llang's `( ) , =` are limited to `[` `]` (array sizes) — all other structure is words. Comments remain `# …`, one statement per line, indentation decorative.

### 3.1 Vocabulary (closed; one module, e.g. `synonyms.py`/`c_vocab.py`)

| Concept | c-ll spelling | C spelling | Canonical op / node |
|---|---|---|---|
| types | `int`, `float`, `void`, `pointer to T`, `array[N] of T`, `struct T` | `int`, `double`, `void`, `T*`, `T[N]`, `struct T` | `Type` value object |
| declare | `let NAME as TYPE be EXPR` | `TYPE NAME = EXPR;` | `TypedDecl` (init **mandatory**) |
| assign | `set LVALUE to EXPR` | `LVALUE = EXPR;` | `Set` / `Store` |
| arithmetic | `plus`, `minus`, `times`, `divided by`, `remainder` | `+ - * / %` | `ADD/SUB/MUL`, new `IDIV/IREM`, `FDIV` |
| cast | `cast EXPR as TYPE` | `(TYPE)EXPR` | `Cast` |
| truth/logic | `and`, `or`, `not` (scalars: nonzero = true, result `int` 0/1) | `&& \|\| !` | new `LAND/LOR/LNOT` |
| compare | `equals`, `does not equal`, `is less than`, `is at most`, `is greater than`, `is at least` | `== != < <= > >=` | `EQ/NE/LT/LE/GT/GE` |
| address / deref | `address of EXPR`, `value at EXPR` | `&EXPR`, `*EXPR` | `AddressOf`, `Deref` |
| member | `member F of EXPR` (struct value), `member F via EXPR` (pointer) | `x.f`, `p->f` | `MemberAccess(via_pointer=…)` |
| index | `item INDEX of EXPR` | `a[i]` / `*(p+i)` | `Index` (bounds-checked) |
| null | `null pointer` | `NULL` | `Literal(None, type=pointer)` |
| heap | `call allocate with type = TYPE, count = EXPR`, `call free with pointer = EXPR` | `malloc`, `free` | `Alloc`, `Free` |
| struct def | `define struct T with F as TYPE, …` … `end struct` | `struct T { TYPE F; … };` | `StructDef` |
| function | `define function F giving TYPE taking P as TYPE, …` … `end function` | `TYPE F(TYPE P, …) { … }` | `FunctionDef(+types)` |
| call | `call F with EXPR, EXPR, …` | `F(a, b)` | `Call` (labels synthesized positionally) |
| return | `give back EXPR` | `return EXPR;` | `Return` |
| if | `if EXPR then` … `otherwise if EXPR then` … `otherwise` … `end if` | `if (…) … else if … else …` | `If` |
| loops | `repeat while EXPR` … `end repeat`; `repeat for NAME from A below B [by S]` … `end repeat` | `while`, `for` | `RepeatWhile`, new `CountedLoop` → desugars |
| break/continue | `stop the loop`, `skip to the next item` | `break`, `continue` | `Break`, `Continue` |
| output | `show EXPR (, EXPR)*` | `printf` (tiny subset) | `Show` |

Synonyms are deliberately *few* — C is not a natural language. The flexibility lives in the mapping table, not in the evaluator; each row produces exactly one canonical node (synonym-equivalence test per `METHOD.md` step 7).

### 3.2 Side-by-side examples

**(a) Swap through pointers — address-of / deref / call-by-value**

```c
/* C11 */
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
# c-ll
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
```

`value at a` is an **lvalue**: it may appear on the left of `set` and as the operand of `address of`. `address of x` requires an lvalue. C's `*a` is overloaded for read/write; here the same word covers both but its lvalue-ness is explicit in the AST.

**(b) Struct + pointer traversal**

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
        set total to ((total plus (member x via (ps plus i)))
                       plus (member y via (ps plus i)))
    end repeat
    give back total
end function
```

`ps plus i` is typed pointer arithmetic (`pointer to struct Point` + `int`); `item i of ps` would be the equivalent subscript. `member f via p` is `p->f`; `member f of s` is `s.f`. The nested parentheses are mandatory — see (d).

**(c) Heap allocation, null check, free**

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

`allocate` zero-initializes (C `malloc` does not) so no uninitialized read exists; `free` accepts `null pointer` as a no-op (C does too [PTR] §"Null pointers").

**(d) Precedence and division — where C and c-ll deliberately differ**

```c
int r  = a + b * c;      /* b*c first, C precedence (C11 Annex A.2.1) [PREC] */
int q  = -7 / 2;         /* -3: truncation toward zero [ARITH] */
int m  = -7 % 2;         /* -1: sign follows dividend [ARITH] */
```

```
let r as int be (a plus (b times c))          # mandatory grouping; single precedence
let q as int be ((0 minus 7) divided by 2)    # -3, C '/' rule, checked
let m as int be ((0 minus 7) remainder 2)     # -1, C '%' rule, checked
```

The harness emits **fully parenthesized C** so the precedence difference cannot change results ([PREC]: precedence is independent of evaluation order; the standard does not even define precedence levels — they are derived from the grammar).

**(e) Conversions must be explicit**

```c
double f(int n) { return n / 2.0; }   /* implicit int -> double via UAC [CONV] */
```

```
define function f giving float taking n as int
    give back (cast n as float) divided by 2.0
end function
```

In C, `n / 2.0` silently promotes `n` to `double`; in c-ll the cast is a visible node, so the audit trail is complete.

### 3.3 Grammar sketch (compact EBNF)

```ebnf
program     ::= (toplevel NEWLINE | NEWLINE)*
toplevel    ::= struct_def | function_def | declaration | statement
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

expr        ::= unary (op unary)*                  (* ONE precedence, left-to-right *)
unary       ::= "not" unary | "address of" unary | postfix
postfix     ::= primary
primary     ::= NUMBER | STRING | "null pointer" | NAME
              | "(" expr ")" | "cast" expr "as" type
              | "value at" expr
              | "item" expr "of" expr
              | "member" NAME "of" expr | "member" NAME "via" expr
              | "call" NAME ["with" arglist]
              | "size of" type
op          ::= "plus" | "minus" | "times" | "divided by" | "remainder"
              | "equals" | "does not equal" | "is less than"
              | "is at most" | "is greater than" | "is at least"
              | "and" | "or"
name        ::= WORD  (* not one of the closed reserved list; keywords never identifiers *)
```

Lexical: `NUMBER` is decimal digits or `digits "." digits` (no sign, suffix, hex, exponent — negative values are `0 minus N`); `STRING` is double-quoted with llang's four escapes; `#` comments; `(` `)` `,` `=` `[` `]` are the only punctuation; newlines terminate statements. Reserved words are the c-ll keyword set plus llang's structural words; `with` introduces arguments, so call names cannot contain it.

---

## 4. Mapping to the canonical IR tiers, required engine changes, and conflict resolution

### 4.1 Tier placement

| IR tier | c-ll constructs mapped | Existing canonical nodes reused |
|---|---|---|
| **L1 dynamic** (shipped) | `show`, `if`, `repeat while`, `stop the loop`, `skip to the next item`, `give back`, arithmetic/calls on `int`/`float` | `Program`, `Block`, `Literal`, `Variable`, `Binary`, `Unary`, `Set`, `Show`, `If`, `RepeatWhile`, `FunctionDef`, `Return`, `Call`, `Break`, `Continue` — byte-identical ASTs where semantics coincide |
| **L2 typed** (new) | `let … as … be …`, struct definitions, `cast`, `giving/taking` types, typed params, block-scoped locals, static type errors | extend `FunctionDef` with `return_type` / `param_types`; new `TypedDecl`, `StructDef`, `Cast`, `MemberAccess`, `Type` |
| **L3 low-level** (new) | `address of`, `value at`, `set value at …`, `allocate`/`free`, `item … of` on pointers, checked pointer arithmetic, layout offsets | new `AddressOf`, `Deref`, `Store`, `Alloc`, `Free`, `Index` (extended), `SizeOf`; `Label`/`Goto` defined for L3 completeness but not in v1 grammar |

Surfaces are syntax, tiers are semantics (`FAMILY-PLAN.md` lines 31–40): a c-ll program carries `tier = 3` (or `2` if it uses no pointers) on `Program`/`FunctionDef`; the English surface emits `tier = 1`. The interpreter dispatches semantics by tier and the linter rejects cross-tier calls (passing a `Pointer` to an L1 builtin, dereferencing a Python `list`, returning an L1 object from a `giving int` function). This is the "never silently merge models" guardrail.

### 4.2 New AST nodes (proposed, in `ast_nodes.py` / a `typed_nodes.py` re-exported there)

```python
@dataclass
class Type:                      # value object, not executed
    kind: str                    # 'int' | 'float' | 'void' | 'pointer' | 'array' | 'struct'
    pointee: object = None       # for 'pointer'
    element: object = None       # for 'array'
    length: int | None = None
    name: str = ""               # for 'struct'

@dataclass
class TypedDecl:                 # L2: declaration != rebinding
    name: str = ""; type: Type | None = None; init: object = None; pos: SourcePos | None = None

@dataclass
class StructDef:
    name: str = ""; fields: list = field(default_factory=list)  # [(name, Type)]
    pos: SourcePos | None = None

@dataclass
class Cast:
    expr: object = None; target: Type | None = None; pos: SourcePos | None = None

@dataclass
class AddressOf:    expr: object = None; pos: SourcePos | None = None
@dataclass
class Deref:        expr: object = None; pos: SourcePos | None = None      # lvalue
@dataclass
class Store:        target: object = None; value: object = None; pos: SourcePos | None = None
@dataclass
class Alloc:        element: Type | None = None; count: object = None; pos: SourcePos | None = None
@dataclass
class Free:         expr: object = None; pos: SourcePos | None = None
@dataclass
class MemberAccess: base: object = None; field: str = ""; via_pointer: bool = False
                    pos: SourcePos | None = None
@dataclass
class SizeOf:       target: Type | None = None; pos: SourcePos | None = None
@dataclass
class CountedLoop:  name: str = ""; start: object = None; limit: object = None
                    step: object = None; body: object = None; pos: SourcePos | None = None
@dataclass
class Label:        name: str = ""; pos: SourcePos | None = None
@dataclass
class Goto:         name: str = ""; pos: SourcePos | None = None
```

New canonical **ops** (kept distinct from llang's so neither surface's semantics change): `IDIV` (C integer `/`, truncate toward zero), `IREM` (C `%`), `FDIV` (float `/`; llang's `DIV` stays float and is not reused for ints), `LAND`, `LOR`, `LNOT` (C truthiness, 0/1 result). `Binary(op="ADD"|"SUB", …)` with one pointer-typed operand is interpreted as pointer arithmetic; the type checker is the only place that permits it.

### 4.3 Interpreter / pipeline changes

1. **Parse → type-check → execute.** New pass `src/llang/ctypes.py` (proposed) after `Parser`, before `Interpreter`: builds a symbol table from `TypedDecl`/`StructDef`/`FunctionDef`, computes struct layouts, checks lvalue-ness, checks arity/types at calls, proves initializers exist, and emits source-located `type_error` using the existing `LangError` machinery (`../REFERENCE.md` §7). English-surface programs skip this pass entirely — zero behavior change.
2. **Lvalue evaluation.** Add `Interpreter._eval_lvalue(node) -> Cell`, used by `Store`, `AddressOf`, and the L2/L3 forms of `set item`/`set field`. Today llang has no lvalue concept: `set x to …` binds a name, and `set item … of …` mutates a Python container. L3 introduces `Memory` (a dict/list of addressable cells) plus runtime values `Pointer(cell, type)`, `ArrayRef(base, length, type)`, `StructRef(layout, cells)`. L1 values (Python `int`, `str`, `list`, `dict`, `Instance`) are untouched, and there is **no implicit conversion** across the boundary.
3. **Checked arithmetic and widths.** After each `int` op, range-check to signed 32 bits; overflow raises `integer overflow`. `IDIV`/`IREM` reject a zero divisor and the `INT_MIN / -1`/`INT_MIN % -1` case. `float` uses Python `float` (binary64) and is never implicitly narrowed. This directly implements §2.1–2.3's "no UB" stance.
4. **Bounds and null checks.** `Index`, `Store` through `item … of`, and pointer arithmetic validate against the allocated length; dereferencing `null pointer` raises `null pointer dereference`; `allocate` with a non-positive count raises `invalid allocation`. These replace C UB with loud, source-located errors.
5. **Calls.** `Call.args` remains `list[(label, expr)]`: the c-ll parser synthesizes labels from the callee's formal parameter names *positionally* at parse time (after resolving the prototype). This preserves the canonical `Call` node and the English surface's labeled calls unchanged. Arguments are evaluated left-to-right; a sequence-point boundary is explicit in the eval loop.
6. **Backend.** `src/llang/compiler.py` currently (a) rejects non-integer literals, (b) maps all functions to `(i32...) -> i32`, (c) treats `Show` as a no-op with a note, (d) maps `DIV` to `i32.div_s` (line 92). Add: per-function typed signatures from `FunctionDef.return_type/param_types`, `f64` opcodes, a WASM memory section with `i32.load`/`i32.store`, and an `Alloc` lowering to a bump allocator. Because c-ll's `divided by` on ints is *defined* as truncating toward zero, it can share `i32.div_s` legitimately — while the English surface's float `divided by` must be routed to `f64.div`, fixing the existing conflation. This is the cleanest way to honor both surfaces.

### 4.4 Conflicts with existing llang semantics and their resolution

| Conflict | English surface (today) | C surface | Resolution (no breakage) |
|---|---|---|---|
| **Precedence** | one level, left-to-right (`REFERENCE.md` §4.1); C has 15 levels [PREC] | same one level | Keep one level; mandatory parentheses; harness emits fully parenthesized C. No precedence table in either surface. |
| **`/` and `%`** | `divided by` always float; `floor divided by` Python floor; `modulo` Python `%` (sign follows divisor) | `/` truncates toward zero on ints; `%` sign follows dividend [ARITH] | Distinct ops `IDIV`, `IREM`, `FDIV`; English surface keeps `DIV/FLOORDIV/MOD`. |
| **`and`/`or`** | short-circuit, *return an operand*, Python truthiness | short-circuit, scalar `!= 0`, result `int` 0/1 | Distinct ops `LAND/LOR/LNOT` vs `AND/OR/NOT`; no shared evaluation helper. |
| **Dynamic vs static typing** | no declarations, runtime type errors | declarations, static type errors | Optional `type` fields default `None`; type checker runs only for `tier ≥ 2`. |
| **Values vs addresses** | names are bindings; containers mutate by aliasing; `Instance` is a value with a field map | pointers are addresses into byte-addressed `Memory` | Two representations + explicit tier flag + linter rejection of cross-tier mixing; never reinterpret an L1 object as a pointer. |
| **Scoping** | blocks do not create scopes; functions are lexical closures | block scope; no closures (top-level functions only) | Tier-2 rule on c-ll functions; English closures untouched. |
| **Calls** | labeled, all mandatory, no positional | positional, typed | Synthesize labels positionally into the existing `Call` node. |
| **Indexing** | bounds-checked, negative rejected, maps/text allowed | C OOB is UB; no bounds check | Keep the check (safe divergence); harness never generates OOB. |
| **Output** | `show` renders Python-style and records `interpreter.output` | `printf` subset | `Show` node reused; c-ll renderer pins integer/decimal formatting (`show` of multiple values = space-separated), no Python float rendering surprises. |
| **Uninitialized state** | `set` always initializes | C leaves automatic objects indeterminate (UB on read) [UB] | Initializer mandatory on every `let`; `allocate` zero-fills. |

---

## 5. Minimal implementable subset for v1

### 5.1 Scope (the "smallest coherent L3 wedge")

- **Types:** `int` (signed 32-bit), `float` (binary64), `void` (return only), `pointer to T`, `array[N] of T`, `struct T`. No unsigned, no `char`/`short`/`long`, no `_Bool`, no unions/bit-fields.
- **Declarations/statements:** `let … as … be …` (mandatory init), `set LVALUE to …`, `show`, `if/otherwise if/otherwise/end if`, `repeat while`, `repeat for … below …`, `stop the loop`, `skip to the next item`, `give back`, `call`.
- **Expressions:** integer/float literals, name, parentheses, `plus/minus/times/divided by/remainder`, the six comparisons, `and/or/not`, `cast … as …`, `address of`, `value at`, `item … of …`, `member … of/via …`, `size of`, calls.
- **Aggregates/memory:** `define struct … end struct` (by-value fields only, self-reference via pointer), `allocate` (zero-filled), `free`, pointer `plus`/`minus` by integer, `null pointer`, equality of pointers.
- **Functions:** top-level, typed, positional, call-by-value, recursion allowed; no nested functions, no function pointers, no variadics.
- **Library:** exactly four builtins — `allocate`, `free`, `size of` (syntax, not a call), and `show` (statement). No libc I/O beyond decimal integer/float printing.

### 5.2 API sketch (proposed; not implemented)

```python
# src/llang/c_front.py  (proposed)
from .errors import SourcePos

def lex_c(source: str) -> list: ...                 # tokens incl. '[', ']'
def parse_c(tokens: list) -> Program: ...           # Program.tier = 2 | 3
def check_types(program: Program) -> TypeReport: ...# errors + inferred types + layouts

def run_c_source(source: str, *, inputs=None) -> Interpreter:
    program = parse_c(lex_c(source))
    report = check_types(program)
    if report.errors:
        raise report.errors[0]                       # source-located LangError
    return Interpreter().run(program)                # same shared evaluator

def compile_c_source(source: str) -> CompileResult:  # extends compiler.py
    program = parse_c(lex_c(source))
    check_types(program)
    return compile_program(program)                  # one shared back-end
```

Tooling entry points mirror the shipped ones: `python run.py --surface c file.cll`, `compile_source`-style API parity, formatter `format_c_source` collapsing any accepted spelling to the canonical one, linter `lint_c_source` adding the C-specific warnings (missing cast, taking `address of` a non-lvalue, implicit narrowing, freeing twice). File extension `.cll`. The corpus in §6 lives in `tests/c_corpus/` with paired `*.c` / `*.cll` files.

### 5.3 Work breakdown (first version)

1. `c_vocab.py` (closed keyword/operator table + tier marker) and `c_lexer.py` (adds `[` `]`).
2. `c_parser.py` producing existing nodes plus the §4.2 nodes; positional labels synthesized from prototypes.
3. `ctypes.py` type checker with C11-aligned rules (§2) and pinned layout model.
4. Interpreter extensions: `Memory`/`Cell`/`Pointer`/`ArrayRef`/`StructRef`, `_eval_lvalue`, checked ops, bounds/null checks, `tier` dispatch.
5. Three kinds of tests in parallel (`METHOD.md` step 7): canonicalization equivalence, semantic edge cases from §2 (negative `/` and `%`, overflow trap, null deref, alias mutation, layout offsets), and pinned-output end-to-end examples from §3.2.
6. Re-run the **entire existing English-surface test suite unchanged** — the regression contract for "without breaking the English surface".

---

## 6. Verification plan

### 6.1 Oracle availability (shell check, 2026-11-22)

```
gcc --version      -> not found
clang --version    -> not found
cc / tcc / cl / zig / g++ / mingw32-gcc -> not found
node -> D:\CHENproject\node.exe          dotnet -> C:\Program Files\dotnet\dotnet.exe
winget -> ...\winget.exe                 choco -> C:\ProgramData\chocolatey\bin\choco.exe
python -> 3.11.8
```

So the oracle is **not installed**: this is a gap to close, not a reason to guess. Concretely:

- Preferred: `winget install -e --id MSYS2.MSYS2` then `pacman -S mingw-w64-x86_64-gcc clang`, or `choco install mingw -y`; verify with `gcc --version` and record the exact version in the test report. Pin `-std=c11 -pedantic -Wall -Wextra -Werror`.
- Secondary oracle: `clang -std=c11 -O1 -fsanitize=undefined,address -fno-sanitize-recover=all` (catches overflow, null deref, OOB, misaligned access, use-after-free).
- Fallback if installation is blocked: a WASM build of clang/tcc driven through the available Node runtime, or the Compiler Explorer REST API for the small corpus. Node is present, so a `wasm-clang` npm package is viable; this is strictly a fallback because it adds network/toolchain variance.

### 6.2 Differential harness

```
for pair in tests/c_corpus/*.c:
    c   = pair
    cll = pair.with_suffix('.cll')
    native = compile(c, flags=[-std=c11, -O1, -fsanitize=undefined,address, -Werror])
    out_c   = run(native, stdin=case.input)
    out_cll = run_c_source(cll, inputs=case.input)
    assert out_c.stdout == out_cll.stdout          # exact bytes
    assert out_c.exit  == out_cll.exit
    assert sanitizer_report is empty                # else the C program had UB: fix/drop case
```

- Emit C from the surface with a **parenthesizer** (`a + (b * c)`) so the single-precedence difference is neutralized; never hand-write unparenthesized mixed-operator C in the corpus.
- Every program's UB-free status is proven by sanitizers at `-O0` *and* `-O2`; if the two native outputs differ, the case is invalid and is removed (this is exactly the optimizer-dependent UB demonstration in [UB] §"UB and optimization").
- Corpus layout: `arithmetic/` (incl. `-7/2`, `-7%2`, `INT_MAX-1`, near-limit casts), `pointers/` (swap, out-parameter, array traversal, null), `structs/` (field order, self-reference, nested structs), `control/` (nested loops, break/continue, early return), `functions/` (recursion, mutual recursion, pointer args), `memory/` (allocate/use/free roundtrip, null check).
- Property-based fuzzing (the project already ships hypothesis-style fuzzing per `FAMILY-PLAN.md`): generate random well-typed expressions with operands bounded to avoid overflow, render both C and c-ll from the same AST with explicit parens, compare. Target ≥10k cases per operator group.

### 6.3 UB-avoidance checklist for every corpus case

No signed overflow or `INT_MIN / -1`, no division/remainder by zero, no OOB or one-past dereference, no null deref, no uninitialized read, no unsequenced `x = x++` / `f(i, i++)`, no type-punned lvalue access (strict aliasing [OBJ]), no misaligned access, no use-after-free/double-free, no reading padding, no float→int out-of-range conversion, no `goto` into a scope, no reliance on unspecified evaluation order. Each rule maps to a row of §2 and to a negative test asserting c-ll raises the corresponding loud error.

### 6.4 Non-differential tests (equivalence and regression)

- **Synonym/structure equivalence:** `member f via p` and `member f of (value at p)` produce byte-identical canonical ASTs apart from `pos`; `item i of p` and `value at (p plus i)` likewise.
- **Tier isolation:** full existing `tests/` suite passes unchanged; an L1 program cannot name `address of`/`pointer to`; an L3 program cannot call a closure or pass a `Pointer` to a builtin.
- **Layout tests:** pinned offsets/sizes computed by the type checker match `offsetof`/`sizeof` printed by the C oracle on the pinned model (LP64-like alignment in §2.6); on hosts with a different model, compare field *values* only and mark layout cases model-dependent.
- **Diagnostics:** pinned messages for overflow, division by zero, type mismatch, uninitialized/OOB/null errors, with line/column, following `../REFERENCE.md` §7.

---

## 7. Explicit omissions (v1 and rationale)

| Omitted | Why |
|---|---|
| **Preprocessor, `#include`, macros, conditional compilation** | Separate translation phase and a separate GNU manual ([GNU] preface); pure text substitution with no semantics, breaks "closed vocabulary/no user syntax" and the single-AST rule. |
| **Unions, type-punning via unions** | Overlapping storage makes effective type and UB rules central [OBJ] §"Strict aliasing"; no need for the L3 wedge, and it invites exactly the UB we are eliminating. |
| **Bit-fields** | Implementation-defined allocation order and padding [STRUCT]; cannot give portable layout. |
| **Varargs / default argument promotions / `printf`** | Default promotions and unprototyped calls are a documented UB trap ([CONV], [CALL]); a tiny typed `show` covers I/O. |
| **Threading, C11 atomics, data races, signal handling** | Memory-model/thread semantics are a separate tier decision; `FAMILY-PLAN.md` defers concurrency; no deterministic differential oracle without extra tooling. |
| **libc beyond `allocate`/`free`/`show`** | Every added function is an unbounded semantic surface (I/O, locale, errno); keep the closed vocabulary intact. |
| **Unsigned integers, `char`/`short`/`long`/`long long`, `_Bool`, complex/imaginary** | They introduce modulo arithmetic, promotions, UAC rank rules, and format ambiguity [TYPES], [CONV]; v1 pins one int and one float and makes promotions vacuous (§2.3). |
| **`goto`, labels, `switch`/`case` fallthrough, `do`, `?:`, comma operator, `++`/`--`, assignment-in-expression** | Hidden/unstructured control flow or unsequenced side effects ([STMT], [EVAL]); `Label`/`Goto` AST nodes exist for L3 completeness but no grammar exposes them in v1. |
| **Function pointers, recursion through pointers, nested functions** | Function/object pointer conversions are not implicit and are UB-prone [CONV]; plain recursion suffices. |
| **`const`/`volatile`/`restrict`, `static`/`extern`/linkage, `typedef`, `enum`, `_Alignas`** | Qualifier/storage-class semantics add aliasing and linkage rules without adding expressive power needed for v1; qualifiers are erased in our model. |
| **VLA, multidimensional arrays, flexible array members, anonymous structs** | Runtime-sized arrays with implementation-defined `__STDC_NO_VLA__` support [ARRAY], and FAMs have subtle UB rules [STRUCT]; fixed `array[N] of T` is enough. |
| **Inline asm, floating-point environment, `FLT_EVAL_METHOD`, FP contraction, decimal FP** | Implementation-defined and optimizer-sensitive ([ARITH] §"Floating-point environment", [TYPES]); we pin binary64 and disable reliance on excess precision. |
| **Raw byte access, pointer/integer casts, `void*`, strict-aliasing exemptions** | The source of most C UB [PTR], [OBJ]; the surface is typed at every dereference. |

These omissions are deliberate, auditable, and each is a candidate for a later tier-3+ release once the differential corpus and the L3 backend are stable.

---

## Summary — recommended first subset

Build **c-ll v1** as: signed 32-bit `int` + binary64 `float`; `let NAME as TYPE be EXPR` declarations (mandatory initializer); `struct` definitions with fixed typed fields; typed `pointer to T` with only `address of`, `value at`, `item i of`, `member f via`, `null pointer`, and bounds-checked pointer `plus`/`minus`; `allocate`/`free` with zero-fill; top-level typed functions with positional call-by-value arguments and recursion; `if`/`otherwise`/`end if`, `repeat while`, `repeat for … below …`, `stop the loop`, `skip to the next item`, `give back`; single-precedence left-to-right word operators with mandatory parentheses and **explicit `cast`** for all conversions. Every C UB case becomes a checked, source-located error; evaluation order is pinned left-to-right; widths/layout are pinned rather than implementation-defined.

This is the smallest surface that exercises all of L2 (types, structs, static checking) and L3 (addresses, stores, allocation, layout) while keeping the English surface's AST, semantics, tests, and behavior byte-for-byte unchanged. Before writing the parser, close the oracle gap (§6.1) — a differential test against `gcc -std=c11` with UBSan/ASan is the acceptance criterion, not a stretch goal.
