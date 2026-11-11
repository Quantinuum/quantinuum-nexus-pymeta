# Development and repository setup

This guide covers local development and the one-time configuration needed to
operate this repository. To install the published SDK for use in your own
project, see the [README](README.md#installation).

## Local development and validation

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

`just setup` installs a Git pre-commit hook in this checkout. The hooks run
Ruff's linter with safe automatic fixes, format Python files, trim trailing
whitespace, ensure a single final newline, and normalize text line endings to
LF. Markdown hard line breaks are preserved. Hook tool versions are pinned in
`.pre-commit-config.yaml`; pre-commit installs them in isolated environments.
If a hook modifies files, review and stage the changes before committing again.

To lint or format every tracked Python file explicitly, run:

```sh
just hooks ruff-check --all-files
just hooks ruff-format --all-files
```

On commits that change Python code or relevant configuration, the hook runs
pytest on every supported Python minor, including approval, merge, and
publication policy tests.
Dependency changes also check the lockfile. Documentation-only commits skip these
tests. The Python suite includes temporary Git repositories, so a full commit
check can take about a minute. Distribution installation tests run in CI and
through `just test-package` or `just test-all`.

Hooks must be installed once per clone. The pre-commit executable lives in the
persistent project `.venv`; run `just setup` again after recreating it. The test
repositories disable Git hooks to avoid recursive test runs during commits.

The approval, merge, and release workflows use `ghapi` with the bot account
PAT or built-in job tokens. Its exact version is pinned in the `automation` dependency group,
which is also included in `dev`. Git operations use the Git executable.
Tests mock GitHub responses and never submit real reviews or merges.

To run an automation script locally, set `GITHUB_REPOSITORY` to `owner/repository`
and `GH_TOKEN` to a token with the required permissions, then use
`python3 scripts/uv_pypi.py run --isolated --locked --only-group automation python scripts/<script>.py ...`.
The automation dependencies are excluded from the published SDK's runtime dependencies.

Commands that dispatch publication also require `WORKFLOW_DISPATCH_TOKEN`, a
token with Actions write permission. GitHub Actions jobs supply their built-in
`GITHUB_TOKEN` for this purpose.

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
installer's indexes. For the published uv installation command in the [README](README.md#installation), unset
`UV_INDEX`, `UV_EXTRA_INDEX_URL`, and `UV_FIND_LINKS` if they are set.

The installation tests build a wheel and source distribution, install each
into a separate fresh environment, run `uv pip check`, and verify the installed
metapackage metadata and all six dependency versions. They resolve dependencies
as a consumer would, independently of the development lockfile.

GitHub CI checks the lockfile and both installation formats on every stable
CPython minor version in the declared Python range. It uses `ubuntu-latest`,
`windows-latest`, `macos-latest` (Apple Silicon), and `macos-26-intel` (the latest
standard Intel macOS image), excluding the unsupported Intel macOS/Python 3.14
combination. The explicit Intel label needs updating when GitHub
introduces a newer image. CI uses the same pytest runner as the just recipes,
running the script and package suites separately on each matrix cell.

## One-time repository setup

1. Use `main` as the default development branch. Set `.github/preview.json` to
   the upcoming series and enable Actions, Dependabot, and squash merges.
   Configure the default squash message as **Pull request title and description**
   to preserve promotion footers.
2. Set `HUGRBOT_PAT` to the release bot account's personal access token. It needs
   Contents, Pull requests, and Issues read/write, plus Actions read permission
   for validating candidates. Publication dispatch uses the job's built-in
   `GITHUB_TOKEN` with Actions write permission. Branch bootstrap writes
   workflow files, so the token also needs permission to update workflows.
   The account must have repository access and any required organization/SSO
   authorization. The bot's login is resolved from the token. Renew it before
   expiry. The PAT allows bot-created PRs and releases to trigger CI.
3. Protect `main` and all `release/*` branches. Require PRs, the **Installation
   checks** status, up-to-date branches, and resolution of review conversations;
   block force pushes and deletion. Configure a ruleset under repository
   Settings → Rules → Rulesets targeting the default branch and `release/*`.
   New numbered branches inherit the rule automatically.
   Require no approving reviews so the bot can merge its own patch
   release PRs after CI. Additional human/code-owner review requirements prevent
   unattended merges until those reviews arrive. Main's development dependency
   PRs receive the bot's approval; other changes need maintainer review.
   The bot does not bypass required checks. Limit release-branch creation to
   maintainers and the release bot if repository rules allow it.

   GitHub plan and repository visibility determine protection availability.
   If protection is unavailable, the automation still checks eligibility and CI,
   but cannot stop other writers from pushing or merging directly.
4. Leave `PYPI_PUBLISH_ENABLED` unset or `false` for GitHub-only publication.
5. Dispatch **Maintain release series** from `main` to initialize branches for
   existing published series. Review and merge its tooling installation PRs.
   For a new series, use the beta/RC and promotion process in
   [Maintaining and releasing](MAINTAINING.md). The support window contains one
   series until a second stable series has been published.

The maintenance workflow creates missing supported branches from their published
release tags and aligns their distribution name with `main`, preserving package
versions, component pins, other lockfile data, and release manifests.
Review the generated branch setup PR before enabling patch
updates. Published tags and release assets are left intact.

The workflows honor repository protections. CI runs after the repository is
pushed; release automation additionally requires the `HUGRBOT_PAT` repository secret.

## Enabling optional PyPI publication

1. Confirm package name availability and Quantinuum ownership on PyPI. Configure
   a trusted publisher (or pending publisher for a new project) for
   `quantinuum-nexus`, GitHub owner `Quantinuum`, repository
   `quantinuum-nexus-pymeta`, workflow filename `publish.yml`, and environment
   `pypi`.
2. Create the GitHub environment `pypi`. Leave required reviewers unset for
   unattended publication, or configure them if publication should require
   approval.
3. Set the Actions **repository variable** `PYPI_PUBLISH_ENABLED` to exactly
   `true`. The build job preserves the wheel and source distribution in an
   immutable workflow artifact. The optional PyPI job downloads it by its
   exact ID, requires a matching integrity digest, and uploads those same
   files using OIDC. No PyPI API token is required.

To publish an existing GitHub release to PyPI after enabling the variable,
rerun **Validate and publish** with that release tag. For a beta or RC, also
select the tag as the workflow ref. Setting the variable to `false` or removing
it disables subsequent PyPI uploads without disabling GitHub releases.

For dependency updates, preview releases, release series promotion, and publication
retries, see [Maintaining and releasing](MAINTAINING.md).
