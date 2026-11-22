# llang-native text module.

define function reverse_text taking value
    set result to ""
    set i to (the length of value) minus 1
    repeat while i is at least 0
        set result to result plus item i of value
        set i to i minus 1
    end repeat
    give back result
end function

define function initials taking value
    set words to call split with text = value, by = " "
    set result to ""
    repeat for each word in words
        if (the length of word) is greater than 0 then
            set result to result plus (call uppercase of with text = item 0 of word) plus "."
        end if
    end repeat
    give back result
end function

define function is_palindrome taking value
    set cleaned to call lowercase of with text = value
    give back cleaned equals (call reverse_text with value = cleaned)
end function
