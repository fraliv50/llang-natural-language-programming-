# A headless 2D rigid-body physics module, re-expressed in llang.
#
# Grounded in pybox2d/pypybox2d at commit
#   ee7b81ff83a03d017534f5f7ac36e642ac27e33c
#   https://github.com/pybox2d/pypybox2d   (zlib license)
# The numerical core follows the pure-Python path of that engine (no optional
# C extension).  Bodies, transforms and worlds are self-describing maps.  The
# foreign math module is used only for correctly rounded sqrt/sin/cos and for
# the value of pi; all orchestration, validation and arithmetic is native
# llang.  There is no rendering, input or audio in this module.

use the foreign math module as hostmath

# ---------------------------------------------------------------------------
# Stage 0: tuning constants from pypybox2d/settings.py
# ---------------------------------------------------------------------------

set pi to item "pi" of hostmath
set epsilon to call to number with text = "2.220446049250313e-16"
set epsilon_sqr to epsilon to the power of 2
set max_float to call to number with text = "1.7976931348623157e308"
set linear_slop to 0.005
set angular_slop to (2.0 divided by 180.0) times pi
set polygon_radius to 2.0 times linear_slop
set aabb_extension to 0.1
set aabb_multiplier to 2.0
set max_manifold_points to 2
set max_sub_steps to 8
set max_toi_contacts to 32
set toi_max_iters to 20
set velocity_threshold to 1.0
set max_linear_correction to 0.2
set max_angular_correction to (8.0 divided by 180.0) times pi
set max_translation to 2.0
set max_translation_sqr to max_translation to the power of 2
set max_rotation to 0.5 times pi
set max_rotation_sqr to max_rotation to the power of 2
set baumgarte to 0.2
set toi_baumgarte to 0.75
set time_to_sleep to 0.5
set linear_sleep_tolerance to 0.01
set distance_max_iters to 20

# ---------------------------------------------------------------------------
# Validation helpers.  Every bad input fails loudly with a physics_error.
# ---------------------------------------------------------------------------

define function require_number taking value
    if not (value is a number) then
        fail with physics_error, "physics_error: expected a number, not a boolean, text or map"
    end if
end function

define function require_map taking value
    if not (value is a map) then
        fail with physics_error, "physics_error: expected a self-describing map"
    end if
end function

define function require_kind taking value, expected
    call require_map with value = value
    if not (call contains with collection = value, value = "kind") then
        fail with physics_error, "physics_error: map is missing its kind tag"
    end if
    if not ((item "kind" of value) equals expected) then
        fail with physics_error, "physics_error: wrong kind of physics map"
    end if
end function

define function require_vec taking value
    call require_kind with value = value, expected = "vec2"
end function

define function require_mat taking value
    call require_kind with value = value, expected = "mat22"
end function

define function require_transform taking value
    call require_kind with value = value, expected = "transform"
end function

define function require_aabb taking value
    call require_kind with value = value, expected = "aabb"
end function

define function truncate taking value
    call require_number with value = value
    if value is less than 0 then
        give back 0 minus ((0 minus value) floor divided by 1)
    end if
    give back value floor divided by 1
end function

# ---------------------------------------------------------------------------
# Stage 1a: Vec2 -- a 2d column vector stored as a self-describing map.
# ---------------------------------------------------------------------------

define function vec2 taking x, y
    call require_number with value = x
    call require_number with value = y
    give back a map with "kind" mapped to "vec2", "x" mapped to x, "y" mapped to y
end function

define function zero_vec
    give back call vec2 with x = 0.0, y = 0.0
end function

define function vec_copy taking v
    call require_vec with value = v
    give back call vec2 with x = (item "x" of v), y = (item "y" of v)
end function

define function vec_add taking a, b
    call require_vec with value = a
    call require_vec with value = b
    give back call vec2 with x = ((item "x" of a) plus (item "x" of b)), y = ((item "y" of a) plus (item "y" of b))
end function

