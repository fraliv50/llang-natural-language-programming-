# Self-hosting Stage 2: a tokenizer for llang, written in llang.
#
# Token representation comes from lib/ast_contract.ll:
#   { category, text, line, column }
# The stream shape matches src/llang/lexer.py exactly: WORD, NUMBER, STRING,
# PUNCT, NEWLINE, EOF, with source positions and decoded string contents.
#
# Scope note: identifiers use ASCII letters/underscore, matching the lexer's
# common case. Unicode letters are left for a later stage.

use the ast_contract module

define function is_digit taking ch
    give back call contains with collection = "0123456789", value = ch
end function

define function is_alpha taking ch
    give back call contains with collection = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_", value = ch
end function

define function is_space taking ch
    give back call contains with collection = " \t\r", value = ch
end function

define function is_punct taking ch
    give back call contains with collection = "(),=@", value = ch
end function

define function tokenize taking text
    set result to an empty list
    set i to 0
    set line to 1
    set column to 1
    set n to the length of text

    repeat while i is less than n
        set ch to item i of text
        set i to i plus 1

        if call is_space with ch = ch then
            set column to column plus 1

        otherwise if ch equals "\n" then
            set tok to call make_token from ast_contract with category = "NEWLINE", content = "\n", line = line, column = column
            add tok to result
            set line to line plus 1
            set column to 1

        otherwise if ch equals "#" then
            set column to column plus 1
            repeat while i is less than n
                set nextch to item i of text
                if nextch equals "\n" then
                    stop the loop
                end if
                set i to i plus 1
                set column to column plus 1
            end repeat

        otherwise if ch equals "\"" then
            set startline to line
            set startcol to column
            set column to column plus 1
            set buffer to ""
            set closed to false
            repeat while i is less than n
                set nextch to item i of text
                set i to i plus 1
                if nextch equals "\"" then
                    set closed to true
                    set column to column plus 1
                    stop the loop
                end if
                if nextch equals "\n" then
                    fail with lex_error, "Unterminated string literal"
                end if
                if nextch equals "\\" then
                    if i is at least n then
                        fail with lex_error, "Unterminated escape sequence"
                    end if
                    set esc to item i of text
                    set i to i plus 1
                    set column to column plus 2
                    if esc equals "n" then
                        set buffer to buffer plus "\n"
                    otherwise if esc equals "t" then
                        set buffer to buffer plus "\t"
                    otherwise if esc equals "r" then
                        set buffer to buffer plus "\r"
                    otherwise if esc equals "\"" then
                        set buffer to buffer plus "\""
                    otherwise if esc equals "\\" then
                        set buffer to buffer plus "\\"
                    otherwise
                        set buffer to buffer plus esc
                    end if
                otherwise
                    set buffer to buffer plus nextch
                    set column to column plus 1
                end if
            end repeat
            if not closed then
                fail with lex_error, "Unterminated string literal"
            end if
            set tok to call make_token from ast_contract with category = "STRING", content = buffer, line = startline, column = startcol
            add tok to result

        otherwise if call is_digit with ch = ch then
            set startcol to column
            set buffer to ch
            set column to column plus 1
            repeat while i is less than n
                set nextch to item i of text
                if not (call is_digit with ch = nextch) then
                    stop the loop
                end if
                set buffer to buffer plus nextch
                set i to i plus 1
                set column to column plus 1
            end repeat
            if i is less than n then
                if (item i of text) equals "." then
                    if i plus 1 is less than n then
                        if call is_digit with ch = (item (i plus 1) of text) then
                            set buffer to buffer plus "."
                            set i to i plus 1
                            set column to column plus 1
                            repeat while i is less than n
                                set nextch to item i of text
                                if not (call is_digit with ch = nextch) then
                                    stop the loop
                                end if
                                set buffer to buffer plus nextch
                                set i to i plus 1
                                set column to column plus 1
                            end repeat
                        end if
                    end if
                end if
            end if
            set tok to call make_token from ast_contract with category = "NUMBER", content = buffer, line = line, column = startcol
            add tok to result

        otherwise if call is_alpha with ch = ch then
            set startcol to column
            set buffer to ch
            set column to column plus 1
            repeat while i is less than n
                set nextch to item i of text
                if (not (call is_alpha with ch = nextch)) and (not (call is_digit with ch = nextch)) then
                    stop the loop
                end if
                set buffer to buffer plus nextch
                set i to i plus 1
                set column to column plus 1
            end repeat
            set tok to call make_token from ast_contract with category = "WORD", content = buffer, line = line, column = startcol
            add tok to result

        otherwise if call is_punct with ch = ch then
            set tok to call make_token from ast_contract with category = "PUNCT", content = ch, line = line, column = column
            add tok to result
            set column to column plus 1

        otherwise
            fail with lex_error, "Unexpected character"
        end if
    end repeat

    set eof to call make_token from ast_contract with category = "EOF", content = "", line = line, column = column
    add eof to result
    give back result
end function

define function token_digests taking tokens
    set result to an empty list
    repeat for each tok in tokens
        add (call token_digest from ast_contract with token = tok) to result
    end repeat
    give back result
end function
