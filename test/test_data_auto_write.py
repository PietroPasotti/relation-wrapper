from itertools import chain

import pytest
import yaml
from conftest import RequirerAppModel, mock_relation_data, reinit_charm
from ops.charm import CharmBase
from ops.testing import Harness

from endpoint_wrapper import (
    CannotWriteError,
    CoercionError,
    DataBagModel,
    Endpoint,
    InvalidFieldNameError,
    Template,
    ValidationError,
    _get_dataclass_defaults,
    _get_pydantic_defaults,
)

try:
    from pydantic import BaseModel

    class RequirerAppModelNoDefault(BaseModel):
        foo: int

    class RequirerUnitModelNoDefault(BaseModel):
        bar: str

    class RequirerAppModelDefault(BaseModel):
        foo: int = 1

    class RequirerUnitModelDefault(BaseModel):
        bar: str = "1"

except ModuleNotFoundError:
    # pydantic-free mode
    from dataclasses import dataclass

    @dataclass
    class RequirerAppModelNoDefault:
        foo: int

    @dataclass
    class RequirerUnitModelNoDefault:
        bar: str

    @dataclass
    class RequirerAppModelDefault:
        foo: int = 1

    @dataclass
    class RequirerUnitModelDefault:
        bar: str = "1"


no_default_template = Template(requirer=DataBagModel(unit=RequirerUnitModelNoDefault))
default_template = Template(requirer=DataBagModel(unit=RequirerUnitModelDefault))

RELATION_NAME = "foo"
LOCAL_APP = "local"
LOCAL_UNIT = "local/0"
REMOTE_APP = "remote"
REMOTE_UNIT = "remote/0"


@pytest.fixture(params=(True, False))
def defaulting(request):
    return request.param


@pytest.fixture
def template(defaulting):
    if defaulting:
        return default_template
    else:
        return no_default_template


@pytest.fixture
def charm(template):
    class MyCharm(CharmBase):
        META = yaml.safe_dump(
            {"name": LOCAL_APP, "requires": {RELATION_NAME: {"interface": "bar"}}}
        )

        def __init__(self, *args):
            super().__init__(*args)
            self.foo = Endpoint(self, "foo", provider_template=template)

    return MyCharm


def test_get_default_dc():
    from dataclasses import dataclass

    @dataclass
    class foo:
        a: int
        b: str
        bar: int = 1
        baz: str = "qux"

    assert _get_dataclass_defaults(foo) == {"bar": 1, "baz": "qux"}


def test_get_default_pydantic():
    try:
        import pydantic
    except ModuleNotFoundError:
        pytest.xfail("pydantic not installed")

    class foo(pydantic.BaseModel):
        a: int
        b: str
        bar: int = 1
        baz: str = "qux"

    assert _get_pydantic_defaults(foo) == {"bar": 1, "baz": "qux"}


def test_defaulted_data_written_automatically(charm, defaulting):
    harness = Harness(charm, meta=charm.META)
    harness.begin()
    harness.set_leader(True)

    # relation not initialized yet: there should be no data at all
    relations = harness.charm.foo
    with pytest.raises(KeyError):
        assert not relations.local_units_data[relations.local_unit]["bar"]
    with pytest.raises(KeyError):
        assert not relations.local_apps_data[relations.local_app]["foo"]

    relation_id = harness.add_relation(RELATION_NAME, REMOTE_APP)

    harness.add_relation_unit(relation_id, REMOTE_UNIT)
    reinit_charm(harness)
    relations = harness.charm.foo

    # if a default was given, it should be in the databags already.
    if defaulting:
        assert relations.relations[0].local_unit_data["bar"] == "1"
    else:
        with pytest.raises(KeyError):
            assert relations.relations[0].local_unit_data["bar"]
