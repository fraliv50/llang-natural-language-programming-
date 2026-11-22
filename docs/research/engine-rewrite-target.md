# Engine rewrite target: research and recommendation

**Question:** which real physics/game engine should llang rewrite end-to-end (one ambitious rewrite, not a template engine) so that the port is large enough to stress edge cases and can be verified differentially against the original?

**Answer:** [`pybox2d/pypybox2d`](https://github.com/pybox2d/pypybox2d) at commit
`ee7b81ff83a03d017534f5f7ac36e642ac27e33c`. It is a ~10.5k-line pure-Python
port of Box2D under the zlib license, its entire computational core runs
headlessly, and it is small enough to port in stages but large enough to
exercise floating-point drift, SAT/GJK/TOI edge cases, sleeping, warm
starting, joint solving, and ordering dependence.

All line counts and commit hashes below were measured from fresh `--depth 1`
clones on 2026-11-22 using `git clone <url> <dir>; git log -1 --format=%H` and
`(Get-ChildItem -Recurse -Filter *.py | Measure-Object -Line -Sum)`. Source URLs
are inline; when a fact came from a cloned file I cite the raw file URL.

---

## 1. Selection criteria

A candidate had to satisfy **all** of:

1. **Mostly pure Python** — no C/C++ extension, CFFI backend, or GPU kernel
   needed to execute the computational core. (A *optional* accelerator that
   can be switched off is acceptable; see pypybox2d's `_common`.)
2. **Substantial but bounded:** roughly 5k–50k Python lines. Too small and it
   teaches llang nothing; too large and the rewrite stops being one project.
3. **Clear permissive license** so a derived llang library and its tests can be
   published without infecting llang's own license.
4. **Verifiable headless core** — integration, collision detection, force/contact
   solving, scene-graph/transform math, or deterministic event scheduling that
   produces numeric/structured output without a display, window, audio device,
   or input event loop.
5. **Deterministic or determinisable** — fixed-step, fixed iteration counts,
   stable iteration order, and serialisable state, so a golden-file differential
   oracle is possible.

---

## 2. Candidate evaluation (7 evaluated, 6 in depth)

### Summary table

| # | Candidate | License | Language mix | Python LOC (core / all) | Headless core? | Fit |
|---|---|---|---|---|---|---|
| 1 | [pybox2d/pypybox2d](https://github.com/pybox2d/pypybox2d) | zlib ([LICENSE](https://raw.githubusercontent.com/pybox2d/pypybox2d/master/LICENSE), `__license__='zlib'` in [setup.py](https://raw.githubusercontent.com/pybox2d/pypybox2d/master/setup.py)) | Python + 5 **optional** C math files | 10,531 / 18,006 | **Yes** — rigid-body stepping, collision, GJK, TOI, broadphase | **Best** |
| 2 | [google-deepmind/pycolab](https://github.com/google-deepmind/pycolab) | Apache-2.0 ([LICENSE](https://raw.githubusercontent.com/google-deepmind/pycolab/master/LICENSE)) | Python, but core imports NumPy + `six` | ~12,083 / 12,083 | Yes — gridworld fixed-step engine; board is `numpy.ndarray` | Strong runner-up |
| 3 | [los-cocos/cocos](https://github.com/los-cocos/cocos) (Python cocos2d) | **Split:** BSD-3-Clause engine ([LICENSE](https://raw.githubusercontent.com/los-cocos/cocos/master/LICENSE)) + **LGPL-2.1** for `cocos/euclid.py` ([LICENSE.euclid](https://raw.githubusercontent.com/los-cocos/cocos/master/LICENSE.euclid)) | Python; pyglet/OpenGL render, pygame/SDL audio | ~42,175 / 42,175 | Partial — math/actions/scene graph testable but package import pulls display deps | License + coupling problems |
| 4 | [team-simpy/simpy](https://gitlab.com/team-simpy/simpy) | MIT ([LICENSE.rst](https://gitlab.com/team-simpy/simpy/-/raw/master/LICENSE.rst)) | Pure Python | ~1,700 src / 4,455 all | Yes — deterministic discrete-event scheduler | Too small, no physics |
| 5 | [viblo/pymunk](https://github.com/viblo/pymunk) | MIT | Python wrapper over **CFFI + Chipmunk/Munk2D C** ([README](https://github.com/viblo/pymunk#readme)) | Python code only; C core required | Core runs headless but **not written in Python** | Rejected: not pure Python |
| 6 | [pybox2d/pybox2d](https://github.com/pybox2d/pybox2d) | zlib-like ([LICENSE](https://raw.githubusercontent.com/pybox2d/pybox2d/master/LICENSE)) | **C++/SWIG** + Python; "based on the Box2D library, written in C++" ([README](https://github.com/pybox2d/pybox2d#readme)) | n/a (C++ core) | Needs compiler; examples need a renderer backend | Rejected: not pure Python |
| 7 | [evennia/evennia](https://github.com/evennia/evennia) | BSD-3-Clause ([LICENSE.txt](https://raw.githubusercontent.com/evennia/evennia/master/LICENSE.txt)) | Pure Python + Django/ORM | 149,215 / 149,215 | Mostly (text MUD) | Rejected: 3–30× over size cap, no numeric core |

---

### 2.1 `pybox2d/pypybox2d` — the choice

- **Repo:** https://github.com/pybox2d/pypybox2d — "(Optionally) pure-Python 2D
  game physics, a Box2D port" ([GitHub](https://github.com/pybox2d/pypybox2d)).
  Upstream algorithm authority is Erin Catto's Box2D
  (https://github.com/erincatto/box2d, https://box2d.org/documentation/).
- **License:** zlib. The cloned `LICENSE` begins "C++ version Copyright (c)
  2006-2011 Erin Catto … Python port by Ken Lauer", and `setup.py` declares
  `__license__='zlib'`. Only attribution and "mark altered versions" are
  required — no copyleft, so the llang port can ship under llang's license with
  a NOTICE. https://opensource.org/license/zlib
- **Language mix:** 89 Python files, 10,531 lines in the `pypybox2d/` package;
  18,006 lines including `tests/`, `examples/`, `testbed/`. The only C is five
  optional math modules in `pypybox2d/src/` (`vec2module.c`, `mat22module.c`,
  `aabbmodule.c`, `transform.c`, `commonmodule.c`). `pypybox2d/common.py` tries
  `from ._common import Vec2, Mat22, Transform, AABB` and on any failure falls
  back to `PyVec2/PyMat22/PyTransform/PyAABB`; `pypybox2d/settings.py:134`
  defines `USE_PURE_PYTHON = False` and forcing it to `True` selects the pure
  path deterministically. ([common.py tail](https://raw.githubusercontent.com/pybox2d/pypybox2d/master/pypybox2d/common.py),
  [settings.py](https://raw.githubusercontent.com/pybox2d/pypybox2d/master/pypybox2d/settings.py))
- **Module structure (measured):**
  `common.py` 880 (Vec2/Mat22/AABB/Transform/Mat33/Sweep/constants),
  `world.py` 796 (`World`, `TimeStep`, `step`, `_solve`, `solve_toi`),
  `body.py` 794, `shapes.py` 771 (Circle/Polygon/Edge/Loop + ray casts),
  `contact.py` 767, `dynamictree.py` 617, `collision.py` 564, `distance.py` 484
  (GJK), `toi.py` 310, `island.py` 303, `contact_util.py` 300,
  `collision_util.py` 133, `broadphase.py` 130, `fixture.py` 263,
  `controllers.py` 247, `settings.py` 104, and 12 joint modules under
  `joints/` (revolute 370, prismatic 418, wheel 326, gear 324, pulley 252,
  distance 243, weld 200, rope 194, friction 180, mouse 186, base 93).
- **Verifiable subset:** everything above. In particular the *pure functions*
  `collide_circles`, `collide_polygon_circle`, `collide_polygons`,
  `collide_edge_circle`, `collide_edge_polygon`; `distance.shape_distance` /
  `distance.test_overlap`; `toi.time_of_impact`; `collision_util.*`;
  `common.{PyVec2, PyMat22, PyTransform, PyAABB, Sweep, distance,
  distance_squared, next_power_of_two, clamp, clamp_vector, inv_sqrt}`;
  `dynamictree.DynamicTree`; `contact_util.Manifold/WorldManifold`;
  `World.step(dt, vel_iters, pos_iters)` and `World._solve`.
- **Proof it runs headlessly (executed during this research):** with the C
  extension absent, importing `pypybox2d` prints `Using Pure Python
  (<class 'ModuleNotFoundError'>: No module named 'pypybox2d._common')`, and:

  ```python
  w = b.World(gravity=(0, -10), do_sleep=False, warm_starting=False)
  g = w.create_dynamic_body(position=(0, 0))
  g.create_circle_fixture(radius=1, density=1)
  for _ in range(60):
      w.step(1.0/60.0, 8, 3)
  ```

  yields `position == Vec2(0, -5.08333)` and `linear_velocity == Vec2(0, -10)`.
  That matches the closed-form semi-implicit-Euler result
  `y_n = ½·g·(n·dt)² + ½·g·dt·(n·dt) = -5 - 0.083333…`, so the oracle is both
  deterministic and independently checkable. No display, GPU, pygame, or
  audio import is needed; only `tests/`, `examples/`, and `testbed/` touch
  pygame ([README](https://raw.githubusercontent.com/pybox2d/pypybox2d/master/README)).

### 2.2 `google-deepmind/pycolab` — deterministic fixed-step gridworld engine

- **Repo/license:** https://github.com/google-deepmind/pycolab, Apache-2.0;
  12,083 Python lines in 44 files at `6504c8065dd5322438f23a2a9026649904f3322a`.
- **Language mix:** Python only, but the core `pycolab/engine.py` imports
  `numpy as np` and `six` ([engine.py](https://raw.githubusercontent.com/google-deepmind/pycolab/master/pycolab/engine.py)), and board state is an
  `np.ndarray`. The terminal UI is optional (`human_ui.py`).
- **Structure:** `engine.py` 811 (`Engine.play`, turn/physics loop),
  `things.py` ( sprites, `Sprite.on_collision`), `plot.py` (reward/channels),
  `rendering.py` 538, `cropping.py` 498, `storytelling.py` 541,
  `prefab_parts/{sprites,drapes}.py`, `protocols/{scrolling,logging}.py`,
  `tests/engine_test.py` 518 (golden trace tests), plus `examples/`.
- **Verifiable subset:** `Engine.play` with headless `human_ui` omitted —
  output is a character grid, reward, and `game_over`; `things.MazeWalker`
  movement/wall collision; `cropping.Cropping` observation windows; `plot`
  reward assignment. `tests/engine_test.py` already provides golden trajectories.
- **Why not chosen:** no continuous physics, forces, transform math, or contact
  solver — the semantics to stress are discrete event ordering and NumPy array
  layout. llang would need a NumPy-compatible array type first (cf.
  [`datascience-library-design.md`](datascience-library-design.md)), which is a
  different feedback loop than the numeric/geometry one this rewrite wants.

### 2.3 `los-cocos/cocos` — scene graph + actions + collision engine

- **Repo/license:** https://github.com/los-cocos/cocos; 42,175 Python lines in
  372 files at `24ec855c2817a1ecf1f2151130ea920108319f4d`. **License split:**
  BSD-3-Clause for the engine, but `LICENSE.euclid` puts `cocos/euclid.py`
  under LGPL-2.1. A derived llang math library that copies euclid's code or
  design closely would inherit obligations — a real cost.
- **Structure:** `cocos/euclid.py` 2,006 (Vec2/Vec3/Mat3/Quaternion/transform
  math), `cocos/cocosnode.py` 773 (scene graph tree, transform composition),
  `cocos/actions/base_actions.py` 812 (composable Move/Rotate/Scale + easing),
  `cocos/collision_model.py` 715, `cocos/tiles.py` 1,641 (tile map logic),
  `cocos/scenes/`, `cocos/layer/`, and `cocos/audio/{SDL,pygame}/mixer.py`
  (SDL mixer 1,006 lines).
- **Verifiable subset headlessly:** `euclid.py` as a standalone math module;
  `actions/` interpolation and easing (pure functions of time);
  `collision_model.py` AABB/circle tests; `cocosnode` transform composition
  when importing only those modules. Rendering (`pyglet`/OpenGL) and audio
  (`pygame`/SDL) are not needed for these.
- **Why not chosen:** display-oriented architecture — importing the `cocos`
  package pulls pyglet; the rich parts (effects, transitions, menus) are
  shader/render bound. Combined with the mixed license and 42k lines, it is a
  weaker first rewrite than a self-contained physics core.

### 2.4 `team-simpy/simpy` — deterministic discrete-event engine

- **Repo/license:** https://gitlab.com/team-simpy/simpy (the old GitHub URL
  `github.com/SimPy/simpy` is now 404); MIT; tag `4.1.2`,
  commit `f43816490c6f76f336ad6e457d3cab9f386894af`.
- **Structure:** `src/simpy/core.py` 210 (`Environment`, event heap),
  `events.py` 500 (`Event`, `Timeout`, `Process`, `AllOf`, `AnyOf`, `Condition`),
  `resources/{base,container,resource,store}.py`, `rt.py` (real-time clock),
  `util.py`; ~4,455 Python lines including tests.
- **Verifiable subset:** event heap ordering, simultaneous-event tie-breaking,
  generator-based process resumption, resource queue fairness. Goldens are
  event traces `(time, event_type, value)`.
- **Why not chosen:** 4,455 total lines is below the 5k floor (~1,700 lines of
  actual library code), and there is no geometry, integration, or force
  solving — it would not stress llang's numeric semantics.

### 2.5 `viblo/pymunk` — rejected contrast case

MIT and 1.1k stars, but its own README states it "is built on top of Munk2D, a
fork of the very capable 2D physics library Chipmunk2D", depends on CFFI, ships
prebuilt Chipmunk C, and needs GCC/Visual Studio to build from source
(https://github.com/viblo/pymunk#readme). Its Python files are a wrapper; the
simulation math lives in C. Translating it to llang would mean reimplementing
Chipmunk, not rewriting Python — exactly what this project is not about.

### 2.6 `pybox2d/pybox2d` — rejected contrast case

515 stars; README: "pybox2d is a 2D physics library … based on the Box2D
library, written in C++" and it ships `Box2D/` C++/SWIG sources plus a
`library/Box2D/examples` testbed requiring pygame/pyglet/OpenCV backends
(https://github.com/pybox2d/pybox2d#readme). Useful as a catalogue of
scenario names (pyramid, tumbler, time_of_impact, one_sided_platform, …) for
the oracle, but not a Python source to rewrite.

### 2.7 `evennia/evennia` — rejected on size and fit

BSD-3-Clause and pure Python, but 149,215 lines across 653 files at
`98b9df21c91b111dda7c51c8ab62f42faf4d9dae`, with Django/ORM persistence and a
text-MUD ticker rather than a numeric core. Three to thirty times the requested
size; it would become a multi-year migration, not one rewrite.

---

## 3. Decision and justification

| Criterion (weight) | pypybox2d | pycolab | cocos | simpy |
|---|---|---|---|---|
| Pure Python / no native core (×2) | 5 | 4 | 3 | 5 |
| Size in 5k–50k (×1) | 5 | 5 | 4 | 2 |
| Headless numeric core (×2) | 5 | 4 | 3 | 4 |
| Rich physics/transform semantics (×2) | 5 | 2 | 4 | 1 |
| License simplicity (×1) | 5 | 4 | 2 | 5 |
| Golden-file oracle ease (×1) | 5 | 5 | 3 | 5 |
| **Weighted total** | **50** | 38 | 31 | 35 |

**pypybox2d wins because:**

1. It is the only candidate that combines a permissive zlib license, a genuine
   pure-Python implementation of a well-known algorithm, and the right size.
2. Its core is *numerically dense but display-free*: 10.5k lines of vector math,
   SAT, GJK, EPA, TOI, broadphase, constraint solving, and 12 joint types —
   exactly the constructs that will force llang to get operator precedence,
   in-place mutation, fixed-size records, and float semantics right.
3. The oracle is trivially headless and independently verifiable (the free-fall
   closed form above; Box2D's own published algorithms as a second reference).
4. The upstream C++ Box2D and the SWIG `pybox2d` exist as *optional* second
   oracles for cross-checking goldens, without being the port target.
5. Staged porting is natural: pure math → pure geometry functions → broadphase →
   solver → `World.step` → joints, with a runnable differential test at every
   stage.

---

## 4. Concrete rewrite plan

### 4.1 Clone and pin

```bash
git clone https://github.com/pybox2d/pypybox2d.git engine-oracle
cd engine-oracle
git checkout ee7b81ff83a03d017534f5f7ac36e642ac27e33c
git rev-parse HEAD   # must print ee7b81ff83a03d017534f5f7ac36e642ac27e33c
```

`master`'s tip at research time is exactly that commit (dated 2019-05-11,
"Merge pull request #3 from PeterJCLaw/python3"). Do **not** run `python setup.py
build_ext`; absence of the optional `pypybox2d._common` extension forces the
pure-Python math path. Optionally set `pypybox2d.settings.USE_PURE_PYTHON = True`
before first import and assert the printed banner says `Using Pure Python`.
Never build the C extension into the oracle: C and Python math paths can differ
by a ULP and would invalidate bit-exact comparisons.

### 4.2 Verifiable subset, port order

| Stage | Modules / symbols | Why it is a good differential unit |
|---|---|---|
| 0 | `settings.py` constants (`LINEAR_SLOP`, `AABB_EXTENSION`, `AABB_MULTIPLIER`, `POLYGON_RADIUS`, `BAUMGARTE`, `MAX_LINEAR_CORRECTION`, `VELOCITY_THRESHOLD`, `TIME_TO_SLEEP`, `DISTANCE_MAX_ITERS`, `TOI_MAX_ITERS`, `USE_PURE_PYTHON`) and `common.py` exceptions | Pure constants/exceptions; validates llang's module constants and exception model |
| 1 | `common.py`: `PyVec2`, `PyMat22`, `PyTransform`, `PyAABB`, `Mat33`, `Sweep`, `distance`, `distance_squared`, `scalar_cross`, `min_vector`, `max_vector`, `clamp`, `clamp_vector`, `next_power_of_two`, `is_power_of_two`, `is_valid_float`, `inv_sqrt` | Thousands of tiny deterministic numeric cases; catches operator/mutation semantics immediately |
| 2 | `collision.py`: all five `collide_*` functions + `EPAxis`, `EPCollider`; `collision_util.py`: `edge_separation`, `max_separation`, `find_incident_edge`, `clip_segment_to_line` | Pure functions of shapes/transforms → manifold arrays; ideal for randomized fuzzing |
| 3 | `distance.py`: `shape_distance`, `test_overlap`, `Simplex`, `DistanceProxy`; `toi.py`: `time_of_impact`, `SeparationFunction` | Iterative algorithms with caps (`DISTANCE_MAX_ITERS=20`, `TOI_MAX_ITERS=20`) — stresses loop/branch fidelity |
| 4 | `dynamictree.py`: `DynamicTree` insert/remove/balance/query/raycast; `broadphase.py` | Deterministic tree shapes given a fixed insert order; stresses index arithmetic and callbacks |
| 5 | `shapes.py` (`Circle`, `Polygon`, `Edge`, `Loop`, ray casts), `body.py`, `fixture.py`, `contact.py`, `contact_util.py` (`mix_friction`, `mix_restitution`, `Manifold`, `WorldManifold`) | Object graph and property setters; validates llang classes/`this`, copying, validation (`CHECK_VERTICES`, `ValueError`) |
| 6 | `world.py`: `World.step`, `World._solve`, `World.solve_toi`, `query_aabb`, `ray_cast`; `island.py`: `Island.solve` **with sleep disabled** | End-to-end numeric trajectory; the core differential target |
| 7 | `joints/`: `distance.py`, `revolute.py`, `friction.py`, `prismatic.py` first; then `weld`, `rope`, `wheel`, `pulley`, `gear` | Adds coupled constraints and Gauss–Seidel ordering effects |
| 8 (optional) | `controllers.py` (`BuoyancyController`), sleeping/warm-start/continuous-physics toggles | Lower priority: stateful, ODE-like, and depends on stage 6 being exact |

### 4.3 Differential verification plan

**Directory layout:** `engine-oracle/` (read-only reference), `engine-oracle/cases/*.json`
(scenarios), `engine-oracle/golden/*.json` (reference outputs),
`tests/engine_rewrite/*.llang` (the llang port + scenario driver),
`tools/engine_rewrite/compare.py` (tolerant comparator).

**Scenario JSON schema** (minimal, deliberately serialisable):

```json
{
  "name": "stacked_boxes_10",
  "gravity": [0, -10],
  "dt": 0.016666666666666666,
  "vel_iters": 8, "pos_iters": 3,
  "steps": 600,
  "world": {"do_sleep": false, "warm_starting": false,
            "continuous_physics": false, "auto_clear_forces": true},
  "bodies": [
    {"type": "dynamic", "position": [0, 0], "angle": 0,
     "fixtures": [{"shape": "polygon", "box": [1, 1], "density": 1,
                   "friction": 0.3, "restitution": 0.0}]}
  ],
  "joints": [{"type": "revolute", "body_a": 0, "body_b": 1, "anchor": [0, 5]}]
}
```

**Oracle runner** (uses only the pinned pure-Python package; real API names
verified against the clone):

```python
import sys, json, math
sys.path.insert(0, "engine-oracle")
try:
    import pypybox2d._common  # noqa: F401  -- must NOT exist in the oracle
    raise RuntimeError("C extension present; do not run setup.py build_ext")
except ImportError:
    pass                       # pure-Python fallback is the only allowed path
import pypybox2d as b

case = json.load(open(sys.argv[1]))
w = b.World(gravity=tuple(case["gravity"]), **case["world"])
for spec in case["bodies"]:
    mk = {"dynamic": w.create_dynamic_body, "static": w.create_static_body,
          "kinematic": w.create_kinematic_body}[spec["type"]]
    body = mk(position=tuple(spec["position"]), angle=spec["angle"])
    for f in spec["fixtures"]:
        if f["shape"] == "circle":
            body.create_circle_fixture(radius=f["radius"], **{k: f[k] for k in
                ("density", "friction", "restitution") if k in f})
        elif f["shape"] == "polygon":
            body.create_polygon_fixture(box=tuple(f["box"]), **{k: f[k] for k in
                ("density", "friction", "restitution") if k in f})
        else:
            body.create_edge_fixture(v1=tuple(f["v1"]), v2=tuple(f["v2"]))
for j in case["joints"]:
    ctor = {"revolute": b.RevoluteJoint, "distance": b.DistanceJoint,
            "friction": b.FrictionJoint, "prismatic": b.PrismaticJoint}[j["type"]]
    w.create_joint(ctor(w.bodies[j["body_a"]], w.bodies[j["body_b"]],
                        anchor=tuple(j["anchor"])))

trace = []
for n in range(case["steps"]):
    w.step(case["dt"], case["vel_iters"], case["pos_iters"])
    trace.append({
        "step": n,
        "bodies": [[repr(b_.position.x), repr(b_.position.y), repr(b_.angle),
                    repr(b_.linear_velocity.x), repr(b_.linear_velocity.y),
                    repr(b_.angular_velocity)] for b_ in w.bodies],
        "contacts": len(w.contact_manager.contacts),
        "manifolds": [[[repr(p.position.x), repr(p.position.y),
                        repr(p.normal.x), repr(p.normal.y), repr(p.impulse)]
                       for p in c.manifold.points]
                      for c in w.contact_manager.contacts],
    })
json.dump(trace, open(sys.argv[2], "w"), sort_keys=True, separators=(",", ":"))
```

Run and compare:

```bash
PYTHONHASHSEED=0 python tools/engine_rewrite/oracle.py \
    engine-oracle/cases/falling_ball.json golden/falling_ball.json
python run.py tests/engine_rewrite/falling_ball.llang --engine-golden golden/falling_ball.json
python tools/engine_rewrite/compare.py golden/falling_ball.json \
    out/falling_ball.llang.json --case falling_ball
```

**Serialisation rules:** floats use `repr(float)` (shortest round-trip, 17
significant digits where needed); dict keys sorted; lists keep insertion order
(order is itself part of the golden); `NaN`/`Inf` serialise as the exact tokens
`"NaN"`, `"Infinity"`, `"-Infinity"` and are compared by class, not by value.
Record a SHA-256 of each golden file so accidental edits are visible.

**Tolerance rules** (two-tier; never loosen a tolerance to make a failing port pass):

| Compared quantity | Rule |
|---|---|
| Stage 0–2 pure functions, same operation order | bit-exact `repr` match, or ≤ 2 ULP / `abs ≤ 1e-12` |
| GJK distance, `test_overlap`, SAT manifold point counts | count exact; coordinates `abs ≤ 1e-9`, normals `dot ≥ 0.999999999` |
| TOI (`time_of_impact`) | time `rel ≤ 1e-6`, `abs ≤ 1e-7`; separation `abs ≤ 1e-7` |
| `World.step` 1–60 steps, sleep off | position/angle/velocity `abs ≤ 1e-6` and `rel ≤ 1e-6` per component |
| `World.step` 600–3600 steps | position `abs ≤ 1e-4`, velocity `abs ≤ 1e-5`, energy drift ≤ 0.1% for elastic cases |
| Contact/joint identity and counts | exact match; only then compare numeric fields |
| Ordering-sensitive arrays | primary comparison is order-preserving; secondary sorted-multiset comparison is reported as a diagnostic only |
| Exceptions / degenerate inputs | same exception class, same NaN/Inf classification, same error message text |

**Independent analytic oracles** (so the test is not merely "copy A into B"):

- Free fall, verified above: `y_n = ½·g·(n·dt)² + ½·g·dt·(n·dt)`,
  `v_n = g·n·dt`. llang must reproduce `-5.08333…` at `n=60, dt=1/60, g=-10`.
- Small-angle pendulum on a `RevoluteJoint`: period `T = 2π√(L/g)` within 1%.
- Bounce on a static floor with restitution `e`: apex height ratio `e²` within
  `1e-3` (accounting for `VELOCITY_THRESHOLD = 1.0`).
- Sliding block with friction `μ`: stop time `v₀/(μ·g)` within 2%.
- Determinism: every case is run twice through the reference with
  `PYTHONHASHSEED=0`; byte-identical goldens are required. A second run with
  bodies inserted in reverse order is stored as a *separate* case, and the
  llang port must reproduce both orderings (this detects hidden global state).

**Golden protocol:** goldens are committed, never regenerated by the port.
Changing a tolerance or a golden requires a PR note explaining which numeric
semantics changed and why.

---

## 5. Edge cases the rewrite is expected to expose

1. **Floating-point drift.** Semi-implicit Euler accumulation over thousands of
   steps; `Sweep.forward`/`backward` interpolation; repeated `Mat22` and
   `Transform` multiplication; `inv_sqrt`, `EPSILON = sys.float_info.epsilon`,
   `MAX_FLOAT`. llang must preserve IEEE-754 doubles and Python's operation
   order; a single re-association (`a*b + c` vs `fma`) will show up as ULP drift
   in stages 1–2 and as centimetre-scale divergence in stage 6.
2. **Collision edge cases.** Coincident circle centres (zero separation),
   circle/polygon vertex-vs-edge ambiguity, parallel polygon edges (SAT axis
   ties), polygon Vertex–Vertex contact, degenerate polygons (`shapes.Polygon`
   has `CHECK_VERTICES = True` and rejects `<3` vertices), collinear vertices,
   duplicate vertices, deeply overlapped polygons where EPA must pick a minimum
   penetration axis, zero-length `Edge` segments and their ghost vertices
   (`v0`/`v3`), one-sided edges, clipping a segment of zero length in
   `clip_segment_to_line`, ray casts hitting exactly a vertex or lying exactly
   along an edge.
3. **Degenerate inputs.** Zero density / zero mass / infinite-mass static
   bodies, zero-radius circles, `NaN`/`Inf` coordinates (`is_valid_float`),
   identical overlapping bodies, huge coordinates approaching `MAX_FLOAT`
   (AABB fattening overflow), `next_power_of_two(0)`, `next_power_of_two` above
   `2**31`, and `AABB_EXTENSION = 0.1`/`AABB_MULTIPLIER = 2.0` boundary values.
4. **Ordering dependence.** `World.bodies` and `World.joints` list order;
   `contact_manager.contacts` array order; island solver Gauss–Seidel order;
   joint list order; `DynamicTree` node allocation, insertion and rebalance
   order; `World` creation order of fixtures; contact-cache warm starting
   (`warm_starting=True` makes results depend on previous steps);
   `PYTHONHASHSEED` effects on any dict iteration. The rewrite must reproduce
   both the sorted and reversed variants as distinct goldens.
5. **Boundary conditions.** TOI at `t = 0` and `t = t_max`; tunnelling at high
   velocity (`MAX_TRANSLATION = 2.0`, `MAX_SUB_STEPS = 8`); sleeping thresholds
   (`TIME_TO_SLEEP = 0.5`, `LINEAR_SLEEP_TOLERANCE = 0.01`); position-correction
   clamps (`MAX_LINEAR_CORRECTION = 0.2`, `MAX_ANGULAR_CORRECTION = 8°`);
   restitution suppressed below `VELOCITY_THRESHOLD = 1.0`; `MAX_TOI_CONTACTS =
   32`; the `LINEAR_SLOP = 0.005` penetration tolerance; stacked-box rests
   where contacts appear/disappear between steps.

---

## 6. Explicit omissions and why

- **Rendering / testbed / examples:** `testbed/` (pygame), `examples/`,
  `pypybox2d` display helpers. They require a display or SDL audio device and
  contribute no physics semantics. They are useful only as a catalogue of
  scenario names to re-create as headless JSON cases.
- **Input, audio, platform windowing, GUI event loops:** none of these exist in
  the core package; pyglet/pygame/OpenGL backends are out of scope by design.
- **The optional C extension** `pypybox2d/src/*.c` and any `_common` build:
  excluded deliberately. The oracle is the pure-Python path; comparing against
  the C path would add a second, platform-dependent source of numerical
  variance. Build tools (`distribute_setup.py`, `setup.py build_ext`) are never
  invoked.
- **Python 2 compatibility shims** in `common.py` (the custom `property`
  wrapper for Python < 2.6, `long` handling): not ported; llang targets Python
  3 semantics ([`python-semantics.md`](python-semantics.md)).
- **Controllers and mouse joint** (`controllers.py`, `joints/mouse.py`): staged
  last/omitted — they model external force callbacks and pointer input rather
  than the engine's own solver; including them would pull input semantics into
  the rewrite.
- **Full joint set:** gear/wheel/pulley are optional stage 8. They multiply
  constraint-coupling complexity without adding new llang library
  requirements beyond stages 6–7.

---

## 7. Feedback into llang's library design

This rewrite is chosen partly for what it *forces llang to add*. Concretely:

- **Numeric tower with exact Python double semantics:** `Vec2`, `Vec3`,
  `Mat22`, `Mat33`, `Transform`, `AABB`, `Sweep`, plus `dot`, `cross`,
  `scalar_cross`, `length`, `length_squared`, `normalize`, `inv_sqrt`, `clamp`,
  `clamp_vector`, `min_vector`, `max_vector`, `next_power_of_two`,
  `is_power_of_two`, `is_valid_float`. Operators (`+`, `-`, `*`, `/`, unary
  `-`, indexing, `x`/`y` attributes) must map to Python semantics exactly.
  Feeds [`math-library-design.md`](math-library-design.md).
- **Mutable fixed-layout records:** `__slots__`-like structs with attribute
  get/set, `copy.copy` semantics (used by `World.create_body`), validation in
  setters (`Polygon.vertices`, `Body.type`), and `repr` determinism. Feeds
  [`classes-semantics.md`](classes-semantics.md).
- **Stable ordered containers:** lists of records with insertion-order
  iteration, dicts keyed by pairs/ids for the contact register, fixed-size
  arrays for manifolds, and explicit copy-vs-reference rules (`World.bodies`
  vs `copy(body)`). Feeds [`stdlib-design.md`](stdlib-design.md).
- **In-place mutation and compound assignment:** `body.position += impulse`,
  `velocity *= damp`, and property setters that can raise `LockedError` while
  the world is locked. Feeds the Python-semantics and class-semantics docs.
- **Exceptions as control flow:** `PhysicsError`, `LockedError`,
  `EmptyFixtureError`, plus `ValueError` from geometry validation. The
  differential harness compares exception class and message text.
- **Iterators and callbacks:** `DynamicTree.query` and `World.query_aabb` take
  callbacks; `Island` traverses arrays; generators must preserve order and
  support early termination.
- **Bit-level integer ops and constants:** `next_power_of_two`, `is_power_of_two`,
  `sys.float_info.epsilon`, `MAX_FLOAT`, and the exact tuning constants in
  `settings.py` must be available as llang module-level constants.
- **17-significant-digit float serialisation** for golden files — a concrete
  requirement for the llang standard library's JSON/formatted-output support
  (cf. [`stdlib-design.md`](stdlib-design.md)).
- **Differential harness infrastructure:** the comparator built here
  (tolerance tables, golden hashing, `PYTHONHASHSEED=0`, analytic cross-checks)
  is reusable by every other planned rewrite
  ([`test-plan.md`](test-plan.md), [`METHOD.md`](../METHOD.md)).

---

## 8. Source index

- pypybox2d: https://github.com/pybox2d/pypybox2d —
  [README](https://raw.githubusercontent.com/pybox2d/pypybox2d/master/README),
  [LICENSE](https://raw.githubusercontent.com/pybox2d/pypybox2d/master/LICENSE),
  [settings.py](https://raw.githubusercontent.com/pybox2d/pypybox2d/master/pypybox2d/settings.py),
  [common.py](https://raw.githubusercontent.com/pybox2d/pypybox2d/master/pypybox2d/common.py)
- Upstream Box2D: https://github.com/erincatto/box2d, https://box2d.org/documentation/, zlib license https://opensource.org/license/zlib
- C++/SWIG sibling: https://github.com/pybox2d/pybox2d
- pymunk: https://github.com/viblo/pymunk
- pycolab: https://github.com/google-deepmind/pycolab —
  [engine.py](https://raw.githubusercontent.com/google-deepmind/pycolab/master/pycolab/engine.py),
  [LICENSE](https://raw.githubusercontent.com/google-deepmind/pycolab/master/LICENSE)
- cocos (Python): https://github.com/los-cocos/cocos —
  [LICENSE](https://raw.githubusercontent.com/los-cocos/cocos/master/LICENSE),
  [LICENSE.euclid](https://raw.githubusercontent.com/los-cocos/cocos/master/LICENSE.euclid)
- SimPy: https://gitlab.com/team-simpy/simpy
- Evennia: https://github.com/evennia/evennia
- Language mix / stars / sizes cross-checked with the GitHub repository search
  API: `https://api.github.com/search/repositories?q=<query>&sort=stars&order=desc`
