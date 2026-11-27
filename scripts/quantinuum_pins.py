"""Require an exact pin for every Quantinuum package the metapackage installs.

A package counts as Quantinuum-managed when its PyPI metadata for the locked
version links to github.com/Quantinuum or github.com/CQCL, or an author or
maintainer uses a quantinuum.com address.

The README's "Included tools" section must also name exactly the pinned packages,
and every locked package and file must come from PyPI, so that a package from
another index with the same name cannot enter the lockfile.
"""

import json
import re
import sys
import time
import tomllib
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPI = "https://pypi.org/simple"
PYPI_FILES = "https://files.pythonhosted.org/"
ORGANISATIONS = re.compile(r"github\.com/(quantinuum|cqcl)(/|$)", re.IGNORECASE)
EMAIL = re.compile(r"@quantinuum\.com\b", re.IGNORECASE)
README_SECTION = "## Included tools"
# A package is a list item, or the second cell of a table row.
README_PACKAGE = re.compile(
    r"^(?:[-*] |\|[^|\n]*\| )`([A-Za-z0-9_.-]+)`(?: \||$)", re.MULTILINE
)


def normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def runtime_packages(lock: dict, project: str) -> set[tuple[str, str]]:
    versions: dict[str, list[str]] = {}
    packages: dict[tuple[str, str], dict] = {}
    for package in lock["package"]:
        versions.setdefault(package["name"], []).append(package["version"])
        packages[package["name"], package["version"]] = package

    def targets(dependency: dict) -> list[tuple[str, str]]:
        name = dependency["name"]
        if "version" in dependency:
            return [(name, dependency["version"])]
        return [(name, version) for version in versions[name]]

    found: set[tuple[str, str]] = set()
    pending = targets({"name": project})
    while pending:
        key = pending.pop()
        if key in found:
            continue
        found.add(key)
        package = packages[key]
        references = list(package.get("dependencies", []))
        for extra in package.get("optional-dependencies", {}).values():
            references += extra
        for dependency in references:
            pending += targets(dependency)
    return {(name, version) for name, version in found if name != project}


def non_pypi_packages(lock: dict, project: str) -> list[tuple[str, str, str]]:
    """Return each locked source or file, except the project's, not from PyPI."""
    found = []
    for package in lock["package"]:
        if package["name"] == project:
            continue
        name, version = package["name"], package["version"]
        source = package.get("source", {})
        if source != {"registry": PYPI}:
            found.append((name, version, f"source {source}"))
        files = [*package.get("wheels", []), *filter(None, [package.get("sdist")])]
        found += [
            (name, version, f"file {file.get('url')}")
            for file in files
            if not str(file.get("url")).startswith(PYPI_FILES)
        ]
    return sorted(found)


def pinned(dependencies: list[str]) -> set[str]:
    pins = set()
    for requirement in dependencies:
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==[^\s*;]+", requirement)
        if match:
            pins.add(normalise(match[1]))
    return pins


def is_quantinuum(info: dict) -> bool:
    links = [
        *(info.get("project_urls") or {}).values(),
        info.get("home_page") or "",
        info.get("download_url") or "",
    ]
    people = [
        info.get(field) or ""
        for field in ("author", "author_email", "maintainer", "maintainer_email")
    ]
    return any(ORGANISATIONS.search(link) for link in links) or any(
        EMAIL.search(person) for person in people
    )


def pypi_info(name: str, version: str) -> dict:
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return json.load(response)["info"]
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def unpinned(
    project: dict, lock: dict, info: Callable[[str, str], dict]
) -> list[tuple[str, str]]:
    pins = pinned(project["dependencies"])
    candidates = [
        (name, version)
        for name, version in sorted(runtime_packages(lock, project["name"]))
        if normalise(name) not in pins
    ]
    with ThreadPoolExecutor(max_workers=16) as pool:
        metadata = list(pool.map(lambda package: info(*package), candidates))
    return [
        package for package, data in zip(candidates, metadata) if is_quantinuum(data)
    ]


def readme_packages(readme: str) -> set[str]:
    """Return the package names listed in the README's tools section."""
    lines = readme.splitlines()
    start = lines.index(README_SECTION) + 1
    end = next(
        (i for i in range(start, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    section = "\n".join(lines[start:end])
    return {normalise(name) for name in README_PACKAGE.findall(section)}


def readme_mismatches(project: dict, readme: str) -> tuple[list[str], list[str]]:
    """Return pinned packages missing from the README, and listed ones not pinned."""
    pins, listed = pinned(project["dependencies"]), readme_packages(readme)
    return sorted(pins - listed), sorted(listed - pins)


if __name__ == "__main__":
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    readme = (ROOT / "README.md").read_text()
    foreign = non_pypi_packages(lock, project["name"])
    for name, version, origin in foreign:
        print(
            f"::error file=uv.lock::{name} {version} is locked with {origin}, "
            f"not from {PYPI}; run `just lock` to resolve it from PyPI"
        )
    unlisted, unexpected = readme_mismatches(project, readme)
    for name in unlisted:
        print(
            f"::error file=README.md::List the pinned package {name} under "
            f'"{README_SECTION}"'
        )
    for name in unexpected:
        print(
            f"::error file=README.md::{name} is listed under "
            f'"{README_SECTION}" but is not pinned in project.dependencies'
        )
    # Locked versions from other indexes may not exist on PyPI.
    missing = [] if foreign else unpinned(project, lock, pypi_info)
    for name, version in missing:
        print(
            f"::error file=pyproject.toml::Pin the Quantinuum package {name}: "
            f'add "{name}=={version}" to project.dependencies'
        )
    if foreign or unlisted or unexpected or missing:
        sys.exit(1)
    print(
        "Every package in uv.lock comes from PyPI, and every Quantinuum package "
        "is pinned and listed in the README."
    )
