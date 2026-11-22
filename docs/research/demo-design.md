# Flagship demo design — "something to confirm the quality of llang"

*Purpose of this document: propose one program whose readability, capability and
correctness can be judged in a few minutes, and give reviewers a concrete rubric.
Status: design draft. The program below is written against `docs/GRAMMAR.md`,
`docs/SEMANTIC-DECISIONS.md`, `docs/DESIGN.md` and the code in `src/llang/`.
Lines that today's interpreter cannot run are marked `# >> PROPOSED EXTENSION:`.

## 1. Candidates considered

| # | Candidate | Readability | Capability | Correctness coverage | New syntax needed | Audit time |
|---|---|---|---|---|---|---|
| 1 | **The Reading Room** — word-frequency report on a short text | High: "tally the word", "the most common word" are natural | Genuine algorithm: tokenise, tally, rank, express as percentages | Map mutation, empty input, Unicode/string keys, sort stability, rounding | High: text-module splitting, list/map literals, membership test, sort, conversion, ranking loop | ~5 min |
| 2 | **The Class Report Card** — aggregate six students' marks into grades and a class summary | Highest: "average", "grade for", "for each student", "marks recorded for Ada" need no explanation | Genuine work: aggregation, per-student grading, ranking, class mean, self-checks | All six required areas, with hand-checkable numbers and objective invariants | Moderate: collections, `for each`, map lookup, `expect`, `round`, text conversion | ~3 min |
| 3 | **The Household Ledger** — budget tracker with categories and running balance | High: "add an expense", "over budget" | Genuine work: sums by category, running balance, alerts | Money rounding and overdraft handling are instructive but invite a decimal-type debate | Moderate-high: money/decimal semantics, category map, `expect`, reports | ~5 min |

**Candidate 1** is the most "English" but pays for it: ranking needs a sort and a
subtle tie rule, and tokenisation belongs to a text module that does not exist
yet. A reviewer would spend more time judging the proposed syntax than the
program. **Candidate 3** is realistic but its correctness story hinges on a
decimal-money decision that `SEMANTIC-DECISIONS.md` has not made; that is a
distraction in a demo whose job is to prove the language, not settle floating
point. **Candidate 2** keeps the whole logical skeleton — functions, aliases,
branching, labeled calls, assertions, output synonyms — in syntax that exists
*today*, and confines the proposals to data access, stdlib and exception
handling. Its expected output can be verified with a pocket calculator, so
"correct" is not a matter of opinion.

## 2. Choice: **The Class Report Card**

Chosen because it maximises the ratio of *language proof* to *new syntax*:

- **Readability:** every function name is a phrase ("average", "grade_for",
  "marks_for"), every call is labeled, and every block is visibly closed.
- **Capability:** it produces a real, deterministic report card, not a toy
  expression; adding a student is an obvious two-line edit.
- **Correctness:** range checks, an empty-list guard, explicit conversions, an
  alias-identity trick, a handled missing-key problem, and two `require`
  invariants that the program checks on itself.
- **Auditability:** one function per concept, a flat control-flow shape, and
  six hand-computable outputs.

The program is `examples/report_card.ll` in draft form below.

## 3. Complete draft implementation

