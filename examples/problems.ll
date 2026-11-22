# Problems (exceptions) and the 'expect' statement.

define function lookup taking scores, name
also called find_score
    set present to call contains with collection = (call keys of with collection = scores), value = name
    if present then
        give back item name of scores
    end if
    fail with missing_score, "no score recorded for that name"
end function

set scores to a map with "Ada" mapped to 91, "Grace" mapped to 98

display call find_score with scores = scores, name = "Ada"

expect
    show call lookup with scores = scores, name = "Nobody"
if a problem of kind missing_score occurs then
    show "handled: unknown student"
if nothing went wrong then
    show "unexpected success"
always
    show "lookup attempt finished"
end expect

expect
    show call lookup with scores = scores, name = "Grace"
if a problem of kind missing_score occurs then
    show "should not happen"
if nothing went wrong then
    show "found Grace"
end expect

show "done"
