# humanize.number and humanize.filesize, re-expressed in llang.
#
# Grounded in the English/default-locale behaviour of:
#   https://raw.githubusercontent.com/python-humanize/humanize/master/src/humanize/number.py
#   https://raw.githubusercontent.com/python-humanize/humanize/master/src/humanize/filesize.py
# (MIT license, python-humanize/humanize).  See tools/rewrites/humanize/SOURCE.md.
#
# i18n/gettext is deliberately omitted: every catalog lookup is resolved to the
# English source string, including the locale separators ("," and ".").  The
# allow-listed foreign math module is used only for the libm primitives that
# llang has no native equivalent for (floor, ceil, log); all formatting,
# rounding, grouping, exponent handling and validation is written in llang.
# No regular expressions are used anywhere in this module.

use the foreign math module as hostmath

# ---------------------------------------------------------------------------
# Self-describing tables (insertion order is meaningful: powers ascend).
# ---------------------------------------------------------------------------

set powers_of_ten to a list of (10 to the power of 3), (10 to the power of 6), (10 to the power of 9), (10 to the power of 12), (10 to the power of 15), (10 to the power of 18), (10 to the power of 21), (10 to the power of 24), (10 to the power of 27), (10 to the power of 30), (10 to the power of 33), (10 to the power of 100)
set power_names to a list of "thousand", "million", "billion", "trillion", "quadrillion", "quintillion", "sextillion", "septillion", "octillion", "nonillion", "decillion", "googol"
set big_prefixes to "kMGTPEZYRQ"
set gnu_prefixes to "KMGTPEZYRQ"
set small_prefixes to "mμnpfazyrq"
set binary_suffixes to a list of "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB", "RiB", "QiB"
set decimal_suffixes to a list of "kB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB", "RB", "QB"
set superscript to a map with "0" mapped to "⁰", "1" mapped to "¹", "2" mapped to "²", "3" mapped to "³", "4" mapped to "⁴", "5" mapped to "⁵", "6" mapped to "⁶", "7" mapped to "⁷", "8" mapped to "⁸", "9" mapped to "⁹", "-" mapped to "⁻"

# ---------------------------------------------------------------------------
# Small text helpers.  llang has no slices, so substring is an explicit loop.
# ---------------------------------------------------------------------------

define function substring taking source, start, count
    set result to ""
    set i to start
    repeat while (i is less than (start plus count)) and (i is less than (the length of source))
        set result to result plus item i of source
        set i to i plus 1
    end repeat
    give back result
end function

define function is_digit taking ch
    give back call contains with collection = "0123456789", value = ch
end function

define function count_decimals taking fmt
    set dot to call find in text with text = fmt, piece = "."
    if dot is less than 0 then
        give back 0
    end if
    set tail to call substring with source = fmt, start = (dot plus 1), count = (the length of fmt) minus (dot plus 1)
    set digits_text to ""
    repeat for each ch in tail
        if call is_digit with ch = ch then
            set digits_text to digits_text plus ch
        otherwise
            stop the loop
        end if
    end repeat
    if (the length of digits_text) equals 0 then
        give back 0
    end if
    give back call to number with text = digits_text
end function

# ---------------------------------------------------------------------------
# Loud, localized validation.  Python's permissive str() fallback remains for
# unconvertible *text*; wrong *types* are rejected with a format_error problem.
# ---------------------------------------------------------------------------

define function require_input taking value
    if (value is a number) or (value is text) then
        give back nothing
    end if
    fail with format_error, "format_error: expected a number or text"
end function

define function require_text taking value
    if not (value is text) then
        fail with format_error, "format_error: expected text"
    end if
end function

define function require_boolean taking value
    if (value equals true) or (value equals false) then
        give back nothing
    end if
    fail with format_error, "format_error: expected a boolean"
end function

define function require_whole taking value
    if not (value is a number) then
        fail with format_error, "format_error: expected a whole number"
    end if
    set rendered to call text of with value = value
    if call contains with collection = rendered, value = "." then
        fail with format_error, "format_error: expected a whole number"
    end if
    if call contains with collection = rendered, value = "e" then
        fail with format_error, "format_error: expected a whole number"
    end if
end function

define function require_nonnegative_whole taking value
    call require_whole with value = value
    if value is less than 0 then
        fail with format_error, "format_error: expected a non-negative whole number"
    end if
end function

# ---------------------------------------------------------------------------
# Conversion and finiteness helpers (Python int()/float() semantics).
# ---------------------------------------------------------------------------

