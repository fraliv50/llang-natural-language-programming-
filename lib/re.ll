# A native, backtracking regular-expression engine written entirely in llang.
#
# Grounding: docs/research/regex-semantics.md. No host regex call is used.
#
# Supported v1 subset: literals, concatenation, ".", greedy and lazy "*", "+",
# "?", character classes (ranges, negation, escapes, shorthands), anchors
# "^", "$", "\\A", "\\Z", "\\b", "\\B", groups "( ... )" and "(?: ... )",
# alternation "|", backreferences "\\1".."\\9", standard character escapes,
# "\\d \\D \\w \\W \\s \\S", and flags ("ignore case", "multiline",
# "dot all", "verbose", "ascii"). Every match map has the documented five
# keys; "named" is always empty because named groups are out of scope.
#
# Deliberately omitted (they raise invalid_pattern instead of mis-matching):
# counted repetition {m,n}, named groups (?P<...>)/(?P=name), lookarounds,
# atomic/possessive groups, inline/scoped flags, conditional groups, comments,
# hexadecimal/unicode/octal escapes, bytes patterns, and any other extension.
# Unknown flag texts raise invalid_flag; wrong argument types raise
# bad_argument.
#
# Naming note: llang function names are single words, so the phrase "find all"
# is exported as find_all (alias findall); "full match" is full_match.
# Optional arguments use parallel exports: replace_count, split_limit, and
# *_flags variants take flag lists (llang user functions have no default
# labels), e.g. search_flags, find_all_flags, replace_count_flags,
# split_limit_flags, matches_flags, full_match_flags.
#
# A step budget (200000 match-node calls per search position) guards against
# the catastrophic backtracking that CPython leaves unbounded.

set bs_char to "\\"
set lf_char to "\n"
set tab_char to "\t"
set cr_char to "\r"
set ff_char to ""
set vt_char to ""
set bel_char to ""
set bh_char to ""

set digits_ascii to "0123456789"
set letters_ascii to "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
set word_ascii to "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
set space_ascii to " \t\n\r" plus ff_char plus vt_char
set special_escape to "()[]{}?*+-|^$\\.&~# \t\n\r" plus vt_char plus ff_char

