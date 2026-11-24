"""Validate release series version sequencing, RC promotion, and dependency preservation."""

import subprocess
import tomllib
from unittest.mock import patch

import pytest

import release_series as release


class TestPreview:
    def test_beta_and_rc_have_independent_monotonic_numbers(self):
        tags = ["v26.1.0", "v26.2.0b1", "v26.2.0b3", "v27.1.0b9"]
        assert release.next_preview("26.2.0", "beta", tags) == "26.2.0b4"
        assert release.next_preview("26.2.0", "rc", tags) == "26.2.0rc1"
        assert (
            release.next_preview("26.2.0", "rc", tags + ["v26.2.0rc2"]) == "26.2.0rc3"
        )
        assert release.next_preview("27.1.0", "rc", tags) == "27.1.0rc1"

    def test_freeze_prevents_returning_to_beta(self):
        with pytest.raises(ValueError, match="freeze"):
            release.next_preview("26.2.0", "beta", ["v26.2.0rc1"])

    def test_final_release_closes_the_preview_series(self):
        for channel in ("beta", "rc"):
            with pytest.raises(ValueError, match="already been released"):
                release.next_preview("26.2.0", channel, ["v26.2.0"])

    def test_preview_selection_is_checked_before_merging(self):
        tags = ["v26.1.0rc1", "v26.1.0", "v26.2.0b1"]
        release.check_preview({"target": "26.1.0", "channel": "rc"}, tags)
        release.check_preview({"target": "26.2.0", "channel": "rc"}, tags)
        release.check_preview({"target": "26.3.0", "channel": "beta"}, tags)
        for config in [
            {"target": "26.2.0", "channel": "RC"},
            {"target": "26.1.0", "channel": "invalid"},
            {"target": "26.2", "channel": "rc"},
            {"target": "26.2.0"},
            {"target": "26.2.0", "channel": "rc", "extra": True},
            {"target": "26.2.0", "channel": "rc", "abandoned": "26.1.0"},
            {"target": "26.2.0", "channel": "rc", "abandoned": [26]},
        ]:
            with pytest.raises(ValueError):
                release.check_preview(config, tags)

    def test_preview_target_cannot_precede_a_published_stable_series(self):
        tags = ["v26.1.0", "v26.2.0rc1", "v26.2.0"]
        with pytest.raises(ValueError, match="older"):
            release.check_preview({"target": "26.1.0", "channel": "rc"}, tags)
        release.check_preview({"target": "26.2.0", "channel": "rc"}, tags)

    def test_active_rc_must_be_released_or_abandoned_before_switching(self):
        tags = ["v26.1.0", "v26.2.0b1", "v26.2.0rc1"]
        release.check_preview({"target": "26.2.0", "channel": "rc"}, tags)
        for config in [
            {"target": "26.3.0", "channel": "beta"},
            {"target": "26.1.0", "channel": "rc"},
        ]:
            with pytest.raises(ValueError, match="abandon"):
                release.check_preview(config, tags)
        with pytest.raises(ValueError, match="freeze"):
            release.check_preview({"target": "26.2.0", "channel": "beta"}, tags)
        release.check_preview(
            {"target": "26.3.0", "channel": "beta", "abandoned": ["26.2.0"]}, tags
        )
        release.check_preview(
            {"target": "26.3.0", "channel": "beta"}, tags + ["v26.2.0"]
        )

    def test_invalid_targets_and_channels_are_rejected(self):
        for target, channel in [
            ("26.0.0", "beta"),
            ("26.01.0", "beta"),
            ("26.-1.0", "beta"),
            ("2026.2.0", "beta"),
            ("6.2.0", "beta"),
            ("06.2.0", "beta"),
            ("26.2.1", "rc"),
            ("26.2.0b1", "beta"),
            ("26.2.0", "nightly"),
        ]:
            with pytest.raises(ValueError):
                release.next_preview(target, channel, [])

    @pytest.mark.parametrize("target", ["26.5.0", "26.12.0", "27.1.0"])
    def test_series_have_no_annual_limit_and_isolate_preview_numbers(self, target):
        tags = ["v26.1.0b99", "v26.2.0rc9", f"v{target}b2"]
        assert release.next_preview(target, "beta", tags) == f"{target}b3"
        assert release.next_preview(target, "rc", tags) == f"{target}rc1"
        with pytest.raises(ValueError, match="freeze"):
            release.next_preview(target, "beta", tags + [f"v{target}rc1"])
        with pytest.raises(ValueError, match="already been released"):
            release.next_preview(target, "rc", tags + [f"v{target}"])

    def test_retry_reuses_a_tag_for_the_same_source_commit(self):
        with (
            patch.object(release, "command") as command,
            patch.object(release, "publish_preview") as publish,
        ):
            with patch.object(release, "ROOT") as root:
                (
                    root / ".github/preview.json"
                ).read_text.return_value = '{"target":"26.2.0","channel":"beta"}'
                command.side_effect = [
                    "source-sha",
                    "",
                    "source-sha",
                    "v26.2.0b1",
                    "chore: prepare 26.2.0b1\n\nPreview-Source: source-sha",
                ]
                with patch.object(release, "write_version") as write:
                    release.preview()
            publish.assert_called_once_with("v26.2.0b1", "source-sha")
            write.assert_not_called()

    def test_outdated_push_does_not_replace_a_newer_preview(self):
        with (
            patch.object(release, "command") as command,
            patch.object(release, "publish_preview") as publish,
        ):
            with patch.object(release, "ROOT") as root:
                (
                    root / ".github/preview.json"
                ).read_text.return_value = '{"target":"26.2.0","channel":"beta"}'
                command.side_effect = ["old-source", "", "new-source"]
                release.preview()
            publish.assert_not_called()


