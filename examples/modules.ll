# Modules: native llang libraries and an explicitly labeled foreign bridge.

use the math module
use the text module
use the lists module
use the foreign json module
use the foreign math module as hostmath

show "--- native modules ---"
show call sqrt from math with value = 81
show (call rounded to places with value = (call sqrt from math with value = 2), places = 5)
show call clamp from math with value = 120, low = 0, high = 100
show call average from math with items = a list of 2, 4, 6
show item "pi" of math

show call reverse_text from text with value ="llang"
show call initials from text with value ="grace hopper"
show call is_palindrome from text with value ="Level"

show call unique from lists with items = a list of 1, 2, 2, 3, 1
show call flatten from lists with groups = a list of (a list of 1, 2), (a list of 3, 4)
show call rotate from lists with items = (a list of 1, 2, 3, 4), places = 2

show "--- foreign modules (host interop, explicitly marked) ---"
set payload to a map with "name" mapped to "Ada", "score" mapped to 91
set encoded to call dumps from json with value = payload
show encoded
show call loads from json with text = encoded
show (call rounded to places with value = (call sqrt from hostmath with value = 2), places = 5)
show item "pi" of hostmath
