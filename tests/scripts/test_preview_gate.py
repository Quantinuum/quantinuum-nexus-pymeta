"""Exercise preview release decisions against real Git history."""

import json
import subprocess
from unittest.mock import Mock

import pytest

import release_series as release


@pytest.fixture
def repository(tmp_path, monkeypatch):
    for variable in subprocess.check_output(
        ["git", "rev-parse", "--local-env-vars"], text=True
    ).splitlines():
        monkeypatch.delenv(variable, raising=False)
    root = tmp_path / "checkout"
    root.mkdir()
    monkeypatch.setattr(release, "ROOT", root)

    def git(*arguments):
        return release.command("git", *arguments)

    origin = tmp_path / "origin.git"
    git("init", "--bare", "-b", "next", str(origin))
    git("init", "-b", "next")
    for key, value in (
        ("user.name", "Test"),
        ("user.email", "test@example.invalid"),
        ("commit.gpgsign", "false"),
        ("core.autocrlf", "false"),
        ("core.hooksPath", str(tmp_path / "empty-hooks")),
    ):
        git("config", key, value)
    (root / ".github").mkdir()
    (root / ".github/preview.json").write_text(
        json.dumps({"target": "2026.2.0", "channel": "beta"})
    )
    (root / "pyproject.toml").write_text(
        '[project]\nname = "tools"\nversion = "2026.1.0"\n'
        'dependencies = ["component==1.0.0"]\n'
    )
    (root / "uv.lock").write_text(
        'version = 1\n[[package]]\nname = "tools"\nversion = "2026.1.0"\n'
    )
    git("add", ".")
    git("commit", "-m", "chore: initialize")
    git("remote", "add", "origin", str(origin))
    git("push", "origin", "HEAD:refs/heads/next")
    git("switch", "--detach")
    publish = Mock()
    monkeypatch.setattr(release, "publish_preview", publish)
    return root, git, publish


def create_preview(repository):
    _, git, publish = repository
    source = git("rev-parse", "HEAD")
    git("push", "origin", "HEAD:refs/heads/next")
    release.preview()
    git("switch", "--detach", source)
    publish.reset_mock()


@pytest.mark.parametrize(
    "message",
    [
        "chore(deps-dev): update pytest",
        "ci: update action",
        "docs: clarify usage",
        "chore: update tooling\n\nfix: this is body text, not a release commit",
    ],
)
def test_maintenance_only_push_does_not_create_another_preview(repository, message):
    _, git, publish = repository
    create_preview(repository)
    git("commit", "--allow-empty", "-m", message)
    git("push", "origin", "HEAD:refs/heads/next")
    release.preview()
    assert git("tag", "--list") == "v2026.2.0b1"
    publish.assert_not_called()


@pytest.mark.parametrize(
    "message",
    ["fix: repair package", "feat(deps): update SDK", "feat!: change API"],
)
def test_release_commit_followed_by_maintenance_still_creates_preview(
    repository, message
):
    _, git, publish = repository
    create_preview(repository)
    git("commit", "--allow-empty", "-m", message)
    git("commit", "--allow-empty", "-m", "chore(deps-dev): update pytest")
    source = git("rev-parse", "HEAD")
    git("push", "origin", "HEAD:refs/heads/next")
    release.preview()
    publish.assert_called_once_with("v2026.2.0b2", source)


@pytest.mark.parametrize(
    ("target", "channel", "tag"),
    [
        ("2026.2.0", "rc", "v2026.2.0rc1"),
        ("2026.3.0", "beta", "v2026.3.0b1"),
        ("2026.5.0", "beta", "v2026.5.0b1"),
        ("2026.12.0", "rc", "v2026.12.0rc1"),
        ("2027.1.0", "beta", "v2027.1.0b1"),
    ],
)
def test_target_or_channel_transition_creates_first_preview(
    repository, target, channel, tag
):
    root, git, publish = repository
    create_preview(repository)
    (root / ".github/preview.json").write_text(
        json.dumps({"target": target, "channel": channel})
    )
    git("add", ".github/preview.json")
    git("commit", "-m", "chore: configure previews")
    source = git("rev-parse", "HEAD")
    git("push", "origin", "HEAD:refs/heads/next")
    release.preview()
    publish.assert_called_once_with(tag, source)


def test_first_preview_does_not_need_a_release_commit(repository):
    _, git, publish = repository
    source = git("rev-parse", "HEAD")
    release.preview()
    publish.assert_called_once_with("v2026.2.0b1", source)


def test_manual_request_releases_maintenance_changes(repository):
    _, git, publish = repository
    create_preview(repository)
    git("commit", "--allow-empty", "-m", "chore: update tools")
    source = git("rev-parse", "HEAD")
    git("push", "origin", "HEAD:refs/heads/next")
    release.preview(force=True)
    publish.assert_called_once_with("v2026.2.0b2", source)


def test_manual_retry_reuses_existing_tag(repository):
    _, git, publish = repository
    source = git("rev-parse", "HEAD")
    release.preview(force=True)
    publish.reset_mock()
    git("switch", "--detach", source)
    release.preview(force=True)
    assert git("tag", "--list") == "v2026.2.0b1"
    publish.assert_called_once_with("v2026.2.0b1", source)


def test_preview_number_order_is_numeric(repository):
    _, git, publish = repository
    create_preview(repository)
    git("commit", "--allow-empty", "-m", "fix: update SDK")
    source = git("rev-parse", "HEAD")
    git(
        "commit",
        "--allow-empty",
        "-m",
        f"chore: preview\n\nPreview-Source: {source}",
    )
    git("tag", "v2026.2.0b10")
    git("switch", "--detach", source)
    git("commit", "--allow-empty", "-m", "chore: update tools")
    git("push", "origin", "HEAD:refs/heads/next")
    release.preview()
    publish.assert_not_called()


def test_rc_maintenance_changes_do_not_create_another_candidate(repository):
    root, git, publish = repository
    (root / ".github/preview.json").write_text(
        json.dumps({"target": "2026.2.0", "channel": "rc"})
    )
    git("add", ".github/preview.json")
    git("commit", "-m", "chore: freeze")
    create_preview(repository)
    git("commit", "--allow-empty", "-m", "ci: update action")
    git("push", "origin", "HEAD:refs/heads/next")
    release.preview()
    assert git("tag", "--list") == "v2026.2.0rc1"
    publish.assert_not_called()
