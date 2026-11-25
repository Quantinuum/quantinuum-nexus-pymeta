# Development and repository setup

This guide covers local development and the one-time configuration needed to
operate this repository. To install the published SDK for use in your own
project, see the [README](README.md#installation).

## Local development and validation

Install Python, uv 0.13.10, `just`, and Git, then run:

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

Commits that change dependency or packaging configuration also check the lockfile.
Commits that change `pyproject.toml`, `uv.lock`, or `README.md` also run the
**Quantinuum pins** check (`just check-pins`), which needs network access to PyPI.
Run script tests explicitly with `just test-scripts 3.12` during development;
`just test-scripts` runs the suite on every supported Python minor. Distribution
installation tests run in CI and through `just test-package` or `just test-all`.

Hooks must be installed once per clone. The pre-commit executable lives in the
persistent project `.venv`; run `just setup` again after recreating it. The test
repositories disable Git hooks to avoid recursive test runs during commits.

The release and promotion workflows use `ghapi` with the bot account
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
metapackage metadata and every pinned dependency version. They resolve dependencies
as a consumer would, independently of the development lockfile. A third
environment installs the exported `pylock.toml` followed by the wheel without
dependencies, checking that the release lock file is complete and consistent.

GitHub CI runs on pull requests, the merge queue, explicit workflow dispatches,
and tagged-release validation. Script tests and the lockfile check run once on Ubuntu/Python 3.12,
matching the automation workflows. To limit runner usage, installation is tested
only on the oldest and newest CPython minor versions in the declared Python
range, one after the other in a single job per platform: `ubuntu-latest`,
`windows-latest`, `macos-latest` (Apple Silicon), and `macos-26-intel` (the latest
standard Intel macOS image). Intel macOS tests Python 3.13 as its newest version,
because Python 3.14 is not supported there. The explicit Intel label needs
updating when GitHub introduces a newer image. CI uses the same pytest runner as
the just recipes; `just test-package` covers every supported version locally.
The required **Installation checks** status covers the script tests, the RC
dependency freeze, the Quantinuum pin check, and the installation matrix. A new
push to a pull request cancels CI still running for its previous commit;
merge-queue, dispatched, and release-validation runs are never cancelled.

## One-time repository setup

1. Use `main` as the default development branch. Set `.github/preview.json` to
   the upcoming series and enable Actions. Under Settings → General → Pull
   Requests, allow squash merges with the default message **Pull request title
   and description** to preserve promotion footers, disable **Allow merge
   commits** and **Allow rebase merging**, enable **Allow auto-merge**, and
   enable **Automatically delete head branches**. Renovate chooses its
   auto-merge method from these settings, so leaving other methods enabled lets
   it request one that the release branch ruleset rejects.
2. Renovate runs in this repository's **Renovate** workflow
   (`.github/workflows/renovate.yml`), so no app installation is needed. It runs
   every four hours, on manual dispatch, when `renovate.json` changes on `main`,
   and when a maintainer checks a box in the Dependency Dashboard issue. It
   reads `renovate.json` from `main` and authenticates as the release bot with
   `HUGRBOT_PAT`, so its PRs trigger CI normally. The workflow sets the git
   author of its commits to the bot account; the commits are unsigned, because
   GitHub signs API commits only for GitHub App tokens. Update `RENOVATE_GIT_AUTHOR` in the
   workflow if the token's account changes.
3. Set `HUGRBOT_PAT` to the release bot account's personal access token. It needs
   Contents, Pull requests, and Issues read/write, plus Actions read permission
   for validating candidates. For Renovate, it also needs Commit statuses and
   Workflows read/write; Workflows lets Renovate update action versions in
   `.github/workflows`. Publication dispatch uses the job's built-in
   `GITHUB_TOKEN` with Actions write permission.
   The account must have repository access and any required organization/SSO
   authorization. The bot's login is resolved from the token. Renew it before
   expiry. The PAT allows bot-created PRs and releases to trigger CI.
4. Protect `main` and all `release/*` branches with two rulesets under
   repository Settings → Rules → Rulesets, because GitHub does not support
   merge queues on wildcard branch patterns. Both require PRs with squash
   merges only, the **Installation checks** status, and resolution of review
   conversations, and block force pushes and deletion.
   - The **main** ruleset targets the default branch. Enable **Require merge
     queue** with the squash merge method, so every PR is tested against the
     latest base branch and the PRs queued ahead of it before merging; the
     queue replaces requiring up-to-date branches. Keep **Only merge
     non-failing pull requests** enabled, so a PR whose own queue check fails,
     such as a Renovate PR held by the RC freeze, cannot merge as part of a
     later passing group.
   - The **release branches** ruleset targets `release/*`, so new numbered
     branches inherit it automatically. Require branches to be up to date
     before merging, and skip the status check requirement on branch creation
     so promotion can create a release branch from its RC.

   Require no approving reviews so the release bot can merge eligible Renovate
   and release PRs after CI. The release bot opens every release-branch PR and
   cannot approve its own PRs, so the **release branches** ruleset should also
   require the **Release review** status check
   (`.github/workflows/release-review.yml`). It enforces maintainer approval for
   everything except eligible patch updates; see
   [Merge queue](MAINTAINING.md#merge-queue). Add this check only once every supported
   release branch contains the workflow, because PRs into a branch without it
   would never receive the status. Additional human/code-owner review
   requirements prevent unattended merges until those reviews arrive. The bot
   does not bypass required checks. Limit release-branch creation to maintainers
   and the release bot if repository rules allow it.

   GitHub auto-merge waits only for required status checks. Without these
   rulesets, automatic merges by Renovate and the release bot can happen before
   CI finishes, so enable them before relying on the automation.
5. Leave `PYPI_PUBLISH_ENABLED` unset or `false` for GitHub-only publication.
   For a new series, use the beta/RC and promotion process in
   [Maintaining and releasing](MAINTAINING.md).

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
rerun **Validate and publish** with that release tag. For an RC, also
select the tag as the workflow ref. Setting the variable to `false` or removing
it disables subsequent PyPI uploads without disabling GitHub releases.

For dependency updates, preview releases, release series promotion, and publication
retries, see [Maintaining and releasing](MAINTAINING.md).