# Unicode range tables: pairs of endpoint characters, generated from Python's
# str.isdecimal / str.isspace / (str.isalnum or "_") so \\d, \\s and \\w match
# exactly the same code points as the CPython engine.
set dec_ranges to "09٠٩۰۹߀߉०९০৯੦੯૦૯୦୯௦௯౦౯೦೯൦൯෦෯๐๙໐໙༠༩၀၉႐႙០៩᠐᠙᥆᥏᧐᧙᪀᪉᪐᪙᭐᭙᮰᮹᱀᱉᱐᱙꘠꘩꣐꣙꤀꤉꧐꧙꧰꧹꩐꩙꯰꯹０９𐒠𐒩𐴰𐴹𑁦𑁯𑃰𑃹𑄶𑄿𑇐𑇙𑋰𑋹𑑐𑑙𑓐𑓙𑙐𑙙𑛀𑛉𑜰𑜹𑣠𑣩𑥐𑥙𑱐𑱙𑵐𑵙𑶠𑶩𖩠𖩩𖫀𖫉𖭐𖭙𝟎𝟿𞅀𞅉𞋰𞋹𞥐𞥙🯰🯹"
set space_ranges to "\t\r             　　"
set word_ranges to "09AZ__azªª²³µµ¹º¼¾ÀÖØöøˁˆˑˠˤˬˬˮˮͰʹͶͷͺͽͿͿΆΆΈΊΌΌΎΡΣϵϷҁҊԯԱՖՙՙՠֈאתׯײؠي٠٩ٮٯٱۓەەۥۦۮۼۿۿܐܐܒܯݍޥޱޱ߀ߪߴߵߺߺࠀࠕࠚࠚࠤࠤࠨࠨࡀࡘࡠࡪࡰࢇࢉࢎࢠࣉऄहऽऽॐॐक़ॡ०९ॱঀঅঌএঐওনপরললশহঽঽৎৎড়ঢ়য়ৡ০ৱ৴৹ৼৼਅਊਏਐਓਨਪਰਲਲ਼ਵਸ਼ਸਹਖ਼ੜਫ਼ਫ਼੦੯ੲੴઅઍએઑઓનપરલળવહઽઽૐૐૠૡ૦૯ૹૹଅଌଏଐଓନପରଲଳଵହଽଽଡ଼ଢ଼ୟୡ୦୯ୱ୷ஃஃஅஊஎஐஒகஙசஜஜஞடணதநபமஹௐௐ௦௲అఌఎఐఒనపహఽఽౘౚౝౝౠౡ౦౯౸౾ಀಀಅಌಎಐಒನಪಳವಹಽಽೝೞೠೡ೦೯ೱೲഄഌഎഐഒഺഽഽൎൎൔൖ൘ൡ൦൸ൺൿඅඖකනඳරලලවෆ෦෯กะาำเๆ๐๙ກຂຄຄຆຊຌຣລລວະາຳຽຽເໄໆໆ໐໙ໜໟༀༀ༠༳ཀཇཉཬྈྌကဪဿ၉ၐၕၚၝၡၡၥၦၮၰၵႁႎႎ႐႙ႠჅჇჇჍჍაჺჼቈቊቍቐቖቘቘቚቝበኈኊኍነኰኲኵኸኾዀዀዂዅወዖዘጐጒጕጘፚ፩፼ᎀᎏᎠᏵᏸᏽᐁᙬᙯᙿᚁᚚᚠᛪᛮᛸᜀᜑᜟᜱᝀᝑᝠᝬᝮᝰកឳៗៗៜៜ០៩៰៹᠐᠙ᠠᡸᢀᢄᢇᢨᢪᢪᢰᣵᤀᤞ᥆ᥭᥰᥴᦀᦫᦰᧉ᧐᧚ᨀᨖᨠᩔ᪀᪉᪐᪙ᪧᪧᬅᬳᭅᭌ᭐᭙ᮃᮠᮮᯥᰀᰣ᱀᱉ᱍᱽᲀᲈᲐᲺᲽᲿᳩᳬᳮᳳᳵᳶᳺᳺᴀᶿḀἕἘἝἠὅὈὍὐὗὙὙὛὛὝὝὟώᾀᾴᾶᾼιιῂῄῆῌῐΐῖΊῠῬῲῴῶῼ⁰ⁱ⁴⁹ⁿ₉ₐₜℂℂℇℇℊℓℕℕℙℝℤℤΩΩℨℨKℭℯℹℼℿⅅⅉⅎⅎ⅐↉①⒛⓪⓿❶➓ⰀⳤⳫⳮⳲⳳ⳽⳽ⴀⴥⴧⴧⴭⴭⴰⵧⵯⵯⶀⶖⶠⶦⶨⶮⶰⶶⶸⶾⷀⷆⷈⷎⷐⷖⷘⷞⸯⸯ々〇〡〩〱〵〸〼ぁゖゝゟァヺーヿㄅㄯㄱㆎ㆒㆕ㆠㆿㇰㇿ㈠㈩㉈㉏㉑㉟㊀㊉㊱㊿㐀䶿一ꒌꓐꓽꔀꘌꘐꘫꙀꙮꙿꚝꚠꛯꜗꜟꜢꞈꞋꟊꟐꟑꟓꟓꟕꟙꟲꠁꠃꠅꠇꠊꠌꠢ꠰꠵ꡀꡳꢂꢳ꣐꣙ꣲꣷꣻꣻꣽꣾ꤀ꤥꤰꥆꥠꥼꦄꦲꧏ꧙ꧠꧤꧦꧾꨀꨨꩀꩂꩄꩋ꩐꩙ꩠꩶꩺꩺꩾꪯꪱꪱꪵꪶꪹꪽꫀꫀꫂꫂꫛꫝꫠꫪꫲꫴꬁꬆꬉꬎꬑꬖꬠꬦꬨꬮꬰꭚꭜꭩꭰꯢ꯰꯹가힣ힰퟆퟋퟻ豈舘並龎ﬀﬆﬓﬗיִיִײַﬨשׁזּטּלּמּמּנּסּףּפּצּﮱﯓﴽﵐﶏﶒﷇﷰﷻﹰﹴﹶﻼ０９ＡＺａｚｦﾾￂￇￊￏￒￗￚￜ𐀀𐀋𐀍𐀦𐀨𐀺𐀼𐀽𐀿𐁍𐁐𐁝𐂀𐃺𐄇𐄳𐅀𐅸𐆊𐆋𐊀𐊜𐊠𐋐𐋡𐋻𐌀𐌣𐌭𐍊𐍐𐍵𐎀𐎝𐎠𐏃𐏈𐏏𐏑𐏕𐐀𐒝𐒠𐒩𐒰𐓓𐓘𐓻𐔀𐔧𐔰𐕣𐕰𐕺𐕼𐖊𐖌𐖒𐖔𐖕𐖗𐖡𐖣𐖱𐖳𐖹𐖻𐖼𐘀𐜶𐝀𐝕𐝠𐝧𐞀𐞅𐞇𐞰𐞲𐞺𐠀𐠅𐠈𐠈𐠊𐠵𐠷𐠸𐠼𐠼𐠿𐡕𐡘𐡶𐡹𐢞𐢧𐢯𐣠𐣲𐣴𐣵𐣻𐤛𐤠𐤹𐦀𐦷𐦼𐧏𐧒𐨀𐨐𐨓𐨕𐨗𐨙𐨵𐩀𐩈𐩠𐩾𐪀𐪟𐫀𐫇𐫉𐫤𐫫𐫯𐬀𐬵𐭀𐭕𐭘𐭲𐭸𐮑𐮩𐮯𐰀𐱈𐲀𐲲𐳀𐳲𐳺𐴣𐴰𐴹𐹠𐹾𐺀𐺩𐺰𐺱𐼀𐼧𐼰𐽅𐽑𐽔𐽰𐾁𐾰𐿋𐿠𐿶𑀃𑀷𑁒𑁯𑁱𑁲𑁵𑁵𑂃𑂯𑃐𑃨𑃰𑃹𑄃𑄦𑄶𑄿𑅄𑅄𑅇𑅇𑅐𑅲𑅶𑅶𑆃𑆲𑇁𑇄𑇐𑇚𑇜𑇜𑇡𑇴𑈀𑈑𑈓𑈫𑊀𑊆𑊈𑊈𑊊𑊍𑊏𑊝𑊟𑊨𑊰𑋞𑋰𑋹𑌅𑌌𑌏𑌐𑌓𑌨𑌪𑌰𑌲𑌳𑌵𑌹𑌽𑌽𑍐𑍐𑍝𑍡𑐀𑐴𑑇𑑊𑑐𑑙𑑟𑑡𑒀𑒯𑓄𑓅𑓇𑓇𑓐𑓙𑖀𑖮𑗘𑗛𑘀𑘯𑙄𑙄𑙐𑙙𑚀𑚪𑚸𑚸𑛀𑛉𑜀𑜚𑜰𑜻𑝀𑝆𑠀𑠫𑢠𑣲𑣿𑤆𑤉𑤉𑤌𑤓𑤕𑤖𑤘𑤯𑤿𑤿𑥁𑥁𑥐𑥙𑦠𑦧𑦪𑧐𑧡𑧡𑧣𑧣𑨀𑨀𑨋𑨲𑨺𑨺𑩐𑩐𑩜𑪉𑪝𑪝𑪰𑫸𑰀𑰈𑰊𑰮𑱀𑱀𑱐𑱬𑱲𑲏𑴀𑴆𑴈𑴉𑴋𑴰𑵆𑵆𑵐𑵙𑵠𑵥𑵧𑵨𑵪𑶉𑶘𑶘𑶠𑶩𑻠𑻲𑾰𑾰𑿀𑿔𒀀𒎙𒐀𒑮𒒀𒕃𒾐𒿰𓀀𓐮𔐀𔙆𖠀𖨸𖩀𖩞𖩠𖩩𖩰𖪾𖫀𖫉𖫐𖫭𖬀𖬯𖭀𖭃𖭐𖭙𖭛𖭡𖭣𖭷𖭽𖮏𖹀𖺖𖼀𖽊𖽐𖽐𖾓𖾟𖿠𖿡𖿣𖿣𗀀𘟷𘠀𘳕𘴀𘴈𚿰𚿳𚿵𚿻𚿽𚿾𛀀𛄢𛅐𛅒𛅤𛅧𛅰𛋻𛰀𛱪𛱰𛱼𛲀𛲈𛲐𛲙𝋠𝋳𝍠𝍸𝐀𝑔𝑖𝒜𝒞𝒟𝒢𝒢𝒥𝒦𝒩𝒬𝒮𝒹𝒻𝒻𝒽𝓃𝓅𝔅𝔇𝔊𝔍𝔔𝔖𝔜𝔞𝔹𝔻𝔾𝕀𝕄𝕆𝕆𝕊𝕐𝕒𝚥𝚨𝛀𝛂𝛚𝛜𝛺𝛼𝜔𝜖𝜴𝜶𝝎𝝐𝝮𝝰𝞈𝞊𝞨𝞪𝟂𝟄𝟋𝟎𝟿𝼀𝼞𞄀𞄬𞄷𞄽𞅀𞅉𞅎𞅎𞊐𞊭𞋀𞋫𞋰𞋹𞟠𞟦𞟨𞟫𞟭𞟮𞟰𞟾𞠀𞣄𞣇𞣏𞤀𞥃𞥋𞥋𞥐𞥙𞱱𞲫𞲭𞲯𞲱𞲴𞴁𞴭𞴯𞴽𞸀𞸃𞸅𞸟𞸡𞸢𞸤𞸤𞸧𞸧𞸩𞸲𞸴𞸷𞸹𞸹𞸻𞸻𞹂𞹂𞹇𞹇𞹉𞹉𞹋𞹋𞹍𞹏𞹑𞹒𞹔𞹔𞹗𞹗𞹙𞹙𞹛𞹛𞹝𞹝𞹟𞹟𞹡𞹢𞹤𞹤𞹧𞹪𞹬𞹲𞹴𞹷𞹹𞹼𞹾𞹾𞺀𞺉𞺋𞺛𞺡𞺣𞺥𞺩𞺫𞺻🄀🄌🯰🯹𠀀𪛟𪜀𫜸𫝀𫠝𫠠𬺡𬺰𮯠丽𪘀𰀀𱍊"

