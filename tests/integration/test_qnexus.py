"""qnexus job inputs built from other SDK components, without contacting Nexus."""

import base64

import pytest
import qnexus as qnx
from guppylang import guppy
from guppylang.std.builtins import output
from guppylang.std.quantum import h, measure, qubit
from hugr.package import Package
from hugr.qsystem.result import QsysResult
from pydantic import TypeAdapter
from qnexus.client.hugr import _encode_hugr
from selene_sim import Stim, build


@guppy
def coin() -> None:
    q = qubit()
    h(q)
    output("c", measure(q).read())


@pytest.mark.parametrize(
    "config",
    [
        qnx.SeleneConfig(simulator=qnx.models.StabilizerSimulator()),
        qnx.SelenePlusConfig(),
        qnx.HeliosConfig(system_name="Helios-1E"),
        qnx.QuantinuumConfig(device_name="H2-1LE"),
    ],
    ids=lambda config: type(config).__name__,
)
def test_backend_configs_roundtrip_through_the_schema_union(config):
    restored = TypeAdapter(qnx.BackendConfig).validate_json(config.model_dump_json())
    assert restored == config


def test_hugr_upload_encoding_preserves_a_runnable_guppy_program():
    package = coin.compile()
    # The private encoder is what qnx.hugr.upload sends to Nexus.
    restored = Package.from_bytes(base64.b64decode(_encode_hugr(package)))
    assert restored.to_bytes() == package.to_bytes()
    result = QsysResult(
        build(restored).run_shots(Stim(random_seed=1), n_qubits=1, n_shots=50)
    )
    assert set(result.register_counts()["c"]) == {"0", "1"}
