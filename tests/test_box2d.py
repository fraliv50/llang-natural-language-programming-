"""The llang rewrite of pypybox2d's numeric core, verified against the oracle.

The reference implementation is the pinned pure-Python clone at
``tools/rewrites/pypybox2d/source`` (commit ee7b81f).  It is loaded read-only
through importlib; the optional C extension is never built.
"""

import contextlib
import importlib
import io
import json
import math
import sys
import atexit
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "tools" / "rewrites" / "pypybox2d" / "source"
sys.path.insert(0, str(ROOT / "src"))

from llang import LangError, Lexer, Parser, Interpreter  # noqa: E402


_ORACLE = None


def oracle():
    """Load the pinned pypybox2d package once, on the pure-Python path."""
    global _ORACLE
    if _ORACLE is None:
        if not (SOURCE / "pypybox2d" / "common.py").is_file():
            raise RuntimeError(f"pypybox2d clone missing at {SOURCE}")
        if str(SOURCE) not in sys.path:
            sys.path.insert(0, str(SOURCE))
        with contextlib.redirect_stdout(io.StringIO()):
            package = importlib.import_module("pypybox2d")
        assert package.Vec2 is package.PyVec2
        _ORACLE = package
    return _ORACLE


def run(source):
    interpreter = Interpreter(library_paths=[ROOT / "lib"])
    with contextlib.redirect_stdout(io.StringIO()):
        interpreter.run(Parser(Lexer(source).tokenize()).parse_program())
    return interpreter.output


def show_value(expression):
    return run("use the box2d module\nshow " + expression)[-1]


def close(a, b, rel=1e-6, abs_=1e-6):
    return math.isclose(float(a), float(b), rel_tol=rel, abs_tol=abs_)


def num(value):
    text = repr(float(value))
    return text if value >= 0 else f"(0 minus {repr(abs(float(value)))})"


