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
            metadata("v26.2.99"),
            metadata("v26.12.1"),
            metadata("v26.9.5"),
            metadata("v26.12.0"),
            metadata("v27.1.0rc1", prerelease=True),
            metadata("v27.1.0", draft=True),
            metadata("v26.01.0"),
            metadata("v2026.1.0"),
        ]
    )
    assert published_series(api) == {
        "release/26.12": "v26.12.1",
        "release/26.9": "v26.9.5",
        "release/26.2": "v26.2.99",
    }
    assert supported_branches(api) == ["release/26.12", "release/26.9"]
    assert not release_allowed(api, "release/26.2", "26.2.100")
    assert release_allowed(api, "release/26.2", "26.2.100", manual=True)


def test_new_stable_series_retires_oldest_but_patches_do_not():
    releases = [metadata("v26.1.0"), metadata("v26.2.0")]
    api = client(releases)
    assert release_allowed(api, "release/26.1", "26.1.1")
    releases.append(metadata("v26.2.10"))
    assert release_allowed(api, "release/26.1", "26.1.1")
    releases.append(metadata("v27.1.0"))
    assert not release_allowed(api, "release/26.1", "26.1.1")
    assert release_allowed(api, "release/26.2", "26.2.11")


def test_one_or_no_published_series_and_initial_promotion():
    assert supported_branches(client([])) == []
    api = client([metadata("v26.1.0")])
    assert supported_branches(api) == ["release/26.1"]
    assert release_allowed(api, "release/26.2", "26.2.0")
    assert not release_allowed(api, "release/26.2", "26.2.1")
    assert not release_allowed(api, "release/25.1", "25.1.0")


@pytest.mark.parametrize("manual", [False, True])
def test_branch_version_mismatch_is_never_allowed(manual):
    with pytest.raises(ValueError, match="belong"):
        release_allowed(client([]), "release/26.1", "26.2.0", manual)
    with pytest.raises(ValueError):
        release_allowed(client([]), "main", "26.1.0", manual)


def test_release_listing_is_paginated():
    api = Mock()
    api.repos.list_releases.side_effect = lambda page, per_page: {
        1: [metadata("v26.2.0b1", prerelease=True)],
        2: [metadata("v26.1.0")],
    }.get(page, [])
    assert supported_branches(api) == ["release/26.1"]
