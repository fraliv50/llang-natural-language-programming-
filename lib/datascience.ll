# llang-native data science: structured tabular data with Python/pandas semantics.
#
# Grounded in NumPy (BSD-3-Clause) and pandas (BSD-3-Clause), re-implemented in
# llang; no host code is used.  See docs/research/datascience-library-design.md.
#
#   use the datascience module
#   set people to call table with columns = (a map with "name" mapped to (a list of "Ada", "Lin"), "score" mapped to (a list of 90, 80)), order = nothing
#   show call dimensions from datascience with dataset = people
#
# A Dataset is an ordinary map: "kind" -> "dataset", "columns" -> map of equal
# length lists, "order" -> list of column names, plus optional "source".
# The canonical missing value is `nothing`; float NaN is normalized on ingress.

use the csv module
use the json module

# --- validation helpers ---------------------------------------------------

define function missing taking value
    if value is nothing then
        give back true
    end if
    if value is a number then
        give back not (value equals value)
    end if
    give back false
end function

define function clean_cell taking cell
    if call missing with value = cell then
        give back nothing
    end if
    give back cell
end function

define function cell_kind taking cell
    if cell is nothing then
        give back "empty"
    end if
    if cell is a number then
        give back "number"
    end if
    if cell is text then
        give back "text"
    end if
    if (cell equals true) or (cell equals false) then
        give back "boolean"
    end if
    give back "other"
end function

define function ensure_dataset taking dataset
    require dataset is a map, "a dataset must be a map"
    require (call contains with collection = dataset, value = "kind"), "a dataset needs a kind"
    require (item "kind" of dataset) equals "dataset", "the kind must be dataset"
    require (call contains with collection = dataset, value = "columns"), "a dataset needs columns"
    require (call contains with collection = dataset, value = "order"), "a dataset needs an order"
    require (item "columns" of dataset) is a map, "columns must be a map"
    require (item "order" of dataset) is a list, "order must be a list"
    set cols to item "columns" of dataset
    set seq to item "order" of dataset
    set width to the length of seq
    set height to nothing
    repeat for each name in seq
        require name is text, "column names must be text"
        require (call contains with collection = cols, value = name), "order names an unknown column"
        require (item name of cols) is a list, "each column must be a list"
        set n to the length of (item name of cols)
        if height is nothing then
            set height to n
        otherwise
            require n equals height, "all columns must have the same length"
        end if
    end repeat
    require (the length of cols) equals width, "columns and order must describe the same columns"
end function

define function ensure_names taking name_list, cols
    require name_list is a list, "names must be a list"
    repeat for each name in name_list
        require name is text, "names must be text"
        if not (call contains with collection = cols, value = name) then
            fail with unknown_column, "unknown column"
        end if
    end repeat
end function

define function source_of taking ds
    if call contains with collection = ds, value = "source" then
        give back item "source" of ds
    end if
    give back nothing
end function

define function fresh_dataset taking cols, seq, src
    set ds to a map with "kind" mapped to "dataset", "columns" mapped to cols, "order" mapped to seq
    if not (src is nothing) then
        set item "source" of ds to src
    end if
    give back ds
end function

define function row_count taking ds
    set seq to item "order" of ds
    if (the length of seq) equals 0 then
        give back 0
    end if
    give back the length of (item (item 0 of seq) of (item "columns" of ds))
end function

define function need_column taking ds, name
    call ensure_dataset with dataset = ds
    require name is text, "a column name must be text"
    set cols to item "columns" of ds
    if not (call contains with collection = cols, value = name) then
        fail with unknown_column, "unknown column"
    end if
    give back item name of cols
end function

define function key_tag taking cell
    if cell is nothing then
        give back "m:"
    end if
    if cell is text then
        give back "t:" plus cell
    end if
    if cell is a number then
        require cell equals (call rounded with value = cell), "join and group keys must be whole numbers"
        give back "n:" plus (call text of with value = cell)
    end if
    fail with bad_join_key, "boolean and collection keys are not supported"
end function

define function first_key_kind taking vals
    repeat for each cell in vals
        if not (call missing with value = cell) then
            give back (call cell_kind with cell = cell)
        end if
    end repeat
    give back ""
end function

