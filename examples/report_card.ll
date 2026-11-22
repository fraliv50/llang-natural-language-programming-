# ---------------------------------------------------------------------------
# The Class Report Card — flagship program for llang.
#
# It reads like structured English, does real work, and checks its own result.
# Indentation is decoration only: every block is closed by an explicit 'end'.
# ---------------------------------------------------------------------------

# --- arithmetic helper ----------------------------------------------------
define a function average taking total, count
    give back total divided by count
end function

# --- branching helper -----------------------------------------------------
define a function grade_for taking score
    if score is at least 90 then
        give back "A"
    otherwise if score is at least 80 then
        give back "B"
    otherwise if score is at least 70 then
        give back "C"
    otherwise if score is at least 60 then
        give back "D"
    otherwise
        give back "F"
    end if
end function

# --- lookup helper: three names, one implementation -----------------------
define a function marks_for taking student, book
also known as marks_of, scores_for
    give back item student of book
end function

# --- the workhorse: validate, accumulate, divide --------------------------
define a function average_for taking student, book
also called mean_for, average_of_student
    set scores to call marks_of with student = student, book = book
    require (the length of scores) is greater than 0, "no marks recorded for that student"
    set total to 0
    set count to 0
    repeat for each score in scores
        # Parentheses are required: there is no operator precedence.
        require (score is at least 0) and (score is at most 100), "a score must run from 0 to 100"
        set total to total plus score
        set count to count plus 1
    end repeat
    give back call average with total = total, count = count
end function

# --- the data -------------------------------------------------------------
set roster to a list of "Ada", "Grace", "Linus", "Barbara", "Dieter", "Hana"
set marks to an empty map
set item "Ada" of marks to a list of 92, 88, 95, 91
set item "Grace" of marks to a list of 99, 97, 100
set item "Linus" of marks to a list of 71, 85
set item "Barbara" of marks to a list of 76, 84, 80
set item "Dieter" of marks to a list of 55, 62
set item "Hana" of marks to a list of 64, 68

# --- the report -----------------------------------------------------------
set class_total to 0
set class_count to 0
set top_average to 0 minus 1
set top_student to nothing

repeat for each student in roster
    set mean to call mean_for with student = student, book = marks
    set letter to call grade_for with score = mean
    set rounded_mean to call rounded to places with value = mean, places = 1
    display student plus ": " plus (call text of with value = rounded_mean) plus " (" plus letter plus ")"
    set class_total to class_total plus mean
    set class_count to class_count plus 1
    if mean is greater than top_average then
        set top_average to mean
        set top_student to student
    end if
end repeat

set class_average to call average with total = class_total, count = class_count
set rounded_class to call rounded to places with value = class_average, places = 1
show "Class mean of student means: " plus (call text of with value = rounded_class)
print "Top student: " plus top_student

# --- a problem that is expected to happen --------------------------------
expect
    show call scores_for with student = "Nobody", book = marks
if a problem of kind missing_key occurs then
    print "Handled: no marks were recorded for that name"
if nothing went wrong then
    print "Unexpected: the name was found"
end expect

# --- self-checks: the program proves its own result -----------------------
require class_count equals (the length of roster), "every student was reported once"
require (top_average is at least 0) and (top_average is at most 100), "the top average is a valid score"
show "All checks passed."
