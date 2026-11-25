# Maintaining and releasing

Complete [repository setup](SETUP.md) before operating release automation.
Versions use `YY.SERIES.PATCH`, where `YY` is the two-digit year, such as `26`
for 2026. Patches retain their year and series even when published in a later year.

## Branches and automatic support

`main` prepares the upcoming series, including betas, release candidates, and
potentially breaking component updates. Each stable series has a maintenance
branch named `release/YY.SERIES`, for example `release/26.1`. Individual
versions are tags such as `v26.1.3`.

The two highest numbered published stable series receive automatic dependency
updates and patch releases. Draft releases and previews do not count. Publishing
a patch does not move the support window; publishing a new stable series retires
the oldest supported series. Older branches remain available for manual patches.

### What is pinned

`pyproject.toml` pins every Quantinuum-maintained package in the resolved
environment with `==`: the six SDK components, and the supporting Quantinuum
packages they depend on, such as `hugr`, `tket`, and `selene-core`. A release
therefore identifies one exact version of all Quantinuum code. Third-party
dependencies stay as ranges so the SDK installs alongside other software; the
lockfile, and the `pylock.toml` attached to each release, record their exact
tested versions.

The **Quantinuum pins** CI check (`scripts/quantinuum_pins.py`) enforces this.
It looks up each runtime package in `uv.lock` on PyPI and fails when a
package linking to github.com/Quantinuum or github.com/CQCL, or maintained
from a quantinuum.com address, is not pinned. It also fails when the README's
"Included tools" section does not list exactly the pinned packages. To add a
component, pin it and any new Quantinuum packages it pulls in, list them in the
README, then run `uv lock`. When a Renovate update introduces a new Quantinuum
dependency, push the missing pin and README entry to the Renovate branch.

### Dependency updates with Renovate