class Box2dRewriteTests(unittest.TestCase):
    def test_vec2_and_dot_are_native(self):
        self.assertEqual(show_value("(call vec_dot from box2d with a = (call vec2 from box2d with x = 3, y = 4), b = (call vec2 from box2d with x = 5, y = 6))"), "39")
        self.assertEqual(show_value("(call vec_len from box2d with v = (call vec2 from box2d with x = 3, y = 4))"), "5.0")

    def test_clamp_and_powers(self):
        self.assertEqual(show_value("(call clamp from box2d with value = 12, low = 0, high = 7)"), "7")
        self.assertEqual(show_value("(call next_power_of_two from box2d with value = 5)"), "8")
        self.assertEqual(show_value("(call next_power_of_two from box2d with value = 0)"), "1")
        self.assertEqual(show_value("(call is_power_of_two from box2d with value = 64)"), "true")
        self.assertEqual(show_value("(call is_power_of_two from box2d with value = 65)"), "false")

    def test_mat22_rotation_matches_oracle(self):
        b = oracle()
        rotation = b.Mat22(angle=0.6)
        v = b.Vec2(2.0, -3.0)
        expected = rotation * v
        matrix_result = run("""
use the box2d module
set m to call mat_angle from box2d with angle = 0.6
set v to call vec2 from box2d with x = 2, y = (0 minus 3)
set r to call mat_mul_vec from box2d with m = m, v = v
show item "x" of r
show item "y" of r
""")
        got_x, got_y = float(matrix_result[0]), float(matrix_result[1])
        self.assertTrue(close(expected.x, got_x, 1e-12, 1e-12))
        self.assertTrue(close(expected.y, got_y, 1e-12, 1e-12))

    def test_aabb_overlap_matches_oracle(self):
        b = oracle()
        first = b.AABB((0, 0), (2, 2))
        second = b.AABB((1, 1), (3, 3))
        third = b.AABB((5, 5), (6, 6))
        self.assertEqual(first.test_overlap(second), True)
        self.assertEqual(first.test_overlap(third), False)
        got = show_value("(call aabb_overlaps from box2d with first = (call aabb from box2d with lower = (call vec2 from box2d with x = 0, y = 0), upper = (call vec2 from box2d with x = 2, y = 2)), second = (call aabb from box2d with lower = (call vec2 from box2d with x = 1, y = 1), upper = (call vec2 from box2d with x = 3, y = 3)))")
        self.assertEqual(got, "true")

    def test_collide_circles_matches_oracle(self):
        b = oracle()
        from pypybox2d.contact_util import Manifold
        from pypybox2d.collision import collide_circles

        a = b.Circle(radius=1.0, position=(0.0, 0.0))
        c = b.Circle(radius=1.0, position=(1.0, 0.0))
        manifold = Manifold()
        collide_circles(manifold, a, b.Transform(), c, b.Transform())
        self.assertEqual(manifold.point_count, 1)

        source = """
use the box2d module
set ca to call circle_shape from box2d with px = 0, py = 0, radius = 1
set cb to call circle_shape from box2d with px = 1, py = 0, radius = 1
set mf to call collide_circles from box2d with circle_a = ca, xf_a = (call identity_transform from box2d), circle_b = cb, xf_b = (call identity_transform from box2d)
show item "point_count" of mf
show item "x" of (item "local_point" of mf)
"""
        self.assertEqual(run(source), ["1", "0"])

    def test_math_primitives_over_many_numeric_cases(self):
        """Compare a deterministic numeric sweep against the original engine."""
        b = oracle()
        from pypybox2d.common import distance as oracle_distance

        cases = [
            (1.0, 2.0, 3.0, 4.0), (0.0, 0.0, -1.0, 1.0),
            (2.5, -3.25, -0.5, 7.75), (-9.0, 4.0, 2.0, -2.0),
            (0.125, 0.5, 0.25, 0.75), (10.0, 10.0, 10.0, 10.0),
            (-3.5, -4.5, 6.5, -1.5), (100.0, -0.1, 0.01, 200.0),
        ]
        lines = ["use the box2d module"]
        wants = []
        for index, (x1, y1, x2, y2) in enumerate(cases):
            a, c = b.Vec2(x1, y1), b.Vec2(x2, y2)
            va = f"(call vec2 from box2d with x = {num(x1)}, y = {num(y1)})"
            vc = f"(call vec2 from box2d with x = {num(x2)}, y = {num(y2)})"
            lines.append(f"show (call vec_dot from box2d with a = {va}, b = {vc})")
            wants.append(a.dot(c))
            lines.append(f"show (call vec_len from box2d with v = {va})")
            wants.append(a.length)
            lines.append(f"show (call vec_distance from box2d with p1 = {va}, p2 = {vc})")
            wants.append(oracle_distance(a, c))
        got = [float(item) for item in run("\n".join(lines))]
        self.assertEqual(len(got), len(wants))
        for index, (expected, actual) in enumerate(zip(wants, got)):
            self.assertTrue(close(expected, actual, 1e-12, 1e-12),
                            f"case {index}: got {actual}, want {expected}")

    def test_falling_body_60_steps_matches_oracle_and_analytic(self):
        b = oracle()
        world = b.World(gravity=(0, -10), do_sleep=False, warm_starting=False)
        ball = world.create_dynamic_body(position=(0, 0))
        ball.create_circle_fixture(radius=1, density=1)
        for _ in range(60):
            world.step(1.0 / 60.0, 8, 3)

        source = """
use the box2d module
set w to call new_world from box2d with gravity = (call vec2 from box2d with x = 0, y = (0 minus 10)), dt = (1 divided by 60), vel_iters = 8, pos_iters = 3
set ball to call new_dynamic_body from box2d with x = 0, y = 0, radius = 1, density = 1
call add_body from box2d with world = w, body = ball
call world_advance from box2d with world = w, steps = 60
show item "y" of (call body_position from box2d with body = ball)
show item "y" of (call body_linear_velocity from box2d with body = ball)
show item "step" of w
"""
        y, vy, steps = run(source)
        steps = int(steps)
        self.assertEqual(steps, 60)
        self.assertTrue(close(ball.position.y, float(y)),
                        f"oracle y={ball.position.y}, llang y={y}")
        self.assertTrue(close(ball.linear_velocity.y, float(vy)),
                        f"oracle vy={ball.linear_velocity.y}, llang vy={vy}")
        dt = 1.0 / 60.0
        analytic_y = 0.5 * -10.0 * (60 * dt) ** 2 + 0.5 * -10.0 * dt * (60 * dt)
        analytic_vy = -10.0 * 60 * dt
        self.assertAlmostEqual(float(y), analytic_y, delta=1e-6)
        self.assertAlmostEqual(float(vy), analytic_vy, delta=1e-6)

    def test_falling_trajectory_matches_oracle_every_step(self):
        b = oracle()
        world = b.World(gravity=(0, -9.8), do_sleep=False, warm_starting=False)
        ball = world.create_dynamic_body(position=(0, 0))
        ball.create_circle_fixture(radius=1, density=1)
        reference = []
        for _ in range(60):
            world.step(1.0 / 60.0, 8, 3)
            reference.append((ball.position.y, ball.linear_velocity.y))

        work = Path(tempfile.mkdtemp(prefix="llang_box2d_test_"))

        atexit.register(shutil.rmtree, work, ignore_errors=True)
        out = work / "trace.json"
        source = f"""
use the box2d module
use the foreign json module as hostjson
set w to call new_world from box2d with gravity = (call vec2 from box2d with x = 0, y = (0 minus 9.8)), dt = (1 divided by 60), vel_iters = 8, pos_iters = 3
set ball to call new_dynamic_body from box2d with x = 0, y = 0, radius = 1, density = 1
call add_body from box2d with world = w, body = ball
set trace to an empty list
set index to 0
repeat while index is less than 60
    call world_step from box2d with world = w
    add (a list of (item "y" of (call body_position from box2d with body = ball)), (item "y" of (call body_linear_velocity from box2d with body = ball))) to trace
    set index to index plus 1
end repeat
call write text to with path = "{str(out).replace(chr(92), '/')}", content = (call dumps from hostjson with value = trace)
"""
        run(source)
        trace = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(len(trace), 60)
        for index, (want_y, want_vy) in enumerate(reference):
            got_y, got_vy = trace[index]
            self.assertTrue(close(want_y, got_y), f"step {index}: y {got_y} != {want_y}")
            self.assertTrue(close(want_vy, got_vy), f"step {index}: vy {got_vy} != {want_vy}")

    def test_invalid_inputs_fail_loudly(self):
        with self.assertRaises(LangError) as ctx:
            run('use the box2d module\nshow call vec2 from box2d with x = "nope", y = 1')
        self.assertIn("physics_error", str(ctx.exception))

        with self.assertRaises(LangError) as ctx:
            run("use the box2d module\nshow call new_dynamic_body from box2d with x = 0, y = 0, radius = 0, density = 1")
        self.assertIn("physics_error", str(ctx.exception))

    def test_differential_corpus_has_zero_mismatches(self):
        import subprocess

        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "compare_box2d.py")],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        timeout=300)
        self.assertEqual(completed.returncode, 0,
                         f"{completed.stdout}\n{completed.stderr}")
        self.assertIn("0 mismatches", completed.stdout)


if __name__ == "__main__":
    unittest.main()
