"""Select automatically maintained release series from published stable releases."""

import re

from github_api import all_items

STABLE = re.compile(r"v(20\d{2})\.([1-9]\d*)\.(0|[1-9]\d*)")
BRANCH = re.compile(r"release/(20\d{2})\.([1-9]\d*)")


def release_branch(version: str) -> str:
    match = STABLE.fullmatch("v" + version)
    if not match:
        raise ValueError("Expected a stable YEAR.SERIES.PATCH version")
    return f"release/{match[1]}.{match[2]}"


def published_series(api) -> dict[str, str]:
    """Map each published stable series to its highest patch tag."""
    versions = {}
    for release in all_items(api.repos.list_releases):
        match = STABLE.fullmatch(release["tag_name"])
        if release["draft"] or release["prerelease"] or not match:
            continue
        parts = tuple(map(int, match.groups()))
        if parts[:2] not in versions or parts > versions[parts[:2]]:
            versions[parts[:2]] = parts
    return {
        f"release/{year}.{series}": "v" + ".".join(map(str, versions[year, series]))
        for year, series in sorted(versions, reverse=True)
    }


def supported_branches(api) -> list[str]:
    return list(published_series(api))[:2]


def check_release_branch(branch: str, version: str):
    if release_branch(version) != branch:
        raise ValueError("Package version must belong to the selected release branch")


def release_allowed(api, branch: str, version: str, manual: bool = False) -> bool:
    """Allow supported patches, reviewed new series, and explicit manual releases."""
    check_release_branch(branch, version)
    series = published_series(api)
    if manual or branch in list(series)[:2]:
        return True
    # A new series' first release is prepared from an RC and reviewed manually.
    return (
        branch not in series
        and version.endswith(".0")
        and (
            not series
            or tuple(map(int, version.split(".")))
            > tuple(map(int, next(iter(series.values()))[1:].split(".")))
        )
    )


if __name__ == "__main__":
    import os
    import tomllib
    from pathlib import Path

    from github_api import create_client, read_file

    api = create_client()
    branch = os.environ["RELEASE_BRANCH"]

    version = tomllib.loads(read_file(api, "pyproject.toml", branch))["project"][
        "version"
    ]
    allowed = bool(STABLE.fullmatch("v" + version)) and release_allowed(
        api, branch, version, os.environ.get("MANUAL_RELEASE") == "true"
    )
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"allowed={str(allowed).lower()}\n")
    if not allowed:
        print(
            "Automatic releases are limited to the two latest published series. Dispatch manually for an older series."
        )
