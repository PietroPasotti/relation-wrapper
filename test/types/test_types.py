from dataclasses import dataclass
from typing import Type

import pytest
from ops.charm import CharmBase
from pyright_test import pyright_test

from endpoint_wrapper import DataBagModel, EndpointWrapper, Template, _EndpointWrapper


def pyright_check_inversion() -> None:
    @dataclass
    class RUM:
        foo: float

    @dataclass
    class RAM:
        bar: str

    @dataclass
    class LUM:
        foo: str

    @dataclass
    class LAM:
        foo: int

    charm = CharmBase(None)  # type: ignore
    Prov_DBM = DataBagModel(unit=RUM, app=RAM)
    Req_DBM = DataBagModel(unit=LUM, app=LAM)
    template = Template(provider=Prov_DBM, requirer=Req_DBM)
    foo: _EndpointWrapper[Type[LAM], Type[LUM], Type[RAM], Type[RUM]] = EndpointWrapper(
        charm, "relation_name", template, "requirer"
    )
    inverted: _EndpointWrapper[
        Type[RAM], Type[RUM], Type[LAM], Type[LUM]
    ] = EndpointWrapper(charm, "relation_name", template, "provider")


def pyright_check_attr_types() -> None:
    @dataclass
    class RUM:
        foo: float

    @dataclass
    class RAM:
        bar: str

    @dataclass
    class LUM:
        foo: str

    @dataclass
    class LAM:
        foo: int

    charm = CharmBase(None)  # type: ignore
    Prov_DBM = DataBagModel(unit=RUM, app=RAM)
    Req_DBM = DataBagModel(unit=LUM, app=LAM)
    template = Template(provider=Prov_DBM, requirer=Req_DBM)
    foo = EndpointWrapper(charm, "relation_name", template, "requirer")
    relation = foo.wrap(charm.model.relations[0])

    valid = relation.remote_app_data_valid

    # LOCAL: so requirer
    local_app_data: Type[LAM] = relation.local_app_data
    value_foo_LAM: int = local_app_data.foo

    local_unit_data: Type[LUM] = relation.local_unit_data
    value_foo_LUM: str = local_unit_data.foo

    remote_unit_data: Type[RUM] = relation.remote_units_data[relation.remote_units[0]]
    value_foo_RUM: float = remote_unit_data.foo

    remote_app_data: Type[RAM] = relation.remote_app_data
    value_foo_RAM = (
        remote_app_data.foo  # pyright: expect-error Cannot access member "foo" for type "Type[RAM]"
    )
    value_bar_RAM: str = remote_app_data.bar


def pyright_check_partial_template_requirer() -> None:
    @dataclass
    class RUM:
        foo: int
        bar: str

    template = Template(provider=DataBagModel(unit=RUM))
    charm = CharmBase(None)  # type: ignore

    foo_req = EndpointWrapper(charm, "relation_name", template, "requirer")
    req_relation = foo_req.wrap(charm.model.relations[0])
    req_remote_unit_data = req_relation.remote_units_data[req_relation.remote_units[0]]
    req_value_foo = req_remote_unit_data.foo
    req_value_bar = req_remote_unit_data.bar


def pyright_check_partial_template_provider() -> None:
    @dataclass
    class RUM:
        foo: int
        bar: str

    template = Template(provider=DataBagModel(unit=RUM))
    charm = CharmBase(None)  # type: ignore

    foo_prov = EndpointWrapper(charm, "relation_name", provider_template=template)
    prov_relation = foo_prov.wrap(charm.model.relations[0])
    prov_remote_unit_data = prov_relation.remote_units_data[
        prov_relation.remote_units[0]
    ]
    reveal_type(prov_remote_unit_data)  # pyright: expect-type None
    # fmt: off
    prov_remote_unit_data.foo  # pyright: expect-error
    prov_remote_unit_data.bar  # pyright: expect-error
    # fmt: on


def pyright_check_pydantic_model() -> None:
    charm = CharmBase(None)  # type: ignore
    try:
        from pydantic import BaseModel  # type: ignore
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
    # local_app_data to be a DataWrapper[RequirerAppModel] so actually:
    data: Type[RequirerAppModel] = foo.relations[0].local_app_data


def test_with_pyright():
    pyright_test(__file__)