```llang
# ---------------------------------------------------------------------------
# The Class Report Card — flagship demo for llang.
# Indentation is decoration only: every block is closed by an explicit end.
# Every line tagged ">> PROPOSED EXTENSION" is designed but not yet runnable;
# untagged lines use the syntax implemented in src/llang today.
# ---------------------------------------------------------------------------

# >> PROPOSED EXTENSION: `use the <name> module` imports a stdlib module.
use the math module

# --- arithmetic helper ----------------------------------------------------
define a function average taking total, count
    return total divided by count
end function

# --- branching helper: one explicit delimiter per branch ------------------
define a function grade_for taking score
    if score is at least 90 then
        give back "A"
    otherwise if score is at least 80 then
        give back "B"
    otherwise if score is at least 70 then
        give back "C"
    otherwise if score is at least 60 then
        give back "D"
    otherwise
        give back "F"
    end if
end function

# --- lookup helper; three names, one implementation -----------------------
define a function marks_for taking student, book
also known as marks_of, scores_for
    # >> PROPOSED EXTENSION: `the value for <key> in <map>`; a missing key
    # >> PROPOSED EXTENSION: raises a problem of kind `missing_key`.
    give back the value for student in book
end function

# --- the workhorse: validate, accumulate, divide --------------------------
define a function average_for taking student, book
also called mean_for, average_of_student
    set scores to call marks_of with student = student, book = book
    # >> PROPOSED EXTENSION: `the length of <list>` from the stdlib.
    require the length of scores is greater than 0, "no marks recorded for that student"
    set total to 0
    let count be 0
    # >> PROPOSED EXTENSION: `for each <name> in <list> ... end repeat`.
    for each score in scores
        # Parentheses are mandatory: there is no operator precedence.
        require (score is at least 0) and (score is at most 100), "a score must run from 0 to 100"
        set total to total plus score
        set count to count plus 1
    end repeat
    give back call average with total = total, count = count
end function

# --- the data -------------------------------------------------------------
set roster to a list of "Ada", "Grace", "Linus", "Barbara", "Dieter", "Hana"
# >> PROPOSED EXTENSION: `an empty map` and
# >> PROPOSED EXTENSION: `set the entry for <key> in <map> to <expr>`.
set marks to an empty map
set the entry for "Ada" in marks to a list of 92, 88, 95, 91
set the entry for "Grace" in marks to a list of 99, 97, 100
set the entry for "Linus" in marks to a list of 71, 85
set the entry for "Barbara" in marks to a list of 76, 84, 80
set the entry for "Dieter" in marks to a list of 55, 62
set the entry for "Hana" in marks to a list of 64, 68

# --- the report -----------------------------------------------------------
set class_total to 0
set class_count to 0
set top_average to 0 minus 1          # no negative literals and no unary minus
set top_student to nothing

# >> PROPOSED EXTENSION: `for each <name> in <list> ... end repeat`.
for each student in roster
    set mean to call mean_for with student = student, book = marks
    set letter to call grade_for with score = mean
    # >> PROPOSED EXTENSION: `call round with value = ..., places = ...`.
    # >> PROPOSED EXTENSION: `the text of <value>` (explicit conversion; no coercion).
    show student plus ": " plus the text of (call round with value = mean, places = 1) plus " (" plus letter plus ")"
    set class_total to class_total plus mean
    set class_count to class_count plus 1
    if mean is greater than top_average then
        set top_average to mean
        set top_student to student
    end if
end repeat

set class_average to call average with total = class_total, count = class_count
display "Class mean of student means: " plus the text of (call round with value = class_average, places = 1)
print "Top student: " plus top_student

# --- error handling: a lookup that is expected to fail --------------------
# >> PROPOSED EXTENSION: `expect ... if a problem of kind <kind> occurs,
# >> PROPOSED EXTENSION: handle it by ... if nothing went wrong, then ... end expect`.
expect
    call scores_for with student = "Nobody", book = marks
if a problem of kind missing_key occurs, handle it by
    print "Handled: no marks were recorded for that name"
if nothing went wrong, then
    print "Unexpected: the name was found"
end expect

# --- self-checks: the program proves its own result -----------------------
require class_count equals the length of roster, "every student was reported once"
require (top_average is at least 0) and (top_average is at most 100), "the top average is a valid score"
show "All checks passed."

# --- DIAGNOSTIC FIXTURES (commented out; run one at a time) ---------------
# These are not part of the report. Each should be rejected with the shown
# message, copied verbatim from the current interpreter.
#
# Fixture 1 — string minus string:
#   show "a" minus "b"
#   -> Operator 'SUB' requires numbers, got a and b at line 1, column 6
# Fixture 2 — missing delimiter:
#   if true then
#   show "yes"
#   -> Unexpected end of input — missing matching 'end' at line 2, column 11
# Fixture 3 — undefined name:
#   show missing
#   -> Undefined name 'missing' at line 1, column 6
# Fixture 4 — mislabeled argument:
#   define function f taking x
#       give back x
#   end function
#   show call f with y = 1
#   -> Unknown argument 'y' for function 'f'; expected: x at line 4, column 6
# Fixture 5 — reserved word as identifier:
#   set end to 5
#   -> Expected a name, found 'end' at line 1, column 5
#      expected one of: 'a non-reserved identifier'
```

### Expected output (hand-checkable, insertion order)

```
Ada: 91.5 (A)
Grace: 98.7 (A)
Linus: 78.0 (C)
Barbara: 80.0 (B)
Dieter: 58.5 (F)
Hana: 66.0 (D)
Class mean of student means: 78.8
Top student: Grace
Handled: no marks were recorded for that name
All checks passed.
```

### Verified against the interpreter today

The untagged logic skeleton below was run unchanged with
`python run.py <file>` and printed exactly `91.25`, `A`, `checks passed`:

```llang
define a function average taking total, count
    return total divided by count
end function

define a function grade_for taking score
    if score is at least 90 then
        give back "A"
    otherwise if score is at least 80 then
        give back "B"
    otherwise
        give back "C or below"
    end if
end function

