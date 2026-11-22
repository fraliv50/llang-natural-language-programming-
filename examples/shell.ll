# A shell/terminal layer written in llang, grounded in Nushell's design.
# Command execution is host-side and opt-in; the llang layer only adds
# structure, labeled calls, and loud failures.

use the shell module

show "--- command results are maps ---"
set result to call run from shell with command = "echo llang says hello"
show item "command" of result
show item "output" of result
show item "code" of result

show "--- text and predicates ---"
show call capture from shell with command = "echo captured text"
show call succeeds from shell with command = "echo yes"
show call succeeds from shell with command = "llang_missing_command_xyz"

show "--- structured output ---"
show call lines from shell with command = "echo first line"

show "--- a sequence of commands ---"
set steps to a list of "echo one", "echo two", "echo three"
set results to call run_each from shell with commands = steps
repeat for each step in results
    show (call trim with text = item "output" of step) plus " (code " plus (call text of with value = item "code" of step) plus ")"
end repeat

show "--- must succeed fails loudly ---"
show (call trim with text = call must_succeed from shell with command = "echo trusted")

show "--- environment lookup ---"
show call env from shell with name = "LLANG_DEMO_VALUE_NOT_SET"

show "--- safe command construction (llang shlex rewrite) ---"
set safe_command to call build from shell with program = "echo", args = a list of "hello world", "it's fine"
show safe_command
show (call trim with text = call capture from shell with command = safe_command)