# --- small character helpers ---------------------------------------------

define function is_in_string taking ch, s
    if ch is empty then
        give back false
    end if
    give back call contains with collection = s, value = ch
end function

define function in_ranges taking ch, ranges
    if (the length of ch) does not equal 1 then
        give back false
    end if
    set i to 0
    repeat while i is less than (the length of ranges)
        set lo to item i of ranges
        set hi to item (i plus 1) of ranges
        if ((ch is at least lo) and (ch is at most hi)) then
            give back true
        end if
        set i to i plus 2
    end repeat
    give back false
end function

define function is_decimal taking ch, ascii_only
    if ascii_only then
        give back call is_in_string with ch = ch, s = digits_ascii
    end if
    give back call in_ranges with ch = ch, ranges = dec_ranges
end function

define function is_word_char taking ch, ascii_only
    if ascii_only then
        give back call is_in_string with ch = ch, s = word_ascii
    end if
    give back call in_ranges with ch = ch, ranges = word_ranges
end function

define function is_space_char taking ch, ascii_only
    if ascii_only then
        give back call is_in_string with ch = ch, s = space_ascii
    end if
    give back call in_ranges with ch = ch, ranges = space_ranges
end function

define function fold_char taking ch
    # The four characters Python's IGNORECASE folds specially.
    if ch equals "ı" then
        give back "i"
    end if
    if ch equals "İ" then
        give back "i"
    end if
    if ch equals "ſ" then
        give back "s"
    end if
    if ch equals "K" then
        give back "k"
    end if
    give back call lowercase of with text = ch
end function

define function char_eq taking a, b, fm
    if not (item "i" of fm) then
        give back (a equals b)
    end if
    give back ((call fold_char with ch = a) equals (call fold_char with ch = b))
end function

define function cat_matches taking cat, ch, fm
    set ascii_only to item "a" of fm
    set code to cat
    set positive to true
    if cat equals "D" then
        set code to "d"
        set positive to false
    end if
    if cat equals "W" then
        set code to "w"
        set positive to false
    end if
    if cat equals "S" then
        set code to "s"
        set positive to false
    end if
    set found to false
    if code equals "d" then
        set found to call is_decimal with ch = ch, ascii_only = ascii_only
    otherwise if code equals "w" then
        set found to call is_word_char with ch = ch, ascii_only = ascii_only
    otherwise
        set found to call is_space_char with ch = ch, ascii_only = ascii_only
    end if
    if positive then
        give back found
    end if
    give back (not found)
end function

define function class_matches taking cls, ch, fm
    set found to false
    repeat for each it in item "items" of cls
        set tag to item "kind" of it
        if tag equals "char" then
            set found to call char_eq with a = ch, b = (item "char" of it), fm = fm
        otherwise if tag equals "category" then
            set found to call cat_matches with cat = (item "cat" of it), ch = ch, fm = fm
        otherwise
            set lo to item "lo" of it
            set hi to item "hi" of it
            set probe to ch
            if item "i" of fm then
                set probe to call fold_char with ch = ch
                set lo to call fold_char with ch = lo
                set hi to call fold_char with ch = hi
            end if
            set found to ((probe is at least lo) and (probe is at most hi))
        end if
        if found then
            stop the loop
        end if
    end repeat
    if item "neg" of cls then
        give back (not found)
    end if
    give back found
