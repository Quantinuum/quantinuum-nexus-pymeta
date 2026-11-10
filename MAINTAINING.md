# Maintaining and releasing

This guide describes how to update the SDK's dependency set and operate its
release workflows. Complete [repository setup](SETUP.md) before using the
release automation. See the [README](README.md#release-cycle) for the release
cycle from a package user's perspective.

## Updates and releases

On `main`, Dependabot checks the six tools daily, groups compatible updates into one PR,
and updates their exact pins and lockfile together. Updates use `fix(deps):`
commit messages, which produce a metapackage patch release. Stable components
allow minor and patch updates; components below 1.0 allow patch updates only.
Major component updates and pre-1.0 minor updates are proposed on `next` for the
upcoming series. Dependency versions alone cannot prove behavioral compatibility;
the automated gate currently tests installation only.

On `main` and `next`, the SDK tools group matches the six SDK packages first.
The following `development-and-automation` group captures minor and patch
updates for all other manifest dependencies, including newly added development and automation
tools, without a separate allowlist. Development dependency updates use
`chore(deps-dev):` commit messages, require manual review and merging, and do not
trigger a stable SDK release on their own. Review the commit type for build
dependency updates: use `chore:` for routine maintenance or `fix:` when correcting
the published package. On `main`, major maintenance updates require manual
updates; on `next`, Dependabot can propose them as separate PRs for review.
Keep the pre-commit minimum version in `.pre-commit-config.yaml` consistent
with the supported tool version when reviewing pre-commit updates. Merge
maintenance changes between branches as needed. Dependabot checks development
and automation dependencies independently on both branches. GitHub Actions
updates target the default branch and must be merged into `next` as needed.

After CI succeeds, the merge workflow checks the PR author, changed files,
version changes, and tested commit SHA. Eligible Dependabot PRs merge
automatically. Release Please then opens a release PR with the version,
changelog, release manifest, and lockfile updated together. The first release
is `2026.1.0`; subsequent dependency updates produce `2026.1.1`, `2026.1.2`, etc.
The first release and patch release PRs merge automatically after CI passes.
Other release versions require review.

Versions follow `YEAR.SERIES.PATCH`. The year identifies when the series begins;
the series number starts at 1 each year and increases for each new series,
without a fixed release schedule or annual limit. The patch number starts at 0.
Patches retain their series' year even when published in a later year.
New series may contain breaking changes; patches within a series must preserve
compatibility. Release Please uses patch increments for ordinary commits on
`main`. Use Conventional Commits
such as `fix:` and `feat:` for release notes. Release series promotion supplies an
explicit `Release-As` footer to choose the next calendar version.

Publishing runs on a published GitHub release. It tests the release commit across
the full matrix again, checks that the tag matches the package version, builds
the distributions, and publishes through PyPI OIDC. To retry a failed publication,
dispatch the Publish workflow with its existing release tag.
For beta or RC retries, select that tag as the workflow ref as well as supplying
the tag input. Existing PyPI distribution files are skipped on retry.

## Release series betas, release candidates, and promotion

`main` maintains the stable series. The protected `next` branch prepares the
upcoming series, including potentially breaking component updates. Set
`.github/preview.json` on `next` to the intended target and channel:

```json
{
  "target": "2026.2.0",
  "channel": "beta"
}
```

The checked-in target is a starting value; set the intended year and series
before creating `next`. Targets use `YEAR.SERIES.0` with a positive series number
without leading zeros. Choose a target newer than the stable series on `main`;
start at series 1 when opening the first series for a new year.
Create `next` from `main`. A separate daily Dependabot configuration proposes
grouped upgrades of the six tools on `next`, including major upgrades and minor
upgrades below 1.0. All component versions remain exact pins. Compatible minor
and patch upgrades are included too, so the beta set can stay current.

After a Dependabot PR passes CI against the current `next` base commit, the
release App submits an approval for that exact head commit and squash merges
the PR. This triggers the next beta release. Automatic approval only applies
to PRs authored by Dependabot that change the six tool pins and lockfile;
project settings, additional files, downgrades, and component prereleases
require manual review. The script rechecks the beta phase and branch commit
before approval and merging, and does not duplicate existing approvals.

Automatic dependency approval and merging on `next` stop when the channel is
`rc`, an RC tag exists for the target, or the release series target is already
released. Dependabot can still open PRs during the freeze, but blocking fixes
must be reviewed and merged by a maintainer. Starting the next series'
beta target re-enables automation after fresh CI on its PRs. Merge stable fixes
into `next` as needed, preserving its preview target and channel.

Pushes to `next` create numbered versions such as `2026.2.0b1`, `b2`, and `b3`
when there are `fix:` or `feat:` commits since the latest preview in the current
target and channel. Scoped commits and their `!` forms are supported. A push
containing only maintenance, CI, or documentation commits does not create
another preview, but still runs CI. The full commit range since the previous
preview's source is checked, so a later maintenance commit does not hide an
unreleased fix or feature. Use `fix:` for packaging corrections that need a
preview, and `chore:` for routine tooling maintenance.

The first preview for a target or channel is created automatically, including
the first RC after switching from beta. To explicitly create a preview after
maintenance changes, dispatch **Release preview** on `next`. The local
equivalent is `python scripts/release_series.py preview --force`, run with the
automation environment and credentials described in [setup](SETUP.md).
Manual requests retain the target, freeze, stale-commit, and retry checks.

The preview workflow stamps the metapackage version into `pyproject.toml` and
`uv.lock` in a tagged commit without advancing either branch or changing
dependency versions. It creates a GitHub prerelease, which triggers the Publish
workflow. That workflow runs the full installation matrix on the tagged commit
before publishing to the same PyPI project as stable releases. GitHub prerelease
creation alone does not indicate successful PyPI publication; check Publish.
Rerunning the preview workflow for the same source commit reuses its tag.
Queued runs for superseded `next` commits are skipped so an older snapshot
cannot become the newest preview.

To start the release candidate freeze, merge a PR on `next` changing `channel`
to `rc`. This publishes `2026.2.0rc1`. Treat its pins as the intended final set;
only reviewed fixes for blocking issues should change them. Further release
commits produce `rc2`, `rc3`, etc.; maintenance-only pushes skip publication.
The tooling prevents returning to beta after an RC
exists, and stops publishing previews once the final version exists.

Users opt in to a particular preview with an exact version:

```sh
python3 scripts/uv_pypi.py pip install quantinuum-nexus-sdk==2026.2.0rc1
```

For the official release:

1. Wait for the RC's Publish workflow to succeed and complete user validation.
2. Dispatch **Promote release candidate** from `main`, providing its tag, for example
   `v2026.2.0rc1`. It rejects betas and RCs without a successful Publish run for
   that exact commit, and opens a promotion PR with the candidate's exact
   dependency metadata and lockfile, changing only the metapackage version.
   It also records the RC tag and commit used for publication verification.
   Selecting a newer RC updates an existing promotion PR with a new commit,
   which triggers fresh CI, and updates its description and candidate record.
   The workflow temporarily makes the PR a draft and dismisses approvals of
   older revisions before restoring its ready state. An intentionally draft PR
   stays a draft. Repeating a completed promotion for the same RC is a no-op;
   choosing an older RC or a moved RC tag is rejected.
   If PR creation fails after the promotion branch was pushed, rerun the workflow.
   It validates and reuses that branch, preserving its commit for the same RC or
   appending a commit for a newer RC. Concurrent branch changes cause the push to
   fail instead of overwriting them.
3. Review and merge the promotion PR. Preserve its `Release-As` footer in the
   squash commit. Configure GitHub's default squash message as **Pull request
   title and description** to retain this footer automatically.
   Require at least one approving review on `main`, enable dismissal of stale
   approvals, and permit the release App to dismiss reviews. If an update cannot
   dismiss old approvals, the workflow fails and leaves the PR as a draft; resolve
   that restriction and rerun before making it ready for a fresh review.
4. Review and merge the Release Please PR for the new series. Both this PR and
   the promotion PR require manual review and merging. The official release
   runs the full matrix again and
   publishes the stable version with the candidate's exact dependency pins.
   Leave other dependency PRs unmerged during promotion; the publisher rejects
   metadata or lockfile changes that differ from the chosen RC.
   Automatic Dependabot merges pause between promotion and stable tag creation.
5. Update the preview target and reset the channel to `beta` on `next` for the
   following series. Targets are chosen explicitly rather than inferred from
   breaking-change commit messages.

Stable patches continue on `main` during the preview cycle. Protect `next` with
the same required installation checks as `main`, require branches to be up to
date, and allow the release App's approval to satisfy the dependency PR review
requirement. Additional human or code-owner review requirements still apply;
the App does not bypass them. The RC freeze and other configuration changes
require maintainer review. Preview releases never mark themselves
as GitHub's latest stable release. For a failed PyPI upload, retry **Publish**
with the existing tag; do not reuse that version for different contents.

## Validating changes

Run `just test` for lockfile and repository script checks. For dependency or
packaging changes, run `just test-all` to include fresh wheel and source
installation tests across supported Python versions. See
[Development and validation](SETUP.md#local-development-and-validation) for
individual commands, environment setup, and CI details.