define function vec_sub taking a, b
    call require_vec with value = a
    call require_vec with value = b
    give back call vec2 with x = ((item "x" of a) minus (item "x" of b)), y = ((item "y" of a) minus (item "y" of b))
end function

define function vec_scale taking v, factor
    call require_vec with value = v
    call require_number with value = factor
    give back call vec2 with x = ((item "x" of v) times factor), y = ((item "y" of v) times factor)
end function

define function vec_div taking v, factor
    call require_vec with value = v
    call require_number with value = factor
    if factor equals 0 then
        fail with physics_error, "physics_error: cannot divide a vector by zero"
    end if
    give back call vec2 with x = ((item "x" of v) divided by factor), y = ((item "y" of v) divided by factor)
end function

define function vec_neg taking v
    call require_vec with value = v
    give back call vec2 with x = (0 minus (item "x" of v)), y = (0 minus (item "y" of v))
end function

define function vec_dot taking a, b
    call require_vec with value = a
    call require_vec with value = b
    give back ((item "x" of a) times (item "x" of b)) plus ((item "y" of a) times (item "y" of b))
end function

define function vec_cross taking a, b
    call require_vec with value = a
    call require_vec with value = b
    give back ((item "x" of a) times (item "y" of b)) minus ((item "y" of a) times (item "x" of b))
end function

define function scalar_cross taking factor, v
    call require_number with value = factor
    call require_vec with value = v
    give back call vec2 with x = ((0 minus factor) times (item "y" of v)), y = (factor times (item "x" of v))
end function

define function vec_skew taking v
    call require_vec with value = v
    give back call vec2 with x = (0 minus (item "y" of v)), y = (item "x" of v)
end function

define function vec_len2 taking v
    call require_vec with value = v
    give back ((item "x" of v) to the power of 2) plus ((item "y" of v) to the power of 2)
end function

define function vec_len taking v
    give back call sqrt from hostmath with value = (call vec_len2 with v = v)
end function

define function vec_normalized taking v
    call require_vec with value = v
    set magnitude to call vec_len with v = v
    if magnitude is less than epsilon then
        give back call vec_copy with v = v
    end if
    set inverse to 1 divided by magnitude
    give back call vec2 with x = ((item "x" of v) times inverse), y = ((item "y" of v) times inverse)
end function

define function vec_valid taking v
    call require_vec with value = v
    give back (call is_valid_float with value = (item "x" of v)) and (call is_valid_float with value = (item "y" of v))
end function

define function vec_distance taking p1, p2
    give back call vec_len with v = (call vec_sub with a = p1, b = p2)
end function

define function vec_distance2 taking p1, p2
    set delta to call vec_sub with a = p1, b = p2
    give back call vec_dot with a = delta, b = delta
end function

define function vec_min taking a, b
    call require_vec with value = a
    call require_vec with value = b
    set x to item "x" of a
    if (item "x" of b) is less than x then
        set x to item "x" of b
    end if
    set y to item "y" of a
    if (item "y" of b) is less than y then
        set y to item "y" of b
    end if
    give back call vec2 with x = x, y = y
end function

define function vec_max taking a, b
    call require_vec with value = a
    call require_vec with value = b
    set x to item "x" of a
    if (item "x" of b) is greater than x then
        set x to item "x" of b
    end if
    set y to item "y" of a
    if (item "y" of b) is greater than y then
        set y to item "y" of b
    end if
    give back call vec2 with x = x, y = y
end function

define function vec_clamp taking v, low, high
    call require_vec with value = v
    call require_vec with value = low
    call require_vec with value = high
    give back call vec2 with x = (call clamp with value = (item "x" of v), low = (item "x" of low), high = (item "x" of high)), y = (call clamp with value = (item "y" of v), low = (item "y" of low), high = (item "y" of high))
end function

# ---------------------------------------------------------------------------
# Stage 1b: scalar helpers -- clamp, powers and finiteness.
# ---------------------------------------------------------------------------

define function clamp taking value, low, high
    call require_number with value = value
    call require_number with value = low
    call require_number with value = high
    set limited to value
    if high is less than limited then
        set limited to high
    end if
    set result to low
    if limited is greater than result then
        set result to limited
    end if
    give back result
