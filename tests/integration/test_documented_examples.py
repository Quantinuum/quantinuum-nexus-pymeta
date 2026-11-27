"""Examples from the SDK components' documentation, run verbatim.

README examples are read from the installed packages' metadata, so they track
the pinned versions.
"""

import re
import runpy
import textwrap
from importlib.metadata import metadata

import pytest


def readme_examples(distribution):
    """Return the Python code blocks in an installed distribution's README."""
    package_metadata = metadata(distribution)
    readme = package_metadata.get_payload() or package_metadata["Description"]
    return re.findall(r"```python\n(.*?)```", readme, re.DOTALL)


def selene_examples():
    """Return the selene-sim README examples, in order.

    The README program passes lazy measurements to ``result()``, which Guppy
    rejects (https://github.com/Quantinuum/selene/issues/282), so they are
    collected first.
    """
    program, build, shots, noise, runtime = readme_examples("selene-sim")
    program = program.replace(
        "ms = measure_array(qubits)",
        "ms = collect_measurements(measure_array(qubits))",
    )
    return program, build, shots, noise, runtime


# From guppyalgos' getting-started guide, which is not in its package metadata.
GUPPYALGOS_GETTING_STARTED = """
from guppylang import guppy
from guppylang.std.quantum import discard_array
from guppyalgos.primitives.state_preparation import uniform_state
from guppyalgos.utils import qarray

uniform = uniform_state(4)


@guppy
def main() -> None:
    register = qarray(2)
    uniform(register)
    discard_array(register)


main.check()
main.compile()
"""


@pytest.fixture
def run_example(tmp_path):
    """Run example source from a file, as Guppy reads function source code."""

    def run(*snippets):
        path = tmp_path / "example.py"
        path.write_text(
            "\n".join(textwrap.dedent(s) for s in snippets), encoding="utf-8"
        )
        return runpy.run_path(str(path), run_name="example")

    return run


def test_guppylang_readme(run_example):
    [example] = readme_examples("guppylang")
    run_example(example)


def test_selene_readme_build_and_single_shots(run_example):
    program, build, shots, *_ = selene_examples()
    single_shots, _, _ = shots.partition("# run_shots")
    namespace = run_example(program, build, single_shots)
    assert len(namespace["shot"].entries[0][1]) == 10


def test_selene_readme_noise_and_runtime(run_example):
    program, build, _, noise, runtime = selene_examples()
    # Stim is imported by the preceding README example.
    namespace = run_example(
        program, build, "from selene_sim import Stim", noise, runtime
    )
    assert len(namespace["shots"].results) == 20


def test_guppyalgos_getting_started(run_example):
    run_example(GUPPYALGOS_GETTING_STARTED)
