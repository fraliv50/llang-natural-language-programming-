# llang-native shell layer, built on the explicitly labeled foreign shell module.
# The foreign module is the only part that touches the host OS; everything here
# is ordinary llang: maps, lists, functions, and loud failures.

use the foreign shell module as host_shell
use the shlex module

define function run taking command
    give back call run command from host_shell with command = command
end function

define function capture taking command
    give back call output of command from host_shell with command = command
end function

define function succeeds taking command
    give back call command succeeds from host_shell with command = command
end function

define function must_succeed taking command
    set result to call run command from host_shell with command = command
    require (item "code" of result) equals 0, "command failed"
    give back item "output" of result
end function

define function lines taking command
    set output to call capture with command = command
    set parts to call split with text = output, by = "\n"
    set result to an empty list
    set i to 0
    repeat while i is less than (the length of parts)
        if (i is less than ((the length of parts) minus 1)) or ((item i of parts) is not empty) then
            add item i of parts to result
        end if
        set i to i plus 1
    end repeat
    give back result
end function

define function run_each taking commands
    set results to an empty list
    repeat for each command in commands
        set result to call run command from host_shell with command = command
        add result to results
    end repeat
    give back results
end function

define function env taking name
    give back call environment value from host_shell with name = name
end function

# Build a command from a program and arguments, quoting each argument with the
# llang rewrite of shlex.quote. This avoids hand-written shell strings.
define function build taking program, args
    set words to a list of program
    repeat for each word in args
        add word to words
    end repeat
    give back call shell_join from shlex with words = words
end function