class TestStamp:
    project = '[project]\nname = "tools"\nversion = "26.1.0"\ndependencies = ["component==1.2.3"]\n'
    lock = 'version = 1\n[[package]]\nname = "tools"\nversion = "26.1.0"\n[[package]]\nname = "component"\nversion = "1.2.3"\n'

    def test_preview_and_promotion_preserve_all_dependency_data(self):
        preview_project, preview_lock = release.stamp(
            self.project, self.lock, "26.2.0rc2"
        )
        stable_project, stable_lock = release.stamp(
            preview_project, preview_lock, "26.2.0"
        )
        for project, lock, version in [
            (preview_project, preview_lock, "26.2.0rc2"),
            (stable_project, stable_lock, "26.2.0"),
        ]:
            assert tomllib.loads(project)["project"]["dependencies"] == [
                "component==1.2.3"
            ]
            assert tomllib.loads(lock)["package"][1] == {
                "name": "component",
                "version": "1.2.3",
            }
            assert tomllib.loads(project)["project"]["version"] == version
            assert tomllib.loads(lock)["package"][0]["version"] == version

    def test_loose_pins_and_missing_lock_entry_are_rejected(self):
        with pytest.raises(ValueError, match="exact pin"):
            release.stamp(self.project.replace("==", ">="), self.lock, "26.2.0b1")
        with pytest.raises(ValueError, match="metapackage entry"):
            release.stamp(self.project, "version = 1\n", "26.2.0b1")

    def test_final_publication_rejects_pin_or_lock_drift_since_the_rc(self):
        candidate_project, candidate_lock = release.stamp(
            self.project, self.lock, "26.2.0rc1"
        )
        project, lock = release.stamp(candidate_project, candidate_lock, "26.2.0")
        release.verify_candidate_files(project, lock, candidate_project, candidate_lock)
        with pytest.raises(ValueError, match="metadata differs"):
            release.verify_candidate_files(
                project.replace("component==1.2.3", "component==1.2.4"),
                lock,
                candidate_project,
                candidate_lock,
            )
        with pytest.raises(ValueError, match="lockfile differs"):
            release.verify_candidate_files(
                project,
                lock.replace('version = "1.2.3"', 'version = "1.2.4"'),
                candidate_project,
                candidate_lock,
            )