end function

define function is_valid_float taking value
    if not (value is a number) then
        fail with physics_error, "physics_error: is_valid_float needs a number"
    end if
    give back value equals value
end function

define function inv_sqrt taking value
    call require_number with value = value
    if value is less than 0 then
        fail with physics_error, "physics_error: inv_sqrt needs a non-negative number"
    end if
    give back 1 divided by (call sqrt from hostmath with value = value)
end function

define function next_power_of_two taking value
    call require_number with value = value
    set whole to call truncate with value = value
    if whole is less than 0 then
        give back 0
    end if
    set power to 1
    repeat while power is at most whole
        set power to power times 2
    end repeat
    give back power
end function

define function is_power_of_two taking value
    call require_number with value = value
    set whole to call truncate with value = value
    if whole is at most 0 then
        give back false
    end if
    set power to 1
    repeat while power is less than whole
        set power to power times 2
    end repeat
    give back power equals whole
end function

# ---------------------------------------------------------------------------
# Stage 1c: Mat22 -- a 2x2 matrix in column-major order.
# ---------------------------------------------------------------------------

define function mat22 taking c1x, c1y, c2x, c2y
    call require_number with value = c1x
    call require_number with value = c1y
    call require_number with value = c2x
    call require_number with value = c2y
    give back a map with "kind" mapped to "mat22", "c1" mapped to (call vec2 with x = c1x, y = c1y), "c2" mapped to (call vec2 with x = c2x, y = c2y)
end function

define function identity_mat
    give back call mat22 with c1x = 1, c1y = 0, c2x = 0, c2y = 1
end function

define function mat_angle taking angle
    call require_number with value = angle
    set c to call cos from hostmath with value = angle
    set s to call sin from hostmath with value = angle
    give back call mat22 with c1x = c, c1y = s, c2x = (0 minus s), c2y = c
end function

define function mat_mul_vec taking m, v
    call require_mat with value = m
    call require_vec with value = v
    set c1 to item "c1" of m
    set c2 to item "c2" of m
    give back call vec2 with x = (((item "x" of c1) times (item "x" of v)) plus ((item "x" of c2) times (item "y" of v))), y = (((item "y" of c1) times (item "x" of v)) plus ((item "y" of c2) times (item "y" of v)))
end function

define function mat_mul_tv taking m, v
    call require_mat with value = m
    call require_vec with value = v
    give back call vec2 with x = (call vec_dot with a = (item "c1" of m), b = v), y = (call vec_dot with a = (item "c2" of m), b = v)
end function

define function mat_mul taking a, b
    call require_mat with value = a
    call require_mat with value = b
    set first to call mat_mul_vec with m = a, v = (item "c1" of b)
    set second to call mat_mul_vec with m = a, v = (item "c2" of b)
    give back call mat22 with c1x = (item "x" of first), c1y = (item "y" of first), c2x = (item "x" of second), c2y = (item "y" of second)
end function

define function mat_mul_t taking a, b
    call require_mat with value = a
    call require_mat with value = b
    set first to call mat_mul_tv with m = a, v = (item "c1" of b)
    set second to call mat_mul_tv with m = a, v = (item "c2" of b)
    give back call mat22 with c1x = (item "x" of first), c1y = (item "y" of first), c2x = (item "x" of second), c2y = (item "y" of second)
end function

define function mat_inverse taking m
    call require_mat with value = m
    set c1 to item "c1" of m
    set c2 to item "c2" of m
    set a to item "x" of c1
    set b to item "x" of c2
    set c to item "y" of c1
    set d to item "y" of c2
    set det to (a times d) minus (b times c)
    if det does not equal 0 then
        set det to 1 divided by det
    end if
    give back call mat22 with c1x = (det times d), c1y = (0 minus (det times c)), c2x = (0 minus (det times b)), c2y = (det times a)
end function

