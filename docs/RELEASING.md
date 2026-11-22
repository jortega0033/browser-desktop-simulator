# Releasing

Only the owner releases. Agents never tag, publish or create a release.

A release here is a Git tag on `main` and the version in `browser_desktop/__init__.py`. Nothing is published to a package index or deployed: the product is run from a checkout.

## Steps

1. All tickets for the release are merged and CI is green on `main` (Linux and Windows, Python 3.12 and 3.13).
2. On a clean checkout of `main`, run `python -m unittest discover -s tests -t .` and confirm the last line is `OK`.
3. Run the smoke steps in `README.md` once in a browser at 800x600.
4. Set `__version__` in `browser_desktop/__init__.py`, update the version expected by the health test and PRD sections 5.1 and 9, and move the `Unreleased` entries in `CHANGELOG.md` under a new dated version heading.
5. Merge that change by pull request, then tag the merge commit: `git tag -a v<version> -m "v<version>"` and push the tag.
6. Create the GitHub release from the tag with the changelog section as its notes.
