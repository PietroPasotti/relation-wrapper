import json
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
        self.foo = Relations(self, 'foo')


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


def mock_data(harness, relation_id):
    mock_relation_data(
        harness, relation_id,
        {
            LOCAL_APP: {'a': 42},
            REMOTE_UNIT: {'b': 42.42},
        }
    )


def test_read_mocked_data(relations, harness, relation_id):
    mock_data(harness, relation_id)
    assert relations.local_app_data['a'] == 42
    assert next(iter(relations.remote_units_data.values()))['b'] == 42.42

    harness.set_leader(True)
    relations.local_app_data['foo'] = 'bar'
    relations.local_app_data['choo'] = 43
    sample_jsn = {'1': 2, 'a': {'2': 3.3}}
    relations.local_app_data['jsn'] = sample_jsn

    assert harness.get_relation_data(relation_id, LOCAL_APP)['jsn'] == json.dumps(sample_jsn)

    assert relations.local_app_data['foo'] == 'bar'
    assert relations.local_app_data['choo'] == 43
    assert relations.local_app_data['jsn'] == sample_jsn