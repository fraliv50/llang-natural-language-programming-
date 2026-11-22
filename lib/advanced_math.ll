# Advanced math for llang: exact integers, rounded primitives and statistics.
#
# Grounded in: https://docs.python.org/3/library/math.html
# Grounded in: https://docs.python.org/3/library/statistics.html
# Semantics are copied from CPython; all phrasing, problem kinds and result
# maps are llang-native.  The allow-listed foreign math module is used only for
# the correctly rounded libm primitives (sqrt/log/sin/cos/floor/ceil); every
# call is guarded so no host exception can leak.  Everything else is computed
# here in llang.

use the foreign math module as hostmath

set pi to 3.141592653589793
set e to 2.718281828459045
set tau to 6.283185307179586

# ---------------------------------------------------------------------------
# Internal validation helpers (also exported, harmless to callers).
# llang has no dynamic message interpolation, so `fail with` messages name the
# failing condition and the Python exception class; the call site is added by
# the interpreter automatically.
# ---------------------------------------------------------------------------

define function is_finite taking value
    if not (value is a number) then
        give back false
    end if
    set product to value times 0
    give back product equals product
end function

define function is_whole taking value
    if not (value is a number) then
        give back false
    end if
    if not (call is_finite with value = value) then
        give back false
    end if
    set rendered to call text of with value = value
    if call contains with collection = rendered, value = "." then
        give back false
    end if
    if call contains with collection = rendered, value = "e" then
        give back false
    end if
    give back true
end function

define function require_number taking value
    if not (value is a number) then
        fail with math_type, "math_type: expected a number, not a boolean or text (TypeError)"
    end if
    if not (call is_finite with value = value) then
        fail with math_domain, "math_domain: NaN and infinity are quarantined (ValueError)"
    end if
end function

define function require_whole taking value
    call require_number with value = value
    if not (call is_whole with value = value) then
        fail with math_type, "math_type: expected a whole number (TypeError)"
    end if
end function

define function require_numbers taking items
    if not (items is a list) then
        fail with math_type, "math_type: expected a list of numbers (TypeError)"
    end if
    repeat for each entry in items
        call require_number with value = entry
    end repeat
end function

define function require_wholes taking items
    if not (items is a list) then
        fail with math_type, "math_type: expected a list of whole numbers (TypeError)"
    end if
    repeat for each entry in items
        call require_whole with value = entry
    end repeat
end function

define function gcd_two taking left, right
    set a to left
    if a is less than 0 then
        set a to 0 minus a
    end if
    set b to right
    if b is less than 0 then
        set b to 0 minus b
    end if
    repeat while b is greater than 0
        set remainder to a modulo b
        set a to b
        set b to remainder
    end repeat
    give back a
end function

# ---------------------------------------------------------------------------
# Exponentials and logarithms
# ---------------------------------------------------------------------------

define function squareroot taking value
    also known as sqrt
    call require_number with value = value
    if value is less than 0 then
        fail with math_domain, "squareroot: value must be non-negative (math sqrt domain error, ValueError)"
    end if
    give back call sqrt from hostmath with value = value
end function

define function exponential taking power
    call require_number with value = power
    set limit to call log from hostmath with value = (call to number with text = "1.7976931348623157e308")
    if power is greater than limit then
        fail with math_overflow, "exponential: power is too large (math range error, OverflowError)"
    end if
    if power is less than (0 minus limit) then
        give back 0.0
    end if
    give back (item "e" of hostmath) to the power of power
end function

define function logarithm taking value
    call require_number with value = value
    if value is at most 0 then
        fail with math_domain, "logarithm: value must be positive (math log domain error, ValueError)"
    end if
    give back call log from hostmath with value = value
end function

define function logbase taking value, base
    call require_number with value = value
    call require_number with value = base
    if value is at most 0 then
        fail with math_domain, "logbase: value must be positive (math log domain error, ValueError)"
    end if
    if (base is at most 0) or (base equals 1) then
        fail with math_domain, "logbase: base must be positive and not one (math log domain error, ValueError)"
    end if
    give back (call log from hostmath with value = value) divided by (call log from hostmath with value = base)
end function

