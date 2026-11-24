"""Require an exact pin for every Quantinuum package the metapackage installs.

A package counts as Quantinuum-managed when its PyPI metadata for the locked
version links to github.com/Quantinuum or github.com/CQCL, or an author or
maintainer uses a quantinuum.com address.
"""

import json
import re
import sys
import time
import tomllib
import urllib.request
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORGANISATIONS = re.compile(r"github\.com/(quantinuum|cqcl)(/|$)", re.IGNORECASE)
EMAIL = re.compile(r"@quantinuum\.com\b", re.IGNORECASE)


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
    return [
        (name, version)
        for name, version in sorted(runtime_packages(lock, project["name"]))
        if normalise(name) not in pins and is_quantinuum(info(name, version))
    ]


if __name__ == "__main__":
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    missing = unpinned(project, lock, pypi_info)
    for name, version in missing:
        print(
            f"::error file=pyproject.toml::Pin the Quantinuum package {name}: "
            f'add "{name}=={version}" to project.dependencies'
        )
    if missing:
        sys.exit(1)
    print("Every Quantinuum package in uv.lock is pinned.")
