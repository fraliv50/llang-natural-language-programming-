"""Unit tests for the native data-science library, plus a NumPy/pandas diff."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang import LangError, Lexer, Parser, Interpreter  # noqa: E402

USE = "use the datascience module\n"
PEOPLE = (
    'set people to call table from datascience with columns = (a map with '
    '"name" mapped to (a list of "Ada", "Grace", "Lin", "Ada"), '
    '"score" mapped to (a list of 90, 95, 80, 70), '
    '"group" mapped to (a list of "a", "b", "a", "b")), '
    'order = nothing\n'
)
SORTED_FIXTURE = (
    'set sorted_ds to call table from datascience with columns = (a map with '
    '"k" mapped to (a list of 2, 1, 2, nothing, 1, 2), '
    '"label" mapped to (a list of "a", "b", "c", "d", "e", "f")), '
    'order = nothing\n'
)


def run(source):
    interpreter = Interpreter(library_paths=[ROOT / "lib"])
    interpreter.run(Parser(Lexer(USE + source).tokenize()).parse_program())
    return interpreter.output


def show(source):
    return run("show " + source)[0]


class DataScienceTests(unittest.TestCase):
    # --- builders and shape ------------------------------------------------
    def test_table_is_self_describing(self):
        output = run(PEOPLE + "show people")
        self.assertEqual(output[0],
                         "{kind: dataset, columns: {name: [Ada, Grace, Lin, Ada], "
                         "score: [90, 95, 80, 70], group: [a, b, a, b]}, "
                         "order: [name, score, group]}")

    def test_records_fill_missing_keys_and_append_new_ones(self):
        output = run('''
set ds to call records from datascience with rows = (a list of (a map with "a" mapped to 1, "b" mapped to "x"), (a map with "a" mapped to 2, "c" mapped to "y")), order = nothing
show call harvest from datascience with dataset = ds
show call dimensions from datascience with dataset = ds
''')
        self.assertEqual(output[0],
                         "[{a: 1, b: x, c: nothing}, {a: 2, b: nothing, c: y}]")
        self.assertEqual(output[1], "{rows: 2, columns: 3}")

    def test_dimensions_and_shape_are_the_same_function(self):
        self.assertEqual(
            run(PEOPLE + 'show call dimensions from datascience with dataset = people'),
            run(PEOPLE + 'show call shape from datascience with dataset = people'),
        )
        self.assertEqual(
            show('call dimensions from datascience with dataset = '
                 '(call table from datascience with columns = (an empty map), order = nothing)'),
            "{rows: 0, columns: 0}",
        )

    def test_empty_dataset_aggregations(self):
        src = ('call table from datascience with columns = (a map with '
               '"n" mapped to (an empty list)), order = nothing')
        values = []
        for method in ("sum", "count", "mean", "min", "max"):
            values.append(show(f'call aggregate from datascience with dataset = ({src}), '
                               f'column = "n", how = "{method}"'))
        self.assertEqual(values, ["0", "0", "nothing", "nothing", "nothing"])

    # --- selection and filtering -------------------------------------------
    def test_column_select_and_where(self):
        output = run(PEOPLE + '''
show call column from datascience with dataset = people, name = "score"
show call select from datascience with dataset = people, names = (a list of "group", "name")
show call where from datascience with dataset = people, column = "score", operator = "is greater than", value = 80
show call where from datascience with dataset = people, column = "name", operator = "contains", value = "a"
''')
        self.assertEqual(output[0], "[90, 95, 80, 70]")
        self.assertIn("{kind: dataset, columns: {group: [a, b, a, b], name: [Ada, Grace, Lin, Ada]}, order: [group, name]}", output[1])
        self.assertIn("[Ada, Grace]", output[2])
        self.assertIn("[Ada, Grace, Ada]", output[3])

    def test_missing_cells_never_match_even_for_does_not_equal(self):
        output = run('''
set ds to call table from datascience with columns = (a map with "v" mapped to (a list of 1, nothing, 3)), order = nothing
show call where from datascience with dataset = ds, column = "v", operator = "does not equal", value = 1
show call where from datascience with dataset = ds, column = "v", operator = "equals", value = nothing
''')
        self.assertIn("columns: {v: [3]}", output[0])
        self.assertIn("v: []", output[1])

    def test_stable_sort_with_missing_last(self):
        output = run(SORTED_FIXTURE + '''
show call order from datascience with dataset = sorted_ds, column = "k", descending = true
show call order from datascience with dataset = sorted_ds, column = "k", descending = false
show call order_rows from datascience with dataset = sorted_ds, column = "k", descending = false
''')
        # ties keep original order; the missing key is last in both directions
        self.assertIn("label: [a, c, f, b, e, d]", output[0])
        self.assertIn("label: [b, e, a, c, f, d]", output[1])
        self.assertEqual(output[1], output[2])

    # --- reductions and grouping -------------------------------------------
    def test_aggregate_and_group(self):
        output = run(PEOPLE + '''
show call aggregate from datascience with dataset = people, column = "score", how = "sum"
show call aggregate from datascience with dataset = people, column = "score", how = "mean"
show call aggregate from datascience with dataset = people, column = "score", how = "count"
show call group from datascience with dataset = people, key = "group", column = "score", how = "mean"
show call group from datascience with dataset = people, key = "group", column = "score", how = "sum"
''')
        self.assertEqual(output[:3], ["335", "83.75", "4"])
        self.assertEqual(output[3], "{a: 85.0, b: 82.5}")
        self.assertEqual(output[4], "{a: 170, b: 165}")

    def test_group_drops_missing_keys_and_keeps_first_appearance_order(self):
        output = run('''
set ds to call table from datascience with columns = (a map with "k" mapped to (a list of "b", nothing, "a", "b"), "v" mapped to (a list of 1, 2, 3, 4)), order = nothing
show call group from datascience with dataset = ds, key = "k", column = "v", how = "sum"
''')
        self.assertEqual(output[0], "{b: 5, a: 3}")

    # --- missing values and conversion -------------------------------------
    def test_distinct_fill_omit_and_convert(self):
        output = run('''
use the foreign json module as hostjson
set ds to call table from datascience with columns = (a map with "k" mapped to (a list of "a", "b", "a"), "v" mapped to (a list of 1, 2, 3), "m" mapped to (a list of "x", nothing, "z")), order = nothing
show call distinct from datascience with dataset = ds, names = (a list of "k")
show call fill from datascience with dataset = ds, column = "m", value = "none"
show call omit from datascience with dataset = ds, names = (a list of "m")
show call dumps from hostjson with value = (call convert from datascience with dataset = ds, column = "v", as_kind = "text")
show call tally from datascience with dataset = ds, column = "k"
''')
        self.assertIn("k: [a, b]", output[0])
        self.assertIn("m: [x, none, z]", output[1])
        self.assertIn("v: [1, 3]", output[2])
        self.assertIn('"v": ["1", "2", "3"]', output[3])
        self.assertEqual(output[4], "{a: 2, b: 1}")

    def test_convert_normalizes_nan_and_fails_loudly(self):
        self.assertEqual(
            show('call convert from datascience with dataset = (call table from datascience '
                 'with columns = (a map with "n" mapped to (a list of "5", "2.5", "NaN", nothing)), '
                 'order = nothing), column = "n", as_kind = "number"'),
            '{kind: dataset, columns: {n: [5, 2.5, nothing, nothing]}, order: [n]}',
        )
        with self.assertRaises(LangError) as ctx:
            run('show call convert from datascience with dataset = (call table from datascience '
                'with columns = (a map with "n" mapped to (a list of "oops")), order = nothing), '
                'column = "n", as_kind = "number"')
        self.assertIn("bad_conversion", str(ctx.exception))

    def test_missing_predicate_and_count(self):
        output = run('''
show call missing from datascience with value = nothing
show call missing from datascience with value = (call to number with text = "NaN")
show call missing from datascience with value = 0
show call count from datascience with values = (a list of 1, nothing, 3)
''')
        self.assertEqual(output, ["true", "true", "false", "2"])

    # --- 1-D math -----------------------------------------------------------
    def test_dot_scale_and_combine(self):
        output = run('''
show call dot from datascience with left = (a list of 1, 2, 3), right = (a list of 4, 5, 6)
show call scale from datascience with values = (a list of 1, 2, nothing), factor = 2.5
show call combine from datascience with left = (a list of 1, 2, 3), right = (a list of 4, 5, 6), operation = "add"
show call combine from datascience with left = (a list of 6, 9), right = (a list of 2, 3), operation = "divided by"
show call dot from datascience with left = (a list of 1, nothing), right = (a list of 2, 3)
''')
        self.assertEqual(output[:4], ["32", "[2.5, 5.0, nothing]", "[5, 7, 9]", "[3.0, 3.0]"])
        self.assertEqual(output[4], "nothing")

    def test_combine_length_mismatch_and_division_by_zero(self):
        with self.assertRaises(LangError):
            run('show call combine from datascience with left = (a list of 1), '
                'right = (a list of 1, 2), operation = "add"')
        with self.assertRaises(LangError) as ctx:
            run('show call combine from datascience with left = (a list of 1), '
                'right = (a list of 0), operation = "divided by"')
        self.assertIn("Division by zero", str(ctx.exception))

    # --- summaries, reshape, joins -----------------------------------------
    def test_overview_describe_row_and_harvest(self):
        output = run(PEOPLE + '''
show call overview from datascience with dataset = people
show call describe from datascience with dataset = people, columns = (a list of "score")
show call row from datascience with dataset = people, index = 1
show call harvest from datascience with dataset = people
''')
        self.assertEqual(output[0], "{kind: dataset, rows: 4, columns: 3, missing: 0, "
                                    "name: {kind: text, missing: 0}, "
                                    "score: {kind: number, missing: 0}, "
                                    "group: {kind: text, missing: 0}}")
        self.assertEqual(output[1], "{score: {count: 4, missing: 0, min: 70, max: 95, mean: 83.75}}")
        self.assertEqual(output[2], "{name: Grace, score: 95, group: b}")
        self.assertTrue(output[3].startswith("[{name: Ada, score: 90, group: a}"))

    def test_describe_skips_non_numeric_columns(self):
        self.assertEqual(
            show('call describe from datascience with dataset = (call table from datascience '
                 'with columns = (a map with "s" mapped to (a list of "x", "y"), '
                 '"n" mapped to (a list of 1, 2)), order = nothing), columns = nothing'),
            '{n: {count: 2, missing: 0, min: 1, max: 2, mean: 1.5}}',
        )

    def test_transpose_append_rename_and_filter(self):
        output = run('''
set nums to call table from datascience with columns = (a map with "a" mapped to (a list of 1, 2), "b" mapped to (a list of 3, 4)), order = nothing
show call transpose from datascience with dataset = nums
show call append from datascience with top = nums, bottom = nums
show call rename from datascience with dataset = nums, mapping = (a map with "a" mapped to "first")
define function big taking r
    give back (item "b" of r) is greater than 3
end function
show call filter from datascience with dataset = nums, predicate = big
''')
        self.assertIn("name: [a, b], 0: [1, 3], 1: [2, 4]", output[0])
        self.assertIn("a: [1, 2, 1, 2]", output[1])
        self.assertIn("first: [1, 2]", output[2])
        self.assertIn("b: [4]", output[3])

    def test_attach_inner_and_left(self):
        output = run('''
set lhs to call table from datascience with columns = (a map with "k" mapped to (a list of "a", "b", "c", "a"), "v" mapped to (a list of 1, 2, 3, 4)), order = nothing
set rhs to call table from datascience with columns = (a map with "k" mapped to (a list of "a", "a", "b"), "w" mapped to (a list of "x", "y", "z")), order = nothing
show call attach from datascience with left = lhs, right = rhs, key = "k", how = "inner"
show call attach from datascience with left = lhs, right = rhs, key = "k", how = "left"
''')
        self.assertIn("k: [a, a, b, a, a]", output[0])
        self.assertIn("w: [x, y, z, x, y]", output[0])
        self.assertIn("w: [x, y, z, nothing, x, y]", output[1])

    # --- IO ----------------------------------------------------------------
    def test_load_csv_and_load_json(self):
        output = run(r'''
set csv_ds to call load_csv from datascience with text = "a,b\n1,\"x,y\"\n", header = true
show call harvest from datascience with dataset = csv_ds
set json_ds to call load_json from datascience with text = "[{\"a\": 1, \"b\": \"x\"}, {\"a\": 2}]"
show call harvest from datascience with dataset = json_ds
show call dimensions from datascience with dataset = (call load_json from datascience with text = "{\"a\": [1, 2], \"b\": [null, \"z\"]}")
''')
        self.assertEqual(output[0], "[{a: 1, b: x,y}]")
        self.assertEqual(output[1], "[{a: 1, b: x}, {a: 2, b: nothing}]")
        self.assertEqual(output[2], "{rows: 2, columns: 2}")

    def test_csv_with_embedded_newline_via_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "case.json"
            path.write_text(json.dumps({"text": 'a,b\r\n1,"x\ny"\r\n', "header": True}),
                            encoding="utf-8")
            escaped = str(path).replace("\\", "/")
            output = run(f'''
use the foreign json module as hostjson
set case to call loads from hostjson with text = (call read text from with path = "{escaped}")
show call harvest from datascience with dataset = (call load_csv from datascience with text = (item "text" of case), header = (item "header" of case))
''')
        self.assertIn("{a: 1, b: x\ny}", output[0])

    # --- validation --------------------------------------------------------
    def test_loud_validation(self):
        cases = [
            ('show call table from datascience with columns = (a map with '
             '"a" mapped to (a list of 1, 2), "b" mapped to (a list of 3)), order = nothing',
             "bad_shape"),
            ('show call aggregate from datascience with dataset = (call table from datascience '
             'with columns = (a map with "a" mapped to (a list of 1)), order = nothing), '
             'column = "b", how = "sum"', "unknown_column"),
            ('show call records from datascience with rows = (a list of 5), order = nothing',
             "bad_row"),
            ('show call row from datascience with dataset = (call table from datascience '
             'with columns = (a map with "a" mapped to (a list of 1)), order = nothing), '
             'index = 4', "index_out_of_range"),
            ('show call attach from datascience with left = (call table from datascience '
             'with columns = (a map with "k" mapped to (a list of "a")), order = nothing), '
             'right = (call table from datascience with columns = (a map with "k" mapped to '
             '(a list of 1)), order = nothing), key = "k", how = "inner"', "bad_join_key"),
        ]
        for source, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaises(LangError) as ctx:
                    run(source)
                self.assertIn(expected, str(ctx.exception))

    def test_label_order_does_not_matter(self):
        a = show('call aggregate from datascience with dataset = (call table from datascience '
                 'with columns = (a map with "a" mapped to (a list of 1, 2)), order = nothing), '
                 'column = "a", how = "sum"')
        b = show('call aggregate from datascience with how = "sum", column = "a", '
                 'dataset = (call table from datascience with order = nothing, '
                 'columns = (a map with "a" mapped to (a list of 1, 2)))')
        self.assertEqual(a, b)

    # --- overall verification ----------------------------------------------
    def test_lint_is_clean(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "run.py"), "--lint", "lib/datascience.ll"],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        timeout=300)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("error:", result.stdout)

    def test_matches_numpy_and_pandas(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "compare_datascience.py")],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        timeout=300)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("0 mismatches", result.stdout)


if __name__ == "__main__":
    unittest.main()
