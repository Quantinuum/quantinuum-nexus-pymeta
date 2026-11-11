"""Resolve and validate the release commit used by the publishing workflow."""

import os
import re
from pathlib import Path

from ghapi.core import GhApi

from github_api import create_client, get_release


def verify_release(tag: str, api: GhApi, event_name: str, workflow_sha: str) -> str:
    if not re.fullmatch(r"v[1-9]\d\.[1-9]\d*\.\d+(?:(?:b|rc)[1-9]\d*)?", tag):
        raise ValueError("Expected a YY.SERIES.PATCH stable, beta, or RC tag")
    release = get_release(api, tag)
    preview = bool(re.search(r"(?:b|rc)[1-9]\d*$", tag))
    if release["prerelease"] != preview:
        raise ValueError("Release status must match the version")
    sha = api.repos.get_commit(ref=tag)["sha"]
    if "rc" in tag and event_name == "workflow_dispatch" and workflow_sha != sha:
        raise ValueError(
            "Run RC retries from the release tag so RC promotion can verify the successful Validate and publish run"
        )
    return sha


if __name__ == "__main__":
    client = create_client()
    sha = verify_release(
        os.environ["TAG"],
        client,
        os.environ["GITHUB_EVENT_NAME"],
        os.environ["GITHUB_SHA"],
    )
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"sha={sha}\n")