define function mat_solve taking m, v
    call require_mat with value = m
    call require_vec with value = v
    set c1 to item "c1" of m
    set c2 to item "c2" of m
    set a to item "x" of c1
    set b to item "x" of c2
    set c to item "y" of c1
    set d to item "y" of c2
    set det to (a times d) minus (b times c)
    if det does not equal 0 then
        set det to 1 divided by det
    end if
    set vx to item "x" of v
    set vy to item "y" of v
    give back call vec2 with x = (det times ((d times vx) minus (b times vy))), y = (det times ((a times vy) minus (c times vx)))
end function

# ---------------------------------------------------------------------------
# Stage 1d: Transform -- translation plus rotation.
# ---------------------------------------------------------------------------

define function transform taking px, py, angle
    call require_number with value = px
    call require_number with value = py
    call require_number with value = angle
    give back a map with "kind" mapped to "transform", "position" mapped to (call vec2 with x = px, y = py), "rotation" mapped to (call mat_angle with angle = angle), "angle" mapped to angle
end function

define function identity_transform
    give back call transform with px = 0, py = 0, angle = 0
end function

define function transform_point taking t, v
    call require_transform with value = t
    call require_vec with value = v
    give back call vec_add with a = (item "position" of t), b = (call mat_mul_vec with m = (item "rotation" of t), v = v)
end function

define function transform_inv_point taking t, v
    call require_transform with value = t
    call require_vec with value = v
    give back call mat_mul_tv with m = (item "rotation" of t), v = (call vec_sub with a = v, b = (item "position" of t))
end function

define function transform_mul_t taking a, b
    call require_transform with value = a
    call require_transform with value = b
    set position to call vec_sub with a = (item "position" of b), b = (item "position" of a)
    set rotation to call mat_mul_t with a = (item "rotation" of a), b = (item "rotation" of b)
    give back a map with "kind" mapped to "transform", "position" mapped to position, "rotation" mapped to rotation, "angle" mapped to 0
end function

# ---------------------------------------------------------------------------
# Stage 1e: AABB -- axis-aligned bounding boxes.
# ---------------------------------------------------------------------------

define function aabb taking lower, upper
    call require_vec with value = lower
    call require_vec with value = upper
    give back a map with "kind" mapped to "aabb", "lower" mapped to (call vec_copy with v = lower), "upper" mapped to (call vec_copy with v = upper)
end function

define function aabb_center taking box
    call require_aabb with value = box
    give back call vec_scale with v = (call vec_add with a = (item "lower" of box), b = (item "upper" of box)), factor = 0.5
end function

define function aabb_extents taking box
    call require_aabb with value = box
    give back call vec_scale with v = (call vec_sub with a = (item "upper" of box), b = (item "lower" of box)), factor = 0.5
end function

define function aabb_perimeter taking box
    call require_aabb with value = box
    set lower to item "lower" of box
    set upper to item "upper" of box
    give back 2.0 times (((item "x" of upper) minus (item "x" of lower)) plus ((item "y" of upper) minus (item "y" of lower)))
end function

define function aabb_combine taking first, second
    call require_aabb with value = first
    call require_aabb with value = second
    give back call aabb with lower = (call vec_min with a = (item "lower" of first), b = (item "lower" of second)), upper = (call vec_max with a = (item "upper" of first), b = (item "upper" of second))
end function

define function aabb_contains taking box, other
    call require_aabb with value = box
    call require_aabb with value = other
    set lo to item "lower" of box
    set hi to item "upper" of box
    set olo to item "lower" of other
    set ohi to item "upper" of other
    give back (((item "x" of lo) is at most (item "x" of olo)) and ((item "y" of lo) is at most (item "y" of olo))) and (((item "x" of ohi) is at most (item "x" of hi)) and ((item "y" of ohi) is at most (item "y" of hi)))
end function

