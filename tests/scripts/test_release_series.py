"""Validate release series version sequencing, RC promotion, and dependency preservation."""

import tomllib
from unittest.mock import patch

import pytest

import release_series as release


class TestPreview:
    def test_beta_and_rc_have_independent_monotonic_numbers(self):
        tags = ["v2026.1.0", "v2026.2.0b1", "v2026.2.0b3", "v2027.1.0b9"]
        assert release.next_preview("2026.2.0", "beta", tags) == "2026.2.0b4"
        assert release.next_preview("2026.2.0", "rc", tags) == "2026.2.0rc1"
        assert (
            release.next_preview("2026.2.0", "rc", tags + ["v2026.2.0rc2"])
            == "2026.2.0rc3"
        )
        assert release.next_preview("2027.1.0", "rc", tags) == "2027.1.0rc1"

    def test_freeze_prevents_returning_to_beta(self):
        with pytest.raises(ValueError, match="freeze"):
            release.next_preview("2026.2.0", "beta", ["v2026.2.0rc1"])

    def test_final_release_closes_the_preview_series(self):
        for channel in ("beta", "rc"):
            with pytest.raises(ValueError, match="already been released"):
                release.next_preview("2026.2.0", channel, ["v2026.2.0"])

    def test_invalid_targets_and_channels_are_rejected(self):
        for target, channel in [
            ("2026.0.0", "beta"),
            ("2026.01.0", "beta"),
            ("2026.-1.0", "beta"),
            ("2026.2.1", "rc"),
            ("2026.2.0b1", "beta"),
            ("2026.2.0", "nightly"),
        ]:
            with pytest.raises(ValueError):
                release.next_preview(target, channel, [])

    @pytest.mark.parametrize("target", ["2026.5.0", "2026.12.0", "2027.1.0"])
    def test_series_have_no_annual_limit_and_isolate_preview_numbers(self, target):
        tags = ["v2026.1.0b99", "v2026.2.0rc9", f"v{target}b2"]
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
                ).read_text.return_value = '{"target":"2026.2.0","channel":"beta"}'
                command.side_effect = [
                    "source-sha",
                    "",
                    "source-sha",
                    "v2026.2.0b1",
                    "chore: prepare 2026.2.0b1\n\nPreview-Source: source-sha",
                ]
                with patch.object(release, "write_version") as write:
                    release.preview()
            publish.assert_called_once_with("v2026.2.0b1", "source-sha")
            write.assert_not_called()

    def test_outdated_push_does_not_replace_a_newer_preview(self):
        with (
            patch.object(release, "command") as command,
            patch.object(release, "publish_preview") as publish,
        ):
            with patch.object(release, "ROOT") as root:
                (
                    root / ".github/preview.json"
                ).read_text.return_value = '{"target":"2026.2.0","channel":"beta"}'
                command.side_effect = ["old-source", "", "new-source"]
                release.preview()
            publish.assert_not_called()


class TestStamp:
    project = '[project]\nname = "tools"\nversion = "2026.1.0"\ndependencies = ["component==1.2.3"]\n'
    lock = 'version = 1\n[[package]]\nname = "tools"\nversion = "2026.1.0"\n[[package]]\nname = "component"\nversion = "1.2.3"\n'

    def test_preview_and_promotion_preserve_all_dependency_data(self):
        preview_project, preview_lock = release.stamp(
            self.project, self.lock, "2026.2.0rc2"
        )
        stable_project, stable_lock = release.stamp(
            preview_project, preview_lock, "2026.2.0"
        )
        for project, lock, version in [
            (preview_project, preview_lock, "2026.2.0rc2"),
            (stable_project, stable_lock, "2026.2.0"),
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
            release.stamp(self.project.replace("==", ">="), self.lock, "2026.2.0b1")
        with pytest.raises(ValueError, match="metapackage entry"):
            release.stamp(self.project, "version = 1\n", "2026.2.0b1")

    def test_final_publication_rejects_pin_or_lock_drift_since_the_rc(self):
        candidate_project, candidate_lock = release.stamp(
            self.project, self.lock, "2026.2.0rc1"
        )
        project, lock = release.stamp(candidate_project, candidate_lock, "2026.2.0")
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
    def test_only_a_successfully_published_rc_can_be_promoted(self):
        published = {"draft": False, "prerelease": True}
        success = [{"head_sha": "candidate", "conclusion": "success"}]
        assert (
            release.validate_candidate("v2026.2.0rc2", published, success, "candidate")
            == "2026.2.0"
        )
        for tag, metadata, runs in [
            ("v2026.2.0b2", published, success),
            ("v2026.2.0", published, success),
            ("v2026.2.0rc2", {"draft": True, "prerelease": True}, success),
            ("v2026.2.0rc2", {"draft": False, "prerelease": False}, success),
            ("v2026.2.0rc2", published, []),
            (
                "v2026.2.0rc2",
                published,
                [{"head_sha": "other", "conclusion": "success"}],
            ),
            (
                "v2026.2.0rc2",
                published,
                [{"head_sha": "candidate", "conclusion": "failure"}],
            ),
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
    with (
        patch.object(release, "dispatch_release"),
        patch.object(release, "create_client", return_value=api),
    ):
        if status in (403, 500):
            with pytest.raises(APIError):
                release.publish_preview("v2026.2.0b1", "source-sha")
        else:
            release.publish_preview("v2026.2.0b1", "source-sha")
    if status == 404:
        api.git.get_ref.assert_called_once_with(ref="tags/v2026.2.0b1")
        arguments = api.repos.create_release.call_args.kwargs
        assert arguments["tag_name"] == "v2026.2.0b1"
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
    with (
        patch.object(release, "create_client", return_value=api),
        pytest.raises(APIError),
    ):
        release.publish_preview("v2026.2.0b1", "source-sha")
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
        ).read_text.return_value = '{"target":"2026.2.0","channel":"rc"}'
        command.side_effect = ["source", "", "source", "v2026.2.0"]
        release.preview()
    publish.assert_not_called()
    write.assert_not_called()
