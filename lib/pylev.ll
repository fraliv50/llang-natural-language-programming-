# Levenshtein-family edit distances, reimplemented in llang.
#
# Grounded in pylev 1.3.0 (New BSD / 3-clause BSD license, Daniel Lindsley):
#   https://github.com/toastdriven/pylev/blob/v1.3.0/pylev.py
# The default `levenshtein` in that release is `wfi_levenshtein`, an iterative
# Wagner-Fischer DP with two rows. `dameraulevenshtein` mirrors pylev's
# `damerau_levenshtein` (the restricted / optimal-string-alignment variant,
# with a third row for adjacent transpositions). `osadistance` computes the
# same optimal-string-alignment distance with the textbook 2D recurrence
# rolled into three rows; pylev's damerau_levenshtein is used as its oracle.
#
# No regex, no slicing syntax, no host calls, no Python bridge: only indexed
# character access (`item i of text`), lists and integer arithmetic.

# Validate a public argument and raise the same kind of loud, catchable
# problem everywhere in this module.
define function require_text taking value
    if not (value is text) then
        fail with edit_error, "pylev expects text arguments"
    end if
end function

# [0, 1, ..., width] — the first row of a Wagner-Fischer DP table.
define function range_row taking width
    require width is at least 0, "pylev: a row width cannot be negative"
    set row to an empty list
    set k to 0
    repeat while k is at most width
        add k to row
        set k to k plus 1
    end repeat
    give back row
end function

# pylev's wfi_levenshtein: two-row iterative Wagner-Fischer.
define function levenshtein taking left, right
also known as lev
    call require_text with value = left
    call require_text with value = right

    if left equals right then
        give back 0
    end if

    set len1 to the length of left
    set len2 to the length of right
    if len1 equals 0 then
        give back len2
    end if
    if len2 equals 0 then
        give back len1
    end if

    # pylev keeps the shorter string in `a` so the inner row has length len2.
    set a to left
    set b to right
    if len1 is greater than len2 then
        set a to right
        set b to left
        set tmp to len1
        set len1 to len2
        set len2 to tmp
    end if

    set d0 to call range_row with width = len2
    set d1 to call range_row with width = len2
    require (the length of d0) equals (len2 plus 1), "pylev: bad DP row width"

    set i to 0
    repeat while i is less than len1
        set item 0 of d1 to i plus 1
        set j to 0
        repeat while j is less than len2
            set cost to item j of d0
            if (item i of a) does not equal (item j of b) then
                set cost to cost plus 1
                set xcost to (item j of d1) plus 1
                if xcost is less than cost then
                    set cost to xcost
                end if
                set ycost to (item (j plus 1) of d0) plus 1
                if ycost is less than cost then
                    set cost to ycost
                end if
            end if
            set item (j plus 1) of d1 to cost
            set j to j plus 1
        end repeat
        set previous to d0
        set d0 to d1
        set d1 to previous
        set i to i plus 1
    end repeat
    give back item len2 of d0
end function

# pylev's damerau_levenshtein: two rolling rows plus dprev for transpositions.
define function dameraulevenshtein taking left, right
also known as damerau_levenshtein
    call require_text with value = left
    call require_text with value = right

    if left equals right then
        give back 0
    end if

    set len1 to the length of left
    set len2 to the length of right
    if len1 equals 0 then
        give back len2
    end if
    if len2 equals 0 then
        give back len1
    end if

    set a to left
    set b to right
    if len1 is greater than len2 then
        set a to right
        set b to left
        set tmp to len1
        set len1 to len2
        set len2 to tmp
    end if

    set d0 to call range_row with width = len2
    set d1 to call range_row with width = len2
    set dprev to call range_row with width = len2
    require (the length of dprev) equals (len2 plus 1), "pylev: bad DP row width"

    set i to 0
    repeat while i is less than len1
        set item 0 of d1 to i plus 1
        set j to 0
        repeat while j is less than len2
            set cost to item j of d0
            if (item i of a) does not equal (item j of b) then
                set cost to cost plus 1
                set xcost to (item j of d1) plus 1
                if xcost is less than cost then
                    set cost to xcost
                end if
                set ycost to (item (j plus 1) of d0) plus 1
                if ycost is less than cost then
                    set cost to ycost
                end if
                if ((i is greater than 0) and (j is greater than 0)) then
                    if ((item i of a) equals (item (j minus 1) of b)) and ((item (i minus 1) of a) equals (item j of b)) then
                        set transpcost to (item (j minus 1) of dprev) plus 1
                        if transpcost is less than cost then
                            set cost to transpcost
                        end if
                    end if
                end if
            end if
            set item (j plus 1) of d1 to cost
            set j to j plus 1
        end repeat
        set oldest to dprev
        set dprev to d0
        set d0 to d1
        set d1 to oldest
        set i to i plus 1
    end repeat
    give back item len2 of d0
end function

# Optimal string alignment distance: Levenshtein plus adjacent swaps, where a
# substring may be edited only once. The classic d[i][j] recurrence is rolled
# into three rows (i-2, i-1, i). On pylev's corpus this agrees exactly with
# pylev's damerau_levenshtein.
define function osadistance taking left, right
also known as osa_distance
    call require_text with value = left
    call require_text with value = right

    set m to the length of left
    set n to the length of right

    set prev2 to call range_row with width = n
    set prev to call range_row with width = n
    set cur to call range_row with width = n
    require (the length of cur) equals (n plus 1), "pylev: bad OSA row width"

    set i to 1
    repeat while i is at most m
        set item 0 of cur to i
        set j to 1
        repeat while j is at most n
            set cost to 0
            if (item (i minus 1) of left) does not equal (item (j minus 1) of right) then
                set cost to 1
            end if
            set best to (item j of prev) plus 1
            set candidate to (item (j minus 1) of cur) plus 1
            if candidate is less than best then
                set best to candidate
            end if
            set candidate to (item (j minus 1) of prev) plus cost
            if candidate is less than best then
                set best to candidate
            end if
            if ((i is greater than 1) and (j is greater than 1)) then
                if ((item (i minus 1) of left) equals (item (j minus 2) of right)) and ((item (i minus 2) of left) equals (item (j minus 1) of right)) then
                    set candidate to (item (j minus 2) of prev2) plus cost
                    if candidate is less than best then
                        set best to candidate
                    end if
                end if
            end if
            set item j of cur to best
            set j to j plus 1
        end repeat
        set oldest to prev2
        set prev2 to prev
        set prev to cur
        set cur to oldest
        set i to i plus 1
    end repeat
    give back item n of prev
end function