define function aabb_overlaps taking first, second
    call require_aabb with value = first
    call require_aabb with value = second
    set d1 to call vec_sub with a = (item "lower" of second), b = (item "upper" of first)
    set d2 to call vec_sub with a = (item "lower" of first), b = (item "upper" of second)
    if ((item "x" of d1) is greater than 0) or ((item "y" of d1) is greater than 0) then
        give back false
    end if
    if ((item "x" of d2) is greater than 0) or ((item "y" of d2) is greater than 0) then
        give back false
    end if
    give back true
end function

define function aabb_valid taking box
    call require_aabb with value = box
    set delta to call vec_sub with a = (item "upper" of box), b = (item "lower" of box)
    give back (((item "x" of delta) is at least 0) and ((item "y" of delta) is at least 0)) and ((call vec_valid with v = (item "lower" of box)) and (call vec_valid with v = (item "upper" of box)))
end function

define function aabb_ray_cast taking box, p1, p2, max_fraction
    call require_aabb with value = box
    call require_vec with value = p1
    call require_vec with value = p2
    set lo to item "lower" of box
    set hi to item "upper" of box
    set tmin to 0 minus max_float
    set tmax to max_float
    set nx to 0.0
    set ny to 0.0

    set px to item "x" of p1
    set dx to (item "x" of p2) minus px
    set adx to call absolute with value = dx
    if adx is less than epsilon then
        if (px is less than (item "x" of lo)) or ((item "x" of hi) is less than px) then
            give back a map with "hit" mapped to false, "normal" mapped to (call zero_vec), "fraction" mapped to 0.0
        end if
    otherwise
        set inverse to 1 divided by dx
        set t1 to ((item "x" of lo) minus px) times inverse
        set t2 to ((item "x" of hi) minus px) times inverse
        set sign to 0 minus 1.0
        if t1 is greater than t2 then
            set swap to t1
            set t1 to t2
            set t2 to swap
            set sign to 1.0
        end if
        if t1 is greater than tmin then
            set nx to sign
            set ny to 0.0
            set tmin to t1
        end if
        if t2 is less than tmax then
            set tmax to t2
        end if
        if tmin is greater than tmax then
            give back a map with "hit" mapped to false, "normal" mapped to (call zero_vec), "fraction" mapped to 0.0
        end if
    end if

    set py to item "y" of p1
    set dy to (item "y" of p2) minus py
    set ady to call absolute with value = dy
    if ady is less than epsilon then
        if (py is less than (item "y" of lo)) or ((item "y" of hi) is less than py) then
            give back a map with "hit" mapped to false, "normal" mapped to (call zero_vec), "fraction" mapped to 0.0
        end if
    otherwise
        set inverse to 1 divided by dy
        set t1 to ((item "y" of lo) minus py) times inverse
        set t2 to ((item "y" of hi) minus py) times inverse
        set sign to 0 minus 1.0
        if t1 is greater than t2 then
            set swap to t1
            set t1 to t2
            set t2 to swap
            set sign to 1.0
        end if
        if t1 is greater than tmin then
            set nx to 0.0
            set ny to sign
            set tmin to t1
        end if
        if t2 is less than tmax then
            set tmax to t2
        end if
        if tmin is greater than tmax then
            give back a map with "hit" mapped to false, "normal" mapped to (call zero_vec), "fraction" mapped to 0.0
        end if
    end if

    if (tmin is less than 0.0) or (max_fraction is less than tmin) then
        give back a map with "hit" mapped to false, "normal" mapped to (call zero_vec), "fraction" mapped to 0.0
    end if
    give back a map with "hit" mapped to true, "normal" mapped to (call vec2 with x = nx, y = ny), "fraction" mapped to tmin
end function

# ---------------------------------------------------------------------------
# Stage 2: geometry and distance functions.
# ---------------------------------------------------------------------------

define function circle_shape taking px, py, radius
    call require_number with value = radius
    if radius is less than 0 then
        fail with physics_error, "physics_error: a circle radius cannot be negative"
    end if
    give back a map with "kind" mapped to "circle", "position" mapped to (call vec2 with x = px, y = py), "radius" mapped to radius
end function

