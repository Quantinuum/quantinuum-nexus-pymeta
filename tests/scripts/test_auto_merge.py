"""Exercise automatic approval and merging without making GitHub requests."""

import base64
import json
from pathlib import Path
import runpy
from types import SimpleNamespace

from ghapi.core import APIError

import pytest

import auto_merge

BASE = """[project]
name = "quantinuum-nexus-sdk"
version = "2026.1.0"
dependencies = [
  "guppylang==1.1.3",
  "guppyft==0.4.0",
  "guppyalgos==0.2.0",
  "selene-sim==0.3.2",
  "pytket==2.18.4",
  "qnexus==0.51.0",
]
"""
BOT = "release-bot[bot]"


def http_error(status):
    return APIError("Failed", status_code=status)


class FakeGitHub:
    repository = "owner/repo"

    def __init__(self, branch="main", **options):
        self.options = options
        self.pr = {
            "number": 1,
            "state": "open",
            "draft": False,
            "title": "fix(deps): update tools",
            "user": {"login": "dependabot[bot]"},
            "base": {"ref": branch, "sha": "base"},
            "head": {
                "sha": "tested",
                "ref": "dependabot/uv/tools",
                "repo": {"full_name": self.repository},
            },
            **options.get("pr", {}),
        }
        self.base_reads = self.config_reads = 0
        self.approvals, self.merges, self.requests = [], [], []
        prefix = f"repos/{self.repository}"
        self.pulls = SimpleNamespace(
            get=lambda pull_number: self.get(f"{prefix}/pulls/{pull_number}"),
            list_files=lambda pull_number, page, per_page: (
                self.list(f"{prefix}/pulls/{pull_number}/files") if page == 1 else []
            ),
            list_reviews=lambda pull_number, page, per_page: (
                self.list(f"{prefix}/pulls/{pull_number}/reviews") if page == 1 else []
            ),
            create_review=lambda pull_number, **payload: self.write(
                "POST", f"{prefix}/pulls/{pull_number}/reviews", payload
            ),
            merge=lambda pull_number, **payload: self.write(
                "PUT", f"{prefix}/pulls/{pull_number}/merge", payload
            ),
        )
        self.git = SimpleNamespace(
            get_ref=lambda ref: self.get(f"{prefix}/git/ref/{ref}"),
            list_matching_refs=lambda ref: self.list(
                f"{prefix}/git/matching-refs/{ref}"
            ),
        )
        self.repos = SimpleNamespace(
            get_content=lambda path, ref: {
                "encoding": "base64",
                "content": base64.b64encode(self.file(path, ref).encode()).decode(),
            }
        )

    def get(self, endpoint):
        self.requests.append(endpoint)
        if endpoint.endswith("/pulls/1"):
            return self.pr
        if endpoint.endswith("/git/ref/heads/next"):
            sequence = self.options.get("base_sequence", ["base"])
            sha = sequence[min(self.base_reads, len(sequence) - 1)]
            self.base_reads += 1
            return {"object": {"sha": sha}}
        if "/git/ref/tags/" in endpoint:
            if self.options.get("stable_tag"):
                return {}
            raise http_error(404)
        raise AssertionError(endpoint)

    def file(self, path, ref):
        self.requests.append((path, ref))
        if path == ".github/stable-candidate.json":
            if "candidate" not in self.options:
                raise http_error(self.options.get("candidate_error", 404))
            return json.dumps(self.options["candidate"])
        if path == ".github/preview.json":
            sequence = self.options.get(
                "config_sequence", [{"target": "2026.2.0", "channel": "beta"}]
            )
            config = sequence[min(self.config_reads, len(sequence) - 1)]
            self.config_reads += 1
            return json.dumps(config)
        if path == ".release-please-manifest.json":
            return json.dumps(self.options.get("manifest", {}))
        assert path == "pyproject.toml"
        return (
            BASE
            if ref == "base"
            else self.options.get(
                "head", BASE.replace("pytket==2.18.4", "pytket==2.18.5")
            )
        )

    def list(self, endpoint):
        self.requests.append(endpoint)
        if endpoint.endswith("/files"):
            return [
                {"filename": name}
                for name in self.options.get("files", ["pyproject.toml", "uv.lock"])
            ]
        if endpoint.endswith("/reviews"):
            return self.options.get("reviews", [])
        if "/git/matching-refs/" in endpoint:
            return [{"ref": ref} for ref in self.options.get("tags", [])]
        raise AssertionError(endpoint)

    def write(self, method, endpoint, payload):
        self.requests.append((method, endpoint, payload))
        if endpoint.endswith("/reviews"):
            assert method == "POST"
            self.approvals.append(payload)
            return {}
        assert method == "PUT" and endpoint.endswith("/merge")
        self.merges.append(payload)
        return {
            "merged": self.options.get("merge_success", True),
            "message": "Merge was rejected",
        }


