from itertools import chain

import pytest
import yaml
from conftest import RequirerAppModel, bar_template, mock_relation_data, reinit_charm
from ops.charm import CharmBase
from ops.testing import Harness

from endpoint_wrapper import (
    CannotWriteError,
    CoercionError,
    Endpoint,
    InvalidFieldNameError,
    ValidationError,
    _Endpoint,
)

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


@pytest.fixture(params=[[0], [1]], ids=["setattr", "setitem"])
def write(request):
    if request.param:
        return setattr
    else:

        def _setitem(obj, key, value):
            obj[key] = value

        return _setitem


@pytest.fixture
def harness():
    h = Harness(RequirerCharm, meta=RequirerCharm.META)
    h.begin()
    return h


@pytest.fixture
def relation_id(harness):
    return harness.add_relation(RELATION_NAME, REMOTE_APP)


@pytest.fixture(autouse=True)
def setup_relation(harness, relation_id):
    harness.add_relation_unit(relation_id, REMOTE_UNIT)
    reinit_charm(harness)


@pytest.fixture
def charm(harness, setup_relation) -> RequirerCharm:
    return harness.charm


@pytest.fixture
def relations(charm) -> _Endpoint:
    return charm.foo


def mock_good_data(harness, relation_id):
    mock_relation_data(
        harness,
        relation_id,
        {
            LOCAL_APP: {"foo": 42},
            REMOTE_UNIT: {"bar": 42.42},
        },
    )


def mock_bad_data(harness, relation_id):
    mock_relation_data(
        harness,
        relation_id,
        {
            LOCAL_APP: {"foo": "invalid data a"},
            LOCAL_UNIT: {"oepsie": "daisie"},
            REMOTE_APP: {"oepsie": "daisie"},
            REMOTE_UNIT: {"bar": "invalid data b"},
        },
    )


def test_data_write_valid_data(harness, relation_id, relations, write):
    harness.set_leader(True)
    assert not harness.get_relation_data(relation_id, LOCAL_APP).get("foo")
    write(relations.relations[0].local_app_data, "foo", 41)
    assert harness.get_relation_data(relation_id, LOCAL_APP)["foo"] == "41"
    assert relations.relations[0].local_app_data["foo"] == 41
    assert relations._local_apps_data_valid
    assert relations._remote_units_data_valid is None
    assert relations.valid is None

    # can't write remote data via relations
    harness.update_relation_data(relation_id, REMOTE_UNIT, {"bar": "41.41"})
    assert list(relations.relations[0].remote_units_data.values())[0]["bar"] == 41.41
    assert relations.valid


@pytest.mark.xfail  # not implemented yet
def test_write_data_setattr(harness, relation_id, relations):
    harness.set_leader(True)
    assert not harness.get_relation_data(relation_id, LOCAL_APP).get("foo")
    relations.relations[0].local_app_data.foo = 41
    rel_data = harness.get_relation_data(relation_id, LOCAL_APP)
    assert rel_data is relations.relations[0].local_app_data.__datawrapper_params__.data
    assert rel_data["foo"] == "41"
    assert relations.relations[0].local_app_data.foo == 41


def test_data_overwrite_valid_data(harness, relation_id, relations, write):
    harness.set_leader(True)
    # set it up with valid data
    mock_good_data(harness, relation_id)
    assert harness.get_relation_data(relation_id, LOCAL_APP)["foo"] == 42

    # now overwrite it with more valid data
    write(relations.relations[0].local_app_data, "foo", 41)
    assert harness.get_relation_data(relation_id, LOCAL_APP)["foo"] == "41"
    assert relations.relations[0].local_app_data["foo"] == 41
    assert relations.valid


def test_data_write_invalid_data(harness, relation_id, relations, write):
    harness.set_leader(True)
    assert not harness.get_relation_data(relation_id, LOCAL_APP).get("foo")
    assert relations.valid is None

    with pytest.raises(ValidationError):
        write(relations.relations[0].local_app_data, "foo", "invalid data")

    # data not changed
    assert not harness.get_relation_data(relation_id, LOCAL_APP).get("foo")
    assert relations.valid is None


def test_data_overwrite_invalid_data(harness, relation_id, relations, write):
    harness.set_leader(True)
    # set it up with invalid data
    mock_bad_data(harness, relation_id)
    assert harness.get_relation_data(relation_id, LOCAL_APP)["foo"] == "invalid data a"
    assert relations.valid is False

    # now overwrite it with bad data
    with pytest.raises(CoercionError):
        write(relations.relations[0].local_app_data, "foo", "even more invalid data")

    # data not changed
    assert harness.get_relation_data(relation_id, LOCAL_APP)["foo"] == "invalid data a"
    assert relations.valid is False


def test_good_data_overwrite_invalid_data(harness, relation_id, relations, write):
    harness.set_leader(True)
    # set it up with good data
    mock_good_data(harness, relation_id)
    assert relations.valid

    # now overwrite it with bad data
    with pytest.raises(ValidationError):
        write(relations.relations[0].local_app_data, "foo", "even more invalid data")

    # data not changed
    assert harness.get_relation_data(relation_id, LOCAL_APP)["foo"] == 42
    assert relations.valid


def test_bad_data_overwrite_good_data(harness, relation_id, relations, write):
    harness.set_leader(True)
    # set it up with bad data
    mock_bad_data(harness, relation_id)
    assert relations.valid is False

    # now overwrite it with good data
    write(relations.relations[0].local_app_data, "foo", 41)
    assert relations.valid is False

    # we cannot write remote units from the charm, so we force it:
    mock_relation_data(
        harness,
        relation_id,
        {
            LOCAL_UNIT: {"oepsie": ""},
            REMOTE_APP: {"oepsie": ""},
            REMOTE_UNIT: {"bar": 41.41},
        },
    )
    assert relations.valid


@pytest.mark.parametrize("leader", ((True, False)))
def test_local_app_data_write_permissions(harness, relations, leader, write):
    harness.set_leader(leader)
    assert (
        relations.relations[0].local_app_data.__datawrapper_params__.can_write == leader
    )
    # can write local app only if leader
    if leader:
        write(relations.relations[0].local_app_data, "foo", 41)
    else:
        with pytest.raises(CannotWriteError):
            write(relations.relations[0].local_app_data, "foo", 41)


@pytest.mark.parametrize("leader", ((True, False)))
def test_local_unit_data_write_permissions(harness, relations, leader, write):
    # can always write local unit
    harness.set_leader(leader)
    assert (
        relations.relations[0].local_unit_data.__datawrapper_params__.can_write is True
    )
    with pytest.raises(InvalidFieldNameError):
        write(relations.relations[0].local_unit_data, "foo", "41")


@pytest.mark.parametrize("leader", ((True, False)))
def test_remote_entities_data_write_permissions(harness, relations, leader, write):
    # can never write remote entities
    harness.set_leader(leader)
    for rem_data in chain(
        relations.remote_units_data.values(), relations.remote_units_data.values()
    ):
        assert rem_data.__datawrapper_params__.can_write is False
        with pytest.raises(CannotWriteError):
            write(rem_data, "foo", "41")


def test_validator_dedup(harness, relations, relation_id, write):
    harness.set_leader(True)
    # set it up with valid data
    mock_good_data(harness, relation_id)

    # we get the local app databag
    local_app_data = relations.relations[0].local_app_data
    # we get the local unit databag
    local_unit_data = relations.relations[0].local_unit_data

    write(local_app_data, "foo", 41)
    with pytest.raises(InvalidFieldNameError):
        write(local_unit_data, "foo", 41)
