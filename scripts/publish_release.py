"""Attach built distributions to a GitHub release without replacing existing assets."""

import hashlib
import os
from pathlib import Path

from ghapi.core import GhApi

from github_api import all_items, create_client
from release_policy import published_series


def publish_assets(api: GhApi, tag: str, sha: str, directory: Path):
    if api.repos.get_commit(ref=tag)["sha"] != sha:
        raise ValueError("The release tag moved after validation")
    release = api.repos.get_release_by_tag(tag=tag)
    wheels = list(directory.glob("*.whl"))
    sources = list(directory.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        raise ValueError("Expected one wheel and one source distribution")
    assets = {
        asset["name"]: asset
        for asset in all_items(api.repos.list_release_assets, release_id=release["id"])
    }
    files = [(path, path.read_bytes()) for path in wheels + sources]
    for path, data in files:
        existing = assets.get(path.name)
        if existing is not None and (
            existing["state"] != "uploaded"
            or existing.get("digest") != "sha256:" + hashlib.sha256(data).hexdigest()
        ):
            raise ValueError(f"Existing release asset differs: {path.name}")
    for path, data in files:
        if path.name in assets:
            print(f"Reusing {path.name}")
            continue
        asset = api(
            release["upload_url"].split("{", 1)[0],
            "POST",
            headers={"Content-Type": "application/octet-stream"},
            query={"name": path.name},
            data=data,
        )
        if (
            asset["state"] != "uploaded"
            or asset.get("digest") != "sha256:" + hashlib.sha256(data).hexdigest()
        ):
            raise ValueError(f"Uploaded release asset failed verification: {path.name}")
        print(f"Uploaded {path.name}")
    if release["draft"]:
        if api.repos.get_commit(ref=tag)["sha"] != sha:
            raise ValueError("The release tag moved before publication")
        stable = published_series(api) if not release["prerelease"] else {}
        newest = next(iter(stable.values()), None)
        latest = not release["prerelease"] and (
            newest is None
            or tuple(map(int, tag[1:].split(".")))
            >= tuple(map(int, newest[1:].split(".")))
        )
        api.repos.update_release(
            release_id=release["id"],
            draft=False,
            make_latest="true" if latest else "false",
        )
    if not release.get("prerelease", False):
        api.actions.create_workflow_dispatch(workflow_id="maintenance.yml", ref="main")


if __name__ == "__main__":
    publish_assets(
        create_client(), os.environ["TAG"], os.environ["RELEASE_SHA"], Path("dist")
    )