end function

# --- flags ---------------------------------------------------------------

define function flag_map taking flags
    if not (flags is a list) then
        fail with bad_argument, "flags must be a list"
    end if
    set fm to a map with "i" mapped to false, "m" mapped to false, "s" mapped to false, "x" mapped to false, "a" mapped to false
    repeat for each f in flags
        if f equals "ignore case" then
            set item "i" of fm to true
        otherwise if f equals "multiline" then
            set item "m" of fm to true
        otherwise if f equals "dot all" then
            set item "s" of fm to true
        otherwise if f equals "verbose" then
            set item "x" of fm to true
        otherwise if f equals "ascii" then
            set item "a" of fm to true
        otherwise
            fail with invalid_flag, "unknown flag"
        end if
    end repeat
    give back fm
end function

# --- pattern parser ------------------------------------------------------

define function char_at taking text, i
    if ((i is at least 0) and (i is less than (the length of text))) then
        give back item i of text
    end if
    give back ""
end function

define function peek taking state
    give back call char_at with text = (item "text" of state), i = (item "i" of state)
end function

define function peek_next taking state
    give back call char_at with text = (item "text" of state), i = ((item "i" of state) plus 1)
end function

define function advance taking state
    set i to item "i" of state
    set item "i" of state to i plus 1
end function

define function starts_with taking state, word
    set j to 0
    repeat while j is less than (the length of word)
        set k to (item "i" of state) plus j
        if (call char_at with text = (item "text" of state), i = k) does not equal (item j of word) then
            give back false
        end if
        set j to j plus 1
    end repeat
    give back true
end function

define function strip_verbose taking pattern
    set out to ""
    set i to 0
    set in_class to false
    set n to the length of pattern
    repeat while i is less than n
        set ch to item i of pattern
        if (ch equals bs_char) and ((i plus 1) is less than n) then
            set out to out plus ch plus (item (i plus 1) of pattern)
            set i to i plus 2
        otherwise if ch equals "[" then
            set in_class to true
            set out to out plus ch
            set i to i plus 1
        otherwise if ch equals "]" then
            set in_class to false
            set out to out plus ch
            set i to i plus 1
        otherwise if (not in_class) and (call is_in_string with ch = ch, s = space_ascii) then
            set i to i plus 1
        otherwise if (not in_class) and (ch equals "#") then
            repeat while (i is less than n) and ((item i of pattern) does not equal lf_char)
                set i to i plus 1
            end repeat
        otherwise
            set out to out plus ch
            set i to i plus 1
        end if
    end repeat
    give back out
end function

define function parse_class_item taking state
    set ch to call peek with state = state
    if ch is empty then
        fail with invalid_pattern, "unterminated character set"
    end if
    call advance with state = state
    if ch does not equal bs_char then
        give back a map with "kind" mapped to "char", "char" mapped to ch
    end if
    set esc to call peek with state = state
    if esc is empty then
        fail with invalid_pattern, "bad escape (end of pattern)"
    end if
    call advance with state = state
    if esc equals "b" then
        give back a map with "kind" mapped to "char", "char" mapped to bh_char
    end if
    if esc equals "n" then
        give back a map with "kind" mapped to "char", "char" mapped to lf_char
    end if
    if esc equals "t" then
        give back a map with "kind" mapped to "char", "char" mapped to tab_char
    end if
    if esc equals "r" then
        give back a map with "kind" mapped to "char", "char" mapped to cr_char
    end if
    if esc equals "f" then
        give back a map with "kind" mapped to "char", "char" mapped to ff_char
    end if
    if esc equals "v" then
        give back a map with "kind" mapped to "char", "char" mapped to vt_char
    end if
    if esc equals "a" then
        give back a map with "kind" mapped to "char", "char" mapped to bel_char
    end if
    if esc equals bs_char then
        give back a map with "kind" mapped to "char", "char" mapped to bs_char
    end if
    if call is_in_string with ch = esc, s = "dDwWsS" then
        give back a map with "kind" mapped to "category", "cat" mapped to esc
    end if
    if call is_in_string with ch = esc, s = letters_ascii then
        fail with invalid_pattern, "bad escape"
    end if
    give back a map with "kind" mapped to "char", "char" mapped to esc
end function

define function parse_class taking state
    set neg to false
    if (call peek with state = state) equals "^" then
        set neg to true
        call advance with state = state
    end if
    set items to an empty list
    set first to true
    repeat while true
        set ch to call peek with state = state
        if ch is empty then
            fail with invalid_pattern, "unterminated character set"
        end if
        if (ch equals "]") and not first then
            call advance with state = state
            stop the loop
        end if
        set it to call parse_class_item with state = state
        set first to false
        set nx to call peek_next with state = state
        if ((call peek with state = state) equals "-") and not (nx is empty) and not (nx equals "]") and ((item "kind" of it) equals "char") then
            call advance with state = state
            set hi to call parse_class_item with state = state
            if (item "kind" of hi) does not equal "char" then
                fail with invalid_pattern, "bad character range"
            end if
            if (item "char" of it) is greater than (item "char" of hi) then
                fail with invalid_pattern, "bad character range"
            end if
            add (a map with "kind" mapped to "range", "lo" mapped to (item "char" of it), "hi" mapped to (item "char" of hi)) to items
        otherwise
            add it to items
        end if
    end repeat
    give back a map with "kind" mapped to "class", "neg" mapped to neg, "items" mapped to items
end function