define function strip_underscores taking text_value
    set result to ""
    repeat for each ch in text_value
        if ch does not equal "_" then
            set result to result plus ch
        end if
    end repeat
    give back result
end function

define function digit_value taking ch
    # The position of a digit in this string is its numeric value.
    give back call find in text with text = "0123456789", piece = ch
end function

define function parse_number taking text_value
    # Python float()/int() for well-formed decimal text, written in llang so an
    # invalid string never reaches a host builtin.  "nothing" means ValueError.
    set text_value to call trim with text = text_value
    if (the length of text_value) equals 0 then
        give back nothing
    end if
    set sign to 1
    if (item 0 of text_value) equals "+" then
        set text_value to call substring with source = text_value, start = 1, count = (the length of text_value) minus 1
    otherwise if (item 0 of text_value) equals "-" then
        set sign to 0 minus 1
        set text_value to call substring with source = text_value, start = 1, count = (the length of text_value) minus 1
    end if
    if (the length of text_value) equals 0 then
        give back nothing
    end if

    set e_pos to call find in text with text = text_value, piece = "e"
    set upper_e to call find in text with text = text_value, piece = "E"
    if upper_e is at least 0 then
        if (e_pos is less than 0) or (upper_e is less than e_pos) then
            set e_pos to upper_e
        end if
    end if
    set exp_part to ""
    if e_pos is at least 0 then
        set exp_part to call substring with source = text_value, start = (e_pos plus 1), count = (the length of text_value) minus (e_pos plus 1)
        set text_value to call substring with source = text_value, start = 0, count = e_pos
    end if

    set dot to call find in text with text = text_value, piece = "."
    set int_part to text_value
    set frac_part to ""
    if dot is at least 0 then
        set int_part to call substring with source = text_value, start = 0, count = dot
        set frac_part to call substring with source = text_value, start = (dot plus 1), count = (the length of text_value) minus (dot plus 1)
    end if
    set int_digits to call strip_underscores with text_value = int_part
    set frac_digits to call strip_underscores with text_value = frac_part
    if (the length of int_digits) equals 0 then
        if (the length of frac_digits) equals 0 then
            give back nothing
        end if
    end if
    repeat for each ch in int_digits
        if not (call is_digit with ch = ch) then
            give back nothing
        end if
    end repeat
    repeat for each ch in frac_digits
        if not (call is_digit with ch = ch) then
            give back nothing
        end if
    end repeat

    set exponent to 0
    if (the length of exp_part) is greater than 0 then
        set exp_sign to 1
        if (item 0 of exp_part) equals "+" then
            set exp_part to call substring with source = exp_part, start = 1, count = (the length of exp_part) minus 1
        otherwise if (item 0 of exp_part) equals "-" then
            set exp_sign to 0 minus 1
            set exp_part to call substring with source = exp_part, start = 1, count = (the length of exp_part) minus 1
        end if
        set exp_digits to call strip_underscores with text_value = exp_part
        if (the length of exp_digits) equals 0 then
            give back nothing
        end if
        repeat for each ch in exp_digits
            if not (call is_digit with ch = ch) then
                give back nothing
            end if
            set exponent to (exponent times 10) plus (call digit_value with ch = ch)
        end repeat
        set exponent to exponent times exp_sign
    end if

    set result to 0
    repeat for each ch in int_digits
        set result to (result times 10) plus (call digit_value with ch = ch)
    end repeat
    if (the length of frac_digits) is greater than 0 then
        set fraction to 0
        set scale to 1
        repeat for each ch in frac_digits
            set fraction to (fraction times 10) plus (call digit_value with ch = ch)
            set scale to scale times 10
        end repeat
        set result to result plus (fraction divided by scale)
    end if
    if exponent does not equal 0 then
        set result to result times (10 to the power of exponent)
    end if
    give back result times sign
end function

define function is_nonfinite_text taking text_value
    set lowered to call lowercase of with text = call trim with text = text_value
    if call contains with collection = lowered, value = "nan" then
        give back true
    end if
    if call contains with collection = lowered, value = "inf" then
        give back true
    end if
    give back false
end function

define function numeric_kind taking value
    if value is a number then
        set product to value times 0
        if product equals product then
            give back "finite"
        end if
        give back "nonfinite"
    end if
    if value is text then
        if call is_nonfinite_text with text_value = value then
            give back "nonfinite"
        end if
        set parsed to call parse_number with text_value = value
        if parsed is nothing then
            give back "unconvertible"
        end if
        set product to parsed times 0
        if product equals product then
            give back "finite"
        end if
        give back "nonfinite"
    end if
    give back "unconvertible"
