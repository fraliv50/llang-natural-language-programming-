"""Compare lib/datascience.ll against NumPy and pandas.

The corpus is written as JSON, loaded by a generated .ll harness through the
foreign json module, and every result is diffed against pinned NumPy/pandas
calls (plain Python where pandas' ordering or rendering is not the contract).
Prints ``compared N cases, M mismatches`` and exits nonzero on any mismatch.
"""

import csv as pycsv
import io
import json
import math
import subprocess
import sys
import atexit
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))


def table(columns, order, ops):
    return {"columns": columns, "order": order, "ops": ops}


# --- curated corpus (design section 6) ------------------------------------
PEOPLE = table(
    {"name": ["Ada", "Grace", "Lin", "Ada"],
     "score": [90, 95, 80, 70],
     "group": ["a", "b", "a", "b"]},
    ["name", "score", "group"],
    [
        {"kind": "select", "names": ["name", "score"]},
        {"kind": "where", "column": "score", "operator": "is greater than", "value": 80},
        {"kind": "where", "column": "name", "operator": "equals", "value": "Ada"},
        {"kind": "where", "column": "group", "operator": "does not equal", "value": "a"},
        {"kind": "order", "column": "score", "descending": True},
        {"kind": "order", "column": "score", "descending": False},
        {"kind": "aggregate", "column": "score", "how": "sum"},
        {"kind": "aggregate", "column": "score", "how": "mean"},
        {"kind": "aggregate", "column": "score", "how": "min"},
        {"kind": "aggregate", "column": "score", "how": "max"},
        {"kind": "aggregate", "column": "score", "how": "count"},
        {"kind": "group", "key": "group", "column": "score", "how": "sum"},
        {"kind": "group", "key": "group", "column": "score", "how": "mean"},
        {"kind": "group", "key": "group", "column": "score", "how": "count"},
        {"kind": "distinct", "names": ["group"]},
        {"kind": "distinct", "names": ["name", "group"]},
        {"kind": "fill", "column": "score", "value": 0},
        {"kind": "omit", "names": ["score"]},
        {"kind": "convert", "column": "score", "as_kind": "text"},
        {"kind": "describe", "columns": ["score"]},
        {"kind": "tally", "column": "group"},
        {"kind": "row", "index": 2},
        {"kind": "column", "name": "name"},
        {"kind": "overview"},
        {"kind": "harvest"},
        {"kind": "dimensions"},
    ],
)

FLOATS = table(
    {"id": ["p", "q", "r", "s", "t"],
     "value": [1.5, -2.0, 1.5, float("nan"), 0.0],
     "cat": ["x", "y", "x", "z", "x"]},
    ["id", "value", "cat"],
    [
        {"kind": "aggregate", "column": "value", "how": "sum"},
        {"kind": "aggregate", "column": "value", "how": "mean"},
        {"kind": "aggregate", "column": "value", "how": "min"},
        {"kind": "aggregate", "column": "value", "how": "max"},
        {"kind": "aggregate", "column": "value", "how": "count"},
        {"kind": "where", "column": "value", "operator": "is at least", "value": 1.5},
        {"kind": "where", "column": "value", "operator": "is less than", "value": 0.0},
        {"kind": "order", "column": "value", "descending": True},
        {"kind": "order", "column": "value", "descending": False},
        {"kind": "omit", "names": ["value"]},
        {"kind": "fill", "column": "value", "value": 0.0},
        {"kind": "distinct", "names": ["value"]},
        {"kind": "describe", "columns": ["value"]},
        {"kind": "tally", "column": "cat"},
        {"kind": "overview"},
        {"kind": "harvest"},
    ],
)

