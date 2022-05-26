import pytest
import yaml
from conftest import (
    ProviderAppModel,
    ProviderUnitModel,
    RequirerAppModel,
    RequirerUnitModel,
    bar_template,
    reinit_charm,
)
from ops.charm import CharmBase
from ops.testing import Harness

from endpoint_wrapper import Endpoint, _Endpoint

RELATION_NAME = "foo"


class RequirerCharm(CharmBase):
    META = yaml.safe_dump(
        {"name": "local", "requires": {RELATION_NAME: {"interface": "bar"}}}
    )

    def __init__(self, *args):
        super().__init__(*args)
        self.foo = Endpoint(
            self,
            "foo",
            requirer_template=bar_template,
            on_joined=self._handle,
            on_broken=self._handle,
            on_departed=self._handle,
            on_changed=self._handle,
        )

    def _handle(self, event):
        pass


@pytest.fixture
def requirer_harness():
    h = Harness(RequirerCharm, meta=RequirerCharm.META)
    h.begin()
    return h


@pytest.fixture(autouse=True)
def setup_requirer_relation(requirer_harness):
    remote_app = "remote"
    remote_unit = "remote/0"
    r_id = requirer_harness.add_relation(RELATION_NAME, remote_app)
    requirer_harness.add_relation_unit(r_id, remote_unit)
    reinit_charm(requirer_harness)


@pytest.fixture
def requirer_charm(requirer_harness) -> RequirerCharm:
    return requirer_harness.charm


@pytest.fixture
def requirer_relations(requirer_charm) -> _Endpoint:
    return requirer_charm.foo


def test_relations_model_from_charm_requirer(requirer_relations):
    # check that local models resolve to requirer models
    assert requirer_relations._relation_model.local_app_data_model is RequirerAppModel
    assert requirer_relations._relation_model.local_unit_data_model is RequirerUnitModel
    assert requirer_relations._relation_model.remote_app_data_model is ProviderAppModel
    assert (
        requirer_relations._relation_model.remote_unit_data_model is ProviderUnitModel
    )


def test_relations_interface_requirer(requirer_relations, requirer_charm):
    assert len(requirer_relations.relations) == 1  # one relation currently active
    assert requirer_relations.relations[0].relation.name == "foo"
    assert requirer_relations.relations[0].remote_app.name == "remote"
    assert requirer_relations.relations[0].local_app.name == "local"