end function

define function float_of taking value
    if value is a number then
        give back value
    end if
    set parsed to call parse_number with text_value = value
    if parsed is nothing then
        give back value
    end if
    give back parsed
end function

define function not_finite_text taking value
    if value is text then
        set lowered to call lowercase of with text = call trim with text = value
        if call contains with collection = lowered, value = "nan" then
            give back "NaN"
        end if
        if call contains with collection = lowered, value = "inf" then
            if (item 0 of lowered) equals "-" then
                give back "-Inf"
            end if
            give back "+Inf"
        end if
    end if
    if value is a number then
        if value is less than 0 then
            give back "-Inf"
        end if
        if value is greater than 0 then
            give back "+Inf"
        end if
    end if
    give back "NaN"
end function

define function integer_of taking value
    # Python int(value): truncates toward zero; text with a dot or exponent is
    # a ValueError, reported here as "nothing" so callers keep the raw text.
    if value is a number then
        if value is at least 0 then
            give back call floor from hostmath with value = value
        end if
        give back call ceil from hostmath with value = value
    end if
    if value is text then
        if call contains with collection = value, value = "." then
            give back nothing
        end if
        if call contains with collection = value, value = "e" then
            give back nothing
        end if
        if call contains with collection = value, value = "E" then
            give back nothing
        end if
        set parsed to call parse_number with text_value = value
        if parsed is nothing then
            give back nothing
        end if
        give back parsed
    end if
    give back nothing
end function

define function is_finite taking value
    if not (value is a number) then
        give back false
    end if
    set product to value times 0
    give back product equals product
end function

define function trunc taking value
    if value is at least 0 then
        give back call floor from hostmath with value = value
    end if
    give back call ceil from hostmath with value = value
end function

# ---------------------------------------------------------------------------
# Number rendering without f-strings or printf: fixed(), plain_decimal() and
# group_digits() together reproduce format(value, ".Nf") / format(value, ",").
# ---------------------------------------------------------------------------

define function fixed taking value, digits
    set negative to false
    if (value is less than 0) or ((value equals 0) and ((call text of with value = value) equals "-0.0")) then
        set negative to true
        set value to 0 minus value
    end if
    set scale to 10 to the power of digits
    set rounded_value to call rounded with value = value, places = digits
    set scaled to call floor from hostmath with value = ((rounded_value times scale) plus 0.5)
    set whole to scaled floor divided by scale
    set fraction to scaled modulo scale
    set result to call text of with value = whole
    if digits is greater than 0 then
        set frac_text to call text of with value = fraction
        repeat while (the length of frac_text) is less than digits
            set frac_text to "0" plus frac_text
        end repeat
        set result to result plus "." plus frac_text
    end if
    if negative then
        set result to "-" plus result
    end if
    give back result
end function

define function plain_decimal taking number_text
    # Utility: expand exponent-form float text into plain decimal.  intcomma
    # does not use it because Python's general format keeps the exponent form.
    set e_pos to call find in text with text = number_text, piece = "e"
    if e_pos is less than 0 then
        give back number_text
    end if
    set mantissa to call substring with source = number_text, start = 0, count = e_pos
    set exp_text to call substring with source = number_text, start = (e_pos plus 1), count = (the length of number_text) minus (e_pos plus 1)
    set exponent to call to number with text = exp_text
    set sign to ""
    if (the length of mantissa) is greater than 0 then
        if (item 0 of mantissa) equals "-" then
            set sign to "-"
            set mantissa to call substring with source = mantissa, start = 1, count = (the length of mantissa) minus 1
        end if
    end if
    set dot to call find in text with text = mantissa, piece = "."
    set digits to ""
    set decimals to 0
    if dot is at least 0 then
        set digits to (call substring with source = mantissa, start = 0, count = dot) plus (call substring with source = mantissa, start = (dot plus 1), count = (the length of mantissa) minus (dot plus 1))
        set decimals to (the length of mantissa) minus (dot plus 1)
    otherwise
        set digits to mantissa
    end if
    set point_pos to (the length of digits) minus decimals plus exponent
    set result to ""
    if point_pos is at most 0 then
        set result to "0."
        repeat while point_pos is less than 0
            set result to result plus "0"
            set point_pos to point_pos plus 1
        end repeat
        set result to result plus digits
    otherwise if point_pos is at least (the length of digits) then
        set result to digits
        repeat while (the length of result) is less than point_pos
            set result to result plus "0"
        end repeat
    otherwise
        set before to call substring with source = digits, start = 0, count = point_pos
        set after to call substring with source = digits, start = point_pos, count = (the length of digits) minus point_pos
        set result to before plus "." plus after
    end if
    give back sign plus result