define function check_key_values taking vals
    set first to nothing
    repeat for each cell in vals
        if not (call missing with value = cell) then
            set celltype to call cell_kind with cell = cell
            if not ((celltype equals "number") or (celltype equals "text")) then
                fail with bad_join_key, "keys must be text or whole numbers"
            end if
            if first is nothing then
                set first to celltype
            otherwise
                if not (celltype equals first) then
                    fail with bad_join_key, "mixed key types"
                end if
            end if
        end if
    end repeat
end function

# --- builders -------------------------------------------------------------

define function table taking columns, order
    require columns is a map, "table: columns must be a map of lists"
    require (order is a list) or (order is nothing), "table: order must be a list or nothing"
    set names to order
    if order is nothing then
        set names to call keys with collection = columns
    end if
    set fresh_names to an empty list
    repeat for each name in names
        require name is text, "table: column names must be text"
        require (the length of name) is greater than 0, "table: column names cannot be blank"
        require (call contains with collection = columns, value = name), "table: order names an unknown column"
        require not (call contains with collection = fresh_names, value = name), "table: duplicate column"
        add name to fresh_names
    end repeat
    set fresh_cols to an empty map
    set height to nothing
    repeat for each name in fresh_names
        set source_list to item name of columns
        require source_list is a list, "table: each column must be a list"
        if height is nothing then
            set height to the length of source_list
        otherwise
            if not ((the length of source_list) equals height) then
                fail with bad_shape, "table: columns must have equal length"
            end if
        end if
        set fresh_col to an empty list
        repeat for each cell in source_list
            add (call clean_cell with cell = cell) to fresh_col
        end repeat
        set item name of fresh_cols to fresh_col
    end repeat
    give back call fresh_dataset with cols = fresh_cols, seq = fresh_names, src = nothing
end function

define function records taking rows, order
    require rows is a list, "records: rows must be a list of maps"
    set names to order
    if order is nothing then
        set names to an empty list
        repeat for each entry in rows
            if not (entry is a map) then
                fail with bad_row, "records: each row must be a map"
            end if
            repeat for each name in (call keys with collection = entry)
                require name is text, "records: row keys must be text"
                if not (call contains with collection = names, value = name) then
                    add name to names
                end if
            end repeat
        end repeat
    otherwise
        require order is a list, "records: order must be a list or nothing"
    end if
    set fresh_cols to an empty map
    repeat for each name in names
        require name is text, "records: column names must be text"
        set fresh_col to an empty list
        repeat for each entry in rows
            if not (entry is a map) then
                fail with bad_row, "records: each row must be a map"
            end if
            if call contains with collection = entry, value = name then
                add (call clean_cell with cell = (item name of entry)) to fresh_col
            otherwise
                add nothing to fresh_col
            end if
        end repeat
        set item name of fresh_cols to fresh_col
    end repeat
    give back call fresh_dataset with cols = fresh_cols, seq = names, src = nothing
end function

define function load_csv taking text, header
    require text is text, "load_csv: text must be text"
    set rows to call read_rows from csv with text = text
    require header is text or (header equals true) or (header equals false), "load_csv: header must be a boolean"
    set names to an empty list
    set start to 0
    if (header equals true) or (header equals "true") then
        require (the length of rows) is greater than 0, "load_csv: a header needs a first row"
        set names to item 0 of rows
        set start to 1
    otherwise
        if (the length of rows) is greater than 0 then
            set width to the length of (item 0 of rows)
            set j to 0
            repeat while j is less than width
                add (call text of with value = j) to names
                set j to j plus 1
            end repeat
        end if
    end if
    repeat for each name in names
        require name is text, "load_csv: header cells must be text"
        require (the length of name) is greater than 0, "load_csv: header cells cannot be blank"
        require not (call has_duplicates with items = names), "load_csv: duplicate header"
    end repeat
    set fresh_cols to an empty map
    repeat for each name in names
        set fresh_col to an empty list
        set i to start
        repeat while i is less than (the length of rows)
            set onerow to item i of rows
            require (the length of onerow) equals (the length of names), "load_csv: ragged row"
            add (item (call index_of_name with names = names, name = name) of onerow) to fresh_col
            set i to i plus 1
        end repeat
        set item name of fresh_cols to fresh_col
    end repeat
    give back call fresh_dataset with cols = fresh_cols, seq = names, src = nothing
