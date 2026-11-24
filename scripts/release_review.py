"""Require a maintainer's approval of release-branch PRs that automation cannot merge.

Every release-branch PR is opened by the release bot, so GitHub's approval count
cannot distinguish unattended patches from changes needing review. This check
passes for eligible Renovate patch updates and Release Please patch releases,
and otherwise requires an approval of the PR's current head commit from another
user with write access, with no outstanding change requests.
"""

import json
import os
import sys
import tomllib
from pathlib import Path

from ghapi.core import GhApi

from github_api import all_items, create_client, read_file
from release_automerge import patch_upgrades, pins, release_pr_eligible
from release_policy import BRANCH, supported_branches

DEPENDENCY_FILES = {"pyproject.toml", "uv.lock"}
WRITE_PERMISSIONS = {"admin", "maintain", "write"}


def without_dependencies(text: str) -> dict:
    data = tomllib.loads(text)
    data["project"].pop("dependencies", None)
    return data


def renovate_patch_eligible(api: GhApi, pr: dict, release_bot: str) -> bool:
    """Allow a Renovate PR that only applies patch upgrades to existing pins."""
    if (
        pr["user"]["login"] != release_bot
        or not pr["head"]["ref"].startswith("renovate/")
        or (pr["head"].get("repo") or {}).get("full_name")
        != pr["base"]["repo"]["full_name"]
        or pr["base"]["ref"] not in supported_branches(api)
    ):
        return False
    files = {
        file["filename"]
        for file in all_items(api.pulls.list_files, pull_number=pr["number"])
    }
    if not files <= DEPENDENCY_FILES:
        return False
    base = read_file(api, "pyproject.toml", pr["base"]["sha"])
    head = read_file(api, "pyproject.toml", pr["head"]["sha"])
    before, after = pins(base), pins(head)
    return (
        without_dependencies(base) == without_dependencies(head)
        and before != after
        and patch_upgrades(before, after)
    )


def approved(api: GhApi, pr: dict) -> bool:
    latest = {}
    for review in all_items(api.pulls.list_reviews, pull_number=pr["number"]):
        if review["state"] != "COMMENTED" and review.get("user"):
            latest[review["user"]["login"]] = review
    reviewers = {
        login: review
        for login, review in latest.items()
        if login != pr["user"]["login"]
        and api.repos.get_collaborator_permission_level(username=login)["permission"]
        in WRITE_PERMISSIONS
    }
    if any(review["state"] == "CHANGES_REQUESTED" for review in reviewers.values()):
        return False
    return any(
        review["state"] == "APPROVED" and review["commit_id"] == pr["head"]["sha"]
        for review in reviewers.values()
    )


def review_satisfied(api: GhApi, number: int, release_bot: str) -> bool:
    pr = api.pulls.get(pull_number=number)
    if not BRANCH.fullmatch(pr["base"]["ref"]):
        return True
    try:
        eligible = release_pr_eligible(api, pr, release_bot)
    except ValueError:
        eligible = False
    if eligible or renovate_patch_eligible(api, pr, release_bot):
        print(f"PR #{number} is an eligible patch update and may merge unattended.")
        return True
    if approved(api, pr):
        print(f"PR #{number} is approved at its current commit.")
        return True
    return False


if __name__ == "__main__":
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    number = event["pull_request"]["number"]
    if not review_satisfied(create_client(), number, os.environ["RELEASE_BOT"]):
        print(
            f"::error::Release-branch PR #{number} requires a maintainer's approval "
            "of its current commit."
        )
        sys.exit(1)
