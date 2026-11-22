# A headless 60-step fall under gravity, using the native box2d module.
# Reference oracle: g = (0, -10), dt = 1/60, 60 semi-implicit Euler steps.
# Expected: position y = -5.083333333333334, velocity y = -9.999999999999998.

use the box2d module

set gravity to call vec2 from box2d with x = 0, y = (0 minus 10)
set world to call new_world from box2d with gravity = gravity, dt = (1 divided by 60), vel_iters = 8, pos_iters = 3
set ball to call new_dynamic_body from box2d with x = 0, y = 0, radius = 1, density = 1
call add_body from box2d with world = world, body = ball

repeat for each index in (a list of 1, 2, 3)
    call world_advance from box2d with world = world, steps = 20
end repeat

set final_position to call body_position from box2d with body = ball
set final_velocity to call body_linear_velocity from box2d with body = ball

show "steps: " plus (call text of with value = (item "step" of world))
show "position y: " plus (call text of with value = (item "y" of final_position))
show "velocity y: " plus (call text of with value = (item "y" of final_velocity))