end function

define function index_of_name taking names, name
    set i to 0
    repeat while i is less than (the length of names)
        if (item i of names) equals name then
            give back i
        end if
        set i to i plus 1
    end repeat
    fail with unknown_column, "unknown column"
end function

define function load_json taking text
    require text is text, "load_json: text must be text"
    set parsed to call parse from json with text = text
    if parsed is a list then
        set ds to call records with rows = parsed, order = nothing
        give back ds
    end if
    if parsed is a map then
        repeat for each name in (call keys with collection = parsed)
            require (item name of parsed) is a list, "load_json: column values must be lists"
        end repeat
        give back call table with columns = parsed, order = nothing
    end if
    fail with bad_json_shape, "JSON must be a list of maps or a map of lists"
end function

# --- selectors ------------------------------------------------------------

define function column_from_dataset taking dataset, name
    set vals to call need_column with ds = dataset, name = name
    set out to an empty list
    repeat for each cell in vals
        add cell to out
    end repeat
    give back out
end function

define function select taking dataset, names
    call ensure_dataset with dataset = dataset
    set cols to item "columns" of dataset
    call ensure_names with name_list = names, cols = cols
    require not (call has_duplicates with items = names), "select: duplicate column"
    set fresh_cols to an empty map
    repeat for each name in names
        set out to an empty list
        repeat for each cell in (item name of cols)
            add cell to out
        end repeat
        set item name of fresh_cols to out
    end repeat
    give back call fresh_dataset with cols = fresh_cols, seq = names, src = (call source_of with ds = dataset)
end function

define function has_duplicates taking items
    repeat for each entry in items
        set occurrences to 0
        repeat for each other in items
            if other equals entry then
                set occurrences to occurrences plus 1
            end if
        end repeat
        if occurrences is greater than 1 then
            give back true
        end if
    end repeat
    give back false
end function

define function row taking dataset, index
    call ensure_dataset with dataset = dataset
    require (index is a number) and (index equals (call rounded with value = index)), "row: index must be a whole number"
    require index is at least 0, "row: negative index"
    if not (index is less than (call row_count with ds = dataset)) then
        fail with index_out_of_range, "row: index out of range"
    end if
    give back call row_map with ds = dataset, i = index
end function

define function row_map taking ds, i
    set out to an empty map
    repeat for each name in (item "order" of ds)
        set item name of out to (item i of (item name of (item "columns" of ds)))
    end repeat
    give back out
end function

define function harvest taking dataset
    call ensure_dataset with dataset = dataset
    set out to an empty list
    set i to 0
    repeat while i is less than (call row_count with ds = dataset)
        add (call row_map with ds = dataset, i = i) to out
        set i to i plus 1
    end repeat
    give back out
end function

define function dimensions taking dataset
also known as shape
    call ensure_dataset with dataset = dataset
    give back a map with "rows" mapped to (call row_count with ds = dataset), "columns" mapped to (the length of (item "order" of dataset))
end function

define function tally taking dataset, column
    set vals to call need_column with ds = dataset, name = column
    set freq to an empty map
    repeat for each cell in vals
        if not (call missing with value = cell) then
            if call contains with collection = freq, value = cell then
                set item cell of freq to (item cell of freq) plus 1
            otherwise
                set item cell of freq to 1
            end if
        end if
    end repeat
    give back freq
end function

# --- filtering, sorting and signatures ------------------------------------

define function matches taking cell, operator, expected
    if call missing with value = cell then
        give back false
    end if
    if call missing with value = expected then
        give back false
    end if
    if operator equals "contains" then
        if cell is text then
            require expected is text, "contains on text needs a text value"
            give back call contains with collection = cell, value = expected
        end if
        if cell is a list then
            give back call contains with collection = cell, value = expected
        end if
        fail with bad_type, "contains needs a text or list column"
    end if
    if operator equals "equals" then
        give back cell equals expected
    end if
    if operator equals "does not equal" then
        give back cell does not equal expected
    end if
    set left to call cell_kind with cell = cell
    set right to call cell_kind with cell = expected
    require left equals right, "comparison needs matching types"
    require (left equals "number") or (left equals "text"), "comparison needs numbers or text"
    if operator equals "is greater than" then
        give back cell is greater than expected
    end if
    if operator equals "is less than" then
        give back cell is less than expected
    end if
    if operator equals "is at least" then
        give back cell is at least expected
    end if
    if operator equals "is at most" then
        give back cell is at most expected
    end if
    fail with bad_type, "unknown operator"
