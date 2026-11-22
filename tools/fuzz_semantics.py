"""Property-based differential testing of llang expression semantics vs Python.

Generates random, type-safe expressions from a small shared subset:

    integer literals (plus | minus | times | floor divided by | modulo)
    comparisons (less / at most / greater / at least / equals / not equal)
    logic (and | or | not) and parentheses

Every generated expression is rendered *twice*: once as a Python expression and
once as the equivalent llang expression. Both are fully parenthesised because
llang deliberately has no operator precedence (it evaluates left to right),
while Python does. Types are tracked during generation so we never feed a
comparison result into llang arithmetic (llang has no implicit coercion and
booleans are not numbers, unlike Python).

The generated expression is evaluated with Python's ``eval`` and with
``run_source("show <expr>")``; the rendered outputs are compared after
normalising booleans (``True`` -> ``true``). Division-by-zero cases are skipped.

Run directly:

    python tools/fuzz_semantics.py --seed 1729 --count 500 --verbose
"""

import argparse
import io
import random
import sys
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llang import LangError, run_source  # noqa: E402

DEFAULT_SEED = 1729
DEFAULT_COUNT = 500
MAX_DEPTH = 4
LEAF_CHANCE = 0.30
MAX_LITERAL = 12

# (llang phrase, Python operator)
INT_OPS: Tuple[Tuple[str, str], ...] = (
    ("plus", "+"),
    ("minus", "-"),
    ("times", "*"),
    ("floor divided by", "//"),
    ("modulo", "%"),
)
ORDER_CMPS: Tuple[Tuple[str, str], ...] = (
    ("is less than", "<"),
    ("is at most", "<="),
    ("is greater than", ">"),
    ("is at least", ">="),
)
EQ_CMPS: Tuple[Tuple[str, str], ...] = (
    ("equals", "=="),
    ("does not equal", "!="),
)
LOGIC_OPS: Tuple[Tuple[str, str], ...] = (("and", "and"), ("or", "or"))


class ExpressionCase(NamedTuple):
    """One expression rendered in both languages.

    ``kind`` is the statically tracked result type: ``"int"`` or ``"bool"``.
    """

    python: str
    llang: str
    kind: str


@dataclass
class Comparison:
    """The outcome of evaluating one :class:`ExpressionCase` in both languages."""

    case: ExpressionCase
    python_value: object = None
    llang_output: List[str] = field(default_factory=list)
    match: bool = False
    skipped: bool = False
    reason: str = ""


@dataclass
class FuzzReport:
    """Aggregate result of a fuzzing run."""

    seed: int
    count: int
    compared: int
    mismatches: int
    skipped: int
    examples: List[Comparison] = field(default_factory=list)


def render_value(value: object) -> str:
    """Render a Python value the way llang's ``show`` statement renders it.

    This is the boolean normalisation point: Python ``True``/``False`` become
    llang's ``true``/``false`` so the two outputs can be compared directly.
    """
    if value is None:
        return "nothing"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def values_match(python_value: object, llang_output) -> bool:
    """Return True when the llang output lines equal the rendered Python value.

    Exposed separately so tests can check that a deliberately broken
    comparison (wrong expected value) is actually detected.
    """
    return list(llang_output) == [render_value(python_value)]


def _leaf(rng: random.Random, kind: str) -> ExpressionCase:
    if kind == "bool":
        value = rng.choice((True, False))
        return ExpressionCase(
            "True" if value else "False", "true" if value else "false", "bool"
        )
    # llang's number lexer has no sign, so literals are non-negative.
    number = rng.randint(0, MAX_LITERAL)
    return ExpressionCase(str(number), str(number), "int")


def _arithmetic(rng: random.Random, max_depth: int, depth: int) -> ExpressionCase:
    llop, pyop = rng.choice(INT_OPS)
    left = generate_expression(rng, max_depth, depth + 1, kind="int")
    right = generate_expression(rng, max_depth, depth + 1, kind="int")
    return ExpressionCase(
        f"({left.python} {pyop} {right.python})",
        f"({left.llang} {llop} {right.llang})",
        "int",
    )


def _comparison(rng: random.Random, max_depth: int, depth: int) -> ExpressionCase:
    if rng.random() < 0.75:
        llop, pyop = rng.choice(ORDER_CMPS)
        operand_kind = "int"
    else:
        llop, pyop = rng.choice(EQ_CMPS)
        # Comparing a bool with an int diverges (llang's `_equal` refuses it,
        # Python's `==` does not), so both sides always share one kind.
        operand_kind = rng.choice(("int", "bool"))
    left = generate_expression(rng, max_depth, depth + 1, kind=operand_kind)
    right = generate_expression(rng, max_depth, depth + 1, kind=operand_kind)
    return ExpressionCase(
        f"({left.python} {pyop} {right.python})",
        f"({left.llang} {llop} {right.llang})",
        "bool",
    )


