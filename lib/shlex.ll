# POSIX shell-like word splitting and quoting, reimplemented in llang.
#
# Grounded in CPython's Lib/shlex.py (PSF license, version 3.11):
#   https://github.com/python/cpython/blob/3.11/Lib/shlex.py
# We implement the `split()`, `quote()` and `join()` behaviour for the
# common case (whitespace_split=True, no comments, posix=True).

define function is_ws taking ch
    give back call contains with collection = " \t\r\n", value = ch
end function

define function is_quote taking ch
    give back call contains with collection = "\"'", value = ch
end function

define function is_safe taking ch
    give back call contains with collection = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_@%+=:,./-", value = ch
end function

define function shell_words taking input
    set result to an empty list
    set n to the length of input
    set i to 0
    set token to ""
    set quoted to false
    set state to " "
    set escapedstate to " "

    repeat while i is less than n
        set ch to item i of input
        set i to i plus 1

        if state equals " " then
            if call is_ws with ch = ch then
                if (the length of token) is greater than 0 or quoted then
                    add token to result
                    set token to ""
                    set quoted to false
                end if
            otherwise if call is_quote with ch = ch then
                set state to ch
                set quoted to true
                set token to ""
            otherwise if ch equals "\\" then
                set escapedstate to "a"
                set state to "\\"
            otherwise
                set token to ch
                set state to "a"
            end if
        otherwise if state equals "a" then
            if call is_ws with ch = ch then
                set state to " "
                if (the length of token) is greater than 0 or quoted then
                    add token to result
                    set token to ""
                    set quoted to false
                end if
            otherwise if call is_quote with ch = ch then
                set state to ch
                set quoted to true
            otherwise if ch equals "\\" then
                set escapedstate to "a"
                set state to "\\"
            otherwise
                set token to token plus ch
            end if
        otherwise if (state equals "'") or (state equals "\"") then
            if ch equals state then
                set state to "a"
            otherwise if (state equals "\"") and (ch equals "\\") then
                set escapedstate to state
                set state to "\\"
            otherwise
                set token to token plus ch
            end if
        otherwise
            if (escapedstate equals "\"") and (ch does not equal state) and (ch does not equal escapedstate) then
                set token to token plus state
            end if
            set token to token plus ch
            set state to escapedstate
        end if
    end repeat

    if (state equals "'") or (state equals "\"") then
        fail with unclosed_quote, "No closing quotation"
    end if
    if state equals "\\" then
        fail with bad_escape, "No escaped character"
    end if
    if (the length of token) is greater than 0 or quoted then
        add token to result
    end if
    give back result
end function

define function shell_quote taking value
    if value equals "" then
        give back "''"
    end if
    set i to 0
    repeat while i is less than (the length of value)
        if not (call is_safe with ch = item i of value) then
            give back "'" plus (call replace in text with text = value, old = "'", new = "'\"'\"'") plus "'"
        end if
        set i to i plus 1
    end repeat
    give back value
end function

define function shell_join taking words
    set result to ""
    repeat for each word in words
        if (the length of result) is greater than 0 then
            set result to result plus " "
        end if
        set result to result plus (call shell_quote with value = word)
    end repeat
    give back result
end function