end function

define function where taking dataset, column, operator, value
    call ensure_dataset with dataset = dataset
    set ops to a list of "equals", "does not equal", "is greater than", "is less than", "is at least", "is at most", "contains"
    require (call contains with collection = ops, value = operator), "where: unknown operator"
    set vals to call need_column with ds = dataset, name = column
    set fresh_cols to an empty map
    repeat for each name in (item "order" of dataset)
        set out to an empty list
        set i to 0
        repeat while i is less than (the length of vals)
            if call matches with cell = (item i of vals), operator = operator, expected = value then
                add (item i of (item name of (item "columns" of dataset))) to out
            end if
            set i to i plus 1
        end repeat
        set item name of fresh_cols to out
    end repeat
    give back call fresh_dataset with cols = fresh_cols, seq = (item "order" of dataset), src = (call source_of with ds = dataset)
end function

define function filter taking dataset, predicate
    call ensure_dataset with dataset = dataset
    require not (predicate is nothing), "filter: predicate must be a function value"
    set fresh_cols to an empty map
    repeat for each name in (item "order" of dataset)
        set item name of fresh_cols to an empty list
    end repeat
    set i to 0
    repeat while i is less than (call row_count with ds = dataset)
        set onerow to call row_map with ds = dataset, i = i
        if call apply with fn = predicate, args = (a list of onerow) then
            repeat for each name in (item "order" of dataset)
                add (item name of onerow) to (item name of fresh_cols)
            end repeat
        end if
        set i to i plus 1
    end repeat
    give back call fresh_dataset with cols = fresh_cols, seq = (item "order" of dataset), src = (call source_of with ds = dataset)
end function

define function sort_indices taking vals, descending
    set idx to an empty list
    set i to 0
    repeat while i is less than (the length of vals)
        add i to idx
        set i to i plus 1
    end repeat
    set j to 1
    repeat while j is less than (the length of idx)
        set current to item j of idx
        set keyval to item current of vals
        set k to j minus 1
        repeat while k is at least 0
            set other to item k of idx
            set otherval to item other of vals
            set move to false
            if call missing with value = keyval then
                set move to false
            otherwise if call missing with value = otherval then
                set move to true
            otherwise if descending then
                set move to keyval is greater than otherval
            otherwise
                set move to keyval is less than otherval
            end if
            if not move then
                stop the loop
            end if
            set item (k plus 1) of idx to other
            set k to k minus 1
        end repeat
        set item (k plus 1) of idx to current
        set j to j plus 1
    end repeat
    give back idx
end function

define function order_rows taking dataset, column, descending
    set vals to call need_column with ds = dataset, name = column
    require (descending equals true) or (descending equals false), "order: descending must be a boolean"
    set first to nothing
    repeat for each cell in vals
        if not (call missing with value = cell) then
            set celltype to call cell_kind with cell = cell
            require (celltype equals "number") or (celltype equals "text"), "order: sort keys must be numbers or text"
            if first is nothing then
                set first to celltype
            otherwise
                require celltype equals first, "order: mixed sort key types"
            end if
        end if
    end repeat
    set idx to call sort_indices with vals = vals, descending = descending
    set fresh_cols to an empty map
    repeat for each name in (item "order" of dataset)
        set old to item name of (item "columns" of dataset)
        set out to an empty list
        repeat for each pos in idx
            add (item pos of old) to out
        end repeat
        set item name of fresh_cols to out
    end repeat
    give back call fresh_dataset with cols = fresh_cols, seq = (item "order" of dataset), src = (call source_of with ds = dataset)
end function

# --- reductions -----------------------------------------------------------

