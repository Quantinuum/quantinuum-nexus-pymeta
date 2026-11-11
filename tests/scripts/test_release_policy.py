"""Check support-window rollover, manual patches, and series identity."""

from unittest.mock import Mock

import pytest

from release_policy import published_series, release_allowed, supported_branches


def metadata(tag, draft=False, prerelease=False):
    return {"tag_name": tag, "draft": draft, "prerelease": prerelease}


def client(releases):
    api = Mock()
    api.repos.list_releases.side_effect = lambda page, per_page: (
        releases if page == 1 else []
    )
    return api


def test_support_window_counts_series_numerically_and_ignores_previews_and_drafts():
    api = client(
        [
            metadata("v2026.2.99"),
            metadata("v2026.12.1"),
            metadata("v2026.9.5"),
            metadata("v2026.12.0"),
            metadata("v2027.1.0rc1", prerelease=True),
            metadata("v2027.1.0", draft=True),
            metadata("v2026.01.0"),
        ]
    )
    assert published_series(api) == {
        "release/2026.12": "v2026.12.1",
        "release/2026.9": "v2026.9.5",
        "release/2026.2": "v2026.2.99",
    }
    assert supported_branches(api) == ["release/2026.12", "release/2026.9"]
    assert not release_allowed(api, "release/2026.2", "2026.2.100")
    assert release_allowed(api, "release/2026.2", "2026.2.100", manual=True)


def test_new_stable_series_retires_oldest_but_patches_do_not():
    releases = [metadata("v2026.1.0"), metadata("v2026.2.0")]
    api = client(releases)
    assert release_allowed(api, "release/2026.1", "2026.1.1")
    releases.append(metadata("v2026.2.10"))
    assert release_allowed(api, "release/2026.1", "2026.1.1")
    releases.append(metadata("v2027.1.0"))
    assert not release_allowed(api, "release/2026.1", "2026.1.1")
    assert release_allowed(api, "release/2026.2", "2026.2.11")


def test_one_or_no_published_series_and_initial_promotion():
    assert supported_branches(client([])) == []
    api = client([metadata("v2026.1.0")])
    assert supported_branches(api) == ["release/2026.1"]
    assert release_allowed(api, "release/2026.2", "2026.2.0")
    assert not release_allowed(api, "release/2026.2", "2026.2.1")
    assert not release_allowed(api, "release/2025.1", "2025.1.0")


@pytest.mark.parametrize("manual", [False, True])
def test_branch_version_mismatch_is_never_allowed(manual):
    with pytest.raises(ValueError, match="belong"):
        release_allowed(client([]), "release/2026.1", "2026.2.0", manual)
    with pytest.raises(ValueError):
        release_allowed(client([]), "main", "2026.1.0", manual)


def test_release_listing_is_paginated():
    api = Mock()
    api.repos.list_releases.side_effect = lambda page, per_page: {
        1: [metadata("v2026.2.0b1", prerelease=True)],
        2: [metadata("v2026.1.0")],
    }.get(page, [])
    assert supported_branches(api) == ["release/2026.1"]
