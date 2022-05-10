from ops.testing import Harness

from endpoint_wrapper import DataBagModel, Template

try:
    from pydantic import BaseModel

    class RequirerAppModel(BaseModel):
        foo: int

    class RequirerUnitModel(BaseModel):
        pass

    class ProviderAppModel(BaseModel):
        pass

    class ProviderUnitModel(BaseModel):
        bar: float

except ModuleNotFoundError:
    # pydantic-free mode
    from dataclasses import dataclass

    @dataclass
    class RequirerAppModel:
        foo: int

    @dataclass
    class RequirerUnitModel:
        pass

    @dataclass
    class ProviderAppModel:
        pass

    @dataclass
    class ProviderUnitModel:
        bar: float


bar_template = Template(
    requirer=DataBagModel(app=RequirerAppModel, unit=RequirerUnitModel),
    provider=DataBagModel(app=ProviderAppModel, unit=ProviderUnitModel),
)


def reinit_charm(harness: Harness):
    charm = harness._charm
    harness._charm = None
    harness.framework._forget(charm)
    harness.framework._forget(charm.on)
    harness.framework._forget(charm.foo)
    harness.begin()


def mock_relation_data(harness, relation_id, mapping: dict):
    for key, value in mapping.items():
        harness.update_relation_data(relation_id, key, value)
