"""Check the version and release-status gates before release publication."""

import runpy
from pathlib import Path
from unittest.mock import Mock

import pytest

import verify_release


@pytest.mark.parametrize(
    "tag,preview,draft,event,workflow_sha,allowed",
    [
        ("v26.1.0", False, False, "release", "tag", True),
        ("v26.2.0b1", True, False, "release", "tag", True),
        ("v26.2.0b1", True, True, "workflow_dispatch", "main", True),
        ("v26.2.0rc1", True, False, "release", "tag", True),
        ("v26.2.0rc1", True, False, "workflow_dispatch", "tag", True),
        ("v26.2.0rc1", True, False, "workflow_dispatch", "main", False),
        ("v26.2.0", True, False, "release", "tag", False),
        ("v26.2.0b1", False, False, "release", "tag", False),
        ("v26.2.0rc1", True, True, "release", "tag", True),
        ("v26.5.0", False, False, "release", "tag", True),
        ("v26.12.1", False, False, "release", "tag", True),
        ("v26.12.0b1", True, False, "release", "tag", True),
        ("v26.12.0rc1", True, False, "release", "tag", True),
        ("v27.1.0", False, False, "release", "tag", True),
        ("v2026.1.0", False, False, "release", "tag", False),
        ("v26.0.0", False, False, "release", "tag", False),
        ("v26.01.0", False, False, "release", "tag", False),
        ("v26.2.0.dev1", True, False, "release", "tag", False),
    ],
)
def test_only_matching_published_stable_beta_and_rc_versions_are_allowed(
    tag, preview, draft, event, workflow_sha, allowed
):
    api = Mock(repository="owner/repo")
    api.repos.get_release_by_tag.return_value = {"draft": draft, "prerelease": preview}
    api.repos.get_commit.return_value = {"sha": "tag"}
    if allowed:
        assert verify_release.verify_release(tag, api, event, workflow_sha) == "tag"
    else:
        with pytest.raises(ValueError):
            verify_release.verify_release(tag, api, event, workflow_sha)


@pytest.mark.parametrize(
    "ref,allowed",
    [
        ("refs/tags/v26.2.0rc1", True),
        ("refs/heads/main", True),
        ("refs/tags/v26.2.0rc2", False),
        ("refs/heads/v26.2.0rc2", False),
    ],
)
def test_dispatches_from_a_release_tag_must_use_the_published_tag(ref, allowed):
    api = Mock(repository="owner/repo")
    api.repos.get_release_by_tag.return_value = {"draft": False, "prerelease": True}
    api.repos.get_commit.return_value = {"sha": "tag"}
    if allowed:
        verify_release.verify_release(
            "v26.2.0rc1", api, "workflow_dispatch", "tag", ref
        )
    else:
        with pytest.raises(ValueError, match="tag being published"):
            verify_release.verify_release(
                "v26.2.0rc1", api, "workflow_dispatch", "tag", ref
            )


def test_cli_writes_the_verified_sha_to_the_workflow_output(tmp_path, monkeypatch):
    api = Mock(repository="owner/repo")
    api.repos.get_release_by_tag.return_value = {"draft": False, "prerelease": False}
    api.repos.get_commit.return_value = {"sha": "verified"}
    output = tmp_path / "output"
    for name, value in {
        "TAG": "v26.1.0",
        "GITHUB_REPOSITORY": "owner/repo",
        "GH_TOKEN": "token",
        "GITHUB_EVENT_NAME": "release",
        "GITHUB_SHA": "verified",
        "GITHUB_REF": "refs/tags/v26.1.0",
        "GITHUB_OUTPUT": str(output),
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr("github_api.create_client", lambda: api)
    runpy.run_path(str(Path(verify_release.__file__)), run_name="__main__")
    assert output.read_text() == "sha=verified\n"