end function

define function group_digits taking number_text
    set sign to ""
    set body to number_text
    if (the length of body) is greater than 0 then
        if (item 0 of body) equals "-" then
            set sign to "-"
            set body to call substring with source = body, start = 1, count = (the length of body) minus 1
        end if
    end if
    set integer_part to body
    set decimal_part to ""
    set dot to call find in text with text = body, piece = "."
    if dot is at least 0 then
        set integer_part to call substring with source = body, start = 0, count = dot
        set decimal_part to call substring with source = body, start = (dot plus 1), count = (the length of body) minus (dot plus 1)
    end if
    set grouped to ""
    set n to the length of integer_part
    set i to 0
    set take to n modulo 3
    if take equals 0 then
        set take to 3
    end if
    repeat while i is less than n
        if (the length of grouped) is greater than 0 then
            set grouped to grouped plus ","
        end if
        set grouped to grouped plus (call substring with source = integer_part, start = i, count = take)
        set i to i plus take
        set take to 3
    end repeat
    if (the length of decimal_part) is greater than 0 then
        set grouped to grouped plus "." plus decimal_part
    end if
    give back sign plus grouped
end function

# ---------------------------------------------------------------------------
# Public formatting functions.  All parameters are labeled and mandatory;
# pass "nothing" for ndigits to select humanize's default grouping.
# ---------------------------------------------------------------------------

define function intcomma taking value, ndigits
    call require_input with value = value
    if not (ndigits is nothing) then
        call require_nonnegative_whole with value = ndigits
    end if
    set conv_kind to call numeric_kind with value = value
    if conv_kind equals "nonfinite" then
        give back call not_finite_text with value = value
    end if
    if conv_kind equals "unconvertible" then
        give back call text of with value = value
    end if

    set working to value
    if value is text then
        set working to call replace in text with text = value, old = ",", new = ""
        set stripped_kind to call numeric_kind with value = working
        if stripped_kind equals "nonfinite" then
            give back call not_finite_text with value = working
        end if
        if stripped_kind equals "unconvertible" then
            give back working
        end if
        if call contains with collection = working, value = "." then
            set working to call float_of with value = working
        otherwise
            set whole to call integer_of with value = working
            if whole is nothing then
                give back working
            end if
            set working to whole
        end if
    otherwise
        if not (call is_finite with value = value) then
            give back call not_finite_text with value = value
        end if
    end if

    if not (ndigits is nothing) then
        set formatted to call fixed with value = working, digits = ndigits
        give back call group_digits with number_text = formatted
    end if
    set rendered to call text of with value = working
    # Python's general format keeps exponent notation unchanged; the mantissa
    # is a single digit, so there is nothing to group.
    if call contains with collection = rendered, value = "e" then
        give back rendered
    end if
    give back call group_digits with number_text = rendered
end function

define function apnumber taking value
    call require_input with value = value
    set conv_kind to call numeric_kind with value = value
    if conv_kind equals "nonfinite" then
        give back call not_finite_text with value = value
    end if
    if conv_kind equals "unconvertible" then
        give back call text of with value = value
    end if
    set whole to call integer_of with value = value
    if whole is nothing then
        give back call text of with value = value
    end if
    if (whole is less than 0) or (whole is greater than 9) then
        give back call text of with value = whole
    end if
    set words to a list of "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"
    give back item whole of words
end function

define function ordinal taking value, gender
    call require_input with value = value
    call require_text with value = gender
    set conv_kind to call numeric_kind with value = value
    if conv_kind equals "nonfinite" then
        give back call not_finite_text with value = value
    end if
    if conv_kind equals "unconvertible" then
        give back call text of with value = value
    end if
    set whole to call integer_of with value = value
    if whole is nothing then
        give back call text of with value = value
    end if

    # In the English catalog the male and female suffix tables are identical;
    # the map keeps the gender distinction visible for future locales.
    set suffixes to a map with "male" mapped to (a list of "th", "st", "nd", "rd", "th", "th", "th", "th", "th", "th"), "female" mapped to (a list of "th", "st", "nd", "rd", "th", "th", "th", "th", "th", "th")
    set chosen to item "male" of suffixes
    if gender does not equal "male" then
        set chosen to item "female" of suffixes
    end if
    set last_two to whole modulo 100
    set digit to whole modulo 10
    if (last_two equals 11) or (last_two equals 12) or (last_two equals 13) then
        set digit to 0
    end if
    give back (call text of with value = whole) plus (item digit of chosen)
