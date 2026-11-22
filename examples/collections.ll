# Collections and iteration.

set numbers to a list of 3, 1, 2
show numbers
show the length of numbers
show item 0 of numbers

add 9 to numbers
set item 0 of numbers to 7
show numbers

repeat for each value in numbers
    show value
end repeat

repeat for each value in numbers
    if value equals 2 then
        stop the loop
    end if
    show value
end repeat

set scores to a map with "Ada" mapped to 10, "Grace" mapped to 20
show scores
show item "Grace" of scores
show call keys with collection = scores
show call sort with items = numbers
show call sum with items = numbers
show call join with items = numbers, separator = " | "
show call split with text = "a,b,c", by = ","
