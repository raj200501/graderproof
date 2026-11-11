# Bump a version number

The release script needs to compute the next version. Write a Python module `semver.py` with a function `bump(version, part)`.

- `version` is a string `MAJOR.MINOR.PATCH` of three non-negative decimal integers without leading zeros (`0` itself is allowed). Anything else, such as `"1.2"`, `"1.2.3.4"`, `"01.2.3"`, `"1.2.3-beta"`, or `"v1.2.3"`, is invalid.
- `part` is `"major"`, `"minor"`, or `"patch"`. Bumping `major` increments MAJOR and resets MINOR and PATCH to 0; bumping `minor` increments MINOR and resets PATCH to 0; bumping `patch` increments PATCH.
- Return the new version string, for example `bump("1.9.9", "major")` returns `"2.0.0"`.
- Raise `ValueError` for an invalid version or an unknown part.