[Renovate](https://docs.renovatebot.com/) proposes dependency updates, as
configured in [`renovate.json`](renovate.json). It is self-hosted: the
**Renovate** workflow runs it every four hours as the release bot. Dispatch
the workflow to run it immediately. Renovate reads its configuration only
from `main`. Each run updates `main` and the two supported release branches,
which the workflow selects from published stable releases and passes to
Renovate as a forced `baseBranchPatterns`, overriding the main-only default in
`renovate.json`. A new series joins
once its `.0` is published, and the oldest series drops out at the same time.
Renovate updates `uv.lock` with the same uv version CI uses.

| Branch | Runtime pins (Quantinuum packages) | Merge |
| --- | --- | --- |
| `main` | All updates, including major and pre-1.0 minor, in one `feat(deps):` group | Automatic |
| `release/*` | Patch updates, in one `fix(deps):` group | Automatic |
| `release/*` | Minor updates of packages at 1.0 or later, in one `fix(deps):` group | Review |
| `release/*` | Major updates, and minor updates below 1.0 | Not proposed |

Development tools and build requirements are grouped as `chore(deps):` on every
branch and require review; they never trigger a release. GitHub Actions updates
target `main` only, as `ci(deps):`, and also require review. A uv update
changes the workflows, the uv constraint in `renovate.json`, and the version in
`SETUP.md` together, so CI and Renovate always use the same uv. The workflows'
Python version follows `.python-version` and is not updated by Renovate, nor is
the supported Python range. The Dependency Dashboard issue that
Renovate opens lists pending and rate-limited updates; checking a box there
starts a workflow run that creates or rebases that update.

### Merge queue

`main` merges through a GitHub merge queue that requires **Installation
checks**. When Renovate marks a PR for automerge, it enables GitHub's
auto-merge; the PR enters the queue once its checks pass, and the queue runs CI
again against the combination of the latest base branch and every PR ahead of
it. A PR therefore merges only if it installs correctly as it will land, and
simultaneous updates cannot break each other. Maintainers merge reviewed PRs
the same way, with **Merge when ready**.

GitHub does not support merge queues on wildcard branch patterns, so
`release/*` branches instead require PRs to be up to date with their branch
before merging. Renovate and Release Please keep their PRs rebased, and
auto-merge merges them once **Installation checks** passes on the updated
branch.

During the RC freeze (`channel` is `rc` in `.github/preview.json`), the
**Dependency freeze** CI check fails for Renovate PRs into `main` that change
`pyproject.toml` or `uv.lock`, including development tool updates. They stay
open until `main` returns to a beta channel. Tooling-only updates, such as
workflow actions and uv, are not held. Renovate rebases automerging
updates when `main` changes; for the others, check their boxes (or the box to
rebase all open PRs) in the Dependency Dashboard so CI runs again. Other PRs,
and release branches, are unaffected. CI also rejects a PR that makes
`.github/preview.json` invalid or returns a series to beta after its first RC.

On a release branch, CI keeps an unreleased `.0` identical to its selected RC:
until the stable tag exists, a PR into the branch fails if its package metadata
or lockfile differs from the RC. The **Release Please** workflow repeats this
check before tagging.

Every release-branch PR is opened by the release bot, so the **Release review**
check, rather than GitHub's approval count, decides which PRs need review. It
passes for Renovate PRs that only apply patch upgrades to existing runtime pins,
and for release PRs that the **Release Please** workflow would merge
automatically. Any other PR needs an approval of its current commit from a
maintainer with write access other than its author, and no outstanding change
requests. Submitting, editing, or dismissing a review re-runs the PR's existing
check through the **Release review refresh** workflow, so the status updates in
place. Reviews on PRs from forks cannot re-run it; re-run the check manually.

Installation tests do not establish behavioral compatibility; maintainers must
assess that separately.

### Patch releases

Release Please runs on numbered release branches. It opens a PR updating the
version, changelog, manifest, and lockfile. The **Release Please** workflow then
enables auto-merge for that PR, guarded by its head commit, when all of the
following hold:

- the branch is a supported series and the PR contains only release files;
- the version is a patch increment within the branch's series, not a `.0`;
- every runtime pin is unchanged or a patch upgrade since the previous release,
  and no pin was added or removed.

Otherwise it leaves the PR for review, disabling auto-merge if it was enabled
for an earlier state. Each run disables existing auto-merge before
re-evaluating, so a failed run never leaves a newer revision queued. If the PR's
checks have already passed, it merges the PR directly. So a minor upgrade requires human review of both the
dependency PR and the SDK release PR. Use `fix:` for package corrections that
need a release and `chore:` for routine tooling changes.

## Initial stable release

`26.1.0` is released through the normal RC flow. `main` starts with the
original 26.1 pins and `.github/preview.json` set to the `26.1.0` RC channel.
Release Please's manifest is empty and its `bootstrap-sha` marks the start of
release history. Each later promotion moves `bootstrap-sha` to the commit where
the previous stable series branched from `main`, so a new series' changelog
lists only the changes made since then.

1. Merging to `main` creates `v26.1.0rc1`.
2. Promote it as described in [Promoting a stable series](#promoting-a-stable-series).
   This creates `release/26.1`.
3. Once `v26.1.0` is published, merge a PR on `main` setting the preview target
   to `26.2.0` with the `beta` channel. Renovate then resumes updates to `main`
   and starts updating `release/26.1`.

## Beta and release candidates

Set `.github/preview.json` on `main` to the intended target and channel:

```json
{
  "target": "26.2.0",
  "channel": "beta"
}
```

Targets use `YY.SERIES.0`, with a positive series number without leading zeros.
Choose a target newer than all published stable series; CI rejects older
targets. Series numbers have no annual limit; start at 1 for a new year.

Once a target has an RC, CI rejects selecting another target until that RC's
stable release is published, so the freeze cannot be lifted by accident. To
abandon an RC series deliberately, list it in `abandoned`:

```json
{
  "target": "26.3.0",
  "channel": "beta",
  "abandoned": ["26.2.0"]
}
```

Pushes to `main` create numbered previews such as `26.2.0b1` when `fix:` or
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
   for example `v26.2.0rc1`. It creates `release/26.2` from that RC if needed,
   then opens a promotion PR against that release branch. Its package metadata
   and lockfile match the RC, with only the SDK version changed. The PR also
   records the RC tag and commit and initializes the branch's Release Please
   configuration and manifest.
3. Review and merge the promotion PR, preserving its `Release-As` footer. Configure
   squash merges to use the PR title and description. A newer RC updates the
   existing promotion PR with a merge of that RC, so all of its changes reach
   the release branch, not only its pins. The `.0` changelog then lists the
   promotion as one entry rather than each commit since the earlier RC. It also dismisses stale approvals and
   requires fresh CI.
   Older RCs and moved candidate tags are rejected. Retries recover a pushed
   branch when PR creation fails; concurrent pushes are not overwritten.
4. Review and merge the Release Please PR for `.0`. The publisher requires the
   selected RC's exact metadata and lockfile for the first stable release, so
   CI rejects dependency changes to the branch until the `.0` is tagged. To
   change dependencies, cut a new RC on `main` and promote it. Renovate does not
   update the new branch until the `.0` is published; from then on, it receives
   dependency updates and automatic patch releases.
5. On `main`, update the preview target to the following series and reset its
   channel to `beta`. Previews stop for a target once its stable tag exists, and
   Renovate updates to `main` resume merging.

Stable patches continue independently on supported release branches throughout
this cycle. Backport relevant stable fixes to `main` through reviewed PRs.

## Manual patches for older series

Open a fix PR against the older `release/YY.SERIES` branch and pass its required
CI and reviews. Dispatch **Release Please** with that branch selected to prepare
a patch release PR. Review and merge it manually, then dispatch **Release Please**
on that branch again to create the release. The explicit dispatch permits older
series without reactivating Renovate or automatic merging for them.
If necessary, backport current release tooling before starting this process.

## Publication and retries

Release Please and preview creation produce draft GitHub releases with existing
tags and explicitly dispatch **Validate and publish** on the tag. The publisher
verifies the tag, runs the installation checks, builds a wheel and source
distribution, exports `pylock.toml` from the release commit's `uv.lock`, and
verifies uploaded assets before publishing the release.
Older-series patches and previews do not become GitHub's latest stable release.
Publication jobs share a repository-wide queue so their latest-version checks
and release publication cannot overlap across tags. Installation checks for
different tags can run concurrently.

To retry, dispatch **Validate and publish** with the existing tag. For RCs,
select the tag as the workflow ref too: promotion only accepts a successful run
from the RC's own tag ref, and the publisher rejects a tag ref that differs from
the tag being published. Beta and stable retries can run from `main`. The
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
tooling to older branches when preparing a manual patch. Renovate configuration
lives only on `main`; copies on release branches are ignored.

Run `just test` for lockfile and repository script checks. For dependency or
packaging changes, run `just test-all` for fresh wheel and source installation
checks across supported Python versions. See [local development](SETUP.md#local-development-and-validation).
