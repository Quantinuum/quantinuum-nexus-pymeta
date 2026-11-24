"""Queue eligible Release Please patch PRs for automatic merging.

GitHub auto-merge merges the PR once required checks pass on a branch that is up
to date with its release branch, so the release is tested as it will land. Each run
first disables auto-merge that an earlier revision enabled, then re-evaluates.
"""

import json
import os
import re
import subprocess
import time
import tomllib

from ghapi.core import APIError, GhApi

from github_api import all_items, create_client, read_file
from release_policy import BRANCH, check_release_branch, supported_branches

PROJECT_VERSION = re.compile(r'^version = "(\d+\.\d+\.\d+)"$', re.MULTILINE)
RELEASE_FILES = {
    "pyproject.toml",
    "uv.lock",
    "CHANGELOG.md",
    ".release-please-manifest.json",
}


def package_version(text: str):
    match = PROJECT_VERSION.search(text)
    return match[1] if match else None


def version_parts(version: str | None):
    return (
        tuple(map(int, version.split(".")))
        if version and re.fullmatch(r"\d+\.\d+\.\d+", version)
        else None
    )


def release_update_allowed(base: str, head: str, manifest: dict) -> bool:
    """Allow only a patch version bump with no other pyproject changes."""
    before, after = (
        version_parts(package_version(base)),
        version_parts(package_version(head)),
    )
    patch = before and after and before[:2] == after[:2] and after[2] == before[2] + 1
    return bool(
        patch
        and manifest.get(".") == package_version(base)
        and PROJECT_VERSION.sub('version = "VERSION"', base)
        == PROJECT_VERSION.sub('version = "VERSION"', head)
    )


def pins(text: str) -> dict | None:
    result = {}
    for requirement in tomllib.loads(text)["project"]["dependencies"]:
        name, separator, value = requirement.partition("==")
        parsed = version_parts(value)
        if not separator or parsed is None or name in result:
            return None
        result[name] = parsed
    return result


def patch_upgrades(before: dict | None, after: dict | None) -> bool:
    """Whether every pin is unchanged or a patch upgrade, with none added or removed."""
    if before is None or after is None or before.keys() != after.keys():
        return False
    return all(
        before[name] == after[name]
        or (after[name] > before[name] and after[name][:2] == before[name][:2])
        for name in before
    )


def release_dependencies_allowed(api: GhApi, head: str, manifest: dict) -> bool:
    """Allow pins that are unchanged or patch upgrades since the previous release."""
    version = manifest.get(".")
    if not version:
        return False
    try:
        previous = read_file(api, "pyproject.toml", f"v{version}")
    except APIError as error:
        if error.status_code != 404:
            raise
        return False
    return patch_upgrades(pins(previous), pins(head))


def release_pr_eligible(api: GhApi, pr: dict, release_bot: str) -> bool:
    branch = pr["base"]["ref"]
    if (
        pr["state"] != "open"
        or pr["draft"]
        or not BRANCH.fullmatch(branch)
        or pr["user"]["login"] != release_bot
        or pr["head"]["ref"] != "release-please--branches--" + branch
        or (pr["head"].get("repo") or {}).get("full_name")
        != pr["base"]["repo"]["full_name"]
    ):
        return False
    if branch not in supported_branches(api):
        print("This series requires manual maintenance.")
        return False
    files = {
        file["filename"]
        for file in all_items(api.pulls.list_files, pull_number=pr["number"])
    }
    if not files <= RELEASE_FILES:
        return False
    base = read_file(api, "pyproject.toml", pr["base"]["sha"])
    head = read_file(api, "pyproject.toml", pr["head"]["sha"])
    manifest = json.loads(
        read_file(api, ".release-please-manifest.json", pr["base"]["sha"])
    )
    if not (
        release_update_allowed(base, head, manifest)
        and release_dependencies_allowed(api, head, manifest)
    ):
        return False
    check_release_branch(branch, package_version(head))
    return True


def mergeable_state(api: GhApi, pr: dict) -> str:
    """Return the PR's mergeable state, waiting while GitHub computes it."""
    state = pr.get("mergeable_state", "unknown")
    for _ in range(5):
        if state != "unknown":
            break
        time.sleep(3)
        state = api.pulls.get(pull_number=pr["number"]).get(
            "mergeable_state", "unknown"
        )
    return state


def queue_release(api: GhApi, number: int, release_bot: str, repository: str):
    pr = api.pulls.get(pull_number=number)
    command = ["gh", "pr", "merge", str(number), "--repo", repository]
    # Auto-merge survives pushes, so clear it before evaluating this revision;
    # if evaluation fails, a newer revision is not merged unreviewed.
    if pr.get("auto_merge"):
        subprocess.run(command + ["--disable-auto"], check=True)
    if not release_pr_eligible(api, pr, release_bot):
        print(f"Release PR #{number} requires manual review.")
        return
    merge = ["--squash", "--match-head-commit", pr["head"]["sha"]]
    # GitHub cannot enable auto-merge on a PR that is already mergeable.
    if mergeable_state(api, pr) == "clean":
        print(f"Merging release PR #{number}; its checks have passed.")
        subprocess.run(command + merge, check=True)
    else:
        print(f"Enabling auto-merge for release PR #{number}.")
        subprocess.run(command + ["--auto"] + merge, check=True)


if __name__ == "__main__":
    client = create_client()
    queue_release(
        client,
        int(os.environ["PR_NUMBER"]),
        client.users.get_authenticated()["login"],
        os.environ["GITHUB_REPOSITORY"],
    )
