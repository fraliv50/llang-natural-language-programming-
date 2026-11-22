"""Tests for the c-ll surface.

Run with: python -m unittest discover -s tests

The native C toolchain (gcc/clang) is not installed on this host, so the
*differential* oracle below is a Python reference implementation of each
program's C semantics.  See docs/CLL.md, "Verification".
"""

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llang.cll import compile_c_source, run_c_source  # noqa: E402
from llang.errors import LangError  # noqa: E402


def source_for(body: str, definitions: str = "") -> str:
    """Wrap statements in a canonical main function plus its invocation."""
    return (definitions
            + "define function main giving int taking none\n"
            + body
            + "\ngive back 0\nend function\ncall main with\n")


def output(body: str, definitions: str = ""):
    return run_c_source(source_for(body, definitions)).output


INT_MIN = -(2 ** 31)
INT_MAX = 2 ** 31 - 1


def int_lit(n: int) -> str:
    """Render an int as c-ll (which has no signed literal syntax)."""
    if n >= 0:
        return str(n)
    if n == INT_MIN:
        return "((0 minus 2147483647) minus 1)"
    return f"(0 minus {-n})"


# --- Python reference semantics (the stand-in C oracle) --------------------

def c_div(a: int, b: int) -> int:
    """C11 integer division: truncate toward zero."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def c_rem(a: int, b: int) -> int:
    """C11 remainder: sign follows the dividend."""
    return a - c_div(a, b) * b


# ---------------------------------------------------------------------------

class ArithmeticTests(unittest.TestCase):
    def test_single_precedence_left_to_right(self):
        self.assertEqual(output("    show 2 plus 3 times 4"), ["20"])
        self.assertEqual(output("    show 2 plus (3 times 4)"), ["14"])
        self.assertEqual(output("    show 10 minus 3 minus 2"), ["5"])

    def test_integer_division_truncates_toward_zero(self):
        self.assertEqual(output("    show ((0 minus 7) divided by 2)"), ["-3"])
        self.assertEqual(output("    show (7 divided by (0 minus 2))"), ["-3"])
        self.assertEqual(output("    show (7 divided by 2)"), ["3"])

    def test_integer_remainder_follows_dividend(self):
        self.assertEqual(output("    show ((0 minus 7) remainder 2)"), ["-1"])
        self.assertEqual(output("    show (7 remainder (0 minus 2))"), ["1"])
        self.assertEqual(output("    show (7 remainder 2)"), ["1"])

    def test_float_division_and_literals(self):
        self.assertEqual(
            output("    show (cast 7 as float) divided by 2.0"), ["3.5"])
        self.assertEqual(output("    show 1.5 plus 2.25"), ["3.75"])

    def test_explicit_cast_required(self):
        with self.assertRaises(LangError):
            output("    show 1 plus 2.5")
        with self.assertRaises(LangError):
            output("    let x as int be 2.5")

    def test_int_to_float_cast_is_exact(self):
        self.assertEqual(output("    show (cast 16777217 as float)"),
                         ["16777217.0"])

    def test_float_to_int_cast_truncates_toward_zero(self):
        self.assertEqual(output("    show cast (0.0 minus 3.9) as int"), ["-3"])

    def test_float_to_int_out_of_range_is_checked(self):
        with self.assertRaises(LangError):
            output("    show cast 2147483648.0 as int")
        with self.assertRaises(LangError):
            output("    show cast (0 minus 2147483649.0) as int")

    def test_comparisons_return_int_zero_or_one(self):
        body = "\n".join([
            "    show 1 equals 1, 1 equals 2, 1 does not equal 2",
            "    show 1 is less than 2, 2 is at most 2",
            "    show 3 is greater than 2, 3 is at least 4",
        ])
        self.assertEqual(output(body), ["1 0 1", "1 1", "1 0"])

    def test_logic_returns_int_zero_or_one(self):
        body = ("    show 1 and 0, 1 or 0, not 0, not 5, "
                "(1 equals 1) and (2 is less than 3)")
        self.assertEqual(output(body), ["0 1 1 0 1"])

    def test_and_or_short_circuit(self):
        # Without short-circuiting, division by zero would be evaluated.
        self.assertEqual(output("    show 0 and (1 divided by 0)"), ["0"])
        self.assertEqual(output("    show 1 or (1 divided by 0)"), ["1"])

    def test_size_of_pinned_types(self):
        body = ("    show size of int, size of float, size of pointer to int, "
                "size of array[3] of int")
        self.assertEqual(output(body), ["4 8 8 12"])

    def test_overflow_is_checked(self):
        for expr in ("2147483647 plus 1", "(0 minus 2147483647) minus 2",
                     "2147483647 times 2"):
            with self.subTest(expr=expr):
                with self.assertRaises(LangError) as caught:
                    output(f"    show {expr}")
                self.assertIn("integer overflow", str(caught.exception))

    def test_division_by_zero_and_int_min_div_minus_one(self):
        for expr in ("1 divided by 0", "1 remainder 0",
                     "((0 minus 2147483647) minus 1) divided by (0 minus 1)",
                     "((0 minus 2147483647) minus 1) remainder (0 minus 1)"):
            with self.subTest(expr=expr):
                with self.assertRaises(LangError):
                    output(f"    show {expr}")

    def test_float_division_by_zero_is_ieee(self):
        # C float division by zero is not UB; it yields an infinity.
        self.assertEqual(output("    show 1.0 divided by 0.0"), ["inf"])


class StructTests(unittest.TestCase):
    POINT = "define struct Point with x as int, y as int\nend struct\n"
    PAIR = "define struct Pair with a as int, b as float\nend struct\n"

    def test_layout_int_and_float(self):
        self.assertEqual(output("    show size of struct Pair", self.PAIR), ["16"])

    def test_layout_order(self):
        body = ("    let p as pointer to struct Pair be "
                "call allocate with type = struct Pair, count = 1\n"
                "    set member a via p to 3\n"
                "    set member b via p to (cast 4 as float)\n"
                "    show (member a via p), (member b via p)")
        self.assertEqual(output(body, self.PAIR), ["3 4.0"])

    def test_member_of_value_and_via_pointer_are_equivalent(self):
        definitions = (self.POINT
                       + "define function from_ptr giving int taking p as pointer to struct Point\n"
                       + "    give back (member x via p)\nend function\n"
                       + "define function from_val giving int taking s as struct Point\n"
                       + "    give back (member x of s)\nend function\n")
        body = ("    let p as pointer to struct Point be "
                "call allocate with type = struct Point, count = 1\n"
                "    set member x via p to 11\n"
                "    let s as struct Point be value at p\n"
                "    show (call from_ptr with p), (call from_val with s)")
        self.assertEqual(output(body, definitions), ["11 11"])

    def test_struct_assignment_copies_not_aliases(self):
        body = ("    let p as pointer to struct Point be "
                "call allocate with type = struct Point, count = 1\n"
                "    set member x via p to 1\n"
                "    let s as struct Point be value at p\n"
                "    set member x of s to 9\n"
                "    show (member x via p), (member x of s)")
        self.assertEqual(output(body, self.POINT), ["1 9"])

    def test_nested_struct(self):
        definitions = (self.POINT
                       + "define struct Line with start as struct Point, "
                         "finish as struct Point\nend struct\n")
        body = ("    let l as pointer to struct Line be "
                "call allocate with type = struct Line, count = 1\n"
                "    set member x of (member start via l) to 5\n"
                "    show (member x of (member start via l))")
        self.assertEqual(output(body, definitions), ["5"])

    def test_self_reference_via_pointer(self):
        definitions = ("define struct Node with val as int, "
                       "nxt as pointer to struct Node\nend struct\n")
        body = ("    let n as pointer to struct Node be "
                "call allocate with type = struct Node, count = 2\n"
                "    set member val via n to 7\n"
                "    set member nxt via n to (n plus 1)\n"
                "    show (member val via (member nxt via n))")
        self.assertEqual(output(body, definitions), ["0"])

    def test_unknown_field_is_type_error(self):
        with self.assertRaises(LangError):
            output("    let p as pointer to struct Point be "
                   "call allocate with type = struct Point, count = 1\n"
                   "    show (member z via p)", self.POINT)

    def test_by_value_self_reference_is_rejected(self):
        bad = ("define struct Loop with me as struct Loop\nend struct\n"
               "define function main giving int taking none\n"
               "give back 0\nend function\ncall main with\n")
        with self.assertRaises(LangError):
            run_c_source(bad)

    def test_duplicate_field_is_rejected(self):
        bad = ("define struct Bad with x as int, x as int\nend struct\n"
               "define function main giving int taking none\n"
               "give back 0\nend function\ncall main with\n")
        with self.assertRaises(LangError):
            run_c_source(bad)


class PointerTests(unittest.TestCase):
    SWAP = ("define function swap giving void taking "
            "a as pointer to int, b as pointer to int\n"
            "    let t as int be value at a\n"
            "    set value at a to value at b\n"
            "    set value at b to t\n"
            "end function\n")

    def test_swap_through_pointers(self):
        body = ("    let x as int be 3\n"
                "    let y as int be 7\n"
                "    call swap with address of x, address of y\n"
                "    show x, y")
        self.assertEqual(output(body, self.SWAP), ["7 3"])

    def test_call_by_value_does_not_change_argument(self):
        definitions = ("define function bump giving void taking n as int\n"
                       "    set n to n plus 1\nend function\n")
        self.assertEqual(output("    let x as int be 1\n"
                                "    call bump with x\n    show x", definitions),
                         ["1"])

    def test_dereference_is_an_lvalue(self):
        body = ("    let x as int be 1\n"
                "    set value at (address of x) to 8\n    show x")
        self.assertEqual(output(body), ["8"])

    def test_pointer_arithmetic_and_subtraction(self):
        body = ("    let a as pointer to int be "
                "call allocate with type = int, count = 4\n"
                "    set item 0 of a to 5\n"
                "    set item 1 of a to 6\n"
                "    show value at (a plus 1), value at (a plus 1 minus 1), "
                "(a plus 1) minus a")
        self.assertEqual(output(body), ["6 5 1"])

    def test_one_past_end_pointer_is_creatable_but_not_dereferenceable(self):
        body = ("    let a as pointer to int be "
                "call allocate with type = int, count = 1\n"
                "    let endp as pointer to int be a plus 1\n"
                "    show endp equals (a plus 1)")
        self.assertEqual(output(body), ["1"])
        with self.assertRaises(LangError) as caught:
            output("    let a as pointer to int be "
                   "call allocate with type = int, count = 1\n"
                   "    show value at (a plus 1)")
        self.assertIn("pointer out of bounds", str(caught.exception))

    def test_null_pointer_equality_and_inequality(self):
        body = ("    let p as pointer to int be null pointer\n"
                "    let q as pointer to int be null pointer\n"
                "    show p equals q, p does not equal q")
        self.assertEqual(output(body), ["1 0"])

    def test_null_dereference_is_checked(self):
        body = "    let p as pointer to int be null pointer\n    show value at p"
        with self.assertRaises(LangError) as caught:
            output(body)
        self.assertIn("null pointer dereference", str(caught.exception))

    def test_address_of_requires_lvalue(self):
        with self.assertRaises(LangError):
            output("    let p as pointer to int be address of 3")

    def test_pointer_ordering_across_objects_is_checked(self):
        body = ("    let a as pointer to int be call allocate with type = int, count = 1\n"
                "    let b as pointer to int be call allocate with type = int, count = 1\n"
                "    show a is less than b")
        with self.assertRaises(LangError):
            output(body)


class ArrayTests(unittest.TestCase):
    def test_array_index_read_write_and_zero_filling(self):
        body = ("    let a as array[3] of int be 0\n"  # replaced below
                )
        # Arrays have no literal in v1; allocate one and view it as an array.
        body = ("    let p as pointer to array[3] of int be "
                "call allocate with type = array[3] of int, count = 1\n"
                "    let a as array[3] of int be value at p\n"
                "    show item 0 of a, item 1 of a\n"
                "    set item 1 of a to 42\n"
                "    show item 1 of a")
        self.assertEqual(output(body), ["0 0", "42"])

    def test_address_of_array_keeps_length(self):
        body = ("    let p as pointer to array[3] of int be "
                "call allocate with type = array[3] of int, count = 1\n"
                "    set item 2 of (value at p) to 9\n"
                "    show item 2 of (value at p), size of pointer to array[3] of int")
        self.assertEqual(output(body), ["9 8"])

    def test_array_out_of_bounds_high_and_low(self):
        for index in ("3", "(0 minus 1)"):
            with self.subTest(index=index):
                body = ("    let p as pointer to array[3] of int be "
                        "call allocate with type = array[3] of int, count = 1\n"
                        f"    show item {index} of (value at p)")
                with self.assertRaises(LangError) as caught:
                    output(body)
                self.assertIn("out of bounds", str(caught.exception))

    def test_pointer_out_of_bounds(self):
        body = ("    let p as pointer to int be "
                "call allocate with type = int, count = 2\n"
                "    show item 2 of p")
        with self.assertRaises(LangError):
            output(body)


class AllocationTests(unittest.TestCase):
    def test_allocate_zero_fills_and_free(self):
        body = ("    let p as pointer to int be "
                "call allocate with type = int, count = 3\n"
                "    show value at p, item 1 of p, item 2 of p\n"
                "    set item 0 of p to 42\n"
                "    let r as int be item 0 of p\n"
                "    call free with pointer = p\n"
                "    show r")
        self.assertEqual(output(body), ["0 0 0", "42"])

    def test_free_null_is_no_op(self):
        body = ("    let p as pointer to int be null pointer\n"
                "    call free with pointer = p\n    show 1")
        self.assertEqual(output(body), ["1"])

    def test_double_free_is_checked(self):
        body = ("    let p as pointer to int be call allocate with type = int, count = 1\n"
                "    call free with pointer = p\n"
                "    call free with pointer = p")
        with self.assertRaises(LangError) as caught:
            output(body)
        self.assertIn("double free", str(caught.exception))

    def test_use_after_free_is_checked(self):
        body = ("    let p as pointer to int be call allocate with type = int, count = 1\n"
                "    call free with pointer = p\n"
                "    show item 0 of p")
        with self.assertRaises(LangError) as caught:
            output(body)
        self.assertIn("use after free", str(caught.exception))

    def test_free_of_interior_pointer_is_checked(self):
        body = ("    let p as pointer to int be call allocate with type = int, count = 3\n"
                "    call free with pointer = (p plus 1)")
        with self.assertRaises(LangError) as caught:
            output(body)
        self.assertIn("invalid free", str(caught.exception))

    def test_non_positive_allocation_is_checked(self):
        for count in ("0", "(0 minus 1)"):
            with self.subTest(count=count):
                body = ("    let p as pointer to int be "
                        f"call allocate with type = int, count = {count}")
                with self.assertRaises(LangError):
                    output(body)

    def test_allocate_struct_array(self):
        body = ("    let p as pointer to struct Point be "
                "call allocate with type = struct Point, count = 3\n"
                "    set member x via (p plus 2) to 5\n"
                "    show (member x via (p plus 2))")
        self.assertEqual(output(body, "define struct Point with x as int, y as int\n"
                                     "end struct\n"), ["5"])


class ControlFlowTests(unittest.TestCase):
    def test_if_otherwise_if_otherwise(self):
        body = ("    let x as int be 4\n"
                "    if x equals 1 then\n        show 1\n"
                "    otherwise if x equals 4 then\n        show 4\n"
                "    otherwise\n        show 9\n    end if")
        self.assertEqual(output(body), ["4"])

    def test_repeat_while(self):
        body = ("    let i as int be 0\n"
                "    repeat while i is less than 3\n"
                "        show i\n        set i to i plus 1\n    end repeat")
        self.assertEqual(output(body), ["0", "1", "2"])

    def test_counted_loop_with_step(self):
        body = ("    let total as int be 0\n"
                "    repeat for i from 1 below 10 by 3\n"
                "        set total to total plus i\n    end repeat\n"
                "    show total")
        self.assertEqual(output(body), ["12"])

    def test_break_and_continue(self):
        body = ("    let total as int be 0\n"
                "    repeat for i from 0 below 6 by 1\n"
                "        if i equals 2 then\n"
                "            skip to the next item\n        end if\n"
                "        if i equals 5 then\n"
                "            stop the loop\n        end if\n"
                "        set total to total plus i\n    end repeat\n"
                "    show total")
        self.assertEqual(output(body), ["8"])

    def test_nested_loops(self):
        body = ("    let hits as int be 0\n"
                "    repeat for i from 0 below 2 by 1\n"
                "        repeat for j from 0 below 3 by 1\n"
                "            set hits to hits plus 1\n"
                "        end repeat\n    end repeat\n    show hits")
        self.assertEqual(output(body), ["6"])

    def test_early_return(self):
        definitions = ("define function classify giving int taking n as int\n"
                       "    if n is less than 0 then\n        give back 1\n    end if\n"
                       "    give back 2\nend function\n")
        body = "    show (call classify with (0 minus 1)), (call classify with 3)"
        self.assertEqual(output(body, definitions), ["1 2"])

    def test_blocks_introduce_scopes(self):
        body = ("    let x as int be 1\n"
                "    if 1 equals 1 then\n        let x as int be 2\n"
                "        show x\n    end if\n    show x")
        self.assertEqual(output(body), ["2", "1"])

    def test_break_outside_loop_is_rejected(self):
        with self.assertRaises(LangError):
            output("    stop the loop")


class RecursionTests(unittest.TestCase):
    FACT = ("define function fact giving int taking n as int\n"
            "    if n is at most 1 then\n        give back 1\n    end if\n"
            "    give back n times (call fact with (n minus 1))\nend function\n")

    def test_factorial(self):
        for n, expected in [(0, 1), (1, 1), (5, 120), (10, 3628800)]:
            with self.subTest(n=n):
                body = f"    show (call fact with {n})"
                self.assertEqual(output(body, self.FACT), [str(expected)])

    def test_fibonacci(self):
        definitions = ("define function fib giving int taking n as int\n"
                       "    if n is less than 2 then\n        give back n\n    end if\n"
                       "    give back (call fib with (n minus 1)) plus "
                       "(call fib with (n minus 2))\nend function\n")
        self.assertEqual(output("    show (call fib with 10)", definitions), ["55"])

    def test_mutual_recursion(self):
        definitions = ("define function even giving int taking n as int\n"
                       "    if n equals 0 then\n        give back 1\n    end if\n"
                       "    give back (call odd with (n minus 1))\nend function\n"
                       "define function odd giving int taking n as int\n"
                       "    if n equals 0 then\n        give back 0\n    end if\n"
                       "    give back (call even with (n minus 1))\nend function\n")
        body = "    show (call even with 10), (call odd with 7)"
        self.assertEqual(output(body, definitions), ["1 1"])

    def test_missing_return_is_checked(self):
        definitions = ("define function bad giving int taking n as int\n"
                       "    show n\nend function\n")
        with self.assertRaises(LangError):
            output("    show (call bad with 1)", definitions)

    def test_void_function_cannot_give_a_value_back(self):
        definitions = ("define function bad giving void taking none\n"
                       "    give back 1\nend function\n")
        with self.assertRaises(LangError):
            output("    call bad", definitions)

    def test_arity_and_argument_types_are_checked(self):
        definitions = ("define function f giving int taking a as int, "
                       "b as pointer to int\n    give back a\nend function\n")
        with self.assertRaises(LangError):
            output("    show (call f with 1)", definitions)
        with self.assertRaises(LangError):
            output("    show (call f with 1, 2.5)", definitions)
        # A null literal is the one implicit pointer conversion.
        self.assertEqual(output("    show (call f with 1, null pointer)", definitions),
                         ["1"])


class SyntaxAndAPITests(unittest.TestCase):
    def test_initializer_is_mandatory(self):
        with self.assertRaises(LangError):
            run_c_source("define function main giving int taking none\n"
                         "    let x as int\n    give back 0\nend function\n"
                         "call main with\n")

    def test_missing_end_is_rejected(self):
        with self.assertRaises(LangError):
            run_c_source("define function main giving int taking none\n"
                         "    show 1")

    def test_illegal_character_is_rejected(self):
        with self.assertRaises(LangError):
            run_c_source("show 1 $ 2")

    def test_reserved_words_cannot_be_identifiers(self):
        with self.assertRaises(LangError):
            run_c_source("define function main giving int taking none\n"
                         "    let pointer as int be 1\n    give back 0\n"
                         "end function\ncall main with\n")

    def test_native_style_punctuation_is_not_accepted(self):
        with self.assertRaises(LangError):
            run_c_source("int x = 1;")

    def test_compile_c_source_succeeds_for_int_subset(self):
        result = compile_c_source(
            "define function f giving int taking a as int, b as int\n"
            "    give back (a plus b)\nend function\n")
        self.assertEqual(result.wasm[:4], b"\x00asm")
        self.assertEqual(result.unsupported, [])

    def test_compile_c_source_reports_unsupported_pointer_code(self):
        result = compile_c_source(
            "define function f giving int taking p as pointer to int\n"
            "    give back value at p\nend function\n")
        self.assertEqual(result.wasm[:4], b"\x00asm")
        self.assertTrue(result.unsupported)

    def test_compile_c_source_type_checks_first(self):
        with self.assertRaises(LangError):
            compile_c_source("define function f giving int taking none\n"
                             "    give back 1.5\nend function\n")


class DifferentialPythonReferenceTests(unittest.TestCase):
    """Python reference oracle: gcc/clang are not installed on this host."""

    def test_swap_against_python_reference(self):
        def reference(x, y):
            x, y = y, x
            return x, y

        definitions = PointerTests.SWAP
        for x, y in [(3, 7), (0, 0), (-4, 9), (2147483647, INT_MIN)]:
            with self.subTest(x=x, y=y):
                body = (f"    let x as int be {int_lit(x)}\n"
                        f"    let y as int be {int_lit(y)}\n"
                        "    call swap with address of x, address of y\n"
                        "    show x, y")
                actual = output(body, definitions)[0].split()
                expected = reference(x, y)
                self.assertEqual(tuple(map(int, actual)), expected)

    def test_array_sum_against_python_reference(self):
        rng = random.Random(20261122)
        data = [rng.randint(-1000, 1000) for _ in range(24)]
        lines = ["    let p as pointer to int be "
                 f"call allocate with type = int, count = {len(data)}"]
        for i, value in enumerate(data):
            lines.append(f"    set item {i} of p to {int_lit(value)}")
        lines.append("    let total as int be 0")
        lines.append("    repeat for i from 0 below 24 by 1")
        lines.append("        set total to total plus (item i of p)")
        lines.append("    end repeat")
        lines.append("    show total")
        actual = int(output("\n".join(lines))[0])
        self.assertEqual(actual, sum(data))

    def test_recursion_against_python_reference(self):
        def reference(n):
            value = 1
            for i in range(2, n + 1):
                value *= i
            return value

        for n in range(0, 12):
            with self.subTest(n=n):
                self.assertEqual(
                    int(output(f"    show (call fact with {n})",
                               RecursionTests.FACT)[0]), reference(n))

    def test_struct_traversal_against_python_reference(self):
        points = [(1, 2), (7, 11), (-3, 5)]
        definitions = "define struct Point with x as int, y as int\nend struct\n"
        lines = ["    let p as pointer to struct Point be "
                 f"call allocate with type = struct Point, count = {len(points)}"]
        for i, (x, y) in enumerate(points):
            lines.append(f"    set member x via (p plus {i}) to {int_lit(x)}")
            lines.append(f"    set member y via (p plus {i}) to {int_lit(y)}")
        lines.append("    let total as int be 0")
        lines.append(f"    repeat for i from 0 below {len(points)} by 1")
        lines.append("        set total to total plus "
                     "(member x via (p plus i))")
        lines.append("        set total to total plus "
                     "(member y via (p plus i))")
        lines.append("    end repeat")
        lines.append("    show total")
        expected = sum(x + y for x, y in points)
        self.assertEqual(int(output("\n".join(lines), definitions)[0]), expected)

    def test_property_based_arithmetic_against_python_reference(self):
        """Random well-typed cases, rendered with explicit C-style parens."""
        rng = random.Random(4242)
        cases = []
        for _ in range(200):
            a = rng.randint(-10_000, 10_000)
            b = rng.randint(-100, 100)
            if b == 0:
                b = 1
            cases.append((a, b))
        lines = []
        for a, b in cases:
            aa, bb = int_lit(a), int_lit(b)
            lines.append(
                f"    show ({aa} plus ({bb})), ({aa} minus ({bb})), "
                f"({aa} times ({bb})), ({aa} divided by ({bb})), "
                f"({aa} remainder ({bb}))")
        actual = output("\n".join(lines))
        flat = []
        for line in actual:
            flat.extend(line.split())
        expected = []
        for a, b in cases:
            expected.extend([str(a + b), str(a - b), str(a * b),
                             str(c_div(a, b)), str(c_rem(a, b))])
        self.assertEqual(flat, expected)


if __name__ == "__main__":
    unittest.main()
