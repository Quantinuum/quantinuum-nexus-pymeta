"""Exercise promotion creation, recovery, and updates with Git and a GitHub stub."""

import copy
import json
import subprocess
import tomllib
from unittest.mock import Mock, patch

import pytest
from ghapi.core import APIError

import release_series as release


class TestPromotionUpdate:
    target = "2026.2.0"
    branch = "promote-2026.2.0"
    project = '[project]\nname = "tools"\nversion = "2026.1.0"\ndependencies = ["component==1.0.0"]\n'
    lock = 'version = 1\n[[package]]\nname = "tools"\nversion = "2026.1.0"\n[[package]]\nname = "component"\nversion = "1.0.0"\n'

    def git(self, root, *arguments):
        return subprocess.check_output(
            ["git", *arguments], cwd=root, text=True, stderr=subprocess.PIPE
        ).strip()

    def configure_git(self, root):
        for key, value in [
            ("user.name", "Test"),
            ("user.email", "test@example.invalid"),
            ("commit.gpgsign", "false"),
            ("core.autocrlf", "false"),
            ("core.hooksPath", str(self.scratch / "empty-hooks")),
        ]:
            self.git(root, "config", key, value)

    def body(self, tag):
        return f"Promote the exact dependency pins and lockfile from {tag}.\n\nThis release may contain breaking changes.\n\nRelease-As: {self.target}"

    @pytest.fixture(autouse=True)
    def setup_repository(self, tmp_path, monkeypatch, request):
        self.target = getattr(request, "param", self.target)
        self.branch = f"promote-{self.target}"
        # Hook-exported repository variables must not redirect these temporary Git operations.
        local_variables = subprocess.check_output(
            ["git", "rev-parse", "--local-env-vars"], text=True
        ).splitlines()
        for variable in local_variables:
            monkeypatch.delenv(variable, raising=False)
        self.scratch = tmp_path
        self.origin = self.scratch / "origin.git"
        seed = self.scratch / "seed"
        seed.mkdir()
        self.git(self.scratch, "init", "--bare", "-b", "main", str(self.origin))
        self.git(seed, "init", "-b", "main")
        self.configure_git(seed)
        (seed / ".github").mkdir()
        (seed / ".github/preview.json").write_text("{}\n")
        (seed / "pyproject.toml").write_text(self.project)
        (seed / "uv.lock").write_text(self.lock)
        self.git(seed, "add", ".")
        self.git(seed, "commit", "-m", "initial")
        self.git(seed, "remote", "add", "origin", str(self.origin))
        self.git(seed, "push", "origin", "main")
        self.candidates = {}
        self.metadata = {}
        with patch.object(release, "ROOT", seed):
            for counter in (1, 2):
                tag = f"v{self.target}rc{counter}"
                self.git(seed, "switch", "--detach", "main")
                project, lock = release.stamp(
                    self.project.replace("1.0.0", f"{counter + 1}.0.0"),
                    self.lock.replace('"1.0.0"', f'"{counter + 1}.0.0"'),
                    tag[1:],
                )
                (seed / "pyproject.toml").write_text(project)
                (seed / "uv.lock").write_text(lock)
                self.git(seed, "add", ".")
                self.git(seed, "commit", "-m", tag)
                self.git(seed, "tag", tag)
                self.candidates[tag] = self.git(seed, "rev-parse", "HEAD")
                self.metadata[tag] = (project, lock)
            self.git(seed, "push", "origin", "--tags")
            self.git(seed, "switch", "-c", self.branch, "main")
            tag = f"v{self.target}rc1"
            release.write_promotion(
                self.target, tag, self.candidates[tag], *self.metadata[tag]
            )
            release.commit(f"feat: promote RC1\n\n{self.body(tag)}")
            self.git(seed, "push", "origin", self.branch)
        self.original_head = self.remote_head()
        self.pr = {
            "number": 7,
            "html_url": "https://example.invalid/pull/7",
            "node_id": "PR_7",
            "head": {"repo": {"full_name": "owner/repo"}},
            "base": {"repo": {"full_name": "owner/repo"}},
            "body": self.body(tag),
            "draft": False,
        }
        self.reviews = [{"id": 1, "state": "APPROVED", "commit_id": self.original_head}]
        self.events = []
        self.attempts = 0
        self.dismiss_failure = False
        self.add_current_approval = False
        self.existing_pr = True
        self.create_failure = False
        self.create_attempts = 0

    def remote_head(self):
        return self.git(
            self.scratch,
            "--git-dir",
            str(self.origin),
            "rev-parse",
            f"refs/heads/{self.branch}",
        )

    def read_remote(self, path):
        return self.git(
            self.scratch, "--git-dir", str(self.origin), "show", f"{self.branch}:{path}"
        )

    def promote(self, counter, before_push=None):
        self.attempts += 1
        clone = self.scratch / f"attempt-{self.attempts}"
        self.git(
            self.scratch, "clone", "--branch", "main", str(self.origin), str(clone)
        )
        self.configure_git(clone)
        api = Mock()
        self.api = api
        api.repos.get_release_by_tag.return_value = {"draft": False, "prerelease": True}
        tag = f"v{self.target}rc{counter}"
        api.actions.list_workflow_runs.return_value = {
            "workflow_runs": [
                {"head_sha": self.candidates[tag], "conclusion": "success"}
            ]
        }

        def create(**parameters):
            self.create_attempts += 1
            if self.create_failure:
                raise APIError("Temporary outage", status_code=503)
            self.existing_pr = True
            self.pr["body"] = parameters["body"]
            return {"html_url": self.pr["html_url"]}

        original_command = release.command

        def command(*arguments):
            if arguments[:3] == ("git", "push", "origin") and before_push:
                before_push()
            return original_command(*arguments)

        def list_pulls(**parameters):
            if parameters["page"] != 1 or not self.existing_pr:
                return []
            pr = copy.deepcopy(self.pr)
            pr["head"]["sha"] = self.remote_head()
            return [pr]

        def set_draft(client, node_id, draft):
            assert client is api and node_id == "PR_7"
            self.pr["draft"] = draft
            self.events.append("draft" if draft else "ready")

        def edit(**parameters):
            self.pr["body"] = parameters["body"]
            self.events.append("edit")

        def reviews(**parameters):
            if parameters["page"] != 1:
                return []
            if self.add_current_approval:
                self.reviews.append(
                    {"id": 2, "state": "APPROVED", "commit_id": self.remote_head()}
                )
            return self.reviews

        def dismiss(**parameters):
            self.events.append("dismiss")
            if self.dismiss_failure:
                raise APIError("Forbidden", status_code=403)
            next(
                review
                for review in self.reviews
                if review["id"] == parameters["review_id"]
            )["state"] = "DISMISSED"

        api.pulls.list.side_effect = list_pulls
        api.pulls.create.side_effect = create
        api.pulls.update.side_effect = edit
        api.pulls.list_reviews.side_effect = reviews
        api.pulls.dismiss_review.side_effect = dismiss
        api.pulls.get.side_effect = lambda **parameters: {
            "head": {"sha": self.remote_head()},
            "state": "open",
            "draft": self.pr["draft"],
        }
        with (
            patch.object(release, "ROOT", clone),
            patch.object(release, "create_client", return_value=api),
            patch.object(release, "command", command),
            patch.object(release, "set_draft", set_draft),
            patch.dict("os.environ", {"GITHUB_REPOSITORY": "owner/repo"}),
        ):
            release.promote(tag)

    def test_first_promotion_opens_a_pr_with_the_selected_candidate(self):
        self.existing_pr = False
        self.git(
            self.scratch,
            "--git-dir",
            str(self.origin),
            "update-ref",
            "-d",
            f"refs/heads/{self.branch}",
        )
        self.promote(2)
        arguments = self.api.pulls.create.call_args.kwargs
        assert arguments["head"] == self.branch
        assert arguments["base"] == "main"
        assert arguments["body"] == self.body(f"v{self.target}rc2")
        assert (
            json.loads(self.read_remote(".github/stable-candidate.json"))["sha"]
            == self.candidates[f"v{self.target}rc2"]
        )
        self.api.pulls.update.assert_not_called()

    @pytest.mark.parametrize(
        "setup_repository", ["2026.5.0", "2026.12.0", "2027.1.0"], indirect=True
    )
    def test_promotes_higher_series_and_new_year_with_exact_candidate(self):
        self.promote(2)
        candidate = f"v{self.target}rc2"
        assert json.loads(self.read_remote(".github/stable-candidate.json")) == {
            "version": self.target,
            "tag": candidate,
            "sha": self.candidates[candidate],
        }
        release.verify_candidate_files(
            self.read_remote("pyproject.toml"),
            self.read_remote("uv.lock"),
            *self.metadata[candidate],
        )

    @pytest.mark.parametrize("retry_counter", [1, 2])
    def test_retry_after_pr_creation_failure_recovers_the_pushed_branch(
        self, retry_counter, monkeypatch
    ):
        self.existing_pr = False
        self.git(
            self.scratch,
            "--git-dir",
            str(self.origin),
            "update-ref",
            "-d",
            f"refs/heads/{self.branch}",
        )
        self.create_failure = True
        monkeypatch.setenv("GIT_AUTHOR_DATE", "2026-11-10T10:00:00+0000")
        monkeypatch.setenv("GIT_COMMITTER_DATE", "2026-11-10T10:00:00+0000")
        with pytest.raises(APIError, match="Temporary outage"):
            self.promote(1)
        pushed = self.remote_head()
        self.create_failure = False
        monkeypatch.setenv("GIT_AUTHOR_DATE", "2026-11-10T10:01:00+0000")
        monkeypatch.setenv("GIT_COMMITTER_DATE", "2026-11-10T10:01:00+0000")
        self.promote(retry_counter)
        head = self.remote_head()
        if retry_counter == 1:
            assert head == pushed
        else:
            assert head != pushed
            assert (
                self.git(
                    self.scratch, "--git-dir", str(self.origin), "rev-parse", f"{head}^"
                )
                == pushed
            )
        candidate = f"v{self.target}rc{retry_counter}"
        assert json.loads(self.read_remote(".github/stable-candidate.json")) == {
            "version": self.target,
            "tag": candidate,
            "sha": self.candidates[candidate],
        }
        release.verify_candidate_files(
            self.read_remote("pyproject.toml"),
            self.read_remote("uv.lock"),
            *self.metadata[candidate],
        )
        assert self.create_attempts == 2
        assert self.api.pulls.create.call_args.kwargs["body"] == self.body(candidate)
        self.api.pulls.update.assert_not_called()

    def test_recovery_cannot_replace_a_newer_candidate_with_an_older_rc(self):
        self.existing_pr = False
        self.promote(2)
        selected = self.remote_head()
        self.existing_pr = False
        with pytest.raises(ValueError, match="older RC"):
            self.promote(1)
        assert self.remote_head() == selected
        self.api.pulls.create.assert_not_called()

    def test_recovery_rejects_a_branch_with_an_invalid_candidate(self):
        self.existing_pr = False
        seed = self.scratch / "seed"
        record = seed / ".github/stable-candidate.json"
        candidate = json.loads(record.read_text())
        candidate["version"] = "2025.4.0"
        record.write_text(json.dumps(candidate))
        self.git(seed, "add", ".github/stable-candidate.json")
        self.git(seed, "commit", "-m", "Invalid candidate")
        self.git(seed, "push", "origin", self.branch)
        head = self.remote_head()
        with pytest.raises(ValueError, match="valid candidate for this series"):
            self.promote(1)
        assert self.remote_head() == head
        self.api.pulls.create.assert_not_called()

    def test_concurrent_push_during_recovery_is_rejected(self):
        self.existing_pr = False
        parent = self.remote_head()
        concurrent = self.git(
            self.scratch,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "--git-dir",
            str(self.origin),
            "commit-tree",
            f"{parent}^{{tree}}",
            "-p",
            parent,
            "-m",
            "Concurrent change",
        )

        def push_concurrent_change():
            self.git(
                self.scratch,
                "--git-dir",
                str(self.origin),
                "update-ref",
                f"refs/heads/{self.branch}",
                concurrent,
            )

        with pytest.raises(subprocess.CalledProcessError):
            self.promote(2, before_push=push_concurrent_change)
        assert self.remote_head() == concurrent
        self.api.pulls.create.assert_not_called()

    def test_new_rc_updates_the_existing_pr_and_requires_a_new_approval(self):
        self.promote(2)
        head = self.remote_head()
        assert head != self.original_head
        assert (
            self.git(
                self.scratch, "--git-dir", str(self.origin), "rev-parse", f"{head}^"
            )
            == self.original_head
        )
        assert json.loads(self.read_remote(".github/stable-candidate.json")) == {
            "version": self.target,
            "tag": f"v{self.target}rc2",
            "sha": self.candidates[f"v{self.target}rc2"],
        }
        project = self.read_remote("pyproject.toml")
        lock = self.read_remote("uv.lock")
        release.verify_candidate_files(
            project, lock, *self.metadata[f"v{self.target}rc2"]
        )
        assert tomllib.loads(project)["project"]["dependencies"] == ["component==3.0.0"]
        assert self.pr["body"] == self.body(f"v{self.target}rc2")
        assert self.events == ["draft", "edit", "dismiss", "ready"]
        assert self.reviews[0]["state"] == "DISMISSED"
        assert not self.pr["draft"]

    def test_repeating_the_same_candidate_preserves_commits_and_approval(self):
        self.promote(1)
        assert self.remote_head() == self.original_head
        assert self.events == []
        assert self.reviews[0]["state"] == "APPROVED"

    def test_an_older_candidate_cannot_replace_a_newer_selection(self):
        self.promote(2)
        selected = self.remote_head()
        with pytest.raises(ValueError, match="older RC"):
            self.promote(1)
        assert self.remote_head() == selected

    def test_failed_approval_dismissal_keeps_the_updated_pr_draft(self):
        self.dismiss_failure = True
        with pytest.raises(APIError):
            self.promote(2)
        assert self.pr["draft"]
        assert "ready" not in self.events
        assert (
            json.loads(self.read_remote(".github/stable-candidate.json"))["tag"]
            == f"v{self.target}rc2"
        )

    def test_retry_after_dismissal_failure_reuses_the_updated_commit(self):
        self.dismiss_failure = True
        with pytest.raises(APIError):
            self.promote(2)
        updated = self.remote_head()
        self.dismiss_failure = False
        self.promote(2)
        assert self.remote_head() == updated
        assert self.reviews[0]["state"] == "DISMISSED"
        assert self.pr["draft"]

    def test_an_intentionally_draft_pr_stays_draft(self):
        self.pr["draft"] = True
        self.promote(2)
        assert self.pr["draft"]
        assert self.events == ["edit", "dismiss"]

    def test_approval_of_the_new_commit_is_preserved(self):
        self.add_current_approval = True
        self.promote(2)
        assert [review["state"] for review in self.reviews] == ["DISMISSED", "APPROVED"]
