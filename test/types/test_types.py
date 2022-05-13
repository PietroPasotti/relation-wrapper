import re
from dataclasses import dataclass
from pathlib import Path
from subprocess import PIPE, Popen
from typing import Type

import pytest
from ops.charm import CharmBase

from endpoint_wrapper import (
    DataBagModel,
    DataWrapper,
    EndpointWrapper,
    Template,
    _EndpointWrapper,
)


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

    foo_prov = EndpointWrapper(charm, "relation_name", template, "provider")
    prov_relation = foo_prov.wrap(charm.model.relations[0])
    prov_remote_unit_data = prov_relation.remote_units_data[
        prov_relation.remote_units[0]
    ]
    prov_value_foo = (
        prov_remote_unit_data.foo  # pyright: expect-error Cannot access member "foo" for type "None"
    )
    prov_value_bar = (
        prov_remote_unit_data.bar  # pyright: expect-error Cannot access member "bar" for type "None"
    )


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


err = re.compile(r"(?P<file>.*):(?P<line>\d*):\d* - error: (?P<error>.*)")
decl = re.compile(r".*# pyright: expect-error(?P<reason> .*)?")


def test_types():
    this_file = Path(__file__)
    proc = Popen(["pyright", str(this_file)], stdout=PIPE)
    proc.wait()
    out = proc.stdout.read().decode("utf-8")  # type: ignore

    errors = err.findall(out)
    source_lines = this_file.read_text().split("\n")

    failures = []

    # check that all errors are expected
    for error in errors:
        file, line, reason = error
        if match := decl.match(source_lines[int(line) - 1]):
            groups = match.groups()
            expected_reason = groups[0]
            if expected_reason is not None and expected_reason.strip() != reason:
                failures.append(f"Expected failure for {expected_reason}; got {reason}")
        else:
            failures.append(", ".join(error))

    # todo: check that all expected failures occur
    assert not failures, "\n".join(failures)
