# Self-hosting stage 0: llang-native representation of tokens and AST nodes.
#
# A token is a map with: category, text, line, column.
# A node is a map with: type, pos (list of line/column), and named fields.
# Every constructor and accessor is total: missing fields fail loudly.

define function make_token taking category, content, line, column
    set result to an empty map
    set item "category" of result to category
    set item "text" of result to content
    set item "line" of result to line
    set item "column" of result to column
    give back result
end function

define function token_category taking token
    give back item "category" of token
end function

define function token_text taking token
    give back item "text" of token
end function

define function token_line taking token
    give back item "line" of token
end function

define function token_column taking token
    give back item "column" of token
end function

define function token_digest taking token
    give back a list of (item "category" of token), (item "text" of token), (item "line" of token), (item "column" of token)
end function

define function make_node taking type, line, column
    set result to an empty map
    set item "type" of result to type
    set item "pos" of result to (a list of line, column)
    give back result
end function

define function set_field taking node, name, value
    set item name of node to value
end function

define function field taking node, name
    give back item name of node
end function

define function has_field taking node, name
    give back call contains with collection = (call keys of with collection = node), value = name
end function

define function node_fields taking node
    give back call sort with items = (call keys of with collection = node)
end function

define function node_digest taking node
    set names to call node_fields with node = node
    set result to an empty list
    repeat for each key in names
        add key to result
    end repeat
    give back result
end function

define function same_value taking left, right
    give back left equals right
end function

define function same_token taking left, right
    give back (call same_value with left = left, right = right)
end function

define function same_node taking left, right
    give back (call same_value with left = left, right = right)
end function

define function describe_token taking token
    give back (item "category" of token) plus " " plus (item "text" of token) plus " at " plus (call text of with value = item "line" of token) plus ":" plus (call text of with value = item "column" of token)
end function