define function logtwo taking value
    call require_number with value = value
    if value is at most 0 then
        fail with math_domain, "logtwo: value must be positive (math log domain error, ValueError)"
    end if
    give back (call log from hostmath with value = value) divided by (call log from hostmath with value = 2)
end function

define function logten taking value
    call require_number with value = value
    if value is at most 0 then
        fail with math_domain, "logten: value must be positive (math log domain error, ValueError)"
    end if
    give back (call log from hostmath with value = value) divided by (call log from hostmath with value = 10)
end function

# ---------------------------------------------------------------------------
# Number theory (exact Python ints)
# ---------------------------------------------------------------------------

define function gcd taking values
    call require_wholes with items = values
    set result to 0
    repeat for each entry in values
        set a to entry
        if a is less than 0 then
            set a to 0 minus a
        end if
        repeat while a is greater than 0
            set remainder to result modulo a
            set result to a
            set a to remainder
        end repeat
    end repeat
    give back result
end function

define function lcm taking values
    call require_wholes with items = values
    set result to 1
    repeat for each entry in values
        set a to entry
        if a is less than 0 then
            set a to 0 minus a
        end if
        if a equals 0 then
            set result to 0
        otherwise
            if result does not equal 0 then
                set divisor to call gcd_two with left = result, right = a
                set result to (result floor divided by divisor) times a
            end if
        end if
    end repeat
    give back result
end function

define function factorial taking number
    call require_whole with value = number
    if number is less than 0 then
        fail with math_domain, "factorial: number must be non-negative (math factorial domain error, ValueError)"
    end if
    set result to 1
    set i to 2
    repeat while i is at most number
        set result to result times i
        set i to i plus 1
    end repeat
    give back result
end function

# ---------------------------------------------------------------------------
# Rounding and distance
# ---------------------------------------------------------------------------

define function floor taking value
    call require_number with value = value
    give back call floor from hostmath with value = value
end function

define function ceil taking value
    call require_number with value = value
    give back call ceil from hostmath with value = value
end function

define function trunc taking value
    call require_number with value = value
    if value is at least 0 then
        give back call floor from hostmath with value = value
    end if
    give back call ceil from hostmath with value = value
end function

define function hypot taking coordinates
    call require_numbers with items = coordinates
    set scale to 0
    repeat for each entry in coordinates
        set magnitude to entry
        if magnitude is less than 0 then
            set magnitude to 0 minus magnitude
        end if
        if magnitude is greater than scale then
            set scale to magnitude
        end if
    end repeat
    if scale equals 0 then
        give back 0.0
    end if
    set totalsq to 0
    repeat for each entry in coordinates
        set ratio to entry divided by scale
        set totalsq to totalsq plus (ratio times ratio)
    end repeat
    give back scale times (call sqrt from hostmath with value = totalsq)
end function

define function distance taking frompoint, topoint
    call require_numbers with items = frompoint
    call require_numbers with items = topoint
    if (the length of frompoint) does not equal (the length of topoint) then
        fail with math_length, "distance: points must have the same number of dimensions (ValueError)"
    end if
    set differences to an empty list
    set i to 0
    repeat while i is less than (the length of frompoint)
        add (item i of topoint) minus (item i of frompoint) to differences
        set i to i plus 1
    end repeat
    give back call hypot with coordinates = differences
end function

define function approxequal taking left, right, reltol, abstol
    call require_number with value = left
    call require_number with value = right
    call require_number with value = reltol
    call require_number with value = abstol
    if (reltol is less than 0) or (abstol is less than 0) then
        fail with math_domain, "approxequal: tolerances must be non-negative"
    end if
    if reltol is at least 1 then
        fail with math_domain, "approxequal: reltol must be less than one"
    end if
    if left equals right then
        give back true
    end if
    set difference to call absolute with value = (left minus right)
    set leftabs to call absolute with value = left
    set rightabs to call absolute with value = right
    set scale to leftabs
    if rightabs is greater than scale then
        set scale to rightabs
    end if
    if difference is at most (reltol times scale) then
        give back true
    end if
    give back difference is at most abstol
end function

define function nearlyequal taking left, right
    give back call approxequal with left = left, right = right, reltol = (1 divided by 1000000000), abstol = 0.0