define function parse_escape taking state
    set ch to call peek with state = state
    if ch is empty then
        fail with invalid_pattern, "bad escape (end of pattern)"
    end if
    call advance with state = state
    if ch equals "n" then
        give back a map with "kind" mapped to "lit", "char" mapped to lf_char
    end if
    if ch equals "t" then
        give back a map with "kind" mapped to "lit", "char" mapped to tab_char
    end if
    if ch equals "r" then
        give back a map with "kind" mapped to "lit", "char" mapped to cr_char
    end if
    if ch equals "f" then
        give back a map with "kind" mapped to "lit", "char" mapped to ff_char
    end if
    if ch equals "v" then
        give back a map with "kind" mapped to "lit", "char" mapped to vt_char
    end if
    if ch equals "a" then
        give back a map with "kind" mapped to "lit", "char" mapped to bel_char
    end if
    if ch equals bs_char then
        give back a map with "kind" mapped to "lit", "char" mapped to bs_char
    end if
    if call is_in_string with ch = ch, s = "dDwWsS" then
        give back a map with "kind" mapped to "category", "cat" mapped to ch
    end if
    if ch equals "A" then
        give back a map with "kind" mapped to "anchor", "which" mapped to "abs_start"
    end if
    if ch equals "Z" then
        give back a map with "kind" mapped to "anchor", "which" mapped to "abs_end"
    end if
    if ch equals "b" then
        give back a map with "kind" mapped to "anchor", "which" mapped to "boundary"
    end if
    if ch equals "B" then
        give back a map with "kind" mapped to "anchor", "which" mapped to "not_boundary"
    end if
    if call is_in_string with ch = ch, s = "123456789" then
        set idx to call to number with text = ch
        if idx is greater than (item "groups" of state) then
            fail with invalid_pattern, "invalid group reference"
        end if
        give back a map with "kind" mapped to "backref", "index" mapped to idx
    end if
    if ch equals "0" then
        fail with invalid_pattern, "octal escapes are not supported in v1"
    end if
    if call is_in_string with ch = ch, s = letters_ascii then
        fail with invalid_pattern, "bad escape"
    end if
    give back a map with "kind" mapped to "lit", "char" mapped to ch
end function

define function parse_atom taking state
    set ch to call peek with state = state
    if ch is empty then
        fail with invalid_pattern, "unexpected end of pattern"
    end if
    if ch equals "(" then
        call advance with state = state
        set capturing to true
        set idx to 0
        if call starts_with with state = state, word = "?:" then
            set capturing to false
            call advance with state = state
            call advance with state = state
        otherwise if (call peek with state = state) equals "?" then
            fail with invalid_pattern, "unsupported group extension"
        otherwise
            set g to (item "groups" of state) plus 1
            set item "groups" of state to g
            set idx to g
        end if
        set body to call parse_alt with state = state
        if not ((call peek with state = state) equals ")") then
            fail with invalid_pattern, "missing ), unterminated subpattern"
        end if
        call advance with state = state
        if capturing then
            give back a map with "kind" mapped to "group", "body" mapped to body, "index" mapped to idx
        end if
        give back body
    end if
    if ch equals "[" then
        call advance with state = state
        give back call parse_class with state = state
    end if
    if ch equals "." then
        call advance with state = state
        give back a map with "kind" mapped to "any"
    end if
    if ch equals "^" then
        call advance with state = state
        give back a map with "kind" mapped to "anchor", "which" mapped to "start"
    end if
    if ch equals "$" then
        call advance with state = state
        give back a map with "kind" mapped to "anchor", "which" mapped to "end"
    end if
    if ch equals bs_char then
        call advance with state = state
        give back call parse_escape with state = state
    end if
    if call is_in_string with ch = ch, s = "*+?{" then
        fail with invalid_pattern, "nothing to repeat"
    end if
    call advance with state = state
    give back a map with "kind" mapped to "lit", "char" mapped to ch
end function

define function parse_piece taking state
    set atom to call parse_atom with state = state
    set ch to call peek with state = state
    set minc to 0
    set maxc to (0 minus 1)
    set greedy to true
    set is_repeat to false
    if ch equals "*" then
        set is_repeat to true
        set minc to 0
        set maxc to (0 minus 1)
    otherwise if ch equals "+" then
        set is_repeat to true
        set minc to 1
        set maxc to (0 minus 1)
    otherwise if ch equals "?" then
        set is_repeat to true
        set minc to 0
        set maxc to 1
    otherwise if ch equals "{" then
        fail with invalid_pattern, "counted repetition is not supported in v1"
    end if
    if not is_repeat then
        give back atom
    end if
    call advance with state = state
    set nx to call peek with state = state
    if nx equals "?" then
        set greedy to false
        call advance with state = state
        set nx to call peek with state = state
    end if
    if call is_in_string with ch = nx, s = "*+?{" then
        fail with invalid_pattern, "multiple repeat"
    end if
    give back a map with "kind" mapped to "repeat", "body" mapped to atom, "min" mapped to minc, "max" mapped to maxc, "greedy" mapped to greedy
end function

define function parse_cat taking state
    set items to an empty list
    repeat while true
        set ch to call peek with state = state
        if (ch is empty) or (ch equals "|") or (ch equals ")") then
            stop the loop
        end if
        add (call parse_piece with state = state) to items
    end repeat
    if (the length of items) equals 0 then
        give back a map with "kind" mapped to "empty"
    end if
    if (the length of items) equals 1 then
        give back item 0 of items
    end if
    give back a map with "kind" mapped to "cat", "items" mapped to items
end function

define function parse_alt taking state
    set branches to an empty list
    add (call parse_cat with state = state) to branches
    repeat while (call peek with state = state) equals "|"
        call advance with state = state
        add (call parse_cat with state = state) to branches
    end repeat
    if (the length of branches) equals 1 then
        give back item 0 of branches
    end if
    give back a map with "kind" mapped to "alt", "branches" mapped to branches
end function

define function compile taking pattern, flags
    if not (pattern is text) then
        fail with bad_argument, "pattern must be text"
    end if
    set fm to call flag_map with flags = flags
    set p to pattern
    if item "x" of fm then
        set p to call strip_verbose with pattern = pattern
    end if
    set state to a map with "text" mapped to p, "i" mapped to 0, "groups" mapped to 0
    set root to call parse_alt with state = state
    if not ((call peek with state = state) is empty) then
        fail with invalid_pattern, "unbalanced parenthesis"
    end if
    give back a map with "root" mapped to root, "groups" mapped to (item "groups" of state), "flags" mapped to fm
