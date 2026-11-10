"""List the supported CPython minor versions for local tests and CI."""

import json
import re
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "https://raw.githubusercontent.com/actions/python-versions/main/versions-manifest.json"


def python_versions(specifier: str) -> list[str]:
    bounds = re.fullmatch(
        r">=(\d+)\.(\d+)(?:,<([0-9]+)\.([0-9]+))?", specifier.replace(" ", "")
    )
    if not bounds:
        raise ValueError(
            "Use >=major.minor with an optional ,<major.minor Python upper bound"
        )
    minimum = tuple(map(int, bounds.group(1, 2)))
    maximum = tuple(map(int, bounds.group(3, 4))) if bounds.group(3) else None
    if maximum and maximum[0] == minimum[0]:
        versions = [f"{minimum[0]}.{minor}" for minor in range(minimum[1], maximum[1])]
    else:
        with urllib.request.urlopen(URL, timeout=30) as response:
            releases = json.load(response)
        minors = {
            tuple(map(int, release["version"].split(".")[:2]))
            for release in releases
            if release["stable"]
        }
        versions = [
            ".".join(map(str, version))
            for version in sorted(minors)
            if version >= minimum and (maximum is None or version < maximum)
        ]
    if not versions or versions[0] != ".".join(map(str, minimum)):
        raise ValueError("The supported Python range must include its minimum version")
    return versions


def supported_versions() -> list[str]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    return python_versions(project["requires-python"])


if __name__ == "__main__":
    print(json.dumps(supported_versions()))