class TestPromotion:
    def test_unreleased_check_skips_a_tagged_stable_version(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\nversion = "26.2.0"\n'
        )
        with (
            patch.object(release, "ROOT", tmp_path),
            patch.object(release, "command", return_value="v26.2.0") as command,
        ):
            release.verify_promotion(unreleased=True)
        command.assert_called_once_with("git", "tag", "--list", "v26.2.0")
        with (
            patch.object(release, "ROOT", tmp_path),
            patch.object(release, "command", return_value=""),
            pytest.raises(FileNotFoundError),
        ):
            # An untagged .0 release must name its RC.
            release.verify_promotion(unreleased=True)

    def test_changelog_starts_where_the_latest_older_series_branched(self):
        tags = "v26.1.0\nv26.1.10\nv26.1.9\nv26.2.0rc1\nv26.2.0\nv27.1.0rc1\n"
        with patch.object(
            release, "command", side_effect=[tags, '{"sha": "rc"}', "branch-point"]
        ) as command:
            assert release.previous_series_start("27.1.0", "candidate") == (
                "branch-point"
            )
        command.assert_called_with("git", "merge-base", "candidate", "rc")
        unpromoted = subprocess.CalledProcessError(128, "git show")
        with patch.object(
            release, "command", side_effect=[tags, unpromoted, "branch-point"]
        ) as command:
            release.previous_series_start("27.1.0", "candidate")
        command.assert_called_with("git", "merge-base", "candidate", "v26.2.0^{commit}")
        with patch.object(release, "command", return_value="v26.1.0rc1\n"):
            assert release.previous_series_start("26.1.0", "candidate") is None

    def test_only_a_successfully_published_rc_can_be_promoted(self):
        published = {"draft": False, "prerelease": True}
        success = [
            {
                "head_sha": "candidate",
                "head_branch": "v26.2.0rc2",
                "conclusion": "success",
            }
        ]
        assert (
            release.validate_candidate("v26.2.0rc2", published, success, "candidate")
            == "26.2.0"
        )
        for tag, metadata, runs in [
            ("v26.2.0b2", published, success),
            ("v26.2.0", published, success),
            ("v26.2.0rc2", {"draft": True, "prerelease": True}, success),
            ("v26.2.0rc2", {"draft": False, "prerelease": False}, success),
            ("v26.2.0rc2", published, []),
            ("v26.2.0rc2", published, [success[0] | {"head_sha": "other"}]),
            ("v26.2.0rc2", published, [success[0] | {"conclusion": "failure"}]),
            # A run dispatched from another ref can publish a different tag.
            ("v26.2.0rc2", published, [success[0] | {"head_branch": "main"}]),
            ("v26.2.0rc2", published, [success[0] | {"head_branch": "v26.2.0b1"}]),
        ]:
            with pytest.raises(ValueError):
                release.validate_candidate(tag, metadata, runs, "candidate")


@pytest.mark.parametrize("status", [404, 403, 500, None])
def test_preview_creates_a_release_only_when_it_is_missing(status):
    from unittest.mock import Mock

    from ghapi.core import APIError

    api = Mock()
    if status is not None:
        api.repos.get_release_by_tag.side_effect = APIError(
            "Failed", status_code=status
        )
    api.repos.get_release_by_tag.return_value = {"draft": False}
    api.repos.list_releases.side_effect = lambda page, per_page: []
    with (
        patch.object(release, "dispatch_release"),
        patch.object(release, "create_client", return_value=api),
    ):
        if status in (403, 500):
            with pytest.raises(APIError):
                release.publish_preview("v26.2.0b1", "source-sha")
        else:
            release.publish_preview("v26.2.0b1", "source-sha")
    if status == 404:
        api.git.get_ref.assert_called_once_with(ref="tags/v26.2.0b1")
        arguments = api.repos.create_release.call_args.kwargs
        assert arguments["tag_name"] == "v26.2.0b1"
        assert arguments["prerelease"] is True
        assert arguments["make_latest"] == "false"
        assert "source-sha" in arguments["body"]
    else:
        api.git.get_ref.assert_not_called()
        api.repos.create_release.assert_not_called()


def test_preview_requires_an_existing_remote_tag():
    from unittest.mock import Mock

    from ghapi.core import APIError

    api = Mock()
    api.repos.get_release_by_tag.side_effect = APIError(
        "Missing release", status_code=404
    )
    api.git.get_ref.side_effect = APIError("Missing tag", status_code=404)
    api.repos.list_releases.side_effect = lambda page, per_page: []
    with (
        patch.object(release, "create_client", return_value=api),
        pytest.raises(APIError),
    ):
        release.publish_preview("v26.2.0b1", "source-sha")
    api.repos.create_release.assert_not_called()


def test_main_maintenance_push_skips_a_target_already_released():
    with (
        patch.object(release, "ROOT") as root,
        patch.object(release, "command") as command,
        patch.object(release, "publish_preview") as publish,
        patch.object(release, "write_version") as write,
    ):
        (
            root / ".github/preview.json"
        ).read_text.return_value = '{"target":"26.2.0","channel":"rc"}'
        command.side_effect = ["source", "", "source", "v26.2.0"]
        release.preview()
    publish.assert_not_called()
    write.assert_not_called()


def test_preview_retry_reuses_draft_not_returned_by_tag_lookup():
    from unittest.mock import Mock

    from ghapi.core import APIError

    api = Mock()
    api.repos.get_release_by_tag.side_effect = APIError("Not Found", status_code=404)
    api.repos.list_releases.side_effect = lambda page, per_page: (
        [{"id": 42, "tag_name": "v26.2.0b1", "draft": True}] if page == 1 else []
    )
    with (
        patch.object(release, "create_client", return_value=api),
        patch.object(release, "dispatch_release") as dispatch,
    ):
        release.publish_preview("v26.2.0b1", "source")
    dispatch.assert_called_once_with(api, "v26.2.0b1")
    api.repos.create_release.assert_not_called()
    api.git.get_ref.assert_not_called()
