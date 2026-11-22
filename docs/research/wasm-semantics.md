# Grounding research — WebAssembly semantics for the llang backend

**Status.** Grounding document for extending `src/llang/compiler.py` beyond its current
i32-only subset (integer literals, variables, arithmetic/comparisons, `if`/`while`/
`break`/`continue`, user calls, assignments, integer globals). Per
[`../METHOD.md`](../METHOD.md) and [`README.md`](README.md): authority first, inline
citations, "when a design doc and the implementation disagree, the code wins."

**Reference language and authoritative sources.** The WebAssembly 1.0 (MVP) spec —
overview, binary format, types, instructions, execution — is the spec we target
(preamble `\0asm` + version `\x01\0\0\0`, [Modules](https://webassembly.github.io/spec/core/binary/modules.html#binary-module)).
Executable oracles: Node.js (V8) present at `v24.18.0`; WABT tools if installable
(`wasm-validate`, `wasm2wat`, `wasm-interp`, [WABT README](https://github.com/WebAssembly/wabt#wabt-the-webassembly-binary-toolkit)).
MDN is used only for embedding-level facts (Module/Instance/Memory/Table,
[Concepts](https://developer.mozilla.org/en-US/docs/WebAssembly/Guides/Concepts);
traps surfacing as `WebAssembly.RuntimeError`,
[RuntimeError](https://developer.mozilla.org/en-US/docs/WebAssembly/Reference/JavaScript_interface/RuntimeError)).

**Key constraint we design under.** WASM has four numeric types and opaque
references, a stack machine with *structured* control flow, a byte-addressable
linear memory, and a separate table of references; there is no GC in MVP, no
dynamic type tags, no host I/O, and traps are uncatchable by WASM code
([Overview](https://webassembly.github.io/spec/core/intro/overview.html)). Every
llang dynamic value and every llang runtime error must therefore be *encoded* by our
compiler, not supplied by WASM.

---

## 1. Authoritative summary of the WASM constructs we need

### 1.1 Module skeleton and section plumbing
A module is a preamble followed by optional sections; each section is
`id:byte, len:u32, contents`, with **prescribed order**
type(1) → import(2) → function(3) → table(4) → memory(5) → tag(13) → global(6) →
export(7) → start(8) → element(9) → data-count(12) → code(10) → data(11); custom(0)
may appear anywhere ([Sections](https://webassembly.github.io/spec/core/binary/modules.html#sections),
[Modules](https://webassembly.github.io/spec/core/binary/modules.html#binary-module)).
Constraints that bite a hand-written emitter:
- `function` section length MUST equal `code` section length; each code entry's size
  MUST equal its byte length ([Function](https://webassembly.github.io/spec/core/binary/modules.html#binary-funcsec),
  [Code](https://webassembly.github.io/spec/core/binary/modules.html#binary-codesec)).
  The current compiler satisfies this by emitting one type per function and one code
  body per definition (`Compiler.compile`, lines 317–340).
- If any data index (`memory.init`/`data.drop`) occurs in code, a **data-count
  section (12)** must be present and match the number of data segments
  ([Data Count](https://webassembly.github.io/spec/core/binary/modules.html#binary-datacntsec)).
  We can avoid it entirely by using only *active* data segments (no bulk-memory
  initialization in code).
- Types: `i32 = 0x7F`, `i64 = 0x7E`, `f64 = 0x7C`, `funcref` heap type `0x70`;
  a function type is `0x60 + vec(params) + vec(results)`; limits `0x00 min` or
  `0x01 min max` (i32 domain); globaltype is `valtype + mut` with `mut = 0x01`
  for mutable; externtype tag bytes `0x00 func`, `0x01 table`, `0x02 mem`, `0x03
  global`, `0x04 tag`
  ([Types](https://webassembly.github.io/spec/core/binary/types.html)).

### 1.2 Linear memory — the heap for text, lists, maps
A memory instance is a sequence of bytes whose length is always a multiple of the
**page size 65 536 (64 KiB)**; bytes are read/written by load/store instructions at
any (even unaligned) byte address; out-of-bounds access **traps**
([Memory Instances](https://webassembly.github.io/spec/core/exec/runtime.html#memory-instances),
[Overview](https://webassembly.github.io/spec/core/intro/overview.html)). Declare one
memory in section 5: `vec([limits])`, e.g. `0x00 0x01` = min 1 page; prefer an
explicit max (`0x01 min max`) for predictable failure. Relevant opcodes
([Instructions](https://webassembly.github.io/spec/core/binary/instructions.html#memory-instructions)):
`i32.load 0x28`, `i32.load8_u 0x2D`, `i32.load16_u 0x2F`, `i32.store 0x36`,
`i32.store8 0x3A`, `i32.store16 0x3B`, `memory.size 0x3F`, `memory.grow 0x40`
(each load/store is followed by a `memarg` = `uleb align, uleb offset`; bit 6 of
`align` selects a non-default memory index). `memory.grow` returns the old size in
pages or `-1` on failure — it does not trap, so our allocator must check for `-1`.
Bulk ops `memory.copy 0xFC 10` and `memory.fill 0xFC 11` are useful for copying
strings/lists and are enabled by default in V8 and WABT
([WABT README, Supported Proposals](https://github.com/WebAssembly/wabt#supported-proposals)).
MDN describes Memory as a growable byte buffer manipulated by low-level instructions
([Concepts](https://developer.mozilla.org/en-US/docs/WebAssembly/Guides/Concepts)).

### 1.3 Data segments — static string/constant pool
Section 11 holds data segments. The MVP-simple *active* form is
`0x00 + offset_expr + vec(byte)` copied into memory 0 at instantiation
([Data Section](https://webassembly.github.io/spec/core/binary/modules.html#binary-datasec);
the offset expression is an `i32.const` followed by `0x0b`,
[Expressions](https://webassembly.github.io/spec/core/binary/instructions.html#binary-expr)).
Each llang string literal becomes one active segment; the compiler records its
`(byte_offset, byte_length)` as the literal's compile-time value. Passive segments
(`0x01`) plus `memory.init` are optional and would require the data-count section —
avoid them in v1. Instantiation traps if an active segment's offset+size exceeds the
memory's initial size, so compute the initial page count from the total static pool.

### 1.4 Table + `call_indirect`, function types — first-class functions, aliases, `apply`
A table is an array of opaque *references*, distinct from linear memory; it is the
mechanism for dynamic dispatch by a runtime index
([Overview](https://webassembly.github.io/spec/core/intro/overview.html),
[Table Instances](https://webassembly.github.io/spec/core/exec/runtime.html#table-instances)).
Declare in section 4: `vec([reftype 0x70 (funcref) + limits])`, e.g.
`0x70 0x00 uleb(N)`; populate with an **active element segment**, section 9 form 0:
`0x00 + offset_expr + vec(funcidx)`
([Element Section](https://webassembly.github.io/spec/core/binary/modules.html#binary-elemsec)).
`call_indirect typeidx tableidx` (`0x11`) pops the dynamic table index **on top of
the ordinary arguments** (stack: `args..., i32_index`) and traps if the index is
out of bounds, the slot is null, or the callee's type does not match `typeidx`
([Control Instructions](https://webassembly.github.io/spec/core/binary/instructions.html#binary-instr-control)).
`table.get 0x25`, `table.set 0x26`, `table.size 0xFC 16`, `table.grow 0xFC 15`
exist for runtime mutation
([Table Instructions](https://webassembly.github.io/spec/core/binary/instructions.html#binary-instr-table)).
Because WASM only does typed indirect calls, **all llang functions must share one
uniform signature** (see §2.5) — that is what makes function values, aliases and
`apply` representable. Direct calls keep `call funcidx` (`0x10`), which the current
compiler already emits (line 196).

### 1.5 Global section — mutable bindings and the allocator bump pointer
Section 6 entries are `valtype + mut + init_expr`
([Global Section](https://webassembly.github.io/spec/core/binary/modules.html#binary-globalsec)).
Globals are module-private unless exported/imported; globals are initialized during
instantiation ([Module Instances](https://webassembly.github.io/spec/core/exec/runtime.html#syntax-moduleinst)).
We will add: `__heap_end : mut i32` (bump allocator cursor, initialized just past
the last static data segment), and optional `__err_kind`, `__err_pos`, `__err_ptr`,
`__err_len` for error reporting. The existing compiler already emits immutable i32
globals for top-level integer literals (`global_section`, lines 329–332); those
become mutable value slots once bindings can hold non-i32 values. `global.get 0x23`
/ `global.set 0x24` are used at lines 163 and 213.

### 1.6 Imports/exports — the host boundary
Import section (2) entry: `module_name, field_name, externtype`
([Import Section](https://webassembly.github.io/spec/core/binary/modules.html#binary-importsec));
export section (7) entry: `name, kind_byte, index`
([Export Section](https://webassembly.github.io/spec/core/binary/modules.html#binary-exportsec)).
The embedder supplies host functions for imports; in JS, WASM can call imported JS
functions synchronously and JS calls exports synchronously
([Concepts](https://developer.mozilla.org/en-US/docs/WebAssembly/Guides/Concepts)).
This is the only legitimate path for `show`, `fail`, and builtins that need host
services — and using it is a deliberate trust-model change (see §5). Function
indices are a single namespace: imported functions come first, then defined ones,
which shifts every `funcidx` the current compiler assigns in `Compiler.compile`
(lines 307–310) — the index allocation must be redone once imports exist.

### 1.7 Traps and exceptions
A computation result is values, a thrown exception, or a **trap**
([Results](https://webassembly.github.io/spec/core/exec/runtime.html#syntax-result));
traps "immediately abort execution", "cannot be handled by WebAssembly code", and
are reported to the outside environment
([Overview, Traps](https://webassembly.github.io/spec/core/intro/overview.html));
in JS this surfaces as `WebAssembly.RuntimeError`
([MDN RuntimeError](https://developer.mozilla.org/en-US/docs/WebAssembly/Reference/JavaScript_interface/RuntimeError)).
Trap sources we will meet: `unreachable 0x00`, OOB memory access, `i32.div_s 0x6D`
/ `i32.rem_s 0x6F` on zero (and overflow for `div_s`), bad `call_indirect`.
The post-MVP exception proposal adds tag section (13), `throw 0x08`,
`throw_ref 0x0A`, `try_table 0x1F` and `catch/catch_all`
([Control Instructions](https://webassembly.github.io/spec/core/binary/instructions.html#binary-instr-control),
[Tags](https://webassembly.github.io/spec/core/binary/types.html#binary-tagtype));
WABT validates/emits it by default but `--disable-exceptions` exists
([wasm-validate(1)](https://webassembly.github.io/wabt/doc/wasm-validate.1.html)).
**MVP traps are not llang `expect` exceptions** (§3.4, §5).

---

## 2. Concrete value representation proposal

### 2.1 Design goal and legacy compatibility
Today every expression leaves exactly one flat `i32`: `i32.const` for literals
(`0x41`, line 151/153), `local.get`/`global.get` for variables, raw arithmetic
(§`OPCODES`). llang is dynamically typed with `nothing`, booleans, arbitrary-size
integers (Python semantics), floats (`DIV`, `POW`, `rounded`), text, lists and maps
([GRAMMAR.md](../../docs/GRAMMAR.md), `interpreter.py` `_eval`, lines 654–682). A
single i32 cannot carry all of that. We keep the *one-value-slot* shape by changing
the slot's meaning to a **tagged value**; existing integer-only codegen becomes a
special case where the tag is statically known and can be omitted (monomorphized
fast path), so today's tests keep passing byte-for-byte if desired.

### 2.2 Recommended ABI: two-word `(tag: i32, payload: i32)` values
Each llang value occupies **two operand-stack words / two function parameters /
two return values** (multi-value is enabled by default in V8 and WABT; see WABT
README "multi-value ✓"). Tag constants (our own, not WASM's):

| Tag | Meaning | `payload` interpretation |
|---|---|---|
| 0 | small integer | signed i32 (fast path; matches today's output) |
| 1 | boolean | 0 = false, 1 = true |
| 2 | nothing | unused (0) |
| 3 | float | byte offset of an 8-byte `f64` cell in linear memory |
| 4 | text | byte offset of UTF-8 bytes; length stored in heap header |
| 5 | list | byte offset of an array record (header: length, capacity, element slots) |
| 6 | map | byte offset of an ordered array of key/value pairs |
| 7 | function | table index of a `funcref` (uniform signature) |

All composite tags point into linear memory; the **first i32 word at the pointer is
a header** (length/capacity for text/list/map), so `(tag, payload)` is enough to
recover length without a third word. An alternative one-word encoding — 3-bit tag
in the low bits plus a 29-bit signed immediate, heap spill for larger numbers — is
possible and would preserve single-i32 function signatures (avoiding multi-value
JS return arrays), but costs masking/shifting on every operation and silently
overflows `int` arithmetic. **Recommendation:** adopt the two-word ABI for the
slow path, with tag-0 unboxed fast path for monomorphized integer functions. This
also fixes the current divergence where `DIV` (`0x6D`) truncates even though the
interpreter returns a Python float (`_arithmetic`, line 766–769).

### 2.3 Static text in memory (pointer + length)
For each `Literal` whose value is `str`, emit one active data segment with the
UTF-8 bytes of the *escaped-decoded* text, at the next aligned offset; store
`(tag=4, payload=byte_offset)` as the literal's compile-time value. Length is
read from memory (or emitted as a constant known to the compiler). Dynamic text
(e.g. `text of`, `plus` on two texts) is produced into the bump heap:
`addr = global.get __heap_end`, check `addr + n <= memory.size * 65536`, grow if
needed, `memory.copy`/`memory.fill` the bytes, update `__heap_end`, return
`(4, addr)`. Interning is optional; identity is never observable in llang v1
(no general identity operator, [SEMANTIC-DECISIONS.md §1](../../docs/SEMANTIC-DECISIONS.md)).

### 2.4 Lists and maps (linear-memory records)
- **List** record at `p`: `i32[p]=length`, `i32[p+4]=capacity`, elements at
  `p+8 + 4*i`, each element occupying two i32 words for `(tag,payload)`. `a list
  of ...` evaluates elements left-to-right (`interpreter.py` line 666), writes
  them in order, and returns `(5,p)`. `the length of` reads `i32[p]`.
- **Map** record at `p`: `i32[p]=number_of_pairs`, followed by consecutive
  `(key_tag,key_payload,val_tag,val_payload)` quadruples **in insertion order** —
  this is exactly the interpreter's dict semantics and the locked decision to
  guarantee insertion order ([SEMANTIC-DECISIONS.md §4](../../docs/SEMANTIC-DECISIONS.md)).
  Lookup is a linear scan calling a `lang_equal` helper on tagged values; missing
  keys and out-of-range indices become llang problems (§3.4). A map key can be any
  hashable llang value, so a helper `lang_hashable` mirrors the interpreter's
  `hash(key)` check (line 671–675).
- **Booleans/nothing**: tags 1 and 2; `nothing` is distinct from every other tag,
  which implements `is nothing` as the only singleton check and avoids Python's
  `True == 1` surprise that `_equal` deliberately guards against (lines 798–803).
- **Truthiness**: helper `lang_truthy(tag,payload)` implements `bool(value)`:
  nothing false, false false, zero false, empty text/list/map false; note
  "empty" excludes `0` and `false` per the locked rule
  ([SEMANTIC-DECISIONS.md §4](../../docs/SEMANTIC-DECISIONS.md)).

### 2.5 Uniform function signature, table and dynamic calls
Every compiled llang function gets one type:
`(i32,i32,i32,i32,...) -> (i32,i32)` — i.e. N tagged parameters (2 words each)
and one tagged result — or the simpler universal variadic shape
`(i32 ptr_to_args, i32 arg_count) -> (i32 tag, i32 payload)` with an argument
frame in linear memory. Choose **one** and use it for *all* functions so a single
`typeidx` works with `call_indirect`. Fill table 0, slot `i` = function `i` via an
element segment. Direct calls remain `call`; `apply` and function values compile to
`call_indirect <typeidx> 0x00` after pushing the table index last
(§1.4). Function aliases bind to the same function index, mirroring
[GRAMMAR.md §Function aliases](../../docs/GRAMMAR.md).

### 2.6 Builtins: helper functions, not magic
Compile each closed-vocabulary builtin to a `call` to an internal helper function
(or an import where host access is required, §5). Builtins are SYNONYMS mapping to
one canonical implementation, exactly as the interpreter's `BUILTINS` table does
(`interpreter.py` lines 309–345; [GRAMMAR.md §Builtins](../../docs/GRAMMAR.md)).
Pure helpers (`uppercase`, `join`, `split`, `sort`, `sum`, `keys`, `values`,
predicates) live in the module; `read_file`/`write_file` and foreign modules must
be imports and are deferred (§5).

---

## 3. Evaluation-order and boundary rules

### 3.1 AST → operand stack (left-to-right)
WASM is a postfix stack machine: each instruction pops its arguments and pushes its
results; control flow is structured and branches may only target enclosing
constructs ([Overview, Instructions/Control](https://webassembly.github.io/spec/core/intro/overview.html)).
Rule: **the code for a node leaves that node's value(s) on the stack and nowhere
else**; compile children in the interpreter's evaluation order:
- `Binary`: emit `left`, then `right`, then the op — matches `_eval_binary` lines
  739–740. The current compiler already does this (lines 184–186).
- `Set`: evaluate RHS, then `local.set`/`global.set` (lines 209–213).
- `Index`: evaluate `collection`, then `key` (lines 685–686); `SetItem` evaluates
  `target, key, value` in that order (lines 562–565); `AddTo` evaluates `target`
  then `value` (lines 555–557); `ListLiteral`/`MapLiteral` evaluate elements in
  source order (lines 666, 669–675). Emitting them in any other order changes
  observable behavior when operands have side effects (calls).
- `Call`: resolve the callable, then emit args left-to-right (lines 820–824), then
  `call`/`call_indirect`. Note the spec's stack convention: for `call_indirect`
  the table index is pushed **after** all arguments, so emit args, then index.
- `local.tee 0x22` is useful to keep a computed value while testing it without
  reordering evaluation.

### 3.2 Short-circuit operators cannot use `select`
`select 0x1B` evaluates **both** arms before choosing
([Parametric Instructions](https://webassembly.github.io/spec/core/binary/instructions.html#binary-instr-parametric)),
but interpreter `AND`/`OR` short-circuit *and return an operand*, not a coerced
boolean (lines 731–737; decision #2 in
[SEMANTIC-DECISIONS.md](../../docs/SEMANTIC-DECISIONS.md)). Compile as: evaluate
left, `local.tee L`, `lang_truthy`, `if (result tag/payload)` … else evaluate right …
`end`, leaving the chosen tagged value on the stack. The current compiler instead
emits bitwise `i32.and 0x71`/`i32.or 0x72` (lines 100–101), which is correct only
for 0/1 booleans and loses operand-returning semantics — a known gap to close in
the corpus (§4).

### 3.3 Escaping and UTF-8 — byte length vs code-point length
The lexer/parser decode escape sequences (`\n`, `\t`, `\"`, `\\`) into Unicode text
([GRAMMAR.md §Lexical](../../docs/GRAMMAR.md)). Data segments store **bytes**
([Data Section](https://webassembly.github.io/spec/core/binary/modules.html#binary-datasec)),
so the compiler must UTF-8 encode the decoded text and store `byte_length`. The
interpreter indexes text by Python **code point** (`collection[key]`, line 693) and
`the length of` returns `len(str)` — the code-point count. Non-ASCII text therefore
requires either (a) a code-point-to-byte-offset side table per string, or (b) a
UTF-8 decoding helper that walks bytes for `item`/`length`/`slice`. Option (b) with
a shared `lang_text_index(s, i)` helper is recommended; constant-folded ASCII
literals can use the fast byte path. Never conflate WASM `i32.load8_u` with a
code-point: WASM memory is bytes ([Memory Instances](https://webassembly.github.io/spec/core/exec/runtime.html#memory-instances)).
Our `name()` encoder (`utf-8` + byte length, compiler lines 75–77) is already
byte-correct for export names; reuse that discipline for string bytes.

### 3.4 Runtime errors: traps vs helper calls
Two classes:
1. **Genuine WASM traps** (OOB access, bad `call_indirect`, `div_s` by zero,
   `unreachable`) — free, but they abort immediately, carry no llang source
   location, and are uncatchable in MVP
   ([Overview, Traps](https://webassembly.github.io/spec/core/intro/overview.html);
   [Runtime Structure](https://webassembly.github.io/spec/core/exec/runtime.html#syntax-result)).
   They are appropriate for *bugs in the generated code*, not for llang program
   errors.
2. **llang program errors** must be source-located: `RuntimeErrorLang` /
   `ProblemSignal` with `node.pos` (`interpreter.py` lines 688–699, 754–779).
   Represent them by calling an imported host function
   `lang_fail(kind_ptr, kind_len, msg_ptr, msg_len, line, col)` that throws a JS
   error decorated with the llang line, or by writing an error record into
   `__err_*` globals and returning tag 7/sentinel to the caller. For *expected*
   failures (`expect`, `require`), prefer the global-flag scheme or post-MVP
   `try_table`/tags; a raw trap cannot implement `expect`
   ([Control Instructions](https://webassembly.github.io/spec/core/binary/instructions.html#binary-instr-control)).
   Store the source line as a compile-time `i32.const` immediately before each
   fallible helper call (the AST already carries `pos`, and `CompileUnsupported`
   uses `node.pos.line` at compiler lines 296–304).

### 3.5 Boundary invariants to preserve
- Integer division: interpreter `DIV` returns float and `FLOORDIV` floors (Python),
  but the current compiler maps both to `i32.div_s` (truncating toward zero, traps
  on zero) — pick explicit helpers `lang_div` (f64) and `lang_floordiv` (floor) to
  restore parity; the corpus must pin negative-operand cases.
- Equality: `lang_equal` must keep `_equal`'s rule that booleans never equal
  numbers (line 801), and handle text by code-point sequence, lists/maps
  structurally only if that is ever exposed — v1 has no identity operator.
- All heap writes go through the bounds-checked allocator; `memory.grow` failures
  (returns `-1`) must become a source-located llang failure, not a silent OOB trap.
- Exported functions keep their llang names; the JS runner in
  `tools/run_wasm.js` currently coerces all arguments with `Number()` and prints
  a single numeric result, so it must be extended to marshal tagged values and to
  expose memory for string/list/map results.

---

## 4. Verification plan

### 4.1 Tools and exact commands
Node is available; WABT is **not currently installed** on this host (`Get-Command
wat2wasm,wasm-validate,wasm2wat` returned nothing). Install via `apt install wabt`,
`brew install wabt`, `pip install wabt-package`, or a GitHub release binary
([WABT README, Installing prebuilt binaries](https://github.com/WebAssembly/wabt#installing-prebuilt-binaries)).

```sh
# 0. Confirm oracles
node --version                         # observed: v24.18.0
wasm-validate --version                # after installing wabt

# 1. Compile a corpus program (existing CLI)
python -m llang.compile_cli corpus/t01.ll -o out/t01.wasm --report out/t01.txt
#    (source: src/llang/compile_cli.py — writes .wasm and an unsupported-construct report)

# 2. Structural validation oracle  (WABT)
wasm-validate out/t01.wasm
wasm2wat out/t01.wasm -o out/t01.wat          # human-readable disassembly
wasm2wat out/t01.wasm -f --generate-names     # folded form, names for indices
wasm-objdump -x out/t01.wasm                  # section/import/export/memory dump
wat2wasm out/t01.wat -o out/t01.roundtrip.wasm # round-trip check
cmp out/t01.wasm out/t01.roundtrip.wasm

# 3. Execution oracle — Node/V8 (already used by tests/test_compiler.py)
node tools/run_wasm.js out/t01.wasm <export> <args...>
#    e.g. current baseline:
node tools/run_wasm.js out/fact.wasm fact 5     # -> 120
#    or an inline validator harness (replaces tools/run_wasm.js once tags exist):
node -e 'const fs=require("fs");const b=fs.readFileSync("out/t01.wasm");
  const m=new WebAssembly.Module(b);            // validation happens here
  const i=new WebAssembly.Instance(m,{});       // LinkError if imports missing
  console.log(i.exports.my_export(/* tagged args */));'

# 4. Execution oracle — WABT interpreter (independent of V8)
wasm-interp out/t01.wasm --run-all-exports
wasm-interp out/t01.wasm --run-all-exports --trace

# 5. Interpreter baseline (must match)
python -m llang.cli corpus/t01.ll

# 6. Full Python test suite
python -m unittest discover -s tests -v
#    or: python -m pytest tests -q
```
For every corpus file, automate the check as: parse/compile → assert
`result.unsupported == []` (as `tests/test_compiler.py` `execute()` does, line 24)
→ `wasm-validate` exit 0 → interpreter output == Node output == `wasm-interp`
output. Keep the disassembly (`.wat`) in review for any codegen change: a wrong
opcode or missing `end`/`else` shows up immediately in `wasm2wat`.

### 4.2 Differential corpus (must compile and run identically under interpreter and WASM)
Each row is a small `.ll` program; the exported function returns a pinned value.
Tier 0 is the current baseline; Tiers 1–4 are the required extension.

| ID | Construct | Example (llang) | Pinned result / check |
|---|---|---|---|
| T0-1 | arithmetic + while | `fact` from `tests/test_compiler.py` | `fact(5)=120` |
| T0-2 | if/else | `choose` from `tests/test_compiler.py` | `choose(10)=1`, `choose(3)=0` |
| T0-3 | globals | `use_base` from `tests/test_compiler.py` | `use_base(5)=15` |
| T0-4 | break/continue | `first_big`, `skip_even` | `3`, `9` |
| T1-1 | text literal | `define function greet taking name / give back "Hello, " plus name / end function` | `"Hello, Ada"` |
| T1-2 | escapes + UTF-8 | `give back "caf\u00e9\n"` (source `"café\n"`) | length 5 code points / 6 bytes; index 3 → `é` |
| T1-3 | text ops | `uppercase of`, `lowercase of`, `trim`, `find in text`, `replace in text` | same as Python `str` methods |
| T1-4 | number↔text | `to text`, `to number` | `to number("42")=42`, error on `"x"` |
| T2-1 | list literal/index/length | `set xs to a list of 1, 2, 3 / give back item 1 of xs` | `2`; `length=3` |
| T2-2 | list mutation | `add 4 to xs`, `set item 0 of xs to 9` | `[9,2,3,4]` via a `join`-like probe |
| T2-3 | for-each snapshot | loop over `xs` while mutating `xs` | same items as interpreter (snapshot rule) |
| T2-4 | list builtins | `sort`, `sum`, `minimum`, `maximum`, `reverse`, `join`, `split` | pinned outputs from `tests/test_language_additions.py` |
| T3-1 | map literal/index | `set m to a map with "a" mapped to 1, "b" mapped to 2 / give back item "b" of m` | `2` |
| T3-2 | insertion order | `keys of m` | `["a","b"]` |
| T3-3 | missing key | `item "z" of m` inside `expect` | `missing_key` handler runs; no abort |
| T3-4 | map mutation | `set item "a" of m to 5` | `{"a":5,"b":2}` |
| T4-1 | predicates | `is empty`, `is nothing`, `is a number`, `is text`, `is a list`, `is a map` | booleans match interpreter |
| T4-2 | short-circuit | `0 and (fail-producing expr)` / `1 or ...` | operand returned, right side skipped |
| T4-3 | truthiness | `not 0`, `not ""`, `not []`, `not nothing` | all `true` |
| T4-4 | aliases + apply | `also known as` names and `apply with fn=..., args=...` | same value via each name |
| T4-5 | division parity | `DIV`, `FLOORDIV`, `MOD` with negative operands and zero | interpreter result; zero → source-located error |
| T4-6 | error location | `item 5 of a list of 1` | error message includes correct source line |
| T5-1 | import boundary | `show` / `fail` via imported helper | JS-side side effect, line-tagged error |
Programs that use `use the foreign shell module`, `read text from`, `write text to`,
or file/package APIs are deliberately **not** in this corpus (§5).

---

## 5. What should stay interpreter-only (and why)

The following should remain supported only by the Python interpreter in this phase.
The reason in every case is either "WASM MVP has no primitive for it" or "doing it
in WASM changes the language's trust/semantics", not mere difficulty.

1. **Foreign modules — `use the foreign ... module`, especially `shell`** (`foreign.py`):
   they run host commands, read environment variables and can execute arbitrary
   programs. WASM runs in a sandbox and has no host I/O; exposing these would
   require powerful imports and would break the security property that "no llang
   program can execute a host command unless it explicitly says `use the foreign
   shell module`". The host bridge is Python-only by design ([Overview,
   Embedder](https://webassembly.github.io/spec/core/intro/overview.html)).
2. **File builtins `read text from` / `write text to`** (`_b_read_file`,
   `_b_write_file`, lines 160–175): need host filesystem imports, are
   non-deterministic, and would make differential testing environment-dependent.
3. **`show`/`print`**: the current compiler intentionally emits `drop` and reports a
   note ("show is a no-op in WASM (no host I/O)", lines 218–222). Making it real
   requires an imported host function; until that import is part of a specified,
   audited ABI, output belongs to the interpreter.
4. **`expect`/`fail` with catchable, typed problems, and `require` assertions**:
   MVP traps abort unconditionally and are uncatchable by WASM code
   ([Overview, Traps](https://webassembly.github.io/spec/core/intro/overview.html)).
   Full parity needs either the post-MVP exception-handling proposal (tags +
   `try_table`, [Control Instructions](https://webassembly.github.io/spec/core/binary/instructions.html#binary-instr-control))
   or a flag/globals protocol that changes control flow. Keep these interpreter-only
   until one convention is locked; do **not** silently compile them to `unreachable`.
5. **Full first-class functions / higher-order `apply` with arbitrary closures**:
   `call_indirect` supports uniform signatures only; closures capturing an
   environment require heap-allocated closure records plus a table discipline.
   A restricted, monomorphic `apply` with table indices is compilable; full
   closure semantics stay interpreter-only in v1 (see decision #6,
   [SEMANTIC-DECISIONS.md](../../docs/SEMANTIC-DECISIONS.md)).
6. **Python-faithful edge semantics that the MVP cannot express cheaply**:
   arbitrary-precision integers, late-bound free variables, generator/on-demand
   evaluation, mutable default arguments, and `return`/`break` inside `always`
   (forbidden by design, decision #11). These live in the interpreter unless a
   typed helper ABI is specified first.
7. **Tooling surfaces unrelated to execution** — formatter, linter, LSP, package
   resolution, synonyms/vocabulary normalization: they operate on source/AST and
   are inherently host-side; the WASM module only consumes the canonical AST.
   The compiler's `unsupported`/`notes` reports must keep flagging any deferred
   construct rather than dropping it (current behavior, `Compiler.flag`, lines
   296–304).

**Exit criterion for the next phase:** every corpus row in §4 has
`unsupported == []`, passes `wasm-validate`, round-trips through `wasm2wat`, and
produces the same pinned result under `python -m llang.cli`, `node tools/run_wasm.js`
and `wasm-interp`; everything in §5 still produces an explicit, source-located
"not compilable" report.