end function

# --- backtracking matcher -------------------------------------------------

define function spend taking ctx
    set t to item "ticks" of ctx
    set item "ticks" of ctx to t plus 1
    give back (t is less than (item "limit" of ctx))
end function

define function new_state taking pos, caps
    give back a map with "pos" mapped to pos, "caps" mapped to caps
end function

define function copy_caps taking caps
    set out to an empty list
    repeat for each c in caps
        add c to out
    end repeat
    give back out
end function

define function set_cap taking caps, index, value
    set out to call copy_caps with caps = caps
    set item index of out to value
    give back out
end function

define function blank_caps taking groups
    set out to an empty list
    set i to 0
    repeat while i is at most groups
        add nothing to out
        set i to i plus 1
    end repeat
    give back out
end function

define function word_at taking text, pos, fm
    if ((pos is less than 0) or (pos is at least (the length of text))) then
        give back false
    end if
    give back call cat_matches with cat = "w", ch = (item pos of text), fm = fm
end function

define function anchor_ok taking which, text, pos, fm
    set n to the length of text
    if which equals "start" then
        if pos equals 0 then
            give back true
        end if
        if item "m" of fm then
            if ((pos is greater than 0) and ((item (pos minus 1) of text) equals lf_char)) then
                give back true
            end if
        end if
        give back false
    end if
    if which equals "end" then
        if pos equals n then
            give back true
        end if
        if pos is less than n then
            if (item pos of text) equals lf_char then
                if item "m" of fm then
                    give back true
                end if
                if pos equals (n minus 1) then
                    give back true
                end if
            end if
        end if
        give back false
    end if
    if which equals "abs_start" then
        give back (pos equals 0)
    end if
    if which equals "abs_end" then
        give back (pos equals n)
    end if
    set before to call word_at with text = text, pos = (pos minus 1), fm = fm
    set after to call word_at with text = text, pos = pos, fm = fm
    if which equals "boundary" then
        give back (before does not equal after)
    end if
    give back (before equals after)
end function

define function match_cat taking items, text, pos, caps, ctx
    set states to a list of (call new_state with pos = pos, caps = caps)
    repeat for each it in items
        set next_states to an empty list
        repeat for each st in states
            set kids to call match_node with node = it, text = text, pos = (item "pos" of st), caps = (item "caps" of st), ctx = ctx
            repeat for each kid in kids
                add kid to next_states
            end repeat
        end repeat
        set states to next_states
        if (the length of states) equals 0 then
            give back an empty list
        end if
    end repeat
    give back states
end function

define function match_alt taking branches, text, pos, caps, ctx
    set out to an empty list
    repeat for each branch in branches
        set kids to call match_node with node = branch, text = text, pos = pos, caps = caps, ctx = ctx
        repeat for each kid in kids
            add kid to out
        end repeat
    end repeat
    give back out
end function

define function match_group taking node, text, pos, caps, ctx
    set kids to call match_node with node = (item "body" of node), text = text, pos = pos, caps = caps, ctx = ctx
    set out to an empty list
    repeat for each kid in kids
        set nc to call set_cap with caps = (item "caps" of kid), index = (item "index" of node), value = (call slice with collection = text, start = pos, finish = (item "pos" of kid))
        add (call new_state with pos = (item "pos" of kid), caps = nc) to out
    end repeat
    give back out
end function

define function repeat_more taking node, text, pos, caps, ctx, count
    set out to an empty list
    set minc to item "min" of node
    set maxc to item "max" of node
    set greedy to item "greedy" of node
    set here to (count is at least minc)
    set can_more to ((maxc is less than 0) or (count is less than maxc))
    set deeper to an empty list
    if can_more then
        set kids to call match_node with node = (item "body" of node), text = text, pos = pos, caps = caps, ctx = ctx
        repeat for each kid in kids
            set kidpos to item "pos" of kid
            if kidpos equals pos then
                # A zero-width iteration is taken at most once.
                add (call new_state with pos = pos, caps = (item "caps" of kid)) to deeper
            otherwise
                set sub to call repeat_more with node = node, text = text, pos = kidpos, caps = (item "caps" of kid), ctx = ctx, count = (count plus 1)
                repeat for each s in sub
                    add s to deeper
                end repeat
            end if
        end repeat
    end if
    if greedy then
        repeat for each s in deeper
            add s to out
        end repeat
        if here then
            add (call new_state with pos = pos, caps = caps) to out
        end if
    otherwise
        if here then
            add (call new_state with pos = pos, caps = caps) to out
        end if
        repeat for each s in deeper
            add s to out
        end repeat
    end if
    give back out
end function

define function match_backref taking node, text, pos, caps, ctx
    set captured to item (item "index" of node) of caps
    if captured is nothing then
        give back an empty list
    end if
    set endpos to pos plus (the length of captured)
    if endpos is greater than (the length of text) then
        give back an empty list
    end if
    set fm to item "flags" of ctx
    set piece to call slice with collection = text, start = pos, finish = endpos
    set same to call char_eq with a = piece, b = captured, fm = fm
    if not same then
        give back an empty list
    end if
    give back a list of (call new_state with pos = endpos, caps = caps)
end function

