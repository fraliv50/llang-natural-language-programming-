define function average taking values
    set total to 0
    repeat for each v in values
        set total to total plus v
    end repeat
    return total divided by (the length of values)
end function
define function classify taking n
    if n is at least 90 then
        return "A"
    otherwise if n is at least 80 then
        return "B"
    otherwise
        return "C"
    end if
end function
set xs to a list of 1, 2, 3
show call average with values = xs
show call classify with n = 91
show call classify with n = 85
show call classify with n = 40
