# Quantinuum Nexus SDK

A Python metapackage that installs an exact set of Quantinuum's user-facing tools.
It provides dependency metadata only; use each tool's own Python API.

This release supports CPython 3.12, 3.13, and 3.14, except Python 3.14 on Intel
macOS. On Intel Macs, use Python 3.12 or 3.13. This restriction also applies to
an Intel Python interpreter running through Rosetta on an Apple Silicon Mac;
use a native ARM64 interpreter for Python 3.14.

The pinned `guppyalgos`
release requires Python below 3.15. Supporting newer Python versions requires
compatible component releases and an updated `requires-python` bound.

After publication, install with:

```sh
uv --no-config pip install --default-index https://pypi.org/simple quantinuum-nexus-sdk==2026.1.0
```

The six runtime dependencies in `pyproject.toml` use exact `==` pins. `uv.lock`
also records transitive dependencies for repository development. Installing the
published package enforces the six direct pins; consumers resolve transitive
dependencies in their own environments.

## Development and validation

Install Python, uv 0.13.5, `just`, and Git, then run:

```sh
just setup                 # Install pinned dev tools and activate commit hooks
just test                  # Lockfile and script tests on 3.12/3.13/3.14
just test-scripts 3.13      # Script tests on one supported Python version
just test-package          # Fresh wheel and source installs on 3.12/3.13/3.14
just test-package 3.12      # Package tests on one Python version
just test-all              # All tests, including the installation matrix
just hooks                 # Run the pre-commit checks over all tracked files
```

`just` lists the available commands. Python versions come from `requires-python`
in `pyproject.toml`, shared by the local runner and CI. The bounded range is
enumerated without a network request; an unbounded range uses GitHub's stable
Python version manifest. uv downloads missing interpreters when needed.

Python tests use pytest, with exact pytest and pre-commit versions pinned in the
`dev` dependency group. The runner isolates pytest from the runtime dependencies
and runs each Python minor sequentially. Tests are separated by what they check:

- `tests/scripts/` checks repository tooling, including release and merge policies.
- `tests/package/` checks the metapackage itself, currently wheel and source installation.

An ordinary `pytest` run selects `tests/scripts/`. Use `pytest tests/package` to
select package tests or `pytest tests` to run both suites on the current Python.
The `just` commands run the selected suite across supported Python versions.

`just setup` installs a Git pre-commit hook in this checkout. On commits that
change Python code or relevant configuration, the hook runs pytest on every
supported Python minor, including approval, merge, and publication policy tests.
Dependency changes also check the lockfile. Documentation-only commits skip these
tests. The Python suite includes temporary Git repositories, so a full commit
check can take about a minute. Distribution installation tests run in CI and
through `just test-package` or `just test-all`.

Hooks must be installed once per clone. The pre-commit executable lives in the
persistent project `.venv`; run `just setup` again after recreating it. The test
repositories disable Git hooks to avoid recursive test runs during commits.

The approval, merge, and release workflows use `ghapi` with their GitHub App or
job tokens. Its exact version is pinned in the `automation` dependency group,
which is also included in `dev`. Git operations use the Git executable.
Tests mock GitHub responses and never submit real reviews or merges.

To run an automation script locally, set `GITHUB_REPOSITORY` to `owner/repository`
and `GH_TOKEN` to a token with the required permissions, then use
`python3 scripts/uv_pypi.py run --isolated --locked --only-group automation python scripts/<script>.py ...`.
The automation dependencies are excluded from the published SDK's runtime dependencies.

`scripts/uv_pypi.py` uses `uv.toml` explicitly, which excludes user- and
system-level uv configuration. It also removes package-index environment
overrides for the child process. Installation tests and CI use this same PyPI
configuration, without changing your global settings.

Use this wrapper for repository uv commands, including installing from this
checkout:

```sh
python3 scripts/uv_pypi.py pip install .
```

Bare `uv` commands still merge user-level index configuration. For an explicit
configuration without the wrapper, use `uv --config-file uv.toml ...`; environment
overrides still apply to that form. A published metapackage cannot control the
installer's indexes. For the published installation command above, unset
`UV_INDEX`, `UV_EXTRA_INDEX_URL`, and `UV_FIND_LINKS` if they are set.

The installation tests build a wheel and source distribution, install each
into a separate fresh environment, runs `uv pip check`, and verifies the installed
metapackage metadata and all six dependency versions. It resolves dependencies
as a consumer would, independently of the development lockfile.

GitHub CI checks the lockfile and both installation formats on every stable
CPython minor version in the declared Python range. It uses `ubuntu-latest`,
`windows-latest`, `macos-latest` (Apple Silicon), and `macos-26-intel` (the latest
standard Intel macOS image), excluding the unsupported Intel macOS/Python 3.14
combination. The explicit Intel label needs updating when GitHub
introduces a newer image. CI uses the same pytest runner as the just recipes,
running the script and package suites separately on each matrix cell.

## Updates and releases

On `main`, Dependabot checks the six tools daily, groups compatible updates into one PR,
and updates their exact pins and lockfile together. Updates use `fix(deps):`
commit messages, which produce a metapackage patch release. Stable components
allow minor and patch updates; components below 1.0 allow patch updates only.
Major component updates and pre-1.0 minor updates are proposed on `next` for the
upcoming quarter. Dependency versions alone cannot prove behavioral compatibility;
the automated gate currently tests installation only.