MISSING = table(
    {"x": [1, 2, 3, 4],
     "y": ["a", None, "c", None],
     "z": [None, None, None, None]},
    ["x", "y", "z"],
    [
        {"kind": "aggregate", "column": "x", "how": "sum"},
        {"kind": "aggregate", "column": "y", "how": "count"},
        {"kind": "aggregate", "column": "z", "how": "count"},
        {"kind": "aggregate", "column": "z", "how": "sum"},
        {"kind": "aggregate", "column": "z", "how": "mean"},
        {"kind": "aggregate", "column": "z", "how": "min"},
        {"kind": "omit", "names": ["y"]},
        {"kind": "omit", "names": ["x", "y"]},
        {"kind": "fill", "column": "y", "value": "filled"},
        {"kind": "fill", "column": "z", "value": "all"},
        {"kind": "where", "column": "y", "operator": "equals", "value": "a"},
        {"kind": "where", "column": "x", "operator": "is greater than", "value": 2},
        {"kind": "distinct", "names": ["y"]},
        {"kind": "column", "name": "z"},
        {"kind": "describe", "columns": ["x", "z"]},
        {"kind": "tally", "column": "y"},
        {"kind": "row", "index": 3},
        {"kind": "overview"},
        {"kind": "harvest"},
    ],
)

EMPTY = table(
    {"a": [], "b": []}, ["a", "b"],
    [
        {"kind": "aggregate", "column": "a", "how": "sum"},
        {"kind": "aggregate", "column": "a", "how": "count"},
        {"kind": "aggregate", "column": "a", "how": "mean"},
        {"kind": "aggregate", "column": "a", "how": "min"},
        {"kind": "aggregate", "column": "a", "how": "max"},
        {"kind": "select", "names": ["a"]},
        {"kind": "where", "column": "a", "operator": "equals", "value": 1},
        {"kind": "order", "column": "a", "descending": True},
        {"kind": "distinct", "names": ["a"]},
        {"kind": "fill", "column": "a", "value": 0},
        {"kind": "omit", "names": ["a"]},
        {"kind": "convert", "column": "a", "as_kind": "number"},
        {"kind": "describe", "columns": ["a"]},
        {"kind": "tally", "column": "a"},
        {"kind": "column", "name": "a"},
        {"kind": "overview"},
        {"kind": "harvest"},
        {"kind": "dimensions"},
    ],
)

ZERO_COL = table({}, [], [
    {"kind": "overview"}, {"kind": "harvest"}, {"kind": "dimensions"},
    {"kind": "select", "names": []},
])

TEXT = table(
    {"word": ["café", "naïve", "Zürich", "hello, \"world\"", "Ω"],
     "cat": ["noun", "noun", "place", "phrase", "letter"]},
    ["word", "cat"],
    [
        {"kind": "order", "column": "word", "descending": False},
        {"kind": "where", "column": "word", "operator": "contains", "value": "a"},
        {"kind": "where", "column": "cat", "operator": "equals", "value": "noun"},
        {"kind": "distinct", "names": ["cat"]},
        {"kind": "tally", "column": "cat"},
        {"kind": "row", "index": 0},
        {"kind": "column", "name": "word"},
        {"kind": "overview"},
        {"kind": "harvest"},
    ],
)

SORT = table(
    {"k": [2, 1, 2, None, 1, 2], "label": ["a", "b", "c", "d", "e", "f"]},
    ["k", "label"],
    [
        {"kind": "order", "column": "k", "descending": True},
        {"kind": "order", "column": "k", "descending": False},
        {"kind": "where", "column": "k", "operator": "is at least", "value": 2},
        {"kind": "aggregate", "column": "k", "how": "mean"},
        {"kind": "aggregate", "column": "k", "how": "count"},
        {"kind": "distinct", "names": ["k"]},
        {"kind": "omit", "names": ["k"]},
        {"kind": "fill", "column": "k", "value": 0},
        {"kind": "harvest"},
    ],
)

CASES = [
    {"name": "people", **PEOPLE},
    {"name": "floats", **FLOATS},
    {"name": "missing", **MISSING},
    {"name": "empty", **EMPTY},
    {"name": "zero_col", **ZERO_COL},
    {"name": "text", **TEXT},
    {"name": "sort", **SORT},
]

