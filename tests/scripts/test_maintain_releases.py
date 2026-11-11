"""Check dependency target rotation and retry-safe maintenance PRs."""

import json
import tomllib
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


def test_bootstrap_retries_after_branch_creation_preserve_package_metadata(tmp_path):
    api = Mock()
    api.git.get_ref.return_value = {"object": {"sha": "baseline"}}
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "quantinuum-nexus"\n')
    (tmp_path / "release-please-config.json").write_text('{"packages": {".": {}}}')

    def read(api, path, ref):
        if path == "scripts/release_policy.py":
            raise APIError("Missing", status_code=404)
        assert path == "pyproject.toml"
        return '[project]\nname = "quantinuum-nexus"\n'

    with (
        patch.object(maintenance, "read_file", side_effect=read),
        patch.object(
            maintenance.subprocess,
            "check_output",
            return_value="release-please-config.json\npyproject.toml\nuv.lock\n.release-please-manifest.json\n",
        ),
        patch.object(maintenance, "ROOT", tmp_path),
        patch.object(maintenance, "open_files_pr") as open_pr,
    ):
        maintenance.bootstrap(api, "release/2026.1", "v2026.1.3")
    contents = open_pr.call_args.args[3]
    assert set(contents) == {"release-please-config.json"}
    assert (
        json.loads(contents["release-please-config.json"])["packages"]["."][
            "initial-version"
        ]
        == "2026.1.0"
    )
    assert open_pr.call_args.kwargs["expected_base"] == "baseline"
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


@pytest.mark.parametrize("has_tooling", [False, True])
def test_branch_setup_renames_distribution_without_copying_development_pins(
    tmp_path, monkeypatch, has_tooling
):
    monkeypatch.setenv("GITHUB_REPOSITORY", "Quantinuum/quantinuum-nexus-pymeta")
    api = Mock()
    api.git.get_ref.return_value = {"object": {"sha": "baseline"}}
    project = '[project]\nname = "quantinuum-nexus-sdk"\nversion = "2026.1.3"\ndependencies = ["component==1.2.3"]\n'
    lock = 'version = 1\n[[package]]\nname = "component"\nversion = "1.2.3"\n[[package]]\nname = "quantinuum-nexus-sdk"\nversion = "2026.1.3"\ndependencies = [{name = "component"}]\n'
    config = {
        "packages": {
            ".": {
                "initial-version": "2026.1.0",
                "extra-files": [
                    {
                        "type": "toml",
                        "path": "uv.lock",
                        "jsonpath": "$.package[?(@.name.value=='quantinuum-nexus-sdk')].version",
                    }
                ],
            }
        }
    }
    files = {
        "pyproject.toml": project,
        "uv.lock": lock,
        "README.md": "[GitHub Releases](https://github.com/Quantinuum/quantinuum-nexus-sdk/releases)\nuv add ./quantinuum_nexus_sdk-*.whl\npip install quantinuum-nexus-sdk\n",
        "release-please-config.json": json.dumps(config),
        "scripts/release_policy.py": "tooling",
    }
    for path, text in files.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "quantinuum-nexus"\nversion = "2026.2.0"\ndependencies = ["component==9.0.0"]\n'
    )
    (tmp_path / "README.md").write_text(
        "[GitHub Releases](https://github.com/Quantinuum/quantinuum-nexus-pymeta/releases)\n"
    )

    def read(api, path, ref):
        if path == "scripts/release_policy.py" and not has_tooling:
            raise APIError("Missing", status_code=404)
        return files[path]

    with (
        patch.object(maintenance, "ROOT", tmp_path),
        patch.object(maintenance, "read_file", side_effect=read),
        patch.object(
            maintenance.subprocess, "check_output", return_value="\n".join(files)
        ),
        patch.object(maintenance, "open_files_pr") as open_pr,
    ):
        maintenance.bootstrap(api, "release/2026.1", "v2026.1.3")
    result = open_pr.call_args.args[3]
    assert open_pr.call_args.args[4] == "fix: rename metapackage to quantinuum-nexus"
    expected_project = tomllib.loads(project)
    expected_project["project"]["name"] = "quantinuum-nexus"
    assert tomllib.loads(result["pyproject.toml"]) == expected_project
    expected_lock = tomllib.loads(lock)
    expected_lock["package"][1]["name"] = "quantinuum-nexus"
    assert tomllib.loads(result["uv.lock"]) == expected_lock
    assert ".release-please-manifest.json" not in result
    assert ("scripts/release_policy.py" in result) is not has_tooling
    assert (
        "https://github.com/Quantinuum/quantinuum-nexus-pymeta/releases"
        in result["README.md"]
    )
    assert "quantinuum_nexus-*.whl" in result["README.md"]
    target = json.loads(result["release-please-config.json"])["packages"]["."]
    assert (
        target["extra-files"][0]["jsonpath"]
        == "$.package[?(@.name.value=='quantinuum-nexus')].version"
    )
    assert target["initial-version"] == "2026.1.0"


def test_setup_rejects_a_concurrent_release_branch_update():
    api = Mock()
    api.git.get_ref.return_value = {"object": {"sha": "new-head"}}
    with pytest.raises(ValueError, match="changed"):
        maintenance.open_files_pr(
            api,
            "release/2026.1",
            "automation/bootstrap-2026.1",
            {},
            "title",
            "body",
            expected_base="old-head",
        )
    api.git.create_commit.assert_not_called()
    api.git.update_ref.assert_not_called()


def test_aligned_release_branch_does_not_get_another_setup_pr(tmp_path):
    api = Mock()
    api.git.get_ref.return_value = {"object": {"sha": "baseline"}}
    project = '[project]\nname = "quantinuum-nexus"\n'
    (tmp_path / "pyproject.toml").write_text(project)
    with (
        patch.object(maintenance, "ROOT", tmp_path),
        patch.object(maintenance, "read_file", return_value=project),
        patch.object(maintenance, "open_files_pr") as open_pr,
    ):
        maintenance.bootstrap(api, "release/2026.1", "v2026.1.3")
    open_pr.assert_not_called()
