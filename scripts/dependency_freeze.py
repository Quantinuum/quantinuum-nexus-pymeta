"""Hold Renovate updates to main during the release-candidate freeze.

Runs in CI for pull requests and merge queue groups. Renovate PRs stay open and
are retested once `.github/preview.json` returns to a beta channel.
"""

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE_BRANCH = re.compile(
    r"refs/heads/gh-readonly-queue/(?P<base>.+)/pr-(?P<number>\d+)-[0-9a-f]+"
)


def frozen(base: str, head: str, preview: dict) -> bool:
    return (
        base == "main" and head.startswith("renovate/") and preview["channel"] == "rc"
    )


def pull_request_branches(event_name: str, event: dict) -> tuple[str, str]:
    if event_name == "pull_request":
        pr = event["pull_request"]
        return pr["base"]["ref"], pr["head"]["ref"]
    match = QUEUE_BRANCH.fullmatch(event["merge_group"]["head_ref"])
    if not match:
        raise ValueError("Unexpected merge queue branch")
    from github_api import create_client

    pr = create_client().pulls.get(pull_number=int(match["number"]))
    return match["base"], pr["head"]["ref"]


if __name__ == "__main__":
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    base, head = pull_request_branches(os.environ["GITHUB_EVENT_NAME"], event)
    preview = json.loads((ROOT / ".github/preview.json").read_text())
    if frozen(base, head, preview):
        print(
            f"::error::Renovate updates to main are held during the {preview['target']} "
            "RC freeze. They resume when the next beta target is set."
        )
        sys.exit(1)
