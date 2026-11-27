"""guppyalgos primitives and algorithms compiled with Guppy, emulated on Selene, and
lowered to QIR.

The ``emulate`` fixture runs Guppy's ``EmulatorBuilder``, which builds and runs the
program with Selene.
"""

import pytest
from guppyalgos.algorithms.phase_estimation.canonical_phase_estimation import qpe
from guppyalgos.primitives.arithmetic.adder.adder_ripple_cuccaro import (
    adder_ripple_cuccaro_mod,
)
from guppyalgos.primitives.state_preparation import ghz_state, uniform_state
from guppyalgos.primitives.subroutines.qft import iqft, qft
from guppyalgos.utils import qarray
from guppylang import guppy
from guppylang.std.angles import angle
from guppylang.std.builtins import output
from guppylang.std.quantum import (
    collect_measurements,
    crz,
    discard,
    h,
    measure_array,
    qubit,
    x,
)
from hugr_qir.hugr_to_qir import hugr_to_qir
from hugr_qir.output import OutputFormat
from quantinuum_qircheck import qircheck

uniform_over_4_states = uniform_state(4)


@guppy
def prepare_ghz() -> None:
    qs = qarray(4)
    ghz_state(qs)
    output("ghz", collect_measurements(measure_array(qs)))


@guppy
def prepare_uniform() -> None:
    qs = qarray(2)
    uniform_over_4_states(qs)
    output("u", collect_measurements(measure_array(qs)))


@guppy
def add_three_and_two() -> None:
    a = qarray(3)
    b = qarray(3)
    # Little-endian registers: a = 3, b = 2.
    x(a[0])
    x(a[1])
    x(b[1])
    adder_ripple_cuccaro_mod(a, b)
    output("a", collect_measurements(measure_array(a)))
    output("b", collect_measurements(measure_array(b)))


@guppy
def qft_roundtrip() -> None:
    qs = qarray(3)
    x(qs[0])
    x(qs[2])
    qft(qs)
    iqft(qs)
    output("r", collect_measurements(measure_array(qs)))


@guppy
def controlled_phase_power(control: qubit, target: qubit, power: int) -> None:
    # On target |1>, CRZ(3pi/2) kicks back a relative phase of 3/8 of a turn.
    crz(control, target, angle(1.5 * float(power)))


@guppy
def estimate_phase() -> None:
    phase = qarray(3)
    target = qubit()
    x(target)
    for i in range(3):
        h(phase[i])
    qpe(phase, target, controlled_phase_power)
    output("phase", collect_measurements(measure_array(phase)))
    discard(target)


def test_ghz_state_on_selene(emulate, register_outcomes):
    result = emulate(prepare_ghz, n_qubits=4, shots=50)
    assert register_outcomes(result, "ghz") == {"0000", "1111"}


def test_uniform_state_on_selene_covers_every_basis_state(emulate, register_outcomes):
    result = emulate(prepare_uniform, n_qubits=2, shots=200, stabilizer=False)
    assert register_outcomes(result, "u") == {"00", "01", "10", "11"}


def test_cuccaro_adder_on_selene(emulate):
    # Toffoli decompositions are non-Clifford, so use the statevector simulator.
    result = emulate(add_three_and_two, n_qubits=7, shots=5, stabilizer=False)
    counts = result.register_counts()
    assert counts["a"] == {"110": 5}
    assert counts["b"] == {"101": 5}  # 5, little-endian


def test_qft_followed_by_inverse_on_selene_is_identity(emulate):
    result = emulate(qft_roundtrip, n_qubits=3, shots=20, stabilizer=False)
    assert result.register_counts()["r"] == {"101": 20}


def test_phase_estimation_on_selene(emulate):
    result = emulate(estimate_phase, n_qubits=4, shots=20, stabilizer=False)
    # A phase of exactly 3/8 is read out deterministically as 3, little-endian.
    assert result.register_counts()["phase"] == {"110": 20}


@pytest.mark.parametrize(
    "entrypoint", [prepare_ghz, prepare_uniform], ids=["ghz", "uniform"]
)
def test_state_preparation_lowers_to_valid_qir(entrypoint):
    qir = hugr_to_qir(entrypoint.compile(), output_format=OutputFormat.LLVM_IR)
    qircheck(qir)
