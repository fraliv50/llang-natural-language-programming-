# Release process

llang uses semantic versioning: `MAJOR.MINOR.PATCH`.

1. Confirm `python tools/check.py` passes on a clean checkout.
2. Update `CHANGELOG.md` with the changes and the release date.
3. Update the `version` field in `pyproject.toml`.
4. Update `docs/ROADMAP.md` and `docs/REWRITES.md` status if needed.
5. Commit with message `Release vX.Y.Z`.
6. Tag: `git tag -a vX.Y.Z -m "vX.Y.Z"` and push the tag.
7. Build and publish (when configured): `python -m build` and `twine upload dist/*`.

Before a 1.0 release, the following should exist: a compiler backend, a language
server, and a documented package system. See `docs/FAMILY-PLAN.md` and
`docs/ROADMAP.md`.