define function circle_aabb taking circle
    call require_kind with value = circle, expected = "circle"
    set p to item "position" of circle
    set r to item "radius" of circle
    give back call aabb with lower = (call vec2 with x = ((item "x" of p) minus r), y = ((item "y" of p) minus r)), upper = (call vec2 with x = ((item "x" of p) plus r), y = ((item "y" of p) plus r))
end function

define function circle_proxy taking circle
    call require_kind with value = circle, expected = "circle"
    give back a map with "kind" mapped to "proxy", "vertices" mapped to (a list of (call vec_copy with v = (item "position" of circle))), "radius" mapped to (item "radius" of circle)
end function

define function empty_manifold
    set p0 to a map with "local_point" mapped to (call zero_vec), "id" mapped to (a list of 0, 0, 0, 0)
    set p1 to a map with "local_point" mapped to (call zero_vec), "id" mapped to (a list of 0, 0, 0, 0)
    give back a map with "kind" mapped to "manifold", "type" mapped to 0, "point_count" mapped to 0, "local_normal" mapped to (call zero_vec), "local_point" mapped to (call zero_vec), "points" mapped to (a list of p0, p1)
end function

define function collide_circles taking circle_a, xf_a, circle_b, xf_b
    call require_kind with value = circle_a, expected = "circle"
    call require_kind with value = circle_b, expected = "circle"
    call require_transform with value = xf_a
    call require_transform with value = xf_b
    set pa to call transform_point with t = xf_a, v = (item "position" of circle_a)
    set pb to call transform_point with t = xf_b, v = (item "position" of circle_b)
    set delta to call vec_sub with a = pb, b = pa
    set dist_sqr to call vec_len2 with v = delta
    set radius to (item "radius" of circle_a) plus (item "radius" of circle_b)
    set manifold to call empty_manifold
    if dist_sqr is greater than (radius to the power of 2) then
        give back manifold
    end if
    set item "type" of manifold to 0
    set item "point_count" of manifold to 1
    set item "local_point" of manifold to (call vec_copy with v = (item "position" of circle_a))
    set points to item "points" of manifold
    set first_point to item 0 of points
    set item "local_point" of first_point to (call vec_copy with v = (item "position" of circle_b))
    set item 0 of points to first_point
    set item "points" of manifold to points
    give back manifold
end function

define function shape_distance taking proxy_a, proxy_b, transform_a, transform_b, use_radii
    call require_kind with value = proxy_a, expected = "proxy"
    call require_kind with value = proxy_b, expected = "proxy"
    set vertices_a to item "vertices" of proxy_a
    set vertices_b to item "vertices" of proxy_b
    if (the length of vertices_a) does not equal 1 then
        fail with physics_error, "physics_error: shape_distance supports single-vertex (circle) proxies"
    end if
    if (the length of vertices_b) does not equal 1 then
        fail with physics_error, "physics_error: shape_distance supports single-vertex (circle) proxies"
    end if
    set pa to call transform_point with t = transform_a, v = (item 0 of vertices_a)
    set pb to call transform_point with t = transform_b, v = (item 0 of vertices_b)
    set delta to call vec_sub with a = pb, b = pa
    set distance to call vec_len with v = delta
    set point_a to pa
    set point_b to pb
    set iterations to 1
    if distance equals 0 then
        set iterations to 0
    end if
    if use_radii then
        set radii to (item "radius" of proxy_a) plus (item "radius" of proxy_b)
        if (distance is greater than radii) and (distance is greater than epsilon) then
            set distance to distance minus radii
            set normal to call vec_normalized with v = delta
            set point_a to call vec_add with a = point_a, b = (call vec_scale with v = normal, factor = (item "radius" of proxy_a))
            set point_b to call vec_sub with a = point_b, b = (call vec_scale with v = normal, factor = (item "radius" of proxy_b))
        otherwise
            set middle to call vec_scale with v = (call vec_add with a = point_a, b = point_b), factor = 0.5
            set point_a to middle
            set point_b to call vec_copy with v = middle
            set distance to 0.0
        end if
    end if
    give back a map with "point_a" mapped to point_a, "point_b" mapped to point_b, "distance" mapped to distance, "iterations" mapped to iterations