define function reduce_values taking vals, how
    set methods to a list of "sum", "mean", "min", "max", "count"
    if not (call contains with collection = methods, value = how) then
        fail with bad_type, "aggregate: unknown method"
    end if
    set total to 0
    set seen to 0
    set best to nothing
    repeat for each cell in vals
        if not (call missing with value = cell) then
            if how equals "count" then
                set total to total plus 1
            otherwise
                require cell is a number, "aggregate: values must be numbers"
                set total to total plus cell
                if seen equals 0 then
                    set best to cell
                otherwise if how equals "min" then
                    if cell is less than best then
                        set best to cell
                    end if
                otherwise if how equals "max" then
                    if cell is greater than best then
                        set best to cell
                    end if
                end if
            end if
            set seen to seen plus 1
        end if
    end repeat
    if how equals "sum" then
        give back total
    end if
    if how equals "count" then
        give back total
    end if
    if seen equals 0 then
        give back nothing
    end if
    if how equals "mean" then
        give back total divided by seen
    end if
    give back best
end function

define function aggregate taking dataset, column, how
    set vals to call need_column with ds = dataset, name = column
    give back call reduce_values with vals = vals, how = how
end function

define function group taking dataset, key, column, how
    call ensure_dataset with dataset = dataset
    set cols to item "columns" of dataset
    call ensure_names with name_list = (a list of key, column), cols = cols
    set keyvals to item key of cols
    set vals to item column of cols
    call check_key_values with vals = keyvals
    set buckets to an empty map
    set originals to an empty map
    set keyseq to an empty list
    set i to 0
    repeat while i is less than (the length of keyvals)
        set k to item i of keyvals
        if not (call missing with value = k) then
            set tag to call key_tag with cell = k
            if not (call contains with collection = buckets, value = tag) then
                set item tag of buckets to an empty list
                set item tag of originals to k
                add tag to keyseq
            end if
            add (item i of vals) to (item tag of buckets)
        end if
        set i to i plus 1
    end repeat
    set out to an empty map
    repeat for each tag in keyseq
        set item (item tag of originals) of out to (call reduce_values with vals = (item tag of buckets), how = how)
    end repeat
    give back out
end function

define function distinct taking dataset, names
    call ensure_dataset with dataset = dataset
    set cols to item "columns" of dataset
    call ensure_names with name_list = names, cols = cols
    set signatures to an empty list
    set keep to an empty list
    set i to 0
    repeat while i is less than (call row_count with ds = dataset)
        set onerow to call row_map with ds = dataset, i = i
        set signature to call row_signature with onerow = onerow, names = names
        if not (call contains with collection = signatures, value = signature) then
            add signature to signatures
            add onerow to keep
        end if
        set i to i plus 1
    end repeat
    give back call from_records with rowmaps = keep, seq = (item "order" of dataset), src = (call source_of with ds = dataset)
end function

define function row_signature taking onerow, names
    set parts to an empty list
    repeat for each name in names
        set cell to item name of onerow
        if call missing with value = cell then
            add "m:" to parts
        otherwise if cell is a number then
            add "n:" plus (call text of with value = cell) to parts
        otherwise if cell is text then
            add "t:" plus cell to parts
        otherwise
            add "o:" plus (call text of with value = cell) to parts
        end if
    end repeat
    give back call join with items = parts, separator = "\t"
end function

define function from_records taking rowmaps, seq, src
    set fresh_cols to an empty map
    repeat for each name in seq
        set out to an empty list
        repeat for each onerow in rowmaps
            require (call contains with collection = onerow, value = name), "from_records: missing key"
            add (item name of onerow) to out
        end repeat
        set item name of fresh_cols to out
    end repeat
    give back call fresh_dataset with cols = fresh_cols, seq = seq, src = src
end function

# --- missing values and conversion ----------------------------------------

define function fill taking dataset, column, value
    set vals to call need_column with ds = dataset, name = column
    require not (call missing with value = value), "fill: the fill value cannot be missing"
    set first to nothing
    repeat for each cell in vals
        if not (call missing with value = cell) then
            set first to call cell_kind with cell = cell
            stop the loop
        end if
    end repeat
    if not (first is nothing) then
        require (call cell_kind with cell = value) equals first, "fill: value type must match the column"
    end if
    set fresh_cols to an empty map
    repeat for each name in (item "order" of dataset)
        if name equals column then
            set out to an empty list
            repeat for each cell in vals
                if call missing with value = cell then
                    add value to out
                otherwise
                    add cell to out
                end if
            end repeat
            set item name of fresh_cols to out
        otherwise
            set out to an empty list
            repeat for each cell in (item name of (item "columns" of dataset))
                add cell to out
            end repeat
            set item name of fresh_cols to out
        end if
    end repeat
    give back call fresh_dataset with cols = fresh_cols, seq = (item "order" of dataset), src = (call source_of with ds = dataset)
