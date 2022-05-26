from itertools import chain

import pytest
import yaml
from conftest import mock_relation_data, reinit_charm
from ops.charm import CharmBase
from ops.testing import Harness

from endpoint_wrapper import Endpoint

RELATION_NAME = "foo"
LOCAL_APP = "local"
LOCAL_UNIT = "local/0"
REMOTE_APP = "remote"
REMOTE_UNIT = "remote/0"


class MyCharm(CharmBase):
    META = yaml.safe_dump(
        {"name": LOCAL_APP, "requires": {RELATION_NAME: {"interface": "bar"}}}
    )

    def __init__(self, *args):
        super().__init__(*args)
        self.foo = Endpoint(self, "foo")


@pytest.fixture
def harness():
    h = Harness(MyCharm, meta=MyCharm.META)
    h.begin()
    return h


@pytest.fixture
def relation_id(harness):
    return harness.add_relation(RELATION_NAME, REMOTE_APP)


# TODO check dataclass and pydantic mixing in Template
