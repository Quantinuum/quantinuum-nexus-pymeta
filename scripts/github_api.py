"""Configure ghapi for workflows and provide repository content helpers."""

import base64
import os

from ghapi.core import GhApi
from ghapi.page import sync_paged


def create_client(token: str | None = None) -> GhApi:
    owner, repo = os.environ["GITHUB_REPOSITORY"].split("/", 1)
    client = GhApi(
        owner=owner,
        repo=repo,
        token=os.environ["GH_TOKEN"] if token is None else token,
        gh_host=os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/"),
        timeout=30,
        sync=True,
    )
    client.headers["X-GitHub-Api-Version"] = "2022-11-28"
    return client


def all_items(operation, **parameters):
    """Iterate every item from a paginated list endpoint."""
    for page in sync_paged(operation, per_page=100, **parameters):
        yield from page


def read_file(api: GhApi, path: str, ref: str) -> str:
    content = api.repos.get_content(path=path, ref=ref)
    if content["encoding"] != "base64":
        raise ValueError("Expected base64-encoded repository content")
    return base64.b64decode(content["content"]).decode("utf-8")


def set_draft(api: GhApi, node_id: str, draft: bool):
    """Change a pull request's draft status, failing on GraphQL errors."""
    mutation = "convertPullRequestToDraft" if draft else "markPullRequestReadyForReview"
    host = api.gh_host
    endpoint = (
        host.removesuffix("/api/v3") + "/api/graphql"
        if host.endswith("/api/v3")
        else host + "/graphql"
    )
    result = api(
        endpoint,
        "POST",
        data={
            "query": f"mutation($id: ID!) {{ {mutation}(input: {{pullRequestId: $id}}) {{ pullRequest {{ isDraft }} }} }}",
            "variables": {"id": node_id},
        },
    )
    if result.get("errors"):
        raise RuntimeError(
            f"Cannot change promotion PR draft status: {result['errors']}"
        )
    if result["data"][mutation]["pullRequest"]["isDraft"] != draft:
        raise RuntimeError(
            "GitHub did not apply the requested promotion PR draft status"
        )