end function

define function precisesum taking values
    call require_numbers with items = values
    set total to 0.0
    set compensation to 0.0
    repeat for each entry in values
        set t to total plus entry
        if (call absolute with value = total) is at least (call absolute with value = entry) then
            set compensation to compensation plus ((total minus t) plus entry)
        otherwise
            set compensation to compensation plus ((entry minus t) plus total)
        end if
        set total to t
    end repeat
    give back total plus compensation
end function

# ---------------------------------------------------------------------------
# Descriptive statistics (NaN/inf rejected before computing)
# ---------------------------------------------------------------------------

define function mean taking values
    call require_numbers with items = values
    set count to the length of values
    if count equals 0 then
        fail with math_empty, "mean: values must not be empty (StatisticsError)"
    end if
    set total to call sum with items = values
    if call is_whole with value = total then
        if total modulo count equals 0 then
            give back total floor divided by count
        end if
    end if
    give back total divided by count
end function

define function median taking values
    call require_numbers with items = values
    set count to the length of values
    if count equals 0 then
        fail with math_empty, "median: values must not be empty (StatisticsError)"
    end if
    set ordered to call sorted with items = values
    set middle to count floor divided by 2
    if count modulo 2 equals 1 then
        give back item middle of ordered
    end if
    set pair to (item (middle minus 1) of ordered) plus (item middle of ordered)
    give back pair divided by 2
end function

define function mode taking values
    if not (values is a list) then
        fail with math_type, "mode: values must be a list (TypeError)"
    end if
    set count to the length of values
    if count equals 0 then
        fail with math_empty, "mode: values must not be empty (StatisticsError)"
    end if
    repeat for each entry in values
        if entry is a number then
            if not (call is_finite with value = entry) then
                fail with math_domain, "mode: NaN and infinity are quarantined (ValueError)"
            end if
        end if
    end repeat
    set best to nothing
    set bestcount to 0
    repeat for each candidate in values
        set hits to 0
        repeat for each other in values
            if candidate equals other then
                set hits to hits plus 1
            end if
        end repeat
        if hits is greater than bestcount then
            set best to candidate
            set bestcount to hits
        end if
    end repeat
    give back best
end function

define function variance taking values
    call require_numbers with items = values
    set count to the length of values
    if count is less than 2 then
        fail with math_length, "variance: at least two values are required (StatisticsError)"
    end if
    set avg to call mean with values = values
    set total to 0.0
    repeat for each entry in values
        set delta to entry minus avg
        set total to total plus (delta times delta)
    end repeat
    give back total divided by (count minus 1)
end function

define function stdev taking values
    set spread to call variance with values = values
    give back call squareroot with value = spread
end function

define function pvariance taking values
    call require_numbers with items = values
    set count to the length of values
    if count equals 0 then
        fail with math_empty, "pvariance: values must not be empty (StatisticsError)"
    end if
    set avg to call mean with values = values
    set total to 0.0
    repeat for each entry in values
        set delta to entry minus avg
        set total to total plus (delta times delta)
    end repeat
    give back total divided by count
end function

define function pstdev taking values
    set spread to call pvariance with values = values
    give back call squareroot with value = spread
end function

# ---------------------------------------------------------------------------
# Trigonometry (angles are radians; libm through the guarded foreign module)
# ---------------------------------------------------------------------------

define function sine taking angle
    call require_number with value = angle
    give back call sin from hostmath with value = angle
end function

define function cosine taking angle
    call require_number with value = angle
    give back call cos from hostmath with value = angle
end function

# ---------------------------------------------------------------------------
# Quality-of-life: a descriptive map with a fixed key order.
# ---------------------------------------------------------------------------

define function summarize taking values
    call require_numbers with items = values
    set average to call mean with values = values
    set middle to call median with values = values
    if (the length of values) is less than 2 then
        set spread to 0.0
    otherwise
        set spread to call stdev with values = values
    end if
    give back a map with "value" mapped to average, "median" mapped to middle, "kind" mapped to "summary", "exact" mapped to false, "count" mapped to (the length of values), "stdev" mapped to spread
end function