JOINS = [
    {"left": {"columns": {"k": ["a", "b", "c", "a"], "v": [1, 2, 3, 4]},
              "order": ["k", "v"]},
     "right": {"columns": {"k": ["a", "a", "b", "d"], "w": ["x", "y", "z", "q"]},
               "order": ["k", "w"]},
     "key": "k", "how": "inner"},
    {"left": {"columns": {"k": ["a", "b", "c", "a"], "v": [1, 2, 3, 4]},
              "order": ["k", "v"]},
     "right": {"columns": {"k": ["a", "a", "b", "d"], "w": ["x", "y", "z", "q"]},
               "order": ["k", "w"]},
     "key": "k", "how": "left"},
    {"left": {"columns": {"k": [1, 2, None, 1], "v": [10, 20, 30, 40]},
              "order": ["k", "v"]},
     "right": {"columns": {"k": [1, None, 3], "w": ["r", "s", "t"]},
               "order": ["k", "w"]},
     "key": "k", "how": "inner"},
    {"left": {"columns": {"k": [1, 2, None, 1], "v": [10, 20, 30, 40]},
              "order": ["k", "v"]},
     "right": {"columns": {"k": [1, None, 3], "w": ["r", "s", "t"]},
               "order": ["k", "w"]},
     "key": "k", "how": "left"},
]

PEOPLE2 = table(
    {"name": ["Mae", "Alan"], "score": [88, 91], "group": ["b", "a"]},
    ["name", "score", "group"], [],
)

PAIRS = [
    {"kind": "append", "top": PEOPLE, "bottom": PEOPLE2},
    {"kind": "rename", "top": PEOPLE, "mapping": {"score": "points"}},
    {"kind": "transpose", "top": table({"a": [1, 2], "b": [3.5, 4]}, ["a", "b"], [])},
]

VECTORS = [
    {"left": [1, 2, 3], "right": [4, 5, 6], "factor": 2, "operation": "add"},
    {"left": [1.5, -2.0, None], "right": [2.0, 3.0, 4.0], "factor": -1.5,
     "operation": "multiply"},
    {"left": [6, 9], "right": [2, 3], "factor": 0.5, "operation": "divided by"},
]

CSV_CASES = [
    {"text": "name,score\nAda,90\nGrace,95\n", "header": True},
    {"text": "a,b\r\n1,\"x,y\"\r\n2,\"line\nbreak\"\r\n", "header": True},
    {"text": "1,2\n3,4\n", "header": False},
    {"text": "a,b\n\"\",2\n", "header": True},
]

JSON_CASES = [
    {"text": '[{"a": 1, "b": "x"}, {"a": 2}]'},
    {"text": '{"a": [1, 2], "b": [null, "z"]}'},
]

CORPUS = {
    "cases": CASES, "joins": JOINS, "pairs": PAIRS, "vectors": VECTORS,
    "csv": CSV_CASES, "json": JSON_CASES,
}


# --- comparison helpers ----------------------------------------------------
def is_missing(value):
    return value is None or (isinstance(value, float) and math.isnan(value))


