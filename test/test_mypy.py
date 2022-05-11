from dataclasses import dataclass
from typing import Type

import pytest
from ops.charm import CharmBase

from endpoint_wrapper import DataBagModel, DataWrapper, EndpointWrapper, Template


@pytest.mark.xfail  # todo: find a way to test mypy output
def test_1() -> None:
    @dataclass
    class RUM:
        foo: int
        bar: str

    @dataclass
    class RAM:
        bar: str

    @dataclass
    class LUM:
        foo: int
        bar: str

    @dataclass
    class LAM:
        foo: int
        bar: str

    charm = CharmBase(None)  # type: ignore
    Prov_DBM = DataBagModel(unit=RUM, app=RAM)
    Req_DBM = DataBagModel(unit=LUM, app=LAM)
    template = Template(provider=Prov_DBM, requirer=Req_DBM)
    foo = EndpointWrapper(charm, "relation_name", template, "requirer")
    reveal_type(foo)
    relation = foo.wrap(charm.model.relations[0])

    valid = relation.remote_app_data_valid

    # LOCAL: so requirer
    local_app_data = relation.local_app_data
    reveal_type(local_app_data)  # expect: LAM

    local_unit_data = relation.local_unit_data
    reveal_type(local_unit_data)  # expect: LUM

    remote_unit_data = relation.remote_units_data[relation.remote_units[0]]
    reveal_type(remote_unit_data)  # expect: RUM

    remote_app_data = relation.remote_app_data
    reveal_type(remote_app_data)  # expect: RAM

    int_value_foo = remote_app_data.foo
    reveal_type(int_value_foo)  # expect: builtins.int


@pytest.mark.xfail  # todo: find a way to test mypy output
def test_2() -> None:
    @dataclass
    class RUM:
        foo: int
        bar: str

    charm = CharmBase(None)  # type: ignore
    Prov_DBM = DataBagModel(unit=RUM)
    template = Template(
        provider=Prov_DBM
    )  # should give error: requirer remote unit data has no foo
    foo_req = EndpointWrapper(charm, "relation_name", template, "requirer")
    req_relation = foo_req.wrap(charm.model.relations[0])
    foo = EndpointWrapper(charm, "relation_name", template, "provider")
    relation = foo.wrap(charm.model.relations[0])

    req_remote_unit_data = req_relation.remote_units_data[relation.remote_units[0]]
    fail_int_value_foo = (
        req_remote_unit_data.foo
    )  # error: "None" has no attribute "Foo"


@pytest.mark.xfail  # todo: find a way to test mypy output
def test_3() -> None:
    charm = CharmBase(None)  # type: ignore
    try:
        from pydantic import BaseModel
    except ModuleNotFoundError:
        pytest.xfail("no-pydantic case")

    class RequirerAppModel(BaseModel):
        foo: int

    class ProviderUnitModel(BaseModel):
        bar: float

    template = Template(
        requirer=DataBagModel(
            app=RequirerAppModel,
        ),
        provider=DataBagModel(unit=ProviderUnitModel),
    )
    foo = EndpointWrapper(
        charm,
        "foo",
        template=template,
        # we can omit `role` and it will be guessed from META, but if we do
        # provide it, we get nice type hints below
        role="requirer",
    )

    # We are the requirer, and our template says that the local app data
    # model for the requirer is RequirerAppModel; so we expect
    # local_app_data to be a DataWrapper[RequirerAppModel]
    data: Type[RequirerAppModel] = foo.relations[0].local_app_data