After CI succeeds, the merge workflow checks the PR author, changed files,
version changes, and tested commit SHA. Eligible Dependabot PRs merge
automatically. Release Please then opens a release PR with the version,
changelog, release manifest, and lockfile updated together. The first release
is `2026.1.0`; subsequent dependency updates produce `2026.1.1`, `2026.1.2`, etc.
The first release and patch release PRs merge automatically after CI passes.
Other release versions require review.

Versions follow `YEAR.QUARTER.PATCH`. Quarterly releases may contain breaking
changes; updates within a quarter must preserve compatibility. Release Please
uses patch increments for ordinary commits on `main`. Use Conventional Commits
such as `fix:` and `feat:` for release notes. Quarterly promotion supplies an
explicit `Release-As` footer to choose the next calendar version.

Publishing runs on a published GitHub release. It tests the release commit across
the full matrix again, checks that the tag matches the package version, builds
the distributions, and publishes through PyPI OIDC. To retry a failed publication,
dispatch the Publish workflow with its existing release tag.
For beta or RC retries, select that tag as the workflow ref as well as supplying
the tag input. Existing PyPI distribution files are skipped on retry.

## Quarterly betas, release candidates, and promotion

`main` maintains the stable quarter. The protected `next` branch prepares the
upcoming quarter, including potentially breaking component updates. Set
`.github/preview.json` on `next` to the intended target and channel:

```json
{
  "target": "2026.2.0",
  "channel": "beta"
}
```

The checked-in target is a starting value; set the intended year and quarter
before creating `next`. Targets use `YEAR.QUARTER.0` with a quarter from 1 to 4.
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
`rc`, an RC tag exists for the target, or the quarterly target is already
released. Dependabot can still open PRs during the freeze, but blocking fixes
must be reviewed and merged by a maintainer. Starting the following quarter's
beta target re-enables automation after fresh CI on its PRs. Merge stable fixes
into `next` as needed, preserving its preview target and channel.

Pushes to `next` create numbered versions such as `2026.2.0b1`, `b2`, and `b3`.
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
only reviewed fixes for blocking issues should change them. Further pushes
produce `rc2`, `rc3`, etc. The tooling prevents returning to beta after an RC
exists, and stops publishing previews once the final version exists.

Users opt in to a particular preview with an exact version:

```sh
python3 scripts/uv_pypi.py pip install quantinuum-nexus-sdk==2026.2.0rc1
```

For the official release:

1. Wait for the RC's Publish workflow to succeed and complete user validation.
2. Dispatch **Promote quarterly RC** from `main`, providing its tag, for example
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
4. Review and merge the quarterly Release Please PR. Neither quarterly PR is
   automatically merged. The official release runs the full matrix again and
   publishes the stable version with the candidate's exact dependency pins.
   Leave other dependency PRs unmerged during promotion; the publisher rejects
   metadata or lockfile changes that differ from the chosen RC.
   Automatic Dependabot merges pause between promotion and stable tag creation.
5. Update the preview target and reset the channel to `beta` on `next` for the
   following quarter. Targets are chosen explicitly rather than inferred from
   breaking-change commit messages.

Stable patches continue on `main` during the preview cycle. Protect `next` with
the same required installation checks as `main`, require branches to be up to
date, and allow the release App's approval to satisfy the dependency PR review
requirement. Additional human or code-owner review requirements still apply;
the App does not bypass them. The RC freeze and other configuration changes
require maintainer review. Preview releases never mark themselves
as GitHub's latest stable release. For a failed PyPI upload, retry **Publish**
with the existing tag; do not reuse that version for different contents.

## One-time repository setup

1. Create the GitHub repository, add its remote, and push an initial `feat:`
   commit to `main`. Enable GitHub Actions, Dependabot, and squash merges.
2. Create and install a GitHub App on this repository with Contents, Pull
   requests, and Issues read/write permissions, plus Actions read permission
   for RC promotion validation. Set the Actions variable
   `RELEASE_APP_CLIENT_ID` and secret `RELEASE_APP_PRIVATE_KEY`. Release and merge
   automation remain disabled until the client ID is configured. App tokens
   ensure bot-created PRs, merges, and releases trigger subsequent workflows.
3. Protect `main`: require the `Installation checks` status and require branches
   to be up to date before merging. Do not grant the release App a protection
   bypass. If reviews are required for every PR, a person must approve bot PRs;
   unattended updates need repository rules that permit them after the required
   checks pass.
4. On PyPI, configure a trusted publisher (or pending publisher for a new
   project) for `quantinuum-nexus-sdk`, your GitHub owner/repository,
   workflow `publish.yml`, and environment `pypi`. Create that GitHub environment;
   leave required reviewers unset for unattended publication. Package name
   availability and organization ownership must be confirmed before publishing.
5. Push the initial commit or dispatch Release Please. It creates the first
   release PR; passing CI starts the automated release chain.

The workflows honor repository protections. No hosted CI run or PyPI publication
occurs until the repository is pushed and these credentials are configured.
