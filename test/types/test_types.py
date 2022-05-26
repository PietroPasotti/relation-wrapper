import os
from dataclasses import dataclass
from pathlib import Path
from typing import Type

import pytest
from ops.charm import CharmBase
from pyright_test import pyright_test

from endpoint_wrapper import DataBagModel, Endpoint, Template, _Endpoint


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
    foo: _Endpoint[Type[LAM], Type[LUM], Type[RAM], Type[RUM]] = Endpoint(
        charm, "relation_name", requirer_template=template
    )
    inverted: _Endpoint[
        Type[RAM], Type[RUM], Type[LAM], Type[LUM]
    ] = Endpoint(charm, "relation_name", provider_template=template)


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
    foo = Endpoint(charm, "relation_name", requirer_template=template)
    relation = foo.wrap(charm.model.relations[0])

    valid = relation._remote_app_data_valid

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

    foo_req = Endpoint(charm, "relation_name", requirer_template=template)
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

    foo_prov = Endpoint(charm, "relation_name", provider_template=template)
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
    foo = Endpoint(
        charm,
        "foo",
        requirer_template=template,
    )

    # We are the requirer, and our template says that the local app data
    # model for the requirer is RequirerAppModel; so we expect
    # local_app_data to be a DataWrapper[RequirerAppModel] so actually:
    data: Type[RequirerAppModel] = foo.relations[0].local_app_data


def test_with_pyright():
    root = Path(os.getcwd()).absolute()
    # dashed name: in github CI pipelines it seems that _ is converted to -
    while root.name not in ['relation-wrapper', 'relation_wrapper']:
        root = root.parent
        if root.name == '':
            raise ValueError('you need to call this function from a '
                             f'(subfolder of) relation_wrapper; not {Path(os.getcwd()).absolute()}')

    pyright_test(__file__, root)