end function

define function intword taking value, fmt
    call require_input with value = value
    call require_text with value = fmt
    set conv_kind to call numeric_kind with value = value
    if conv_kind equals "nonfinite" then
        give back call not_finite_text with value = value
    end if
    if conv_kind equals "unconvertible" then
        give back call text of with value = value
    end if
    set whole to call integer_of with value = value
    if whole is nothing then
        give back call text of with value = value
    end if

    set negative_prefix to ""
    if whole is less than 0 then
        set negative_prefix to "-"
        set whole to 0 minus whole
    end if
    if whole is less than (item 0 of powers_of_ten) then
        give back negative_prefix plus (call text of with value = whole)
    end if

    # bisect_right: first power strictly greater than the value.
    set ordinal_index to 0
    repeat while ordinal_index is less than (the length of powers_of_ten)
        if (item ordinal_index of powers_of_ten) is greater than whole then
            stop the loop
        end if
        set ordinal_index to ordinal_index plus 1
    end repeat
    set largest to false
    if ordinal_index is at least (the length of powers_of_ten) then
        set largest to true
    end if
    set ordinal_index to ordinal_index minus 1
    set power to item ordinal_index of powers_of_ten
    set chopped to whole divided by power
    set digits to call count_decimals with fmt = fmt
    set rounded_value_text to call fixed with value = chopped, digits = digits
    set rounded_value to call to number with text = rounded_value_text

    # A rounded value landing exactly on the next power carries one ordinal.
    if not largest then
        set next_power to item (ordinal_index plus 1) of powers_of_ten
        set ratio to next_power floor divided by power
        if rounded_value equals ratio then
            set ordinal_index to ordinal_index plus 1
            set rounded_value to 1.0
        end if
    end if

    set number_text to call fixed with value = rounded_value, digits = digits
    give back negative_prefix plus number_text plus " " plus (item ordinal_index of power_names)
end function

define function to_superscript taking text_value
    set result to ""
    set allowed_chars to call keys of with collection = superscript
    repeat for each ch in text_value
        if call contains with collection = allowed_chars, value = ch then
            set result to result plus item ch of superscript
        otherwise
            set result to result plus ch
        end if
    end repeat
    give back result
end function

define function decimal_exponent taking magnitude
    # floor(log10(magnitude)) repaired at powers of ten: log(x)/log(10) can be
    # a hair below the integer (1e33 -> 32.999...), so compare the mantissa.
    set ratio to (call log from hostmath with value = magnitude) divided by (call log from hostmath with value = 10)
    set exponent to call floor from hostmath with value = ratio
    set trial to magnitude divided by (10 to the power of exponent)
    if trial is at least 10 then
        set exponent to exponent plus 1
    end if
    if trial is less than 1 then
        set exponent to exponent minus 1
    end if
    give back exponent
end function

define function scientific taking value, precision
    call require_input with value = value
    call require_nonnegative_whole with value = precision
    set conv_kind to call numeric_kind with value = value
    if conv_kind equals "nonfinite" then
        give back call not_finite_text with value = value
    end if
    if conv_kind equals "unconvertible" then
        give back call text of with value = value
    end if

    set amount to call float_of with value = value
    set negative to false
    if (amount is less than 0) or ((amount equals 0) and ((call text of with value = amount) equals "-0.0")) then
        set negative to true
        set amount to 0 minus amount
    end if
    set exponent to 0
    if amount does not equal 0 then
        set exponent to call decimal_exponent with magnitude = amount
    end if
    set mantissa to amount
    if amount does not equal 0 then
        set mantissa to amount divided by (10 to the power of exponent)
    end if
    set rounded_mantissa to call rounded with value = mantissa, places = precision
    if rounded_mantissa is at least 10 then
        set rounded_mantissa to rounded_mantissa divided by 10
        set exponent to exponent plus 1
    end if
    set part1 to call fixed with value = rounded_mantissa, digits = precision
    if negative then
        set part1 to "-" plus part1
    end if
    give back part1 plus " x 10" plus (call to_superscript with text_value = (call text of with value = exponent))
end function

