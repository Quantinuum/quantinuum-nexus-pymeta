"""Check dependency target rotation and retry-safe maintenance PRs."""

from unittest.mock import Mock, patch

import pytest
from ghapi.core import APIError

import maintain_releases as maintenance


def test_dependency_targets_include_main_and_only_the_two_supported_series():
    stable = (maintenance.ROOT / ".github/templates/dependabot-stable.yml").read_text()
    development = (
        maintenance.ROOT / ".github/templates/dependabot-main.yml"
    ).read_text()
    config = maintenance.dependabot_config(
        ["release/2027.1", "release/2026.12"], stable, development
    )
    assert "target-branch: main" in config
    assert "target-branch: release/2027.1" in config
    assert "target-branch: release/2026.12" in config
    assert "target-branch: next" not in config
    assert config.count("package-ecosystem: uv") == 3
    assert "prefix: feat" in development and "prefix: fix" in stable
    assert "version-update:semver-major" in stable


@pytest.mark.parametrize(
    "merge_base,refresh", [("base", False), ("previous-base", True)]
)
def test_maintenance_pr_with_unchanged_contents_refreshes_only_outdated_base(
    monkeypatch, merge_base, refresh
):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    api = Mock(owner="owner")
    api.git.get_ref.side_effect = lambda ref: {
        "object": {"sha": "base" if ref == "heads/main" else "head"}
    }
    api.repos.compare_commits.return_value = {"merge_base_commit": {"sha": merge_base}}
    api.git.get_commit.return_value = {"tree": {"sha": "base-tree"}}
    api.git.create_tree.return_value = {"sha": "new-tree"}
    api.git.create_commit.return_value = {"sha": "refreshed-head"}
    api.pulls.list.side_effect = lambda page, per_page, **kwargs: (
        [{"html_url": "existing"}] if page == 1 else []
    )
    with patch.object(
        maintenance,
        "read_file",
        side_effect=lambda api, path, ref: "old" if ref == "base" else "desired",
    ):
        maintenance.open_files_pr(
            api,
            "main",
            "automation/supported-series",
            {".github/dependabot.yml": "desired"},
            "title",
            "body",
        )
    api.repos.compare_commits.assert_called_once_with(basehead="base...head")
    if refresh:
        api.git.create_commit.assert_called_once_with(
            message="title", tree="new-tree", parents=["head", "base"]
        )
        api.git.update_ref.assert_called_once_with(
            ref="heads/automation/supported-series", sha="refreshed-head", force=False
        )
    else:
        api.git.create_commit.assert_not_called()
        api.git.update_ref.assert_not_called()
    api.pulls.create.assert_not_called()


def test_bootstrap_retries_after_branch_creation_preserve_package_metadata():
    api = Mock()
    files = {"release-please-config.json": '{"packages": {".": {}}}'}
    with (
        patch.object(
            maintenance, "read_file", side_effect=APIError("Missing", status_code=404)
        ),
        patch.object(
            maintenance.subprocess,
            "check_output",
            return_value="release-please-config.json\npyproject.toml\nuv.lock\n.release-please-manifest.json\n",
        ),
        patch.object(maintenance, "ROOT") as root,
        patch.object(maintenance, "open_files_pr") as open_pr,
    ):
        (root / "release-please-config.json").read_text.return_value = files[
            "release-please-config.json"
        ]
        maintenance.bootstrap(api, "release/2026.1", "v2026.1.3")
    contents = open_pr.call_args.args[3]
    assert set(contents) == {"release-please-config.json"}
    assert '"initial-version": "2026.1.0"' in contents["release-please-config.json"]
    api.git.create_ref.assert_not_called()


def test_refresh_commit_includes_current_base_in_ancestry(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    api = Mock()
    api.git.get_ref.side_effect = lambda ref: {
        "object": {"sha": "current-main" if ref == "heads/main" else "old-pr-head"}
    }
    api.git.get_commit.return_value = {"tree": {"sha": "base-tree"}}
    api.git.create_tree.return_value = {"sha": "new-tree"}
    api.git.create_commit.return_value = {"sha": "new-commit"}
    api.pulls.list.side_effect = lambda page, per_page, **kwargs: []
    api.pulls.create.return_value = {"html_url": "new-pr"}
    with patch.object(maintenance, "read_file", return_value="old"):
        maintenance.open_files_pr(
            api,
            "main",
            "automation/supported-series",
            {".github/dependabot.yml": "new"},
            "title",
            "body",
        )
    assert api.git.create_commit.call_args.kwargs["parents"] == [
        "old-pr-head",
        "current-main",
    ]
    api.git.update_ref.assert_called_once_with(
        ref="heads/automation/supported-series", sha="new-commit", force=False
    )
    assert api.git.create_tree.call_args.kwargs["base_tree"] == "base-tree"


def test_minor_update_restrictions_follow_each_series_component_major_versions():
    api = Mock()
    api.repos.list_releases.side_effect = lambda page, per_page: (
        [
            {"tag_name": tag, "draft": False, "prerelease": False}
            for tag in ("v2026.1.0", "v2026.2.0")
        ]
        if page == 1
        else []
    )

    def read(api, path, ref):
        if path == "pyproject.toml":
            version = "1.0.0" if ref == "release/2026.2" else "0.9.0"
            return f'[project]\ndependencies = ["qnexus=={version}"]\n'
        return (maintenance.ROOT / path).read_text()

    with patch.object(maintenance, "read_file", side_effect=read):
        config = maintenance.expected_dependabot(api)
    current, previous = config.split("target-branch: release/2026.1")
    assert "dependency-name: qnexus" not in current
    assert "dependency-name: qnexus" in previous