define function match_node taking node, text, pos, caps, ctx
    if not (call spend with ctx = ctx) then
        give back an empty list
    end if
    set fm to item "flags" of ctx
    set tag to item "kind" of node
    set n to the length of text
    if tag equals "empty" then
        give back a list of (call new_state with pos = pos, caps = caps)
    end if
    if tag equals "lit" then
        if pos is less than n then
            if call char_eq with a = (item pos of text), b = (item "char" of node), fm = fm then
                give back a list of (call new_state with pos = (pos plus 1), caps = caps)
            end if
        end if
        give back an empty list
    end if
    if tag equals "class" then
        if pos is less than n then
            if call class_matches with cls = node, ch = (item pos of text), fm = fm then
                give back a list of (call new_state with pos = (pos plus 1), caps = caps)
            end if
        end if
        give back an empty list
    end if
    if tag equals "any" then
        if pos is less than n then
            set ch to item pos of text
            if ((not (ch equals lf_char)) or (item "s" of fm)) then
                give back a list of (call new_state with pos = (pos plus 1), caps = caps)
            end if
        end if
        give back an empty list
    end if
    if tag equals "cat" then
        give back call match_cat with items = (item "items" of node), text = text, pos = pos, caps = caps, ctx = ctx
    end if
    if tag equals "alt" then
        give back call match_alt with branches = (item "branches" of node), text = text, pos = pos, caps = caps, ctx = ctx
    end if
    if tag equals "group" then
        give back call match_group with node = node, text = text, pos = pos, caps = caps, ctx = ctx
    end if
    if tag equals "repeat" then
        give back call repeat_more with node = node, text = text, pos = pos, caps = caps, ctx = ctx, count = 0
    end if
    if tag equals "backref" then
        give back call match_backref with node = node, text = text, pos = pos, caps = caps, ctx = ctx
    end if
    if tag equals "anchor" then
        if call anchor_ok with which = (item "which" of node), text = text, pos = pos, fm = fm then
            give back a list of (call new_state with pos = pos, caps = caps)
        end if
        give back an empty list
    end if
    if tag equals "category" then
        if pos is less than n then
            if call cat_matches with cat = (item "cat" of node), ch = (item pos of text), fm = fm then
                give back a list of (call new_state with pos = (pos plus 1), caps = caps)
            end if
        end if
        give back an empty list
    end if
    if pos is less than n then
        if call cat_matches with cat = (item "cat" of node), ch = (item pos of text), fm = fm then
            give back a list of (call new_state with pos = (pos plus 1), caps = caps)
        end if
    end if
    give back an empty list
end function

define function make_match taking text, start, finish, caps, groups
    set glist to an empty list
    set i to 1
    repeat while i is at most groups
        add (item i of caps) to glist
        set i to i plus 1
    end repeat
    give back a map with "matched" mapped to (call slice with collection = text, start = start, finish = finish), "start" mapped to start, "end" mapped to finish, "groups" mapped to glist, "named" mapped to (an empty map)
end function

define function fresh_ctx taking text, fm
    give back a map with "text" mapped to text, "flags" mapped to fm, "ticks" mapped to 0, "limit" mapped to 200000
end function

define function first_at taking node, text, pos, caps, ctx
    set results to call match_node with node = node, text = text, pos = pos, caps = caps, ctx = ctx
    if (the length of results) is greater than 0 then
        give back item 0 of results
    end if
    give back nothing
end function

define function first_nonempty_at taking node, text, pos, caps, ctx
    set results to call match_node with node = node, text = text, pos = pos, caps = caps, ctx = ctx
    repeat for each st in results
        if (item "pos" of st) is greater than pos then
            give back st
        end if
    end repeat
    give back nothing
end function

define function scan_matches taking pattern, text, flags
    set compiled to call compile with pattern = pattern, flags = flags
    set node to item "root" of compiled
    set fm to item "flags" of compiled
    set groups to item "groups" of compiled
    set out to an empty list
    set n to the length of text
    set pos to 0
    repeat while pos is at most n
        set caps to call blank_caps with groups = groups
        set ctx to call fresh_ctx with text = text, fm = fm
        set st to call first_at with node = node, text = text, pos = pos, caps = caps, ctx = ctx
        if not (st is nothing) then
            set finish to item "pos" of st
            add (call make_match with text = text, start = pos, finish = finish, caps = (item "caps" of st), groups = groups) to out
            if finish equals pos then
                # Python retries at the same position for a non-empty match
                # after yielding an empty one (CPython scanner behaviour).
                set caps2 to call blank_caps with groups = groups
                set ctx2 to call fresh_ctx with text = text, fm = fm
                set alt to call first_nonempty_at with node = node, text = text, pos = pos, caps = caps2, ctx = ctx2
                if not (alt is nothing) then
                    set altfinish to item "pos" of alt
                    add (call make_match with text = text, start = pos, finish = altfinish, caps = (item "caps" of alt), groups = groups) to out
                    set pos to altfinish
                otherwise
                    set pos to pos plus 1
                end if
            otherwise
                set pos to finish
            end if
        otherwise
            set pos to pos plus 1
        end if
    end repeat
    give back out
end function

define function do_search taking pattern, text, flags, anchored
    set compiled to call compile with pattern = pattern, flags = flags
    set node to item "root" of compiled
    set fm to item "flags" of compiled
    set groups to item "groups" of compiled
    set n to the length of text
    set pos to 0
    repeat while pos is at most n
        set caps to call blank_caps with groups = groups
        set ctx to call fresh_ctx with text = text, fm = fm
        set st to call first_at with node = node, text = text, pos = pos, caps = caps, ctx = ctx
        if not (st is nothing) then
            give back call make_match with text = text, start = pos, finish = (item "pos" of st), caps = (item "caps" of st), groups = groups
        end if
        if anchored then
            give back nothing
        end if
        set pos to pos plus 1
    end repeat
    give back nothing
end function

define function do_full_match taking pattern, text, flags
    set m to call do_search with pattern = pattern, text = text, flags = flags, anchored = true
    if not (m is nothing) then
        if (item "end" of m) equals (the length of text) then
            give back m
        end if
    end if
    give back nothing
end function

# --- replacement templates ----------------------------------------------

define function group_text taking m, index
    set gs to item "groups" of m
    if index is greater than (the length of gs) then
        fail with invalid_pattern, "invalid group reference in replacement"
    end if
    set gv to item (index minus 1) of gs
    if gv is nothing then
        give back ""
    end if
    give back gv
