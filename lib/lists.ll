# llang-native list module.

define function unique taking items
    set result to an empty list
    repeat for each entry in items
        if not (call contains with collection = result, value = entry) then
            add entry to result
        end if
    end repeat
    give back result
end function

define function flatten taking groups
    set result to an empty list
    repeat for each group in groups
        repeat for each entry in group
            add entry to result
        end repeat
    end repeat
    give back result
end function

define function rotate taking items, places
    set n to the length of items
    if n is greater than 0 then
        set shift to places modulo n
        set result to an empty list
        set i to shift
        repeat while i is less than n
            add item i of items to result
            set i to i plus 1
        end repeat
        set i to 0
        repeat while i is less than shift
            add item i of items to result
            set i to i plus 1
        end repeat
        give back result
    end if
    give back items
end function
