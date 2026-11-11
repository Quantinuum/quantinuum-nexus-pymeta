"""Verify ghapi workflow configuration and repository helpers without network calls."""

import base64
import json

import httpx2
import pytest
from ghapi.core import APIError

from github_api import all_items, create_client, read_file, set_draft


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GH_TOKEN", "app-token")
    monkeypatch.setenv("GITHUB_API_URL", "https://github.example/api/v3")
    monkeypatch.delenv("GITHUB_JWT_TOKEN", raising=False)
    return create_client()


def stub_requests(client, handler):
    client.transport.client = httpx2.Client(transport=httpx2.MockTransport(handler))


def test_client_uses_the_workflow_repository_token_and_configured_host(client):
    def respond(request):
        assert request.method == "PUT"
        assert (
            str(request.url)
            == "https://github.example/api/v3/repos/owner/repo/pulls/1/merge"
        )
        assert request.headers["Authorization"] == "token app-token"
        assert request.headers["X-GitHub-Api-Version"] == "2022-11-28"
        assert json.loads(request.content) == {
            "sha": "tested",
            "merge_method": "squash",
        }
        return httpx2.Response(200, json={"merged": True})

    stub_requests(client, respond)
    assert client.transport.timeout == 30
    assert client.pulls.merge(pull_number=1, sha="tested", merge_method="squash")[
        "merged"
    ]


def test_lists_use_library_pagination_without_following_external_links(client):
    pages = []

    def respond(request):
        assert request.url.host == "github.example"
        page = int(request.url.params["page"])
        pages.append(page)
        assert request.url.params["per_page"] == "100"
        return httpx2.Response(
            200,
            json=[{"id": page}] if page < 3 else [],
            headers={"Link": '<https://other.example/items>; rel="next"'},
        )

    stub_requests(client, respond)
    assert list(all_items(client.pulls.list_reviews, pull_number=1)) == [
        {"id": 1},
        {"id": 2},
    ]
    assert pages == [1, 2, 3]


def test_file_content_and_ref_are_passed_to_the_generated_endpoint(client):
    def respond(request):
        assert request.url.path == "/api/v3/repos/owner/repo/contents/pyproject.toml"
        assert request.url.params["ref"] == "branch/name"
        return httpx2.Response(
            200,
            json={
                "encoding": "base64",
                "content": base64.b64encode(b"[project]\n").decode(),
            },
        )

    stub_requests(client, respond)
    assert read_file(client, "pyproject.toml", "branch/name") == "[project]\n"


def test_unexpected_content_encoding_is_rejected(client):
    stub_requests(
        client,
        lambda request: httpx2.Response(200, json={"encoding": "none", "content": ""}),
    )
    with pytest.raises(ValueError, match="base64"):
        read_file(client, "large-file", "main")


def test_http_errors_keep_the_status_for_release_policies(client):
    stub_requests(
        client, lambda request: httpx2.Response(403, json={"message": "Forbidden"})
    )
    with pytest.raises(APIError) as error:
        client.repos.get()
    assert error.value.status_code == 403


@pytest.mark.parametrize("draft", [True, False])
def test_draft_mutations_use_the_pr_node_id_and_configured_graphql_host(client, draft):
    mutation = "convertPullRequestToDraft" if draft else "markPullRequestReadyForReview"

    def respond(request):
        assert str(request.url) == "https://github.example/api/graphql"
        payload = json.loads(request.content)
        assert mutation in payload["query"]
        assert payload["variables"] == {"id": "PR_7"}
        return httpx2.Response(
            200, json={"data": {mutation: {"pullRequest": {"isDraft": draft}}}}
        )

    stub_requests(client, respond)
    set_draft(client, "PR_7", draft)


def test_graphql_errors_stop_promotion(client):
    stub_requests(
        client,
        lambda request: httpx2.Response(
            200, json={"errors": [{"message": "Forbidden"}]}
        ),
    )
    with pytest.raises(RuntimeError, match="draft status"):
        set_draft(client, "PR_7", True)


def test_explicit_token_overrides_the_default_repository_token(client):
    dispatcher = create_client(token="workflow-token")

    def respond(request):
        assert request.headers["Authorization"] == "token workflow-token"
        assert (
            str(request.url)
            == "https://github.example/api/v3/repos/owner/repo/actions/workflows/publish.yml/dispatches"
        )
        assert json.loads(request.content) == {"ref": "v2026.1.1"}
        return httpx2.Response(204)

    stub_requests(dispatcher, respond)
    dispatcher.actions.create_workflow_dispatch(
        workflow_id="publish.yml", ref="v2026.1.1"
    )


def test_release_lookup_finds_exact_draft_tag_across_pages(client):
    from github_api import get_release

    pages = []

    def respond(request):
        assert request.headers["Authorization"] == "token app-token"
        if "/releases/tags/" in request.url.path:
            return httpx2.Response(404, json={"message": "Not Found"})
        assert request.url.path.endswith("/releases")
        page = int(request.url.params["page"])
        pages.append(page)
        return httpx2.Response(
            200,
            json=[{"tag_name": "v2026.2.0b10", "draft": True}]
            if page == 1
            else [{"tag_name": "v2026.2.0b1", "draft": True, "id": 42}],
        )

    stub_requests(client, respond)
    assert get_release(client, "v2026.2.0b1")["id"] == 42
    assert pages == [1, 2]


@pytest.mark.parametrize("status", [403, 500])
def test_release_lookup_does_not_hide_permission_or_server_errors(client, status):
    from github_api import get_release

    requests = []

    def respond(request):
        requests.append(request.url.path)
        return httpx2.Response(status, json={"message": "Failed"})

    stub_requests(client, respond)
    with pytest.raises(APIError) as error:
        get_release(client, "v2026.2.0b1")
    assert error.value.status_code == status
    assert len(requests) == 1


def test_release_lookup_preserves_missing_tag_error_when_no_draft_matches(client):
    from github_api import get_release

    def respond(request):
        if "/releases/tags/" in request.url.path:
            return httpx2.Response(404, json={"message": "Not Found"})
        return httpx2.Response(200, json=[])

    stub_requests(client, respond)
    with pytest.raises(APIError) as error:
        get_release(client, "v2026.2.0b1")
    assert error.value.status_code == 404


def test_release_lookup_propagates_draft_listing_failure(client):
    from github_api import get_release

    def respond(request):
        status = 404 if "/releases/tags/" in request.url.path else 403
        return httpx2.Response(
            status, json={"message": "Not Found" if status == 404 else "Forbidden"}
        )

    stub_requests(client, respond)
    with pytest.raises(APIError) as error:
        get_release(client, "v2026.2.0b1")
    assert error.value.status_code == 403
