# Provenance: pypybox2d rewrite in llang

## Source

- **Repository:** https://github.com/pybox2d/pypybox2d
- **Pinned commit:** `ee7b81ff83a03d017534f5f7ac36e642ac27e33c`
  (the `master` tip at research time, dated 2019-05-11, "Merge pull request #3
  from PeterJCLaw/python3"). Verified with `git rev-parse HEAD` in the local
  clone at `tools/rewrites/pypybox2d/source`.
- **License:** zlib. The clone's `LICENSE` begins "C++ version Copyright (c)
  2006-2011 Erin Catto … Python port by Ken Lauer"; `setup.py` declares
  `__license__='zlib'`. Only attribution and marking of altered versions are
  required. The llang port is an altered version: it is written natively in
  llang and is **not** a copy of the Python source.
- **Oracle path:** the pure-Python math path only. The optional C extension in
  `pypybox2d/src/*.c` is excluded and `python setup.py build_ext` is never run.
  `pypybox2d.common.Vec2 is pypybox2d.common.PyVec2` is asserted in both
  verification entry points.

## What was ported

The staged plan in `docs/research/engine-rewrite-target.md` §4.2 was followed:

- **Stage 0 — constants.** `settings.py` tuning constants are module values in
  `lib/box2d.ll` (`pi`, `epsilon`, `max_float`, `linear_slop`, `polygon_radius`,
  `baumgarte`, `max_translation`, sleep and iteration limits, AABB fattening
  values, and so on).
- **Stage 1 — math primitives.** `Vec2` (`vec2`, `zero_vec`, `vec_add`,
  `vec_sub`, `vec_scale`, `vec_div`, `vec_neg`, `vec_dot`, `vec_cross`,
  `scalar_cross`, `vec_skew`, `vec_len`, `vec_len2`, `vec_normalized`,
  `vec_distance`, `vec_distance2`, `vec_min`, `vec_max`, `vec_clamp`,
  `vec_valid`, `vec_copy`), `Mat22` (`mat22`, `identity_mat`, `mat_angle`,
  `mat_mul_vec`, `mat_mul_tv`, `mat_mul`, `mat_mul_t`, `mat_inverse`,
  `mat_solve`), `Transform` (`transform`, `identity_transform`,
  `transform_point`, `transform_inv_point`, `transform_mul_t`), `AABB`
  (`aabb`, `aabb_center`, `aabb_extents`, `aabb_perimeter`, `aabb_combine`,
  `aabb_contains`, `aabb_overlaps`, `aabb_valid`, `aabb_ray_cast`), and the
  scalar helpers `clamp`, `clamp_vector` (as `vec_clamp`), `min_vector` /
  `max_vector` (as `vec_min` / `vec_max`), `is_valid_float`, `inv_sqrt`,
  `next_power_of_two` and `is_power_of_two`.
- **Stage 2 — geometry and distance.** Circle shapes and proxies,
  `collide_circles` producing a self-describing manifold map, `shape_distance`
  and `test_overlap` for single-vertex (circle) distance proxies,
  `point_segment_distance`, `circle_aabb` and `polygon_aabb`.
- **Stage 3 — headless world.** `new_world`, `new_dynamic_body`, `add_body`,
  `add_circle_fixture`, `world_step`, `world_advance`, `body_position`,
  `body_linear_velocity`, `body_angle`, `world_gravity`. Integration is
  semi-implicit Euler with pypybox2d's operation order (velocity integration,
  linear/angular damping clamps, velocity clamping, then position/angle
  integration). The documented oracle is reproduced: with `gravity=(0,-10)`,
  `dt=1/60`, sleeping and warm starting off, 60 steps give
  `position.y = -5.083333333333334` and
  `linear_velocity.y = -9.999999999999998` (the research doc's `-10` rounded).
- **Stage 6 (narrow slice) — collision case.** Circle–circle collision
  detection is ported as a pure geometry function and verified against
  `pypybox2d.collision.collide_circles`. It is not wired into `World.step`:
  contact manifolds, the contact solver, warm starting and TOI are omitted.

## Deliberate omissions

- The full `collision.py` SAT/EPA port (`collide_polygons`,
  `collide_polygon_circle`, `collide_edge_circle`, `collide_edge_polygon`,
  `EPCollider`), and the full GJK `Simplex` in `distance.py`; `shape_distance`
  intentionally rejects multi-vertex proxies with a loud `physics_error`.
- `dynamictree.py`, `broadphase.py`, `contact_manager.py`, `contact.py`,
  `contact_util.py`, `island.py` (island/contact solving), `fixture.py`,
  `controllers.py`, and all 12 joint modules.
- Sleeping, warm starting, continuous physics/TOI, joint constraints,
  `World.query_aabb` / `ray_cast`, and body copying/property setters.
- Rendering, input, audio, the pygame testbed and all built C extensions.
- Python 2 compatibility shims. llang targets Python 3 semantics.

## Verification commands

From the repository root:

```bash
python run.py --lint lib/box2d.ll
python run.py examples/box2d.ll
python tools/compare_box2d.py
python tests/test_box2d.py -v
```

Expected: the linter reports no errors; the example prints `steps: 60`,
`position y: -5.083333333333334`, `velocity y: -9.999999999999998`; the harness
prints `compared 1113 cases, 0 mismatches`; all 10 unit/differential tests pass.

Tolerances follow `docs/research/engine-rewrite-target.md` §4.3: Stage 1–2
pure functions use near-bit-exact comparison (`rel_tol=1e-12`, `abs_tol=1e-12`)
and `World.step` trajectories use `rel_tol=1e-6`, `abs_tol=1e-6` per component.
The 60-step fall is additionally checked against the independent closed-form
semi-implicit-Euler oracle `y = ½·g·(n·dt)² + ½·g·dt·(n·dt)`, `v = g·n·dt`.