end function

define function test_overlap taking proxy_a, proxy_b, transform_a, transform_b
    set result to call shape_distance with proxy_a = proxy_a, proxy_b = proxy_b, transform_a = transform_a, transform_b = transform_b, use_radii = true
    give back (item "distance" of result) is less than (10 times epsilon)
end function

define function point_segment_distance taking p, a, b
    call require_vec with value = p
    call require_vec with value = a
    call require_vec with value = b
    set edge to call vec_sub with a = b, b = a
    set length_sq to call vec_len2 with v = edge
    if length_sq equals 0 then
        give back call vec_distance with p1 = p, p2 = a
    end if
    set fraction to (call vec_dot with a = (call vec_sub with a = p, b = a), b = edge) divided by length_sq
    set fraction to call clamp with value = fraction, low = 0, high = 1
    set closest to call vec_add with a = a, b = (call vec_scale with v = edge, factor = fraction)
    give back call vec_distance with p1 = p, p2 = closest
end function

define function polygon_aabb taking vertices, radius
    call require_number with value = radius
    if (the length of vertices) is less than 1 then
        fail with physics_error, "physics_error: polygon_aabb needs at least one vertex"
    end if
    set low to item 0 of vertices
    set high to item 0 of vertices
    set index to 1
    repeat while index is less than (the length of vertices)
        set low to call vec_min with a = low, b = (item index of vertices)
        set high to call vec_max with a = high, b = (item index of vertices)
        set index to index plus 1
    end repeat
    give back call aabb with lower = (call vec2 with x = ((item "x" of low) minus radius), y = ((item "y" of low) minus radius)), upper = (call vec2 with x = ((item "x" of high) plus radius), y = ((item "y" of high) plus radius))
end function

# ---------------------------------------------------------------------------
# Stage 3: a headless World with semi-implicit Euler integration.
# ---------------------------------------------------------------------------

define function new_world taking gravity, dt, vel_iters, pos_iters
    call require_vec with value = gravity
    call require_number with value = dt
    if dt is at most 0 then
        fail with physics_error, "physics_error: the time step must be positive"
    end if
    give back a map with "kind" mapped to "world", "gravity" mapped to (call vec_copy with v = gravity), "dt" mapped to dt, "vel_iters" mapped to vel_iters, "pos_iters" mapped to pos_iters, "bodies" mapped to (an empty list), "step" mapped to 0, "locked" mapped to false
end function

define function new_dynamic_body taking x, y, radius, density
    call require_number with value = radius
    call require_number with value = density
    if radius is at most 0 then
        fail with physics_error, "physics_error: a dynamic circle needs a positive radius"
    end if
    if density is at most 0 then
        fail with physics_error, "physics_error: a dynamic body needs a positive density"
    end if
    set mass to density times (pi times (radius to the power of 2))
    set inertia to 0.5 times (mass times (radius to the power of 2))
    give back a map with "kind" mapped to "body", "type" mapped to "dynamic", "position" mapped to (call vec2 with x = x, y = y), "linear_velocity" mapped to (call zero_vec), "angle" mapped to 0.0, "angular_velocity" mapped to 0.0, "mass" mapped to mass, "inverse_mass" mapped to (1 divided by mass), "inertia" mapped to inertia, "inverse_inertia" mapped to (1 divided by inertia), "linear_damping" mapped to 0.0, "angular_damping" mapped to 0.0, "gravity_scale" mapped to 1.0, "force" mapped to (call zero_vec), "torque" mapped to 0.0, "fixtures" mapped to (an empty list), "awake" mapped to true, "radius" mapped to radius
end function

define function add_body taking world, body
    call require_kind with value = world, expected = "world"
    call require_kind with value = body, expected = "body"
    if item "locked" of world then
        fail with physics_error, "physics_error: the world is locked while stepping"
    end if
    set bodies to item "bodies" of world
    add body to bodies
    set item "bodies" of world to bodies
    give back body
