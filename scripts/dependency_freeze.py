"""Hold Renovate dependency updates to main during the release-candidate freeze.

Runs in CI for pull requests and merge queue groups. Renovate PRs that change the
package metadata or lockfile stay open and are retested once
`.github/preview.json` returns to a beta channel. Tooling-only updates, such as
workflow actions, are not held.
"""

import json
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE_BRANCH = re.compile(
    r"refs/heads/gh-readonly-queue/(?P<base>.+)/pr-(?P<number>\d+)-[0-9a-f]+"
)
DEPENDENCY_FILES = {"pyproject.toml", "uv.lock"}


def frozen(base: str, head: str, preview: dict, files: Callable[[], set[str]]) -> bool:
    if base != "main" or not head.startswith("renovate/") or preview["channel"] != "rc":
        return False
    return bool(files() & DEPENDENCY_FILES)


def pull_request(event_name: str, event: dict) -> tuple[str, str, int]:
    """Return the base branch, head branch, and number of the PR being tested."""
    if event_name == "pull_request":
        pr = event["pull_request"]
        return pr["base"]["ref"], pr["head"]["ref"], pr["number"]
    match = QUEUE_BRANCH.fullmatch(event["merge_group"]["head_ref"])
    if not match:
        raise ValueError("Unexpected merge queue branch")
    from github_api import create_client

    pr = create_client().pulls.get(pull_number=int(match["number"]))
    return match["base"], pr["head"]["ref"], int(match["number"])


def changed_files(number: int) -> set[str]:
    from github_api import all_items, create_client

    api = create_client()
    return {
        file["filename"] for file in all_items(api.pulls.list_files, pull_number=number)
    }


if __name__ == "__main__":
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    base, head, number = pull_request(os.environ["GITHUB_EVENT_NAME"], event)
    preview = json.loads((ROOT / ".github/preview.json").read_text())
    if frozen(base, head, preview, lambda: changed_files(number)):
        print(
            f"::error::Renovate dependency updates to main are held during the {preview['target']} "
            "RC freeze. They resume when the next beta target is set."
        )
        sys.exit(1)