def simulate(
    branch="main",
    event="pull_request",
    conclusion="success",
    tested_base="base",
    **options,
):
    api = FakeGitHub(branch, **options)
    run = {
        "event": event,
        "conclusion": conclusion,
        "head_sha": "tested",
        "pull_requests": [{"number": 1, "base": {"sha": tested_base}}],
    }
    auto_merge.merge_updates(run, api, BOT, api.repository)
    return api


def test_merges_a_tested_patch_with_a_sha_guard_and_conventional_title():
    api = simulate()
    assert api.merges == [
        {
            "sha": "tested",
            "merge_method": "squash",
            "commit_title": "fix(deps): update tools (#1)",
        }
    ]
    assert api.approvals == []


def test_accepts_stable_minor_and_coordinated_updates():
    assert (
        len(
            simulate(
                head=BASE.replace("pytket==2.18.4", "pytket==2.19.0").replace(
                    "qnexus==0.51.0", "qnexus==0.51.1"
                )
            ).merges
        )
        == 1
    )


def test_freezes_dependency_updates_during_quarterly_promotion():
    assert not simulate(candidate={"version": "2026.1.0"}).merges
    assert simulate(candidate={"version": "2026.1.0"}, stable_tag=True).merges
    assert simulate(candidate={"version": "2025.4.0"}).merges


def test_approves_and_merges_breaking_updates_into_next():
    api = simulate(
        "next",
        head=BASE.replace("pytket==2.18.4", "pytket==3.0.0").replace(
            "qnexus==0.51.0", "qnexus==0.52.0"
        ),
    )
    assert len(api.merges) == len(api.approvals) == 1
    assert api.approvals[0]["event"] == "APPROVE"
    assert api.approvals[0]["commit_id"] == "tested"


@pytest.mark.parametrize("review_sha,new_approvals", [("tested", 0), ("older", 1)])
def test_reuses_only_an_approval_for_the_current_commit(review_sha, new_approvals):
    api = simulate(
        "next",
        reviews=[
            {"user": {"login": BOT}, "commit_id": review_sha, "state": "APPROVED"}
        ],
    )
    assert len(api.merges) == 1
    assert len(api.approvals) == new_approvals


@pytest.mark.parametrize(
    "options",
    [
        {"config_sequence": [{"target": "2026.2.0", "channel": "rc"}]},
        {"tags": ["refs/tags/v2026.2.0rc1"]},
        {"tags": ["refs/tags/v2026.2.0"]},
        {"config_sequence": [{"target": "2026.5.0", "channel": "beta"}]},
        {"tested_base": "older-base"},
        {"conclusion": "failure"},
        {"event": "push"},
        {"head": BASE.replace("pytket==2.18.4", "pytket==2.18.3")},
        {"head": BASE.replace("pytket==2.18.4", "pytket==3.0.0rc1")},
        {"head": BASE.replace("pytket==2.18.4", "pytket>=3.0.0")},
        {"files": ["pyproject.toml", ".github/preview.json"]},
        {"pr": {"user": {"login": "someone"}}},
    ],
)
def test_next_rejects_ineligible_updates_without_approval(options):
    api = simulate("next", **options)
    assert not api.merges and not api.approvals