end function

define function add_circle_fixture taking body, radius, density
    call require_kind with value = body, expected = "body"
    set fixtures to item "fixtures" of body
    add (call circle_shape with px = 0, py = 0, radius = radius) to fixtures
    set item "fixtures" of body to fixtures
    set mass to density times (pi times (radius to the power of 2))
    set inertia to 0.5 times (mass times (radius to the power of 2))
    set item "mass" of body to mass
    set item "inverse_mass" of body to (1 divided by mass)
    set item "inertia" of body to inertia
    set item "inverse_inertia" of body to (1 divided by inertia)
    set item "radius" of body to radius
    give back body
end function

define function world_step taking world
    call require_kind with value = world, expected = "world"
    if item "locked" of world then
        fail with physics_error, "physics_error: the world is already locked"
    end if
    set item "locked" of world to true
    set dt to item "dt" of world
    set gravity to item "gravity" of world
    set gx to item "x" of gravity
    set gy to item "y" of gravity
    set bodies to item "bodies" of world
    repeat for each body in bodies
        if (item "type" of body) equals "dynamic" then
            set velocity to item "linear_velocity" of body
            set force to item "force" of body
            set inverse_mass to item "inverse_mass" of body
            set scale to item "gravity_scale" of body
            set ax to ((scale times gx) plus (inverse_mass times (item "x" of force)))
            set ay to ((scale times gy) plus (inverse_mass times (item "y" of force)))
            set vx to (item "x" of velocity) plus (dt times ax)
            set vy to (item "y" of velocity) plus (dt times ay)
            set damp to 1 minus (dt times (item "linear_damping" of body))
            set damp to call clamp with value = damp, low = 0, high = 1
            set vx to vx times damp
            set vy to vy times damp
            set angular_damp to 1 minus (dt times (item "angular_damping" of body))
            set angular_damp to call clamp with value = angular_damp, low = 0, high = 1
            set omega to (item "angular_velocity" of body) times angular_damp
            set omega to omega plus ((dt times (item "inverse_inertia" of body)) times (item "torque" of body))

            set translation to call vec2 with x = (dt times vx), y = (dt times vy)
            set speed_sq to call vec_len2 with v = translation
            if speed_sq is greater than max_translation_sqr then
                set ratio to max_translation divided by (call vec_len with v = translation)
                set vx to vx times ratio
                set vy to vy times ratio
            end if
            if (dt times omega) to the power of 2 is greater than max_rotation_sqr then
                set ratio to max_rotation divided by (call absolute with value = (dt times omega))
                set omega to omega times ratio
            end if

            set position to item "position" of body
            set px to (item "x" of position) plus (dt times vx)
            set py to (item "y" of position) plus (dt times vy)
            set item "position" of body to (call vec2 with x = px, y = py)
            set item "linear_velocity" of body to (call vec2 with x = vx, y = vy)
            set item "angle" of body to ((item "angle" of body) plus (dt times omega))
            set item "angular_velocity" of body to omega
        end if
    end repeat
    set item "step" of world to (item "step" of world) plus 1
    set item "locked" of world to false
    give back world
end function

define function world_advance taking world, steps
    call require_kind with value = world, expected = "world"
    set count to call truncate with value = steps
    if count is less than 0 then
        fail with physics_error, "physics_error: step count cannot be negative"
    end if
    set index to 0
    repeat while index is less than count
        call world_step with world = world
        set index to index plus 1
    end repeat
    give back world
end function

define function body_position taking body
    call require_kind with value = body, expected = "body"
    give back call vec_copy with v = (item "position" of body)
end function

define function body_linear_velocity taking body
    call require_kind with value = body, expected = "body"
    give back call vec_copy with v = (item "linear_velocity" of body)
end function

define function body_angle taking body
    call require_kind with value = body, expected = "body"
    give back item "angle" of body
end function

define function world_gravity taking world
    call require_kind with value = world, expected = "world"
    give back call vec_copy with v = (item "gravity" of world)
end function
