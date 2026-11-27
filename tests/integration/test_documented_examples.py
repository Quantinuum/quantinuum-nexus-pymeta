"""Examples from the SDK components' README files, run verbatim.

Examples that fail against the pinned versions are marked ``xfail(strict=True)``
so a fix in either the documentation or the package is noticed. See
``tests/integration/REPORT.md`` for details of each failure.
"""

import runpy
import textwrap

import pytest
from guppylang_internals.error import GuppyError

GUPPYLANG_README = """
from guppylang import guppy
from guppylang.std.builtins import owned
from guppylang.std.quantum import cx, h, measure, qubit, x, z


@guppy
def teleport(src: qubit @ owned, tgt: qubit) -> None:
    \"\"\"Teleports the state in `src` to `tgt`.\"\"\"
    # Create ancilla and entangle it with src and tgt
    tmp = qubit()
    h(tmp)
    cx(tmp, tgt)
    cx(src, tmp)

    # Apply classical corrections
    h(src)
    if measure(src):
        z(tgt)
    if measure(tmp):
        x(tgt)


teleport.check()
"""

SELENE_README_PROGRAM = """
from guppylang import guppy
from guppylang.std.quantum import *
from hugr.qsystem.result import QsysShot, QsysResult

@guppy
def main() -> None:
    # allocate 10 qubits
    qubits = array(qubit() for _ in range(10))

    # prepare the 10-qubit GHZ state (|0000000000> + |1111111111>)/sqrt(2)
    h(qubits[0])
    for i in range(9):
        cx(qubits[i], qubits[i+1])

    # measure all qubits
    ms = measure_array(qubits)

    # report measurements to the results stream
    result("measurements", ms)

compiled_hugr = main.compile()
"""

# The README program with its measurements collected, so that the remaining
# README snippets can be checked independently of the compilation failure.
SELENE_PROGRAM_COLLECTED = SELENE_README_PROGRAM.replace(
    "ms = measure_array(qubits)",
    "ms = collect_measurements(measure_array(qubits))",
)

SELENE_README_BUILD = """
from selene_sim import build
runner = build(compiled_hugr)
"""

SELENE_README_SINGLE_SHOTS = """
from selene_sim import Quest, Stim
# run a single shot with Quest, the statevector simulator
shot = QsysShot(runner.run(simulator=Quest(), n_qubits=10))
print(shot)

# run a single shot with Stim, the stabilizer simulator
shot = QsysShot(runner.run(simulator=Stim(), n_qubits=10))
print(shot)
"""

SELENE_README_MULTI_SHOT = """
# run_shots runs efficient multi-shot simulations
# n_processes provides multi-processing across shots
# deterministic results can be achieved by providing a random seed
shots = QsysShot(runner.run(
    simulator=Stim(random_seed=5),
    n_qubits=10,
    n_shots=100,
    n_processes=8
))
print(shots)
"""

SELENE_README_NOISE = """
from selene_sim import DepolarizingErrorModel
error_model = DepolarizingErrorModel(
    random_seed=12478918,
    p_init=1e-3,
    p_meas=1e-2,
    p_1q=1e-5,
    p_2q=1e-6,
)

shots = QsysResult(runner.run_shots(
    simulator=Stim(
        random_seed=10
    ),
    error_model=error_model,
    n_qubits=10,
    n_shots=20,
    n_processes=4,
))
print(shots)

from selene_sim import SoftRZRuntime

shots = QsysResult(runner.run_shots(
    simulator=Stim(),
    runtime=SoftRZRuntime(),
    error_model=error_model,
    n_qubits=10,
    n_shots=20
))
print(shots)
"""

GUPPYFT_README = """
from guppylang import guppy
from guppylang.std.builtins import owned, output
from guppylang.std.quantum import cx, h, measure, qubit, x, z
from guppyft.code.steane.encode import SteaneBuilder


@guppy
def teleport() -> None:
    \"\"\"Teleports the state in `src` to `tgt`.\"\"\"
    src = qubit()

    tmp = qubit()
    tgt = qubit()
    h(tmp)
    cx(tmp, tgt)

    cx(src, tmp)
    h(src)
    if measure(src).read():
        z(tgt)
    if measure(tmp).read():
        x(tgt)

    output("tgt", measure(tgt).read())


# Use Steane architecture to encode the program
steane = SteaneBuilder().build(n_blocks=3)
teleport_encoded = steane.encode(teleport.compile())
"""

# From guppyalgos' getting-started guide.
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
        path.write_text("\n".join(textwrap.dedent(s) for s in snippets))
        return runpy.run_path(str(path), run_name="example")

    return run


def test_guppylang_readme(run_example):
    run_example(GUPPYLANG_README)


@pytest.mark.xfail(
    strict=True,
    raises=GuppyError,
    reason="REPORT.md#1: selene-sim README passes Measurement values to result()",
)
def test_selene_readme_program(run_example):
    run_example(SELENE_README_PROGRAM)


def test_selene_readme_build_and_single_shots(run_example):
    namespace = run_example(
        SELENE_PROGRAM_COLLECTED, SELENE_README_BUILD, SELENE_README_SINGLE_SHOTS
    )
    assert set(namespace["shot"].entries[0][1]) in ({0}, {1})


@pytest.mark.xfail(
    strict=True,
    raises=TypeError,
    reason="REPORT.md#2: selene-sim README passes n_shots to SeleneInstance.run()",
)
def test_selene_readme_multi_shot(run_example):
    run_example(
        SELENE_PROGRAM_COLLECTED,
        SELENE_README_BUILD,
        "from selene_sim import Stim",
        SELENE_README_MULTI_SHOT,
    )


def test_selene_readme_noise_and_runtime(run_example):
    namespace = run_example(
        SELENE_PROGRAM_COLLECTED,
        SELENE_README_BUILD,
        "from selene_sim import Stim",
        SELENE_README_NOISE,
    )
    assert len(namespace["shots"].results) == 20


@pytest.mark.xfail(
    strict=True,
    raises=TypeError,
    reason="REPORT.md#3: guppyft README calls SteaneBuilder().build(n_blocks=3)",
)
def test_guppyft_readme(run_example):
    run_example(GUPPYFT_README)


def test_guppyalgos_getting_started(run_example):
    run_example(GUPPYALGOS_GETTING_STARTED)
