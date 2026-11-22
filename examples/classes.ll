# The minimal class/record system: declared fields plus explicit methods.
# Instances are ordinary mutable values; `this` is an explicit first parameter.

define class Point taking x, y
define method move taking this, dx, dy
    set item "x" of this to (item "x" of this) plus dx
    set item "y" of this to (item "y" of this) plus dy
    give back this
end method
define method render taking this
    give back (call text of with value = (item "x" of this)) plus ", " plus (call text of with value = (item "y" of this))
end method
end class

set p to call new Point with x = 1, y = 2
show p                                  # Point(x: 1, y: 2)
show ask p to render                    # 1, 2

ask p to move with dx = 3, dy = 4
show ask p to render                    # 4, 6

# Aliasing: `alias` is the very same instance, so both names see the change.
set alias to p
ask alias to move with dx = 1, dy = 1
show ask p to render                    # 5, 7
show item "x" of p                      # 5
