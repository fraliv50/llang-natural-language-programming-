# CPython's csv module (default "excel" dialect), reimplemented in llang.
#
# Grounded in CPython 3.11 Lib/_csv.py / Modules/_csv.c (PSF license):
#   https://github.com/python/cpython/blob/3.11/Modules/_csv.c
# We implement the excel dialect: comma delimiter, double-quote quoting,
# doubled quotes inside quoted fields, embedded newlines, and CRLF/LF rows.
#
# The exports are single-word names, used like this:
#   use the csv module
#   set rows to call read_rows from csv with text = text
#   set text to call write_rows from csv with rows = rows

# --- reader -------------------------------------------------------------
# A character-by-character state machine mirroring CPython's parser states:
# start_record, start_field, in_field, quoted, quote_after, eat_crnl.
define function read_rows taking text
    set rows to an empty list
    set row to an empty list
    set field to ""
    set state to "start_record"
    set i to 0
    set n to the length of text

    repeat while i is less than n
        set ch to item i of text
        set consume to true

        if state equals "eat_crnl" then
            if ch equals "\n" then
                set state to "start_record"
            otherwise if ch equals "\r" then
                add row to rows
                set row to an empty list
            otherwise
                set state to "start_record"
                set consume to false
            end if

        otherwise if state equals "start_record" then
            if (ch equals "\n") or (ch equals "\r") then
                add row to rows
                set row to an empty list
                if ch equals "\r" then
                    set state to "eat_crnl"
                end if
            otherwise if ch equals "\"" then
                set state to "quoted"
            otherwise if ch equals "," then
                add field to row
                set field to ""
                set state to "start_field"
            otherwise
                set field to ch
                set state to "in_field"
            end if

        otherwise if state equals "start_field" then
            if (ch equals "\n") or (ch equals "\r") then
                add field to row
                set field to ""
                add row to rows
                set row to an empty list
                if ch equals "\r" then
                    set state to "eat_crnl"
                otherwise
                    set state to "start_record"
                end if
            otherwise if ch equals "\"" then
                set state to "quoted"
            otherwise if ch equals "," then
                add field to row
                set field to ""
            otherwise
                set field to ch
                set state to "in_field"
            end if

        otherwise if state equals "in_field" then
            if (ch equals "\n") or (ch equals "\r") then
                add field to row
                set field to ""
                add row to rows
                set row to an empty list
                if ch equals "\r" then
                    set state to "eat_crnl"
                otherwise
                    set state to "start_record"
                end if
            otherwise if ch equals "," then
                add field to row
                set field to ""
                set state to "start_field"
            otherwise
                set field to field plus ch
            end if

        otherwise if state equals "quoted" then
            if ch equals "\"" then
                set state to "quote_after"
            otherwise
                set field to field plus ch
            end if

        otherwise if state equals "quote_after" then
            if ch equals "\"" then
                set field to field plus "\""
                set state to "quoted"
            otherwise if ch equals "," then
                add field to row
                set field to ""
                set state to "start_field"
            otherwise if (ch equals "\n") or (ch equals "\r") then
                add field to row
                set field to ""
                add row to rows
                set row to an empty list
                if ch equals "\r" then
                    set state to "eat_crnl"
                otherwise
                    set state to "start_record"
                end if
            otherwise
                set field to field plus ch
                set state to "in_field"
            end if
        end if

        if consume then
            set i to i plus 1
        end if
    end repeat

    # Flush any pending record at end of input.  CPython's non-strict mode
    # accepts an unterminated quoted field, so "quoted" is flushed too.
    if (state equals "in_field") or (state equals "quoted") or (state equals "quote_after") or (state equals "start_field") then
        add field to row
        add row to rows
    end if

    give back rows
end function

# --- writer -------------------------------------------------------------
# True when VALUE must be quoted: it holds a delimiter, a quote, or a
# line break.  ONLY is true when the row has exactly one field; CPython
# quotes a lone empty field as "" rather than writing nothing at all.
define function needs_quote taking value, only
    set n to the length of value
    set i to 0
    repeat while i is less than n
        set ch to item i of value
        if (ch equals ",") or (ch equals "\"") or (ch equals "\n") or (ch equals "\r") then
            give back true
        end if
        set i to i plus 1
    end repeat
    give back (only and (n equals 0))
end function

# Double every quote inside a quoted field.
define function escape_quotes taking value
    set result to ""
    set i to 0
    repeat while i is less than (the length of value)
        set ch to item i of value
        if ch equals "\"" then
            set result to result plus "\"\""
        otherwise
            set result to result plus ch
        end if
        set i to i plus 1
    end repeat
    give back result
end function

define function write_rows taking rows
    set out to ""
    repeat for each row in rows
        set line to ""
        set count to the length of row
        set j to 0
        repeat while j is less than count
            set text_value to (call text of with value = item j of row)
            set quoted to (call needs_quote with value = text_value, only = (count equals 1))
            if quoted then
                set line to line plus "\"" plus (call escape_quotes with value = text_value) plus "\""
            otherwise
                set line to line plus text_value
            end if
            if j is less than (count minus 1) then
                set line to line plus ","
            end if
            set j to j plus 1
        end repeat
        set out to out plus line plus "\r\n"
    end repeat
    give back out
end function
