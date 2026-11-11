"""Approve and merge eligible dependency and release PRs after successful CI."""

import json
import os
import re
from pathlib import Path

from ghapi.core import APIError, GhApi

from github_api import all_items, create_client, read_file

TOOLS = ("guppylang", "guppyft", "guppyalgos", "selene-sim", "pytket", "qnexus")
PROJECT_VERSION = re.compile(r'^version = "(\d+\.\d+\.\d+)"$', re.MULTILINE)


def package_version(text: str):
    match = PROJECT_VERSION.search(text)
    return match[1] if match else None


def version_parts(version: str | None):
    return (
        tuple(map(int, version.split(".")))
        if version and re.fullmatch(r"\d+\.\d+\.\d+", version)
        else None
    )


def dependency_update_allowed(base: str, head: str, beta: bool) -> bool:
    changed = False
    for tool in TOOLS:
        pattern = re.compile(rf'"{re.escape(tool)}==([^"\s]+)"')
        before, after = pattern.findall(base), pattern.findall(head)
        if len(before) != 1 or len(after) != 1:
            return False
        old, new = version_parts(before[0]), version_parts(after[0])
        if old is None or new is None:
            return False
        if old != new:
            changed = True
            if new <= old or (
                not beta and (old[0] != new[0] or (old[0] == 0 and old[1] != new[1]))
            ):
                return False
        base = pattern.sub(f'"{tool}==VERSION"', base)
        head = pattern.sub(f'"{tool}==VERSION"', head)
    return changed and base == head


def beta_state(api: GhApi):
    sha = api.git.get_ref(ref="heads/next")["object"]["sha"]
    config = json.loads(read_file(api, ".github/preview.json", sha))
    target = config["target"]
    if config["channel"] != "beta" or not re.fullmatch(r"20\d{2}\.[1-9]\d*\.0", target):
        return None
    tags = api.git.list_matching_refs(ref=f"tags/v{target}")
    if any(
        tag["ref"] == f"refs/tags/v{target}"
        or re.fullmatch(rf"refs/tags/v{re.escape(target)}rc[1-9]\d*", tag["ref"])
        for tag in tags
    ):
        return None
    return sha


def stable_frozen(api: GhApi, base_sha: str, version: str | None) -> bool:
    try:
        candidate = json.loads(
            read_file(api, ".github/stable-candidate.json", base_sha)
        )
    except APIError as error:
        if error.status_code != 404:
            raise
        return False
    if candidate.get("version") == version:
        try:
            api.git.get_ref(ref=f"tags/v{candidate['version']}")
        except APIError as error:
            if error.status_code != 404:
                raise
            return True
    return False


def release_update_allowed(base: str, head: str, manifest: dict) -> bool:
    before, after = (
        version_parts(package_version(base)),
        version_parts(package_version(head)),
    )
    first_release = not manifest.get(".") and package_version(head) == "2026.1.0"
    patch = before and after and before[:2] == after[:2] and after[2] == before[2] + 1
    return bool(
        (first_release or patch)
        and PROJECT_VERSION.sub('version = "VERSION"', base)
        == PROJECT_VERSION.sub('version = "VERSION"', head)
    )


def merge_updates(run: dict, api: GhApi, release_bot: str, repository: str):
    if run.get("event") != "pull_request" or run.get("conclusion") != "success":
        return
    for candidate in run.get("pull_requests", []):
        number = candidate["number"]
        pr = api.pulls.get(pull_number=number)
        if (
            pr["state"] != "open"
            or pr["draft"]
            or pr["base"]["ref"] not in ("main", "next")
            or (pr["head"].get("repo") or {}).get("full_name") != repository
            or pr["head"]["sha"] != run["head_sha"]
        ):
            continue
        files = {
            file["filename"]
            for file in all_items(api.pulls.list_files, pull_number=number)
        }
        base = read_file(api, "pyproject.toml", pr["base"]["sha"])
        head = read_file(api, "pyproject.toml", pr["head"]["sha"])
        is_next = pr["base"]["ref"] == "next"
        eligible = False
        tested_beta_base = None
        if (
            pr["user"]["login"] == "dependabot[bot]"
            and files <= {"pyproject.toml", "uv.lock"}
            and "pyproject.toml" in files
        ):
            if is_next:
                tested_beta_base = beta_state(api)
                if (
                    not tested_beta_base
                    or (candidate.get("base") or {}).get("sha") != tested_beta_base
                ):
                    print(
                        "Next requires an active beta cycle and CI against its current base commit."
                    )
                    continue
            elif stable_frozen(api, pr["base"]["sha"], package_version(base)):
                print(
                    "Dependency updates are frozen while the release is being promoted."
                )
                continue
            eligible = dependency_update_allowed(base, head, is_next)
        elif (
            not is_next
            and pr["user"]["login"] == release_bot
            and pr["head"]["ref"].startswith("release-please--branches--main")
            and files
            <= {
                "pyproject.toml",
                "uv.lock",
                "CHANGELOG.md",
                ".release-please-manifest.json",
            }
        ):
            manifest = json.loads(
                read_file(api, ".release-please-manifest.json", pr["base"]["sha"])
            )
            eligible = release_update_allowed(base, head, manifest)
        if not eligible:
            print(f"PR #{number} requires manual review.")
            continue
        if is_next:
            if beta_state(api) != tested_beta_base:
                print("The beta branch changed after validation; waiting for fresh CI.")
                continue
            reviews = all_items(api.pulls.list_reviews, pull_number=number)
            if not any(
                review["user"]["login"] == release_bot
                and review["commit_id"] == pr["head"]["sha"]
                and review["state"] == "APPROVED"
                for review in reviews
            ):
                api.pulls.create_review(
                    pull_number=number,
                    commit_id=pr["head"]["sha"],
                    event="APPROVE",
                    body="Automated approval for the next beta: exact dependency upgrades passed installation CI. "
                    "Breaking component upgrades are allowed in this channel; behavioral compatibility "
                    "is not established by installation tests.",
                )
            if api.git.get_ref(ref="heads/next")["object"]["sha"] != tested_beta_base:
                print("Next changed during approval; waiting for fresh CI.")
                continue
        result = api.pulls.merge(
            pull_number=number,
            sha=pr["head"]["sha"],
            merge_method="squash",
            commit_title=f"{pr['title']} (#{number})",
        )
        if not result["merged"]:
            raise RuntimeError(result["message"])


if __name__ == "__main__":
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    client = create_client()
    merge_updates(
        event["workflow_run"],
        client,
        client.users.get_authenticated()["login"],
        os.environ["GITHUB_REPOSITORY"],
    )