end function

define function omit taking dataset, names
    call ensure_dataset with dataset = dataset
    set cols to item "columns" of dataset
    call ensure_names with name_list = names, cols = cols
    set keep to an empty list
    set i to 0
    repeat while i is less than (call row_count with ds = dataset)
        set keeprow to true
        repeat for each name in names
            if call missing with value = (item i of (item name of cols)) then
                set keeprow to false
            end if
        end repeat
        if keeprow then
            add (call row_map with ds = dataset, i = i) to keep
        end if
        set i to i plus 1
    end repeat
    give back call from_records with rowmaps = keep, seq = (item "order" of dataset), src = (call source_of with ds = dataset)
end function

define function numeric_text taking txt
    set t to call trim with text = txt
    if t equals "" then
        give back false
    end if
    if (call uppercase of with text = t) equals "NAN" then
        give back true
    end if
    set n to the length of t
    set start to 0
    if ((item 0 of t) equals "+") or ((item 0 of t) equals "-") then
        set start to 1
    end if
    if start is at least n then
        give back false
    end if
    set digits to 0
    set dots to 0
    set i to start
    repeat while i is less than n
        set ch to item i of t
        if ch equals "." then
            set dots to dots plus 1
            if dots is greater than 1 then
                give back false
            end if
        otherwise if call contains with collection = "0123456789", value = ch then
            set digits to digits plus 1
        otherwise
            give back false
        end if
        set i to i plus 1
    end repeat
    give back digits is greater than 0
end function

define function convert taking dataset, column, as_kind
    set vals to call need_column with ds = dataset, name = column
    require (as_kind equals "number") or (as_kind equals "text"), "convert: kind must be number or text"
    set out to an empty list
    repeat for each cell in vals
        if call missing with value = cell then
            add nothing to out
        otherwise if as_kind equals "text" then
            add (call text of with value = cell) to out
        otherwise if cell is a number then
            add cell to out
        otherwise if cell is text then
            if (call uppercase of with text = (call trim with text = cell)) equals "NAN" then
                add nothing to out
            otherwise if call numeric_text with txt = cell then
                add (call to number with text = cell) to out
            otherwise
                fail with bad_conversion, "value is not a number"
            end if
        otherwise
            fail with bad_conversion, "value cannot be converted to a number"
        end if
    end repeat
    set fresh_cols to an empty map
    repeat for each name in (item "order" of dataset)
        if name equals column then
            set item name of fresh_cols to out
        otherwise
            set old to an empty list
            repeat for each cell in (item name of (item "columns" of dataset))
                add cell to old
            end repeat
            set item name of fresh_cols to old
        end if
    end repeat
    give back call fresh_dataset with cols = fresh_cols, seq = (item "order" of dataset), src = (call source_of with ds = dataset)
end function

# --- 1-D math -------------------------------------------------------------

define function count taking values
    require values is a list, "count: values must be a list"
    set total to 0
    repeat for each cell in values
        if not (call missing with value = cell) then
            set total to total plus 1
        end if
    end repeat
    give back total
end function

define function dot taking left, right
    require left is a list, "dot: left must be a list"
    require right is a list, "dot: right must be a list"
    require (the length of left) equals (the length of right), "dot: lengths must match"
    set total to 0
    set i to 0
    repeat while i is less than (the length of left)
        set a to item i of left
        set b to item i of right
        if (call missing with value = a) or (call missing with value = b) then
            give back nothing
        end if
        require (a is a number) and (b is a number), "dot: values must be numbers"
        set total to total plus (a times b)
        set i to i plus 1
    end repeat
    give back total
end function

define function scale taking values, factor
    require values is a list, "scale: values must be a list"
    require factor is a number, "scale: factor must be a number"
    set out to an empty list
    repeat for each cell in values
        if call missing with value = cell then
            add nothing to out
        otherwise
            require cell is a number, "scale: values must be numbers"
            add (cell times factor) to out
        end if
    end repeat
    give back out
end function

