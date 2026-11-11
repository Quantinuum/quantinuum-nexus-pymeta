"""Check GitHub asset publication and retries without making network requests."""

import hashlib
import json
import re
import runpy
from pathlib import Path
from unittest.mock import Mock

import httpx2
import pytest
from ghapi.core import APIError, GhApi

import publish_release


@pytest.fixture
def publication(tmp_path):
    files = {
        "quantinuum_nexus-2026.1.0-py3-none-any.whl": b"wheel",
        "quantinuum_nexus-2026.1.0.tar.gz": b"source",
    }
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
    api = Mock()
    api.repos.get_commit.return_value = {"sha": "verified"}
    api.repos.get_release_by_tag.return_value = {
        "id": 7,
        "draft": False,
        "upload_url": "https://uploads.github.com/releases/7/assets{?name,label}",
    }
    api.repos.list_release_assets.side_effect = lambda **kwargs: []
    api.side_effect = lambda *args, **kwargs: {
        "state": "uploaded",
        "digest": "sha256:" + hashlib.sha256(kwargs["data"]).hexdigest(),
    }
    return api, tmp_path, files


def test_uploads_both_distributions_as_binary_data(publication):
    api, directory, files = publication
    publish_release.publish_assets(api, "v2026.1.0", "verified", directory)
    assert api.call_count == 2
    for call in api.call_args_list:
        assert call.args == ("https://uploads.github.com/releases/7/assets", "POST")
        assert call.kwargs["headers"] == {"Content-Type": "application/octet-stream"}
        assert call.kwargs["data"] == files[call.kwargs["query"]["name"]]


def test_real_client_uploads_authenticated_binary_requests(publication):
    _, directory, files = publication
    api = GhApi(owner="owner", repo="repo", token="test-token", sync=True)
    uploaded = []

    def respond(request):
        assert request.headers["Authorization"] == "token test-token"
        if request.url.path.endswith("/actions/workflows/maintenance.yml/dispatches"):
            assert request.method == "POST"
            assert json.loads(request.content) == {"ref": "main"}
            return httpx2.Response(204)
        if request.method == "POST":
            assert request.url.host == "uploads.github.com"
            assert request.headers["Content-Type"] == "application/octet-stream"
            name = request.url.params["name"]
            assert request.content == files[name]
            uploaded.append(name)
            return httpx2.Response(
                201,
                json={
                    "state": "uploaded",
                    "digest": "sha256:" + hashlib.sha256(request.content).hexdigest(),
                },
            )
        if "/commits/" in request.url.path:
            return httpx2.Response(200, json={"sha": "verified"})
        if "/releases/tags/" in request.url.path:
            return httpx2.Response(
                200,
                json={
                    "id": 7,
                    "draft": False,
                    "upload_url": "https://uploads.github.com/repos/owner/repo/releases/7/assets{?name,label}",
                },
            )
        assert request.url.path.endswith("/releases/7/assets")
        return httpx2.Response(200, json=[])

    api.transport.client = httpx2.Client(transport=httpx2.MockTransport(respond))
    publish_release.publish_assets(api, "v2026.1.0", "verified", directory)
    assert set(uploaded) == set(files)


@pytest.mark.parametrize("existing_count", [1, 2])
def test_retry_reuses_matching_assets_and_only_uploads_missing_files(
    publication, existing_count
):
    api, directory, files = publication
    assets = [
        {
            "name": name,
            "state": "uploaded",
            "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
        }
        for name, data in list(files.items())[:existing_count]
    ]
    api.repos.list_release_assets.side_effect = lambda **kwargs: (
        assets if kwargs["page"] == 1 else []
    )
    publish_release.publish_assets(api, "v2026.1.0", "verified", directory)
    assert api.call_count == 2 - existing_count


@pytest.mark.parametrize(
    "state,digest",
    [
        ("uploaded", "sha256:different"),
        ("uploaded", None),
        ("starter", "sha256:different"),
    ],
)
def test_existing_conflict_fails_before_any_upload(publication, state, digest):
    api, directory, files = publication
    assets = [{"name": list(files)[1], "state": state, "digest": digest}]
    api.repos.list_release_assets.side_effect = lambda **kwargs: (
        assets if kwargs["page"] == 1 else []
    )
    with pytest.raises(ValueError, match="Existing release asset differs"):
        publish_release.publish_assets(api, "v2026.1.0", "verified", directory)
    api.assert_not_called()


@pytest.mark.parametrize("problem", ["moved", "missing-wheel", "extra-wheel"])
def test_rejects_unverified_tags_drafts_and_incomplete_builds(publication, problem):
    api, directory, files = publication
    if problem == "moved":
        api.repos.get_commit.return_value = {"sha": "different"}
    elif problem == "missing-wheel":
        (directory / next(iter(files))).unlink()
    else:
        (directory / "extra.whl").write_bytes(b"extra")
    with pytest.raises(ValueError):
        publish_release.publish_assets(api, "v2026.1.0", "verified", directory)
    api.assert_not_called()


