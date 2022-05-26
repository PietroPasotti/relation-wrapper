from dataclasses import dataclass
from unittest.mock import Mock

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
from ops.charm import CharmBase, RelationDepartedEvent
from ops.testing import Harness

from endpoint_wrapper import Endpoint, _Endpoint, UnboundEndpointError

RELATION_NAME = "foo"


class MyCharm(CharmBase):
    META = yaml.safe_dump(
        {"name": "local", "requires": {RELATION_NAME: {"interface": "bar"}}}
    )

    def __init__(self, *args):
        super().__init__(*args)
        self.foo = Endpoint(
            self,
            "foo",
            requirer_template=bar_template,
            on_joined=self._handle_wrapped,
            on_broken=self._handle_wrapped,
        )

        self.framework.observe(self.on.foo_relation_departed,
                               self._handle_unwrapped)
        self.framework.observe(self.on.foo_relation_changed,
                               self._handle_unwrapped)

    def _handle_wrapped(self, event):
        self._callback(self, event)

    def _handle_unwrapped(self, event):
        self._callback(self, event)


@pytest.fixture
def provider_harness():
    h = Harness(MyCharm, meta=MyCharm.META)
    h.begin()
    return h


@pytest.fixture
def charm(provider_harness):
    return provider_harness.charm

@dataclass
class MockRelation:
    name: str
    id: int
    units = []
    app = None


def test_unwrapped_events(charm):
    def try_get_current(self, event):
        cur = self.foo.current

    charm._callback = try_get_current

    relation = MockRelation(name="foo", id=1)
    with pytest.raises(UnboundEndpointError):
        charm.on.foo_relation_departed.emit(relation)

    with pytest.raises(UnboundEndpointError):
        charm.on.foo_relation_changed.emit(relation)


def test_wrapped_events(charm):
    relation = MockRelation(name="foo", id=1)
    charm.foo._model.relations._data['foo'] = (relation, )

    def assert_wrapped(self, event):
        assert self.foo.current.relation is relation

    charm._callback = assert_wrapped

    charm.on.foo_relation_joined.emit(relation)
    charm.on.foo_relation_broken.emit(relation)
