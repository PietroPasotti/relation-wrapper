from itertools import chain

import pytest
import yaml
from ops.charm import CharmBase
from ops.testing import Harness
from conftest import RequirerAppModel, RequirerUnitModel, \
    ProviderAppModel, ProviderUnitModel, bar_template, reinit_charm, \
    mock_relation_data
from relation import Relations, ValidationError, CannotWriteError, \
    CoercionError, InvalidFieldNameError

RELATION_NAME = 'foo'
LOCAL_APP = 'local'
LOCAL_UNIT = 'local/0'
REMOTE_APP = 'remote'
REMOTE_UNIT = 'remote/0'


class RequirerCharm(CharmBase):
    META = yaml.safe_dump(
        {
            'name': LOCAL_APP,
            'requires': {
                RELATION_NAME: {
                    'interface': 'bar'
                }
            }
        }
    )

    def __init__(self, *args):
        super().__init__(*args)
        self.foo = Relations(self, 'foo', bar_template,
                             on_joined=self._handle,
                             on_broken=self._handle,
                             on_departed=self._handle,
                             on_changed=self._handle)

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


@pytest.fixture(autouse=True)
def setup_relation(harness, relation_id):
    harness.add_relation_unit(relation_id, REMOTE_UNIT)
    reinit_charm(harness)


@pytest.fixture
def charm(harness, setup_relation) -> RequirerCharm:
    return harness.charm


@pytest.fixture
def relations(charm) -> Relations:
    return charm.foo


def mock_good_data(harness, relation_id):
    mock_relation_data(
        harness, relation_id,
        {
            LOCAL_APP: {'foo': 42},
            REMOTE_UNIT: {'bar': 42.42},
        }
    )


def mock_bad_data(harness, relation_id):
    mock_relation_data(
        harness, relation_id,
        {
            LOCAL_APP: {'foo': 'invalid data a'},
            LOCAL_UNIT: {'oepsie': 'daisie'},
            REMOTE_APP: {'oepsie': 'daisie'},
            REMOTE_UNIT: {'bar': 'invalid data b'}
        }
    )


def test_data_write_valid_data(harness, relation_id, relations):
    harness.set_leader(True)
    assert not harness.get_relation_data(relation_id, LOCAL_APP).get('foo')
    relations.relations[0].local_app_data['foo'] = 41
    assert harness.get_relation_data(relation_id, LOCAL_APP)['foo'] == '41'
    assert relations.relations[0].local_app_data['foo'] == 41
    assert relations.local_app_valid
    assert relations.remote_units_valid is None
    assert relations.valid is None

    # can't write remote data via relations
    harness.update_relation_data(relation_id, REMOTE_UNIT, {'bar': '41.41'})
    assert list(relations.relations[0].remote_units_data.values())[0]['bar'] == 41.41
    assert relations.valid


@pytest.mark.xfail  # not implemented yet
def test_write_data_setattr(harness, relation_id, relations):
    harness.set_leader(True)
    assert not harness.get_relation_data(relation_id, LOCAL_APP).get('foo')
    relations.relations[0].local_app_data.foo = 41
    assert harness.get_relation_data(relation_id, LOCAL_APP)['foo'] == '41'
    assert relations.relations[0].local_app_data.foo == 41


def test_data_overwrite_valid_data(harness, relation_id, relations):
    harness.set_leader(True)
    # set it up with valid data
    mock_good_data(harness, relation_id)
    assert harness.get_relation_data(relation_id, LOCAL_APP)['foo'] == 42

    # now overwrite it with more valid data
    relations.relations[0].local_app_data['foo'] = 41
    assert harness.get_relation_data(relation_id, LOCAL_APP)['foo'] == '41'
    assert relations.relations[0].local_app_data['foo'] == 41
    assert relations.valid


def test_data_write_invalid_data(harness, relation_id, relations):
    harness.set_leader(True)
    assert not harness.get_relation_data(relation_id, LOCAL_APP).get('foo')
    assert relations.valid is None

    with pytest.raises(ValidationError):
        relations.relations[0].local_app_data['foo'] = 'invalid data'

    # data not changed
    assert not harness.get_relation_data(relation_id, LOCAL_APP).get('foo')
    assert relations.valid is None


def test_data_overwrite_invalid_data(harness, relation_id, relations):
    harness.set_leader(True)
    # set it up with invalid data
    mock_bad_data(harness, relation_id)
    assert harness.get_relation_data(relation_id, LOCAL_APP)['foo'] == 'invalid data a'
    assert relations.valid is False

    # now overwrite it with bad data
    with pytest.raises(CoercionError):
        relations.relations[0].local_app_data['foo'] = 'even more invalid data'

    # data not changed
    assert harness.get_relation_data(relation_id, LOCAL_APP)['foo'] == 'invalid data a'
    assert relations.valid is False


def test_good_data_overwrite_invalid_data(harness, relation_id, relations):
    harness.set_leader(True)
    # set it up with good data
    mock_good_data(harness, relation_id)
    assert relations.valid

    # now overwrite it with bad data
    with pytest.raises(ValidationError):
        relations.relations[0].local_app_data['foo'] = 'even more invalid data'

    # data not changed
    assert harness.get_relation_data(relation_id, LOCAL_APP)['foo'] == 42
    assert relations.valid


def test_bad_data_overwrite_good_data(harness, relation_id, relations):
    harness.set_leader(True)
    # set it up with bad data
    mock_bad_data(harness, relation_id)
    assert relations.valid is False

    # now overwrite it with good data
    relations.relations[0].local_app_data['foo'] = 41
    assert relations.valid is False

    # we cannot write remote units from the charm, so we force it:
    mock_relation_data(
        harness, relation_id,
        {
            LOCAL_UNIT: {'oepsie': ''},
            REMOTE_APP: {'oepsie': ''},
            REMOTE_UNIT: {'bar': 41.41}
        }
    )
    assert relations.valid


@pytest.mark.parametrize('leader', ((True, False)))
def test_local_app_data_write_permissions(harness, relations, leader):
    harness.set_leader(leader)
    assert relations.local_app_data.can_write == leader
    # can write local app only if leader
    if leader:
        relations.local_app_data['foo'] = 41
    else:
        with pytest.raises(CannotWriteError):
            relations.local_app_data['foo'] = 41


@pytest.mark.parametrize('leader', ((True, False)))
def test_local_unit_data_write_permissions(harness, relations, leader):
    # can always write local unit
    harness.set_leader(leader)
    assert relations.local_unit_data.can_write == True
    with pytest.raises(InvalidFieldNameError):
        relations.local_unit_data['foo'] = '41'


@pytest.mark.parametrize('leader', ((True, False)))
def test_remote_entities_data_write_permissions(harness, relations, leader):
    # can never write remote entities
    harness.set_leader(leader)
    for rem_data in chain(relations.remote_units_data.values(),
                          relations.remote_units_data.values()):
        assert rem_data.can_write == False
        with pytest.raises(CannotWriteError):
            rem_data['foo'] = '41'


