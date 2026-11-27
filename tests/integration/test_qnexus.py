"""qnexus job inputs built from other SDK components, without contacting Nexus."""

import base64
import json
import uuid
from datetime import UTC, datetime

import httpx
import pytest
import qnexus as qnx
import qnexus.client.hugr
from guppylang import guppy
from guppylang.std.builtins import output
from guppylang.std.quantum import h, measure, qubit
from hugr.package import Package
from hugr.qsystem.result import QsysResult
from pydantic import TypeAdapter
from qnexus.exceptions import ResourceCreateFailed
from qnexus.models.annotations import Annotations
from qnexus.models.references import ProjectRef
from selene_sim import Stim


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


def test_hugr_upload_sends_a_runnable_guppy_program(monkeypatch, selene_build):
    requests = []

    def offline_nexus(request):
        requests.append(request)
        return httpx.Response(503, text="offline")

    monkeypatch.setattr(
        qnexus.client.hugr,
        "get_nexus_client",
        lambda: httpx.Client(
            base_url="https://nexus.invalid",
            transport=httpx.MockTransport(offline_nexus),
        ),
    )
    project = ProjectRef(
        id=uuid.uuid4(),
        annotations=Annotations(name="integration"),
        contents_modified=datetime.now(UTC),
        archived=False,
    )
    package = coin.compile()
    with pytest.raises(ResourceCreateFailed):
        qnx.hugr.upload(package, name="coin", project=project)

    [request] = requests
    data = json.loads(request.content)["data"]
    assert data["attributes"]["name"] == "coin"
    assert data["relationships"]["project"]["data"]["id"] == str(project.id)
    restored = Package.from_bytes(base64.b64decode(data["attributes"]["contents"]))
    assert restored.to_bytes() == package.to_bytes()
    result = QsysResult(
        selene_build(restored).run_shots(Stim(random_seed=1), n_qubits=1, n_shots=50)
    )
    assert set(result.register_counts()["c"]) == {"0", "1"}
