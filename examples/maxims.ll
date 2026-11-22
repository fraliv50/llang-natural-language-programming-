# English phrase builtins and postfix predicates.

set name to "  ada lovelace  "
show name
show call trim with text = name
show call uppercase of with text = (call trim with text = name)
show call find in text with text = "hello world", piece = "world"
show call replace in text with text = "one fish", old = "one", new = "two"

set xs to a list of 1, 2, 3
show xs is empty
show (an empty list) is empty
show (an empty list) is not empty
show nothing is nothing
show 5 is a number
show "hi" is text
show xs is a list
show (an empty map) is a map
show call reverse of with items = xs