end function

define function expand_replacement taking template, m
    set out to ""
    set i to 0
    set n to the length of template
    repeat while i is less than n
        set ch to item i of template
        if ch does not equal bs_char then
            set out to out plus ch
            set i to i plus 1
        otherwise
            set nx to call char_at with text = template, i = (i plus 1)
            if nx is empty then
                fail with invalid_pattern, "bad escape (end of replacement)"
            end if
            set adv to 2
            if call is_in_string with ch = nx, s = "123456789" then
                set out to out plus (call group_text with m = m, index = (call to number with text = nx))
            otherwise if nx equals "g" then
                if (call char_at with text = template, i = (i plus 2)) does not equal "<" then
                    fail with invalid_pattern, "missing < in replacement group reference"
                end if
                set j to i plus 3
                set num to ""
                repeat while (j is less than n) and ((item j of template) does not equal ">")
                    set num to num plus (item j of template)
                    set j to j plus 1
                end repeat
                if j is at least n then
                    fail with invalid_pattern, "missing > in replacement group reference"
                end if
                set out to out plus (call group_text with m = m, index = (call to number with text = num))
                set adv to (j plus 1) minus i
            otherwise if nx equals bs_char then
                set out to out plus bs_char
            otherwise if nx equals "n" then
                set out to out plus lf_char
            otherwise if nx equals "t" then
                set out to out plus tab_char
            otherwise if nx equals "r" then
                set out to out plus cr_char
            otherwise if nx equals "f" then
                set out to out plus ff_char
            otherwise if nx equals "v" then
                set out to out plus vt_char
            otherwise if nx equals "a" then
                set out to out plus bel_char
            otherwise
                fail with invalid_pattern, "bad escape in replacement"
            end if
            set i to i plus adv
        end if
    end repeat
    give back out
end function

define function do_replace taking pattern, text, replacement, count, flags
    if not (replacement is text) then
        fail with bad_argument, "replacement must be text"
    end if
    set found to call scan_matches with pattern = pattern, text = text, flags = flags
    set out to ""
    set last to 0
    set used to 0
    repeat for each m in found
        if (count is greater than 0) and (used is at least count) then
            stop the loop
        end if
        set out to out plus (call slice with collection = text, start = last, finish = (item "start" of m))
        set out to out plus (call expand_replacement with template = replacement, m = m)
        set last to item "end" of m
        set used to used plus 1
    end repeat
    set out to out plus (call slice with collection = text, start = last, finish = (the length of text))
    give back out
end function

define function do_split taking pattern, text, limit, flags
    set found to call scan_matches with pattern = pattern, text = text, flags = flags
    set parts to an empty list
    set last to 0
    set used to 0
    repeat for each m in found
        if (limit is greater than 0) and (used is at least limit) then
            stop the loop
        end if
        add (call slice with collection = text, start = last, finish = (item "start" of m)) to parts
        # re.split also inserts the text of every capturing group (a group
        # that did not participate becomes nothing).
        repeat for each g in (item "groups" of m)
            add g to parts
        end repeat
        set last to item "end" of m
        set used to used plus 1
    end repeat
    add (call slice with collection = text, start = last, finish = (the length of text)) to parts
    give back parts
end function

# --- public API ----------------------------------------------------------

define function match taking pattern, text
    give back call do_search with pattern = pattern, text = text, flags = (an empty list), anchored = true
end function

define function match_flags taking pattern, text, flags
    give back call do_search with pattern = pattern, text = text, flags = flags, anchored = true
end function

define function search taking pattern, text
    give back call do_search with pattern = pattern, text = text, flags = (an empty list), anchored = false
end function

define function search_flags taking pattern, text, flags
    give back call do_search with pattern = pattern, text = text, flags = flags, anchored = false
end function

define function full_match taking pattern, text
    give back call do_full_match with pattern = pattern, text = text, flags = (an empty list)
end function

define function full_match_flags taking pattern, text, flags
    give back call do_full_match with pattern = pattern, text = text, flags = flags
end function

define function find_all taking pattern, text
    also known as findall
    give back call scan_matches with pattern = pattern, text = text, flags = (an empty list)
end function

define function find_all_flags taking pattern, text, flags
    give back call scan_matches with pattern = pattern, text = text, flags = flags
end function

define function replace taking pattern, text, replacement
    give back call do_replace with pattern = pattern, text = text, replacement = replacement, count = 0, flags = (an empty list)
end function

define function replace_count taking pattern, text, replacement, count
    give back call do_replace with pattern = pattern, text = text, replacement = replacement, count = count, flags = (an empty list)
end function

define function replace_flags taking pattern, text, replacement, flags
    give back call do_replace with pattern = pattern, text = text, replacement = replacement, count = 0, flags = flags
end function

define function replace_count_flags taking pattern, text, replacement, count, flags
    give back call do_replace with pattern = pattern, text = text, replacement = replacement, count = count, flags = flags
end function

define function split taking pattern, text
    give back call do_split with pattern = pattern, text = text, limit = 0, flags = (an empty list)
end function

define function split_limit taking pattern, text, limit
    give back call do_split with pattern = pattern, text = text, limit = limit, flags = (an empty list)
end function

define function split_flags taking pattern, text, flags
    give back call do_split with pattern = pattern, text = text, limit = 0, flags = flags
end function

define function split_limit_flags taking pattern, text, limit, flags
    give back call do_split with pattern = pattern, text = text, limit = limit, flags = flags
end function

define function escape taking text
    set out to ""
    repeat for each ch in text
        if call is_in_string with ch = ch, s = special_escape then
            set out to out plus bs_char plus ch
        otherwise
            set out to out plus ch
        end if
    end repeat
    give back out
end function

define function matches taking pattern, text
    give back not ((call search with pattern = pattern, text = text) is nothing)
end function

define function matches_flags taking pattern, text, flags
    give back not ((call search_flags with pattern = pattern, text = text, flags = flags) is nothing)
end function
