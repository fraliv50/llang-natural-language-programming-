"""Compare lib/box2d.ll against the pinned pure-Python pypybox2d engine.

This is the verification harness for the Box2D rewrite.  It loads the pinned
clone read-only, computes expected values from the original engine, drives the
llang implementation through the interpreter, diffs every value, checks the
independent free-fall closed form, prints ``compared N cases, M mismatches``
and exits nonzero on any mismatch.
"""

import contextlib
import importlib
import io
import json
import math
import random
import subprocess
import sys
import atexit
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "tools" / "rewrites" / "pypybox2d" / "source"
sys.path.insert(0, str(ROOT / "src"))


def load_oracle():
    """Import the pinned clone, forcing the pure-Python math path."""
    if not (SOURCE / "pypybox2d" / "common.py").is_file():
        raise RuntimeError(f"pypybox2d clone not found at {SOURCE}")
    if str(SOURCE) not in sys.path:
        sys.path.insert(0, str(SOURCE))
    with contextlib.redirect_stdout(io.StringIO()):
        package = importlib.import_module("pypybox2d")
        common = importlib.import_module("pypybox2d.common")
        collision = importlib.import_module("pypybox2d.collision")
        contact_util = importlib.import_module("pypybox2d.contact_util")
        distance = importlib.import_module("pypybox2d.distance")
    assert common.Vec2 is common.PyVec2, "C math extension leaked into the oracle"
    return package, common, collision, contact_util, distance