@pytest.mark.parametrize(
    "options",
    [
        {"base_sequence": ["base", "new-base"]},
        {
            "config_sequence": [
                {"target": "2026.2.0", "channel": "beta"},
                {"target": "2026.2.0", "channel": "rc"},
            ]
        },
    ],
)
def test_branch_or_rc_phase_changes_before_approval_require_fresh_ci(options):
    api = simulate("next", **options)
    assert not api.merges and not api.approvals


def test_branch_changes_during_approval_prevent_merging():
    api = simulate("next", base_sequence=["base", "base", "new-base"])
    assert not api.merges and len(api.approvals) == 1


def test_missing_ci_base_snapshot_never_approves_next():
    api = FakeGitHub("next")
    auto_merge.merge_updates(
        {
            "event": "pull_request",
            "conclusion": "success",
            "head_sha": "tested",
            "pull_requests": [{"number": 1, "base": None}],
        },
        api,
        BOT,
        api.repository,
    )
    assert not api.merges and not api.approvals


@pytest.mark.parametrize(
    "head",
    [
        BASE.replace("pytket==2.18.4", "pytket==3.0.0"),
        BASE.replace("qnexus==0.51.0", "qnexus==0.52.0"),
        BASE.replace("pytket==2.18.4", "pytket==2.18.3"),
        BASE.replace("pytket==2.18.4", "pytket==2.18.5rc1"),
        BASE.replace("pytket==2.18.4", "pytket==2.18.5") + "\n# changed\n",
        BASE.replace("pytket==2.18.4", "pytket>=2.18.5"),
    ],
)
def test_main_leaves_incompatible_or_unrelated_changes_for_review(head):
    assert not simulate(head=head).merges


@pytest.mark.parametrize(
    "options",
    [
        {"pr": {"head": {"sha": "untested", "repo": {"full_name": "owner/repo"}}}},
        {"pr": {"user": {"login": "someone"}}},
        {"files": ["pyproject.toml", ".github/workflows/ci.yml"]},
        {"pr": {"head": {"sha": "tested", "repo": {"full_name": "fork/repo"}}}},
        {"pr": {"draft": True}},
        {"pr": {"state": "closed"}},
    ],
)
def test_rejects_untested_or_unauthorized_prs(options):
    assert not simulate(**options).merges


@pytest.mark.parametrize(
    "version,manifest,allowed",
    [
        ("2026.1.0", {}, True),
        ("2026.1.1", {".": "2026.1.0"}, True),
        ("2026.2.0", {".": "2026.1.0"}, False),
    ],
)
def test_release_bot_can_merge_only_the_initial_or_patch_release(
    version, manifest, allowed
):
    api = simulate(
        pr={
            "user": {"login": BOT},
            "head": {
                "sha": "tested",
                "ref": "release-please--branches--main",
                "repo": {"full_name": "owner/repo"},
            },
        },
        files=[
            "pyproject.toml",
            "uv.lock",
            "CHANGELOG.md",
            ".release-please-manifest.json",
        ],
        head=BASE.replace('version = "2026.1.0"', f'version = "{version}"'),
        manifest=manifest,
    )
    assert bool(api.merges) == allowed


def test_non_404_api_failures_are_not_treated_as_missing_candidate_files():
    with pytest.raises(APIError) as error:
        simulate(candidate_error=403)
    assert error.value.status_code == 403


def test_rejected_merges_fail_the_workflow():
    with pytest.raises(RuntimeError, match="Merge was rejected"):
        simulate(merge_success=False)


def test_cli_reads_the_workflow_event_and_uses_the_app_identity(tmp_path, monkeypatch):
    api = FakeGitHub()
    path = tmp_path / "event.json"
    path.write_text(
        json.dumps(
            {
                "workflow_run": {
                    "event": "pull_request",
                    "conclusion": "success",
                    "head_sha": "tested",
                    "pull_requests": [{"number": 1}],
                }
            }
        )
    )
    for name, value in {
        "GITHUB_EVENT_PATH": str(path),
        "GITHUB_REPOSITORY": "owner/repo",
        "GH_TOKEN": "test-token",
        "RELEASE_BOT": BOT,
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr("github_api.create_client", lambda: api)
    runpy.run_path(str(Path(auto_merge.__file__)), run_name="__main__")
    assert len(api.merges) == 1
