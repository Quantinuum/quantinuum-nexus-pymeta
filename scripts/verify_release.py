"""Resolve and validate the release commit used by the publishing workflow."""

import os
import re
from pathlib import Path

from ghapi.core import GhApi

from github_api import create_client, get_release

TAG = re.compile(r"v[1-9]\d\.[1-9]\d*\.\d+(?:(?:b|rc)[1-9]\d*)?")


def verify_release(
    tag: str, api: GhApi, event_name: str, workflow_sha: str, workflow_ref: str = ""
) -> str:
    if not TAG.fullmatch(tag):
        raise ValueError("Expected a YY.SERIES.PATCH stable, beta, or RC tag")
    # RC promotion identifies a run by its ref, so a release ref must name this tag.
    ref_name = workflow_ref.removeprefix("refs/tags/").removeprefix("refs/heads/")
    if (
        event_name == "workflow_dispatch"
        and TAG.fullmatch(ref_name)
        and workflow_ref != f"refs/tags/{tag}"
    ):
        raise ValueError("A release tag workflow ref must be the tag being published")
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
        os.environ["GITHUB_REF"],
    )
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"sha={sha}\n")