def num(value):
    """Render a Python number as an llang number expression."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value) if value >= 0 else f"(0 minus {abs(value)})"
    text = repr(value)
    if text == "-0.0":
        return "(0.0 times (0 minus 1))"
    if "e" in text or "E" in text:
        return f'(call to number with text = "{text}")'
    if value < 0:
        return f"(0 minus {repr(abs(value))})"
    return text


def vec_expr(v):
    return f"(call vec2 from box2d with x = {num(v[0])}, y = {num(v[1])})"


def aabb_expr(box):
    lower, upper = box
    return (f"(call aabb from box2d with lower = {vec_expr(lower)}, "
            f"upper = {vec_expr(upper)})")


def circle_expr(c):
    px, py, radius = c
    return (f"(call circle_shape from box2d with px = {num(px)}, "
            f"py = {num(py)}, radius = {num(radius)})")


def transform_expr(xf):
    px, py, angle = xf
    return (f"(call transform from box2d with px = {num(px)}, "
            f"py = {num(py)}, angle = {num(angle)})")


IDENTITY_XF = (0.0, 0.0, 0.0)


def build_corpus():
    """Return (llang_lines, expected) for every differential case."""
    package, common, collision, contact_util, distance = load_oracle()
    Vec2, Mat22, Transform = common.Vec2, common.Mat22, common.Transform
    lines = [
        "use the box2d module",
        "use the foreign json module as hostjson",
        "set results to an empty map",
    ]
    expected = {}

    def record(key, want, expression):
        lines.append(f'set item "{key}" of results to {expression}')
        expected[key] = want

    rng = random.Random(20261122)
    vectors = []
    for _ in range(24):
        vectors.append((
            round(rng.uniform(-8, 8), 3),
            round(rng.uniform(-8, 8), 3),
            round(rng.uniform(-8, 8), 3),
            round(rng.uniform(-8, 8), 3),
            round(rng.uniform(0.25, 4.0), 3),
        ))

    # --- Stage 1a: Vec2 operations -----------------------------------------
    for i, (x1, y1, x2, y2, factor) in enumerate(vectors):
        a, b = Vec2(x1, y1), Vec2(x2, y2)
        ea, eb = vec_expr((x1, y1)), vec_expr((x2, y2))
        record(f"vadd{i}_x", (a + b).x, f"(item \"x\" of (call vec_add from box2d with a = {ea}, b = {eb}))")
        record(f"vadd{i}_y", (a + b).y, f"(item \"y\" of (call vec_add from box2d with a = {ea}, b = {eb}))")
        record(f"vsub{i}_x", (a - b).x, f"(item \"x\" of (call vec_sub from box2d with a = {ea}, b = {eb}))")
        record(f"vsub{i}_y", (a - b).y, f"(item \"y\" of (call vec_sub from box2d with a = {ea}, b = {eb}))")
        record(f"vscale{i}_x", (factor * a).x, f"(item \"x\" of (call vec_scale from box2d with v = {ea}, factor = {num(factor)}))")
        record(f"vscale{i}_y", (factor * a).y, f"(item \"y\" of (call vec_scale from box2d with v = {ea}, factor = {num(factor)}))")
        record(f"vdiv{i}_x", (a / factor).x, f"(item \"x\" of (call vec_div from box2d with v = {ea}, factor = {num(factor)}))")
        record(f"vdiv{i}_y", (a / factor).y, f"(item \"y\" of (call vec_div from box2d with v = {ea}, factor = {num(factor)}))")
        record(f"vneg{i}_x", (-a).x, f"(item \"x\" of (call vec_neg from box2d with v = {ea}))")
        record(f"vneg{i}_y", (-a).y, f"(item \"y\" of (call vec_neg from box2d with v = {ea}))")
        record(f"vdot{i}", a.dot(b), f"(call vec_dot from box2d with a = {ea}, b = {eb})")
        record(f"vcross{i}", a.cross(b), f"(call vec_cross from box2d with a = {ea}, b = {eb})")
        record(f"vlen{i}", a.length, f"(call vec_len from box2d with v = {ea})")
        record(f"vlen2{i}", a.length_squared, f"(call vec_len2 from box2d with v = {ea})")
        na = a.normalized
        record(f"vnorm{i}_x", na.x, f"(item \"x\" of (call vec_normalized from box2d with v = {ea}))")
        record(f"vnorm{i}_y", na.y, f"(item \"y\" of (call vec_normalized from box2d with v = {ea}))")
        record(f"vdist{i}", common.distance(a, b), f"(call vec_distance from box2d with p1 = {ea}, p2 = {eb})")
        record(f"vdist2{i}", common.distance_squared(a, b), f"(call vec_distance2 from box2d with p1 = {ea}, p2 = {eb})")
        vmin, vmax = common.min_vector(a, b), common.max_vector(a, b)
        record(f"vmin{i}_x", vmin.x, f"(item \"x\" of (call vec_min from box2d with a = {ea}, b = {eb}))")
        record(f"vmin{i}_y", vmin.y, f"(item \"y\" of (call vec_min from box2d with a = {ea}, b = {eb}))")
        record(f"vmax{i}_x", vmax.x, f"(item \"x\" of (call vec_max from box2d with a = {ea}, b = {eb}))")
        record(f"vmax{i}_y", vmax.y, f"(item \"y\" of (call vec_max from box2d with a = {ea}, b = {eb}))")
        sc = common.scalar_cross(factor, a)
        record(f"scross{i}_x", sc.x, f"(item \"x\" of (call scalar_cross from box2d with factor = {num(factor)}, v = {ea}))")
        record(f"scross{i}_y", sc.y, f"(item \"y\" of (call scalar_cross from box2d with factor = {num(factor)}, v = {ea}))")
        skew = a.skew()
        record(f"skew{i}_x", skew.x, f"(item \"x\" of (call vec_skew from box2d with v = {ea}))")
        record(f"skew{i}_y", skew.y, f"(item \"y\" of (call vec_skew from box2d with v = {ea}))")
        vc = common.clamp_vector(a, Vec2(-1, -1), Vec2(1, 1))
        record(f"vclamp{i}_x", vc.x, f"(item \"x\" of (call vec_clamp from box2d with v = {ea}, low = {vec_expr((-1, -1))}, high = {vec_expr((1, 1))}))")
        record(f"vclamp{i}_y", vc.y, f"(item \"y\" of (call vec_clamp from box2d with v = {ea}, low = {vec_expr((-1, -1))}, high = {vec_expr((1, 1))}))")
        record(f"vvalid{i}", a.valid, f"(call vec_valid from box2d with v = {ea})")

    # --- Stage 1b: scalar helpers ------------------------------------------
    scalars = [0, 1, 2, 3, 7, 8, 16, 31, 32, 33, 1024, 4097, -1, -8, -31,
               0.25, 2.5, 99.75]
    for i, value in enumerate(scalars):
        record(f"clamp{i}", common.clamp(value, 0, 10),
               f"(call clamp from box2d with value = {num(value)}, low = 0, high = 10)")
        record(f"npot{i}", common.next_power_of_two(value),
               f"(call next_power_of_two from box2d with value = {num(value)})")
        if isinstance(value, int):
            record(f"ipo2{i}", common.is_power_of_two(value),
                   f"(call is_power_of_two from box2d with value = {num(value)})")
        record(f"validf{i}", common.is_valid_float(float(value)),
               f"(call is_valid_float from box2d with value = {num(float(value))})")
        if value > 0:
            record(f"isqrt{i}", common.inv_sqrt(float(value)),
                   f"(call inv_sqrt from box2d with value = {num(float(value))})")

    # --- Stage 1c: Mat22 ---------------------------------------------------
    angles = [0.0, 0.1, 0.5, 1.0, 2.5, -0.7]
    for i, angle in enumerate(angles):
        m = Mat22(angle=angle)
        n = Mat22(angle=angle + 0.3)
        record(f"mangle{i}_c1x", m.col1.x, f"(item \"x\" of (item \"c1\" of (call mat_angle from box2d with angle = {num(angle)})))")
        record(f"mangle{i}_c1y", m.col1.y, f"(item \"y\" of (item \"c1\" of (call mat_angle from box2d with angle = {num(angle)})))")
        record(f"mangle{i}_c2x", m.col2.x, f"(item \"x\" of (item \"c2\" of (call mat_angle from box2d with angle = {num(angle)})))")
        record(f"mangle{i}_c2y", m.col2.y, f"(item \"y\" of (item \"c2\" of (call mat_angle from box2d with angle = {num(angle)})))")
        for j, (vx, vy) in enumerate([(1.0, 0.0), (0.5, -2.0), (-3.0, 4.0)]):
            v = Vec2(vx, vy)
            product, transpose = m * v, m.mul_tv(v)
            record(f"mmul{i}_{j}_x", product.x, f"(item \"x\" of (call mat_mul_vec from box2d with m = (call mat_angle from box2d with angle = {num(angle)}), v = {vec_expr((vx, vy))}))")
            record(f"mmul{i}_{j}_y", product.y, f"(item \"y\" of (call mat_mul_vec from box2d with m = (call mat_angle from box2d with angle = {num(angle)}), v = {vec_expr((vx, vy))}))")
            record(f"mmultv{i}_{j}_x", transpose.x, f"(item \"x\" of (call mat_mul_tv from box2d with m = (call mat_angle from box2d with angle = {num(angle)}), v = {vec_expr((vx, vy))}))")
            record(f"mmultv{i}_{j}_y", transpose.y, f"(item \"y\" of (call mat_mul_tv from box2d with m = (call mat_angle from box2d with angle = {num(angle)}), v = {vec_expr((vx, vy))}))")
            solved = m.solve(v)
            record(f"msolve{i}_{j}_x", solved.x, f"(item \"x\" of (call mat_solve from box2d with m = (call mat_angle from box2d with angle = {num(angle)}), v = {vec_expr((vx, vy))}))")
            record(f"msolve{i}_{j}_y", solved.y, f"(item \"y\" of (call mat_solve from box2d with m = (call mat_angle from box2d with angle = {num(angle)}), v = {vec_expr((vx, vy))}))")
        # The pure-Python Mat22 only overloads multiplication by a vector, so
        # build the expected matrix column by column using that supported path.
        first_column = m * n.col1
        inv = m.inverse
        record(f"mmatm{i}_c1x", first_column.x, f"(item \"x\" of (item \"c1\" of (call mat_mul from box2d with a = (call mat_angle from box2d with angle = {num(angle)}), b = (call mat_angle from box2d with angle = {num(angle + 0.3)}))))")
        record(f"minv{i}_c1x", inv.col1.x, f"(item \"x\" of (item \"c1\" of (call mat_inverse from box2d with m = (call mat_angle from box2d with angle = {num(angle)}))))")
        record(f"minv{i}_c1y", inv.col1.y, f"(item \"y\" of (item \"c1\" of (call mat_inverse from box2d with m = (call mat_angle from box2d with angle = {num(angle)}))))")
        record(f"minv{i}_c2x", inv.col2.x, f"(item \"x\" of (item \"c2\" of (call mat_inverse from box2d with m = (call mat_angle from box2d with angle = {num(angle)}))))")
        record(f"minv{i}_c2y", inv.col2.y, f"(item \"y\" of (item \"c2\" of (call mat_inverse from box2d with m = (call mat_angle from box2d with angle = {num(angle)}))))")

    # --- Stage 1d: Transform -----------------------------------------------
    xforms = [(0.0, 0.0, 0.0), (3.0, -4.0, 0.5), (-1.5, 2.25, -1.1)]
    for i, xf in enumerate(xforms):
        tx = Transform(position=(xf[0], xf[1]), angle=xf[2])
        for j, (vx, vy) in enumerate([(1.0, 2.0), (-2.0, 0.5)]):
            p = tx * Vec2(vx, vy)
            q = tx.mul_t(Vec2(vx, vy))
            record(f"xfpt{i}_{j}_x", p.x, f"(item \"x\" of (call transform_point from box2d with t = {transform_expr(xf)}, v = {vec_expr((vx, vy))}))")
            record(f"xfpt{i}_{j}_y", p.y, f"(item \"y\" of (call transform_point from box2d with t = {transform_expr(xf)}, v = {vec_expr((vx, vy))}))")
            record(f"xfiv{i}_{j}_x", q.x, f"(item \"x\" of (call transform_inv_point from box2d with t = {transform_expr(xf)}, v = {vec_expr((vx, vy))}))")
            record(f"xfiv{i}_{j}_y", q.y, f"(item \"y\" of (call transform_inv_point from box2d with t = {transform_expr(xf)}, v = {vec_expr((vx, vy))}))")

    # --- Stage 1e: AABB ----------------------------------------------------
    boxes = [
        ((0.0, 0.0), (2.0, 2.0)),
        ((-3.0, -1.0), (1.0, 4.0)),
        ((1.0, 1.0), (1.5, 2.5)),
    ]
    for i, box in enumerate(boxes):
        oracle_box = common.AABB(box[0], box[1])
        bexpr = aabb_expr(box)
        centre, extents = oracle_box.center, oracle_box.extents
        record(f"abcenter{i}_x", centre.x, f"(item \"x\" of (call aabb_center from box2d with box = {bexpr}))")
        record(f"abcenter{i}_y", centre.y, f"(item \"y\" of (call aabb_center from box2d with box = {bexpr}))")
        record(f"abext{i}_x", extents.x, f"(item \"x\" of (call aabb_extents from box2d with box = {bexpr}))")
        record(f"abext{i}_y", extents.y, f"(item \"y\" of (call aabb_extents from box2d with box = {bexpr}))")
        record(f"abperi{i}", oracle_box.perimeter, f"(call aabb_perimeter from box2d with box = {bexpr})")
        record(f"abvalid{i}", oracle_box.valid, f"(call aabb_valid from box2d with box = {bexpr})")
        for j, other in enumerate(boxes):
            oracle_other = common.AABB(other[0], other[1])
            record(f"abover{i}_{j}", oracle_box.test_overlap(oracle_other),
                   f"(call aabb_overlaps from box2d with first = {bexpr}, second = {aabb_expr(other)})")
            record(f"abcont{i}_{j}", oracle_box.contains(oracle_other),
                   f"(call aabb_contains from box2d with box = {bexpr}, other = {aabb_expr(other)})")
            merged = oracle_box + oracle_other
            record(f"abmerge{i}_{j}_x", merged.lower_bound.x, f"(item \"x\" of (item \"lower\" of (call aabb_combine from box2d with first = {bexpr}, second = {aabb_expr(other)})))")
            record(f"abmerge{i}_{j}_y", merged.upper_bound.y, f"(item \"y\" of (item \"upper\" of (call aabb_combine from box2d with first = {bexpr}, second = {aabb_expr(other)})))")
        for j, (p1, p2) in enumerate([
            ((-4.0, 1.0), (4.0, 1.0)),
            ((0.5, 0.5), (0.5, 5.0)),
            ((10.0, 10.0), (11.0, 11.0)),
        ]):
            hit, normal, fraction = oracle_box.ray_cast(Vec2(*p1), Vec2(*p2), 1.0)
            rayexpr = (f"(call aabb_ray_cast from box2d with box = {bexpr}, "
                       f"p1 = {vec_expr(p1)}, p2 = {vec_expr(p2)}, max_fraction = 1)")
            record(f"abray{i}_{j}_hit", hit, f"(item \"hit\" of {rayexpr})")
            if normal is not None:
                record(f"abray{i}_{j}_nx", normal.x, f"(item \"x\" of (item \"normal\" of {rayexpr}))")
                record(f"abray{i}_{j}_ny", normal.y, f"(item \"y\" of (item \"normal\" of {rayexpr}))")
            record(f"abray{i}_{j}_frac", fraction, f"(item \"fraction\" of {rayexpr})")

    # --- Stage 2: collide_circles, shape_distance, test_overlap -------------
    circle_pairs = [
        ((0.0, 0.0, 1.0), (1.0, 0.0, 1.0)),
        ((0.0, 0.0, 1.0), (3.0, 0.0, 1.0)),
        ((0.0, 0.0, 0.5), (0.0, 0.0, 0.5)),
        ((2.0, -1.0, 1.5), (3.0, -1.0, 0.5)),
        ((-4.0, 2.0, 2.0), (-1.0, 2.0, 2.0)),
    ]
    for i, (ca, cb) in enumerate(circle_pairs):
        oracle_a = package.Circle(radius=ca[2], position=(ca[0], ca[1]))
        oracle_b = package.Circle(radius=cb[2], position=(cb[0], cb[1]))
        manifold = contact_util.Manifold()
        collision.collide_circles(manifold, oracle_a, Transform(), oracle_b, Transform())
        mexpr = (f"(call collide_circles from box2d with circle_a = {circle_expr(ca)}, "
                 f"xf_a = {transform_expr(IDENTITY_XF)}, circle_b = {circle_expr(cb)}, "
                 f"xf_b = {transform_expr(IDENTITY_XF)})")
        record(f"col{i}_count", manifold.point_count, f"(item \"point_count\" of {mexpr})")
        if manifold.point_count:
            record(f"col{i}_lp_x", manifold.local_point.x, f"(item \"x\" of (item \"local_point\" of {mexpr}))")
            record(f"col{i}_lp_y", manifold.local_point.y, f"(item \"y\" of (item \"local_point\" of {mexpr}))")
            point = manifold.points[0].local_point
            record(f"col{i}_p0_x", point.x, f"(item \"x\" of (item \"local_point\" of (item 0 of (item \"points\" of {mexpr}))))")
            record(f"col{i}_p0_y", point.y, f"(item \"y\" of (item \"local_point\" of (item 0 of (item \"points\" of {mexpr}))))")
        proxy_a, proxy_b = distance.DistanceProxy(oracle_a, 0), distance.DistanceProxy(oracle_b, 0)
        point_a, point_b, dist, iterations = distance.shape_distance(
            proxy_a, proxy_b, Transform(), Transform(), True)
        dexpr = (f"(call shape_distance from box2d with proxy_a = (call circle_proxy from box2d with circle = {circle_expr(ca)}), "
                 f"proxy_b = (call circle_proxy from box2d with circle = {circle_expr(cb)}), "
                 f"transform_a = {transform_expr(IDENTITY_XF)}, "
                 f"transform_b = {transform_expr(IDENTITY_XF)}, use_radii = true)")
        record(f"sd{i}_distance", dist, f"(item \"distance\" of {dexpr})")
        record(f"sd{i}_pa_x", point_a.x, f"(item \"x\" of (item \"point_a\" of {dexpr}))")
        record(f"sd{i}_pa_y", point_a.y, f"(item \"y\" of (item \"point_a\" of {dexpr}))")
        record(f"sd{i}_pb_x", point_b.x, f"(item \"x\" of (item \"point_b\" of {dexpr}))")
        record(f"sd{i}_pb_y", point_b.y, f"(item \"y\" of (item \"point_b\" of {dexpr}))")
        overlap = distance.test_overlap(oracle_a, 0, oracle_b, 0, Transform(), Transform())
        texpr = (f"(call test_overlap from box2d with proxy_a = (call circle_proxy from box2d with circle = {circle_expr(ca)}), "
                 f"proxy_b = (call circle_proxy from box2d with circle = {circle_expr(cb)}), "
                 f"transform_a = {transform_expr(IDENTITY_XF)}, "
                 f"transform_b = {transform_expr(IDENTITY_XF)})")
        record(f"ov{i}", overlap, texpr)

    # --- Stage 3: headless falling bodies ----------------------------------
    fall_cases = [
        ((0.0, -10.0), 1.0 / 60.0, 60),
        ((0.0, -9.8), 1.0 / 120.0, 120),
        ((0.0, -20.0), 1.0 / 30.0, 30),
        ((0.0, -10.0), 1.0 / 60.0, 1),
        ((3.0, -7.0), 1.0 / 45.0, 25),
    ]
    for i, (gravity, dt, steps) in enumerate(fall_cases):
        world = package.World(gravity=gravity, do_sleep=False, warm_starting=False)
        body = world.create_dynamic_body(position=(0, 0))
        body.create_circle_fixture(radius=1, density=1)
        for _ in range(steps):
            world.step(dt, 8, 3)
        lines.extend([
            f"set fallw{i} to call new_world from box2d with gravity = {vec_expr(gravity)}, dt = {num(dt)}, vel_iters = 8, pos_iters = 3",
            f"set fallb{i} to call new_dynamic_body from box2d with x = 0, y = 0, radius = 1, density = 1",
            f"call add_body from box2d with world = fallw{i}, body = fallb{i}",
            f"call world_advance from box2d with world = fallw{i}, steps = {steps}",
        ])
        record(f"fall{i}_x", body.position.x, f"(item \"x\" of (call body_position from box2d with body = fallb{i}))")
        record(f"fall{i}_y", body.position.y, f"(item \"y\" of (call body_position from box2d with body = fallb{i}))")
        record(f"fall{i}_vx", body.linear_velocity.x, f"(item \"x\" of (call body_linear_velocity from box2d with body = fallb{i}))")
        record(f"fall{i}_vy", body.linear_velocity.y, f"(item \"y\" of (call body_linear_velocity from box2d with body = fallb{i}))")
        record(f"fall{i}_steps", steps, f"(item \"step\" of fallw{i})")

    lines.append("show (call dumps from hostjson with value = results)")
    return lines, expected, fall_cases


def close_enough(want, got, *, rel=1e-12, abs_=1e-12):
    if isinstance(want, bool) or isinstance(got, bool):
        return want is got
    if isinstance(want, (int, float)) and isinstance(got, (int, float)):
        if want == got:
            return True
        return math.isclose(got, want, rel_tol=rel, abs_tol=abs_)
    return want == got


def main():
    work = Path(tempfile.mkdtemp(prefix="llang_box2d_"))
    atexit.register(shutil.rmtree, work, ignore_errors=True)
    lines, expected, fall_cases = build_corpus()
    harness_path = work / "harness.ll"
    harness_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(ROOT / "run.py"), str(harness_path)],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
    timeout=300)
    if completed.returncode != 0:
        print("llang run failed:")
        print(completed.stdout)
        print(completed.stderr)
        sys.exit(1)

    actual = json.loads(completed.stdout.strip().splitlines()[-1])
    mismatches = 0
    for key, want in expected.items():
        got = actual.get(key)
        is_fall = key.startswith("fall")
        ok = close_enough(want, got, rel=1e-6, abs_=1e-6) if is_fall else close_enough(want, got)
        if not ok:
            mismatches += 1
            print(f"{key}: got {got!r}, want {want!r}")

    # Independent analytic oracle: semi-implicit Euler in closed form.
    g, dt, steps = fall_cases[0]
    analytic_y = 0.5 * g[1] * (steps * dt) ** 2 + 0.5 * g[1] * dt * (steps * dt)
    analytic_vy = g[1] * steps * dt
    for key, analytic in (("fall0_y", analytic_y), ("fall0_vy", analytic_vy)):
        if not close_enough(analytic, actual.get(key), rel=1e-6, abs_=1e-6):
            mismatches += 1
            print(f"analytic {key}: got {actual.get(key)!r}, want {analytic!r}")

    total = len(expected) + 2
    print(f"compared {total} cases, {mismatches} mismatches")
    if mismatches:
        sys.exit(1)
    print("lib/box2d.ll matches pinned pypybox2d (pure Python path)")
    print(f"falling body after 60 steps: y={actual['fall0_y']!r}, vy={actual['fall0_vy']!r}")


if __name__ == "__main__":
    main()
