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


class ProviderCharm(CharmBase):
    META = yaml.safe_dump(
        {"name": "local", "provides": {RELATION_NAME: {"interface": "bar"}}}
    )

    def __init__(self, *args):
        super().__init__(*args)
        self.foo = Endpoint(
            self,
            "foo",
            provider_template=bar_template,
            on_joined=self._handle,
            on_broken=self._handle,
            on_departed=self._handle,
            on_changed=self._handle,
        )

    def _handle(self, event):
        pass


@pytest.fixture
def provider_harness():
    h = Harness(ProviderCharm, meta=ProviderCharm.META)
    h.begin()
    return h


@pytest.fixture(autouse=True)
def setup_provider_relation(provider_harness):
    remote_app = "remote"
    remote_unit = "remote/0"
    r_id = provider_harness.add_relation(RELATION_NAME, remote_app)
    provider_harness.add_relation_unit(r_id, remote_unit)
    reinit_charm(provider_harness)


@pytest.fixture
def provider_charm(provider_harness) -> ProviderCharm:
    return provider_harness.charm


@pytest.fixture
def provider_relations(provider_charm) -> _Endpoint:
    return provider_charm.foo


def test_relations_model_from_charm_provider(provider_relations):
    # check that local models resolve to provider models
    assert provider_relations._relation_model.local_app_data_model is ProviderAppModel
    assert provider_relations._relation_model.local_unit_data_model is ProviderUnitModel
    assert provider_relations._relation_model.remote_app_data_model is RequirerAppModel
    assert (
        provider_relations._relation_model.remote_unit_data_model is RequirerUnitModel
    )


def test_relations_interface_provider(provider_relations, provider_charm):
    assert len(provider_relations.relations) == 1  # one relation currently active
    assert provider_relations.relations[0].relation.name == "foo"
    assert provider_relations.relations[0].remote_app.name == "remote"
    assert provider_relations.relations[0].local_app.name == "local"
