# Unix shell-style wildcard matching, reimplemented in llang.
#
# Grounded in CPython's Lib/fnmatch.py (PSF license, version 3.11):
#   https://github.com/python/cpython/blob/3.11/Lib/fnmatch.py
# CPython translates a pattern to a regular expression; llang has neither a
# regex engine nor slices, so we match directly with recursion and character
# indexing (`item i of text`, `the length of text`).
#
# Supported pattern syntax:
#   *       matches any run of characters (including none); runs of '*' collapse
#   ?       matches exactly one character (newlines included)
#   [seq]   matches any one character in seq
#   [!seq]  matches any one character not in seq
#   a-z     inside a class, a range between two characters (code point order)
# Everything else matches itself literally. An unclosed '[' is a literal '['.

# Locate the closing ']' for a class whose '[' sits at the position before
# `start`. A leading '!' and a leading ']' are class members, not the closer.
# Give back the index of the closer, or -1 when the class is never closed.
define function find_close taking pattern, start
    set n to the length of pattern
    set j to start
    if ((j is less than n) and ((item j of pattern) equals "!")) then
        set j to j plus 1
    end if
    if ((j is less than n) and ((item j of pattern) equals "]")) then
        set j to j plus 1
    end if
    repeat while j is less than n
        if (item j of pattern) equals "]" then
            give back j
        end if
        set j to j plus 1
    end repeat
    give back 0 minus 1
end function

# Is character `ch` present in `content` between indices `begin` and `finish`?
# A '-' with a character on each side is an inclusive code-point range.
define function class_member taking content, ch, begin, finish
    set k to begin
    repeat while k is less than finish
        if (((k plus 2) is less than finish) and ((item (k plus 1) of content) equals "-")) then
            set low to item k of content
            set high to item (k plus 2) of content
            if ((low is at most ch) and (ch is at most high)) then
                give back true
            end if
            set k to k plus 3
        otherwise
            if (item k of content) equals ch then
                give back true
            end if
            set k to k plus 1
        end if
    end repeat
    give back false
end function

# Match one character against a bracket expression. `start` is the index just
# after '['; `close` is the index of the closing ']'.
define function class_match taking pattern, ch, start, close
    set begin to start
    set negated to false
    if ((begin is less than close) and ((item begin of pattern) equals "!")) then
        set negated to true
        set begin to begin plus 1
    end if
    set inside to call class_member with content = pattern, ch = ch, begin = begin, finish = close
    if negated then
        give back not inside
    end if
    give back inside
end function

# Core recursive matcher: does pattern[pi:] match all of name[ni:]?
define function match_here taking name, pattern, ni, pi
    set nn to the length of name
    set pn to the length of pattern

    if pi equals pn then
        give back ni equals nn
    end if

    set c to item pi of pattern

    if c equals "*" then
        set cursor to pi plus 1
        repeat while ((cursor is less than pn) and ((item cursor of pattern) equals "*"))
            set cursor to cursor plus 1
        end repeat
        if cursor equals pn then
            give back true
        end if
        set k to ni
        repeat while k is less than (nn plus 1)
            if call match_here with name = name, pattern = pattern, ni = k, pi = cursor then
                give back true
            end if
            set k to k plus 1
        end repeat
        give back false
    end if

    if ni equals nn then
        give back false
    end if
    set ch to item ni of name

    if c equals "?" then
        give back call match_here with name = name, pattern = pattern, ni = (ni plus 1), pi = (pi plus 1)
    end if

    if c equals "[" then
        set close to call find_close with pattern = pattern, start = (pi plus 1)
        if close equals (0 minus 1) then
            if ch does not equal "[" then
                give back false
            end if
            give back call match_here with name = name, pattern = pattern, ni = (ni plus 1), pi = (pi plus 1)
        end if
        if not (call class_match with pattern = pattern, ch = ch, start = (pi plus 1), close = close) then
            give back false
        end if
        give back call match_here with name = name, pattern = pattern, ni = (ni plus 1), pi = (close plus 1)
    end if

    if ch does not equal c then
        give back false
    end if
    give back call match_here with name = name, pattern = pattern, ni = (ni plus 1), pi = (pi plus 1)
end function

define function fnmatchcase taking name, pattern
    give back call match_here with name = name, pattern = pattern, ni = 0, pi = 0
end function

# fnmatch() case-normalizes both arguments on Windows (os.path.normcase
# lowercases); our test host is Windows, so lowercase both before matching.
define function fnmatch taking name, pattern
    set lower_name to call lowercase of with text = name
    set lower_pattern to call lowercase of with text = pattern
    give back call fnmatchcase with name = lower_name, pattern = lower_pattern
end function
