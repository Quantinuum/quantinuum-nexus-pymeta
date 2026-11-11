"""Check that publication dispatch uses a separate workflow token after validation."""

from unittest.mock import Mock, patch

import pytest

import dispatch_release


@pytest.mark.parametrize("tag", ["v2026.1.1", "v2026.2.0rc1"])
def test_dispatch_uses_workflow_token_and_verifies_with_repository_client(
    monkeypatch, tag
):
    monkeypatch.setenv("WORKFLOW_DISPATCH_TOKEN", "workflow-token")
    repository = Mock()
    repository.repos.get_release_by_tag.return_value = {
        "draft": True,
        "prerelease": "rc" in tag,
    }
    repository.repos.get_commit.return_value = {"sha": "verified-sha"}
    dispatcher = Mock()
    with patch.object(
        dispatch_release, "create_client", return_value=dispatcher
    ) as create:
        dispatch_release.dispatch_release(repository, tag)
    create.assert_called_once_with(token="workflow-token")
    repository.repos.get_release_by_tag.assert_called_once_with(tag=tag)
    repository.repos.get_commit.assert_called_once_with(ref=tag)
    repository.actions.create_workflow_dispatch.assert_not_called()
    dispatcher.actions.create_workflow_dispatch.assert_called_once_with(
        workflow_id="publish.yml", ref=tag, inputs={"tag": tag}
    )
    dispatcher.repos.get_release_by_tag.assert_not_called()


def test_invalid_release_never_dispatches(monkeypatch):
    monkeypatch.setenv("WORKFLOW_DISPATCH_TOKEN", "workflow-token")
    repository = Mock()
    repository.repos.get_release_by_tag.return_value = {
        "draft": True,
        "prerelease": False,
    }
    with (
        patch.object(dispatch_release, "create_client") as create,
        pytest.raises(ValueError, match="status"),
    ):
        dispatch_release.dispatch_release(repository, "v2026.2.0rc1")
    create.assert_not_called()
    repository.actions.create_workflow_dispatch.assert_not_called()


def test_missing_workflow_token_does_not_fall_back_to_repository_token(monkeypatch):
    monkeypatch.delenv("WORKFLOW_DISPATCH_TOKEN", raising=False)
    monkeypatch.setenv("GH_TOKEN", "repository-token")
    repository = Mock()
    repository.repos.get_release_by_tag.return_value = {
        "draft": True,
        "prerelease": False,
    }
    repository.repos.get_commit.return_value = {"sha": "verified-sha"}
    with (
        patch.object(dispatch_release, "create_client") as create,
        pytest.raises(KeyError, match="WORKFLOW_DISPATCH_TOKEN"),
    ):
        dispatch_release.dispatch_release(repository, "v2026.1.1")
    create.assert_not_called()
    repository.actions.create_workflow_dispatch.assert_not_called()
