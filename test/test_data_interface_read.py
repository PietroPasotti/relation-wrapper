from itertools import chain

import pytest
import yaml
from conftest import (
    ProviderAppModel,
    ProviderUnitModel,
    RequirerAppModel,
    RequirerUnitModel,
    bar_template,
    mock_relation_data,
    reinit_charm,
)
from ops.charm import CharmBase
from ops.testing import Harness

from endpoint_wrapper import Relations

RELATION_NAME = "foo"
LOCAL_APP = "local"
LOCAL_UNIT = "local/0"
REMOTE_APP = "remote"
REMOTE_UNIT = "remote/0"


class RequirerCharm(CharmBase):
    META = yaml.safe_dump(
        {"name": LOCAL_APP, "requires": {RELATION_NAME: {"interface": "bar"}}}
    )

    def __init__(self, *args):
        super().__init__(*args)
        self.foo = Relations(
            self,
            "foo",
            bar_template,
            on_joined=self._handle,
            on_broken=self._handle,
            on_departed=self._handle,
            on_changed=self._handle,
        )

        self.foo.relations[0].local_app_data

    def _handle(self, event):
        pass


@pytest.fixture
def harness():
    h = Harness(RequirerCharm, meta=RequirerCharm.META)
    h.begin()
    return h


@pytest.fixture
def relation_id(harness):
    return harness.add_relation(RELATION_NAME, REMOTE_APP)


def test_data_read_no_relation(harness):
    relations = harness.charm.foo
    # no data present
    assert not relations.remote_units_data
    assert not relations.remote_apps_data
    assert not relations.local_app_data
    assert not relations.local_unit_data


@pytest.fixture
def setup_relation(harness, relation_id):
    harness.add_relation_unit(relation_id, REMOTE_UNIT)
    reinit_charm(harness)


@pytest.fixture
def charm(harness, setup_relation) -> RequirerCharm:
    return harness.charm


@pytest.fixture
def relations(charm) -> Relations:
    return charm.foo


def test_data_read_no_data(relations):
    # no data present; but relations are; therefore we have remote units and remote apps
    assert relations.remote_units_data
    assert relations.remote_apps_data
    # however they are empty:
    for value in chain(
        relations.remote_apps_data.values(), relations.remote_units_data.values()
    ):
        assert value == {}

    # local app and unit data are empty
    for value in relations.local_app_data.values():
        assert value == {}
    for value in relations.local_unit_data.values():
        assert value == {}


def test_data_validation_no_data(relations):
    # all validations are None
    assert relations.remote_apps_valid is True  # There is no data, and we expect none
    assert relations.remote_units_valid is None  # There is no data, and we expect some
    assert relations.remote_valid is None  # worst of previous two
    assert relations.local_app_valid is None  # There is no data, and we expect some
    assert relations.local_unit_valid is True  # There is no data, and we expect none
    assert relations.local_valid is None  # worst of previous two
    assert relations.valid is None  # worst of previous


def test_data_validation_some_data(harness, relation_id, relations):
    mock_relation_data(
        harness,
        relation_id,
        {
            REMOTE_UNIT: {"bar": 42.42},
        },
    )

    assert relations.remote_apps_valid is True  # There is no data, and we expect none
    assert relations.remote_units_valid is True  # There is some data and it is valid
    assert relations.remote_valid is True  # worst of previous two
    assert relations.local_app_valid is None  # There is no data, and we expect some
    assert relations.local_unit_valid is True  # There is no data, and we expect none
    assert relations.local_valid is None  # worst of previous two
    assert relations.valid is None  # worst of previous


def test_data_validation_bad_data(harness, relation_id, relations):
    mock_relation_data(
        harness,
        relation_id,
        {
            REMOTE_UNIT: {"bar": "invalid data"},
        },
    )

    assert relations.remote_apps_valid is True  # There is no data, and we expect none
    assert relations.remote_units_valid is False  # There is some data and it is invalid
    assert relations.remote_valid is False  # worst of previous two
    assert relations.local_app_valid is None  # There is no data, and we expect some
    assert relations.local_unit_valid is True  # There is no data, and we expect none
    assert relations.local_valid is None  # worst of previous two
    assert relations.valid is False  # worst of previous


def test_data_validation_good_data(harness, relation_id, relations):
    mock_relation_data(
        harness,
        relation_id,
        {
            LOCAL_APP: {"foo": 42},
            REMOTE_UNIT: {"bar": 42.42},
        },
    )

    assert relations.remote_apps_valid is True  # There is no data, and we expect none
    assert relations.remote_units_valid is True  # There is some data and it is good
    assert relations.remote_valid is True  # worst of previous two
    assert relations.local_app_valid is True  # There is some data and it is good
    assert relations.local_unit_valid is True  # There is no data, and we expect none
    assert relations.local_valid is True  # worst of previous two
    assert relations.valid is True  # worst of previous


def test_invalid_data_read(harness, relation_id, relations):
    mock_relation_data(
        harness,
        relation_id,
        {
            LOCAL_APP: {"foo": "invalid data"},
        },
    )

    assert relations.valid is False
    # even though it's invalid, we can still read it
    assert relations.relations[0].local_app_data == {"foo": "invalid data"}
    assert relations.relations[0].local_unit_data == {}


def test_valid_data_read(harness, relation_id, relations):
    mock_relation_data(
        harness,
        relation_id,
        {
            LOCAL_APP: {"foo": 42},
            REMOTE_UNIT: {"bar": 42.42},
        },
    )

    assert relations.relations[0].local_app_data == {"foo": 42}
    assert relations.relations[0].local_unit_data == {}

    ops_relation = relations._relations[0]
    remote_app = ops_relation.app
    remote_unit = list(ops_relation.units)[0]

    assert relations.remote_apps_data[remote_app] == {}
    assert relations.remote_units_data[remote_unit] == {"bar": 42.42}
