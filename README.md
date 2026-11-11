# Quantinuum Nexus Python Metapackage

`quantinuum-nexus` installs a versioned set of Quantinuum's Python tools for
quantum programming, fault tolerance, local emulation, circuit compilation, and
access to Quantinuum Nexus. Install one SDK version to select the exact component
versions for that release instead of choosing each component version separately.

This is a Python **metapackage**: it contains dependency metadata, with no
additional Python API. After installation, use each component's own imports,
APIs, and documentation.

## Included tools

The SDK includes these six packages:

| Tool | Python package | Purpose |
| --- | --- | --- |
| Guppy | `guppylang` | Write hybrid quantum-classical programs in a language embedded in Python. |
| Guppy FT | `guppyft` | Write, compile, and run fault-tolerant Guppy programs. |
| Guppy Algorithms | `guppyalgos` | Work with quantum algorithms in the Guppy toolkit. |
| Selene | `selene-sim` | Emulate hybrid quantum-classical programs locally. |
| TKET | `pytket` | Build, transform, and optimize quantum circuits. |
| Nexus client | `qnexus` | Access the Quantinuum Nexus platform from Python. |

See the [Quantinuum documentation](https://docs.quantinuum.com/) for tutorials
and API references, and the
[platform release notes](https://docs.quantinuum.com/platform/releases/) for
component release notes and platform changes.

## Python and platform support

This release supports CPython 3.12, 3.13, and 3.14 on Linux, Windows, and macOS,
with one exception: **Python 3.14 is not supported on Intel macOS**. On Intel
Macs, use Python 3.12 or 3.13. This restriction also applies to an Intel Python
interpreter running through Rosetta on an Apple Silicon Mac; use a native ARM64
interpreter for Python 3.14.

Python 3.15 and later are outside this release's supported range. The pinned
`guppyalgos` version requires Python below 3.15.

## Installation

Releases are initially distributed through
[GitHub Releases](https://github.com/Quantinuum/quantinuum-nexus-pymeta/releases).
Download the wheel (`.whl`) attached to the release you want. In a directory
containing that single SDK wheel, add it to your uv project using:

```sh
uv add ./quantinuum_nexus-*.whl
```

Or install it into an existing activated virtual environment using:

```sh
uv pip install ./quantinuum_nexus-*.whl
```

Alternatively, use pip:

```sh
python -m pip install ./quantinuum_nexus-*.whl
```

These shell examples expand the wheel filename; you can also pass its exact
path. Dependencies are resolved from PyPI as usual. A GitHub release is ready
to install once its wheel and source distribution appear under release assets.

### Installing from PyPI

For releases also published to PyPI, add the SDK to your uv project using:

```sh
uv add quantinuum-nexus
```

Or install it into an existing activated virtual environment using:

```sh
uv pip install quantinuum-nexus
```

Alternatively, install it into that environment using pip:

```sh
python -m pip install quantinuum-nexus
```

Verify that the environment's installed dependencies are consistent with:

```sh
python -m pip check
```

There is no `quantinuum_nexus` module to import. Use the installed tools
directly, for example:

```python
from pytket import Circuit

circuit = Circuit(2).H(0).CX(0, 1)
```

### Dependency versions and reproducibility

Every SDK release uses exact pins for all dependencies. Updating the SDK version
is required to get new component versions, because a component's independent
release does not change an already published SDK release.

## Release cycle

SDK versions follow **`YY.SERIES.PATCH`** calendar versioning:

- **YY** is the two-digit year the release series begins, such as `26` for 2026.
- **SERIES** starts at 1 each year and increases for each new release series.
- **PATCH** starts at 0 and increases for compatible updates within a series.

New release series are published as needed, with no fixed schedule or annual
limit. The series number indicates release order within the year. Patches to an
existing series retain its year and series number, even when published in a
later year.

### Stable release series and patches

New release series may introduce breaking component changes. Review the release
notes and validate your application before moving to a new series.

Patch releases within a series are intended to preserve compatibility. The
stable dependency update process checks daily for eligible component updates:
minor and patch updates for components at version 1.0 or later, and patch updates
only for components below 1.0. Major component updates and pre-1.0 minor updates
are reserved for the upcoming series. A daily update check does not imply a new
SDK release every day.

For the two most recent stable series, component patch updates and their SDK
patch releases merge automatically after CI. Post-1.0 component minor updates
require human review of both the dependency PR and the resulting SDK patch
release PR. Older series can receive manually initiated patches. Stable
patches can continue while the next series is in preview.

### Betas and release candidates

Upcoming release series are offered as opt-in GitHub prereleases:

- **Beta** (`YY.SERIES.0bN`): a preview whose component versions can still
  change, including potentially breaking updates. Further previews increment
  the beta number.
- **Release candidate** (`YY.SERIES.0rcN`): the intended final component
  set, frozen except for reviewed fixes to blocking issues. Further fixes
  produce additional numbered release candidates.
- **Stable** (`YY.SERIES.0`): the first stable release in a series, using the
  chosen release candidate's exact direct dependency pins.

To try a preview from GitHub, download and install its wheel as described
above. For previews also published to PyPI, allow preview versions when adding
or upgrading the SDK in your uv project:

```sh
uv add --upgrade --prerelease allow quantinuum-nexus
```

Alternatively, use pip in an existing activated virtual environment:

```sh
python -m pip install --upgrade --pre quantinuum-nexus
```

## Repository guides

- [Development and repository setup](SETUP.md): local tools, validation commands,
  commit hooks, and one-time GitHub and PyPI configuration.
- [Maintaining and releasing](MAINTAINING.md): dependency updates, release
  workflows, beta and RC management, release series promotion, and publication retries.
