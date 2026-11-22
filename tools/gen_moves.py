"""Generate the facelet permutation tables used by examples/rubiks.ll.

Coordinate system: x right, y up, z front. Each facelet is identified by a
position p and a normal n. Faces are numbered U,R,F,D,L,B with 9 row-major
facelets each, for a total of 54 (standard Kociemba-style ordering).

A move table P means: new_facelet[i] = old_facelet[P[i]].
"""

FACES = ("U", "R", "F", "D", "L", "B")


def facelet_index(face, p, n):
    x, y, z = p
    if face == "U":
        row, col = z + 1, x + 1
    elif face == "D":
        row, col = 1 - z, x + 1
    elif face == "F":
        row, col = 1 - y, x + 1
    elif face == "B":
        row, col = 1 - y, 1 - x
    elif face == "R":
        row, col = 1 - y, 1 - z
    else:  # L
        row, col = 1 - y, z + 1
    return FACES.index(face) * 9 + row * 3 + col


def build_facelets():
    facelets = []  # (p, n, face)
    for face in FACES:
        for a in (-1, 0, 1):
            for b in (-1, 0, 1):
                if face == "U":
                    p, n = (a, 1, b), (0, 1, 0)
                elif face == "D":
                    p, n = (a, -1, b), (0, -1, 0)
                elif face == "F":
                    p, n = (a, b, 1), (0, 0, 1)
                elif face == "B":
                    p, n = (a, b, -1), (0, 0, -1)
                elif face == "R":
                    p, n = (1, b, a), (1, 0, 0)
                else:
                    p, n = (-1, b, a), (-1, 0, 0)
                facelets.append((p, n, face))
    return facelets


def rotate(v, axis, sign):
    x, y, z = v
    if axis == "x":
        return (x, -sign * z, sign * y)
    if axis == "y":
        return (sign * z, y, -sign * x)
    return (-sign * y, sign * x, z)


def move_permutation(face):
    axis = {"U": "y", "D": "y", "R": "x", "L": "x", "F": "z", "B": "z"}[face]
    sign = -1 if face in ("U", "R", "F") else 1
    layer_value = 1 if face in ("U", "R", "F") else -1
    layer_axis = {"x": 0, "y": 1, "z": 2}[axis]
    facelets = build_facelets()
    lookup = {(p, n): i for i, (p, n, _) in enumerate(facelets)}
    perm = list(range(54))
    for i, (p, n, _) in enumerate(facelets):
        if p[layer_axis] != layer_value:
            continue
        new_p = rotate(p, axis, sign)
        new_n = rotate(n, axis, sign)
        j = lookup[(new_p, new_n)]
        perm[j] = i
    assert sorted(perm) == list(range(54)), face
    return perm


def compose(p, q):
    """Apply p then q: result[i] = p[q[i]]."""
    return [p[q[i]] for i in range(54)]


def identity():
    return list(range(54))


def verify():
    for face in FACES:
        perm = move_permutation(face)
        acc = identity()
        for _ in range(4):
            acc = compose(acc, perm)
        assert acc == identity(), f"{face}^4 is not identity"
        assert perm != identity(), f"{face} is identity"
    print("all move tables verified: permutations, non-identity, order 4")


def emit():
    entries = []
    for face in FACES:
        values = ", ".join(str(v) for v in move_permutation(face))
        entries.append(f'"{face}" mapped to (a list of {values})')
    print("set moves to a map with " + ", ".join(entries))


if __name__ == "__main__":
    verify()
    print()
    emit()
