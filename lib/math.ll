# llang-native math module (no host interop used).

define function sqrt taking value
    require value is at least 0, "sqrt needs a non-negative number"
    if value equals 0 then
        give back 0
    end if
    set guess to value
    set i to 0
    repeat while i is less than 30
        set guess to (guess plus (value divided by guess)) divided by 2
        set i to i plus 1
    end repeat
    give back guess
end function

define function clamp taking value, low, high
    require low is at most high, "low must not exceed high"
    if value is less than low then
        give back low
    end if
    if value is greater than high then
        give back high
    end if
    give back value
end function

define function average taking items
    require (the length of items) is greater than 0, "average needs a non-empty list"
    give back (call sum with items = items) divided by (the length of items)
end function

set pi to 3.14159265358979
set e to 2.71828182845905