def norm(value):
    """JSON-friendly canonical form: missing cells become None."""
    if is_missing(value):
        return None
    if isinstance(value, dict):
        return {key: norm(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [norm(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def close(actual, expected):
    if is_missing(actual) or is_missing(expected):
        return is_missing(actual) and is_missing(expected)
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        a = 0.0 if actual == 0 else actual
        b = 0.0 if expected == 0 else expected
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)
    return actual == expected


def compare(path, actual, expected, failures):
    """Structural compare; maps are compared as ordered key/value pairs."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            failures.append((path, actual, expected))
            return
        if list(actual.keys()) != list(expected.keys()):
            failures.append((path + ".keys", list(actual.keys()), list(expected.keys())))
            return
        for key in expected:
            compare(f"{path}.{key}", actual[key], expected[key], failures)
        return
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            failures.append((path, actual, expected))
            return
        for index, item in enumerate(expected):
            compare(f"{path}[{index}]", actual[index], item, failures)
        return
    if not close(actual, expected):
        failures.append((path, actual, expected))


# --- pandas / numpy oracles ------------------------------------------------
def frame(columns, order):
    data = {name: [np.nan if is_missing(cell) else cell for cell in columns[name]]
            for name in order}
    return pd.DataFrame(data, columns=order)


def dataset_of(columns, order):
    return {"kind": "dataset", "columns": {name: norm(columns[name]) for name in order},
            "order": list(order)}


def frame_dataset(df, order):
    return dataset_of({name: df[name].tolist() for name in order}, order)


def rows_dataset(rows, order):
    return dataset_of({name: [row.get(name) for row in rows] for name in order}, order)


def py_kind(values):
    kinds = []
    for value in values:
        if is_missing(value):
            continue
        kind = "boolean" if isinstance(value, bool) else (
            "number" if isinstance(value, (int, float)) else (
                "text" if isinstance(value, str) else "other"))
        if kind not in kinds:
            kinds.append(kind)
    if not kinds:
        return "empty"
    return kinds[0] if len(kinds) == 1 else "mixed"


def ll_text(value):
    if is_missing(value):
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def ll_number(value):
    if is_missing(value):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return int(value)
    except ValueError:
        return float(value)


def matches(cell, operator, expected):
    if is_missing(cell) or is_missing(expected):
        return False
    if operator == "equals":
        return cell == expected
    if operator == "does not equal":
        return cell != expected
    if operator == "contains":
        return expected in cell
    if operator == "is greater than":
        return cell > expected
    if operator == "is less than":
        return cell < expected
    if operator == "is at least":
        return cell >= expected
    if operator == "is at most":
        return cell <= expected
    raise AssertionError(operator)


def expected_summary(columns, order, what):
    if what == "describe":
        report = {}
        for name in order:
            miss = sum(1 for cell in columns[name] if is_missing(cell))
            vals = [cell for cell in columns[name] if not is_missing(cell)]
            report[name] = {
                "count": len(vals),
                "missing": miss,
                "min": min(vals) if vals else None,
                "max": max(vals) if vals else None,
                "mean": (sum(vals) / len(vals)) if vals else None,
            }
        return report
    report = {"kind": "dataset", "rows": len(columns[order[0]]) if order else 0,
              "columns": len(order), "missing": 0}
    missing_total = 0
    for name in order:
        miss = sum(1 for cell in columns[name] if is_missing(cell))
        missing_total += miss
        report[name] = {"kind": py_kind(columns[name]), "missing": miss}
    report["missing"] = missing_total
    return report


def expected_op(case_columns, case_order, op):
    kind = op["kind"]
    df = frame(case_columns, case_order)
    if kind == "select":
        names = op["names"]
        return dataset_of({name: case_columns[name] for name in names}, names)
    if kind == "where":
        rows = [{name: case_columns[name][i] for name in case_order}
                for i in range(len(df))]
        kept = [row for row in rows
                if matches(row[op["column"]], op["operator"], op["value"])]
        return rows_dataset(kept, case_order)
    if kind == "order":
        ordered = df.sort_values(by=op["column"], ascending=not op["descending"],
                                 na_position="last", kind="stable")
        return frame_dataset(ordered, case_order)
    if kind == "aggregate":
        ser = df[op["column"]]
        method = op["how"]
        if method == "count":
            return int(ser.count())
        if method == "sum":
            return norm(ser.sum())
        if method == "mean":
            return norm(ser.mean())
        if method == "min":
            return norm(ser.min())
        return norm(ser.max())
    if kind == "group":
        grouped = df.groupby(op["key"], sort=False, dropna=True)[op["column"]]
        return norm(getattr(grouped, op["how"])().to_dict())
    if kind == "distinct":
        return frame_dataset(df.drop_duplicates(subset=op["names"], keep="first"),
                             case_order)
    if kind == "fill":
        copied = df.copy()
        copied[op["column"]] = copied[op["column"]].fillna(op["value"])
        return frame_dataset(copied, case_order)
    if kind == "omit":
        return frame_dataset(df.dropna(subset=op["names"]), case_order)
    if kind == "convert":
        as_kind = op["as_kind"]
        convert = ll_number if as_kind == "number" else ll_text
        return dataset_of({name: ([convert(cell) for cell in case_columns[name]]
                                  if name == op["column"] else case_columns[name])
                           for name in case_order}, case_order)
    if kind == "describe":
        names = case_order if op["columns"] is None else op["columns"]
        chosen = {name: case_columns[name] for name in names
                  if py_kind(case_columns[name]) == "number"}
        return expected_summary(chosen, list(chosen), "describe")
    if kind == "tally":
        freq = {}
        for cell in case_columns[op["column"]]:
            if not is_missing(cell):
                freq[cell] = freq.get(cell, 0) + 1
        return norm(freq)
    if kind == "row":
        index = op["index"]
        return norm({name: case_columns[name][index] for name in case_order})
    if kind == "column":
        return norm(case_columns[op["name"]])
    if kind == "overview":
        return expected_summary(case_columns, case_order, "overview")
    if kind == "harvest":
        return [norm({name: case_columns[name][i] for name in case_order})
                for i in range(len(df))]
    if kind == "dimensions":
        return {"rows": len(df), "columns": len(case_order)}
    raise AssertionError(kind)


def expected_join(fixture):
    left = frame(fixture["left"]["columns"], fixture["left"]["order"])
    right = frame(fixture["right"]["columns"], fixture["right"]["order"])
    with np.errstate(invalid="ignore"):
        merged = left.merge(right, on=fixture["key"], how=fixture["how"])
    order = list(merged.columns)
    return frame_dataset(merged, order)


def expected_pair(fixture):
    kind = fixture["kind"]
    top = fixture["top"]
    if kind == "append":
        a = frame(top["columns"], top["order"])
        b = frame(fixture["bottom"]["columns"], fixture["bottom"]["order"])
        merged = pd.concat([a, b], ignore_index=True)
        return frame_dataset(merged, top["order"])
    if kind == "rename":
        mapping = fixture["mapping"]
        order = [mapping.get(name, name) for name in top["order"]]
        renamed = frame(top["columns"], top["order"]).rename(columns=mapping)
        return frame_dataset(renamed, order)
    order = top["order"]
    height = len(top["columns"][order[0]])
    new_order = ["name"] + [str(i) for i in range(height)]
    columns = {"name": list(order)}
    for i in range(height):
        columns[str(i)] = [top["columns"][name][i] for name in order]
    return dataset_of(columns, new_order)


def expected_vector(fixture):
    left, right = fixture["left"], fixture["right"]
    factor, operation = fixture["factor"], fixture["operation"]
    dot = None if any(is_missing(a) or is_missing(b) for a, b in zip(left, right)) \
        else np.dot([0 if is_missing(v) else v for v in left],
                    [0 if is_missing(v) else v for v in right])
    scale = [None if is_missing(v) else v * factor for v in left]
    op = {"add": np.add, "subtract": np.subtract, "multiply": np.multiply,
          "divided by": np.divide}[operation]
    combine = [None if is_missing(a) or is_missing(b) else op(a, b)
               for a, b in zip(left, right)]
    return {"dot": norm(dot), "scale": norm(scale), "combine": norm(combine)}


def csv_dataset(text, header):
    rows = list(pycsv.reader(io.StringIO(text)))
    if header:
        names, data = rows[0], rows[1:]
    elif rows:
        names, data = [str(i) for i in range(len(rows[0]))], rows
    else:
        names, data = [], []
    return dataset_of({name: [row[i] for row in data]
                       for i, name in enumerate(names)}, names)


def json_dataset(text):
    parsed = json.loads(text)
    if isinstance(parsed, list):
        names = []
        for record in parsed:
            for name in record:
                if name not in names:
                    names.append(name)
        return dataset_of({name: [record.get(name) for record in parsed]
                           for name in names}, names)
    if isinstance(parsed, dict):
        return dataset_of(parsed, list(parsed.keys()))
    raise AssertionError(text)


def make_harness(cases_path, results_path):
    def esc(path):
        return str(path).replace("\\", "/")

    return f"""use the datascience module
use the foreign json module as hostjson

set corpus to call loads from hostjson with text = (call read text from with path = "{esc(cases_path)}")
set case_results to an empty list

repeat for each case in (item "cases" of corpus)
    set one to call table from datascience with columns = (item "columns" of case), order = (item "order" of case)
    set op_results to an empty list
    repeat for each op in (item "ops" of case)
        set op_kind to item "kind" of op
        if op_kind equals "select" then
            add (call select from datascience with dataset = one, names = (item "names" of op)) to op_results
        otherwise if op_kind equals "where" then
            add (call where from datascience with dataset = one, column = (item "column" of op), operator = (item "operator" of op), value = (item "value" of op)) to op_results
        otherwise if op_kind equals "order" then
            add (call order from datascience with dataset = one, column = (item "column" of op), descending = (item "descending" of op)) to op_results
        otherwise if op_kind equals "aggregate" then
            add (call aggregate from datascience with dataset = one, column = (item "column" of op), how = (item "how" of op)) to op_results
        otherwise if op_kind equals "group" then
            add (call group from datascience with dataset = one, key = (item "key" of op), column = (item "column" of op), how = (item "how" of op)) to op_results
        otherwise if op_kind equals "distinct" then
            add (call distinct from datascience with dataset = one, names = (item "names" of op)) to op_results
        otherwise if op_kind equals "fill" then
            add (call fill from datascience with dataset = one, column = (item "column" of op), value = (item "value" of op)) to op_results
        otherwise if op_kind equals "omit" then
            add (call omit from datascience with dataset = one, names = (item "names" of op)) to op_results
        otherwise if op_kind equals "convert" then
            add (call convert from datascience with dataset = one, column = (item "column" of op), as_kind = (item "as_kind" of op)) to op_results
        otherwise if op_kind equals "describe" then
            add (call describe from datascience with dataset = one, columns = (item "columns" of op)) to op_results
        otherwise if op_kind equals "tally" then
            add (call tally from datascience with dataset = one, column = (item "column" of op)) to op_results
        otherwise if op_kind equals "row" then
            add (call row from datascience with dataset = one, index = (item "index" of op)) to op_results
        otherwise if op_kind equals "column" then
            add (call column from datascience with dataset = one, name = (item "name" of op)) to op_results
        otherwise if op_kind equals "overview" then
            add (call overview from datascience with dataset = one) to op_results
        otherwise if op_kind equals "harvest" then
            add (call harvest from datascience with dataset = one) to op_results
        otherwise if op_kind equals "dimensions" then
            add (call dimensions from datascience with dataset = one) to op_results
        end if
    end repeat
    add (a map with "name" mapped to (item "name" of case), "ops" mapped to op_results) to case_results
end repeat

set join_results to an empty list
repeat for each fixture in (item "joins" of corpus)
    set lhs to call table from datascience with columns = (item "columns" of (item "left" of fixture)), order = (item "order" of (item "left" of fixture))
    set rhs to call table from datascience with columns = (item "columns" of (item "right" of fixture)), order = (item "order" of (item "right" of fixture))
    add (call attach from datascience with left = lhs, right = rhs, key = (item "key" of fixture), how = (item "how" of fixture)) to join_results
end repeat

set pair_results to an empty list
repeat for each fixture in (item "pairs" of corpus)
    set lhs to call table from datascience with columns = (item "columns" of (item "top" of fixture)), order = (item "order" of (item "top" of fixture))
    set pair_kind to item "kind" of fixture
    if pair_kind equals "append" then
        set rhs to call table from datascience with columns = (item "columns" of (item "bottom" of fixture)), order = (item "order" of (item "bottom" of fixture))
        add (call append from datascience with top = lhs, bottom = rhs) to pair_results
    otherwise if pair_kind equals "rename" then
        add (call rename from datascience with dataset = lhs, mapping = (item "mapping" of fixture)) to pair_results
    otherwise if pair_kind equals "transpose" then
        add (call transpose from datascience with dataset = lhs) to pair_results
    end if
end repeat

set vector_results to an empty list
repeat for each fixture in (item "vectors" of corpus)
    add (a map with "dot" mapped to (call dot from datascience with left = (item "left" of fixture), right = (item "right" of fixture)), "scale" mapped to (call scale from datascience with values = (item "left" of fixture), factor = (item "factor" of fixture)), "combine" mapped to (call combine from datascience with left = (item "left" of fixture), right = (item "right" of fixture), operation = (item "operation" of fixture))) to vector_results
end repeat

set csv_results to an empty list
repeat for each fixture in (item "csv" of corpus)
    add (call load_csv from datascience with text = (item "text" of fixture), header = (item "header" of fixture)) to csv_results
end repeat

set json_results to an empty list
repeat for each fixture in (item "json" of corpus)
    add (call load_json from datascience with text = (item "text" of fixture)) to json_results
end repeat

set payload to a map with "cases" mapped to case_results, "joins" mapped to join_results, "pairs" mapped to pair_results, "vectors" mapped to vector_results, "csv" mapped to csv_results, "json" mapped to json_results
call write text to with path = "{esc(results_path)}", content = (call dumps from hostjson with value = payload)
"""


def main():
    work = Path(tempfile.mkdtemp(prefix="llang_datascience_"))
    atexit.register(shutil.rmtree, work, ignore_errors=True)
    cases_path, results_path = work / "cases.json", work / "results.json"
    harness_path = work / "harness.ll"
    cases_path.write_text(json.dumps(CORPUS, ensure_ascii=False), encoding="utf-8")
    harness_path.write_text(make_harness(cases_path, results_path), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(ROOT / "run.py"), str(harness_path)],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
    timeout=300)
    if completed.returncode != 0:
        print("llang run failed:")
        print(completed.stdout)
        print(completed.stderr)
        sys.exit(1)

    results = json.loads(results_path.read_text(encoding="utf-8"))
    failures = []
    total = 0

    for case, actual_case in zip(CASES, results["cases"]):
        for index, op in enumerate(case["ops"]):
            total += 1
            expected = expected_op(case["columns"], case["order"], op)
            compare(f"{case['name']}.ops[{index}].{op['kind']}",
                    actual_case["ops"][index], expected, failures)

    for index, fixture in enumerate(JOINS):
        total += 1
        compare(f"joins[{index}].{fixture['how']}", results["joins"][index],
                expected_join(fixture), failures)

    for index, fixture in enumerate(PAIRS):
        total += 1
        compare(f"pairs[{index}].{fixture['kind']}", results["pairs"][index],
                expected_pair(fixture), failures)

    for index, fixture in enumerate(VECTORS):
        total += 1
        compare(f"vectors[{index}]", results["vectors"][index],
                expected_vector(fixture), failures)

    for index, fixture in enumerate(CSV_CASES):
        total += 1
        compare(f"csv[{index}]", results["csv"][index],
                csv_dataset(fixture["text"], fixture["header"]), failures)

    for index, fixture in enumerate(JSON_CASES):
        total += 1
        compare(f"json[{index}]", results["json"][index],
                json_dataset(fixture["text"]), failures)

    print(f"compared {total} cases, {len(failures)} mismatches")
    for path, actual, expected in failures[:40]:
        print(f"  {path}: got {actual!r}, want {expected!r}")
    if failures:
        sys.exit(1)
    print("lib/datascience.ll matches NumPy and pandas")


if __name__ == "__main__":
    main()
