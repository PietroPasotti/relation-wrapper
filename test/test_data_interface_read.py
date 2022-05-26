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

from endpoint_wrapper import Endpoint, _Endpoint

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


@pytest.fixture(params=[[0], [1]], ids=["getattr", "getitem"])
def read(request):
    if request.param:
        return getattr
    else:

        def _getitem(obj, key):
            return obj[key]

        return _getitem


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
    assert not relations.local_apps_data
    assert not relations.local_units_data


@pytest.fixture
def setup_relation(harness, relation_id):
    harness.add_relation_unit(relation_id, REMOTE_UNIT)
    reinit_charm(harness)


@pytest.fixture
def charm(harness, setup_relation) -> RequirerCharm:
    return harness.charm


@pytest.fixture
def relations(charm) -> _Endpoint:
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
    for value in relations.local_apps_data.values():
        assert value == {}
    for value in relations.local_units_data.values():
        assert value == {}


def test_data_validation_no_data(relations):
    # all validations are None
    assert (
        relations._remote_apps_data_valid is True
    )  # There is no data, and we expect none
    assert (
        relations._remote_units_data_valid is None
    )  # There is no data, and we expect some
    assert relations.remote_valid is None  # worst of previous two
    assert (
        relations._local_apps_data_valid is None
    )  # There is no data, and we expect some
    assert (
        relations._local_units_data_valid is True
    )  # There is no data, and we expect none
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

    assert (
        relations._remote_apps_data_valid is True
    )  # There is no data, and we expect none
    assert (
        relations._remote_units_data_valid is True
    )  # There is some data and it is valid
    assert relations.remote_valid is True  # worst of previous two
    assert (
        relations._local_apps_data_valid is None
    )  # There is no data, and we expect some
    assert (
        relations._local_units_data_valid is True
    )  # There is no data, and we expect none
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

    assert (
        relations._remote_apps_data_valid is True
    )  # There is no data, and we expect none
    assert (
        relations._remote_units_data_valid is False
    )  # There is some data and it is invalid
    assert relations.remote_valid is False  # worst of previous two
    assert (
        relations._local_apps_data_valid is None
    )  # There is no data, and we expect some
    assert (
        relations._local_units_data_valid is True
    )  # There is no data, and we expect none
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

    assert (
        relations._remote_apps_data_valid is True
    )  # There is no data, and we expect none
    assert (
        relations._remote_units_data_valid is True
    )  # There is some data and it is good
    assert relations.remote_valid is True  # worst of previous two
    assert relations._local_apps_data_valid is True  # There is some data and it is good
    assert (
        relations._local_units_data_valid is True
    )  # There is no data, and we expect none
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


def test_valid_data_read(harness, relation_id, relations, read):
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

    assert read(relations.relations[0].local_app_data, "foo") == 42

    ops_relation = relations._relations[0]
    remote_app = ops_relation.app
    remote_unit = list(ops_relation.units)[0]

    assert relations.remote_apps_data[remote_app] == {}
    assert relations.remote_units_data[remote_unit] == {"bar": 42.42}

    assert read(relations.remote_units_data[remote_unit], "bar") == 42.42