define function naturalsize taking value, binary, gnu, fmt
    call require_input with value = value
    call require_boolean with value = binary
    call require_boolean with value = gnu
    call require_text with value = fmt

    set suffix to decimal_suffixes
    set base to 1000
    if gnu then
        set suffix to gnu_prefixes
        set base to 1024
    otherwise if binary then
        set suffix to binary_suffixes
        set base to 1024
    end if

    set byte_count to call float_of with value = value
    set abs_bytes to call absolute with value = byte_count
    if (abs_bytes equals 1) and (not gnu) then
        give back (call text of with value = (call trunc with value = byte_count)) plus " Byte"
    end if
    if abs_bytes is less than base then
        if gnu then
            give back (call text of with value = (call trunc with value = byte_count)) plus "B"
        end if
        give back (call text of with value = (call trunc with value = byte_count)) plus " Bytes"
    end if

    set exp to call floor from hostmath with value = ((call log from hostmath with value = abs_bytes) divided by (call log from hostmath with value = base))
    if exp is greater than (the length of suffix) then
        set exp to the length of suffix
    end if
    set digits to call count_decimals with fmt = fmt
    set mantissa to abs_bytes divided by (base to the power of exp)
    set scaled_mantissa to call rounded with value = mantissa, places = digits
    if (exp is less than (the length of suffix)) and (scaled_mantissa is at least base) then
        set exp to exp plus 1
    end if

    set space to " "
    if gnu then
        set space to ""
    end if
    set number_text to call fixed with value = (byte_count divided by (base to the power of exp)), digits = digits
    give back number_text plus space plus (item (exp minus 1) of suffix)
end function

define function metric taking value, unit, precision
    call require_input with value = value
    if value is text then
        fail with format_error, "format_error: metric expects a number, not text"
    end if
    call require_text with value = unit
    call require_nonnegative_whole with value = precision
    set conv_kind to call numeric_kind with value = value
    if conv_kind equals "nonfinite" then
        give back call not_finite_text with value = value
    end if

    set amount to call float_of with value = value
    set magnitude to call absolute with value = amount
    set exponent to 0
    if magnitude does not equal 0 then
        set exponent to call decimal_exponent with magnitude = magnitude
    end if
    if (exponent is at least 33) or (exponent is less than (0 minus 30)) then
        give back (call scientific with value = value, precision = (precision minus 1)) plus unit
    end if

    set old_bucket to ((exponent floor divided by 3) times 3)
    set scaled to amount divided by (10 to the power of old_bucket)
    set digits to precision minus (exponent modulo 3) minus 1
    if digits is less than 0 then
        set digits to 0
    end if
    if exponent is less than 30 then
        set threshold to 10 to the power of ((exponent modulo 3) plus 1)
        set rounded_scaled to call rounded with value = (call absolute with value = scaled), places = digits
        if rounded_scaled is at least threshold then
            set exponent to exponent plus 1
            set new_bucket to ((exponent floor divided by 3) times 3)
            set scaled to scaled divided by (10 to the power of (new_bucket minus old_bucket))
            set digits to precision minus (exponent modulo 3) minus 1
            if digits is less than 0 then
                set digits to 0
            end if
        end if
    end if

    set prefix to ""
    if exponent is at least 3 then
        set prefix to item ((exponent floor divided by 3) minus 1) of big_prefixes
    otherwise if exponent is less than 0 then
        set prefix to item ((((0 minus exponent) minus 1) floor divided by 3)) of small_prefixes
    end if
    set rendered to call fixed with value = scaled, digits = digits
    set space to " "
    if (unit is empty) and (prefix is empty) then
        set space to ""
    end if
    if (unit equals "°") or (unit equals "′") or (unit equals "″") then
        set space to ""
    end if
    give back rendered plus space plus prefix plus unit
end function

# ---------------------------------------------------------------------------
# Quality of life: one call that reports every English formatting of a value.
# ---------------------------------------------------------------------------

define function describe taking value
    set metric_text to "not a number"
    expect
        set metric_text to call metric with value = value, unit = "", precision = 3
    if a problem occurs then
        set metric_text to "not a number"
    end expect
    give back a map with "input" mapped to (call text of with value = value), "intcomma" mapped to (call intcomma with value = value, ndigits = nothing), "intword" mapped to (call intword with value = value, fmt = "%.1f"), "apnumber" mapped to (call apnumber with value = value), "ordinal" mapped to (call ordinal with value = value, gender = "male"), "scientific" mapped to (call scientific with value = value, precision = 2), "naturalsize" mapped to (call naturalsize with value = value, binary = false, gnu = false, fmt = "%.1f"), "metric" mapped to metric_text
end function
