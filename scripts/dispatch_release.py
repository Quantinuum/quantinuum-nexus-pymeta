"""Start validation and publication using the exact release tag as workflow ref."""

import os

from github_api import create_client
from verify_release import verify_release


def dispatch_release(api, tag: str):
    sha = verify_release(tag, api, "automation", "")
    api.actions.create_workflow_dispatch(
        workflow_id="publish.yml", ref=tag, inputs={"tag": tag}
    )
    print(f"Queued validation for {tag} at {sha}")


if __name__ == "__main__":
    dispatch_release(create_client(), os.environ["TAG"])
