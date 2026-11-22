# A native llang reimplementation of the core of CPython's textwrap module.
#
# Grounded in CPython's Lib/textwrap.py (PSF license, version 3.11):
#   https://github.com/python/cpython/blob/3.11/Lib/textwrap.py
#
# Supported subset (documented explicitly):
#   * wrap(text, width) and fill(text, width) with the TextWrapper defaults,
#     except for the features intentionally left out here:
#       - No expand_tabs / replace_whitespace preprocessing. Input is treated
#         as ordinary text whose whitespace characters are plain separators;
#         internal runs of whitespace are preserved byte-for-byte on a line,
#         and whitespace at line boundaries is dropped. Callers who need exact
#         stdlib behaviour should pass text containing only spaces.
#       - No break_on_hyphens: hyphenated words are never split at a hyphen;
#         they are only broken at the width boundary when the whole chunk is
#         too long (break_long_words = true, as in the stdlib default).
#       - No initial_indent, subsequent_indent, placeholder, max_lines, or
#         drop_whitespace switches: drop_whitespace is always true.
#   * Long words are broken greedily and the remainder is carried over to the
#     next line, exactly like TextWrapper._handle_long_word.
#
# The algorithm mirrors TextWrapper._split / _wrap_chunks / _handle_long_word
# for that subset, using a forward index instead of a reversed chunk stack.

define function is_whitespace taking ch
    give back call contains with collection = " \t\n", value = ch
end function

# A chunk is either all whitespace or all non-whitespace, so inspecting the
# first character is enough. An empty chunk counts as "not whitespace" here;
# it only ever appears as a synthetic zero-length piece of a long word.
define function whitespace_chunk taking chunk
    if (the length of chunk) equals 0 then
        give back false
    end if
    give back call is_whitespace with ch = item 0 of chunk
end function

# Python's value[begin:finish] for indices inside the string, built manually
# because llang has no slicing syntax and no substring builtin.
define function slice_text taking value, begin, finish
    set result to ""
    set i to begin
    repeat while i is less than finish
        set result to result plus item i of value
        set i to i plus 1
    end repeat
    give back result
end function

# Equivalent to TextWrapper._split with break_on_hyphens = false: alternate
# runs of whitespace and runs of word characters, with no empty chunks.
define function split_chunks taking text
    set chunks to an empty list
    set current to ""
    set current_is_ws to nothing
    repeat for each ch in text
        set ch_ws to call is_whitespace with ch = ch
        if current_is_ws is nothing then
            set current_is_ws to ch_ws
            set current to ch
        otherwise if ch_ws equals current_is_ws then
            set current to current plus ch
        otherwise
            add current to chunks
            set current to ch
            set current_is_ws to ch_ws
        end if
    end repeat
    if (the length of current) is greater than 0 then
        add current to chunks
    end if
    give back chunks
end function

# Lists cannot shrink in llang, so build a copy without the final element.
define function without_last taking items
    set result to an empty list
    set k to 0
    repeat while k is less than ((the length of items) minus 1)
        add item k of items to result
        set k to k plus 1
    end repeat
    give back result
end function

define function wrap taking text, width
    if width is at most 0 then
        give back an empty list
    end if

    set chunks to call split_chunks with text = text
    set lines to an empty list
    set i to 0
    set n to the length of chunks

    repeat while i is less than n
        # Drop leading whitespace on every line except the very first one.
        if (the length of lines) is greater than 0 then
            if call whitespace_chunk with chunk = item i of chunks then
                set i to i plus 1
            end if
        end if
        if i is at least n then
            stop the loop
        end if

        set cur_line to an empty list
        set cur_len to 0

        # Greedily fill the line with chunks that still fit.
        repeat while i is less than n
            set chunk to item i of chunks
            set chunk_len to the length of chunk
            if (cur_len plus chunk_len) is at most width then
                add chunk to cur_line
                set cur_len to cur_len plus chunk_len
                set i to i plus 1
            otherwise
                stop the loop
            end if
        end repeat

        # A chunk longer than the whole width is broken: take what fits on
        # this line and leave the remainder for the next one.
        if (i is less than n) and ((the length of (item i of chunks)) is greater than width) then
            set space_left to width minus cur_len
            set chunk to item i of chunks
            set piece to call slice_text with value = chunk, begin = 0, finish = space_left
            add piece to cur_line
            set rest to call slice_text with value = chunk, begin = space_left, finish = (the length of chunk)
            set item i of chunks to rest
        end if

        # Drop trailing whitespace from the finished line (one chunk, as the
        # stdlib does).
        if (the length of cur_line) is greater than 0 then
            if call whitespace_chunk with chunk = item ((the length of cur_line) minus 1) of cur_line then
                set cur_line to call without_last with items = cur_line
            end if
        end if

        # When cur_line is empty, no line is emitted and the loop retries with
        # the remaining chunks. Progress is guaranteed: either the greedy pass
        # consumed a chunk, or the long-word pass shortened the next chunk.
        if (the length of cur_line) is greater than 0 then
            add call join with items = cur_line, separator = "" to lines
        end if
    end repeat

    give back lines
end function

define function fill taking text, width
    set lines to call wrap with text = text, width = width
    give back call join with items = lines, separator = "\n"
end function
