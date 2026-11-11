# Maintaining and releasing

Complete [repository setup](SETUP.md) before operating release automation.
Versions use `YEAR.SERIES.PATCH`; patches retain their year and series even when
published in a later year.

## Branches and automatic support

`main` prepares the upcoming series, including betas, release candidates, and
potentially breaking component updates. Each stable series has a maintenance
branch named `release/YEAR.SERIES`, for example `release/2026.1`. Individual
versions are tags such as `v2026.1.3`.

The two highest numbered published stable series receive automatic dependency
updates and patch releases. Draft releases and previews do not count. Publishing
a patch does not move the support window; publishing a new stable series retires
the oldest supported series. Older branches remain available for manual patches.
The release and merge workflows query published releases directly, so stale
Dependabot PRs cannot keep an unsupported series in automatic maintenance.

**Maintain release series** runs daily, on stable publication, and when its
configuration or release tooling changes on `main`. It opens a PR updating `.github/dependabot.yml`
from the templates in `.github/templates/`. The merge workflow merges this PR
after CI only when its contents exactly match the current support window.
Dispatch the maintenance workflow on `main` to reconcile immediately. It also
creates missing supported branches from their highest published patch tag and
opens a tooling installation PR. Review and merge that PR before using the branch
for maintenance. Retrying the workflow resumes a partial branch setup.
The setup PR aligns the distribution name with `main`, including the metapackage
entry in the lockfile and the Release Please version target, while preserving
the branch's version and component pins.

Dependabot checks the six SDK tools daily. On supported stable branches, it
groups compatible upgrades: minor and patch updates for components at version
1.0 or later, and patch updates below 1.0. On `main`, it can propose major
upgrades and pre-1.0 minor upgrades too. All runtime versions remain exact pins.
The development-and-automation group proposes minor and patch updates separately;
these require manual review and do not trigger releases on their own.
GitHub Actions updates target `main`.

Eligible dependency PRs merge after successful installation CI, with author,
file, version, and commit checks. Stable updates use `fix(deps):`; development
updates use `feat(deps):`. On `main`, automatic merging requires an active beta
cycle and CI against the current base commit. It stops during the RC freeze.
Installation tests do not establish behavioral compatibility; maintainers must
assess that separately.

Release Please runs on numbered release branches. It opens a PR updating the
version, changelog, manifest, and lockfile. Patch release PRs on supported series
merge automatically after CI. The first `.0` release of a series requires manual
review. Ordinary release commits increment only the patch number; the branch and
package version must identify the same series. Use `fix:` for package corrections
that need a release and `chore:` for routine tooling changes.

## Beta and release candidates

Set `.github/preview.json` on `main` to the intended target and channel:

```json
{
  "target": "2026.2.0",
  "channel": "beta"
}
```

Targets use `YEAR.SERIES.0`, with a positive series number without leading zeros.
Choose a target newer than all published stable series. Series numbers have no
annual limit; start at 1 for a new year.

Pushes to `main` create numbered previews such as `2026.2.0b1` when `fix:` or
`feat:` commits have appeared since the latest preview source. Scoped commits and
breaking-change markers are supported. Maintenance-only pushes skip subsequent
previews; the first preview for a target or channel is always created. Dispatch
**Release preview** on `main` to force a preview after maintenance changes.
The tagged preview commit stamps the version without advancing `main` or changing
component pins. Retries reuse the tag for the same source commit, and superseded
source commits are skipped.

To begin the RC freeze, merge a PR changing the channel to `rc`. The first RC is
created automatically. Once an RC exists, returning to beta for that target is
rejected. Further reviewed fixes produce numbered RCs. The intended final pins
must be validated before promotion.

## Promoting a stable series

1. Wait for the selected RC's **Validate and publish** run to succeed and finish
   user validation.
2. Dispatch **Promote release candidate** from `main`, supplying its exact RC tag,
   for example `v2026.2.0rc1`. It creates `release/2026.2` from that RC if needed,
   then opens a promotion PR against that release branch. Its package metadata
   and lockfile match the RC, with only the SDK version changed. The PR also
   records the RC tag and commit and initializes the branch's Release Please
   configuration and manifest.
3. Review and merge the promotion PR, preserving its `Release-As` footer. Configure
   squash merges to use the PR title and description. A newer RC updates the
   existing promotion PR, dismisses stale approvals, and requires fresh CI.
   Older RCs and moved candidate tags are rejected. Retries recover a pushed
   branch when PR creation fails; concurrent pushes are not overwritten.
4. Review and merge the Release Please PR for `.0`. Avoid dependency changes
   between promotion and publication: the publisher requires the selected RC's
   exact metadata and lockfile for the first stable release.
5. On `main`, update the preview target to the following series and reset its
   channel to `beta`. Previews stop for a target once its stable tag exists.

Stable patches continue independently on supported release branches throughout
this cycle. Backport relevant stable fixes to `main` through reviewed PRs.

## Manual patches for older series

Open a fix PR against the older `release/YEAR.SERIES` branch and pass its required
CI and reviews. Dispatch **Release Please** with that branch selected to prepare
a patch release PR. Review and merge it manually, then dispatch **Release Please**
on that branch again to create the release. The explicit dispatch permits older
series without reactivating Dependabot or automatic merging for them.
If necessary, backport current release tooling before starting this process.

## Publication and retries

Release Please and preview creation produce draft GitHub releases with existing
tags and explicitly dispatch **Validate and publish** on the tag. The publisher
verifies the tag, tests the full installation matrix, builds a wheel and source
distribution, and verifies uploaded assets before publishing the release.
Older-series patches and previews do not become GitHub's latest stable release.
Publication jobs share a repository-wide queue so their latest-version checks
and release publication cannot overlap across tags. Installation checks for
different tags can run concurrently.

To retry, dispatch **Validate and publish** with the existing tag. For RCs,
select the tag as the workflow ref too, so promotion can find the successful run
for that exact RC commit. Beta and stable retries can run from `main`. The
publisher uses current tooling from `main` to attach the distributions built
from the verified release commit. Matching assets are reused; differing or incomplete
assets fail rather than being replaced. Do not reuse a version for different
contents. Builds use the release commit timestamp for reproducible archives.

GitHub-only publication is the default. PyPI publication runs only when
`PYPI_PUBLISH_ENABLED` is exactly `true`. It publishes the verified build from an
immutable workflow artifact, with an integrity check, rather than rebuilding or
downloading mutable release assets. Each run attempt has its own artifact.
See [optional PyPI setup](SETUP.md#enabling-optional-pypi-publication).

## Shared tooling and validation

Develop tooling and workflow changes on `main`, then cherry-pick relevant focused
commits into supported release branches through PRs. Preserve branch-specific
versions, manifests, candidate records, dependency pins, and lockfiles. Backport
tooling to older branches when preparing a manual patch. Dependabot templates
live on `main`; edit the templates and run **Maintain release series** rather
than editing generated targets independently.

Run `just test` for lockfile and repository script checks. For dependency or
packaging changes, run `just test-all` for fresh wheel and source installation
checks across supported Python versions. See [local development](SETUP.md#local-development-and-validation).