def _logic(rng: random.Random, max_depth: int, depth: int) -> ExpressionCase:
    llop, pyop = rng.choice(LOGIC_OPS)
    # Bool operands keep the operand-returning and/or behaviour observable
    # without letting a non-bool leak into a context that expects a bool.
    left = generate_expression(rng, max_depth, depth + 1, kind="bool")
    right = generate_expression(rng, max_depth, depth + 1, kind="bool")
    return ExpressionCase(
        f"({left.python} {pyop} {right.python})",
        f"({left.llang} {llop} {right.llang})",
        "bool",
    )


def _not(rng: random.Random, max_depth: int, depth: int) -> ExpressionCase:
    operand_kind = rng.choice(("int", "bool"))
    operand = generate_expression(rng, max_depth, depth + 1, kind=operand_kind)
    return ExpressionCase(
        f"(not {operand.python})", f"(not {operand.llang})", "bool"
    )


def generate_expression(
    rng: random.Random,
    max_depth: int = MAX_DEPTH,
    depth: int = 0,
    kind: Optional[str] = None,
) -> ExpressionCase:
    """Generate one type-safe expression with parallel Python/llang renderings."""
    if kind is None:
        kind = rng.choice(("int", "bool"))
    if depth >= max_depth or rng.random() < LEAF_CHANCE:
        return _leaf(rng, kind)
    if kind == "int":
        return _arithmetic(rng, max_depth, depth)
    if rng.random() < 0.10:
        return _leaf(rng, kind)
    builder = rng.choice((_comparison, _logic, _not))
    return builder(rng, max_depth, depth)


def generate_case(rng: random.Random, max_depth: int = MAX_DEPTH) -> ExpressionCase:
    """Generate one random expression case from the supported subset."""
    return generate_expression(rng, max_depth)


def evaluate_case(case: ExpressionCase) -> Comparison:
    """Evaluate a case in Python and llang and compare their rendered results.

    A ``ZeroDivisionError`` from Python marks the case as skipped (the divisor
    may be a computed subexpression, so this cannot always be prevented by the
    generator). All other differences, including llang errors, are mismatches.
    """
    try:
        value = eval(case.python, {"__builtins__": {}}, {})
    except ZeroDivisionError as exc:
        return Comparison(case, skipped=True, reason=f"division by zero: {exc}")

    try:
        with redirect_stdout(io.StringIO()):
            interpreter = run_source(f"show {case.llang}")
    except LangError as exc:
        return Comparison(
            case, python_value=value, reason=f"llang error: {exc}"
        )

    output = list(interpreter.output)
    match = values_match(value, output)
    reason = "" if match else (
        f"python {render_value(value)!r} != llang {output!r}"
    )
    return Comparison(case, value, output, match=match, reason=reason)


def fuzz(
    seed: int = DEFAULT_SEED,
    count: int = DEFAULT_COUNT,
    verbose: bool = False,
    max_depth: int = MAX_DEPTH,
) -> FuzzReport:
    """Generate and compare ``count`` expressions using a deterministic seed."""
    rng = random.Random(seed)
    report = FuzzReport(seed=seed, count=count, compared=0, mismatches=0, skipped=0)

    for index in range(count):
        result = evaluate_case(generate_case(rng, max_depth))
        if result.skipped:
            report.skipped += 1
            if verbose:
                print(f"[{index}] SKIP {result.case.python}: {result.reason}")
            continue
        report.compared += 1
        if not result.match:
            report.mismatches += 1
            report.examples.append(result)
            if verbose:
                print(
                    f"[{index}] MISMATCH python={result.case.python!r} "
                    f"llang={result.case.llang!r}: {result.reason}"
                )

    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED,
                        help=f"PRNG seed (default: {DEFAULT_SEED})")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT,
                        help=f"expressions to generate (default: {DEFAULT_COUNT})")
    parser.add_argument("--verbose", action="store_true",
                        help="print skipped cases and mismatches as they occur")
    args = parser.parse_args(argv)

    report = fuzz(seed=args.seed, count=args.count, verbose=args.verbose)
    print(f"compared {report.compared} expressions, {report.mismatches} mismatches")
    if args.verbose:
        print(f"seed {report.seed}, skipped {report.skipped} division-by-zero case(s)")
    return 1 if report.mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
