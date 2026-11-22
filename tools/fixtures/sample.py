def average(values):
    total = 0
    for v in values:
        total += v
    return total / len(values)


def classify(n):
    if n >= 90:
        return "A"
    elif n >= 80:
        return "B"
    else:
        return "C"


xs = [1, 2, 3]
print(average(xs))
print(classify(91))
print(classify(85))
print(classify(40))