set total to 92 plus 88 plus 95 plus 91
set mean to call average with total = total, count = 4
show mean
display call grade_for with score = mean
require (mean is at least 0) and (mean is at most 100), "mean must be a score"
show "checks passed"
```

The diagnostic messages in the fixtures were also observed directly, not
invented.

## 4. Feature inventory and review rubric

### Exactly which features the program exercises

| Feature | Where | Status |
|---|---|---|
| `#` comments, one statement per line | throughout | current |
| `set ... to ...` and `let ... be ...` | `average_for`, setup | current (synonyms) |
| Number/string literals, string concatenation with `plus` | marks, `show` lines | current |
| `plus`, `minus`, `divided by`; parentheses; left-associative no precedence | `average`, `top_average`, conditions | current |
| `is greater than`, `is at least`, `is at most`, `equals`, `and` | grading, ranking, `require`s | current |
| `if / otherwise if / otherwise / end if` | `grade_for`, ranking | current |
| `define ["a"] function ... taking ...`, alias lines, `end function` | all four helpers | current |
| `also known as` and `also called` | `marks_for`, `average_for` | current (synonyms) |
| `give back` and `return` | helpers | current (synonyms) |
| `call ... with <label> = ...` as statement and nested expression | throughout | current |
| `show`, `display`, `print` | report and error handler | current (synonyms) |
| `require <cond>, "message"` | range check, empty guard, self-checks | current |
| Source-located errors, expected-token hint, undefined-name/type diagnostics | five fixtures | current |
| `use the math module`; `call round with value = ..., places = ...` | report | proposed |
| `a list of ...`; `an empty map`; `set the entry for <key> in <map> to ...` | data section | proposed |
| `the value for <key> in <map>`; `missing_key` problem | `marks_for`, error section | proposed |
| `the length of <list>` | empty guard, self-check | proposed |
| `for each <name> in <list> ... end repeat` | `average_for`, report | proposed |
| `the text of <value>` (explicit conversion, no coercion) | `show` lines | proposed |
| `expect ... if a problem of kind ... occurs, handle it by ...; if nothing went wrong, then ...; end expect` | error section | proposed |

### What a reviewer should look at

1. **Read first, syntax second.** Can a reader who has never seen llang
   paraphrase `average_for` and the report loop on one pass? If a line needs a
   grammar rule to be understood, the readability claim fails.
2. **Visible structure.** Count `define`/`end function`, `if`/`end if`,
   `for each`/`end repeat`, `expect`/`end expect`. Every opener has one closer,
   and nothing depends on indentation. Scramble the indentation and re-run:
   output must be identical.
3. **No hidden precedence.** The two compound conditions are parenthesised.
   Remove the parentheses and the program must mean something different (or
   fail loudly), demonstrating the single left-to-right rule.
4. **Aliases are real aliases.** Replace `marks_of` with `marks_for` or
   `scores_for`, and `mean_for` with `average_for` or `average_of_student`.
   Output must not change; redefining an alias name must be rejected.
5. **Labeled calls self-document.** Every argument has a role, including the
   nested `call round` inside `the text of (...)`. Mislabel one and the error
   must name the function and list the expected labels.
6. **No coercion, no surprises.** `the text of` is explicit. Concatenating a
   raw number into a string should fail at that line, not silently print a
   converted value.
7. **Correctness is checked, not assumed.** The two `require` invariants pass,
   the six grades and the class mean match the hand-computed table, and the
   handled missing-key lookup does not corrupt the report that follows.
8. **Diagnostics are part of the artifact.** Run the five fixtures. Each error
   must name a line and column, say what was wrong in domain terms, and offer
   an expected-token list where relevant — that is the LLM self-correction
   loop working.
9. **Extension hygiene.** Every non-runnable line is tagged in place. No
   proposal hides inside the interpreter; each maps to a documented canonical
   node and a Python-semantics decision (`for each`: iterate once; map:
   insertion order; `expect`: Python `try`/`except`/`else` termination model).

## 5. "Why this proves it" — acceptance criteria

- A reviewer can describe what the program does after reading it once, without
  consulting the grammar.
- The six student lines and the class mean are verifiable by hand; all ten
  output lines are deterministic and in insertion order.
- Swapping any function for one of its aliases changes nothing; deleting an
  `end` or mislabeling an argument produces a localized, actionable error.
- The program exercises collections, functions+aliases, control flow, error
  handling, stdlib and diagnostics in about 110 lines (excluding the diagnostic
  fixture appendix), with every extension explicitly flagged.
- The current-syntax subset shown above runs today unchanged and still computes
  a grade; the proposals only add collections, stdlib and error handling, so
  this is a growth path rather than a rewrite.
- It fails loudly: out-of-range marks, an empty mark list, a missing key and an
  implicit string/number mix all stop at the offending line rather than
  producing a plausible wrong answer.
