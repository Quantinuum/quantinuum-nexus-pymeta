"""pytket circuits loaded into Guppy and tket passes applied to Guppy HUGR."""

import pytest
from guppylang import guppy
from guppylang.std.builtins import array, output
from guppylang.std.quantum import (
    cx,
    discard_array,
    h,
    measure,
    qubit,
    x,
)
from hugr.package import Package
from hugr.qsystem.result import QsysResult
from pytket import Circuit
from pytket.passes import RemoveRedundancies
from selene_sim import Stim, build
from tket.passes import Normalize, PytketHugrPass, QSystemRebasePass

bell_circuit = guppy.load_pytket(
    "bell_circuit", Circuit(2).H(0).CX(0, 1).measure_all(), use_arrays=True
)


@guppy
def run_bell_circuit() -> None:
    qs = array(qubit() for _ in range(2))
    bits = bell_circuit(qs)
    discard_array(qs)
    output("c", bits)


@guppy
def redundant_bell() -> None:
    a = qubit()
    b = qubit()
    h(a)
    h(a)
    h(a)
    cx(a, b)
    x(b)
    x(b)
    output("a", measure(a).read())
    output("b", measure(b).read())


def test_pytket_circuit_runs_inside_guppy(emulate, register_outcomes):
    result = emulate(run_bell_circuit, n_qubits=2, shots=50)
    assert register_outcomes(result, "c") == {"00", "11"}


@pytest.mark.parametrize(
    "hugr_pass",
    [PytketHugrPass(RemoveRedundancies()), QSystemRebasePass(), Normalize()],
    ids=lambda hugr_pass: type(hugr_pass).__name__,
)
def test_tket_passes_preserve_guppy_program_behaviour(hugr_pass):
    package = redundant_bell.compile()
    pass_result = hugr_pass.run(package.modules[0])
    optimised = Package(modules=[pass_result.hugr], extensions=package.extensions)
    result = QsysResult(
        build(optimised).run_shots(Stim(random_seed=1), n_qubits=2, n_shots=50)
    )
    outcomes = {tuple(sorted(dict(shot).items())) for shot in result.collated_counts()}
    assert outcomes == {(("a", "0"), ("b", "0")), (("a", "1"), ("b", "1"))}