define function combine taking left, right, operation
    require left is a list, "combine: left must be a list"
    require right is a list, "combine: right must be a list"
    require (the length of left) equals (the length of right), "combine: lengths must match"
    set ops to a list of "add", "subtract", "multiply", "divided by"
    require (call contains with collection = ops, value = operation), "combine: unknown operation"
    set out to an empty list
    set i to 0
    repeat while i is less than (the length of left)
        set a to item i of left
        set b to item i of right
        if (call missing with value = a) or (call missing with value = b) then
            add nothing to out
        otherwise
            require (a is a number) and (b is a number), "combine: values must be numbers"
            if operation equals "add" then
                add (a plus b) to out
            otherwise if operation equals "subtract" then
                add (a minus b) to out
            otherwise if operation equals "multiply" then
                add (a times b) to out
            otherwise
                add (a divided by b) to out
            end if
        end if
        set i to i plus 1
    end repeat
    give back out
end function

# --- summaries ------------------------------------------------------------

define function column_kind taking vals
    set kinds to an empty list
    repeat for each cell in vals
        set celltype to call cell_kind with cell = cell
        if not (call contains with collection = kinds, value = celltype) then
            if not (celltype equals "empty") then
                add celltype to kinds
            end if
        end if
    end repeat
    if (the length of kinds) equals 0 then
        give back "empty"
    end if
    if (the length of kinds) equals 1 then
        give back item 0 of kinds
    end if
    give back "mixed"
end function

define function column_missing taking vals
    set total to 0
    repeat for each cell in vals
        if call missing with value = cell then
            set total to total plus 1
        end if
    end repeat
    give back total
end function

define function overview taking dataset
    call ensure_dataset with dataset = dataset
    set cols to item "columns" of dataset
    set seq to item "order" of dataset
    set report to a map with "kind" mapped to "dataset", "rows" mapped to (call row_count with ds = dataset), "columns" mapped to (the length of seq), "missing" mapped to 0
    set missing_total to 0
    repeat for each name in seq
        set vals to item name of cols
        set n to call column_missing with vals = vals
        set missing_total to missing_total plus n
        set info to a map with "kind" mapped to (call column_kind with vals = vals), "missing" mapped to n
        set item name of report to info
    end repeat
    set item "missing" of report to missing_total
    give back report
end function

define function describe taking dataset, columns
    call ensure_dataset with dataset = dataset
    set seq to columns
    if columns is nothing then
        set seq to item "order" of dataset
    end if
    call ensure_names with name_list = seq, cols = (item "columns" of dataset)
    set report to an empty map
    repeat for each name in seq
        set vals to item name of (item "columns" of dataset)
        if (call column_kind with vals = vals) equals "number" then
            set stats to a map with "count" mapped to (call reduce_values with vals = vals, how = "count"), "missing" mapped to (call column_missing with vals = vals), "min" mapped to (call reduce_values with vals = vals, how = "min"), "max" mapped to (call reduce_values with vals = vals, how = "max"), "mean" mapped to (call reduce_values with vals = vals, how = "mean")
            set item name of report to stats
        end if
    end repeat
    give back report
end function

# --- reshaping and joining -------------------------------------------------

define function transpose taking dataset
    call ensure_dataset with dataset = dataset
    set cols to item "columns" of dataset
    set seq to item "order" of dataset
    set height to call row_count with ds = dataset
    set fresh_cols to an empty map
    set name_col to an empty list
    repeat for each name in seq
        add name to name_col
    end repeat
    set item "name" of fresh_cols to name_col
    set fresh_seq to a list of "name"
    set i to 0
    repeat while i is less than height
        set new_name to call text of with value = i
        add new_name to fresh_seq
        set out to an empty list
        repeat for each name in seq
            set cell to item i of (item name of cols)
            if not (call missing with value = cell) then
                require cell is a number, "transpose: only numeric datasets can be transposed"
            end if
            add cell to out
        end repeat
        set item new_name of fresh_cols to out
        set i to i plus 1
    end repeat
    give back call fresh_dataset with cols = fresh_cols, seq = fresh_seq, src = (call source_of with ds = dataset)
end function

