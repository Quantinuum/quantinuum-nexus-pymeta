"""Guppy programs encoded with guppyft codes and emulated on Selene.

``build_emulator`` builds Guppy's ``EmulatorBuilder``, which runs the encoded
physical program with Selene.
"""

import pytest
from guppyft.code.steane.encode import SteaneBuilder
from guppyft.code.toy_k2.encode import ToyK2Builder
from guppylang import guppy
from guppylang.std.builtins import output
from guppylang.std.quantum import cx, h, measure, qubit, x, z
from hugr.package import Package
from hugr_qir.hugr_to_qir import hugr_to_qir
from selene_sim import DepolarizingErrorModel


@guppy
def bell_pair() -> None:
    a = qubit()
    b = qubit()
    h(a)
    cx(a, b)
    output("a", measure(a).read())
    output("b", measure(b).read())


@guppy
def teleport_one() -> None:
    src = qubit()
    x(src)
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


@pytest.mark.parametrize(
    ("code", "n_qubits"),
    [
        (SteaneBuilder.new(n_blocks=2).build(), 30),
        (ToyK2Builder().build(2), 12),
    ],
    ids=["steane", "toy_k2"],
)
def test_encoded_bell_pair_on_selene_is_logically_correlated(
    build_emulator, code, n_qubits
):
    encoded = code.encode(bell_pair.compile())
    assert isinstance(encoded, Package)

    result = (
        build_emulator(encoded, n_qubits=n_qubits)
        .stabilizer_sim()
        .with_seed(2)
        .with_shots(20)
        .run()
    )
    assert set(result.collated_counts()) == {
        (("a", "0"), ("b", "0")),
        (("a", "1"), ("b", "1")),
    }


@pytest.fixture(scope="module")
def steane_teleport_emulator(build_emulator):
    steane = SteaneBuilder.new(n_blocks=3).build()
    encoded = steane.encode(teleport_one.compile())
    # Three logical blocks of 7 physical qubits, plus ancillas for syndrome
    # extraction.
    return build_emulator(encoded, n_qubits=30).stabilizer_sim().with_seed(3)


def test_steane_encoded_teleportation_on_selene(steane_teleport_emulator):
    result = steane_teleport_emulator.with_shots(10).run()
    assert result.register_counts()["tgt"] == {"1": 10}


def test_steane_encoded_teleportation_on_noisy_selene(steane_teleport_emulator):
    noise = DepolarizingErrorModel(
        random_seed=5, p_init=1e-3, p_1q=1e-4, p_2q=1e-3, p_meas=1e-3
    )
    result = steane_teleport_emulator.with_error_model(noise).with_shots(50).run()
    # Low physical noise should rarely flip the logical outcome.
    assert result.register_counts()["tgt"]["1"] >= 45


@pytest.mark.xfail(
    strict=True,
    raises=ValueError,
    reason=(
        "reports/2026-11-27-sdk-integration.md#4: "
        "hugr-qir fails to emit LLVM for guppyft-encoded programs"
    ),
)
def test_steane_encoded_program_lowers_to_qir():
    steane = SteaneBuilder.new(n_blocks=3).build()
    hugr_to_qir(steane.encode(teleport_one.compile()))
