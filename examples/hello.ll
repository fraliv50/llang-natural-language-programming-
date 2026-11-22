# A first llang program.
# Note: indentation is decoration only; 'end ...' closes blocks.

set greeting to "Hello"
set name to "Ada"

display greeting plus ", " plus name

if name equals "Ada" then
    show "recognised"
otherwise
    show "unknown"
end if

set counter to 0
repeat while counter is less than 3
    print counter
    set counter to counter plus 1
end repeat

define function greet taking whom
also known as say_hello, welcome
    give back "Welcome, " plus whom
end function

show call greet with whom = "Grace"
show call say_hello with whom = "Linus"

require counter equals 3, "counter should be 3"
show "all good"