define function append taking top, bottom
    call ensure_dataset with dataset = top
    call ensure_dataset with dataset = bottom
    set a to item "order" of top
    set b to item "order" of bottom
    require (the length of a) equals (the length of b), "append: column sets must match"
    set rowmaps to call harvest with dataset = top
    repeat for each onerow in (call harvest with dataset = bottom)
        add onerow to rowmaps
    end repeat
    give back call from_records with rowmaps = rowmaps, seq = a, src = (call source_of with ds = top)
end function

define function rename taking dataset, mapping
    call ensure_dataset with dataset = dataset
    require mapping is a map, "rename: mapping must be a map"
    set seq to an empty list
    repeat for each name in (item "order" of dataset)
        set new_name to name
        if call contains with collection = mapping, value = name then
            set new_name to item name of mapping
        end if
        require new_name is text, "rename: new names must be text"
        require not (call contains with collection = seq, value = new_name), "rename: duplicate new name"
        add new_name to seq
    end repeat
    set fresh_cols to an empty map
    repeat for each name in (item "order" of dataset)
        set new_name to name
        if call contains with collection = mapping, value = name then
            set new_name to item name of mapping
        end if
        set out to an empty list
        repeat for each cell in (item name of (item "columns" of dataset))
            add cell to out
        end repeat
        set item new_name of fresh_cols to out
    end repeat
    give back call fresh_dataset with cols = fresh_cols, seq = seq, src = (call source_of with ds = dataset)
end function

define function attach taking left, right, key, how
    call ensure_dataset with dataset = left
    call ensure_dataset with dataset = right
    require (how equals "inner") or (how equals "left"), "attach: how must be inner or left"
    set lcols to item "columns" of left
    set rcols to item "columns" of right
    require (call contains with collection = lcols, value = key), "attach: unknown key in left"
    require (call contains with collection = rcols, value = key), "attach: unknown key in right"
    set lkeys to item key of lcols
    set rkeys to item key of rcols
    call check_key_values with vals = lkeys
    call check_key_values with vals = rkeys
    set left_kind to call first_key_kind with vals = lkeys
    set right_kind to call first_key_kind with vals = rkeys
    if (the length of left_kind) is greater than 0 then
        if (the length of right_kind) is greater than 0 then
            if not (left_kind equals right_kind) then
                fail with bad_join_key, "left and right keys have different types"
            end if
        end if
    end if
    set right_names to an empty list
    repeat for each name in (item "order" of right)
        if not (name equals key) then
            require not (call contains with collection = lcols, value = name), "attach: duplicate non-key column"
            add name to right_names
        end if
    end repeat
    set buckets to an empty map
    set i to 0
    repeat while i is less than (the length of rkeys)
        set tag to call key_tag with cell = (item i of rkeys)
        if not (call contains with collection = buckets, value = tag) then
            set item tag of buckets to an empty list
        end if
        set onerow to call row_map with ds = right, i = i
        add onerow to (item tag of buckets)
        set i to i plus 1
    end repeat
    set out_names to an empty list
    repeat for each name in (item "order" of left)
        add name to out_names
    end repeat
    repeat for each name in right_names
        add name to out_names
    end repeat
    set out_rows to an empty list
    set i to 0
    repeat while i is less than (the length of lkeys)
        set tag to call key_tag with cell = (item i of lkeys)
        set lrow to call row_map with ds = left, i = i
        if call contains with collection = buckets, value = tag then
            repeat for each rrow in (item tag of buckets)
                set merged to an empty map
                repeat for each name in out_names
                    if call contains with collection = lrow, value = name then
                        set item name of merged to item name of lrow
                    otherwise
                        set item name of merged to item name of rrow
                    end if
                end repeat
                add merged to out_rows
            end repeat
        otherwise if how equals "left" then
            set merged to an empty map
            repeat for each name in out_names
                if call contains with collection = lrow, value = name then
                    set item name of merged to item name of lrow
                otherwise
                    set item name of merged to nothing
                end if
            end repeat
            add merged to out_rows
        end if
        set i to i plus 1
    end repeat
    give back call from_records with rowmaps = out_rows, seq = out_names, src = (call source_of with ds = left)
end function

# The labels `order` and `column` are also public function names.  Binding
# those exports as values keeps every call label identical to the design while
# avoiding a local binding that would shadow a function of the same name.
set column to column_from_dataset
set order to order_rows