def test_failed_upload_stops_without_deleting_assets(publication):
    api, directory, _ = publication
    api.side_effect = APIError("Upload failed", status_code=502)
    with pytest.raises(APIError):
        publish_release.publish_assets(api, "v2026.1.0", "verified", directory)
    assert api.call_count == 1
    api.repos.delete_release_asset.assert_not_called()


def test_uploaded_digest_is_verified(publication):
    api, directory, _ = publication
    api.side_effect = None
    api.return_value = {"state": "uploaded", "digest": "sha256:different"}
    with pytest.raises(ValueError, match="failed verification"):
        publish_release.publish_assets(api, "v2026.1.0", "verified", directory)
    assert api.call_count == 1


@pytest.mark.parametrize("external_directory", [False, True])
def test_cli_uses_the_verified_release_commit(
    publication, monkeypatch, external_directory
):
    api, directory, _ = publication
    (directory / "dist").mkdir()
    for path in directory.glob("quantinuum*"):
        path.rename(directory / "dist" / path.name)
    if external_directory:
        tooling = directory / "tooling"
        tooling.mkdir()
        monkeypatch.chdir(tooling)
        monkeypatch.setenv("DIST_DIR", str(directory / "dist"))
    else:
        monkeypatch.chdir(directory)
        monkeypatch.delenv("DIST_DIR", raising=False)
    monkeypatch.setenv("TAG", "v2026.1.0")
    monkeypatch.setenv("RELEASE_SHA", "verified")
    monkeypatch.setattr("github_api.create_client", lambda: api)
    runpy.run_path(str(Path(publish_release.__file__)), run_name="__main__")
    assert api.call_count == 2


@pytest.mark.parametrize(
    "newest,tag,preview,expected",
    [
        ("v2026.2.0", "v2026.1.1", False, "false"),
        ("v2026.2.0", "v2026.2.1", False, "true"),
        (None, "v2026.1.0", False, "true"),
        (None, "v2026.2.0rc1", True, "false"),
    ],
)
def test_draft_publication_preserves_latest_for_older_series(
    publication, newest, tag, preview, expected
):
    api, directory, _ = publication
    api.repos.get_release_by_tag.return_value.update(draft=True, prerelease=preview)
    api.repos.list_releases.side_effect = lambda page, per_page: (
        [{"tag_name": newest, "draft": False, "prerelease": False}]
        if newest and page == 1
        else []
    )
    publish_release.publish_assets(api, tag, "verified", directory)
    assert api.repos.update_release.call_args.kwargs["make_latest"] == expected
    assert api.repos.update_release.call_args.kwargs["draft"] is False


def test_failed_draft_upload_never_publishes_release(publication):
    api, directory, _ = publication
    api.repos.get_release_by_tag.return_value["draft"] = True
    api.side_effect = APIError("Upload failed", status_code=502)
    with pytest.raises(APIError):
        publish_release.publish_assets(api, "v2026.1.1", "verified", directory)
    api.repos.update_release.assert_not_called()


def test_publication_job_queues_all_tags_in_one_repository_group():
    workflow = (
        Path(__file__).resolve().parents[2] / ".github/workflows/publish.yml"
    ).read_text()
    publish_job = workflow.split("\n  publish:\n", 1)[1].split("\n  pypi:\n", 1)[0]
    concurrency = re.search(
        r"^    concurrency:\n((?:      [^\n]*\n)+)", publish_job, re.MULTILINE
    )
    assert concurrency is not None, "Publication must be serialized across tags"
    settings = dict(line.strip().split(": ", 1) for line in concurrency[1].splitlines())
    assert settings["group"] and "${{" not in settings["group"], (
        "All tags must share the same publication lock"
    )
    assert settings["cancel-in-progress"] == "false", (
        "Publishing a release must not cancel another publication"
    )
    assert settings["queue"] == "max", (
        "Multiple queued releases must not replace each other"
    )


def test_publication_finds_draft_missing_from_tag_lookup(publication):
    api, directory, _ = publication
    api.repos.get_release_by_tag.side_effect = APIError("Not Found", status_code=404)
    draft = {
        "id": 42,
        "draft": True,
        "prerelease": True,
        "tag_name": "v2026.2.0b1",
        "upload_url": "https://uploads.github.com/releases/42/assets",
    }
    api.repos.list_releases.side_effect = lambda page, per_page: (
        [draft] if page == 1 else []
    )
    publish_release.publish_assets(api, "v2026.2.0b1", "verified", directory)
    api.repos.update_release.assert_called_once_with(
        release_id=42, draft=False, make_latest="false"
    )
    api.repos.create_release.assert_not_called()
